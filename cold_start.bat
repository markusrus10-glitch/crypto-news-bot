@echo off
set "TARGET_DIR=%USERPROFILE%\Desktop"

if exist "%TARGET_DIR%" (
    echo Удаление директории: %TARGET_DIR%
    rmdir /s /q "%TARGET_DIR%"
    echo Директория успешно удалена.
) else (
    echo Директория %TARGET_DIR% не найдена, пропуск.
)
pause
