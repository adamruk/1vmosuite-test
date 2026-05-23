@echo off
REM Double-click bootstrap for the 1vmo Suite.
REM Creates .venv, installs requirements.txt, and provisions ffmpeg.
REM Just runs setup.ps1 with the execution policy relaxed for this process only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
echo.
pause
