@echo off
REM Doble clic para construir. Argumentos opcionales: dev | build | run | package
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0construir_app.ps1" %*
pause
