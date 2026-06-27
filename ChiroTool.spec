# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec pour ChiroTool.

Produit un `.exe` unique portable (~80-120 MB) incluant :
  - l'interpréteur Python 3.13 embarqué
  - tous nos modules (gui_*, pipeline, vigiechiro_api, te10, etc.)
  - chirotool_fast.pyd (extension Rust, ×2 sur TE×10 NVMe)
  - openpyxl, requests, keyring, customtkinter, tkintermapview
  - Tcl/Tk pour Tkinter
  - SpeciesListComplete.csv (754 taxons MNHN)
  - icône applicative (si présente)

Build : pyinstaller ChiroTool.spec
Sortie : dist/ChiroTool.exe

Mode par défaut : `--onefile --windowed` (un seul exe, pas de console).
Pour iterer vite en dev, passer `--onedir` via `pyinstaller --onedir ChiroTool.spec`.
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# -- Données embarquées --
datas = []

# CustomTkinter : themes JSON + assets
datas += collect_data_files("customtkinter")
# tkintermapview : assets (markers par défaut, etc.)
datas += collect_data_files("tkintermapview")
# Notre table taxons officielle
datas += [("SpeciesListComplete.csv", ".")]
# Icône — embarquée aussi dans les datas pour l'accéder en runtime via
# sys._MEIPASS (fenêtre principale appelle iconbitmap au démarrage).
datas += [("icon.ico", ".")]

# -- Hidden imports --
# Modules utilisés via importlib ou en dynamique (à déclarer explicitement)
hidden = [
    "chirotool_fast",       # extension Rust
    "keyring.backends.Windows",   # backend keyring Windows
    "win32timezone",        # sous-dépendance keyring
]
# Tous les sous-modules tkintermapview (certains sont chargés dynamiquement)
hidden += collect_submodules("tkintermapview")

block_cipher = None

a = Analysis(
    ["gui_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # On n'a pas besoin de ces modules lourds
        "tkinter.test",
        "unittest",
        "pytest",
        "pandas",      # pas utilisé (openpyxl suffit)
        "numpy",       # pas utilisé directement
        "scipy",
        "matplotlib",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# -- Métadonnées d'éditeur Windows (resource VERSIONINFO) --------------------
# Rendent le binaire « légitime » (clic droit → Propriétés → Détails) et un peu
# moins suspect pour les heuristiques antivirus. Auteur = Kevin Guille (projet
# personnel). Acer Campestre n'apparaît PAS ici (seulement dans l'« À propos »).
# La version est générée depuis version.py pour rester toujours synchronisée.
import sys as _sys
if str(SPECPATH) not in _sys.path:
    _sys.path.insert(0, str(SPECPATH))
from version import __version__ as _APP_VER
_nums = (_APP_VER.split("-")[0].split(".") + ["0", "0", "0", "0"])[:4]
_vt = tuple(int(x) for x in _nums)
_ver_dotted = ".".join(str(x) for x in _vt)
_version_file = Path(SPECPATH) / "build_version_info.txt"
_version_file.write_text(
    "VSVersionInfo(\n"
    "  ffi=FixedFileInfo(\n"
    f"    filevers={_vt}, prodvers={_vt},\n"
    "    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)\n"
    "  ),\n"
    "  kids=[\n"
    "    StringFileInfo([\n"
    "      StringTable('040c04b0', [\n"
    "        StringStruct('CompanyName', 'Kevin Guille'),\n"
    "        StringStruct('FileDescription', 'ChiroTool - traitement Vigie-Chiro Point Fixe (chiropteres)'),\n"
    f"        StringStruct('FileVersion', '{_ver_dotted}'),\n"
    "        StringStruct('InternalName', 'ChiroTool'),\n"
    "        StringStruct('LegalCopyright', '(c) 2026 Kevin Guille - Licence MIT'),\n"
    "        StringStruct('OriginalFilename', 'ChiroTool.exe'),\n"
    "        StringStruct('ProductName', 'ChiroTool'),\n"
    f"        StringStruct('ProductVersion', '{_ver_dotted}')\n"
    "      ])\n"
    "    ]),\n"
    "    VarFileInfo([VarStruct('Translation', [0x040c, 1200])])\n"
    "  ]\n"
    ")\n",
    encoding="utf-8",
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ChiroTool",
    version=str(_version_file),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # UPX complique la distribution + antivirus false positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # windowed : pas de console noire au lancement
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",       # icône applicative custom (cercle bleu + chiro)
)
