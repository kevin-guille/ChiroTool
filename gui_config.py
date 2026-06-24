"""
gui_config.py — persistance des préférences GUI + détection portable/installé.

Mode portable : un fichier ``chirotool.cfg`` existe à côté de l'exécutable
(ou à côté de gui_app.py en dev). Tout est stocké dans
``<exe_dir>/ChiroTool_data/``.

Mode installé : config dans ``%APPDATA%\\ChiroTool\\``.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


APP_NAME = "ChiroTool"
PORTABLE_MARKER = "chirotool.cfg"


def _app_root() -> Path:
    """Dossier où se trouve le .exe PyInstaller ou le script en dev."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def is_portable() -> bool:
    return (_app_root() / PORTABLE_MARKER).exists()


def config_dir() -> Path:
    if is_portable():
        d = _app_root() / "ChiroTool_data"
    else:
        base = os.environ.get("APPDATA") or str(Path.home() / ".config")
        d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Settings:
    last_workspace: str | None = None           # dossier racine ouvert
    recent_workspaces: list[str] = field(default_factory=list)
    appearance: str = "system"                  # system | light | dark
    # Seuils cleanup mémorisés
    threshold_chiros: float = 0.5
    threshold_orthos: float = 0.5
    threshold_micromam: float = 0.5
    threshold_oiseaux: float = 0.5
    silent_policy: str = "delete"               # delete | keep
    unknown_action: str = "keep"
    # ChiroSurf (v2)
    chirosurf_path: str | None = None
    # Onboarding : True après que l'utilisateur a terminé (ou ignoré) le wizard
    # d'accueil au premier lancement. Évite de le ré-afficher à chaque démarrage.
    onboarding_done: bool = False
    # Mémoire des noms de contrats déjà saisis (autocomplétion wizard meta)
    # Limité à 50 entrées max, plus récents en tête (LRU).
    recent_contracts: list[str] = field(default_factory=list)
    # Chemins absolus des fichiers materiels.json déjà proposés à l'utilisateur
    # via la détection automatique au scan workspace. Évite de re-proposer
    # à chaque scan ou changement d'onglet.
    materiels_seen_files: list[str] = field(default_factory=list)
    # Vérification automatique des mises à jour au démarrage (non bloquante).
    auto_update_check: bool = True
    # Tag de version que l'utilisateur a choisi d'« ignorer » (ne plus proposer).
    update_skip_version: str | None = None
    # Date ISO (YYYY-MM-DD) du dernier check auto réussi → throttle 1×/jour.
    last_update_check: str | None = None


def _settings_file() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> Settings:
    p = _settings_file()
    if not p.is_file():
        return Settings()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Settings()
    # Tolère clés inconnues
    known = {f.name for f in Settings.__dataclass_fields__.values()}
    return Settings(**{k: v for k, v in data.items() if k in known})


def save_settings(s: Settings) -> None:
    p = _settings_file()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(s), indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(p)


def remember_workspace(path: str, s: Settings, keep: int = 8) -> None:
    """Ajoute `path` en tête de recent_workspaces."""
    p = str(Path(path).resolve())
    if p in s.recent_workspaces:
        s.recent_workspaces.remove(p)
    s.recent_workspaces.insert(0, p)
    s.recent_workspaces = s.recent_workspaces[:keep]
    s.last_workspace = p


# ---------------------------------------------------------------------------
# Single instance lock (évite les multi-instances accidentelles)
# ---------------------------------------------------------------------------

def single_instance_acquire() -> tuple[object | None, bool]:
    """
    Tente d'acquérir un verrou d'instance unique. Retourne (lock_object, acquired).
    Si acquired=False, une autre instance tourne déjà.
    Le lock_object doit être gardé en vie pendant toute l'exécution.
    """
    lock_path = config_dir() / f"{APP_NAME}.lock"
    # Sous Windows on utilise msvcrt, ailleurs fcntl
    try:
        if sys.platform == "win32":
            import msvcrt
            f = open(lock_path, "wb")
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                f.write(str(os.getpid()).encode())
                f.flush()
                return f, True
            except OSError:
                f.close()
                return None, False
        else:
            import fcntl
            f = open(lock_path, "wb")
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                f.write(str(os.getpid()).encode())
                f.flush()
                return f, True
            except OSError:
                f.close()
                return None, False
    except Exception:
        return None, True  # Si ça plante, on laisse passer par défaut


def storage_info() -> dict:
    return {
        "app_root": str(_app_root()),
        "portable": is_portable(),
        "config_dir": str(config_dir()),
        "settings_file": str(_settings_file()),
    }
