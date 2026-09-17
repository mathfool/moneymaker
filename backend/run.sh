#!/bin/bash
cd "$(dirname "$0")"
exec .venv/bin/uvicorn app.main:app --port 8000 --reload
