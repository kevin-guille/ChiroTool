"""
credentials.py — stockage sécurisé du token Vigie-Chiro.

Priorité : **Windows Credential Manager** via ``keyring`` (le token est chiffré
par Windows avec la clé de la session user, inaccessible par un autre compte).

Fallback (keyring indisponible) : fichier JSON dans ``%APPDATA%\\ChiroTool\\``.
Le token y est **chiffré via DPAPI** (``CryptProtectData``, portée utilisateur)
sous Windows — donc illisible par un autre compte, même avec accès au fichier.
En dernier recours seulement (non-Windows ou DPAPI indisponible) le token est
écrit en clair, avec restriction d'accès best-effort (ACL / chmod).

Jamais de token envoyé ailleurs que vers vigiechiro.herokuapp.com.
"""

from __future__ import annotations

import base64
import getpass
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Final


SERVICE_NAME: Final = "ChiroTool/VigieChiro"
ACCOUNT_NAME: Final = "token"
ENV_TOKEN: Final = "VIGIECHIRO_TOKEN"


def prompt_token(arg_token: str | None = None, *, _input=None) -> str:
    """Obtient un token **sans le laisser traîner dans l'historique shell**.

    Un token passé en argument (``save-token XXXX`` / ``--token XXXX``) reste
    visible dans l'historique du shell, la liste des process et certains logs
    d'audit : c'est le mode déprécié, il émet un avertissement.

    Ordre de résolution :
      1. ``arg_token`` — **déprécié** (avertit) ;
      2. variable d'environnement ``VIGIECHIRO_TOKEN`` ;
      3. **stdin** si l'entrée est un pipe (``echo TOKEN | ... save-token``) ;
      4. saisie **interactive masquée** (``getpass``).

    ``_input`` : injection pour les tests (remplace getpass).
    """
    if arg_token:
        warnings.warn(
            "Token passé en argument : il est exposé (historique shell, liste "
            "des process). Préférez la saisie interactive, un pipe, ou la "
            f"variable d'environnement {ENV_TOKEN}.",
            stacklevel=2)
        return arg_token.strip()

    env = os.environ.get(ENV_TOKEN)
    if env and env.strip():
        return env.strip()

    try:
        piped = not sys.stdin.isatty()
    except (AttributeError, ValueError):
        piped = False
    if piped:
        try:
            data = (sys.stdin.read() or "").strip()
        except (OSError, ValueError):
            data = ""      # stdin non lisible (ex. sortie capturée) → saisie interactive
        if data:
            return data

    ask = _input or (lambda: getpass.getpass(
        "Token Vigie-Chiro (saisie masquée) : "))
    return (ask() or "").strip()


def _dpapi(protect: bool, data: bytes) -> bytes | None:
    """Chiffre (protect=True) ou déchiffre le blob via DPAPI (portée user).

    Retourne ``None`` si indisponible (non-Windows) ou en cas d'échec —
    l'appelant retombe alors sur un stockage en clair.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        buf = ctypes.create_string_buffer(data, len(data))   # gardé vivant
        blob_in = DATA_BLOB(len(data),
                            ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = DATA_BLOB()
        fn = (ctypes.windll.crypt32.CryptProtectData if protect
              else ctypes.windll.crypt32.CryptUnprotectData)
        CRYPTPROTECT_UI_FORBIDDEN = 0x01
        ok = fn(ctypes.byref(blob_in), None, None, None, None,
                CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return None


def _restrict_permissions(p: Path) -> None:
    """Restreint l'accès au fichier au seul utilisateur courant (best-effort)."""
    try:
        if os.name == "nt":
            import subprocess
            user = os.environ.get("USERNAME")
            if user:
                subprocess.run(
                    ["icacls", str(p), "/inheritance:r", "/grant:r", f"{user}:F"],
                    capture_output=True, check=False,
                )
        else:
            os.chmod(p, 0o600)
    except Exception:
        pass


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
    # Fallback fichier : chiffré DPAPI si possible, clair en dernier recours.
    p = _fallback_path()
    enc = _dpapi(True, token.encode("utf-8"))
    if enc is not None:
        p.write_text(
            json.dumps({"token_dpapi": base64.b64encode(enc).decode("ascii")}),
            encoding="utf-8",
        )
    else:
        # Dernier recours (non-Windows / DPAPI KO) : clair + restriction d'accès.
        p.write_text(json.dumps({"token": token}), encoding="utf-8")
    _restrict_permissions(p)
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
        except (OSError, json.JSONDecodeError):
            return None
        enc = data.get("token_dpapi")
        if enc:
            try:
                dec = _dpapi(False, base64.b64decode(enc))
            except Exception:
                dec = None
            return dec.decode("utf-8") if dec else None
        # Compat : ancien format en clair.
        return data.get("token") or None
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
