"""
gui_cleanup_recap.py — popup graphique récap après un cleanup.

Affiche en un coup d'œil :
  - Volume avant / après / gagné (bar chart horizontal)
  - Répartition des décisions (kept / deleted_noise / deleted_low_confidence)
  - Présence éventuelle d'un dossier Data/ (WAV bruts) non encore supprimés

Source : ``_stats_before_cleanup.json`` à la racine de la session + scan
physique des dossiers Data/ et Data_k/ pour calculer le réel.

Rendu : tkinter.Canvas natif (zéro dépendance ajoutée).
"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path

import customtkinter as ctk


def _fmt_size(n: int | float) -> str:
    """Formate une taille en B/KB/MB/GB selon l'échelle."""
    if n is None:
        return "?"
    n = float(n)
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} To"


def _dir_size_bytes(path: Path) -> int:
    """Taille totale d'un dossier en octets (sommée sur tous les WAV)."""
    if not path.is_dir():
        return 0
    total = 0
    try:
        for p in path.glob("*.wav"):
            try:
                total += p.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def _count_wav(path: Path) -> int:
    if not path.is_dir():
        return 0
    try:
        return sum(1 for _ in path.glob("*.wav"))
    except OSError:
        return 0


class CleanupRecapDialog(ctk.CTkToplevel):
    """Popup d'analyse post-cleanup pour une session.

    Peut être ouvert à 2 moments :
      - automatiquement à la fin d'un cleanup réussi (via gui_runner)
      - à la demande depuis le bouton « Détails avancés » d'une session déjà
        nettoyée (relit le _stats_before_cleanup.json)
    """

    def __init__(self, master, session_path: Path):
        super().__init__(master)
        self.session_path = Path(session_path)
        self.title(f"Nettoyage — {self.session_path.name}")
        self.geometry("680x560")
        self.minsize(560, 480)
        self.transient(master)
        self.after(50, self.grab_set)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_body()
        self._load_and_render()

    def _build_header(self):
        h = ctk.CTkFrame(self, fg_color=("gray92", "gray20"), corner_radius=0)
        h.grid(row=0, column=0, sticky="ew")
        h.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            h, text="🧹  Récap du nettoyage",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(
            h, text=self.session_path.name,
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray70"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

    def _build_body(self):
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        self.body.grid_columnconfigure(0, weight=1)

        # Footer
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            footer, text="Fermer", width=120, height=34,
            font=ctk.CTkFont(weight="bold"),
            command=self.destroy,
        ).grid(row=0, column=1, sticky="e")

    def _load_and_render(self):
        stats_path = self.session_path / "_stats_before_cleanup.json"
        if not stats_path.is_file():
            ctk.CTkLabel(
                self.body,
                text="(pas de _stats_before_cleanup.json — la session n'a pas été nettoyée.)",
                font=ctk.CTkFont(size=12, slant="italic"),
                text_color=("gray50", "gray60"),
            ).grid(row=0, column=0, pady=40)
            return
        try:
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
        except Exception as e:
            ctk.CTkLabel(
                self.body, text=f"Lecture impossible : {e}",
                text_color=("#cf222e", "#f85149"),
            ).grid(row=0, column=0, pady=40)
            return

        files = stats.get("files", {}) or {}
        contacts = stats.get("contacts", {}) or {}
        by_decision = contacts.get("by_decision", {}) or {}

        # --- Bloc 1 : volume avant / après / gagné
        self._render_volume_block(files)

        # --- Bloc 2 : camembert des décisions
        self._render_decisions_block(by_decision, contacts.get("total", 0))

        # --- Bloc 3 : sanité dossiers (réel sur disque)
        self._render_disk_block(files)

    # =========================================================================
    # Blocs
    # =========================================================================

    def _render_volume_block(self, files: dict):
        card = ctk.CTkFrame(self.body, fg_color=("gray96", "gray17"),
                              corner_radius=8)
        card.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="📊  Volume avant / après cleanup",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))

        total = files.get("bytes_total") or 0
        to_del = files.get("bytes_to_delete") or 0
        kept = total - to_del

        # Bar chart horizontal : 2 barres empilées (avant en haut, après en bas)
        canvas_h = 100
        c = tk.Canvas(card, height=canvas_h, bg=self._canvas_bg(),
                       highlightthickness=0)
        c.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        # Force la mesure du width après pack/grid
        card.update_idletasks()
        w = max(c.winfo_width(), 400)

        margin_x = 90
        bar_h = 28
        # Barre AVANT
        y_top = 10
        c.create_text(8, y_top + bar_h // 2, text="Avant",
                       anchor="w", fill=self._gray(),
                       font=("Segoe UI", 11, "bold"))
        c.create_rectangle(
            margin_x, y_top, w - 16, y_top + bar_h,
            fill="#a0c4ff", outline="",
        )
        c.create_text(
            (margin_x + w - 16) // 2, y_top + bar_h // 2,
            text=f"{_fmt_size(total)}", fill="#0b3a78",
            font=("Segoe UI", 10, "bold"),
        )

        # Barre APRÈS (proportionnelle)
        y_bot = y_top + bar_h + 22
        if total > 0:
            after_w = int((w - 16 - margin_x) * kept / total)
        else:
            after_w = 0
        c.create_text(8, y_bot + bar_h // 2, text="Après",
                       anchor="w", fill=self._gray(),
                       font=("Segoe UI", 11, "bold"))
        # zone supprimée (rouge pâle) en arrière-plan
        c.create_rectangle(
            margin_x, y_bot, w - 16, y_bot + bar_h,
            fill="#ffd7d7", outline="",
        )
        # zone conservée (verte)
        c.create_rectangle(
            margin_x, y_bot, margin_x + after_w, y_bot + bar_h,
            fill="#7dd87d", outline="",
        )
        if after_w > 60:
            c.create_text(
                margin_x + after_w // 2, y_bot + bar_h // 2,
                text=f"{_fmt_size(kept)} gardés", fill="#0a4a0a",
                font=("Segoe UI", 10, "bold"),
            )
        if (w - 16 - margin_x - after_w) > 60:
            c.create_text(
                margin_x + after_w + (w - 16 - margin_x - after_w) // 2,
                y_bot + bar_h // 2,
                text=f"{_fmt_size(to_del)} libérés", fill="#6e0e0e",
                font=("Segoe UI", 10, "bold"),
            )

        # Stats textuelles en dessous
        n_kept = files.get("planned_kept", 0)
        n_del = files.get("planned_deleted", 0)
        ratio = (to_del / total * 100) if total else 0.0
        ctk.CTkLabel(
            card, anchor="w",
            text=(
                f"  • Avant : {files.get('total_wav_on_disk', 0)} WAV  ·  {_fmt_size(total)}\n"
                f"  • Conservés : {n_kept} WAV  ·  {_fmt_size(kept)}\n"
                f"  • Supprimés : {n_del} WAV  ·  {_fmt_size(to_del)}  "
                f"({ratio:.0f} % du volume)"
            ),
            font=ctk.CTkFont(family="Consolas", size=11),
            justify="left",
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 12))

    def _render_decisions_block(self, by_decision: dict, total_contacts: int):
        card = ctk.CTkFrame(self.body, fg_color=("gray96", "gray17"),
                              corner_radius=8)
        card.grid(row=1, column=0, sticky="ew", padx=2, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text=f"🎯  Décisions sur les contacts  ({total_contacts} au total)",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))

        # Liste les décisions triées
        items = sorted(by_decision.items(), key=lambda kv: -kv[1])
        # Couleurs par décision
        colors = {
            "kept": "#2ea043",
            "deleted_noise": "#9b59b6",
            "deleted_low_confidence": "#e67e22",
            "deleted_group_disabled": "#7f8c8d",
            "deleted_unknown_group": "#34495e",
        }
        labels_fr = {
            "kept": "Conservés",
            "deleted_noise": "Supprimés (noise Tadarida)",
            "deleted_low_confidence": "Supprimés (proba < seuil)",
            "deleted_group_disabled": "Supprimés (groupe désactivé)",
            "deleted_unknown_group": "Supprimés (taxon non classé)",
        }

        # Barre empilée horizontale
        total = sum(n for _, n in items) or 1
        canvas_h = 36
        c = tk.Canvas(card, height=canvas_h, bg=self._canvas_bg(),
                       highlightthickness=0)
        c.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        card.update_idletasks()
        w = max(c.winfo_width(), 400) - 24

        x = 12
        for key, n in items:
            seg_w = int(w * n / total)
            color = colors.get(key, "#888")
            c.create_rectangle(x, 4, x + seg_w, 30,
                                fill=color, outline="")
            if seg_w > 50:
                c.create_text(
                    x + seg_w // 2, 17,
                    text=f"{n}", fill="white",
                    font=("Segoe UI", 10, "bold"),
                )
            x += seg_w

        # Légende sous la barre
        leg = ctk.CTkFrame(card, fg_color="transparent")
        leg.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        for i, (key, n) in enumerate(items):
            color = colors.get(key, "#888")
            label = labels_fr.get(key, key)
            pct = (n / total_contacts * 100) if total_contacts else 0
            chip = ctk.CTkFrame(leg, fg_color="transparent")
            chip.grid(row=i // 2, column=i % 2, sticky="w",
                       padx=(0, 12), pady=2)
            sw = tk.Canvas(chip, width=14, height=14,
                            bg=self._canvas_bg(), highlightthickness=0)
            sw.create_rectangle(0, 4, 14, 12, fill=color, outline="")
            sw.pack(side="left")
            ctk.CTkLabel(
                chip, text=f"  {label}  ·  {n}  ({pct:.0f}%)",
                font=ctk.CTkFont(size=11),
            ).pack(side="left")

    def _render_disk_block(self, files: dict):
        """Bloc d'info : ce qui reste sur disque, notamment le dossier Data/ raw."""
        card = ctk.CTkFrame(self.body, fg_color=("gray96", "gray17"),
                              corner_radius=8)
        card.grid(row=2, column=0, sticky="ew", padx=2, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="💾  État actuel sur le disque",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))

        # Scan réel
        data_k = self.session_path / "Data_k"
        data_raw = self.session_path / "Data"
        n_dk = _count_wav(data_k)
        s_dk = _dir_size_bytes(data_k)
        n_raw = _count_wav(data_raw)
        s_raw = _dir_size_bytes(data_raw)

        lines = [
            f"  • Data_k/  (WAV TE×10, envoyés à Vigie-Chiro) : "
            f"{n_dk} fichiers  ·  {_fmt_size(s_dk)}",
        ]
        if data_raw.is_dir() and n_raw > 0:
            lines.append(
                f"  • Data/  (WAV bruts originaux) : "
                f"{n_raw} fichiers  ·  {_fmt_size(s_raw)}  ⚠  non touché par le cleanup"
            )

        ctk.CTkLabel(
            card, text="\n".join(lines),
            font=ctk.CTkFont(family="Consolas", size=11),
            justify="left", anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        # Si le dossier Data/ existe avec contenu : proposer suppression
        if data_raw.is_dir() and n_raw > 0:
            warn = ctk.CTkFrame(card, fg_color=("#fff4d6", "#3a2d12"),
                                  corner_radius=6)
            warn.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
            warn.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                warn,
                text=(
                    f"Tu peux libérer {_fmt_size(s_raw)} supplémentaires en\n"
                    "supprimant les WAV bruts originaux (dossier Data/).\n\n"
                    "À ne faire qu'une fois sûr que l'analyse est validée :\n"
                    "ces fichiers ne sont plus utilisés par ChiroTool après\n"
                    "l'upload, mais conservés par sécurité."
                ),
                font=ctk.CTkFont(size=11),
                text_color=("#7a5a00", "#e8c060"),
                anchor="w", justify="left", wraplength=540,
            ).grid(row=0, column=0, sticky="ew", padx=10, pady=8)

            ctk.CTkButton(
                card,
                text=f"🗑  Supprimer aussi Data/  (libère {_fmt_size(s_raw)})",
                height=34, width=300,
                fg_color=("#cf222e", "#b42318"),
                hover_color=("#b42318", "#961f17"),
                text_color="white",
                command=lambda: self._delete_raw_data(data_raw, s_raw, n_raw),
            ).grid(row=3, column=0, padx=16, pady=(0, 12))

    def _delete_raw_data(self, data_raw: Path, expected_size: int, n_files: int):
        """Confirmation puis suppression du dossier Data/ original."""
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Supprimer les WAV bruts ?",
            f"Tu vas supprimer DÉFINITIVEMENT {n_files} fichiers WAV bruts\n"
            f"du dossier {data_raw.name}/ ({_fmt_size(expected_size)}).\n\n"
            "L'analyse Tadarida + le nettoyage sont déjà faits, ces fichiers\n"
            "ne sont plus utilisés. Mais ils ne pourront plus être re-analysés\n"
            "manuellement par la suite.\n\n"
            "Confirmer la suppression ?",
            parent=self,
        ):
            return

        # Suppression
        errors = 0
        deleted = 0
        for p in data_raw.glob("*.wav"):
            try:
                p.unlink()
                deleted += 1
            except OSError:
                errors += 1
        # Tente de supprimer le dossier s'il est vide
        try:
            data_raw.rmdir()
        except OSError:
            pass

        if errors:
            messagebox.showwarning(
                "Suppression partielle",
                f"{deleted} fichier(s) supprimé(s), {errors} échec(s).",
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Suppression terminée",
                f"✓ {deleted} fichiers supprimés\n"
                f"✓ {_fmt_size(expected_size)} libérés",
                parent=self,
            )
        # Re-render le bloc disque
        for w in self.body.winfo_children():
            w.destroy()
        self._load_and_render()

    # =========================================================================
    # Helpers couleurs (thème CTk)
    # =========================================================================

    def _canvas_bg(self) -> str:
        try:
            return "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#fafafa"
        except Exception:
            return "#fafafa"

    def _gray(self) -> str:
        try:
            return "#aaaaaa" if ctk.get_appearance_mode() == "Dark" else "#555555"
        except Exception:
            return "#555555"
