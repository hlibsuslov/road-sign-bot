# 🇳🇴 Дорожні знаки 2026 — Telegram bot

Telegram-бот для вивчення норвезьких дорожніх знаків ([@roadsigns2026_bot](https://t.me/roadsigns2026_bot)).
Картковий формат (flashcards) із зображеннями знаків, категоріями, темами оформлення
та трекінгом прогресу. Інтерфейс — українською / англійською.

## Можливості

- **Онбординг** — вибір мови вивчення (норвезька / англійська) та мови перекладу.
- **Картки** — знак + опис; кнопки «вже знаю» / «показати ще» для повторення.
- **Категорії** — навігація по групах знаків.
- **Налаштування** — зміна теми оформлення, мови, скидання прогресу.
- **Статистика** — прогрес вивчення (`/stats`).
- **Перевірка цілісності** — на старті бот валідує наявність зображень для всіх
  знаків і виключає ті, для яких картинки відсутні.

## Стек

- Python 3.13
- [aiogram](https://docs.aiogram.dev) 3.17 (long-polling, FSM на `MemoryStorage`)
- [Pillow](https://python-pillow.org) — обробка зображень знаків
- SQLite — прогрес користувачів

## Структура

```
.
├── bot.py              # хендлери, FSM, точка входу (start_polling)
├── database.py         # SQLite-шар (прогрес, налаштування)
├── keyboards.py        # inline / reply клавіатури
├── utils.py            # завантаження знаків, пошук та обробка зображень
├── data/
│   ├── signs_main.json # основна база знаків
│   ├── signs_extra.json
│   ├── signs_list.txt
│   └── images/         # зображення знаків (*.jpg)
├── Dockerfile          # multi-stage, non-root user `bot`
├── docker-compose.yml  # сервіс road-sign-bot + том bot-db
├── requirements.txt
└── .env.example        # шаблон змінних оточення
```

## Змінні оточення

Скопіюй `.env.example` у `.env` і заповни (див. коментарі у файлі):

| Змінна      | Опис                                              |
|-------------|---------------------------------------------------|
| `BOT_TOKEN` | Токен бота від [@BotFather](https://t.me/BotFather) (обовʼязково) |
| `DB_PATH`   | Шлях до SQLite-файлу (у проді — `/app/db/...` на томі) |

`.env` у `.gitignore` — секрети ніколи не комітяться.

## Запуск через Docker (рекомендовано)

```bash
cp .env.example .env       # і вписати BOT_TOKEN
docker compose up -d --build
docker compose logs -f
```

Особливості compose-стека:

- `build: .` — образ збирається локально (multi-stage, запускається від non-root `bot`).
- `env_file: .env` — змінні передаються в контейнер.
- Том **`bot-db`** змонтований на `/app/db` — база прогресу переживає перебудови.
- Ліміти: `mem_limit: 128m`, `cpus: 0.5`, `pids_limit: 128`.
- `no-new-privileges`, `STOPSIGNAL SIGINT` для коректного завершення polling.
- `autoheal=true` — рестарт контейнера у разі unhealthy (через зовнішній autoheal).

## Локальний запуск (без Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export BOT_TOKEN=...    # і за потреби DB_PATH=road_signs_bot.db
python -u bot.py
```
