@echo off
chcp 65001 >nul
echo ========================================
echo    Бот репоста Telegram каналов
echo ========================================
echo.

pip install -r requirements.txt --quiet 2>nul

echo Запуск бота...
python repost_bot.py

pause
