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
ACTION_NOOP = "noop"

SUGGESTED_ACTIONS = (
    ACTION_SET_UPLOADED,
    ACTION_RESUME_UPLOAD,
    ACTION_TRIGGER,
    ACTION_FETCH,
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
    def download_observations_as_xlsx(
        self, participation_id: str, dst: Path, on_progress=None,
    ) -> dict: ...


class RegistryLike(Protocol):
    def update_fields(self, sid: str, fields: dict) -> None: ...
    def get_session(self, sid: str) -> dict | None: ...


# ---------------------------------------------------------------------------
# Helpers purs (testables sans I/O réseau)
# ---------------------------------------------------------------------------

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
) -> list[str]:
    """Détermine les actions logiques (pure). Ne regarde pas allow_*.

    Ordre stable, déterministe. Retourne toujours au moins ``noop`` si
    aucune action corrective n'est pertinente.
    """
    if not has_participation_id:
        return [ACTION_NOOP]

    actions: list[str] = []
    etat = (traitement_etat or "").strip().upper()

    # 1. Fichiers manquants → reprise upload, jamais trigger / set_uploaded
    if listing_ok and missing_on_server:
        actions.append(ACTION_RESUME_UPLOAD)
        # Pas de set_uploaded ni trigger tant que la couverture n'est pas 100 %
        if etat in _ETAT_DONE and not has_xlsx:
            # Analyse déjà finie côté serveur malgré trous locaux ? rare ;
            # on peut quand même récupérer l'xlsx.
            actions.append(ACTION_FETCH)
        return actions or [ACTION_NOOP]

    # 2. Listing KO → on ne propose rien d'automatique risqué
    if not listing_ok:
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
    listing_ok: bool = True
    listing_error: str | None = None
    traitement_etat: str | None = None
    traitement_date: str | None = None
    has_xlsx: bool = False
    xlsx_path: str | None = None
    local_flags: dict[str, bool] = field(default_factory=dict)
    suggested_actions: list[str] = field(default_factory=list)
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
    ACTION_TRIGGER: "Relancer l'analyse Tadarida (trigger_compute)",
    ACTION_FETCH: "Télécharger le tableur d'observations (xlsx)",
    ACTION_NOOP: "Aucune action nécessaire",
}


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
    if not listing_ok:
        cov = "non comparable (listing serveur en échec)"
        list_ok = "ÉCHEC listing"
    elif r.get("coverage_ok"):
        cov = "✓ 100 % (tous les locaux sont en ligne)"
        list_ok = "OK"
    else:
        cov = "✗ incomplète (locaux absents du serveur)"
        list_ok = "OK"
    lines.append(f"  Couverture      : {cov}  (listing {list_ok})")
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
    session = Path(session)
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
    part_id = (m.meta or {}).get("vigiechiro_participation_id")
    report.participation_id = str(part_id) if part_id else None

    # -- Disque local ------------------------------------------------------
    local_wavs = list_local_data_k_wavs(session)
    report.local_wav_count = len(local_wavs)
    xlsx = find_local_observations_xlsx(session)
    report.has_xlsx = xlsx is not None
    report.xlsx_path = str(xlsx) if xlsx else None

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

    # -- Listing fichiers serveur ------------------------------------------
    server_names: list[str] = []
    listing_ok = True
    try:
        server_names = list(api.list_participation_files(report.participation_id) or [])
    except Exception as e:
        listing_ok = False
        report.listing_error = str(e)
        report.errors.append(f"list_participation_files : {e}")

    # Listing vide + beaucoup de locaux + xlsx déjà là → suspect (souvent
    # bug API / max_results / filtre), PAS « 0 WAV uploadés ».
    # On refuse alors de proposer un re-upload massif de tout Data_k.
    empty_listing_suspect = (
        listing_ok
        and not server_names
        and len(local_wavs) >= 20
        and (report.has_xlsx or report.local_flags.get("cleaned")
             or report.local_flags.get("uploaded")
             or (etat or "").strip().upper() in _ETAT_DONE)
    )
    if empty_listing_suspect:
        listing_ok = False
        report.listing_error = (
            report.listing_error
            or "listing serveur vide alors que la session a déjà un xlsx / "
               "flag uploadé-nettoyé — listing jugé non fiable"
        )
        report.notes.append(
            "⚠ Listing serveur = 0 fichier alors que Data_k en contient "
            f"{len(local_wavs)} et qu'un xlsx/flag indique un traitement déjà "
            "avancé. On ne propose PAS de re-uploader tout Data_k. "
            "Vérifie la participation sur le portail Vigie-Chiro."
        )
        server_names = []  # coverage with listing_ok=False

    cov = compute_coverage(local_wavs, server_names, listing_ok=listing_ok)
    report.server_wav_count = cov["server_wav_count"]
    report.missing_on_server = list(cov["missing_on_server"])
    report.extra_on_server = list(cov["extra_on_server"])
    report.coverage_ok = bool(cov["coverage_ok"])
    report.listing_ok = bool(cov["listing_ok"])

    if not local_wavs:
        report.notes.append("Data_k/ absent ou vide — couverture locale non évaluable.")

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

    # -- Suggestions -------------------------------------------------------
    report.suggested_actions = suggest_actions(
        coverage_ok=report.coverage_ok,
        listing_ok=report.listing_ok,
        missing_on_server=report.missing_on_server,
        traitement_etat=etat,
        has_xlsx=report.has_xlsx,
        flag_uploaded=report.local_flags["uploaded"],
        has_participation_id=True,
    )

    if not apply:
        report.notes.append("dry-run : aucune modification (apply=False).")
        return report.to_dict()

    # =====================================================================
    # APPLY
    # =====================================================================
    actions_planned = list(report.suggested_actions)
    manifest_dirty = False

    def _skip(action: str, reason: str) -> None:
        report.skipped_actions.append({"action": action, "reason": reason})

    # --- set_uploaded_true ------------------------------------------------
    if ACTION_SET_UPLOADED in actions_planned:
        if not report.coverage_ok:
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
        if not report.coverage_ok:
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
