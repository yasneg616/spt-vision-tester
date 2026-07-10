"""Bounded local SPT offline visual test helper."""

import ctypes
import os


if os.name == "nt":
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass


__version__ = "0.3.0"
