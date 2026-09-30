"""Учебный разбор звонка: расшифровка + файл промпта → JSON от YandexGPT.

Боевой промпт и ключи работодателя здесь не используются.
Ключи берутся из окружения, не из кода.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

# Тот же REST, что в Yandex Cloud: в messages поле text, не content.
_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
_ROOT = Path(__file__).resolve().parent
_DEFAULT_PROMPT = _ROOT / "prompts" / "call_quality_v2.txt"
_DEFAULT_TRANSCRIPT = _ROOT / "examples" / "transcript_price.txt"


def _load_dotenv(path: Path) -> None:
    """Подхватить .env, если переменных ещё нет в окружении."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _parse_json(text: str) -> dict:
    """Модель иногда оборачивает JSON в ```json ... ```."""
    raw = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("ответ модели — не JSON-объект")
    return data


def analyze(transcript: str, prompt: str, api_key: str, folder_id: str) -> dict:
    """Один запрос в YandexGPT. temperature низкая: нужен стабильный JSON, не сочинение."""
    body = {
        "modelUri": f"gpt://{folder_id}/yandexgpt-lite/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.2,
            "maxTokens": "2000",
        },
        "messages": [
            {"role": "system", "text": prompt},
            {"role": "user", "text": transcript[:12000]},
        ],
    }
    response = requests.post(
        _GPT_URL,
        headers={
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": folder_id,
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload["result"]["alternatives"][0]["message"]["text"]
    return _parse_json(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Разобрать расшифровку звонка промптом из файла")
    parser.add_argument("--prompt", type=Path, default=_DEFAULT_PROMPT)
    parser.add_argument("--transcript", type=Path, default=_DEFAULT_TRANSCRIPT)
    args = parser.parse_args()

    _load_dotenv(_ROOT / ".env")
    api_key = os.environ.get("YANDEX_API_KEY", "").strip()
    folder_id = os.environ.get("YANDEX_FOLDER_ID", "").strip()
    if not api_key or not folder_id:
        print("Нужны YANDEX_API_KEY и YANDEX_FOLDER_ID. Скопируйте .env.example в .env.", file=sys.stderr)
        return 1

    result = analyze(
        args.transcript.read_text(encoding="utf-8"),
        args.prompt.read_text(encoding="utf-8"),
        api_key,
        folder_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
