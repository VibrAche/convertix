# Construit Convertix sur un PC Windows (solution de secours sans GitHub).
# Prérequis : Python 3.12 (python.org, cocher "Add to PATH"). Inno Setup 6 facultatif (pour l'installeur).
# Usage (PowerShell, à la racine du projet) :  powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv")) { py -3.12 -m venv .venv }
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt

.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\pyinstaller packaging\convertix.spec --noconfirm

$version = .\.venv\Scripts\python -c "import convertix; print(convertix.__version__)"
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    & $iscc "/DMyAppVersion=$version" packaging\windows\installer.iss
    Write-Host "Installeur : dist\Convertix-Setup-$version.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup absent : l'app portable est dans dist\Convertix\Convertix.exe" -ForegroundColor Yellow
    Write-Host "Lance 'dist\Convertix\Convertix.exe --install' pour ajouter le clic droit." -ForegroundColor Yellow
}
