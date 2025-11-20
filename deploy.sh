#!/bin/bash
# Скрипт для деплоя бота

echo "Проверка готовности к деплою..."

# Проверка наличия .env файла
if [ ! -f .env ]; then
    echo "⚠️  ВНИМАНИЕ: Файл .env не найден!"
    echo "Создайте файл .env на основе config.example.env и добавьте BOT_TOKEN"
    exit 1
fi

# Проверка наличия BOT_TOKEN в .env
if ! grep -q "BOT_TOKEN=" .env || grep -q "BOT_TOKEN=123456:YOUR_TOKEN_HERE" .env; then
    echo "⚠️  ВНИМАНИЕ: BOT_TOKEN не настроен в .env файле!"
    exit 1
fi

echo "✅ Все проверки пройдены. Бот готов к запуску."
echo ""
echo "Для запуска бота выполните:"
echo "  source .venv/bin/activate"
echo "  python main.py"

