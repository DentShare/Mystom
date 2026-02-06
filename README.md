# MiniStom - Telegram Bot для стоматологов

Полнофункциональный Telegram-бот для стоматологов с тремя уровнями подписки (Basic, Standard, Premium).

## Возможности

### Базовый уровень (Basic)
- Регистрация врача с полной информацией
- Визитка врача с геолокацией
- Календарь и запись пациентов
- Просмотр расписания

### Стандартный уровень (Standard)
- База данных пациентов
- Умный поиск пациентов
- История болезни
- Управление визитами (отмена, перенос)
- Имплантологическая карта с генерацией PDF

### Премиум уровень (Premium)
- Финансовый учет (суммы, скидки, способы оплаты)
- Зубная формула и детальные записи лечения
- Прайс-лист услуг
- Генерация PDF счетов
- Экспорт данных в Excel

## Установка

1. Клонируйте репозиторий
2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` на основе `.env.example` и заполните его:
```bash
cp .env.example .env
```

5. Настройте базу данных PostgreSQL и укажите `DATABASE_URL` в `.env`

6. Примените миграции:
```bash
alembic upgrade head
```

7. Запустите бота:
```bash
python -m app.main
```

## Структура проекта

```
MiniStom/
├── app/
│   ├── main.py                 # Точка входа
│   ├── config.py               # Конфигурация
│   ├── database/               # Модели и работа с БД
│   ├── middleware/             # Middleware для проверки подписок
│   ├── handlers/               # Обработчики команд
│   ├── keyboards/              # Клавиатуры
│   ├── services/               # Бизнес-логика
│   ├── states/                 # FSM состояния
│   └── utils/                  # Утилиты
├── templates/                  # HTML шаблоны для PDF
├── static/                     # Статические файлы
└── alembic/                    # Миграции БД
```

## Технологии

- Python 3.10+
- aiogram 3.x
- PostgreSQL
- SQLAlchemy (Async)
- Alembic
- WeasyPrint (PDF)
- openpyxl (Excel)

## Лицензия

MIT

