"""
repair.py — diagnostic et réparation d'état d'une session (une nuit).

Aligne, sur demande, le manifest local (+ registry optionnel) avec la réalité
serveur Vigie-Chiro et le disque (Data_k/, xlsx d'observations).

Contexte
--------
Trois couches d'état coexistent (manifest, filesystem/UI, registry SQLite) et
se désynchronisent après upload partiel, crash, ou lancement manuel de
l'analyse sur le portail. Ce module fournit une API **pure / testable**, sans
GUI, strictement limitée à **une session**.

Usage typique
-------------
    # 1. Dry-run (défaut) — aucun fichier modifié
    report = diagnose_and_repair_session(session, token)

    # 2. Appliquer les actions sûres (flags + fetch si TERMINE)
    report = diagnose_and_repair_session(session, token, apply=True)

    # 3. Avec re-déclenchement Tadarida (double confirmation API)
    report = diagnose_and_repair_session(
        session, token, apply=True,
        allow_trigger=True, confirm_trigger=True,
    )

Le rapport contient toujours ``suggested_actions``, le diff de couverture
WAV, l'état ``traitement.etat``, et (si ``apply=True``) ``applied_actions``
+ ``errors``.

Garde-fous
----------
- Jamais de ``trigger_compute`` si des WAV locaux manquent sur le serveur.
- ``set_uploaded_true`` uniquement si couverture **100 %** (et listing OK).
- Trigger uniquement si ``allow_trigger`` **et** ``confirm_trigger``.
- Dry-run (``apply=False``) ne touche ni disque ni registry.
- Toute mutation est journalisée via ``manifest.record_action`` (type
  ``repair`` / ``resync_state``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from chiro_core import (
    collect_local_participation_fields,
    diff_participation_update,
    resolve_session_root,
    server_fields_from_participation,
)
from manifest import Manifest

try:
    from version import __version__ as TOOL_VERSION
except Exception:  # pragma: no cover
    TOOL_VERSION = "?"

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# États Tadarida considérés "déjà en route ou terminés" → pas de re-trigger
# automatique (évite double job / 429).
_ETAT_NO_RETRIGGER = frozenset({
    "PLANIFIE", "EN_COURS", "TERMINE", "FINI",
})
_ETAT_DONE = frozenset({"TERMINE", "FINI"})
_ETAT_ERROR = frozenset({"ERROR", "ERREUR"})

ACTION_SET_UPLOADED = "set_uploaded_true"
ACTION_RESUME_UPLOAD = "resume_upload_missing"
ACTION_TRIGGER = "trigger_compute"
ACTION_FETCH = "fetch_xlsx"
ACTION_SYNC_META = "sync_participation_meta"
ACTION_NOOP = "noop"

SUGGESTED_ACTIONS = (
    ACTION_SET_UPLOADED,
    ACTION_RESUME_UPLOAD,
    ACTION_TRIGGER,
    ACTION_FETCH,
    ACTION_SYNC_META,
    ACTION_NOOP,
)


# ---------------------------------------------------------------------------
# Protocol client (injectable pour tests, sans réseau)
# ---------------------------------------------------------------------------

class RepairClient(Protocol):
    """Sous-ensemble de VigieChiroClient utilisé par le repair."""

    def participation_status(self, participation_id: str) -> dict: ...
    def list_participation_files(self, participation_id: str) -> list[str]: ...
    def trigger_compute(self, participation_id: str) -> dict: ...
    def get_participation(self, participation_id: str) -> Any: ...
    def edit_participation(self, participation_id: str, **kwargs) -> dict: ...
    def download_observations_as_xlsx(
        self, participation_id: str, dst: Path, on_progress=None,
    ) -> dict: ...
    def probe_titre_registered(
        self, participation_id: str, titre: str,
    ) -> str: ...


class RegistryLike(Protocol):
    def update_fields(self, sid: str, fields: dict) -> None: ...
    def get_session(self, sid: str) -> dict | None: ...


# ---------------------------------------------------------------------------
# Helpers purs (testables sans I/O réseau)
# ---------------------------------------------------------------------------

def participation_id_from_observations_name(name: str) -> str | None:
    """Extrait l'ID depuis ``participation-<id>-observations*.xlsx/csv``."""
    n = (name or "").strip()
    low = n.lower()
    if not low.startswith("participation-"):
        return None
    key = "-observations"
    idx = low.find(key)
    if idx <= len("participation-"):
        return None
    pid = n[len("participation-"):idx].strip()
    return pid or None


def list_local_data_k_wavs(session: Path) -> list[str]:
    """Noms des WAV dans ``session/Data_k/`` (triés). Liste vide si absent."""
    data_k = Path(session) / "Data_k"
    if not data_k.is_dir():
        return []
    try:
        return sorted(p.name for p in data_k.iterdir()
                      if p.is_file() and p.suffix.lower() == ".wav")
    except OSError:
        return []


def find_local_observations_xlsx(session: Path) -> Path | None:
    """xlsx/csv d'observations à la racine (exclut ``_cleanup``)."""
    session = Path(session)
    if not session.is_dir():
        return None
    candidates: list[Path] = []
    try:
        for p in session.iterdir():
            if not p.is_file():
                continue
            n = p.name.lower()
            if not n.startswith("participation-"):
                continue
            if "observations" not in n:
                continue
            if not (n.endswith(".xlsx") or n.endswith(".csv")):
                continue
            if "_cleanup" in n:
                continue
            candidates.append(p)
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def pick_probe_names(names: list[str], k: int = 5) -> list[str]:
    """Échantillon stable de noms (premier, dernier, et répartis)."""
    clean = [n for n in names if n]
    if not clean:
        return []
    if len(clean) <= k:
        return list(clean)
    n = len(clean)
    idxs = sorted({int(round(i * (n - 1) / (k - 1))) for i in range(k)})
    return [clean[i] for i in idxs]


def _norm_wav_name(name: str) -> str:
    """Normalise un nom WAV pour comparaison local ↔ serveur.

    - basenom seulement (pas de chemin)
    - minuscules
    - force l'extension ``.wav`` si absente (certains titres API n'en ont pas)
    """
    n = str(name or "").strip().replace("\\", "/")
    if "/" in n:
        n = n.rsplit("/", 1)[-1]
    n = n.strip().lower()
    if n and not n.endswith(".wav") and not n.endswith(".w4v"):
        n = n + ".wav"
    return n


def compute_coverage(
    local_names: set[str] | list[str],
    server_names: set[str] | list[str],
    *,
    listing_ok: bool = True,
) -> dict[str, Any]:
    """Diff de couverture local ↔ serveur (fonction pure).

    ``missing_on_server`` = fichiers **encore présents localement** (Data_k)
    absents du listing serveur → vrai trou d'upload à reprendre.

    ``extra_on_server`` = fichiers sur le serveur **absents de Data_k** →
    typique **après nettoyage** (WAV purgés localement mais encore en ligne).
    Ce n'est **pas** un échec d'upload : la couverture reste OK si tous les
    locaux restants sont sur le serveur.

    ``listing_ok=False`` : le listing serveur a échoué → on refuse toute
    conclusion positive (pas de couverture 100 %, pas d'auto-set uploaded).
    """
    # Mappe forme normalisée → nom d'origine (pour messages lisibles)
    local_map: dict[str, str] = {}
    for n in local_names:
        key = _norm_wav_name(n)
        if key:
            local_map.setdefault(key, str(n))
    server_map: dict[str, str] = {}
    for n in server_names:
        key = _norm_wav_name(n)
        if key:
            server_map.setdefault(key, str(n))

    local_keys = set(local_map)
    server_keys = set(server_map)
    missing_keys = sorted(local_keys - server_keys)
    extra_keys = sorted(server_keys - local_keys)
    missing = [local_map[k] for k in missing_keys]
    extra = [server_map[k] for k in extra_keys]

    if not listing_ok:
        # Ne pas présenter tous les locaux comme « à uploader » : le diff
        # n'est pas fiable (token expiré, réseau, API). La GUI / le rapport
        # insistent sur l'échec de listing.
        return {
            "local_wav_count": len(local_keys),
            "server_wav_count": len(server_keys),
            "missing_on_server": [],
            "extra_on_server": [],
            "coverage_ok": False,
            "listing_ok": False,
        }
    # Couverture 100 % = tous les WAV **encore locaux** sont sur le serveur.
    # Les extras serveur (post-nettoyage) n'empêchent PAS coverage_ok.
    # local vide + serveur vide : coverage_ok False (rien à valider).
    coverage_ok = bool(local_keys) and not missing_keys
    return {
        "local_wav_count": len(local_keys),
        "server_wav_count": len(server_keys),
        "missing_on_server": missing,
        "extra_on_server": extra,
        "coverage_ok": coverage_ok,
        "listing_ok": True,
    }


def suggest_actions(
    *,
    coverage_ok: bool,
    listing_ok: bool,
    missing_on_server: list[str],
    traitement_etat: str | None,
    has_xlsx: bool,
    flag_uploaded: bool,
    has_participation_id: bool,
    files_registered: bool = False,
    meta_needs_sync: bool = False,
) -> list[str]:
    """Détermine les actions logiques (pure). Ne regarde pas allow_*.

    Ordre stable, déterministe. Retourne toujours au moins ``noop`` si
    aucune action corrective n'est pertinente.

    ``files_registered`` : les titres WAV sont déjà des fiches serveur
    (listing fiable OU sonde HTTP 409), même si ``GET /fichiers`` est en
    403. Dans ce cas on propose ``trigger_compute`` plutôt qu'un re-upload
    qui échouerait en 409.
    """
    if not has_participation_id:
        return [ACTION_NOOP]

    actions: list[str] = []
    if meta_needs_sync:
        actions.append(ACTION_SYNC_META)
    etat = (traitement_etat or "").strip().upper()

    # 1. Fichiers manquants → reprise upload, jamais trigger / set_uploaded
    if listing_ok and missing_on_server and not files_registered:
        actions.append(ACTION_RESUME_UPLOAD)
        # Pas de set_uploaded ni trigger tant que la couverture n'est pas 100 %
        if etat in _ETAT_DONE and not has_xlsx:
            # Analyse déjà finie côté serveur malgré trous locaux ? rare ;
            # on peut quand même récupérer l'xlsx.
            actions.append(ACTION_FETCH)
        return actions or [ACTION_NOOP]

    # 2. Listing KO → pas de re-upload massif. Si les titres sont quand
    # même enregistrés (sonde 409), on peut lancer Tadarida : c'est le
    # cas « upload coupé, compute jamais parti ».
    if not listing_ok:
        if files_registered and etat not in _ETAT_NO_RETRIGGER:
            actions.append(ACTION_TRIGGER)
        if etat in _ETAT_DONE and not has_xlsx:
            actions.append(ACTION_FETCH)
        return actions or [ACTION_NOOP]

    # 3. Couverture 100 % → aligner flag uploaded si besoin
    if coverage_ok and not flag_uploaded:
        actions.append(ACTION_SET_UPLOADED)

    # 4. Trigger seulement si couverture OK et état pas déjà lancé/terminé
    if coverage_ok and etat not in _ETAT_NO_RETRIGGER:
        # Inclut etat vide, ERROR/ERREUR (re-tentative consciente), inconnu
        actions.append(ACTION_TRIGGER)

    # 5. Fetch si analyse terminée sans xlsx local
    if etat in _ETAT_DONE and not has_xlsx:
        actions.append(ACTION_FETCH)

    if not actions:
        actions.append(ACTION_NOOP)
    return actions


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

@dataclass
class RepairReport:
    """Rapport structuré de diagnostic (+ actions appliquées si apply)."""
    session: str
    participation_id: str | None = None
    local_wav_count: int = 0
    server_wav_count: int = 0
    missing_on_server: list[str] = field(default_factory=list)
    extra_on_server: list[str] = field(default_factory=list)
    coverage_ok: bool = False
    coverage_skipped: bool = False
    listing_ok: bool = True
    listing_error: str | None = None
    files_registered: bool = False
    registration_via: str | None = None
    traitement_etat: str | None = None
    traitement_date: str | None = None
    has_xlsx: bool = False
    xlsx_path: str | None = None
    local_flags: dict[str, bool] = field(default_factory=dict)
    suggested_actions: list[str] = field(default_factory=list)
    meta_changes: list[str] = field(default_factory=list)
    applied_actions: list[str] = field(default_factory=list)
    skipped_actions: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    apply: bool = False
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ACTION_LABELS = {
    ACTION_SET_UPLOADED: "Aligner le flag « uploadé » (manifest)",
    ACTION_RESUME_UPLOAD: "Reprendre l'upload des WAV manquants (via bouton Upload)",
    ACTION_TRIGGER: "Relancer l'analyse Tadarida",
    ACTION_FETCH: "Télécharger le tableur d'observations (xlsx)",
    ACTION_SYNC_META: "Mettre à jour les métadonnées sur Vigie-Chiro (sans relancer Tadarida)",
    ACTION_NOOP: "Aucune action nécessaire",
}

# Groupes de confirmation (un Oui/Non par groupe, pas un PATCH unique aveugle).
META_CONFIRM_GROUPS = (
    (
        "Horaires d'enregistrement",
        ("horaires d'enregistrement",),
        "Début / fin lus dans le log Titley (Recording start / stop).",
    ),
    (
        "Températures",
        ("T° début", "T° fin"),
        "T° de début et de fin de nuit.",
    ),
    (
        "Vent et couverture",
        ("vent", "couverture"),
        "Vent et couverture nuageuse.",
    ),
    (
        "Matériel",
        (
            "n° de série",
            "type d'enregistreur",
            "micro",
            "hauteur micro",
            "micro droit",
            "hauteur micro droit",
        ),
        "N° de série, type d'enregistreur, micro, hauteur.",
    ),
)


def meta_confirm_groups(changes: list[str] | None) -> list[tuple[str, list[str], str]]:
    """Groupes dont au moins un libellé est dans ``changes``."""
    found = list(changes or [])
    out: list[tuple[str, list[str], str]] = []
    for title, labels, hint in META_CONFIRM_GROUPS:
        hit = [lab for lab in labels if lab in found]
        if hit:
            out.append((title, hit, hint))
    return out


def action_label(action: str) -> str:
    """Libellé humain d'une action de repair (GUI / logs)."""
    return ACTION_LABELS.get(action, action)


def format_repair_report(report: dict[str, Any] | RepairReport) -> str:
    """Formate un rapport de repair en texte lisible (GUI / logs)."""
    if isinstance(report, RepairReport):
        r = report.to_dict()
    else:
        r = report or {}

    lines: list[str] = []
    lines.append("═══ Diagnostic session ═══")
    lines.append(f"Session          : {r.get('session') or '—'}")
    lines.append(f"Participation ID : {r.get('participation_id') or '— (absente)'}")
    lines.append("")
    lines.append("── Couverture WAV (Data_k ↔ serveur) ──")
    lines.append(f"  Local  (Data_k) : {r.get('local_wav_count', 0)} fichier(s)")
    lines.append(f"  Serveur         : {r.get('server_wav_count', 0)} fichier(s)")
    listing_ok = r.get("listing_ok", True)
    files_registered = bool(r.get("files_registered"))
    via = r.get("registration_via") or ""
    if not listing_ok and files_registered:
        cov = "portail : listing indisponible, fichiers déjà enregistrés (code 409)"
        list_ok = (
            "listing KO, enregistrement confirmé"
            if via == "409_probe" else "ÉCHEC listing"
        )
    elif not listing_ok:
        cov = "non comparable (listing serveur en échec)"
        list_ok = "ÉCHEC listing"
    elif r.get("coverage_ok"):
        cov = "✓ 100 % (tous les locaux sont en ligne)"
        list_ok = "OK"
    else:
        cov = "✗ incomplète (locaux absents du serveur)"
        list_ok = "OK"
    lines.append(f"  Couverture      : {cov}  (listing {list_ok})")
    if files_registered and not listing_ok:
        lines.append(
            "  Enregistrement  : les WAV Data_k sont déjà connus de cette "
            "participation. Lancer Tadarida. Si l'analyse sort 0 contact, "
            "le son n'est probablement pas arrivé sur le serveur "
            "(coupure pendant l'envoi) : nouvelle participation et "
            "renvoyer Data_k."
        )
    missing = r.get("missing_on_server") or []
    if missing and listing_ok:
        preview = ", ".join(missing[:8])
        more = f" … (+{len(missing) - 8})" if len(missing) > 8 else ""
        lines.append(
            f"  À uploader       : {len(missing)} encore dans Data_k, "
            f"absents serveur — {preview}{more}"
        )
    extra = r.get("extra_on_server") or []
    if extra and listing_ok:
        cleaned = (r.get("local_flags") or {}).get("cleaned")
        why = " (normal après nettoyage)" if cleaned else ""
        lines.append(
            f"  Sur serveur seul : {len(extra)} fichier(s) absents de Data_k"
            f"{why} — ce n'est PAS un échec d'upload"
        )
    if r.get("listing_error"):
        err = str(r["listing_error"])
        lines.append(f"  Erreur listing  : {err}")
        if "401" in err or "expir" in err.lower() or "token" in err.lower():
            lines.append(
                "  → Action : Préférences → API Vigie-Chiro → coller un "
                "nouveau token (F12 sur le portail), puis relancer le diagnostic."
            )

    lines.append("")
    lines.append("── État Tadarida (serveur) ──")
    lines.append(f"  traitement.etat : {r.get('traitement_etat') or '(vide / inconnu)'}")
    if r.get("traitement_date"):
        lines.append(f"  date            : {r['traitement_date']}")

    lines.append("")
    lines.append("── Disque local ──")
    if r.get("has_xlsx"):
        xname = Path(r["xlsx_path"]).name if r.get("xlsx_path") else "oui"
        lines.append(f"  xlsx observations : présent ({xname})")
    else:
        lines.append("  xlsx observations : absent")
    flags = r.get("local_flags") or {}
    flag_bits = []
    for k in ("renamed", "te10_done", "uploaded", "analyzed", "cleaned"):
        flag_bits.append(f"{k}={'✓' if flags.get(k) else '·'}")
    lines.append(f"  flags manifest    : {'  '.join(flag_bits)}")

    meta_changes = r.get("meta_changes") or []
    if meta_changes:
        lines.append("")
        lines.append("── Métadonnées participation ──")
        lines.append(
            "  Écart local / serveur : " + ", ".join(meta_changes)
        )
        lines.append(
            "  (PATCH uniquement, Tadarida n'est pas relancée)"
        )

    lines.append("")
    lines.append("── Actions proposées ──")
    suggested = r.get("suggested_actions") or [ACTION_NOOP]
    for a in suggested:
        lines.append(f"  • {action_label(a)}")

    if r.get("applied_actions"):
        lines.append("")
        lines.append("── Actions appliquées ──")
        for a in r["applied_actions"]:
            lines.append(f"  ✓ {action_label(a)}")

    if r.get("skipped_actions"):
        lines.append("")
        lines.append("── Actions ignorées ──")
        for s in r["skipped_actions"]:
            if isinstance(s, dict):
                lines.append(
                    f"  · {s.get('action', '?')} — {s.get('reason', '')}"
                )
            else:
                lines.append(f"  · {s}")

    if r.get("notes"):
        lines.append("")
        lines.append("── Notes ──")
        for n in r["notes"]:
            lines.append(f"  · {n}")

    if r.get("errors"):
        lines.append("")
        lines.append("── Erreurs ──")
        for e in r["errors"]:
            lines.append(f"  ✗ {e}")

    mode = "dry-run (aucune modification)" if r.get("dry_run", True) else "apply"
    lines.append("")
    lines.append(f"Mode : {mode}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

def diagnose_and_repair_session(
    session: Path | str,
    token: str | None = None,
    *,
    apply: bool = False,
    allow_trigger: bool = False,
    confirm_trigger: bool = False,
    allow_fetch: bool = True,
    allow_sync_meta: bool = True,
    allow_set_uploaded: bool = True,
    allowed_meta_changes: list[str] | None = None,
    client: RepairClient | None = None,
    registry: RegistryLike | None = None,
    registry_session_id: str | None = None,
    progress=None,
) -> dict[str, Any]:
    """Diagnostique (et optionnellement répare) l'état d'**une** session.

    Parameters
    ----------
    session
        Chemin du dossier de session (une nuit).
    token
        Token API Vigie-Chiro. Requis sauf si ``client`` est injecté.
    apply
        ``False`` (défaut) = dry-run, aucune écriture. ``True`` = applique
        les actions autorisées (flags, fetch, trigger si confirmé).
    allow_trigger
        Autorise la *proposition exécutable* de ``trigger_compute``.
        Seul, ne suffit pas : il faut aussi ``confirm_trigger=True``.
    confirm_trigger
        Confirmation explicite (équivalent UI « Oui »). Double barrière
        avec ``allow_trigger`` pour éviter un double job accidentel.
    allow_fetch
        Si True et état TERMINE/FINI sans xlsx, télécharge les observations
        quand ``apply=True``.
    client
        Client API injectable (tests / mocks). Sinon construit via token.
    registry
        Registry optionnel pour ``update_fields`` ciblé (pas de pull global).
    registry_session_id
        ID registry (défaut = nom du dossier session).
    progress
        Callback optionnel ``(done, total, label)`` (fetch uniquement).

    Returns
    -------
    dict
        Rapport sérialisable (voir :class:`RepairReport`).

    Notes
    -----
    - Strictement une session : aucun parcours multi-nuits.
    - Couverture 100 % exigée pour auto-set ``flags.uploaded``.
    - ``resume_upload_missing`` est **suggéré** mais non exécuté ici
      (relancer ``run_phase_upload`` / bouton Upload côté UI).
    """
    session = resolve_session_root(Path(session))
    report = RepairReport(
        session=str(session),
        apply=bool(apply),
        dry_run=not bool(apply),
    )

    if not session.is_dir():
        report.errors.append(f"session introuvable ou pas un dossier : {session}")
        report.suggested_actions = [ACTION_NOOP]
        return report.to_dict()

    # -- Manifest ----------------------------------------------------------
    m = Manifest.load_or_create(session)
    flags = dict(m.flags or {})
    report.local_flags = {
        "renamed": bool(flags.get("renamed")),
        "te10_done": bool(flags.get("te10_done")),
        "uploaded": bool(flags.get("uploaded")),
        "analyzed": bool(flags.get("analyzed")),
        "cleaned": bool(flags.get("cleaned")),
    }

    # -- Tableur et noms locaux (pas d'appel réseau) ------------------------
    xlsx = find_local_observations_xlsx(session)
    local_wavs = list_local_data_k_wavs(session)
    report.local_wav_count = len(local_wavs)
    report.has_xlsx = xlsx is not None
    report.xlsx_path = str(xlsx) if xlsx else None

    part_id = (m.meta or {}).get("vigiechiro_participation_id")
    recovered_pid_from_xlsx = False
    if not part_id and xlsx is not None:
        part_id = participation_id_from_observations_name(xlsx.name)
        if part_id:
            recovered_pid_from_xlsx = True
            report.notes.append(
                f"ID participation relu depuis {xlsx.name}"
            )
    report.participation_id = str(part_id) if part_id else None
    if recovered_pid_from_xlsx and apply and part_id:
        try:
            m.set_meta(vigiechiro_participation_id=part_id)
        except Exception:
            pass

    if not report.participation_id:
        report.errors.append(
            "pas d'ID participation dans le manifest "
            "(meta.vigiechiro_participation_id manquant)"
        )
        report.suggested_actions = suggest_actions(
            coverage_ok=False,
            listing_ok=False,
            missing_on_server=[],
            traitement_etat=None,
            has_xlsx=report.has_xlsx,
            flag_uploaded=report.local_flags["uploaded"],
            has_participation_id=False,
        )
        if report.has_xlsx:
            report.notes.append(
                "Un tableur d'observations est présent, mais sans ID "
                "participation. Relancer Scanner, ou Upload pour recréer "
                "la liaison portail."
            )
        else:
            report.notes.append(
                "Créer/reprendre une participation via Upload avant réparation."
            )
        return report.to_dict()

    # -- Client API --------------------------------------------------------
    api = client
    if api is None:
        if not token:
            report.errors.append(
                "token API requis (ou injecter client= pour les tests)"
            )
            report.suggested_actions = [ACTION_NOOP]
            return report.to_dict()
        from vigiechiro_api import VigieChiroClient
        api = VigieChiroClient(token)

    # -- État traitement ---------------------------------------------------
    etat: str | None = None
    try:
        status = api.participation_status(report.participation_id)
        etat = status.get("etat")
        report.traitement_etat = etat
        report.traitement_date = status.get("date")
    except Exception as e:
        report.errors.append(f"participation_status : {e}")
        # On continue si possible pour lister les fichiers

    etat_u = (etat or "").strip().upper()
    # Nuit déjà analysée : le tableur suffit. Lister des milliers de WAV
    # (pages de 99) prend un quart d'heure et ne change pas l'action.
    skip_listing = etat_u in _ETAT_DONE
    server_names: list[str] = []
    listing_ok = True
    if skip_listing:
        report.coverage_skipped = True
        report.listing_ok = True
        report.coverage_ok = True
        report.files_registered = True
        report.registration_via = "etat_terminal"
        if report.has_xlsx:
            report.notes.append(
                "Nuit déjà analysée sur le portail, tableur déjà dans le "
                "dossier : pas de comparaison des WAV."
            )
        else:
            report.notes.append(
                "Nuit déjà analysée sur le portail : le tableur manque "
                "en local. Pas de comparaison des WAV, téléchargement proposé."
            )
        if progress:
            try:
                progress(1, 1, "nuit déjà analysée")
            except Exception:
                pass
    elif progress:
        try:
            progress(len(local_wavs), len(local_wavs) or 1,
                     f"{len(local_wavs)} WAV locaux")
        except Exception:
            pass

    # -- Listing fichiers serveur (sauf nuit déjà analysée) ----------------
    if not skip_listing:
        try:
            try:
                server_names = list(api.list_participation_files(
                    report.participation_id, progress=progress) or [])
            except TypeError:
                server_names = list(
                    api.list_participation_files(report.participation_id) or [])
        except Exception as e:
            listing_ok = False
            report.listing_error = str(e)
            report.errors.append(f"list_participation_files : {e}")

        # Listing vide + beaucoup de locaux + xlsx déjà là → suspect.
        # On refuse alors de proposer un re-upload massif de tout Data_k.
        empty_listing_suspect = (
            listing_ok
            and not server_names
            and len(local_wavs) >= 20
            and (report.has_xlsx or report.local_flags.get("cleaned")
                 or report.local_flags.get("uploaded")
                 or etat_u in _ETAT_DONE)
        )
        if empty_listing_suspect:
            listing_ok = False
            report.listing_error = (
                report.listing_error
                or "listing serveur vide alors que la session a déjà un xlsx / "
                   "flag uploadé-nettoyé : listing jugé non fiable"
            )
            report.notes.append(
                "Listing serveur = 0 fichier alors que Data_k en contient "
                f"{len(local_wavs)} et qu'un xlsx ou un flag indique un "
                "traitement déjà avancé. Pas de re-upload de tout Data_k. "
                "Vérifie la participation sur le portail Vigie-Chiro."
            )
            server_names = []

        cov = compute_coverage(local_wavs, server_names, listing_ok=listing_ok)
        report.server_wav_count = cov["server_wav_count"]
        report.missing_on_server = list(cov["missing_on_server"])
        report.extra_on_server = list(cov["extra_on_server"])
        report.coverage_ok = bool(cov["coverage_ok"])
        report.listing_ok = bool(cov["listing_ok"])
        report.files_registered = bool(report.coverage_ok)
        report.registration_via = "listing" if report.coverage_ok else None

    # Listing vide ou 403 (GET /fichiers → S3 AccessDenied) alors que Data_k
    # a des WAV et que Tadarida n'a jamais produit de /donnees : sonder un
    # échantillon de titres via POST /fichiers. HTTP 409 = déjà enregistré.
    need_probe = (
        bool(local_wavs)
        and not report.coverage_ok
        and (not report.listing_ok or not server_names)
        and (etat or "").strip().upper() not in _ETAT_DONE
        and not report.has_xlsx
    )
    probe_fn = getattr(api, "probe_titre_registered", None)
    if need_probe and callable(probe_fn):
        sample = pick_probe_names(local_wavs, 5)
        probe_hits: list[str] = []
        for name in sample:
            try:
                probe_hits.append(str(probe_fn(report.participation_id, name)))
            except Exception:
                probe_hits.append("unknown")
        n_reg = probe_hits.count("registered")
        n_abs = probe_hits.count("absent")
        if sample and n_reg == len(probe_hits):
            report.files_registered = True
            report.registration_via = "409_probe"
            report.listing_ok = False
            report.missing_on_server = []
            report.listing_error = (
                report.listing_error
                or "listing portail indisponible ou vide ; "
                   "fichiers confirmés (code 409, déjà enregistrés)"
            )
            report.notes.append(
                "Le portail n'arrive pas à lister les fichiers, mais les "
                f"{len(sample)} noms sondés de Data_k sont déjà enregistrés "
                "(code 409). Cas typique : l'envoi a créé les fiches, puis "
                "s'est interrompu (réseau ou saturation) avant le lancement "
                "de Tadarida. Lancer l'analyse. Si elle sort 0 contact, "
                "le son n'est pas sur le serveur : nouvelle participation et "
                "renvoyer Data_k."
            )
        elif sample and n_abs == len(probe_hits):
            report.notes.append(
                "Les noms sondés ne sont pas encore sur le serveur. "
                "Reprends l'upload."
            )
        elif n_reg and n_abs:
            report.notes.append(
                f"État mixte : {n_reg} déjà enregistré(s), {n_abs} encore "
                f"absent(s). Relance Upload : les déjà enregistrés (code 409) "
                f"seront sautés, les manquants renvoyés, puis Tadarida part."
            )

    if not skip_listing and not local_wavs:
        report.notes.append(
            "Data_k/ absent ou vide : couverture locale non évaluable.")

    # Post-nettoyage : beaucoup d'extras serveur est attendu
    if report.local_flags.get("cleaned") and report.extra_on_server:
        report.notes.append(
            f"{len(report.extra_on_server)} fichier(s) encore sur le serveur "
            "mais absents de Data_k/ (supprimés au nettoyage) — normal, "
            "ce ne sont pas des manquants d'upload."
        )
    if (report.listing_ok
            and report.local_wav_count > 0
            and report.server_wav_count > 0
            and report.server_wav_count < report.local_wav_count
            and len(report.missing_on_server) > 50
            and report.server_wav_count <= 99):
        report.notes.append(
            "Le listing serveur semble tronqué (≤99 fichiers). "
            "Relance le diagnostic ; si ça persiste, vérifie l'API."
        )

    # -- Métadonnées participation (série, type, T°, horaires) -------------
    meta_needs_sync = False
    try:
        local_fields = collect_local_participation_fields(session)
        raw_part: dict = {}
        getter = getattr(api, "get_participation", None)
        if callable(getter):
            pobj = getter(report.participation_id)
            raw_cand = getattr(pobj, "raw", None)
            if isinstance(raw_cand, dict):
                raw_part = raw_cand
            elif isinstance(pobj, dict):
                raw_part = pobj
        server_fields = server_fields_from_participation(raw_part)
        meta_patch = diff_participation_update(server_fields, local_fields)
        report.meta_changes = list(meta_patch.get("changes") or [])
        meta_needs_sync = bool(report.meta_changes)
        if report.meta_changes:
            report.notes.append(
                "Métadonnées à pousser (sans relancer Tadarida) : "
                + ", ".join(report.meta_changes)
            )
    except Exception as e:
        report.notes.append(f"comparaison métadonnées : {e}")

    # -- Suggestions -------------------------------------------------------
    report.suggested_actions = suggest_actions(
        coverage_ok=report.coverage_ok,
        listing_ok=report.listing_ok,
        missing_on_server=report.missing_on_server,
        traitement_etat=etat,
        has_xlsx=report.has_xlsx,
        flag_uploaded=report.local_flags["uploaded"],
        has_participation_id=True,
        files_registered=report.files_registered,
        meta_needs_sync=meta_needs_sync,
    )

    if not apply:
        report.notes.append("dry-run : aucune modification (apply=False).")
        return report.to_dict()

    # =====================================================================
    # APPLY
    # =====================================================================
    actions_planned = list(report.suggested_actions)
    manifest_dirty = bool(recovered_pid_from_xlsx)

    def _skip(action: str, reason: str) -> None:
        report.skipped_actions.append({"action": action, "reason": reason})

    # --- set_uploaded_true ------------------------------------------------
    if ACTION_SET_UPLOADED in actions_planned:
        if not allow_set_uploaded:
            _skip(ACTION_SET_UPLOADED, "allow_set_uploaded=False")
        elif not report.coverage_ok:
            _skip(ACTION_SET_UPLOADED, "couverture < 100 %")
        elif not report.listing_ok:
            _skip(ACTION_SET_UPLOADED, "listing serveur non fiable")
        else:
            try:
                m.flags["uploaded"] = True
                m.record_action(
                    "repair",
                    status="ok",
                    params={
                        "kind": "set_uploaded_true",
                        "participation_id": report.participation_id,
                    },
                    stats={
                        "local_wav_count": report.local_wav_count,
                        "server_wav_count": report.server_wav_count,
                        "traitement_etat": etat,
                    },
                    notes="alignement flag uploaded (couverture 100 %)",
                    tool_version=TOOL_VERSION,
                )
                # record_action("repair") ne pose pas de flag dédié — OK
                manifest_dirty = True
                report.applied_actions.append(ACTION_SET_UPLOADED)
                report.local_flags["uploaded"] = True
            except Exception as e:
                report.errors.append(f"set_uploaded_true : {e}")

    # --- sync_participation_meta : PATCH sans trigger_compute -------------
    if ACTION_SYNC_META in actions_planned:
        if not allow_sync_meta:
            _skip(ACTION_SYNC_META, "allow_sync_meta=False")
        else:
            editor = getattr(api, "edit_participation", None)
            if not callable(editor):
                _skip(ACTION_SYNC_META, "client sans edit_participation")
            else:
                try:
                    local_fields = collect_local_participation_fields(session)
                    raw_part = {}
                    getter = getattr(api, "get_participation", None)
                    if callable(getter):
                        pobj = getter(report.participation_id)
                        raw_cand = getattr(pobj, "raw", None)
                        if isinstance(raw_cand, dict):
                            raw_part = raw_cand
                        elif isinstance(pobj, dict):
                            raw_part = pobj
                    patch = diff_participation_update(
                        server_fields_from_participation(raw_part),
                        local_fields,
                        only_changes=allowed_meta_changes,
                    )
                    changes = list(patch.pop("changes", []) or [])
                    if not changes or not patch:
                        _skip(ACTION_SYNC_META, "plus d'écart à l'application")
                    else:
                        editor(report.participation_id, **patch)
                        cached = dict((m.meta or {}).get("participation_payload") or {})
                        if patch.get("date_debut") is not None:
                            dd = patch["date_debut"]
                            cached["date_debut"] = (
                                dd.isoformat() if hasattr(dd, "isoformat") else str(dd)
                            )
                        if patch.get("date_fin") is not None:
                            df = patch["date_fin"]
                            cached["date_fin"] = (
                                df.isoformat() if hasattr(df, "isoformat") else str(df)
                            )
                        if isinstance(patch.get("meteo"), dict):
                            for k in ("temperature_debut", "temperature_fin",
                                      "vent", "couverture"):
                                if patch["meteo"].get(k) is not None:
                                    cached[k] = patch["meteo"][k]
                        if isinstance(patch.get("configuration"), dict):
                            for k, v in patch["configuration"].items():
                                if v is not None and v != "":
                                    cached[k] = v
                        m.set_meta(participation_payload=cached)
                        m.record_action(
                            "repair",
                            status="ok",
                            params={
                                "kind": "sync_participation_meta",
                                "participation_id": report.participation_id,
                            },
                            stats={"changes": changes},
                            notes="PATCH métadonnées, Tadarida non relancée",
                            tool_version=TOOL_VERSION,
                        )
                        manifest_dirty = True
                        report.applied_actions.append(ACTION_SYNC_META)
                        report.notes.append(
                            "Métadonnées mises à jour sur Vigie-Chiro : "
                            + ", ".join(changes)
                        )
                except Exception as e:
                    report.errors.append(f"sync_participation_meta : {e}")

    # --- resume_upload_missing : suggestion seule -------------------------
    if ACTION_RESUME_UPLOAD in actions_planned:
        _skip(
            ACTION_RESUME_UPLOAD,
            "non exécuté par repair — relancer run_phase_upload / Upload UI",
        )
        report.notes.append(
            f"{len(report.missing_on_server)} WAV manquant(s) sur le serveur "
            f"— relancer l'upload pour reprise automatique."
        )

    # --- trigger_compute --------------------------------------------------
    if ACTION_TRIGGER in actions_planned:
        if not (report.coverage_ok or report.files_registered):
            _skip(ACTION_TRIGGER, "fichiers manquants sur le serveur")
        elif not allow_trigger:
            _skip(ACTION_TRIGGER, "allow_trigger=False")
        elif not confirm_trigger:
            _skip(ACTION_TRIGGER, "confirm_trigger=False (confirmation requise)")
        else:
            try:
                api.trigger_compute(report.participation_id)
                m.record_action(
                    "repair",
                    status="ok",
                    params={
                        "kind": "trigger_compute",
                        "participation_id": report.participation_id,
                    },
                    stats={"traitement_etat_before": etat},
                    notes="trigger_compute demandé explicitement",
                    tool_version=TOOL_VERSION,
                )
                manifest_dirty = True
                report.applied_actions.append(ACTION_TRIGGER)
                report.notes.append("trigger_compute envoyé au serveur.")
            except Exception as e:
                report.errors.append(f"trigger_compute : {e}")
                try:
                    m.record_action(
                        "repair",
                        status="error",
                        params={
                            "kind": "trigger_compute",
                            "participation_id": report.participation_id,
                        },
                        notes=str(e),
                        tool_version=TOOL_VERSION,
                    )
                    manifest_dirty = True
                except Exception:
                    pass

    # --- fetch_xlsx -------------------------------------------------------
    if ACTION_FETCH in actions_planned:
        if not allow_fetch:
            _skip(ACTION_FETCH, "allow_fetch=False")
        elif report.has_xlsx:
            _skip(ACTION_FETCH, "xlsx déjà présent")
        else:
            etat_u = (etat or "").strip().upper()
            if etat_u not in _ETAT_DONE:
                _skip(
                    ACTION_FETCH,
                    f"état non terminal ({etat!r}) — fetch refusé",
                )
            else:
                try:
                    dst = session / (
                        f"participation-{report.participation_id}-observations.xlsx"
                    )
                    res = api.download_observations_as_xlsx(
                        report.participation_id, dst, on_progress=progress,
                    )
                    m.record_action(
                        "fetch_observations",
                        status="ok",
                        params={"participation_id": report.participation_id,
                                "source": "repair"},
                        stats=res if isinstance(res, dict) else {},
                        tool_version=TOOL_VERSION,
                    )
                    # resync_state : journalise l'alignement post-fetch
                    m.record_action(
                        "resync_state",
                        status="ok",
                        params={
                            "kind": "fetch_xlsx",
                            "participation_id": report.participation_id,
                        },
                        stats={
                            "xlsx": dst.name,
                            "traitement_etat": etat,
                        },
                        notes="xlsx récupéré par repair",
                        tool_version=TOOL_VERSION,
                    )
                    manifest_dirty = True
                    report.applied_actions.append(ACTION_FETCH)
                    report.has_xlsx = True
                    report.xlsx_path = str(dst)
                    report.notes.append(f"xlsx téléchargé : {dst.name}")
                except Exception as e:
                    report.errors.append(f"fetch_xlsx : {e}")
                    try:
                        m.record_action(
                            "resync_state",
                            status="error",
                            params={"kind": "fetch_xlsx"},
                            notes=str(e),
                            tool_version=TOOL_VERSION,
                        )
                        manifest_dirty = True
                    except Exception:
                        pass

    if ACTION_NOOP in actions_planned and not report.applied_actions:
        report.notes.append("noop : état déjà cohérent ou rien d'applicable.")

    # --- Persist manifest -------------------------------------------------
    if manifest_dirty:
        try:
            m.save(session)
        except Exception as e:
            report.errors.append(f"sauvegarde manifest : {e}")

    # --- Registry ciblé (pas de pull multi-nuits) -------------------------
    if registry is not None:
        sid = registry_session_id or session.name
        fields: dict[str, Any] = {
            "api_etat": etat or "",
            "last_api_sync_at": _now_iso(),
        }
        if report.participation_id:
            fields["vigiechiro_participation_id"] = report.participation_id
        if report.local_flags.get("uploaded") or ACTION_SET_UPLOADED in report.applied_actions:
            fields["uploaded"] = 1
        # analyzed côté registry = xlsx présent OU état terminal (upgrade-only
        # cohérent avec sync_from_api). On ne downgrade jamais.
        if report.has_xlsx or (etat or "").strip().upper() in _ETAT_DONE:
            if report.has_xlsx:
                fields["analyzed"] = 1
        try:
            # N'écrit que si la session existe déjà dans le registry
            existing = None
            try:
                existing = registry.get_session(sid)
            except Exception:
                existing = None
            if existing is not None:
                registry.update_fields(sid, fields)
                report.notes.append(f"registry mis à jour (id={sid}).")
            else:
                report.notes.append(
                    f"registry : session id={sid!r} absente — update ignoré."
                )
        except Exception as e:
            report.errors.append(f"registry.update_fields : {e}")

    # Journal campagne (best-effort, non bloquant)
    try:
        from campaign_log import log_to_campaign
        log_to_campaign(
            session,
            phase="repair",
            action="diagnose_and_repair",
            status="ok" if not report.errors else "warning",
            stats={
                "applied": report.applied_actions,
                "suggested": report.suggested_actions,
                "coverage_ok": report.coverage_ok,
                "etat": etat,
            },
            notes="; ".join(report.notes[:3]) if report.notes else None,
            tool_version=TOOL_VERSION,
        )
    except Exception:
        pass

    return report.to_dict()
