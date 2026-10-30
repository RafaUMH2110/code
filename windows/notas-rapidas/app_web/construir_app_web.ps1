<#
.SYNOPSIS
  Construye NotasRapidasWeb.exe (pywebview + PyInstaller) en Windows.

.EXAMPLE
  .\construir_app_web.ps1              # carpeta dist\NotasRapidasWeb\ (recomendado)
  .\construir_app_web.ps1 -UnSoloExe   # un único .exe (arranque más lento)
  .\construir_app_web.ps1 -Consola     # con consola, para ver errores
#>
param(
    [switch]$UnSoloExe,
    [switch]$Consola
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
}
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip pyinstaller pywebview pillow

if (-not (Test-Path "icono.ico") -and (Test-Path "icono.png")) {
    Write-Host "Generando icono.ico..."
    & $py -c "from PIL import Image; Image.open('icono.png').convert('RGBA').save('icono.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
}

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# --add-data "origen;destino": en Windows el separador es «;»
$opc = @("--noconfirm", "--clean", "--name", "NotasRapidasWeb",
          "--add-data", "ui;ui",
          "--collect-all", "webview")
if (Test-Path "icono.ico") { $opc += @("--icon", "icono.ico") }
if ($UnSoloExe)            { $opc += "--onefile" }
if ($Consola)              { $opc += "--console" } else { $opc += "--windowed" }

& $py -m PyInstaller @args notas_web.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller terminó con errores" }

$salida = if ($UnSoloExe) { "dist\NotasRapidasWeb.exe" } else { "dist\NotasRapidasWeb\NotasRapidasWeb.exe" }
Write-Host ""
Write-Host "Listo: $salida"
Write-Host "Requiere Microsoft Edge WebView2 Runtime (incluido en Windows 11 y en Windows 10 actualizado)."
explorer.exe (Join-Path $PSScriptRoot "dist")
