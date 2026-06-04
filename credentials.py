"""
credentials.py — stockage sécurisé du token Vigie-Chiro.

Utilise **Windows Credential Manager** via la lib ``keyring`` quand c'est
disponible (le token est chiffré par Windows avec la clé de la session user,
inaccessible par un autre compte / autre PC).

Fallback : fichier JSON dans ``%APPDATA%\\ChiroTool\\`` avec permissions
restreintes (best effort). Pas chiffré mais protégé par ACL du dossier user.

Jamais de token envoyé ailleurs que vers vigiechiro.herokuapp.com.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final


SERVICE_NAME: Final = "ChiroTool/VigieChiro"
ACCOUNT_NAME: Final = "token"


def _fallback_dir() -> Path:
    """Dossier pour le stockage fallback (APPDATA sous Windows)."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / "ChiroTool"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fallback_path() -> Path:
    return _fallback_dir() / "credentials.json"


def _try_keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def save_token(token: str) -> str:
    """
    Enregistre le token de façon persistante.
    Retourne 'keyring' ou 'file' selon la méthode utilisée.
    """
    kr = _try_keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE_NAME, ACCOUNT_NAME, token)
            return "keyring"
        except Exception:
            pass  # fallback
    # Fallback fichier
    p = _fallback_path()
    p.write_text(json.dumps({"token": token}), encoding="utf-8")
    try:
        # Restreint l'accès au propriétaire (best effort)
        os.chmod(p, 0o600)
    except OSError:
        pass
    return "file"


def load_token() -> str | None:
    """Retourne le token stocké, ou None."""
    kr = _try_keyring()
    if kr is not None:
        try:
            tok = kr.get_password(SERVICE_NAME, ACCOUNT_NAME)
            if tok:
                return tok
        except Exception:
            pass
    p = _fallback_path()
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("token") or None
        except (OSError, json.JSONDecodeError):
            return None
    return None


def delete_token() -> bool:
    """Supprime le token de tous les stockages. Retourne True si au moins un."""
    ok = False
    kr = _try_keyring()
    if kr is not None:
        try:
            kr.delete_password(SERVICE_NAME, ACCOUNT_NAME)
            ok = True
        except Exception:
            pass
    p = _fallback_path()
    if p.is_file():
        try:
            p.unlink()
            ok = True
        except OSError:
            pass
    return ok


def storage_backend() -> str:
    """Pour diagnostic : 'keyring' / 'file' / 'file (indisponible)'."""
    if _try_keyring() is not None:
        return "keyring"
    return "file"
