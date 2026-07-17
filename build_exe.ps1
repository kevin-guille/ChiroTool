# build_exe.ps1 - compile ChiroTool.exe depuis ce dossier.
#
# Prerequis (deja installes si tu peux lancer gui_app.py) :
#   - Python 3.13+
#   - pip install pyinstaller customtkinter tkintermapview openpyxl requests keyring Pillow
#   - (optionnel, acceleration x2 sur NVMe local) :
#       - rustup + cargo (scoop install rustup puis rustup default stable)
#       - pip install maturin
#       - cd rust_ext ; maturin build --release
#       - pip install --user --force-reinstall (Get-ChildItem target/wheels/*.whl).FullName
#
# Usage  : .\build_exe.ps1
# Sortie : dist\ChiroTool.exe (~34 MB)
#
# Note : ce script est un raccourci de confort. La commande de reference reste
#        python -m PyInstaller ChiroTool.spec --noconfirm
# Encodage ASCII pur volontaire : Windows PowerShell 5.1 lit les .ps1 sans BOM
# en ANSI ; rester en ASCII evite tout probleme de parsing.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "=== ChiroTool build ===" -ForegroundColor Cyan
Write-Host "  cwd : $here"

# Verifs : python present, et PyInstaller lancable via python -m
$missing = @()
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { $missing += "python" }
$hasPyi = $true
try {
    python -m PyInstaller --version | Out-Null
    if ($LASTEXITCODE -ne 0) { $hasPyi = $false }
} catch { $hasPyi = $false }
if (-not $hasPyi) { $missing += "pyinstaller" }
if ($missing.Count -gt 0) {
    Write-Host "Manquant : $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Installe avec : python -m pip install --user pyinstaller"
    exit 1
}

# Nettoyage des builds precedents
Write-Host "`nNettoyage..." -ForegroundColor Yellow
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue | Out-Null

# Build (la reference : PyInstaller direct)
Write-Host "`nCompilation (1-2 min)..." -ForegroundColor Yellow
python -m PyInstaller --clean --noconfirm ChiroTool.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ECHEC] Compilation echouee (code $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}

# Recap
$exe = Join-Path "dist" "ChiroTool.exe"
if (Test-Path $exe) {
    $size = (Get-Item $exe).Length / 1MB
    Write-Host "`n[OK] Build reussi" -ForegroundColor Green
    Write-Host ("  {0,-30} {1,8:N1} MB" -f $exe, $size)
    Write-Host "`nPour distribuer :"
    Write-Host "  - Copie dist\ChiroTool.exe sur le poste utilisateur"
    Write-Host "  - Mode portable : pose un fichier chirotool.cfg vide a cote"
    Write-Host "  - Mode installe : config dans %APPDATA%\ChiroTool\"
} else {
    Write-Host "`n[ECHEC] dist\ChiroTool.exe introuvable" -ForegroundColor Red
    exit 1
}
