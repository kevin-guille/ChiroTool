"""
gui_windowing.py : restauration des fenêtres transientes après
« Afficher le bureau ».

Sous Windows, le bouton en bas à droite (ou Win+D) masque les Toplevel
``transient`` + ``grab_set``. Elles n'ont pas d'icône dans la barre des
tâches : recliquer ChiroTool restaure la fenêtre principale, mais le grab
reste sur la modale invisible. L'UI paraît figée, il faut tuer le process.

Ce module :
  - marque les modales (``_chiro_modal``) ;
  - sous Windows, leur donne une icône dans la barre des tâches ;
  - au ``<Map>`` / ``<FocusIn>`` de la fenêtre principale, réaffiche et
    reprend le grab sur la dernière modale encore ouverte ;
  - tant qu'une modale existe, vérifie périodiquement qu'elle n'est pas
    restée masquée alors que la fenêtre principale est déjà visible.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

_WATCH_MS = 400
_TOPMOST_MS = 250


def find_ancestor_with(widget: Any, attr: str) -> Any | None:
    """Remonte ``master`` jusqu'au widget qui porte ``attr`` (valeur non None).

    Un ``Toplevel`` a ``winfo_toplevel()`` égal à lui-même. Le wizard
    métadonnées ne doit pas s'en servir pour trouver la carte de l'application.
    """
    w = getattr(widget, "master", None)
    seen: set[int] = set()
    while w is not None and id(w) not in seen:
        seen.add(id(w))
        if getattr(w, attr, None) is not None:
            return w
        w = getattr(w, "master", None)
    return None
_DEBOUNCE_MS = 50


def _overrideredirect_on(w: Any) -> bool:
    """True si la fenêtre n'a pas de barre de titre (tooltip, popup carte)."""
    for attr in ("overrideredirect", "wm_overrideredirect"):
        fn = getattr(w, attr, None)
        if not callable(fn):
            continue
        try:
            val = fn()
        except TypeError:
            continue
        except Exception:
            continue
        if val:
            return True
    return False


def _looks_like_toplevel(w: Any) -> bool:
    name = type(w).__name__
    if "Toplevel" in name:
        return True
    return bool(getattr(w, "_chiro_modal", False))


def _window_state(w: Any) -> str:
    try:
        if callable(getattr(w, "state", None)):
            return str(w.state())
    except Exception:
        pass
    return "normal"


def _is_viewable(w: Any) -> bool:
    fn = getattr(w, "winfo_viewable", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            return False
    return _window_state(w) == "normal"


def iter_toplevels(root: Any) -> list[Any]:
    """Tous les Toplevel descendants (y compris imbriqués)."""
    out: list[Any] = []

    def walk(w: Any) -> None:
        try:
            children = list(w.winfo_children())
        except Exception:
            return
        for c in children:
            if _looks_like_toplevel(c):
                out.append(c)
            walk(c)

    walk(root)
    return out


def restore_transient_windows(root: Any) -> int:
    """Déiconifie / ramène au premier plan les Toplevels encore ouverts.

    Ignore les fenêtres ``withdrawn`` (fermées volontairement) et les
    ``overrideredirect`` (tooltips). Reprend le grab sur la dernière modale.
    Retourne le nombre de fenêtres ramenées.
    """
    restored = 0
    last_modal = None
    for w in iter_toplevels(root):
        try:
            if not w.winfo_exists():
                continue
            if _overrideredirect_on(w):
                continue
            if _window_state(w) == "withdrawn":
                continue
            w.deiconify()
            w.lift()
            restored += 1
            if getattr(w, "_chiro_modal", False):
                last_modal = w
        except Exception:
            continue
    if last_modal is not None:
        try:
            last_modal.lift()
            last_modal.grab_set()
            last_modal.focus_force()
        except Exception:
            pass
        try:
            last_modal.attributes("-topmost", True)
            last_modal.after(
                _TOPMOST_MS,
                lambda m=last_modal: _clear_topmost(m),
            )
        except Exception:
            pass
    return restored


def _clear_topmost(w: Any) -> None:
    try:
        if w.winfo_exists():
            w.attributes("-topmost", False)
    except Exception:
        pass


def watch_hidden_modals(root: Any) -> bool:
    """Restaure si la fenêtre principale est visible et une modale masquée.

    Retourne True si une restauration a eu lieu.
    """
    try:
        if not _is_viewable(root):
            return False
    except Exception:
        return False
    for w in iter_toplevels(root):
        try:
            if not getattr(w, "_chiro_modal", False):
                continue
            if not w.winfo_exists():
                continue
            if _overrideredirect_on(w):
                continue
            if _window_state(w) == "withdrawn":
                continue
            if not _is_viewable(w):
                restore_transient_windows(root)
                return True
        except Exception:
            continue
    return False


def _live_modals(root: Any) -> bool:
    for w in iter_toplevels(root):
        try:
            if not getattr(w, "_chiro_modal", False):
                continue
            if not w.winfo_exists():
                continue
            if _window_state(w) == "withdrawn":
                continue
            return True
        except Exception:
            continue
    return False


def _start_modal_watch(root: Any) -> None:
    """Poll léger tant qu'une modale est ouverte (filet si ``<Map>`` ne part pas)."""
    if getattr(root, "_chiro_modal_watch", False):
        return
    after = getattr(root, "after", None)
    if not callable(after):
        return
    root._chiro_modal_watch = True

    def _tick() -> None:
        try:
            alive = _live_modals(root)
        except Exception:
            alive = False
        if not alive:
            root._chiro_modal_watch = False
            return
        try:
            watch_hidden_modals(root)
        except Exception:
            pass
        try:
            after(_WATCH_MS, _tick)
        except Exception:
            root._chiro_modal_watch = False

    try:
        after(_WATCH_MS, _tick)
    except Exception:
        root._chiro_modal_watch = False


def _hwnd_toplevel(widget: Any) -> int:
    """HWND de la fenêtre décorée (pas le client Tk). 0 si indisponible."""
    hwnd = 0
    wm_frame = getattr(widget, "wm_frame", None)
    if callable(wm_frame):
        try:
            frame = wm_frame()
            if frame:
                hwnd = int(str(frame), 16)
        except Exception:
            hwnd = 0
    if hwnd:
        return hwnd
    wid = getattr(widget, "winfo_id", None)
    if not callable(wid):
        return 0
    try:
        hwnd = int(wid())
    except Exception:
        return 0
    if sys.platform != "win32" or not hwnd:
        return hwnd
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        get_parent = user32.GetParent
        get_parent.restype = wintypes.HWND
        get_parent.argtypes = [wintypes.HWND]
        get_long, _set_long = _win_get_set_long(user32)
        gwl_style = -16
        ws_child = 0x40000000
        cur = hwnd
        for _ in range(8):
            style = int(get_long(cur, gwl_style) or 0)
            if not (style & ws_child):
                return int(cur)
            parent = get_parent(cur)
            if not parent:
                return int(cur)
            cur = int(parent)
        return int(cur)
    except Exception:
        return hwnd


def _win_get_set_long(user32: Any) -> tuple[Callable, Callable]:
    import ctypes
    from ctypes import wintypes

    if ctypes.sizeof(ctypes.c_void_p) == 8:
        get_long = user32.GetWindowLongPtrW
        set_long = user32.SetWindowLongPtrW
        get_long.restype = ctypes.c_ssize_t
        set_long.restype = ctypes.c_ssize_t
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        return get_long, set_long
    get_long = user32.GetWindowLongW
    set_long = user32.SetWindowLongW
    get_long.restype = ctypes.c_long
    set_long.restype = ctypes.c_long
    get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    return get_long, set_long


def promote_to_taskbar(widget: Any) -> bool:
    """Force une icône barre des tâches pour une fenêtre owned/transient.

    Sans cela, Win+D masque la modale et elle n'apparaît nulle part.
    No-op hors Windows. Retourne True si le style a été posé.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = _hwnd_toplevel(widget)
        if not hwnd:
            return False
        user32 = ctypes.windll.user32
        get_long, set_long = _win_get_set_long(user32)
        gwl_exstyle = -20
        ws_ex_appwindow = 0x00040000
        ws_ex_toolwindow = 0x00000080
        ex = int(get_long(hwnd, gwl_exstyle) or 0)
        new_ex = (ex | ws_ex_appwindow) & ~ws_ex_toolwindow
        if new_ex != ex:
            set_long(hwnd, gwl_exstyle, new_ex)
        set_pos = user32.SetWindowPos
        set_pos.restype = wintypes.BOOL
        set_pos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.UINT,
        ]
        swp_nosize = 0x0001
        swp_nomove = 0x0002
        swp_nozorder = 0x0004
        swp_noactivate = 0x0010
        swp_framechanged = 0x0020
        set_pos(
            hwnd, 0, 0, 0, 0, 0,
            swp_nosize | swp_nomove | swp_nozorder | swp_noactivate | swp_framechanged,
        )
        return True
    except Exception:
        return False


def install_show_desktop_restore(root: Any) -> None:
    """Installe le hook une seule fois sur la fenêtre principale."""
    if getattr(root, "_chiro_show_desktop_hooked", False):
        return
    root._chiro_show_desktop_hooked = True
    pending: dict[str, Any] = {"id": None}

    def _run() -> None:
        pending["id"] = None
        restore_transient_windows(root)

    def _schedule(event=None) -> None:
        if event is not None and getattr(event, "widget", None) is not root:
            return
        cancel: Callable | None = getattr(root, "after_cancel", None)
        after: Callable | None = getattr(root, "after", None)
        if pending["id"] is not None and callable(cancel):
            try:
                cancel(pending["id"])
            except Exception:
                pass
        if callable(after):
            try:
                pending["id"] = after(_DEBOUNCE_MS, _run)
                return
            except Exception:
                pass
        _run()

    bind = getattr(root, "bind", None)
    if not callable(bind):
        return
    bind("<Map>", _schedule, add="+")
    bind("<FocusIn>", _schedule, add="+")


def bind_modal(dialog: Any, master: Any, *, grab_delay_ms: int = 50) -> None:
    """``transient`` + ``grab_set`` avec restauration après Afficher le bureau."""
    dialog._chiro_modal = True
    try:
        dialog.transient(master)
    except Exception:
        pass

    def _post_map() -> None:
        try:
            upd = getattr(dialog, "update_idletasks", None)
            if callable(upd):
                upd()
        except Exception:
            pass
        grab = getattr(dialog, "grab_set", None)
        if callable(grab):
            try:
                grab()
            except Exception:
                pass
        promote_to_taskbar(dialog)

    delay = max(0, int(grab_delay_ms))
    after = getattr(dialog, "after", None)
    if callable(after) and delay:
        try:
            after(delay, _post_map)
        except Exception:
            _post_map()
    else:
        _post_map()

    root = master
    wtl = getattr(master, "winfo_toplevel", None)
    if callable(wtl):
        try:
            root = wtl()
        except Exception:
            root = master
    install_show_desktop_restore(root)
    _start_modal_watch(root)
