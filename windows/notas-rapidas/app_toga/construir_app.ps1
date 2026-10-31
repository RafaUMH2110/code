<#
.SYNOPSIS
  Construye la app de Toga con Briefcase (Windows).

.EXAMPLE
  .\construir_app.ps1 dev        # ejecuta en modo desarrollo (sin construir)
  .\construir_app.ps1            # crea/actualiza y construye (por defecto)
  .\construir_app.ps1 run        # ejecuta la app construida
  .\construir_app.ps1 package    # además genera un instalador .msi en dist\
#>
param(
    [ValidateSet("dev", "build", "package", "run")]
    [string]$Accion = "build"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
}
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements.txt

function Invoke-Briefcase {
    & $py -m briefcase @args
    if ($LASTEXITCODE -ne 0) { throw "briefcase terminó con errores" }
}

switch ($Accion) {
    "dev"  { Invoke-Briefcase dev }
    "run"  { Invoke-Briefcase run windows }
    default {
        if (Test-Path "build\notas-rapidas-toga\windows") {
            Invoke-Briefcase update windows
        } else {
            Invoke-Briefcase create windows
        }
        Invoke-Briefcase build windows
        if ($Accion -eq "package") {
            # --adhoc-sign: sin certificado de firma (SmartScreen avisará al instalar)
            Invoke-Briefcase package windows --adhoc-sign
            Write-Host "Instalador (MSI) en dist\"
        }
        Write-Host ""
        Write-Host "Listo. Para ejecutarla:  .\construir_app.ps1 run"
    }
}
