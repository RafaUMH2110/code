@echo off
REM Doble clic para construir. Argumentos opcionales: -UnSoloExe  -Consola
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0construir_app_web.ps1" %*
pause
