#!/bin/bash
# 一键启动：后端 (FastAPI :8000) + 前端 (Vite :5173)
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi
# 重新打包，保证 http://localhost:8000 上的静态版本和源码一致
(cd frontend && npm run build >/dev/null 2>&1) || echo "前端打包失败，8000 端口可能是旧版本；请用 5173"
trap 'kill 0' EXIT
(cd backend && .venv/bin/uvicorn app.main:app --port 8000 --reload) &
(cd frontend && npm run dev) &
sleep 2
echo
echo "打开浏览器访问  http://localhost:5173  （开发版，改代码即时生效）"
echo "或者            http://localhost:8000  （打包版，同一份功能）"
wait
