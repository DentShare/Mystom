"""AI-сервис: распознавание голоса (Whisper) и парсинг текста/изображений (GPT-4o-mini)."""
import json
import logging
import base64
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

from app.config import Config

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
    return _client


@dataclass
class ParsedBooking:
    """Результат парсинга голосового/текстового сообщения."""
    patient_name: Optional[str] = None
    date_str: Optional[str] = None       # "2026-03-15" или None
    time_str: Optional[str] = None       # "14:30" или None
    service: Optional[str] = None
    raw_text: str = ""
    confidence: float = 0.0              # 0-1
    unclear_fields: list = field(default_factory=list)  # ["date", "time", ...]


async def transcribe_voice(voice_file_bytes: bytes) -> str:
    """Транскрипция голосового сообщения через Whisper."""
    client = _get_client()
    # Whisper принимает файл — создаём виртуальный .ogg файл
    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=("voice.ogg", voice_file_bytes, "audio/ogg"),
        language="ru",
    )
    text = response.text.strip()
    logger.info("Whisper transcription: %s", text[:100])
    return text


async def parse_image_for_booking(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Извлечение текста из скриншота через GPT-4o-mini vision."""
    client = _get_client()
    b64 = base64.b64encode(image_bytes).decode()

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты помощник стоматолога. Из изображения извлеки информацию о записи на прием: "
                    "имя пациента, дату, время, услугу. Ответь обычным текстом на русском, "
                    "как если бы ты описывал запись словами. Например: "
                    "'Иванов Иван, 15 марта в 14:30, лечение кариеса'. "
                    "Если чего-то не видно на изображении — не придумывай, просто опусти."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Извлеки данные о записи на прием из этого изображения:"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                ],
            },
        ],
        max_tokens=300,
    )
    text = response.choices[0].message.content.strip()
    logger.info("Image parsing result: %s", text[:100])
    return text


async def parse_booking_text(raw_text: str) -> ParsedBooking:
    """Парсинг текста (из голоса или изображения) в структурированные данные."""
    client = _get_client()
    today = date.today()

    system_prompt = f"""Ты помощник стоматолога. Из текста извлеки данные о записи на приём.
Сегодня: {today.isoformat()} ({_weekday_ru(today)}).

Верни JSON (и ТОЛЬКО JSON, без markdown):
{{
  "patient_name": "ФИО пациента или null",
  "date": "YYYY-MM-DD или null",
  "time": "HH:MM или null",
  "service": "название услуги или null",
  "confidence": 0.8,
  "unclear": ["список неясных полей, например date, time"]
}}

Правила:
- Если сказано "завтра" → {(today + timedelta(days=1)).isoformat()}
- Если сказано "послезавтра" → {(today + timedelta(days=2)).isoformat()}
- Если сказано "в понедельник/вторник/..." → ближайший такой день начиная с завтра
- Если сказано "в 2" или "в два" → "14:00" (рабочие часы)
- Если сказано "в 9 утра" → "09:00"
- Имя пациента может быть в любом падеже — верни в именительном
- Услуга: "лечение", "удаление", "консультация", "чистка", "имплантация" и т.д.
- confidence: 0-1, насколько уверен в правильности парсинга"""

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_text},
        ],
        max_tokens=300,
        temperature=0.1,
    )

    content = response.choices[0].message.content.strip()
    # Убираем markdown обёртку если есть
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("GPT returned invalid JSON: %s", content[:200])
        return ParsedBooking(raw_text=raw_text, unclear_fields=["all"])

    result = ParsedBooking(
        patient_name=data.get("patient_name"),
        date_str=data.get("date"),
        time_str=data.get("time"),
        service=data.get("service"),
        raw_text=raw_text,
        confidence=data.get("confidence", 0.5),
        unclear_fields=data.get("unclear", []),
    )
    logger.info("Parsed booking: name=%s, date=%s, time=%s, service=%s, conf=%.1f",
                result.patient_name, result.date_str, result.time_str,
                result.service, result.confidence)
    return result


def _weekday_ru(d: date) -> str:
    days = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return days[d.weekday()]
