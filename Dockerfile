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
COPY bot.py database.py keyboards.py learning.py utils.py miniapp_server.py init_data.py ./
COPY data/ ./data/
COPY webapp/index.html webapp/app.css ./webapp/
COPY webapp/_kit/ ./webapp/_kit/
COPY --from=webapp /webapp/dist/ ./webapp/dist/

RUN mkdir -p /app/db && chown -R bot:bot /app

USER bot

STOPSIGNAL SIGINT

CMD ["python", "-u", "bot.py"]
