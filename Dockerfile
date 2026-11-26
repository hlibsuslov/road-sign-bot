FROM python:3.13-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Mini App: TypeScript -> JavaScript with Node's own type stripping (no packages)
FROM node:24-alpine AS webapp
WORKDIR /webapp
COPY webapp/ ./
RUN node build.mjs

FROM python:3.13-slim

RUN groupadd -r bot && useradd -r -g bot -d /app -s /sbin/nologin bot

WORKDIR /app
COPY --from=builder /install /usr/local
# every runtime module at the repo root (tools/ and tests/ are folders and stay out)
COPY *.py ./
COPY data/ ./data/
COPY webapp/index.html webapp/app.css ./webapp/
COPY webapp/_kit/ ./webapp/_kit/
COPY --from=webapp /webapp/dist/ ./webapp/dist/

# smoke check: the bot must import with every module and data file present
RUN BOT_TOKEN=123456789:BUILD-SMOKE-CHECK-NOT-A-TOKEN DB_PATH=/tmp/smoke.db python -c "import bot, miniapp_server"     && rm -f /tmp/smoke.db*
RUN mkdir -p /app/db && chown -R bot:bot /app

USER bot

STOPSIGNAL SIGINT

CMD ["python", "-u", "bot.py"]
