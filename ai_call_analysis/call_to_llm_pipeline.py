"""Вебхук телефонии → SpeechKit → YandexGPT.

Демонстрация. Боевые ключи, внутренние причины отказа и сырые записи звонков сюда не входят.
--demo показывает тело запроса в YandexGPT на учебной расшифровке и в сеть не ходит.
--live скачивает запись по ссылке, распознаёт её отложенной моделью SpeechKit и разбирает промптом.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parents[1]
_PROMPT_PATH = _ROOT / "yandexgpt_prompt_example.txt"
_SAMPLE_TRANSCRIPT = Path(__file__).resolve().parent / "sample_transcript.txt"
_STT_START = "https://stt.api.cloud.yandex.net/stt/v3/recognizeFileAsync"
_STT_RESULT = "https://stt.api.cloud.yandex.net/stt/v3/getRecognition"
_OPERATIONS = "https://operation.api.cloud.yandex.net/operations"
_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def audio_url_from_webhook(payload: dict) -> str:
    """Ссылка на запись из вебхука. Имя поля у разных АТС отличается."""
    for key in ("call_record_link", "record_url", "audio_url"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def transcribe(audio: bytes, api_key: str, folder_id: str) -> str:
    """Отложенное распознавание SpeechKit: дешевле синхронного, для потока звонков это важно."""
    headers = {"Authorization": f"Api-Key {api_key}", "x-folder-id": folder_id}
    started = requests.post(
        _STT_START,
        headers=headers,
        json={
            "content": _b64(audio),
            "recognitionModel": {
                "model": "deferred-general",
                "audioFormat": {"containerAudio": {"containerAudioType": "MP3"}},
                "languageRestriction": {
                    "restrictionType": "WHITELIST",
                    "languageCode": ["ru-RU"],
                },
            },
        },
        timeout=120,
    )
    started.raise_for_status()
    operation_id = str(started.json().get("id") or "")
    if not operation_id:
        raise RuntimeError("SpeechKit не вернул id операции")

    for _ in range(60):
        time.sleep(3)
        operation = requests.get(f"{_OPERATIONS}/{operation_id}", headers=headers, timeout=30)
        operation.raise_for_status()
        state = operation.json()
        if not state.get("done"):
            continue
        if state.get("error"):
            raise RuntimeError(str(state["error"]))
        result = requests.get(
            _STT_RESULT,
            headers=headers,
            params={"operation_id": operation_id},
            timeout=120,
        )
        result.raise_for_status()
        return _text_from_events(result.text)
    raise TimeoutError("SpeechKit не успел отдать текст")


def analyze(transcript: str, prompt: str, api_key: str, folder_id: str) -> dict:
    """YandexGPT: в messages поле text, не content. Иначе API отвечает 400."""
    response = requests.post(
        _GPT_URL,
        headers={
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": folder_id,
            "Content-Type": "application/json",
        },
        json={
            "modelUri": f"gpt://{folder_id}/yandexgpt-lite/latest",
            "completionOptions": {"stream": False, "temperature": 0.2, "maxTokens": "2000"},
            "messages": [
                {"role": "system", "text": prompt},
                {"role": "user", "text": transcript[:12000]},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    text = response.json()["result"]["alternatives"][0]["message"]["text"]
    return _parse_json(text)


def _b64(audio: bytes) -> str:
    import base64

    return base64.b64encode(audio).decode("ascii")


def _text_from_events(body: str) -> str:
    """В ответе SpeechKit несколько JSON-событий. Берём финальные куски, не черновики."""
    parts: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = event.get("result") if isinstance(event.get("result"), dict) else event
        final = result.get("final") if isinstance(result, dict) else None
        alternatives = (final or {}).get("alternatives") if isinstance(final, dict) else None
        if alternatives:
            text = str(alternatives[0].get("text") or "").strip()
            if text:
                parts.append(text)
    return " ".join(parts)


def _parse_json(text: str) -> dict:
    """Модель иногда оборачивает JSON в ```json ... ```."""
    raw = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("ответ модели — не JSON-объект")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Разобрать запись звонка через SpeechKit и YandexGPT")
    parser.add_argument("--demo", action="store_true", help="Показать запрос на учебной расшифровке, без сети")
    parser.add_argument("--live", action="store_true", help="Реальный вызов API по ссылке из --audio-url")
    parser.add_argument("--audio-url", default="")
    args = parser.parse_args()

    _load_dotenv(_ROOT / ".env")
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    transcript = _SAMPLE_TRANSCRIPT.read_text(encoding="utf-8")

    if args.demo or not args.live:
        print("демо: в сеть не хожу. Так выглядит запрос в YandexGPT:\n")
        print(
            json.dumps(
                {
                    "modelUri": "gpt://<folder>/yandexgpt-lite/latest",
                    "messages": [
                        {"role": "system", "text": prompt[:180] + "..."},
                        {"role": "user", "text": transcript},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    api_key = os.environ["YANDEX_API_KEY"]
    folder_id = os.environ["YANDEX_FOLDER_ID"]
    audio_url = args.audio_url or audio_url_from_webhook({})
    if not audio_url:
        raise SystemExit("Для --live нужна --audio-url")
    audio = requests.get(audio_url, timeout=60).content
    text = transcribe(audio, api_key, folder_id)
    print(json.dumps(analyze(text, prompt, api_key, folder_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
