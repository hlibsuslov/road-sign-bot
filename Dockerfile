FROM python:3.13-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim

RUN groupadd -r bot && useradd -r -g bot -d /app -s /sbin/nologin bot

WORKDIR /app
COPY --from=builder /install /usr/local
COPY bot.py database.py keyboards.py learning.py utils.py ./
COPY data/ ./data/

RUN mkdir -p /app/db && chown -R bot:bot /app

USER bot

STOPSIGNAL SIGINT

CMD ["python", "-u", "bot.py"]
