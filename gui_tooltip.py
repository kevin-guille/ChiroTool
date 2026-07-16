"""
gui_tooltip.py — infobulle légère au survol pour ``ttk.Treeview``.

``ttk.Treeview`` n'a pas d'infobulle native. ``TreeCellTooltip`` en attache une :
au survol d'une cellule, un ``resolver(row_id, col_name) -> str | None`` fournit
le texte à afficher (None = pas d'infobulle sur cette cellule). Rendu discret,
texte clair sur fond sombre, avec un léger délai anti-clignotement.

Usage :
    TreeCellTooltip(tree, resolver)   # se branche tout seul (binds add="+")
"""

from __future__ import annotations

import tkinter as tk


class TreeCellTooltip:
    """Infobulle par cellule pour un ``ttk.Treeview``.

    ``resolver(row_id, col_name)`` : ``col_name`` vaut ``"#0"`` pour la colonne
    d'arbre (gouttière), sinon le nom logique de la colonne de données. Retourne
    le texte à afficher, ou None.
    """

    def __init__(self, tree, resolver, *, delay: int = 350):
        self.tree = tree
        self.resolver = resolver
        self.delay = delay
        self._tip: tk.Toplevel | None = None
        self._after = None
        self._cell = None            # (row_id, colid) courant, pour éviter le re-render
        # add="+" : ne pas écraser les binds existants (double-clic, clic droit…)
        tree.bind("<Motion>", self._on_motion, add="+")
        tree.bind("<Leave>", lambda e: self._reset(), add="+")
        tree.bind("<Button-1>", lambda e: self._reset(), add="+")

    # -- conversion colonne -------------------------------------------------

    def _col_name(self, colid: str) -> str:
        if colid == "#0" or not colid:
            return colid or ""
        try:
            idx = int(colid[1:]) - 1          # "#3" -> 2 (colonnes affichées = ordre)
        except (ValueError, IndexError):
            return colid
        cols = self.tree["columns"]
        return cols[idx] if 0 <= idx < len(cols) else colid

    # -- évènements ---------------------------------------------------------

    def _on_motion(self, event):
        row = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        cell = (row, colid)
        if cell == self._cell:
            return
        self._cell = cell
        self._cancel()
        self._hide()
        if not row:
            return
        try:
            text = self.resolver(row, self._col_name(colid))
        except Exception:
            text = None
        if text:
            x, y = event.x_root, event.y_root
            self._after = self.tree.after(self.delay, lambda: self._show(text, x, y))

    def _show(self, text: str, x: int, y: int):
        self._hide()
        tip = tk.Toplevel(self.tree)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        # Fond sombre subtil + fine bordure, texte clair.
        frame = tk.Frame(tip, background="#1f1f1f",
                         highlightbackground="#3a3a3a", highlightthickness=1)
        frame.pack()
        tk.Label(frame, text=text, background="#1f1f1f", foreground="#f2f2f2",
                 font=("Segoe UI", 9), padx=8, pady=4, justify="left").pack()
        tip.wm_geometry(f"+{x + 14}+{y + 18}")
        self._tip = tip

    def _hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    def _cancel(self):
        if self._after is not None:
            try:
                self.tree.after_cancel(self._after)
            except (tk.TclError, ValueError):
                pass
            self._after = None

    def _reset(self):
        self._cell = None
        self._cancel()
        self._hide()
