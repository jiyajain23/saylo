@echo off
set "ROOT=%~dp0"

start "Saylo Analysis" /D "%ROOT%services\analysis-service" cmd /k "venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload"
start "Saylo Backend" /D "%ROOT%backend" cmd /k "start "" /b venv\Scripts\python.exe worker.py && venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 5000 --reload"
start "Saylo Frontend" /D "%ROOT%frontend" cmd /k "npm run dev"

echo Saylo started in three terminals.
echo Backend terminal runs both the gateway and durable analysis worker.
