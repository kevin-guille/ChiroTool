# build_exe.ps1 — compile ChiroTool.exe depuis ce dossier.
#
# Prérequis (tous déjà installés si tu peux lancer gui_app.py) :
#   - Python 3.13+
#   - pip install pyinstaller customtkinter tkintermapview openpyxl requests keyring
#   - (optionnel, pour accélération ×2 sur NVMe) :
#       - rustup + cargo (scoop install rustup puis rustup default stable)
#       - pip install maturin
#       - cd rust_ext ; maturin build --release
#       - pip install --user --force-reinstall (Get-ChildItem target/wheels/*.whl).FullName
#
# Usage : .\build_exe.ps1
# Sortie : dist\ChiroTool.exe (~33 MB)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "=== ChiroTool build ===" -ForegroundColor Cyan
Write-Host "  cwd : $here"

# Vérifs rapides
$missing = @()
foreach ($cmd in @("python", "pyinstaller")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        # pyinstaller peut être installé en --user, donc on teste aussi via python -m
        if ($cmd -eq "pyinstaller") {
            try { python -m PyInstaller --version | Out-Null } catch { $missing += $cmd }
        } else {
            $missing += $cmd
        }
    }
}
if ($missing.Count -gt 0) {
    Write-Host "Manquant : $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Installe avec : python -m pip install --user pyinstaller"
    exit 1
}

# Nettoyage des builds précédents
Write-Host "`nNettoyage..." -ForegroundColor Yellow
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue | Out-Null

# Build
Write-Host "`nCompilation (1-2 min)..." -ForegroundColor Yellow
python -m PyInstaller --clean --noconfirm ChiroTool.spec 2>&1 | Tee-Object -Variable output | Select-String -Pattern "INFO:|ERROR|WARNING" | Select-Object -Last 5

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n✗ Compilation échouée" -ForegroundColor Red
    exit $LASTEXITCODE
}

# Récap
$exe = Join-Path "dist" "ChiroTool.exe"
if (Test-Path $exe) {
    $size = (Get-Item $exe).Length / 1MB
    Write-Host "`n✓ Build réussi" -ForegroundColor Green
    Write-Host ("  {0,-30} {1,8:N1} MB" -f $exe, $size)
    Write-Host "`nPour distribuer :"
    Write-Host "  - Copie simplement dist\ChiroTool.exe sur le poste utilisateur"
    Write-Host "  - Mode portable : pose chirotool.cfg à côté (marqueur vide suffit)"
    Write-Host "  - Mode installé : config dans %APPDATA%\ChiroTool\"
} else {
    Write-Host "`n✗ dist\ChiroTool.exe introuvable" -ForegroundColor Red
    exit 1
}
