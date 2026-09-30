"""Cookie stuffing: CPA-событие сразу после платного клика того же пользователя.

Демонстрация на sample_logs.csv. Боевые логи и названия партнёрских сетей не используются.
Правило из кейса: смена источника на CPA меньше чем за 60 секунд после cpc/cpm.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

_SAMPLE = Path(__file__).resolve().parent / "sample_logs.csv"
_WINDOW_SEC = 60
_PAID_MEDIUMS = {"cpc", "cpm"}
_CPA_MEDIUMS = {"cpa", "affiliate"}


def find_stuffing(logs: pd.DataFrame, window_sec: int = _WINDOW_SEC) -> pd.DataFrame:
    """Для каждого CPA-события берём ближайший предыдущий платный клик того же user_id."""
    frame = logs.copy()
    frame["event_time"] = pd.to_datetime(frame["event_time"], errors="coerce")
    frame["medium"] = frame["medium"].astype(str).str.lower()
    frame = frame.dropna(subset=["user_id", "event_time"])

    paid = frame.loc[frame["medium"].isin(_PAID_MEDIUMS), ["user_id", "event_time", "source"]]
    paid = paid.rename(columns={"event_time": "paid_time", "source": "paid_source"})
    paid = paid.sort_values(["paid_time", "user_id"], kind="mergesort")

    cpa = frame.loc[frame["medium"].isin(_CPA_MEDIUMS), ["user_id", "event_time", "source"]]
    cpa = cpa.rename(columns={"event_time": "cpa_time", "source": "cpa_source"})
    cpa = cpa.sort_values(["cpa_time", "user_id"], kind="mergesort")
    if paid.empty or cpa.empty:
        return cpa.iloc[0:0]

    nearest = pd.merge_asof(
        cpa,
        paid,
        left_on="cpa_time",
        right_on="paid_time",
        by="user_id",
        direction="backward",
    )
    delta = (nearest["cpa_time"] - nearest["paid_time"]).dt.total_seconds()
    stolen = nearest.loc[delta.gt(0) & delta.le(window_sec)].copy()
    stolen["delta_sec"] = delta.loc[stolen.index].astype(int)
    return stolen.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Найти CPA-хиты сразу после платного клика")
    parser.add_argument("--logs", type=Path, default=_SAMPLE)
    args = parser.parse_args()

    stolen = find_stuffing(pd.read_csv(args.logs))
    if stolen.empty:
        print("аномалий нет")
        return
    print(stolen.to_string(index=False))


if __name__ == "__main__":
    main()
