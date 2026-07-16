"""
gui_app.py — point d'entrée de la GUI ChiroTool.

Sprint 1 : squelette + liste sessions + scan.

Usage :
    python gui_app.py

À terme : packagé en .exe via PyInstaller.
"""

from __future__ import annotations

import os
import sys
import threading
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox

# PyInstaller --windowed : sys.stdout peut être None (pas de console).
# On guard pour éviter AttributeError au démarrage du .exe.
if sys.stdout is not None and getattr(sys.stdout, "encoding", None):
    if sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            if sys.stderr is not None:
                sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

try:
    import customtkinter as ctk
except ImportError:
    print("ERREUR : customtkinter n'est pas installé.\n"
          "Fais : python -m pip install customtkinter", file=sys.stderr)
    raise SystemExit(1)

from chiro_core import SessionState, analyze_session, walk_sessions
from credentials import load_token
from gui_config import (
    Settings, config_dir, is_portable, load_settings, remember_workspace,
    save_settings, single_instance_acquire, storage_info,
)
from gui_history import HistoryPanel
from gui_map import MapPanel
from gui_registry import RegistryPanel
from gui_preferences import PreferencesDialog
from gui_runner import RunDialog, run_cleanup, run_prep, run_upload_flow
from gui_validation import ValidationView, find_observations_xlsx
from gui_synthesis import SynthesisView
from gui_wizard import open_wizard


APP_TITLE = "ChiroTool"
try:
    from version import __version__ as APP_VERSION
except Exception:                       # version.py absent (cas improbable)
    APP_VERSION = "?"
MIN_WIDTH = 1100
MIN_HEIGHT = 700


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.0f} PB"


def _session_status_glyph(s: SessionState) -> tuple[str, str]:
    """Retourne (glyph, couleur).

    Glyphs :
      ● vert    : session complète (rename + te10 + analyzed + cleaned)
      ⏳ orange : participation créée côté serveur mais xlsx pas récupéré
                 (Tadarida en cours OU upload interrompu — relancer pour finir)
      ● jaune  : étape intermédiaire en cours
      ● rouge  : brut (rien fait)
    """
    done = sum([s.flag_renamed, s.flag_te10_done, s.flag_analyzed, s.flag_cleaned])
    if done == 4:
        return "●", "#2ea043"          # vert : complet
    if getattr(s, "flag_pending_fetch", False):
        return "⏳", "#e67e22"          # orange : upload incomplet à reprendre
    if done == 0:
        return "●", "#f85149"          # rouge : brut
    return "●", "#d29922"              # jaune : en cours


# ---------------------------------------------------------------------------
# SessionCard : une ligne cliquable dans la liste
# ---------------------------------------------------------------------------

class SessionCard(ctk.CTkFrame):
    def __init__(self, master, state: SessionState, on_click,
                  on_batch_toggle=None):
        super().__init__(master, corner_radius=6, fg_color="transparent",
                         border_width=1, border_color=("gray80", "gray25"))
        self.state = state
        self.on_click = on_click
        self.on_batch_toggle = on_batch_toggle
        self._selected = False
        self._batch_checked = False

        glyph, color = _session_status_glyph(state)

        self.grid_columnconfigure(2, weight=1)

        # Case à cocher pour mode batch (masquée par défaut)
        self._batch_var = ctk.BooleanVar(value=False)
        self.batch_chk = ctk.CTkCheckBox(
            self, text="", variable=self._batch_var,
            width=24, command=self._on_batch_check,
        )
        # pas de grid() : visible seulement en mode batch via show_batch_checkbox

        self.status_lbl = ctk.CTkLabel(self, text=glyph, text_color=color,
                                        font=ctk.CTkFont(size=18, weight="bold"),
                                        width=20)
        self.status_lbl.grid(row=0, column=1, rowspan=2, padx=(8, 4), pady=6)

        self.name_lbl = ctk.CTkLabel(self, text=state.name,
                                      font=ctk.CTkFont(size=13, weight="bold"),
                                      anchor="w", justify="left")
        self.name_lbl.grid(row=0, column=2, sticky="ew", padx=(0, 8))

        flags_parts = []
        if state.flag_renamed: flags_parts.append("renommé")
        if state.flag_te10_done: flags_parts.append("TE×10")
        if state.flag_analyzed: flags_parts.append("analysé")
        if state.flag_cleaned: flags_parts.append("nettoyé")
        if getattr(state, "flag_pending_fetch", False):
            flags_parts.append("⏳ à reprendre")
        flags_s = " · ".join(flags_parts) if flags_parts else "brut"
        size_s = _fmt_size(state.total_bytes)
        meta = f"{state.n_wav} wav · {size_s} · {flags_s}"

        self.meta_lbl = ctk.CTkLabel(self, text=meta,
                                      font=ctk.CTkFont(size=11),
                                      text_color=("gray40", "gray70"),
                                      anchor="w", justify="left")
        self.meta_lbl.grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(0, 4))

        # Bind clic sur toute la carte (sauf checkbox)
        for w in (self, self.status_lbl, self.name_lbl, self.meta_lbl):
            w.bind("<Button-1>", self._on_click)

    def _on_click(self, _event):
        self.on_click(self.state)

    def _on_batch_check(self):
        self._batch_checked = bool(self._batch_var.get())
        if self.on_batch_toggle:
            try:
                self.on_batch_toggle(self.state, self._batch_checked)
            except Exception:
                pass

    def show_batch_checkbox(self, visible: bool):
        """Affiche/masque la case à cocher de sélection batch."""
        if visible:
            self.batch_chk.grid(row=0, column=0, rowspan=2,
                                  padx=(4, 0), pady=6)
        else:
            try:
                self.batch_chk.grid_forget()
            except Exception:
                pass
            # Décoche au passage pour ne pas garder une sélection cachée
            self._batch_var.set(False)
            self._batch_checked = False

    def is_batch_checked(self) -> bool:
        return self._batch_checked

    def set_batch_checked(self, value: bool):
        self._batch_var.set(bool(value))
        self._batch_checked = bool(value)

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self.configure(fg_color=("#d5e7f7", "#1f3a52"))
        else:
            self.configure(fg_color="transparent")


# ---------------------------------------------------------------------------
# MainApp
# ---------------------------------------------------------------------------

class ChiroToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.settings = load_settings()
        # Mode compatible antivirus : reflété dans la variable d'env que
        # rename._av_safe_pace lit au moment du renommage. Additif (on ne retire
        # pas un éventuel CHIROTOOL_AV_SAFE posé par un lanceur externe).
        if getattr(self.settings, "av_safe_mode", False):
            os.environ["CHIROTOOL_AV_SAFE"] = "1"
        ctk.set_appearance_mode(self.settings.appearance)
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        self.geometry(f"{MIN_WIDTH}x{MIN_HEIGHT}")
        self.minsize(900, 600)

        # Icône de fenêtre (barre de titre + taskbar). Cherche icon.ico à côté
        # du script (dev) ou dans le bundle PyInstaller (prod).
        try:
            import sys
            if getattr(sys, "frozen", False):
                icon_path = Path(sys._MEIPASS) / "icon.ico"  # type: ignore[attr-defined]
            else:
                icon_path = Path(__file__).parent / "icon.ico"
            if icon_path.is_file():
                self.iconbitmap(str(icon_path))
        except Exception:
            pass  # icône non critique, on ignore silencieusement

        self.sessions: list[SessionState] = []
        self.session_cards: list[SessionCard] = []
        self.selected_card: SessionCard | None = None

        # Fermeture propre (obligation utilisateur)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._bind_shortcuts()

        # Onboarding au premier lancement : si onboarding_done=False, on
        # affiche le wizard une fois la fenêtre principale dessinée. L'auto-scan
        # du workspace attend la fin du wizard pour démarrer (sinon il y aurait
        # 2 modales superposées sur un poste qui a un registre pré-existant).
        self.after(200, self._maybe_show_onboarding)

        # Vérification de mise à jour NON BLOQUANTE : planifiée après l'affichage
        # de la fenêtre, exécutée dans un thread daemon avec timeout réseau court
        # → aucun impact sur le temps de lancement. Throttle 1×/jour + réglage on/off.
        self.after(3000, self._auto_update_check)

    def _auto_update_check(self):
        """Lance (si activé) une vérification de mise à jour en arrière-plan.

        Garde-fous : réglage ``auto_update_check``, throttle 1×/jour, thread
        daemon avec timeout réseau court. N'interrompt jamais l'UI ; en cas de
        nouvelle version, propose seulement une boîte de dialogue.
        """
        try:
            if not getattr(self.settings, "auto_update_check", True):
                return
            import datetime as _dt
            if getattr(self.settings, "last_update_check", None) == _dt.date.today().isoformat():
                return
        except Exception:
            return

        import threading

        def _worker():
            try:
                from version import (__version__, fetch_latest_release,
                                      is_newer)
                info = fetch_latest_release(timeout=6.0)
                # Mémorise la date du check réussi (throttle) — best effort.
                if info is not None:
                    try:
                        import datetime as _dt
                        from gui_config import save_settings
                        self.settings.last_update_check = _dt.date.today().isoformat()
                        save_settings(self.settings)
                    except Exception:
                        pass
                if not info or not is_newer(info["tag"], __version__):
                    return
                if getattr(self.settings, "update_skip_version", None) == info["tag"]:
                    return
                self.after(0, lambda: self._prompt_auto_update(info))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _prompt_auto_update(self, info: dict):
        """Propose la mise à jour (thread UI). Oui = page de téléchargement,
        Non = plus tard, Annuler = ignorer cette version (ne plus proposer)."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        from version import GITHUB_RELEASES_PAGE, __version__
        tag = info.get("tag") or "?"
        url = info.get("url") or GITHUB_RELEASES_PAGE
        pre = "  (pre-release)" if info.get("prerelease") else ""
        resp = messagebox.askyesnocancel(
            "Mise à jour disponible",
            f"✨ Une nouvelle version de ChiroTool est disponible : {tag}{pre}\n"
            f"(tu utilises la version {__version__}).\n\n"
            f"  • Oui — ouvrir la page de téléchargement\n"
            f"  • Non — plus tard\n"
            f"  • Annuler — ignorer cette version\n",
            parent=self,
        )
        if resp is True:
            import webbrowser
            try:
                webbrowser.open(url)
            except Exception:
                pass
        elif resp is None:   # « Annuler » → ignorer cette version
            try:
                from gui_config import save_settings
                self.settings.update_skip_version = tag
                save_settings(self.settings)
            except Exception:
                pass

    def _maybe_show_onboarding(self):
        """Affiche le wizard d'accueil au 1er lancement. No-op si déjà fait."""
        try:
            from gui_onboarding import OnboardingWizard, should_show_onboarding
        except Exception:
            should_show_onboarding = lambda s: False
            OnboardingWizard = None

        if OnboardingWizard is not None and should_show_onboarding(self.settings):
            OnboardingWizard(
                self, self.settings,
                on_done=self._on_onboarding_done,
            )
            # L'ouverture auto du workspace se fera après la fermeture du wizard
            return

        # Pas d'onboarding → ouverture auto du dernier workspace si présent
        if (self.settings.last_workspace
                and Path(self.settings.last_workspace).is_dir()):
            self._scan_workspace(self.settings.last_workspace)

    def _on_onboarding_done(self, settings):
        """Callback à la fermeture du wizard : on applique les settings.

        Si un workspace a été renseigné dans le wizard, on le scanne
        immédiatement pour que l'utilisateur voie tout de suite l'outil "vivre".
        """
        self.settings = settings
        try:
            self.workspace_var.set(settings.last_workspace or "(aucun)")
        except Exception:
            pass
        if settings.last_workspace and Path(settings.last_workspace).is_dir():
            self.after(100, lambda: self._scan_workspace(settings.last_workspace))

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Barre du haut
        self._build_toolbar().grid(row=0, column=0, columnspan=2, sticky="ew",
                                    padx=10, pady=(10, 4))

        # Sidebar (liste sessions)
        self._build_sidebar().grid(row=1, column=0, sticky="nsew",
                                    padx=(10, 4), pady=(4, 4))

        # Zone détail
        self._build_detail_panel().grid(row=1, column=1, sticky="nsew",
                                         padx=(4, 10), pady=(4, 4))

        # Barre du bas (status)
        self._build_statusbar().grid(row=2, column=0, columnspan=2, sticky="ew",
                                      padx=10, pady=(4, 8))

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid_columnconfigure(2, weight=1)

        title = ctk.CTkLabel(bar, text=f"🦇  {APP_TITLE}",
                              font=ctk.CTkFont(size=18, weight="bold"))
        title.grid(row=0, column=0, padx=(4, 20), sticky="w")

        self.workspace_var = ctk.StringVar(value=self.settings.last_workspace or "(aucun)")
        ws_label = ctk.CTkLabel(bar, text="Dossier :",
                                 font=ctk.CTkFont(size=12))
        ws_label.grid(row=0, column=1, padx=(0, 6), sticky="w")

        self.workspace_entry = ctk.CTkEntry(bar, textvariable=self.workspace_var,
                                              width=500, height=32)
        self.workspace_entry.grid(row=0, column=2, padx=(0, 6), sticky="ew")

        self.browse_btn = ctk.CTkButton(bar, text="Parcourir…", width=100, height=32,
                                    command=self._on_browse)
        self.browse_btn.grid(row=0, column=3, padx=(0, 6))

        self.scan_btn = ctk.CTkButton(bar, text="🔄 Scanner", width=100, height=32,
                                  command=self._on_scan)
        self.scan_btn.grid(row=0, column=4, padx=(0, 6))

        settings_btn = ctk.CTkButton(bar, text="⚙", width=40, height=32,
                                       command=self._on_settings)
        settings_btn.grid(row=0, column=5, padx=0)

        about_btn = ctk.CTkButton(
            bar, text="ℹ", width=40, height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_about,
        )
        about_btn.grid(row=0, column=6, padx=(6, 0))

        return bar

    def _on_about(self):
        """Affiche la fenêtre À propos."""
        try:
            from gui_about import AboutDialog
            AboutDialog(self)
        except Exception as e:
            messagebox.showerror("À propos", f"Erreur ouverture : {e}")

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, corner_radius=8)
        sidebar.grid_rowconfigure(3, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        header_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
        header_row.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(header_row, text="Sessions",
                               font=ctk.CTkFont(size=14, weight="bold"),
                               anchor="w")
        header.grid(row=0, column=0, sticky="w")

        # Toggle "mode batch" : affiche les cases à cocher sur les cards.
        # La sélection est dérivée des cards (pas de set séparé à synchroniser).
        self._batch_mode = False
        self.batch_btn = ctk.CTkButton(
            header_row, text="☐ Batch", width=70, height=24,
            font=ctk.CTkFont(size=10),
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._toggle_batch_mode,
        )
        self.batch_btn.grid(row=0, column=1, sticky="e")

        self.sessions_count_lbl = ctk.CTkLabel(
            sidebar, text="(aucun scan)",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
        )
        self.sessions_count_lbl.grid(row=1, column=0, padx=10, pady=(0, 4), sticky="w")

        # Barre d'actions batch (masquée tant que mode batch off)
        self.batch_actions = ctk.CTkFrame(sidebar, fg_color=("gray92", "gray20"),
                                              corner_radius=6)
        self.batch_actions.grid(row=2, column=0, sticky="ew",
                                  padx=6, pady=(0, 6))
        self.batch_actions.grid_columnconfigure(0, weight=1)
        self.batch_actions.grid_remove()

        self.batch_count_lbl = ctk.CTkLabel(
            self.batch_actions, text="0 sélectionnée(s)",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        )
        self.batch_count_lbl.grid(row=0, column=0, sticky="w",
                                     padx=10, pady=(8, 4))

        btns = ctk.CTkFrame(self.batch_actions, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        ctk.CTkButton(
            btns, text="▶ Préparer", width=82, height=26,
            font=ctk.CTkFont(size=11),
            command=lambda: self._run_batch("prep"),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            btns, text="▶ Upload", width=82, height=26,
            font=ctk.CTkFont(size=11),
            command=lambda: self._run_batch("upload"),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            btns, text="▶ Nettoyer", width=82, height=26,
            font=ctk.CTkFont(size=11),
            command=lambda: self._run_batch("cleanup"),
        ).pack(side="left")

        self.sidebar_scroll = ctk.CTkScrollableFrame(
            sidebar, corner_radius=0, fg_color="transparent",
            width=320,
        )
        self.sidebar_scroll.grid(row=3, column=0, sticky="nsew", padx=6, pady=6)

        return sidebar

    # -- Mode batch ---------------------------------------------------------

    def _toggle_batch_mode(self):
        """Active/désactive l'affichage des cases à cocher sur les cards."""
        self._batch_mode = not self._batch_mode
        if self._batch_mode:
            self.batch_btn.configure(text="☑ Batch ON",
                                       fg_color=("#1f6feb", "#1f6feb"),
                                       text_color="white")
            self.batch_actions.grid()
        else:
            self.batch_btn.configure(text="☐ Batch",
                                       fg_color=("gray85", "gray25"),
                                       text_color=("gray15", "gray90"))
            self.batch_actions.grid_remove()
        # Met à jour l'affichage des cards (décoche tout en sortie de mode)
        for c in self.session_cards:
            c.show_batch_checkbox(self._batch_mode)
        self._update_batch_count()

    def _on_batch_card_toggle(self, state, checked: bool):
        # Source unique de vérité = l'état des cases à cocher des cards.
        # (Avant : un set d'id() qui survivait aux re-scans et donnait un
        # compteur faux après réutilisation mémoire des SessionState par le GC.)
        self._update_batch_count()

    def _update_batch_count(self):
        n = len(self._selected_batch_states())
        self.batch_count_lbl.configure(
            text=f"{n} sélectionnée(s)" if n != 1 else "1 sélectionnée"
        )

    def _selected_batch_states(self) -> list[SessionState]:
        """Retourne la liste des SessionState cochées (ordre sidebar).

        Dérivée directement des cards : pas de cache à invalider, toujours
        cohérent avec ce que l'utilisateur voit coché.
        """
        out: list[SessionState] = []
        for c in self.session_cards:
            try:
                if c.is_batch_checked():
                    out.append(c.state)
            except Exception:
                pass
        return out

    def _run_batch(self, phase: str):
        """Lance un traitement batch sur les sessions cochées.

        ``phase`` : 'prep' / 'upload' / 'cleanup'

        Pour cette v1, on enchaîne en SÉRIE (une session puis la suivante).
        Le mode parallèle multi-sessions est laissé pour v2 — il pose des
        questions de rate-limit serveur et de UX (3 RunDialogs simultanés).
        En série, c'est simple, robuste, et le throughput reste correct grâce
        à l'upload parallèle déjà en place dans la phase upload elle-même.
        """
        sessions = self._selected_batch_states()
        if not sessions:
            messagebox.showinfo(
                "Sélection vide",
                "Coche au moins une session avant de lancer un batch.")
            return
        from tkinter import messagebox as mb
        if not mb.askyesno(
            "Confirmer le batch",
            f"Lancer la phase « {phase} » sur {len(sessions)} session(s) "
            f"en série (l'une après l'autre) ?\n\n"
            f"Les sessions qui ne sont pas prêtes pour cette phase (ou déjà "
            f"faites) seront automatiquement ignorées — le détail apparaît "
            f"dans le journal du modal.\n\n"
            f"Tu pourras suivre la progression dans le modal qui s'ouvre.",
        ):
            return
        self._run_batch_serial(phase, sessions)

    def _run_batch_serial(self, phase: str, sessions: list):
        """Lance le batch en série : une session traitée, puis la suivante."""
        from gui_runner import RunDialog
        title = f"Batch {phase} — {len(sessions)} session(s)"
        # On met le compteur (i/N) dans le titre live, et on chaîne les phases
        # via un worker qui itère sur les sessions.

        # Logger applicatif pour persister l'avancement du batch en cas
        # d'interruption (PC éteint, crash, fermeture forcée). Ainsi à la
        # ré-ouverture on peut diagnostiquer où ça s'est arrêté.
        import logging as _log
        _log.info("=== Batch %s démarré sur %d session(s) ===",
                  phase, len(sessions))
        for s in sessions:
            _log.info("  prévue : %s", s.name)

        def worker(log, progress=None):
            results = []
            total = len(sessions)

            # === Phase 1 : exécution séquentielle de la phase principale ===
            label_phase_1 = "Upload" if phase == "upload" else phase.capitalize()
            log(f"=== Phase 1 : {label_phase_1} (séquentiel) ===")
            for i, s in enumerate(sessions, 1):
                log("")
                log(f"────────  Session {i}/{total} : {s.name}  ────────")
                _log.info("Batch %s : session %d/%d START — %s",
                          phase, i, total, s.name)
                if progress:
                    progress(i - 1, total, f"session {i}/{total}")
                try:
                    r = self._run_phase_for(s, phase, log, progress)
                    results.append({"session": s.name, "session_obj": s,
                                     "result": r})
                    if isinstance(r, dict) and (r.get("error") or r.get("errors")):
                        _log.warning("Batch %s : session %d/%d %s erreur(s) — %s",
                                      phase, i, total, s.name,
                                      r.get("error") or r.get("errors"))
                    else:
                        _log.info("Batch %s : session %d/%d OK — %s",
                                  phase, i, total, s.name)
                except Exception as e:
                    log(f"⚠ Erreur sur {s.name} : {e}")
                    _log.exception("Batch %s : session %d/%d EXCEPTION — %s",
                                    phase, i, total, s.name)
                    results.append({"session": s.name, "session_obj": s,
                                     "error": str(e)})

            # === Phase 2 : wait + fetch en PARALLÈLE (uniquement pour upload) ===
            if phase == "upload":
                pending = [
                    r for r in results
                    if "error" not in r
                    and not (isinstance(r.get("result"), dict)
                             and r["result"].get("error"))
                    and not (isinstance(r.get("result"), dict)
                             and r["result"].get("skipped"))
                ]
                if pending:
                    log("")
                    log(f"=== Phase 2 : Wait Tadarida + Fetch xlsx ({len(pending)} sessions, en parallèle) ===")
                    log("Les analyses tournent en parallèle côté serveur Vigie-Chiro.")
                    log("Chaque nuit terminée → fetch immédiat. Tu peux fermer l'app à tout moment.")
                    log("")
                    self._run_waits_in_parallel(pending, log, progress, _log)

            if progress:
                progress(total, total, "terminé")
            n_ok = sum(1 for r in results
                        if "error" not in r
                        and not (isinstance(r.get("result"), dict)
                                 and r["result"].get("error")))
            n_err = total - n_ok
            log("")
            log(f"=== Bilan : {n_ok}/{total} OK, {n_err} erreur(s) ===")
            _log.info("=== Batch %s terminé : %d OK / %d erreur(s) ===",
                      phase, n_ok, n_err)
            # Strip session_obj qui n'est pas sérialisable proprement
            for r in results:
                r.pop("session_obj", None)
            return {"batch": True, "results": results,
                     "n_ok": n_ok, "n_err": n_err}

        RunDialog(self, title=title, worker=worker)

    def _run_waits_in_parallel(self, pending, log, progress, _log):
        """Pour chaque session dont l'upload est OK, lance wait + fetch en
        parallèle (un thread par session, max 5 simultanés pour ne pas
        marteler l'API). Logs interlacés mais préfixés du nom de session.
        """
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from credentials import load_token
        from pipeline import run_phase_fetch, run_phase_wait

        token = load_token()
        if not token:
            log("⚠ token API absent — wait/fetch impossible")
            return

        # Lock pour interleaver les logs proprement
        log_lock = threading.Lock()

        def _wf(entry):
            s = entry["session_obj"]
            session_path = s.path
            tag = f"[{s.name[:30]}]"

            def _slog(msg):
                with log_lock:
                    log(f"{tag} {msg}")

            try:
                _slog("⏳ wait Tadarida (poll 60s)…")
                r_wait = run_phase_wait(session_path, token=token,
                                          poll_interval=60)
                if r_wait.get("error"):
                    _slog(f"⚠ wait erreur : {r_wait['error']}")
                    entry["wait"] = r_wait
                    return entry
                etat = r_wait.get("final_state", "?")
                _slog(f"✓ wait terminé ({etat})")
                entry["wait"] = r_wait

                _slog("⬇ fetch xlsx observations…")
                r_fetch = run_phase_fetch(session_path, token=token,
                                            force=False)
                if r_fetch.get("error"):
                    _slog(f"⚠ fetch erreur : {r_fetch['error']}")
                else:
                    _slog(f"✓ fetch OK ({r_fetch.get('n_contacts', '?')} contacts)")
                entry["fetch"] = r_fetch
            except Exception as e:
                _slog(f"⚠ exception : {e}")
                entry["error"] = str(e)
            return entry

        max_workers = min(5, len(pending))
        n_done = [0]
        total = len(pending)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_wf, entry): entry for entry in pending}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    log(f"⚠ thread wait/fetch exception : {e}")
                n_done[0] += 1
                if progress:
                    progress(n_done[0], total,
                              f"wait/fetch {n_done[0]}/{total}")

        log("")
        log(f"✓ Phase 2 terminée — {n_done[0]}/{total} sessions finalisées")

    @staticmethod
    def _meta_is_complete(meta) -> bool:
        """Vrai si la meta a tous les champs requis pour le renommage.

        try_auto_meta renvoie une meta PARTIELLE (date + série + contrat) quand
        le carré/point ne sont pas déductibles (cas normal sans Suivi). Dans ce
        cas il FAUT passer par le wizard (simple-clic) ou signaler « à compléter »
        (batch) — surtout pas lancer un renommage qui échouera sur
        « n_site_tadarida manquant ».
        """
        if meta is None:
            return False
        return all([
            meta.date_debut is not None,
            bool(meta.n_site_tadarida),
            bool(meta.n_point_fixe),
            meta.n_passage is not None,
            meta.n_enregistreur is not None,
            bool(meta.n_serie),
        ])

    def _resolve_meta_for_batch(self, s):
        """Résout la meta pour une session dans un contexte batch.

        - Lit le manifest existant en priorité (rapide, déterministe)
        - Fallback : try_auto_meta (heuristiques sur les WAV / Suivi)
        - Pas de wizard interactif (le batch tourne dans un thread)

        Retourne SessionMeta ou None.
        """
        # 1. Manifest
        try:
            from datetime import datetime as _dt
            from manifest import Manifest
            from naming import SessionMeta
            m = Manifest.load(s.path)
            if m and m.meta:
                dt = (_dt.fromisoformat(m.meta["date_debut"])
                      if m.meta.get("date_debut") else None)
                meta = SessionMeta(
                    date_debut=dt,
                    n_site_tadarida=m.meta.get("n_site_tadarida"),
                    n_point_fixe=m.meta.get("n_point_fixe"),
                    n_passage=m.meta.get("n_passage"),
                    n_enregistreur=m.meta.get("n_enregistreur"),
                    n_serie=m.meta.get("n_serie"),
                    nom_contrat=m.meta.get("nom_contrat"),
                )
                # Validation basique : si tous les champs critiques sont là
                if meta.date_debut and meta.n_site_tadarida and meta.n_point_fixe \
                        and meta.n_passage is not None:
                    return meta
        except Exception:
            pass
        # 2. Auto-résolution heuristique — uniquement si elle est COMPLÈTE.
        # Une meta partielle (carré/point manquants) ne peut pas être renommée
        # en batch (pas de wizard dans un thread) → on renvoie None pour que le
        # batch saute proprement la session avec un message explicite.
        try:
            from rename import try_auto_meta
            auto, _msgs = try_auto_meta(s.path)
            if self._meta_is_complete(auto):
                return auto
        except Exception:
            pass
        return None

    def _run_phase_for(self, s, phase: str, log, progress):
        """Exécute une phase pour une session donnée dans un contexte batch.

        Pour phase="upload" : fait SEULEMENT l'upload + trigger_compute (pas
        de wait/fetch — ils sont orchestrés en parallèle après dans
        _run_batch_upload_pipelined).
        """
        from gui_runner import _capture_stdout
        if phase == "prep":
            from pipeline import run_phase_prep
            meta = self._resolve_meta_for_batch(s)
            if meta is None:
                log(f"  ⚠ {s.name} : métadonnées incomplètes (carré/point) — "
                    f"prépare cette nuit en simple-clic pour les saisir, puis "
                    f"relance le batch. Session ignorée.")
                return {"skipped": "métadonnées incomplètes (saisie wizard requise)"}
            return _capture_stdout(
                lambda: run_phase_prep(s.path, meta, dry_run=False,
                                         force=False, progress=progress),
                log,
            )
        if phase == "upload":
            # Upload SEUL (sans wait/fetch). L'orchestration parallèle des
            # wait/fetch après tous les uploads est gérée par
            # _run_batch_upload_pipelined.
            from credentials import load_token
            from pipeline import run_phase_upload
            token = load_token()
            if not token:
                log(f"  ⚠ {s.name} : token API absent, skip")
                return {"skipped": "token absent"}
            meta = self._resolve_meta_for_batch(s)
            if meta is None:
                log(f"  ⚠ {s.name} : meta introuvable, skip")
                return {"skipped": "meta indisponible"}
            return _capture_stdout(
                lambda: run_phase_upload(s.path, meta, dry_run=False,
                                            token=token, progress=progress),
                log,
            )
        if phase == "cleanup":
            from pipeline import run_phase_cleanup
            t = self.settings
            thresholds = {
                "chiros": t.threshold_chiros,
                "orthos": t.threshold_orthos,
                "micromam": t.threshold_micromam,
                "oiseaux": t.threshold_oiseaux,
            }
            return _capture_stdout(
                lambda: run_phase_cleanup(
                    s.path, thresholds, set(),
                    t.silent_policy, t.unknown_action,
                    dry_run=False, force=False, progress=progress),
                log,
            )
        return {"error": f"phase inconnue : {phase}"}

    def _build_detail_panel(self):
        """Panneau droit avec onglets : Vue session / Carte."""
        self.detail_frame = ctk.CTkFrame(self, corner_radius=8)
        self.detail_frame.grid_rowconfigure(0, weight=1)
        self.detail_frame.grid_columnconfigure(0, weight=1)

        self.detail_tabs = ctk.CTkTabview(self.detail_frame, corner_radius=6)
        self.detail_tabs.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.detail_tabs.add("Vue session")
        self.detail_tabs.add("Registre")
        self.detail_tabs.add("Historique")
        self.detail_tabs.add("Carte")
        self.detail_tabs.add("Dashboard")
        self.detail_tabs.add("Activité")

        # Onglet session
        session_tab = self.detail_tabs.tab("Vue session")
        session_tab.grid_columnconfigure(0, weight=1)
        session_tab.grid_rowconfigure(0, weight=1)
        self.session_container = ctk.CTkFrame(session_tab, fg_color="transparent")
        self.session_container.grid(row=0, column=0, sticky="nsew")
        self.session_container.grid_columnconfigure(0, weight=1)
        self.session_container.grid_rowconfigure(0, weight=1)

        # Onglet Registre
        reg_tab = self.detail_tabs.tab("Registre")
        reg_tab.grid_columnconfigure(0, weight=1)
        reg_tab.grid_rowconfigure(0, weight=1)
        self.registry_panel = RegistryPanel(reg_tab, corner_radius=0)
        self.registry_panel.grid(row=0, column=0, sticky="nsew")

        # Onglet Historique
        hist_tab = self.detail_tabs.tab("Historique")
        hist_tab.grid_columnconfigure(0, weight=1)
        hist_tab.grid_rowconfigure(0, weight=1)
        self.history_panel = HistoryPanel(hist_tab, corner_radius=0,
                                            fg_color="transparent")
        self.history_panel.grid(row=0, column=0, sticky="nsew")

        # Onglet carte (lazy-init à la 1ère ouverture)
        map_tab = self.detail_tabs.tab("Carte")
        map_tab.grid_columnconfigure(0, weight=1)
        map_tab.grid_rowconfigure(0, weight=1)
        self.map_panel = MapPanel(map_tab, corner_radius=0)
        self.map_panel.grid(row=0, column=0, sticky="nsew")
        # Permet au popup "fiche récap point" d'ouvrir la session dans le
        # Registre d'un clic (bascule sur l'onglet Registre + filtre dessus).
        try:
            self.map_panel.set_on_open_in_registry(self._open_session_in_registry)
        except Exception:
            pass

        # Onglet dashboard (stats transverses)
        from gui_dashboard import DashboardPanel
        dash_tab = self.detail_tabs.tab("Dashboard")
        dash_tab.grid_columnconfigure(0, weight=1)
        dash_tab.grid_rowconfigure(0, weight=1)
        self.dashboard_panel = DashboardPanel(dash_tab, corner_radius=0)
        self.dashboard_panel.grid(row=0, column=0, sticky="nsew")

        # Onglet activité (graphes par tranche horaire post-validation)
        from gui_activity import ActivityPanel
        act_tab = self.detail_tabs.tab("Activité")
        act_tab.grid_columnconfigure(0, weight=1)
        act_tab.grid_rowconfigure(0, weight=1)
        self.activity_panel = ActivityPanel(act_tab, corner_radius=0)
        self.activity_panel.grid(row=0, column=0, sticky="nsew")

        # Callback quand on bascule d'onglet (pour lazy-load de la carte)
        self.detail_tabs._segmented_button.configure(command=self._on_tab_change)

        self._show_empty_detail()

        return self.detail_frame

    def _open_session_in_registry(self, session: dict) -> None:
        """Bascule sur l'onglet Registre et filtre sur une session précise.

        Appelé par le popup de la carte quand on clique sur une ligne
        d'historique. ``session`` est le dict renvoyé par _get_point_history
        (registre local ou cache API).
        """
        try:
            self.detail_tabs.set("Registre")
            # Filtre sur le n° site + point si dispo
            numero = session.get("n_site_tadarida") or ""
            if numero and hasattr(self.registry_panel, "set_quick_filter"):
                self.registry_panel.set_quick_filter(n_site=numero)
            elif numero and hasattr(self.registry_panel, "search_var"):
                # Fallback : utilise la barre de recherche globale
                try:
                    self.registry_panel.search_var.set(str(numero))
                except Exception:
                    pass
        except Exception:
            pass

    def _on_tab_change(self, tab_name: str):
        # Bascule normale du TabView
        self.detail_tabs.set(tab_name)
        if tab_name == "Carte":
            self.map_panel.load_sites_async()
        elif tab_name == "Historique":
            if self.selected_card:
                self.history_panel.set_session(self.selected_card.state)
        elif tab_name == "Registre":
            # Lazy-init du workspace
            if self.registry_panel.workspace is None:
                path = self.workspace_var.get().strip()
                if path and Path(path).is_dir():
                    self.registry_panel.set_workspace(Path(path))
                    self.registry_panel.auto_import_suivi()

    def _show_empty_detail(self):
        for w in self.session_container.winfo_children():
            w.destroy()
        empty = ctk.CTkFrame(self.session_container, fg_color="transparent")
        empty.grid(row=0, column=0, sticky="nsew")
        empty.grid_columnconfigure(0, weight=1)
        empty.grid_rowconfigure(0, weight=1)
        empty.grid_rowconfigure(2, weight=1)

        msg = ctk.CTkLabel(empty,
                            text="← Sélectionne une session dans la liste",
                            font=ctk.CTkFont(size=14),
                            text_color=("gray50", "gray60"))
        msg.grid(row=1, column=0)

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent", height=24)
        bar.grid_columnconfigure(1, weight=1)

        info = storage_info()
        mode = "portable" if info["portable"] else "installé"
        self.status_left = ctk.CTkLabel(
            bar, text=f"mode {mode} · config : {info['config_dir']}",
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray60"), anchor="w",
        )
        self.status_left.grid(row=0, column=0, padx=4, sticky="w")

        self.status_right = ctk.CTkLabel(
            bar, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray60"), anchor="e",
        )
        self.status_right.grid(row=0, column=2, padx=4, sticky="e")

        return bar

    def _bind_shortcuts(self):
        self.bind("<F5>", lambda e: self._on_scan())
        self.bind("<Control-o>", lambda e: self._on_browse())
        self.bind("<Control-q>", lambda e: self._on_close())
        # Event personnalisé : ouvrir les préférences (p.ex. depuis la vue
        # validation quand ChiroSurf n'est pas configuré)
        self.bind("<<OpenPreferences>>", lambda e: self._on_settings())

    # -- Handlers -----------------------------------------------------------

    def _on_browse(self):
        initial = self.settings.last_workspace or str(Path.home())
        path = filedialog.askdirectory(
            title="Dossier racine à scanner",
            initialdir=initial if Path(initial).is_dir() else None,
        )
        if path:
            self.workspace_var.set(path)
            self._scan_workspace(path)

    def _on_scan(self):
        # Garde anti double-clic : si un scan est déjà en cours, ignore.
        if getattr(self, "_scan_in_progress", False):
            return
        path = self.workspace_var.get().strip()
        if not path or path == "(aucun)":
            self._on_browse()
            return
        if not Path(path).is_dir():
            messagebox.showerror("Dossier introuvable",
                                 f"Le chemin n'est pas un dossier valide :\n{path}")
            return
        self._scan_workspace(path)

    def _on_settings(self):
        """Ouvre la fenêtre Préférences (modale)."""
        PreferencesDialog(self, self.settings, on_apply=self._on_settings_applied)

    def _on_settings_applied(self, new_settings):
        # Le thème peut avoir changé, tout le reste est déjà persisté côté
        # gui_preferences. Rien d'autre à faire pour l'instant.
        self.settings = new_settings

    def _on_close(self):
        try:
            save_settings(self.settings)
        finally:
            self.destroy()

    # -- Scan ---------------------------------------------------------------

    def _scan_workspace(self, path: str):
        """Lance un scan du dossier dans un thread pour ne pas figer l'UI."""
        self._scan_in_progress = True
        # Grise les boutons pendant le scan pour éviter un second thread concurrent
        try:
            self.scan_btn.configure(state="disabled", text="⏳ Scan…")
            self.browse_btn.configure(state="disabled")
        except Exception:
            pass
        self.sessions_count_lbl.configure(text="scan en cours…")
        # Nettoyer TOUT le contenu de la sidebar (cards + headers campagne)
        for w in self.sidebar_scroll.winfo_children():
            w.destroy()
        self.session_cards.clear()
        self.sessions.clear()
        self.selected_card = None
        self._show_empty_detail()

        def _worker():
            try:
                paths = walk_sessions(Path(path))
                # Parallélisation I/O-bound : analyze_session fait plusieurs
                # stat() + wave.open() par session. Sur 200 sessions c'est
                # dominant. ThreadPool réduit le temps de scan typiquement ×4-8
                # sur SSD. Chaque appel est indépendant, pas de lock à gérer.
                if len(paths) >= 4:
                    from concurrent.futures import ThreadPoolExecutor
                    max_workers = min(8, len(paths))
                    with ThreadPoolExecutor(max_workers=max_workers) as ex:
                        states = list(ex.map(analyze_session, paths))
                else:
                    states = [analyze_session(p) for p in paths]
            except Exception:
                err = traceback.format_exc()
                def _on_err():
                    self._scan_in_progress = False
                    try:
                        self.scan_btn.configure(state="normal", text="🔄 Scanner")
                        self.browse_btn.configure(state="normal")
                    except Exception:
                        pass
                    messagebox.showerror("Erreur scan",
                                          f"Échec du scan :\n\n{err[:500]}")
                self.after(0, _on_err)
                return
            # Retour au thread UI
            self.after(0, lambda: self._on_scan_done(path, states))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_scan_done(self, path: str, states: list[SessionState]):
        self.sessions = states
        remember_workspace(path, self.settings)
        save_settings(self.settings)

        # Auto-détection d'un parc matériel dans le workspace
        # (typique d'un dossier partagé d'équipe). Voir _autodetect_materiels.
        try:
            self._autodetect_materiels(Path(path))
        except Exception:
            pass

        # Alimenter le registre SQLite
        try:
            self.registry_panel.set_workspace(Path(path))
            self.registry_panel.feed_from_scan(states)
            # Partager la Registry avec la carte pour colorer les markers
            # selon l'état réel (done/in_progress/idle) des sites.
            try:
                self.map_panel.set_registry(self.registry_panel.registry)
            except Exception:
                pass
            # Idem pour le dashboard (stats transverses)
            try:
                self.dashboard_panel.set_registry(self.registry_panel.registry)
            except Exception:
                pass
            # Activité = scan workspace pour les xlsx d'observations
            try:
                self.activity_panel.set_workspace(Path(path))
            except Exception:
                pass
        except Exception:
            pass  # registre non critique si ça plante

        # Nettoyer toute la sidebar avant de re-remplir
        for w in self.sidebar_scroll.winfo_children():
            w.destroy()
        self.session_cards.clear()

        # Groupement par campagne
        by_campaign: dict[str, list[SessionState]] = {}
        for s in states:
            by_campaign.setdefault(s.campaign, []).append(s)

        # Affichage
        for campaign in sorted(by_campaign):
            header = ctk.CTkLabel(
                self.sidebar_scroll, text=campaign.upper(),
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray40", "gray60"), anchor="w",
            )
            header.pack(fill="x", padx=4, pady=(8, 2))
            for s in by_campaign[campaign]:
                card = SessionCard(
                    self.sidebar_scroll, s, self._on_card_click,
                    on_batch_toggle=self._on_batch_card_toggle,
                )
                # Si on était en mode batch avant le rescan, on ré-affiche
                if getattr(self, "_batch_mode", False):
                    card.show_batch_checkbox(True)
                card.pack(fill="x", padx=2, pady=2)
                self.session_cards.append(card)

        self.sessions_count_lbl.configure(
            text=f"{len(states)} session(s) · {len(by_campaign)} campagne(s)"
        )
        self.status_left.configure(
            text=f"scanné : {path}  ·  {len(states)} session(s)"
        )

        # Dé-griser les boutons et autoriser de nouveaux scans
        self._scan_in_progress = False
        try:
            self.scan_btn.configure(state="normal", text="🔄 Scanner")
            self.browse_btn.configure(state="normal")
        except Exception:
            pass

    def _on_card_click(self, state: SessionState):
        # Déselectionner l'ancienne carte
        if self.selected_card:
            self.selected_card.set_selected(False)
        # Trouver la carte correspondante
        for c in self.session_cards:
            if c.state is state:
                c.set_selected(True)
                self.selected_card = c
                break
        self._show_session_detail(state)
        # Mettre à jour la timeline d'historique en arrière-plan
        try:
            self.history_panel.set_session(state)
        except Exception:
            pass
        # Carte : pas de focus auto (préserve la vue utilisateur). L'utilisateur
        # clique "📍 Voir sur la carte" depuis le panneau détail s'il veut.

    # -- Detail panel -------------------------------------------------------

    def _show_session_detail(self, s: SessionState):
        for w in self.session_container.winfo_children():
            w.destroy()

        self.session_container.grid_rowconfigure(2, weight=1)
        self.session_container.grid_columnconfigure(0, weight=1)

        # Titre (marges réduites pour éviter le gros espace gris)
        title = ctk.CTkLabel(
            self.session_container, text=s.name,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="ew", padx=12, pady=(4, 0))

        subtitle = ctk.CTkLabel(
            self.session_container,
            text=f"Campagne : {s.campaign}   ·   {s.n_wav} WAV   ·   "
                 f"{_fmt_size(s.total_bytes)}",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
            anchor="w",
        )
        subtitle.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

        # Zone info scrollable
        info = ctk.CTkScrollableFrame(self.session_container, fg_color="transparent")
        info.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 2))
        info.grid_columnconfigure(0, weight=1)

        # Bloc étapes pipeline
        steps_frame = ctk.CTkFrame(info, fg_color=("gray92", "gray20"),
                                    corner_radius=8, border_width=1,
                                    border_color=("gray80", "gray25"))
        steps_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        steps_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(steps_frame, text="Progression pipeline",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      anchor="w").grid(row=0, column=0, sticky="ew",
                                        padx=12, pady=(10, 6))

        steps = [
            ("Renommage Vigie-Chiro", s.flag_renamed),
            ("TE×10 (Kaleidoscope-like)", s.flag_te10_done),
            ("Upload + Tadarida", s.flag_analyzed),
            ("Nettoyage (cleanup)", s.flag_cleaned),
        ]
        for i, (label, done) in enumerate(steps):
            glyph = "✓" if done else "◯"
            color = "#2ea043" if done else "#8b949e"
            row = ctk.CTkFrame(steps_frame, fg_color="transparent")
            row.grid(row=i+1, column=0, sticky="ew", padx=12, pady=2)
            ctk.CTkLabel(row, text=glyph, text_color=color, width=20,
                          font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
            ctk.CTkLabel(row, text=label,
                          font=ctk.CTkFont(size=12),
                          anchor="w").pack(side="left", padx=(4, 0))
        # Espace bas
        ctk.CTkLabel(steps_frame, text="").grid(row=len(steps)+1, column=0, pady=2)

        # Bloc infos détaillées
        meta_frame = ctk.CTkFrame(info, fg_color=("gray92", "gray20"),
                                   corner_radius=8, border_width=1,
                                   border_color=("gray80", "gray25"))
        meta_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        meta_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(meta_frame, text="Détection",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      anchor="w").grid(row=0, column=0, columnspan=2,
                                        sticky="ew", padx=12, pady=(10, 6))

        rows = [
            ("Chemin", str(s.path)),
            ("Noms WAV", self._naming_summary(s)),
            ("Sample rates échantillonnés",
             ", ".join(f"{sr/1000:.1f} kHz" for sr in s.sr_samples) or "—"),
            ("Time-expanded ?",
             "oui (TE probable)" if s.looks_time_expanded else
             "non (brut)" if s.looks_time_expanded is False else "indéterminé"),
            ("Data_k/ miroir", "oui" if s.has_data_k_mirror else "non"),
            ("Summary.txt", "présent" if s.has_summary_txt else "absent"),
            ("Observations xlsx",
             ", ".join(p.name for p in s.observations_paths) or "absent"),
            ("Stats pré-cleanup", "présent" if s.has_stats_snapshot else "absent"),
        ]
        if s.summary:
            sm = s.summary
            dt_s = ""
            if sm.start_dt and sm.end_dt:
                dt_s = f"{sm.start_dt:%Y-%m-%d %H:%M} → {sm.end_dt:%H:%M}"
            extra = []
            if dt_s: extra.append(dt_s)
            if sm.temp_start is not None:
                extra.append(f"T {sm.temp_start:.0f}→{sm.temp_end:.0f}°C")
            if sm.lat:
                extra.append(f"GPS {sm.lat:.4f},{sm.lon:.4f}")
            rows.append(("Summary details", "  ·  ".join(extra) or "—"))

        for i, (k, v) in enumerate(rows):
            ctk.CTkLabel(meta_frame, text=k,
                          font=ctk.CTkFont(size=11, weight="bold"),
                          text_color=("gray30", "gray75"),
                          anchor="nw", width=160).grid(
                row=i+1, column=0, sticky="nw", padx=(12, 4), pady=2)
            ctk.CTkLabel(meta_frame, text=str(v),
                          font=ctk.CTkFont(size=11),
                          anchor="nw", justify="left",
                          wraplength=600).grid(
                row=i+1, column=1, sticky="ew", padx=(4, 12), pady=2)
        ctk.CTkLabel(meta_frame, text="").grid(
            row=len(rows)+1, column=0, columnspan=2, pady=4)

        # Barre d'actions : 3 étapes du pipeline en boutons séparés, chacun
        # activable individuellement. Le "prochain logique" selon l'état est
        # mis en évidence visuellement (bleu + gras) ; les autres restent
        # accessibles (gris + visibles) mais non-proéminents. Au clic sur une
        # étape normalement pas atteinte (ex: Nettoyer sur une session pas
        # encore analysée), l'action est tentée et remonte proprement l'erreur.
        actions = ctk.CTkFrame(self.session_container, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=8, pady=(2, 8))

        next_step = self._next_step_name(s)  # "prep" | "upload" | "cleanup" | "done"

        # Atteignabilité d'une étape : une étape n'a de sens que si la
        # précédente est faite. On grise les étapes prématurées (un clic
        # "Nettoyer" sur une session brute n'aurait rien à nettoyer et
        # afficherait une erreur déroutante pour un non-tech). Les étapes
        # déjà faites restent cliquables (re-run possible).
        can_upload = bool(s.flag_renamed and s.flag_te10_done)
        can_cleanup = bool(s.flag_analyzed)

        def _mk_btn(label: str, cmd, is_primary: bool, enabled: bool = True):
            state = "normal" if enabled else "disabled"
            if is_primary and enabled:
                return ctk.CTkButton(
                    actions, text=label, height=36,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    state=state, command=cmd,
                )
            return ctk.CTkButton(
                actions, text=label, height=36,
                fg_color=("gray85", "gray25"),
                text_color=("gray15", "gray90"),
                hover_color=("gray75", "gray35"),
                state=state, command=cmd,
            )

        prep_btn = _mk_btn(
            "▶  Préparer (rename + TE×10)",
            lambda: self._run_prep(s),
            is_primary=(next_step == "prep"),
        )
        prep_btn.pack(side="left", padx=(0, 6))

        upload_btn = _mk_btn(
            "▶  Upload + Tadarida",
            lambda: self._run_upload(s),
            is_primary=(next_step == "upload"),
            enabled=can_upload,
        )
        upload_btn.pack(side="left", padx=(0, 6))

        cleanup_btn = _mk_btn(
            "▶  Nettoyer (seuils)",
            lambda: self._run_cleanup(s),
            is_primary=(next_step == "cleanup"),
            enabled=can_cleanup,
        )
        cleanup_btn.pack(side="left", padx=(0, 10))

        edit_btn = ctk.CTkButton(
            actions, text="Modifier métadonnées…", height=36, width=180,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            border_width=0,
            command=lambda: self._edit_meta(s),
        )
        edit_btn.pack(side="left", padx=(0, 6))

        map_btn = ctk.CTkButton(
            actions, text="📍 Voir sur la carte", height=36, width=160,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            border_width=0,
            command=lambda: self._view_on_map(s),
        )
        map_btn.pack(side="left", padx=(0, 6))

        # "Valider la nuit" / "Synthèse" : visibles si xlsx observations présent
        if find_observations_xlsx(s.path) is not None:
            validate_btn = ctk.CTkButton(
                actions, text="🔍 Valider la nuit…", height=36, width=160,
                fg_color="#1f6feb",
                hover_color="#1158c7",
                command=lambda: self._open_validation_view(s),
            )
            validate_btn.pack(side="left", padx=(0, 6))

            synth_btn = ctk.CTkButton(
                actions, text="📊 Synthèse", height=36, width=110,
                fg_color=("gray85", "gray25"),
                text_color=("gray15", "gray90"),
                hover_color=("gray75", "gray35"),
                command=lambda: self._open_synthesis_view(s),
            )
            synth_btn.pack(side="left", padx=(0, 6))

        details_btn = ctk.CTkButton(
            actions, text="Détails avancés…", height=36, width=140,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            border_width=0,
            command=lambda: self._show_advanced(s),
        )
        details_btn.pack(side="left")

    def _naming_summary(self, s: SessionState) -> str:
        parts = []
        if s.n_wav_vigiechiro:
            parts.append(f"{s.n_wav_vigiechiro} Vigie-Chiro")
        if s.n_wav_raw:
            parts.append(f"{s.n_wav_raw} bruts")
        if s.n_wav_unknown:
            parts.append(f"{s.n_wav_unknown} inconnus")
        return "  ·  ".join(parts) if parts else "—"

    def _next_step_name(self, s: SessionState) -> str:
        """Retourne le nom de la prochaine étape logique : prep / upload / cleanup / done.

        Utilisé par la barre d'actions pour mettre en évidence l'étape "next"
        tout en gardant les 3 boutons visibles.
        """
        if not s.flag_renamed or not s.flag_te10_done:
            return "prep"
        if not s.flag_analyzed:
            return "upload"
        if not s.flag_cleaned:
            return "cleanup"
        return "done"

    # -- Résolution meta ----------------------------------------------------

    def _resolve_meta_interactive(self, s: SessionState):
        """Résout la meta via auto-résolution.

        Stratégie :
          1. Si un manifest existe avec meta complète → on la prend directement.
          2. Sinon try_auto_meta → si OK on demande confirmation.
          3. Sinon ouverture du wizard (avec pré-remplissage partiel).
        """
        # 1. Manifest déjà présent
        from manifest import Manifest
        m = Manifest.load(s.path)
        if m and m.meta and all(k in m.meta for k in
                                 ("n_site_tadarida", "n_point_fixe",
                                  "n_passage", "n_enregistreur",
                                  "n_serie", "date_debut")):
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(m.meta["date_debut"])
                from naming import SessionMeta
                return SessionMeta(
                    date_debut=dt,
                    n_site_tadarida=m.meta["n_site_tadarida"],
                    n_point_fixe=m.meta["n_point_fixe"],
                    n_passage=int(m.meta["n_passage"]),
                    n_enregistreur=int(m.meta["n_enregistreur"]),
                    n_serie=m.meta["n_serie"],
                    nom_contrat=m.meta.get("nom_contrat"),
                )
            except (TypeError, ValueError):
                pass

        # 2. Auto-résolution — on ne court-circuite le wizard QUE si la meta est
        # complète. Sinon (carré/point non déductibles, fréquent sans Suivi) on
        # conserve la meta partielle pour pré-remplir le wizard à l'étape 3.
        from rename import try_auto_meta
        auto_meta, msgs = try_auto_meta(s.path)
        if self._meta_is_complete(auto_meta):
            return auto_meta

        # 3. Échec auto → proposer le wizard
        reasons = "\n  · ".join(msgs) if msgs else "(pas de détails)"
        if not messagebox.askyesno(
            "Métadonnées à compléter",
            f"Impossible de résoudre automatiquement les métadonnées.\n\n"
            f"Raisons :\n  · {reasons}\n\n"
            f"Ouvrir le formulaire de saisie manuelle ?"):
            return None

        # Pré-remplissage : on part de la meta partielle déjà résolue (série,
        # date, contrat) puis on complète au besoin depuis les noms de WAV.
        from naming import SessionMeta, extract_serial_from_name, extract_timestamp_from_name
        prefill = auto_meta if auto_meta is not None else SessionMeta()
        # Série dominante
        serials = {}
        dts = []
        try:
            from chiro_core import _find_raw_wav_subdir
            wav_dir = s.path if any(p.suffix.lower() == ".wav" for p in s.path.iterdir() if p.is_file()) else _find_raw_wav_subdir(s.path)
            if wav_dir:
                for p in wav_dir.iterdir():
                    if p.suffix.lower() != ".wav":
                        continue
                    ser = extract_serial_from_name(p.name)
                    if ser:
                        serials[ser] = serials.get(ser, 0) + 1
                    ti = extract_timestamp_from_name(p.name)
                    if ti:
                        dts.append(ti[0])
        except Exception:
            pass
        if serials:
            prefill.n_serie = max(serials, key=serials.get)
        if dts:
            prefill.date_debut = min(dts)

        return open_wizard(self, prefill=prefill, session_name=s.name)

    # -- Actions réelles ----------------------------------------------------

    def _run_prep(self, s: SessionState):
        meta = self._resolve_meta_interactive(s)
        if meta is None:
            return
        # Confirmation
        if not messagebox.askyesno(
            "Confirmer la préparation",
            f"Session : {s.name}\n"
            f"Meta : site {meta.n_site_tadarida} / {meta.n_point_fixe} / "
            f"Pass{meta.n_passage} / enr#{meta.n_enregistreur} ({meta.n_serie})\n\n"
            f"Actions :\n"
            f"  • renommage du dossier au format canonique\n"
            f"  • renommage des {s.n_wav} WAV au format Vigie-Chiro\n"
            f"  • génération du dossier Data_k/ (TE×10)\n"
            f"  • mise à jour du registre\n\n"
            f"Continuer ?"):
            return
        worker = run_prep(s.path, meta, dry_run=False, force=False)
        RunDialog(self, title=f"Préparation — {s.name}",
                  worker=worker, on_done=self._after_phase_done)

    def _run_upload(self, s: SessionState):
        token = load_token()
        if not token:
            if messagebox.askyesno(
                "Token Vigie-Chiro manquant",
                "Aucun token API enregistré.\n"
                "Ouvrir les préférences pour en ajouter un ?"):
                self._on_settings()
            return
        meta = self._resolve_meta_interactive(s)
        if meta is None:
            return

        # Si la participation a déjà été créée (visible dans le manifest),
        # on skip le wizard et on continue l'upload sur celle-ci.
        from manifest import Manifest
        m = Manifest.load(s.path)
        existing_participation_id = (m.meta or {}).get("vigiechiro_participation_id") if m else None

        participation_payload = None
        if not existing_participation_id:
            # Nouveau : ouvrir le wizard pour collecter météo + matos + commentaire
            from gui_participation_wizard import open_participation_wizard
            participation_payload = open_participation_wizard(
                self, session_path=s.path, meta=meta)
            if participation_payload is None:
                return  # utilisateur a annulé

        if not messagebox.askyesno(
            "Confirmer l'upload",
            f"Session : {s.name}\n"
            f"Cette action va :\n"
            f"  • {'réutiliser la participation existante' if existing_participation_id else 'créer une nouvelle participation avec les métadonnées saisies'}\n"
            f"  • uploader tous les WAV du dossier Data_k/\n"
            f"  • lancer le traitement Tadarida\n"
            f"  • attendre la fin (jusqu'à 3h) puis télécharger le xlsx\n\n"
            f"Cela peut prendre plusieurs minutes à plusieurs heures.\n"
            f"Continuer ?"):
            return
        worker = run_upload_flow(s.path, meta, token, dry_run=False,
                                   participation_payload=participation_payload)
        RunDialog(self, title=f"Upload + Tadarida — {s.name}",
                  worker=worker, on_done=self._after_phase_done)

    def _run_cleanup(self, s: SessionState):
        meta = self._resolve_meta_interactive(s)
        if meta is None:
            return
        t = self.settings
        if not messagebox.askyesno(
            "Confirmer le nettoyage",
            f"Session : {s.name}\n\n"
            f"Seuils utilisés :\n"
            f"  • chiroptères  ≥ {t.threshold_chiros:.2f}\n"
            f"  • orthoptères  ≥ {t.threshold_orthos:.2f}\n"
            f"  • micro-mam.   ≥ {t.threshold_micromam:.2f}\n"
            f"  • oiseaux      ≥ {t.threshold_oiseaux:.2f}\n"
            f"  • silencieux   : {t.silent_policy}\n"
            f"  • taxon inconnu: {t.unknown_action}\n\n"
            f"Les seuils sont modifiables dans Préférences.\n"
            f"Les WAV supprimés sont identifiés dans le xlsx _cleanup.\n\n"
            f"Continuer ?"):
            return
        worker = run_cleanup(s.path, meta, self.settings,
                             dry_run=False, force=False)
        # On capture la session path pour pouvoir ouvrir le récap après
        def _on_cleanup_done(result, session_path=s.path):
            self._after_phase_done(result)
            # Si le cleanup a effectivement écrit ses stats, montre le récap
            from pathlib import Path as _P
            if (_P(session_path) / "_stats_before_cleanup.json").is_file() \
                    and not (result.get("errors") or result.get("error")):
                try:
                    from gui_cleanup_recap import CleanupRecapDialog
                    self.after(300, lambda: CleanupRecapDialog(self, session_path))
                except Exception:
                    pass

        RunDialog(self, title=f"Nettoyage — {s.name}",
                  worker=worker, on_done=_on_cleanup_done)

    def _after_phase_done(self, result: dict):
        """Callback appelé après la fin d'une phase : on rafraîchit la liste."""
        # Re-scan du workspace pour refléter les nouveaux états
        path = self.workspace_var.get().strip()
        if path and Path(path).is_dir():
            self.after(200, lambda: self._scan_workspace(path))

    def _open_validation_view(self, s: SessionState):
        """Ouvre la fenêtre de validation de la nuit."""
        xlsx = find_observations_xlsx(s.path)
        if xlsx is None:
            messagebox.showwarning(
                "Pas d'observations",
                "Aucun fichier participation-*-observations*.xlsx trouvé "
                "dans ce dossier.\n\nLance d'abord l'upload + Tadarida."
            )
            return
        initiales = self._guess_initiales()
        ValidationView(
            self, session_path=s.path, xlsx_path=xlsx,
            chirosurf_path=self.settings.chirosurf_path,
            initiales=initiales,
        )

    def _open_synthesis_view(self, s: SessionState):
        """Ouvre la fenêtre de synthèse (contacts par espèce) de la nuit."""
        xlsx = find_observations_xlsx(s.path)
        if xlsx is None:
            messagebox.showwarning(
                "Pas d'observations",
                "Aucun tableur d'observations trouvé dans ce dossier.\n\n"
                "Lance d'abord l'upload + Tadarida."
            )
            return
        SynthesisView(self, session_path=s.path, xlsx_path=xlsx)

    def _guess_initiales(self) -> str:
        """Essaie de déduire les initiales de l'utilisateur (2-3 lettres majuscules)."""
        # Depuis l'API si token → pseudo
        try:
            token = load_token()
            if token:
                from vigiechiro_api import VigieChiroClient
                client = VigieChiroClient(token)
                me = client.me()
                pseudo = me.get("pseudo") or ""
                parts = [p for p in pseudo.split() if p]
                if len(parts) >= 2:
                    return (parts[0][0] + parts[-1][0]).upper()
                if parts:
                    return parts[0][:2].upper()
        except Exception:
            pass
        # Fallback : nom d'utilisateur Windows
        try:
            u = os.environ.get("USERNAME") or os.environ.get("USER") or ""
            if u:
                return u[:2].upper()
        except Exception:
            pass
        # Dernier recours : initiales neutres. Surtout PAS des initiales
        # codées en dur d'une personne : en diffusion publique, cela
        # attribuerait les validations d'un autre observateur à quelqu'un
        # d'autre (le suffixe se retrouve dans le nom du xlsx validé).
        return "XX"

    def _view_on_map(self, s: SessionState):
        """Bascule sur l'onglet Carte et centre sur la session."""
        self.detail_tabs.set("Carte")
        self.map_panel.load_sites_async()
        # Petit délai pour laisser le chargement se faire si c'est la 1ère fois
        self.after(300, lambda: self.map_panel.focus_on_session(s, force=True))

    def _edit_meta(self, s: SessionState):
        """Ouvre le wizard pour éditer les metadata d'une session.
        Persiste dans le manifest si validé."""
        prefill = None
        from manifest import Manifest
        m = Manifest.load(s.path)
        if m and m.meta:
            try:
                from datetime import datetime as _dt
                from naming import SessionMeta
                dt = _dt.fromisoformat(m.meta["date_debut"]) if m.meta.get("date_debut") else None
                prefill = SessionMeta(
                    date_debut=dt,
                    n_site_tadarida=m.meta.get("n_site_tadarida"),
                    n_point_fixe=m.meta.get("n_point_fixe"),
                    n_passage=m.meta.get("n_passage"),
                    n_enregistreur=m.meta.get("n_enregistreur"),
                    n_serie=m.meta.get("n_serie"),
                    nom_contrat=m.meta.get("nom_contrat"),
                )
            except (TypeError, ValueError):
                prefill = None
        if prefill is None:
            try:
                from rename import try_auto_meta
                auto, _msgs = try_auto_meta(s.path)
                prefill = auto
            except Exception:
                prefill = None

        meta = open_wizard(self, prefill=prefill, session_name=s.name)
        if meta is None:
            return
        m = Manifest.load_or_create(s.path)
        m.set_meta(
            nom_contrat=meta.nom_contrat,
            date_debut=meta.date_debut.isoformat() if meta.date_debut else None,
            n_site_tadarida=meta.n_site_tadarida,
            n_point_fixe=meta.n_point_fixe,
            n_passage=meta.n_passage,
            n_enregistreur=meta.n_enregistreur,
            n_serie=meta.n_serie,
        )
        m.save(s.path)
        # Mémorise le contrat saisi pour l'autocomplétion future (LRU, 50 max)
        self._remember_contract(meta.nom_contrat)
        messagebox.showinfo(
            "Métadonnées enregistrées",
            f"Session : {s.name}\n\nLes métadonnées seront utilisées pour "
            f"les prochaines actions (préparation, upload, nettoyage)."
        )

    def _autodetect_materiels(self, workspace: Path) -> None:
        """Détecte un parc matériel à importer dans le workspace.

        Usage type "équipe partagée" : un BE pose son parc dans le dossier
        commun (E:\\Chiros-2026\\materiels.json), ChiroTool propose à chaque
        membre de l'importer la première fois qu'il scanne ce workspace.

        Logique :
          - Cherche un fichier JSON qui ressemble à un parc :
            ``materiels.json`` ou ``chirotool_materiels_*.json`` dans le
            workspace ou dans un sous-dossier de niveau 1.
          - Ne propose pas plus d'une fois pour le même fichier (mémorisé
            dans ``settings.materiels_seen_files``).
          - Propose : Importer (fusion) / Ignorer / Toujours ignorer ce fichier
        """
        from materiels import Materiel as _M
        from materiels import load_materiels as _load_mats
        from materiels import save_materiels as _save_mats
        import json as _json

        # Candidats : racine + 1 niveau de sous-dossier (pour ne pas scanner
        # toute l'arborescence)
        candidates: list[Path] = []
        for pattern in ("materiels.json", "chirotool_materiels_*.json"):
            candidates.extend(workspace.glob(pattern))
            candidates.extend(workspace.glob(f"*/{pattern}"))
        if not candidates:
            return

        seen = set(getattr(self.settings, "materiels_seen_files", None) or [])
        for path in candidates:
            key = str(path.resolve())
            if key in seen:
                continue

            # Parse + dédup avec parc local
            try:
                data = _json.loads(path.read_text(encoding="utf-8"))
                items = data.get("materiels") or []
            except Exception:
                continue
            if not items:
                continue

            local_ms = _load_mats()
            new_ms: list[_M] = []
            known = {f for f in _M.__dataclass_fields__}
            for raw in items:
                if not isinstance(raw, dict) or "id" not in raw:
                    continue
                try:
                    clean = {k: v for k, v in raw.items() if k in known}
                    clean["id"] = int(clean["id"])
                    new_ms.append(_M(**clean))
                except Exception:
                    continue
            if not new_ms:
                continue

            existing_ids = {m.id for m in local_ms}
            new_only = [m for m in new_ms if m.id not in existing_ids]
            already_present = len(new_ms) - len(new_only)

            # Si tous les IDs sont déjà connus : on mémorise pour ne plus
            # demander, sans intervention utilisateur.
            if not new_only:
                seen.add(key)
                self.settings.materiels_seen_files = sorted(seen)[-30:]
                save_settings(self.settings)
                continue

            # Demande utilisateur
            msg = (
                f"Un parc matériel a été trouvé dans le workspace :\n"
                f"   {path.name}\n\n"
                f"Contient {len(new_ms)} matériel(s) ({len(new_only)} nouveau(x), "
                f"{already_present} déjà connu(s)).\n\n"
                "L'importer dans ton parc local ?\n"
                "(les IDs déjà présents chez toi seront conservés)"
            )
            ok = messagebox.askyesno("Parc matériel détecté", msg, parent=self)
            seen.add(key)  # mémorise dans tous les cas
            self.settings.materiels_seen_files = sorted(seen)[-30:]
            save_settings(self.settings)
            if not ok:
                continue
            # Fusion : on ajoute uniquement les IDs absents
            merged = list(local_ms) + new_only
            merged.sort(key=lambda m: m.id)
            try:
                _save_mats(merged)
                messagebox.showinfo(
                    "Parc importé",
                    f"✓ {len(new_only)} matériel(s) ajouté(s) à ton parc.\n"
                    f"Total : {len(merged)} matériels.",
                    parent=self,
                )
            except Exception as e:
                messagebox.showerror("Erreur import", str(e), parent=self)

    def _remember_contract(self, name: str | None) -> None:
        """Ajoute le contrat à la liste des récents (LRU 50). Persiste."""
        if not name:
            return
        n = str(name).strip()
        if not n:
            return
        recents = list(self.settings.recent_contracts or [])
        if n in recents:
            recents.remove(n)
        recents.insert(0, n)
        self.settings.recent_contracts = recents[:50]
        try:
            save_settings(self.settings)
        except Exception:
            pass

    def _show_advanced(self, s: SessionState):
        """Popup détails techniques : flags, chemins, stats, manifest.

        Version CTkToplevel stylée (avant : messagebox natif illisible).
        """
        dlg = ctk.CTkToplevel(self)
        dlg.title("Détails avancés")
        dlg.geometry("640x520")
        dlg.minsize(520, 400)
        dlg.transient(self)
        dlg.after(50, dlg.grab_set)

        dlg.grid_columnconfigure(0, weight=1)
        dlg.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=16, pady=(14, 6))
        body.grid_columnconfigure(1, weight=1)

        row = 0

        def _section(title: str):
            nonlocal row
            ctk.CTkLabel(
                body, text=title,
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w",
            ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(10, 4))
            row += 1

        def _kv(key: str, value: str, mono: bool = False):
            nonlocal row
            ctk.CTkLabel(
                body, text=key, width=140, anchor="w",
                text_color=("gray40", "gray60"),
                font=ctk.CTkFont(size=11),
            ).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            font = ctk.CTkFont(family="Consolas", size=11) if mono \
                else ctk.CTkFont(size=11)
            lbl = ctk.CTkLabel(
                body, text=value, anchor="w", justify="left",
                wraplength=440, font=font,
            )
            lbl.grid(row=row, column=1, sticky="w", pady=2)
            row += 1

        _section("Session")
        _kv("Nom", s.name)
        _kv("Campagne", s.campaign or "—")
        _kv("Chemin", str(s.path), mono=True)

        _section("Flags")
        _kv("renamed", "✓ oui" if s.flag_renamed else "— non")
        _kv("TE×10 fait", "✓ oui" if s.flag_te10_done else "— non")
        _kv("analysé (xlsx)", "✓ oui" if s.flag_analyzed else "— non")
        _kv("nettoyé", "✓ oui" if s.flag_cleaned else "— non")

        _section("Volumétrie")
        _kv("Nb WAV", f"{s.n_wav:,}".replace(",", " "))
        if s.total_bytes:
            mb = s.total_bytes / (1024 * 1024)
            gb = s.total_bytes / (1024 ** 3)
            _kv("Taille totale", f"{gb:.2f} GB  ({mb:.0f} MB)")
        else:
            _kv("Taille totale", "—")

        # Manifest complet si dispo
        try:
            from manifest import Manifest
            m = Manifest.load(s.path)
            if m:
                _section("Manifest")
                _kv("Schema version", str(m.schema_version or "?"))
                _kv("Canonical name", m.canonical_name or "—", mono=True)
                _kv("N° actions", str(len(m.actions or [])))
                if m.meta:
                    meta = m.meta
                    if meta.get("nom_contrat"):
                        _kv("Contrat", str(meta["nom_contrat"]))
                    if meta.get("vigiechiro_participation_id"):
                        _kv("Participation ID",
                             str(meta["vigiechiro_participation_id"]), mono=True)
                    if meta.get("vigiechiro_site_id"):
                        _kv("Site ID", str(meta["vigiechiro_site_id"]), mono=True)
        except Exception:
            pass

        # Footer : copier chemin + fermer
        footer = ctk.CTkFrame(dlg, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        footer.grid_columnconfigure(0, weight=1)

        def _copy_path():
            try:
                dlg.clipboard_clear()
                dlg.clipboard_append(str(s.path))
                dlg.update()
                copy_btn.configure(text="✓ copié")
                dlg.after(1500, lambda: copy_btn.configure(text="📋 Copier le chemin"))
            except Exception:
                pass

        copy_btn = ctk.CTkButton(
            footer, text="📋 Copier le chemin", width=180, height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=_copy_path,
        )
        copy_btn.grid(row=0, column=0, sticky="w")

        # Si la session est nettoyée, propose d'ouvrir le récap visuel
        if s.flag_cleaned and (s.path / "_stats_before_cleanup.json").is_file():
            def _open_recap():
                try:
                    from gui_cleanup_recap import CleanupRecapDialog
                    CleanupRecapDialog(self, s.path)
                except Exception as e:
                    messagebox.showerror("Récap", f"Impossible d'ouvrir : {e}")
            ctk.CTkButton(
                footer, text="🧹 Récap nettoyage", width=180, height=32,
                fg_color=("gray85", "gray25"),
                text_color=("gray15", "gray90"),
                hover_color=("gray75", "gray35"),
                command=_open_recap,
            ).grid(row=0, column=1, sticky="w", padx=(8, 0))

        ctk.CTkButton(
            footer, text="Fermer", width=100, height=32,
            font=ctk.CTkFont(weight="bold"),
            command=dlg.destroy,
        ).grid(row=0, column=2, sticky="e")


_FAULT_FH = None   # garde le fichier faulthandler ouvert (sinon GC → désactivé)


def _install_crash_logger() -> Path | None:
    """Installe un fichier de log applicatif + capture les exceptions non gérées.

    Le log est rotatif (max 1 MB, 3 backups) dans le dossier de config :
    %APPDATA%\\ChiroTool\\chirotool.log (ou ChiroTool_data/chirotool.log
    en portable).

    Sans ça, un crash de la GUI (notamment en exe windowed où stdout/stderr
    sont None) disparaît silencieusement et l'utilisateur ne peut pas nous
    aider à diagnostiquer. Maintenant on a une trace exploitable.
    """
    import logging
    import sys as _sys
    import traceback as _tb
    from logging.handlers import RotatingFileHandler

    try:
        log_dir = config_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "chirotool.log"
        handler = RotatingFileHandler(
            log_path, maxBytes=1024 * 1024, backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        # Évite les doublons si re-installé (rebuild dev)
        for h in list(root_logger.handlers):
            if isinstance(h, RotatingFileHandler):
                root_logger.removeHandler(h)
        root_logger.addHandler(handler)

        # Hook exceptions non rattrapées (incl. threads via threading.excepthook)
        def _excepthook(exc_type, exc_value, exc_tb):
            try:
                txt = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
                logging.critical("UNCAUGHT EXCEPTION:\n%s", txt)
            except Exception:
                pass
        _sys.excepthook = _excepthook
        try:
            import threading as _th
            def _thread_excepthook(args):
                try:
                    txt = "".join(_tb.format_exception(
                        args.exc_type, args.exc_value, args.exc_traceback))
                    logging.critical(
                        "UNCAUGHT THREAD EXCEPTION in %s:\n%s",
                        args.thread.name if args.thread else "?", txt)
                except Exception:
                    pass
            _th.excepthook = _thread_excepthook
        except Exception:
            pass

        # faulthandler : capture les crashs NATIFS (segfault, abort Tcl/Tk
        # « async handler deleted by the wrong thread », etc.) que excepthook
        # ne voit PAS. Sur un hard-close silencieux, le fichier ci-dessous
        # contiendra la pile de tous les threads → diagnostic définitif.
        try:
            import faulthandler
            import datetime as _dt
            global _FAULT_FH
            _FAULT_FH = open(log_dir / "chirotool_crash.log", "a",
                             encoding="utf-8", buffering=1)
            _FAULT_FH.write(f"\n===== session {_dt.datetime.now().isoformat()} "
                            f"=====\n")
            _FAULT_FH.flush()
            faulthandler.enable(file=_FAULT_FH, all_threads=True)
        except Exception:
            pass

        logging.info("=" * 60)
        logging.info("ChiroTool démarrage")
        return log_path
    except Exception:
        return None


def main() -> int:
    # Logger applicatif + capture crashes
    log_path = _install_crash_logger()

    # Lock d'instance unique (évite plusieurs .exe ouverts)
    lock, acquired = single_instance_acquire()
    if not acquired:
        # Une autre instance tourne déjà
        import tkinter as tk
        root = tk.Tk(); root.withdraw()
        messagebox.showwarning(
            "ChiroTool déjà ouvert",
            "Une autre instance de ChiroTool est déjà en cours d'exécution.\n"
            "Bascule dessus plutôt que d'en lancer une nouvelle."
        )
        return 1

    try:
        app = ChiroToolApp()
        try:
            app.mainloop()
        finally:
            if lock:
                try:
                    lock.close()
                except Exception:
                    pass
    except Exception:
        # Crash au démarrage de l'app : log + messagebox pour l'utilisateur
        import logging as _log
        import traceback as _tb
        _log.critical("Crash au démarrage : %s", _tb.format_exc())
        try:
            import tkinter as tk
            root = tk.Tk(); root.withdraw()
            msg = (
                "ChiroTool a rencontré une erreur fatale et doit fermer.\n\n"
                f"Détails enregistrés dans :\n{log_path}\n\n"
                "Tu peux partager ce fichier pour aider au diagnostic."
            )
            messagebox.showerror("Erreur fatale", msg)
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
