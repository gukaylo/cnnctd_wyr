#!/bin/bash
# Скрипт для коммита и пуша изменений в GitHub

echo "Добавление изменений в git..."
git add main.py README.md requirements.txt deploy.sh COMMIT_AND_PUSH.sh

echo "Создание коммита..."
git commit -m "Обновление бота: исправлена логика таймера, добавлена загрузка токена из .env, обновлена документация"

echo "Проверка удаленного репозитория..."
if git remote | grep -q origin; then
    echo "Отправка изменений в GitHub..."
    # Пробуем сначала main, потом master
    if git branch | grep -q "main"; then
        git push origin main
    elif git branch | grep -q "master"; then
        git push origin master
    else
        CURRENT_BRANCH=$(git branch --show-current)
        git push origin "$CURRENT_BRANCH"
    fi
    echo "✅ Изменения отправлены в GitHub!"
else
    echo "⚠️  Удаленный репозиторий не настроен."
    echo "Добавление remote для https://github.com/gukaylo/cnnctd_wyr..."
    git remote add origin https://github.com/gukaylo/cnnctd_wyr.git 2>/dev/null || git remote set-url origin https://github.com/gukaylo/cnnctd_wyr.git
    echo "Отправка изменений в GitHub..."
    if git branch | grep -q "main"; then
        git push -u origin main
    elif git branch | grep -q "master"; then
        git push -u origin master
    else
        CURRENT_BRANCH=$(git branch --show-current)
        git push -u origin "$CURRENT_BRANCH"
    fi
    echo "✅ Изменения отправлены в GitHub!"
fi

