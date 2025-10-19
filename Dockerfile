ARG PYTHON_VERSION=3.12.1
FROM python:${PYTHON_VERSION}-slim AS base


# Базовые настройки Python и часовой пояс
ENV PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1 \
PIP_NO_CACHE_DIR=1 \
TZ=Europe/Berlin


# Системные зависимости
RUN apt-get update \
&& DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
build-essential curl tzdata git sqlite3 ffmpeg libgomp1 libstdc++6 \
&& rm -rf /var/lib/apt/lists/*

WORKDIR /app


# Сначала ставим зависимости (для лучшего кеширования слоёв)
COPY requirements.txt ./
RUN pip install --upgrade pip \
&& pip install -r requirements.txt


# Затем — остальной код
COPY . .


# Папка для данных рантайма (db, логи и т.д.)
RUN mkdir -p /app/data \
&& ln -sf /app/data/db.db /app/db.db || true


# Порт веб-сервера OAuth (если используется)
EXPOSE 8080


# Точка входа
CMD ["python", "main.py"]