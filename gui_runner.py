"""
gui_runner.py — exécution d'une phase pipeline en arrière-plan avec modal
de progression.

Principe :
  - On affiche un CTkToplevel modal avec zone texte + bouton Fermer (désactivé
    pendant l'exécution).
  - Un thread worker fait tourner la phase et appelle ``log(line)`` pour
    alimenter le textbox en temps réel (via after(0, ...)).
  - À la fin, le bouton Fermer s'active.
"""

from __future__ import annotations

import sys
import threading
import traceback
from io import StringIO
from pathlib import Path
from typing import Callable

import customtkinter as ctk


class RunDialog(ctk.CTkToplevel):
    """Modal de progression d'une phase pipeline."""

    def __init__(self, master, title: str,
                 worker: Callable[[Callable[[str], None]], dict],
                 on_done: Callable[[dict], None] | None = None):
        super().__init__(master)
        self.title(title)
        self.geometry("720x520")
        self.minsize(600, 400)
        self.transient(master)
        self.after(50, self.grab_set)

        self.worker = worker
        self.on_done = on_done
        self.result: dict | None = None
        # Initialisé AVANT tout after() : _on_close_attempt lit self._done, et
        # l'utilisateur peut fermer la fenêtre dans les 100ms avant _launch.
        self._done = False

        self._build_ui(title)
        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        self.after(100, self._launch)

    def _build_ui(self, title: str):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkLabel(self, text=title,
                                font=ctk.CTkFont(size=15, weight="bold"),
                                anchor="w")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))

        self.textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=11),
                                        wrap="none", activate_scrollbars=True)
        self.textbox.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        self.textbox.configure(state="disabled")

        # --- Bloc progression (barre + label pourcentage + ETA)
        # Masqué par défaut, affiché dès que update_progress() est appelé.
        self._progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._progress_frame.grid(row=2, column=0, sticky="ew",
                                     padx=16, pady=(0, 6))
        self._progress_frame.grid_columnconfigure(0, weight=1)
        self._progress_frame.grid_remove()  # caché par défaut

        self.progress_bar = ctk.CTkProgressBar(self._progress_frame, height=12)
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.progress_lbl = ctk.CTkLabel(
            self._progress_frame, text="", width=200,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=("gray35", "gray70"),
            anchor="e",
        )
        self.progress_lbl.grid(row=0, column=1, sticky="e")

        # --- Footer (status + bouton fermer)
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        footer.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(
            footer, text="⏳  Préparation…",
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.status_lbl.grid(row=0, column=0, sticky="w")

        # Bouton "Arrière-plan" : visible en phase wait (long-poll Tadarida).
        # Le traitement tourne côté serveur Vigie-Chiro, fermer la fenêtre ne
        # casse rien. L'utilisateur récupère le xlsx plus tard en relançant
        # « Upload + Tadarida » (qui détecte la participation existante) ou
        # via le bouton « 🔄 Sync API » du Registre.
        self.background_btn = ctk.CTkButton(
            footer, text="🔌 Arrière-plan", width=140, height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_background,
        )
        # Caché par défaut, affiché par _apply_progress quand label = wait
        self.background_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        self.background_btn.grid_remove()

        self.close_btn = ctk.CTkButton(footer, text="Fermer", width=120, height=32,
                                         state="disabled",
                                         command=self._on_close_attempt)
        self.close_btn.grid(row=0, column=2, sticky="e")

        # État ETA : timestamp du 1er appel progress pour un (total) donné
        self._progress_start_ts: float | None = None
        self._progress_last_total: int | None = None
        self._progress_last_ui_update: float = 0.0

    # -- Log helper ---------------------------------------------------------

    def _append(self, line: str):
        # Le widget a pu être détruit entre-temps (utilisateur a fermé la
        # modale alors que le worker continue) — on ignore proprement.
        try:
            if not self.winfo_exists():
                return
            self.textbox.configure(state="normal")
            self.textbox.insert("end", line + "\n")
            self.textbox.see("end")
            self.textbox.configure(state="disabled")
        except Exception:
            pass

    def update_progress(self, done: int, total: int, label: str = ""):
        """Callback thread-safe pour reporter l'avancement.

        Appelé depuis le thread worker (pipeline). On marshalle vers l'UI via
        after(0, ...). Throttle interne à 100ms max pour ne pas saturer Tk
        sur des milliers de callbacks.
        """
        import time
        now = time.monotonic()
        if now - self._progress_last_ui_update < 0.1 and done < total:
            return  # throttle : une update UI max / 100ms
        self._progress_last_ui_update = now
        try:
            self.after(0, self._apply_progress, done, total, label)
        except Exception:
            pass

    def _apply_progress(self, done: int, total: int, label: str):
        """Exécuté sur le thread UI (via after)."""
        import time
        try:
            if not self.winfo_exists():
                return
            # Reset des compteurs si on change de "phase" (total différent)
            if self._progress_last_total != total:
                self._progress_last_total = total
                self._progress_start_ts = time.monotonic()
            # Affiche le bloc progression la 1ère fois
            try:
                self._progress_frame.grid()
            except Exception:
                pass
            # Phase wait Tadarida : done/total = SECONDES écoulées / timeout, pas
            # des fichiers → surtout pas d'ETA ni de ratio "X/Y" trompeur (un
            # "178m" mensonger). On affiche le temps d'attente ; le traitement
            # est côté serveur, sa durée réelle est inconnue.
            is_wait = bool(label) and "wait" in label.lower()
            pct = (done / total) if total else 0.0
            self.progress_bar.set(pct)

            if is_wait:
                mins = done // 60
                txt = f"{label}   ·   {mins} min d'attente"
            else:
                # ETA basé sur le débit observé depuis le début de la phase
                elapsed = time.monotonic() - (self._progress_start_ts or time.monotonic())
                if done > 0 and elapsed > 1.0:
                    rate = done / elapsed
                    eta = int((total - done) / rate) if rate > 0 else 0
                    eta_s = (f"{eta // 60}m{eta % 60:02d}s"
                             if eta >= 60 else f"{eta}s")
                    txt = f"{done}/{total}  ({int(pct * 100)}%)  ETA {eta_s}"
                else:
                    txt = f"{done}/{total}  ({int(pct * 100)}%)"
                if label:
                    txt = f"{label}   {txt}"
            self.progress_lbl.configure(text=txt)

            # En phase wait Tadarida, on expose le bouton "Arrière-plan" :
            # le traitement tourne côté serveur, l'utilisateur peut sortir
            # sans rien casser et récupérer le xlsx plus tard.
            if is_wait:
                try:
                    self.background_btn.grid()
                    self.status_lbl.configure(
                        text="⏳  Tadarida analyse côté serveur — "
                             "tu peux fermer en arrière-plan.",
                        text_color=("gray35", "gray70"),
                    )
                except Exception:
                    pass
            else:
                try:
                    self.background_btn.grid_remove()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_background(self):
        """Ferme la fenêtre tout en laissant le worker tourner en arrière-plan.

        Le thread daemon=True continue jusqu'à la fin (timeout 3h max sur
        wait). Si l'utilisateur ferme l'app avant la fin, le thread est
        interrompu par l'exit du process — l'analyse Tadarida côté serveur
        n'est pas affectée. Pour récupérer le xlsx ensuite, relancer
        « Upload + Tadarida » qui détectera la participation existante.
        """
        from tkinter import messagebox
        ok = messagebox.askyesno(
            "Continuer en arrière-plan ?",
            "Le traitement Tadarida tourne sur les serveurs Vigie-Chiro, pas "
            "sur ton PC. Fermer cette fenêtre ne casse rien.\n\n"
            "Pour récupérer le xlsx d'observations plus tard :\n"
            "  • relance « Upload + Tadarida » sur la même session\n"
            "    (l'app détecte la participation existante et récupère "
            "directement le résultat)\n"
            "  • ou onglet Registre → bouton « 🔄 Sync API »\n\n"
            "Fermer maintenant ?",
            parent=self,
        )
        if ok:
            # Marque _done pour ne pas redéclencher la confirmation classique
            self._done = True
            self.destroy()

    def log(self, line: str):
        """Callback thread-safe pour le worker."""
        try:
            self.after(0, self._append, line)
        except Exception:
            # Tcl interp détruit (app en cours de fermeture) : silencieux
            pass

    # -- Lancement ---------------------------------------------------------

    def _launch(self):
        self._done = False

        def _run():
            try:
                # Les worker() récents acceptent 2 arguments : (log, progress).
                # Ancienne signature (log,) tolérée via TypeError / fallback.
                try:
                    self.result = self.worker(self.log, self.update_progress)
                except TypeError:
                    self.result = self.worker(self.log)
                self.after(0, self._on_finish_ok)
            except Exception:
                err = traceback.format_exc()
                self.after(0, self._on_finish_err, err)

        threading.Thread(target=_run, daemon=True).start()

    def _on_finish_ok(self):
        self._done = True
        result = self.result or {}
        errs = result.get("errors") or []
        err_single = result.get("error")
        warnings = result.get("warnings") or []

        # Affichage des warnings (verify_failed, Suivi verrouillé, etc.) en
        # fin de log, visibles à l'utilisateur
        if warnings:
            self._append("")
            self._append("=== Avertissements ===")
            for w in warnings:
                self._append(f"⚠  {w}")

        if errs or err_single:
            self.status_lbl.configure(text="✗  Terminé avec erreurs",
                                         text_color=("#cf222e", "#f85149"))
        elif warnings:
            self.status_lbl.configure(text="⚠  Terminé avec avertissements",
                                         text_color=("#bf8700", "#d29922"))
        else:
            self.status_lbl.configure(text="✓  Terminé",
                                         text_color=("#2ea043", "#2ea043"))
        self.close_btn.configure(state="normal")
        if self.on_done:
            try:
                self.on_done(self.result or {})
            except Exception:
                self._append(f"\n[callback on_done a levé] {traceback.format_exc()}")

    def _on_finish_err(self, err: str):
        self._done = True
        self._append("\n=== Exception ===\n" + err)
        self.status_lbl.configure(text="✗  Échec",
                                     text_color=("#cf222e", "#f85149"))
        self.close_btn.configure(state="normal")

    def _on_close_attempt(self):
        if self._done:
            self.destroy()
            return
        # Phase encore en cours : demande confirmation avant de laisser
        # l'utilisateur fermer. Le thread de travail continue en arrière-plan
        # (daemon=True, se terminera avec l'app) mais on ne le tue pas
        # brutalement au milieu d'une écriture manifest/xlsx.
        try:
            from tkinter import messagebox
            ok = messagebox.askyesno(
                "Fermer pendant le traitement ?",
                "Un traitement est en cours. Fermer cette fenêtre ne l'annulera "
                "pas — il continuera jusqu'à la fin en arrière-plan.\n\n"
                "Fermer quand même ?",
                parent=self,
            )
        except Exception:
            ok = False
        if ok:
            self._done = True  # évite le re-prompt si re-clic croix
            self.destroy()


# ---------------------------------------------------------------------------
# Helpers de haut niveau : enveloppent les phases du pipeline
# ---------------------------------------------------------------------------

class _StdoutRouter:
    """Redirige sys.stdout vers le bon ``log`` selon le thread courant.

    L'ancienne implémentation échangeait le ``sys.stdout`` global à chaque
    appel : avec des phases concurrentes (upload d'une nuit + attente Tadarida
    d'une autre, en batch), deux threads se marchaient dessus → un thread
    remettait stdout à ``None`` pendant que l'autre lisait ``.buf`` →
    ``AttributeError: 'NoneType' object has no attribute 'buf'``.

    Ici un routeur UNIQUE est installé une fois ; chaque thread enregistre son
    propre callback ``log``. Pas de swap concurrent, pas de sortie mal aiguillée.
    """

    def __init__(self, original):
        self._original = original
        self._logs: dict[int, object] = {}
        self._bufs: dict[int, str] = {}
        self._lock = threading.Lock()

    def register(self, log):
        with self._lock:
            self._logs[threading.get_ident()] = log

    def unregister(self):
        tid = threading.get_ident()
        with self._lock:
            log = self._logs.pop(tid, None)
            rest = self._bufs.pop(tid, "")
        if rest and log is not None:
            try:
                log(rest)
            except Exception:
                pass

    def write(self, s):
        tid = threading.get_ident()
        log = self._logs.get(tid)
        if log is None:
            # Thread sans capture active → sortie d'origine (None en exe windowed)
            if self._original is not None:
                try:
                    self._original.write(s)
                except Exception:
                    pass
            return
        buf = self._bufs.get(tid, "") + s
        lines = []
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            lines.append(line)
        self._bufs[tid] = buf
        for line in lines:
            try:
                log(line)
            except Exception:
                pass

    def flush(self):
        pass


_STDOUT_ROUTER: _StdoutRouter | None = None
_STDOUT_ROUTER_LOCK = threading.Lock()


def _capture_stdout(fn, log):
    """Exécute fn(), redirige son stdout vers log(line) — thread-safe."""
    global _STDOUT_ROUTER
    with _STDOUT_ROUTER_LOCK:
        if _STDOUT_ROUTER is None:
            _STDOUT_ROUTER = _StdoutRouter(sys.stdout)
            sys.stdout = _STDOUT_ROUTER
    _STDOUT_ROUTER.register(log)
    try:
        return fn()
    finally:
        _STDOUT_ROUTER.unregister()


def run_prep(session_path: Path, meta, *, dry_run: bool = False, force: bool = False):
    """Retourne un worker compatible RunDialog pour la phase prep."""
    from pipeline import run_phase_prep

    def worker(log, progress=None):
        log(f"Session : {session_path}")
        log(f"Meta    : site={meta.n_site_tadarida} pt={meta.n_point_fixe} "
            f"pass{meta.n_passage} enr#{meta.n_enregistreur} ({meta.n_serie}) "
            f"{meta.date_debut:%Y-%m-%d}")
        log("")
        log("=== Phase PREP ===")
        log("")
        return _capture_stdout(
            lambda: run_phase_prep(session_path, meta, dry_run=dry_run,
                                     force=force, progress=progress),
            log,
        )

    return worker


def run_cleanup(session_path: Path, meta, settings,
                *, dry_run: bool = False, force: bool = False):
    from pipeline import run_phase_cleanup

    thresholds = {
        "chiros": settings.threshold_chiros,
        "orthos": settings.threshold_orthos,
        "micromam": settings.threshold_micromam,
        "oiseaux": settings.threshold_oiseaux,
    }

    def worker(log, progress=None):
        log(f"Session : {session_path}")
        log(f"Seuils : chiros≥{thresholds['chiros']} "
            f"ortho≥{thresholds['orthos']} mam≥{thresholds['micromam']} "
            f"oisx≥{thresholds['oiseaux']}")
        log(f"Silent : {settings.silent_policy}   Unknown : {settings.unknown_action}")
        log("")
        log("=== Phase CLEANUP ===")
        log("")
        return _capture_stdout(
            lambda: run_phase_cleanup(
                session_path, thresholds, set(), settings.silent_policy,
                settings.unknown_action, dry_run=dry_run, force=force,
                meta=meta, progress=progress,
            ),
            log,
        )

    return worker


def run_upload_flow(session_path: Path, meta, token: str,
                    *, dry_run: bool = False,
                    participation_payload: dict | None = None):
    """Phase upload + wait + fetch en une passe (long !).

    ``participation_payload`` : payload collecté par le wizard GUI
    (météo, config, commentaire, dates). Si None, des défauts sont utilisés.
    """
    from pipeline import run_phase_upload, run_phase_wait, run_phase_fetch

    def worker(log, progress=None):
        log(f"Session : {session_path}")
        log(f"Meta    : site={meta.n_site_tadarida} pt={meta.n_point_fixe} "
            f"pass{meta.n_passage}")
        log("")
        log("=== Phase UPLOAD ===")
        r = _capture_stdout(
            lambda: run_phase_upload(
                session_path, meta, dry_run=dry_run,
                token=token,
                participation_payload=participation_payload,
                progress=progress,
            ),
            log,
        )
        if r.get("error"):
            return r
        if dry_run:
            log("(dry-run → on saute wait + fetch)")
            return r

        log("")
        log("=== Phase WAIT Tadarida ===")
        r_wait = _capture_stdout(
            lambda: run_phase_wait(session_path, token=token,
                                     poll_interval=60, progress=progress),
            log,
        )
        if r_wait.get("error"):
            return r_wait

        log("")
        log("=== Phase FETCH observations ===")
        r_fetch = _capture_stdout(
            lambda: run_phase_fetch(session_path, token=token, force=False,
                                      progress=progress),
            log,
        )
        return r_fetch

    return worker
