@echo off
title AI Backend + Frontend

echo.
echo ======================================
echo  Starting Backend + Frontend
echo ======================================
echo.

REM Start Backend
echo Starting Backend (port 5000)...
start "Backend" cmd /k "cd C:\Users\rahul_oysz3kk\OneDrive\Desktop\ai_backend && .\venv\Scripts\python.exe ai_backend\app.py"

REM Wait 3 seconds
timeout /t 3 /nobreak

REM Start Frontend
echo Starting Frontend (port 8000)...
start "Frontend" cmd /k "cd C:\Users\rahul_oysz3kk\OneDrive\Desktop\ai_backend\front-end && python -m http.server 8000 --bind 127.0.0.1"

echo.
echo ======================================
echo  Frontend: http://localhost:8000
echo  Backend:  http://localhost:5000
echo ======================================
echo.