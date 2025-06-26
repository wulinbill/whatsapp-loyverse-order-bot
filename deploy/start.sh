#!/bin/bash

# 使用 Render 提供的 PORT 环境变量，如果没有则默认 8000
PORT=${PORT:-8000}

echo "Starting application on port $PORT"

# 启动 FastAPI 应用
exec uvicorn app:main --host 0.0.0.0 --port $PORT
