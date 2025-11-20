FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для компиляции
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование остальных файлов
COPY . .

# Запуск бота
CMD ["python", "main.py"]

