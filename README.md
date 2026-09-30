# BI-аналитика: портфолио скриптов и кейсов

Репозиторий содержит обезличенный код на Python и SQL по проектам в BI, ETL и внедрении AI.

Названия компаний, продуктов и партнёрских сетей удалены. Ключи только из переменных окружения.

## Стек

- **Языки:** Python (pandas, requests), SQL
- **Базы данных:** PostgreSQL, ClickHouse
- **BI:** DataLens
- **API:** Яндекс Метрика, Яндекс Директ, VK Реклама, AmoCRM, GetCourse, Sipuni
- **AI:** YandexGPT, Yandex SpeechKit, промпт-инжиниринг

## Структура и кейсы

### 1. ETL: рекламные расходы и сквозная аналитика

- **Папка:** `etl_ad_spend/`
- **Файл:** `etl_direct_vk.py`
- **Что делает:** забирает расходы по API Яндекс Директа и VK Рекламы, приводит их к одной таблице в pandas и загружает в ClickHouse.

```bash
python etl_ad_spend/etl_direct_vk.py --demo
```

### 2. Антифрод: cookie stuffing в CPA

- **Папка:** `antifraud_cpa/`
- **Файл:** `fraud_detection.py`
- **Что делает:** по сырым логам ищет пользователя, у которого источник сменился с платного канала на CPA быстрее чем за 60 секунд.

```bash
python antifraud_cpa/fraud_detection.py
```

### 3. AI: разбор звонков отдела продаж

- **Папка:** `ai_call_analysis/`
- **Файл:** `call_to_llm_pipeline.py`
- **Промпт:** `yandexgpt_prompt_example.txt`
- **Что делает:** принимает ссылку на запись звонка, отправляет аудио в Yandex SpeechKit и текст в YandexGPT. Ответ — JSON, не свободный пересказ.

```bash
python ai_call_analysis/call_to_llm_pipeline.py --demo
```

Живой вызов SpeechKit и YandexGPT включается флагом `--live` и ключами из `.env`.

### 4. SQL-витрина

- **Файл:** `sql_data_mart.sql`
- Дневная витрина для DataLens: лиды, оплаты, выручка, расход, CPL, ROMI и накопленная выручка по каналу.

## Запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

В `.env` подставляются свои ключи. Файл в git не попадает.
