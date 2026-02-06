# MiniStom — веб-админка (Web App)

Веб-интерфейс для админов: просмотр пользователей подписки, ручная выдача уровней (Basic / Standard / Premium) и установка срока подписки.

## Возможности

- Список пользователей: ФИО, Telegram ID, уровень, дата окончания подписки
- Изменение уровня подписки (0 = Basic, 1 = Standard, 2 = Premium)
- Установка или сброс даты окончания подписки
- Открывается из Telegram по кнопке в команде `/admin` (кнопка «Админка (Web App)»)

## Требования

- Запуск из **корня проекта** MiniStom (рядом с `app/`, `admin_webapp/`)
- В `.env` должны быть: `BOT_TOKEN`, `DATABASE_URL`, `ADMIN_IDS`
- Для кнопки в боте: в `.env` задать **ADMIN_WEBAPP_URL** (см. ниже)

## Запуск локально

Из корня проекта:

```bash
# Установить зависимости основного проекта (если ещё не установлены)
pip install -r requirements.txt

# Запуск веб-админки на порту 8001
uvicorn admin_webapp.main:app --reload --port 8001
```

Откройте в браузере: http://localhost:8001  

**Важно:** из браузера по прямой ссылке авторизация не пройдёт (нет initData от Telegram). Для проверки API можно временно отключить проверку в коде или открывать админку **только из бота** (кнопка в `/admin`).

## Подключение как Telegram Web App

1. **Разместите приложение по HTTPS**  
   Telegram открывает Web App только по HTTPS. Варианты:
   - Сервер с nginx + SSL (Let's Encrypt)
   - Туннель (ngrok, cloudflared) для разработки
   - Хостинг с HTTPS (Railway, Render, VPS и т.п.)

2. **Укажите URL в боте**  
   В `.env` в корне проекта добавьте:
   ```env
   ADMIN_WEBAPP_URL=https://ваш-домен.com
   ```
   Перезапустите бота. В команде `/admin` появится кнопка «Админка (Web App)».

3. **Настройка в BotFather (по желанию)**  
   - Откройте [@BotFather](https://t.me/BotFather)
   - Команда `/mybots` → выберите бота → **Bot Settings** → **Menu Button** → **Configure menu button**
   - Укажите URL вашей админки и текст кнопки (например: «Админка»)

Тогда кнопка меню в чате с ботом будет открывать админку. Либо оставьте только кнопку в ответе на `/admin`.

## Безопасность

- Доступ к API имеют только пользователи из **ADMIN_IDS** (их Telegram ID в `.env`).
- Запросы к `/api/users` и `/api/users/:id` проверяют подпись **initData** от Telegram (без неё запрос извне бота не пройдёт).

## API (для разработки)

- `GET /api/me` — проверка авторизации (initData в заголовке `X-Telegram-Init-Data`).
- `GET /api/users` — список пользователей (поля: id, telegram_id, full_name, subscription_tier, subscription_end_date).
- `PATCH /api/users/{id}` — обновить пользователя. Тело: `{"subscription_tier": 0|1|2, "subscription_end_date": "YYYY-MM-DD" | null}`.

Во всех запросах передаётся заголовок:  
`X-Telegram-Init-Data: <строка initData из Telegram.WebApp.initData>`.
