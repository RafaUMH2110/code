@echo off
REM Doble clic para construir. Evita el bloqueo de scripts de PowerShell.
REM Argumentos opcionales: -UnSoloExe  -Consola
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0construir_app.ps1" %*
pause
