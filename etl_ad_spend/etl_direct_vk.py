"""Расходы Яндекс Директа и VK Рекламы → одна таблица → ClickHouse.

Демонстрационный скрипт: без боевых кабинетов и без сумм из отчётов.
Ключи читаются из окружения. Запуск без сети: python etl_direct_vk.py --demo
"""

from __future__ import annotations

import argparse
import io
import os
import time
from pathlib import Path

import pandas as pd
import requests

_ROOT = Path(__file__).resolve().parents[1]
_DIRECT_REPORTS = "https://api.direct.yandex.com/json/v5/reports"
_VK_STATS = "https://ads.vk.com/api/v2/statistics/ad_plans/day.json"


def _load_dotenv(path: Path) -> None:
    """Подхватить .env, не перетирая уже заданные переменные."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def fetch_direct(token: str, login: str, date_from: str, date_to: str) -> pd.DataFrame:
    """Отчёт Директа приходит TSV. returnMoneyInMicros=false — сумма уже в валюте кабинета, не в микроединицах."""
    body = {
        "params": {
            "SelectionCriteria": {"DateFrom": date_from, "DateTo": date_to},
            "FieldNames": ["Date", "CampaignName", "Cost"],
            "ReportName": "portfolio_direct_spend",
            "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "YES",
            "IncludeDiscount": "NO",
        }
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Login": login,
        "Accept-Language": "ru",
        "processingMode": "auto",
        "returnMoneyInMicros": "false",
        "skipReportHeader": "true",
        "skipReportSummary": "true",
    }
    # Отчёт может собираться не с первого ответа: 201/202 — подождать и повторить.
    for _ in range(20):
        response = requests.post(_DIRECT_REPORTS, json=body, headers=headers, timeout=60)
        if response.status_code == 200:
            frame = pd.read_csv(io.StringIO(response.text), sep="\t")
            frame = frame.rename(columns={"Date": "day", "CampaignName": "campaign", "Cost": "cost"})
            frame["channel"] = "yandex"
            return frame[["day", "channel", "campaign", "cost"]]
        if response.status_code in (201, 202):
            time.sleep(2)
            continue
        response.raise_for_status()
    raise TimeoutError("Яндекс Директ не отдал отчёт")


def fetch_vk(token: str, date_from: str, date_to: str) -> pd.DataFrame:
    """Дневная статистика кампаний VK Рекламы. Сумма в ответе — строка, приводим к числу."""
    response = requests.get(
        _VK_STATS,
        params={"date_from": date_from, "date_to": date_to, "metrics": "base"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    rows = []
    for item in response.json().get("items", []):
        campaign = str(item.get("id") or "")
        for row in item.get("rows", []):
            base = row.get("base") or {}
            rows.append(
                {
                    "day": row.get("date"),
                    "channel": "vk",
                    "campaign": campaign,
                    "cost": base.get("spent"),
                }
            )
    frame = pd.DataFrame(rows, columns=["day", "channel", "campaign", "cost"])
    frame["cost"] = pd.to_numeric(frame["cost"], errors="coerce").fillna(0)
    return frame


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    """Одинаковые имена колонок и день как дата. Пустые кампании не кладём в витрину."""
    out = frame.copy()
    out["day"] = pd.to_datetime(out["day"], errors="coerce").dt.date
    out["cost"] = pd.to_numeric(out["cost"], errors="coerce").fillna(0)
    out["campaign"] = out["campaign"].fillna("").astype(str).str.strip()
    out = out.dropna(subset=["day"])
    out = out[out["campaign"] != ""]
    return out.groupby(["day", "channel", "campaign"], as_index=False)["cost"].sum()


def load_clickhouse(frame: pd.DataFrame) -> None:
    """INSERT через HTTP ClickHouse. Пароль не пишется в код."""
    url = os.environ["CLICKHOUSE_URL"].rstrip("/")
    database = os.environ.get("CLICKHOUSE_DATABASE", "demo")
    query = f"INSERT INTO {database}.ad_spend FORMAT JSONEachRow"
    payload = frame.assign(day=frame["day"].astype(str)).to_json(orient="records", lines=True)
    response = requests.post(
        url,
        params={"query": query},
        data=payload.encode("utf-8"),
        auth=(os.environ.get("CLICKHOUSE_USER", ""), os.environ.get("CLICKHOUSE_PASSWORD", "")),
        timeout=60,
    )
    response.raise_for_status()


def demo_frame() -> pd.DataFrame:
    """Фиктивные строки, чтобы показать форму таблицы без кабинетов."""
    return pd.DataFrame(
        [
            {"day": "2026-09-01", "channel": "yandex", "campaign": "campaign_a", "cost": 1000},
            {"day": "2026-09-01", "channel": "vk", "campaign": "campaign_b", "cost": 500},
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Свести расходы Директа и VK в одну таблицу")
    parser.add_argument("--demo", action="store_true", help="Не ходить в API, показать форму таблицы")
    parser.add_argument("--date-from", default="2026-09-01")
    parser.add_argument("--date-to", default="2026-09-07")
    args = parser.parse_args()

    _load_dotenv(_ROOT / ".env")
    if args.demo:
        print(normalize(demo_frame()).to_string(index=False))
        return

    direct = fetch_direct(
        os.environ["YANDEX_DIRECT_TOKEN"],
        os.environ["YANDEX_DIRECT_LOGIN"],
        args.date_from,
        args.date_to,
    )
    vk = fetch_vk(os.environ["VK_ADS_TOKEN"], args.date_from, args.date_to)
    ready = normalize(pd.concat([direct, vk], ignore_index=True))
    load_clickhouse(ready)
    print(f"загружено строк: {len(ready)}")


if __name__ == "__main__":
    main()
