FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование файлов приложения
COPY bot.py .
COPY proxy_server.py .
COPY index.html .

# Создание директорий
RUN mkdir -p /var/lib/marzban/certs
RUN mkdir -p /app/static

# Установка переменных окружения
ENV PYTHONUNBUFFERED=1

# Запуск обоих сервисов через supervisor
RUN apt-get update && apt-get install -y supervisor && rm -rf /var/lib/apt/lists/*

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
