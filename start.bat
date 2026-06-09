@echo off
start "WPRecover API" cmd /k "cd /d %~dp0api && python -m uvicorn main:app --reload"
start "WPRecover Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
