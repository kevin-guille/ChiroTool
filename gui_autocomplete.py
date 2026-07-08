"""
gui_autocomplete.py — champ de saisie avec autocomplétion (CustomTkinter).

``AutocompleteEntry`` est un ``CTkEntry`` qui affiche, à la frappe, une petite
liste de suggestions fournie par ``suggest_fn(query) -> list[(valeur, libellé)]``.
La sélection insère la **valeur** (le code). Navigation clavier ↓/Entrée/Échap,
clic pour choisir. Défensif : si ``suggest_fn`` renvoie vide, se comporte comme un
champ libre normal (aucune popup).
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


class AutocompleteEntry(ctk.CTkEntry):
    def __init__(self, master, *, suggest_fn, on_pick=None, max_items: int = 10, **kw):
        super().__init__(master, **kw)
        self._suggest_fn = suggest_fn
        self._on_pick = on_pick
        self._max = max_items
        self._popup: tk.Toplevel | None = None
        self._list: tk.Listbox | None = None
        self._values: list[str] = []
        self._close_after = None      # id du after de fermeture différée (grâce clic)
        self.bind("<KeyRelease>", self._on_key, add="+")
        self.bind("<FocusOut>", self._on_focus_out, add="+")
        self.bind("<Down>", self._to_list, add="+")
        self.bind("<Escape>", lambda e: self._close(), add="+")

    def _on_focus_out(self, event):
        # Fermeture différée : laisse passer un clic sur la liste. Le passage
        # VOLONTAIRE du focus vers la liste (touche ↓) annule ce timer (_to_list).
        self._close_after = self.after(150, self._close)

    # -- frappe -------------------------------------------------------------

    _NAV = {"Up", "Down", "Return", "Escape", "Tab", "Left", "Right",
            "Shift_L", "Shift_R", "Control_L", "Control_R"}

    def _on_key(self, event):
        if event.keysym in self._NAV:
            return
        query = self.get().strip()
        try:
            items = list(self._suggest_fn(query) or [])[:self._max]
        except Exception:
            items = []
        if not items:
            self._close()
            return
        self._show(items)

    def _show(self, items):
        if self._popup is None or not self._popup.winfo_exists():
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            try:
                self._popup.attributes("-topmost", True)
            except tk.TclError:
                pass
            self._list = tk.Listbox(
                self._popup, activestyle="dotbox", highlightthickness=1,
                bd=0, font=("Segoe UI", 10), exportselection=False)
            self._list.pack(fill="both", expand=True)
            self._list.bind("<ButtonRelease-1>", lambda e: self._pick())
            self._list.bind("<Return>", lambda e: self._pick())
            self._list.bind("<Escape>", lambda e: (self._close(), self.focus_set()))
        self._list.delete(0, "end")
        self._values = []
        for code, label in items:
            self._list.insert("end", f"{code}   —   {label}" if label else code)
            self._values.append(code)
        self._list.configure(height=min(len(items), self._max))
        try:
            x = self.winfo_rootx()
            y = self.winfo_rooty() + self.winfo_height()
            w = max(self.winfo_width(), 280)
            self._popup.wm_geometry(f"{w}x{self._list.winfo_reqheight()}+{x}+{y}")
        except tk.TclError:
            pass

    def _to_list(self, event):
        if self._list is not None and self._popup and self._popup.winfo_exists():
            # annule la fermeture différée : on garde la popup pour naviguer
            if self._close_after is not None:
                try:
                    self.after_cancel(self._close_after)
                except (tk.TclError, ValueError):
                    pass
                self._close_after = None
            self._list.focus_set()
            self._list.selection_clear(0, "end")
            self._list.selection_set(0)
            self._list.activate(0)
            return "break"

    def _pick(self):
        if self._list is None:
            return
        sel = self._list.curselection()
        if not sel:
            return
        code = self._values[sel[0]]
        self.delete(0, "end")
        self.insert(0, code)
        self._close()
        self.focus_set()
        if self._on_pick:
            try:
                self._on_pick(code)
            except Exception:
                pass

    def _close(self):
        self._close_after = None
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None
            self._list = None
