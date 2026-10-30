<#
.SYNOPSIS
  Construye NotasRapidas.exe con PyInstaller (Windows).

.EXAMPLE
  .\construir_app.ps1              # carpeta dist\NotasRapidas\ (recomendado)
  .\construir_app.ps1 -UnSoloExe   # un único NotasRapidas.exe (arranque más lento)
  .\construir_app.ps1 -Consola     # con ventana de consola, para depurar errores
#>
param(
    [switch]$UnSoloExe,
    [switch]$Consola
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1) Entorno virtual con PyInstaller
if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
}
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip pyinstaller pillow

# 2) Icono: si falta icono.ico se genera desde icono.png
if (-not (Test-Path "icono.ico") -and (Test-Path "icono.png")) {
    Write-Host "Generando icono.ico..."
    & $py -c "from PIL import Image; Image.open('icono.png').convert('RGBA').save('icono.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
}

# 3) Limpiar y construir
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

$opc = @("--noconfirm", "--clean", "--name", "NotasRapidas",
          "--add-data", "icono.ico;.")
if (Test-Path "icono.ico") { $opc += @("--icon", "icono.ico") }
if ($UnSoloExe)            { $opc += "--onefile" }
if ($Consola)              { $opc += "--console" } else { $opc += "--windowed" }

& $py -m PyInstaller @args notas_app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller terminó con errores" }

$salida = if ($UnSoloExe) { "dist\NotasRapidas.exe" } else { "dist\NotasRapidas\NotasRapidas.exe" }
Write-Host ""
Write-Host "Listo: $salida"
Write-Host "Haz doble clic para ejecutarla (o crea un acceso directo en el Escritorio)."
explorer.exe (Join-Path $PSScriptRoot "dist")
