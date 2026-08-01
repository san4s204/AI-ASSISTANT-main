# CHESS IT — Telegram AI-менеджер

Сервис запускает основной Telegram-бот, через который продавец подключает
собственного Telegram-бота с ИИ, Google Docs/Sheets, памятью диалога,
Google Calendar, голосовыми сообщениями и подпиской.

## Быстрый запуск

1. Создайте локальный файл окружения:

   ```bash
   cp .env.example .env
   ```

2. Заполните как минимум:

   ```dotenv
   BOT_TOKEN=...
   OPEN_ROUTER_API_KEY=...
   LLM_MODEL=openai/gpt-5.4-mini
   ```

   Секреты из `.env` нельзя добавлять в Git.

3. Запустите приложение:

   ```bash
   docker compose up -d --build
   ```

4. Проверьте конфигурацию и соединения:

   ```bash
   docker compose exec app python scripts/diagnose.py
   docker compose logs --tail=200 app
   ```

При первом запуске приложение само создаёт таблицы SQLite. Рабочая база
находится в `db.db` и подключается в контейнер как `/app/db.db`.

## Настройка модели

По умолчанию используется `openai/gpt-5.4-mini`: она подходит для
диалогового менеджера и значительно дешевле Pro-версии.

```dotenv
LLM_MODEL=openai/gpt-5.4-mini
LLM_MAX_OUTPUT_TOKENS=700
LLM_TIMEOUT_SECONDS=90
LLM_MAX_ATTEMPTS=2
```

Для другого OpenAI-совместимого провайдера задайте `LLM_API_URL`,
`LLM_API_KEY` и соответствующее значение `LLM_MODEL`.

## Проверки

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

Тесты не обращаются к боевым Telegram, Google или LLM API и не расходуют
баланс провайдера.

## Резервная копия

```bash
make backup
```

Копии SQLite сохраняются в `backups/`, которая исключена из Git.
