"""
gui_about.py — fenêtre « À propos » de ChiroTool.

Affiche :
  - Logo + nom + version
  - Description courte
  - Crédits : auteur, soutien Acer Campestre, protocole Vigie-Chiro/MNHN
  - Licence MIT
  - Liens : GitHub repo, issues, LinkedIn auteur
  - Bouton « Vérifier les mises à jour » (interroge GitHub Releases,
    pre-releases incluses, et propose la dernière version disponible)

Conçue pour être lisible (le futur utilisateur lambda doit comprendre d'un
coup d'œil qui a fait quoi et où aller pour signaler un bug).
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from version import (
    AUTHOR_LINKEDIN, AUTHOR_NAME,
    EMPLOYER_LINKEDIN, EMPLOYER_NAME, EMPLOYER_URL,
    GITHUB_ISSUES_URL, GITHUB_RELEASES_API, GITHUB_RELEASES_PAGE,
    GITHUB_REPO_URL,
    LICENSE_NAME, LICENSE_URL,
    PROTOCOL_NAME, PROTOCOL_URL,
    is_newer,
    __build_date__, __version__,
)


class AboutDialog(ctk.CTkToplevel):
    """Fenêtre modale « À propos »."""

    def __init__(self, master):
        super().__init__(master)
        self.title("À propos de ChiroTool")
        self.geometry("560x680")
        self.resizable(False, False)
        self.transient(master)
        self.after(50, self.grab_set)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 8))
        body.grid_columnconfigure(0, weight=1)

        # --- Header : logo + nom + version
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(1, weight=1)

        # Icône si trouvée
        icon_path = self._find_icon()
        if icon_path:
            try:
                import tkinter as tk
                # CTk n'a pas de support natif pour les ico — on utilise un
                # placeholder texte ; un futur PR pourra ajouter PhotoImage.
                ctk.CTkLabel(
                    header, text="🦇", font=ctk.CTkFont(size=42),
                    width=64,
                ).grid(row=0, column=0, rowspan=2, padx=(0, 16))
            except Exception:
                pass
        else:
            ctk.CTkLabel(
                header, text="🦇", font=ctk.CTkFont(size=42), width=64,
            ).grid(row=0, column=0, rowspan=2, padx=(0, 16))

        ctk.CTkLabel(
            header, text="ChiroTool",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        ).grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(
            header,
            text=f"version {__version__}  ·  build {__build_date__}",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"), anchor="w",
        ).grid(row=1, column=1, sticky="w")

        # --- Description
        ctk.CTkLabel(
            body,
            text=(
                "Outil libre d'automatisation du traitement des "
                "enregistrements ultrason chiroptères pour le protocole "
                "Vigie-Chiro Point Fixe (MNHN).\n\n"
                "Remplace la chaîne manuelle LupasRename → Kaleidoscope → "
                "upload portail → validation Excel par un workflow piloté "
                "depuis une seule interface, avec stockage local de "
                "l'historique et synchronisation API."
            ),
            font=ctk.CTkFont(size=11),
            text_color=("gray25", "gray80"),
            justify="left", anchor="w", wraplength=500,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 16))

        # --- Crédits
        self._section(body, 2, "👤  Auteur principal")
        self._linked_label(
            body, 3,
            text=f"{AUTHOR_NAME}",
            sub="Chargé d'études naturalistes",
            url=AUTHOR_LINKEDIN,
            link_label="LinkedIn",
        )

        self._section(body, 4, "🏢  Avec le soutien de")
        self._linked_label(
            body, 5,
            text=EMPLOYER_NAME,
            sub="Bureau d'études en écologie",
            url=EMPLOYER_URL,
            link_label="Site web",
            url2=EMPLOYER_LINKEDIN,
            link_label2="LinkedIn",
        )

        self._section(body, 6, "📡  Protocole & API")
        self._linked_label(
            body, 7,
            text=PROTOCOL_NAME,
            sub="Programme de sciences participatives du MNHN",
            url=PROTOCOL_URL,
            link_label="vigienature.fr",
        )

        self._section(body, 8, "📜  Licence")
        self._linked_label(
            body, 9,
            text=f"Licence {LICENSE_NAME}",
            sub="Code source ouvert — usage et contributions libres",
            url=LICENSE_URL,
            link_label="Texte de la licence",
        )

        self._section(body, 10, "🐙  Code source & bugs")
        self._linked_label(
            body, 11,
            text="Dépôt GitHub",
            sub="Code source, issues, contributions",
            url=GITHUB_REPO_URL,
            link_label="Ouvrir sur GitHub",
        )
        self._linked_label(
            body, 12,
            text="Signaler un bug / suggérer une amélioration",
            sub="",
            url=GITHUB_ISSUES_URL,
            link_label="Issues GitHub",
        )

        # --- Footer : check updates + close
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        footer.grid_columnconfigure(0, weight=1)

        self.update_btn = ctk.CTkButton(
            footer, text="🔄  Vérifier les mises à jour", height=34, width=220,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_check_updates,
        )
        self.update_btn.grid(row=0, column=0, sticky="w")

        self.update_status = ctk.CTkLabel(
            footer, text="", font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"), anchor="w",
        )
        self.update_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

        ctk.CTkButton(
            footer, text="Fermer", width=100, height=34,
            font=ctk.CTkFont(weight="bold"),
            command=self.destroy,
        ).grid(row=0, column=1, sticky="e")

        self.bind("<Escape>", lambda _e: self.destroy())

    # =========================================================================
    # Helpers UI
    # =========================================================================

    def _section(self, parent, row: int, title: str):
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", pady=(8, 2))

    def _linked_label(self, parent, row: int, *,
                        text: str, sub: str, url: str, link_label: str,
                        url2: str | None = None,
                        link_label2: str | None = None):
        """Bloc 'libellé principal + sous-titre + 1 ou 2 liens cliquables'."""
        frame = ctk.CTkFrame(parent, fg_color=("gray96", "gray18"),
                                corner_radius=6)
        frame.grid(row=row, column=0, sticky="ew", padx=2, pady=(0, 6))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text=text,
            font=ctk.CTkFont(size=12),
            anchor="w", justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))

        if sub:
            ctk.CTkLabel(
                frame, text=sub,
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "gray60"),
                anchor="w", justify="left",
            ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 2))

        links_row = ctk.CTkFrame(frame, fg_color="transparent")
        links_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 8))

        link = ctk.CTkLabel(
            links_row, text=f"→ {link_label}",
            font=ctk.CTkFont(size=11, underline=True),
            text_color=("#1f6feb", "#58a6ff"),
            cursor="hand2",
        )
        link.pack(side="left")
        link.bind("<Button-1>", lambda _e: self._safe_open(url))

        if url2 and link_label2:
            sep = ctk.CTkLabel(links_row, text="  ·  ",
                                 font=ctk.CTkFont(size=11),
                                 text_color=("gray50", "gray60"))
            sep.pack(side="left")
            link2 = ctk.CTkLabel(
                links_row, text=f"→ {link_label2}",
                font=ctk.CTkFont(size=11, underline=True),
                text_color=("#1f6feb", "#58a6ff"),
                cursor="hand2",
            )
            link2.pack(side="left")
            link2.bind("<Button-1>", lambda _e: self._safe_open(url2))

    def _safe_open(self, url: str):
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Ouverture impossible",
                                  f"Impossible d'ouvrir le lien :\n{e}",
                                  parent=self)

    def _find_icon(self) -> Path | None:
        """Cherche icon.ico (mode dev ou bundle PyInstaller)."""
        import sys
        try:
            if getattr(sys, "frozen", False):
                p = Path(sys._MEIPASS) / "icon.ico"  # type: ignore[attr-defined]
            else:
                p = Path(__file__).parent / "icon.ico"
            return p if p.is_file() else None
        except Exception:
            return None

    # =========================================================================
    # Vérification des mises à jour (GitHub Releases)
    # =========================================================================

    def _on_check_updates(self):
        """Vérifie sur GitHub Releases s'il existe une version plus récente.

        Interroge la LISTE des releases (pour inclure les pre-releases) et
        compare la plus récente avec ``__version__`` via une vraie comparaison
        de version (``version.is_newer``), pas une simple égalité de chaînes.
        """
        self.update_btn.configure(state="disabled", text="⏳  Vérification…")
        self.update_status.configure(text="")

        def _worker():
            try:
                import requests
                r = requests.get(GITHUB_RELEASES_API, timeout=8,
                                  params={"per_page": 20},
                                  headers={"Accept": "application/vnd.github+json"})
                if r.status_code == 404:
                    self.after(0, lambda: self._show_update_result(
                        "Dépôt ou releases introuvables (réseau / dépôt privé ?).",
                        is_error=False))
                    return
                r.raise_for_status()
                releases = r.json() or []
                # Ne garde que les releases publiées (pas les brouillons).
                # Les pre-releases SONT prises en compte (phase de test).
                candidates = [rel for rel in releases if not rel.get("draft")]
                if not candidates:
                    self.after(0, lambda: self._show_update_result(
                        "Aucune release publiée pour le moment.", is_error=False))
                    return
                # Release au tag de version le plus élevé.
                def _key(rel):
                    from version import parse_version
                    return parse_version(rel.get("tag_name") or "")
                latest = max(candidates, key=_key)
                latest_tag = latest.get("tag_name") or ""
                pre = "  (pre-release)" if latest.get("prerelease") else ""

                if is_newer(latest_tag, __version__):
                    url = latest.get("html_url") or GITHUB_RELEASES_PAGE
                    self.after(0, lambda: self._prompt_update(
                        latest_tag, pre, url))
                else:
                    self.after(0, lambda: self._show_update_result(
                        f"✓ Tu es à jour (version {__version__} ; "
                        f"dernière publiée : {latest_tag or '—'})",
                        is_error=False))
            except Exception as e:
                self.after(0, lambda: self._show_update_result(
                    f"Vérification impossible : {e}", is_error=True))

        threading.Thread(target=_worker, daemon=True).start()

    def _prompt_update(self, latest_tag: str, pre: str, url: str):
        """Propose (sur le thread UI) d'ouvrir la page de la nouvelle version."""
        msg = (f"✨  Nouvelle version disponible : {latest_tag}{pre}\n"
               f"     (tu utilises {__version__})\n\n"
               "Ouvrir la page de release pour télécharger ?")
        if messagebox.askyesno("Mise à jour disponible", msg, parent=self):
            self._safe_open(url)
        self._show_update_result(
            f"✨ Version {latest_tag} disponible", is_error=False)

    def _show_update_result(self, msg: str, *, is_error: bool):
        try:
            if not self.winfo_exists():
                return
            self.update_btn.configure(
                state="normal", text="🔄  Vérifier les mises à jour")
            self.update_status.configure(
                text=msg,
                text_color=("#cf222e", "#f85149") if is_error
                else ("gray35", "gray70"),
            )
        except Exception:
            pass
