# Lance Convertix en mode développement sur Windows (sans construire l'exe).
# Usage :  powershell -ExecutionPolicy Bypass -File scripts\dev_windows.ps1 [--install]
#   --install : ajoute aussi le clic droit en pointant vers ce dossier (pythonw run.py)

Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
    .\.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
}
if ($args -contains "--install") { .\.venv\Scripts\python run.py --install }
.\.venv\Scripts\python run.py --verbose
