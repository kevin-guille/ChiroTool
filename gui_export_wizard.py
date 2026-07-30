"""
gui_export_wizard.py — assistant d'export portable de sessions (USB / partage).

Workflow guidé :
  1. Cocher un ou plusieurs contrats
  2. Pour chaque contrat, cocher les nuits à emporter
  3. Options Data / Data_k (métadonnées toujours incluses)
  4. Estimation de volume (plan_export)
  5. Choix du dossier destination + lancement avec journal (RunDialog)

S'appuie sur ``export_sessions.plan_export`` / ``run_export`` (aucune logique
de copie dans ce module).
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from export_sessions import ExportSessionSpec, plan_export


def _fmt_bytes(n: int) -> str:
    x = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(x) < 1024:
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024
    return f"{x:.1f} PB"


def _session_label(s: dict) -> str:
    """Libellé d'une nuit pour la liste."""
    date = (s.get("date_debut") or "")[:10] or "?"
    point = s.get("n_point_fixe") or "?"
    passage = s.get("n_passage")
    pass_s = f"Pass{passage}" if passage is not None else "Pass?"
    name = s.get("canonical_name") or s.get("id") or "?"
    # Raccourcir si le nom canonique est déjà très long
    short = name if len(str(name)) <= 42 else str(name)[:39] + "…"
    return f"{date}  ·  {point}  ·  {pass_s}  —  {short}"


def _group_sessions(sessions: list[dict]) -> dict[str, list[dict]]:
    """Groupe par contrat (fallback campagne)."""
    by: dict[str, list[dict]] = {}
    for s in sessions:
        key = (s.get("nom_contrat") or "").strip() \
            or (s.get("campaign") or "").strip() \
            or "(sans contrat)"
        by.setdefault(key, []).append(s)
    # Tri nuits : date desc puis point
    for key in by:
        by[key].sort(
            key=lambda r: (
                (r.get("date_debut") or ""),
                r.get("n_point_fixe") or "",
                r.get("n_passage") or 0,
            ),
            reverse=True,
        )
    return dict(sorted(by.items(), key=lambda kv: kv[0].lower()))


def _usable_sessions(registry) -> list[dict]:
    """Sessions du registre dont le chemin disque existe encore."""
    if registry is None:
        return []
    out = []
    for s in registry.all_sessions(include_archived=False):
        path = s.get("session_path") or s.get("path") or ""
        if not path:
            continue
        p = Path(path)
        if p.is_dir():
            out.append(s)
    return out


class ExportSessionsWizard(ctk.CTkToplevel):
    """Wizard modal d'export de sessions.

    Après fermeture : ``self.result`` vaut un dict
    ``{dest, specs, plan}`` si l'utilisateur a lancé l'export, sinon None.
    L'appelant peut aussi laisser le wizard lancer lui-même via
    ``run_on_confirm=True`` (défaut) et un callback ``on_export_done``.
    """

    def __init__(
        self,
        master,
        *,
        registry,
        workspace: Path | None = None,
        run_on_confirm: bool = True,
        on_export_done=None,
    ):
        super().__init__(master)
        self.title("Exporter des sessions (USB / partage)")
        self.geometry("780x640")
        self.minsize(680, 520)
        self.transient(master)
        self.after(50, self.grab_set)

        self.registry = registry
        self.workspace = Path(workspace) if workspace else None
        self.run_on_confirm = run_on_confirm
        self.on_export_done = on_export_done
        self.result: dict | None = None

        self._sessions = _usable_sessions(registry)
        self._groups = _group_sessions(self._sessions)

        # id session → BooleanVar
        self._night_vars: dict[str, ctk.BooleanVar] = {}
        # contrat → BooleanVar (état « tous cochés »)
        self._contract_vars: dict[str, ctk.BooleanVar] = {}
        # contrat → frame des nuits (pour collapse)
        self._contract_frames: dict[str, ctk.CTkFrame] = {}
        self._contract_expand_btns: dict[str, ctk.CTkButton] = {}
        self._contract_expanded: dict[str, bool] = {}

        self._include_data_k = ctk.BooleanVar(value=True)
        self._include_data = ctk.BooleanVar(value=False)
        self._dest_var = ctk.StringVar(value="")
        self._size_var = ctk.StringVar(value="Estimation : —")
        self._count_var = ctk.StringVar(value="0 nuit(s) sélectionnée(s)")
        self._plan_cache = None
        self._estimate_after_id = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        if not self._sessions:
            self.after(100, self._warn_empty)

    # -- UI ----------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text="Exporter des nuits (portable)",
            font=ctk.CTkFont(size=16, weight="bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            head,
            text="Métadonnées toujours incluses (manifest, xlsx, Summary…). "
                 "Choisis les bruts et/ou le Data_k TE×10.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
            anchor="w", wraplength=720, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Options globales
        opts = ctk.CTkFrame(
            self, fg_color=("gray92", "gray20"),
            corner_radius=8, border_width=1,
            border_color=("gray80", "gray25"),
        )
        opts.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        for i in range(4):
            opts.grid_columnconfigure(i, weight=0)
        opts.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            opts, text="Contenu audio",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=(12, 8), pady=10, sticky="w")

        chk_k = ctk.CTkCheckBox(
            opts, text="Data_k (TE×10) — recommandé",
            variable=self._include_data_k,
            command=self._schedule_estimate,
        )
        chk_k.grid(row=0, column=1, padx=8, pady=10, sticky="w")

        chk_d = ctk.CTkCheckBox(
            opts, text="Data (bruts, lourds)",
            variable=self._include_data,
            command=self._schedule_estimate,
        )
        chk_d.grid(row=0, column=2, padx=8, pady=10, sticky="w")

        ctk.CTkLabel(
            opts, text="✓ Métadonnées (forcé)",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
        ).grid(row=0, column=3, padx=12, pady=10, sticky="e")

        # Corps : liste contrats / nuits
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 4))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        tools = ctk.CTkFrame(body, fg_color="transparent")
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        tools.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(
            tools, text="Tout cocher", width=100, height=28,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=lambda: self._set_all(True),
        ).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkButton(
            tools, text="Tout décocher", width=110, height=28,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=lambda: self._set_all(False),
        ).grid(row=0, column=1, padx=(0, 6))
        ctk.CTkLabel(
            tools, textvariable=self._count_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="e",
        ).grid(row=0, column=2, sticky="e")

        self.scroll = ctk.CTkScrollableFrame(
            body, fg_color=("gray95", "gray17"), corner_radius=8,
        )
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

        self._populate_tree()

        # Destination + estimation
        foot_top = ctk.CTkFrame(
            self, fg_color=("gray92", "gray20"),
            corner_radius=8, border_width=1,
            border_color=("gray80", "gray25"),
        )
        foot_top.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 4))
        foot_top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(foot_top, text="Destination",
                      font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=(12, 8), pady=(10, 2), sticky="w")
        dest_row = ctk.CTkFrame(foot_top, fg_color="transparent")
        dest_row.grid(row=1, column=0, columnspan=3, sticky="ew",
                       padx=12, pady=(0, 10))
        dest_row.grid_columnconfigure(0, weight=1)
        self.dest_entry = ctk.CTkEntry(
            dest_row, textvariable=self._dest_var, height=32,
            placeholder_text="Dossier où créer ChiroTool_export_…",
        )
        self.dest_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            dest_row, text="Parcourir…", width=100, height=32,
            command=self._browse_dest,
        ).grid(row=0, column=1)

        self.size_lbl = ctk.CTkLabel(
            foot_top, textvariable=self._size_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#1f6feb", "#58a6ff"),
            anchor="w",
        )
        self.size_lbl.grid(row=0, column=1, columnspan=2, padx=12, pady=(10, 2),
                            sticky="e")

        # Boutons bas
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 14))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            footer, text="Annuler", width=110, height=34,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_cancel,
        ).grid(row=0, column=1, padx=(0, 8))
        self.export_btn = ctk.CTkButton(
            footer, text="📤  Exporter", width=140, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_export,
        )
        self.export_btn.grid(row=0, column=2)

    def _populate_tree(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._night_vars.clear()
        self._contract_vars.clear()
        self._contract_frames.clear()
        self._contract_expand_btns.clear()
        self._contract_expanded.clear()

        if not self._groups:
            ctk.CTkLabel(
                self.scroll,
                text="Aucune session avec dossier accessible sur le disque.\n"
                     "Lance un scan du workspace d'abord.",
                text_color=("gray40", "gray70"),
                justify="left",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=20)
            return

        row = 0
        for contrat, nights in self._groups.items():
            # Filtrer les nuits sans id
            usable = []
            for n in nights:
                sid = n.get("id") or n.get("canonical_name")
                if not sid:
                    continue
                path = n.get("session_path") or n.get("path")
                if not path or not Path(path).is_dir():
                    continue
                usable.append(n)
            if not usable:
                continue

            block = ctk.CTkFrame(
                self.scroll, fg_color=("gray90", "gray22"), corner_radius=6,
            )
            block.grid(row=row, column=0, sticky="ew", padx=4, pady=3)
            block.grid_columnconfigure(1, weight=1)
            row += 1

            cvar = ctk.BooleanVar(value=False)
            self._contract_vars[contrat] = cvar
            self._contract_expanded[contrat] = True

            def _toggle_contract(c=contrat, var=cvar):
                self._on_contract_toggle(c, var.get())

            chk = ctk.CTkCheckBox(
                block, text="", variable=cvar, width=24,
                command=_toggle_contract,
            )
            chk.grid(row=0, column=0, padx=(8, 2), pady=8)

            expand_btn = ctk.CTkButton(
                block, text="▼", width=28, height=28,
                fg_color="transparent",
                text_color=("gray20", "gray90"),
                hover_color=("gray80", "gray30"),
                command=lambda c=contrat: self._toggle_expand(c),
            )
            expand_btn.grid(row=0, column=1, sticky="w", pady=6)
            self._contract_expand_btns[contrat] = expand_btn

            ctk.CTkLabel(
                block,
                text=f"📁  {contrat}   ({len(usable)} nuit{'s' if len(usable) != 1 else ''})",
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w",
            ).grid(row=0, column=2, sticky="w", padx=4, pady=8)

            nights_frame = ctk.CTkFrame(block, fg_color="transparent")
            nights_frame.grid(row=1, column=0, columnspan=3, sticky="ew",
                               padx=(36, 8), pady=(0, 8))
            nights_frame.grid_columnconfigure(0, weight=1)
            self._contract_frames[contrat] = nights_frame

            for i, n in enumerate(usable):
                sid = str(n.get("id") or n.get("canonical_name"))
                nvar = ctk.BooleanVar(value=False)
                self._night_vars[sid] = nvar
                # keep session dict reachable
                nvar._session = n  # type: ignore[attr-defined]

                def _night_changed(*_a, c=contrat):
                    self._sync_contract_var(c)
                    self._schedule_estimate()

                nchk = ctk.CTkCheckBox(
                    nights_frame,
                    text=_session_label(n),
                    variable=nvar,
                    command=_night_changed,
                    font=ctk.CTkFont(size=12),
                )
                nchk.grid(row=i, column=0, sticky="w", pady=2)

    # -- interactions ------------------------------------------------------

    def _warn_empty(self):
        messagebox.showinfo(
            "Export sessions",
            "Aucune session accessible sur le disque.\n\n"
            "Ouvre un workspace et lance un scan pour alimenter le registre.",
            parent=self,
        )

    def _toggle_expand(self, contrat: str):
        fr = self._contract_frames.get(contrat)
        if fr is None:
            return
        expanded = not self._contract_expanded.get(contrat, True)
        self._contract_expanded[contrat] = expanded
        if expanded:
            fr.grid()
        else:
            fr.grid_remove()
        btn = self._contract_expand_btns.get(contrat)
        if btn is not None:
            try:
                btn.configure(text="▼" if expanded else "▶")
            except Exception:
                pass

    def _on_contract_toggle(self, contrat: str, checked: bool):
        fr = self._contract_frames.get(contrat)
        if fr is None:
            return
        for sid, var in self._night_vars.items():
            sess = getattr(var, "_session", None)
            if sess is None:
                continue
            key = (sess.get("nom_contrat") or "").strip() \
                or (sess.get("campaign") or "").strip() \
                or "(sans contrat)"
            if key == contrat:
                var.set(checked)
        self._schedule_estimate()

    def _sync_contract_var(self, contrat: str):
        """Met le checkbox contrat à True ssi toutes les nuits sont cochées."""
        cvar = self._contract_vars.get(contrat)
        if cvar is None:
            return
        nights = []
        for sid, var in self._night_vars.items():
            sess = getattr(var, "_session", None)
            if sess is None:
                continue
            key = (sess.get("nom_contrat") or "").strip() \
                or (sess.get("campaign") or "").strip() \
                or "(sans contrat)"
            if key == contrat:
                nights.append(var.get())
        if not nights:
            return
        all_on = all(nights)
        # Évite de re-trigger _on_contract_toggle en cascade
        if cvar.get() != all_on:
            cvar.set(all_on)

    def _set_all(self, value: bool):
        for var in self._night_vars.values():
            var.set(value)
        for cvar in self._contract_vars.values():
            cvar.set(value)
        self._schedule_estimate()

    def _selected_sessions(self) -> list[dict]:
        out = []
        for sid, var in self._night_vars.items():
            if var.get():
                sess = getattr(var, "_session", None)
                if sess is not None:
                    out.append(sess)
        return out

    def _browse_dest(self):
        initial = self._dest_var.get().strip()
        if not initial and self.workspace:
            initial = str(self.workspace)
        path = filedialog.askdirectory(
            title="Dossier de destination de l'export",
            initialdir=initial or None,
            parent=self,
        )
        if path:
            self._dest_var.set(path)

    def _schedule_estimate(self):
        """Debounce l'estimation (plan_export peut parcourir beaucoup de fichiers)."""
        n = len(self._selected_sessions())
        self._count_var.set(
            f"{n} nuit{'s' if n != 1 else ''} sélectionnée{'s' if n != 1 else ''}"
        )
        if self._estimate_after_id is not None:
            try:
                self.after_cancel(self._estimate_after_id)
            except Exception:
                pass
        self._size_var.set("Estimation : calcul…")
        self._estimate_after_id = self.after(250, self._run_estimate)

    def _build_specs(self, sessions: list[dict]) -> list[ExportSessionSpec]:
        include_k = bool(self._include_data_k.get())
        include_d = bool(self._include_data.get())
        specs = []
        for s in sessions:
            path = s.get("session_path") or s.get("path")
            if not path:
                continue
            campaign = (s.get("nom_contrat") or "").strip() \
                or (s.get("campaign") or "").strip() or None
            specs.append(ExportSessionSpec(
                session_path=Path(path),
                include_data=include_d,
                include_data_k=include_k,
                campaign=campaign,
            ))
        return specs

    def _run_estimate(self):
        self._estimate_after_id = None
        sessions = self._selected_sessions()
        if not sessions:
            self._size_var.set("Estimation : —")
            self._plan_cache = None
            return
        if not self._include_data_k.get() and not self._include_data.get():
            # Meta only — estimation légère
            pass
        try:
            # dest fictif pour le plan (seul le rel compte pour les tailles)
            dest = Path(self._dest_var.get().strip() or ".")
            specs = self._build_specs(sessions)
            plan = plan_export(specs, dest, stamp="estimate")
            self._plan_cache = plan
            n_files = len(plan.files)
            size_s = _fmt_bytes(plan.estimated_bytes)
            warn = f"  ·  {len(plan.warnings)} avert." if plan.warnings else ""
            self._size_var.set(
                f"Estimation : {size_s}  ·  {n_files} fichier(s){warn}"
            )
        except Exception as e:
            self._plan_cache = None
            self._size_var.set(f"Estimation impossible : {e}")

    # -- export ------------------------------------------------------------

    def _on_cancel(self):
        self.result = None
        self.destroy()

    def _on_export(self):
        sessions = self._selected_sessions()
        if not sessions:
            messagebox.showinfo(
                "Sélection vide",
                "Coche au moins une nuit à exporter.",
                parent=self,
            )
            return

        if not self._include_data_k.get() and not self._include_data.get():
            if not messagebox.askyesno(
                "Audio non inclus",
                "Ni Data_k ni Data ne sont cochés : l'export ne contiendra "
                "que les métadonnées (manifest, xlsx, Summary…).\n\n"
                "Continuer ?",
                parent=self,
                default=messagebox.YES,
            ):
                return

        dest_s = self._dest_var.get().strip()
        if not dest_s:
            messagebox.showwarning(
                "Destination manquante",
                "Choisis un dossier de destination (clé USB, disque…).",
                parent=self,
            )
            self._browse_dest()
            dest_s = self._dest_var.get().strip()
            if not dest_s:
                return

        dest = Path(dest_s)
        if not dest.is_dir():
            messagebox.showerror(
                "Destination invalide",
                f"Le dossier n'existe pas :\n{dest}",
                parent=self,
            )
            return

        specs = self._build_specs(sessions)
        try:
            plan = plan_export(specs, dest)
        except Exception as e:
            messagebox.showerror("Plan d'export", str(e), parent=self)
            return

        size_s = _fmt_bytes(plan.estimated_bytes)
        if not messagebox.askyesno(
            "Confirmer l'export",
            f"{len(sessions)} nuit(s)  ·  {len(plan.files)} fichier(s)\n"
            f"Volume estimé : {size_s}\n"
            f"Data_k : {'oui' if self._include_data_k.get() else 'non'}  ·  "
            f"Data : {'oui' if self._include_data.get() else 'non'}\n\n"
            f"Destination :\n{plan.dest_root}\n\n"
            f"Lancer la copie ?",
            parent=self,
            default=messagebox.YES,
        ):
            return

        self.result = {
            "dest": dest,
            "specs": specs,
            "plan": plan,
            "sessions": sessions,
        }

        if self.run_on_confirm:
            self._launch_export(plan)
        else:
            self.destroy()

    def _launch_export(self, plan):
        """Lance run_export dans un RunDialog puis ferme le wizard."""
        from gui_runner import RunDialog

        # Fermer le wizard avant le modal de progression (évite double grab)
        self.withdraw()

        def worker(log, progress=None):
            from export_sessions import run_export
            log(f"Destination : {plan.dest_root}")
            log(f"Sessions    : {len(plan.sessions)}")
            log(f"Fichiers    : {len(plan.files)}")
            log(f"Estimation  : {_fmt_bytes(plan.estimated_bytes)}")
            if plan.warnings:
                log("")
                log("Avertissements du plan :")
                for w in plan.warnings[:20]:
                    log(f"  ⚠ {w}")
                if len(plan.warnings) > 20:
                    log(f"  … +{len(plan.warnings) - 20}")
            log("")
            log("=== Copie en cours ===")
            log("")
            res = run_export(plan, dry_run=False, progress=progress)
            log("")
            log(f"✓ Copiés  : {res.get('n_copied', 0)}")
            log(f"  Ignorés : {res.get('n_skipped', 0)}")
            log(f"  Erreurs : {res.get('n_errors', 0)}")
            log(f"  Volume  : {_fmt_bytes(res.get('bytes_copied', 0))}")
            log(f"  Paquet  : {res.get('dest_root')}")
            for e in (res.get("errors") or [])[:15]:
                log(f"  ✗ {e}")
            if res.get("n_errors") and not res.get("n_copied"):
                res["error"] = res.get("error") or "export échoué"
            return res

        def _done(result):
            try:
                self.destroy()
            except Exception:
                pass
            dest_root = (result or {}).get("dest_root") or plan.dest_root
            n_err = (result or {}).get("n_errors") or 0
            n_ok = (result or {}).get("n_copied") or 0
            if n_err and not n_ok:
                messagebox.showerror(
                    "Export échoué",
                    f"Aucune copie réussie.\n\n"
                    + "\n".join((result or {}).get("errors") or [])[:800],
                )
            else:
                msg = (
                    f"Export terminé.\n\n"
                    f"{n_ok} fichier(s) copié(s)"
                    + (f", {n_err} erreur(s)" if n_err else "")
                    + f"\n\n{dest_root}"
                )
                messagebox.showinfo("Export sessions", msg)
            if self.on_export_done:
                try:
                    self.on_export_done(result or {})
                except Exception:
                    pass

        RunDialog(
            self.master,
            title="Export sessions",
            worker=worker,
            on_done=_done,
        )


def open_export_sessions_wizard(
    master,
    *,
    registry,
    workspace: Path | None = None,
    on_export_done=None,
) -> ExportSessionsWizard:
    """Ouvre le wizard (non bloquant ; l'export se lance depuis le wizard)."""
    return ExportSessionsWizard(
        master,
        registry=registry,
        workspace=workspace,
        run_on_confirm=True,
        on_export_done=on_export_done,
    )
