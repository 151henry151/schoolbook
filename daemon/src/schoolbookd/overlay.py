# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Always-on-top close button so a child can leave a fullscreen app."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable

CLOSE_SIZE = 72
CLOSE_MARGIN = 16


def close_button_geometry(screen_w: int, screen_h: int) -> tuple[int, int, int, int]:
    del screen_h
    return (screen_w - CLOSE_SIZE - CLOSE_MARGIN, CLOSE_MARGIN, CLOSE_SIZE, CLOSE_SIZE)


def show_close_overlay(on_close: Callable[[], None]) -> Callable[[], None]:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return lambda: None
    hidden = threading.Event()
    ready = threading.Event()
    holder: dict[str, object] = {}

    def run() -> None:
        try:
            import tkinter as tk
        except ImportError:
            ready.set()
            return
        try:
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.configure(bg="#d12c2c")
            left, top, width, height = close_button_geometry(
                root.winfo_screenwidth(), root.winfo_screenheight()
            )
            root.geometry(f"{width}x{height}+{left}+{top}")
            canvas = tk.Canvas(
                root, width=width, height=height, highlightthickness=0, bg="#d12c2c"
            )
            canvas.pack(fill="both", expand=True)
            canvas.create_oval(1, 1, width - 2, height - 2, fill="#d12c2c", outline="#d12c2c")
            pad = 20
            canvas.create_line(pad, pad, width - pad, height - pad, fill="#ffffff", width=6)
            canvas.create_line(width - pad, pad, pad, height - pad, fill="#ffffff", width=6)

            def clicked(_event: object = None) -> None:
                if hidden.is_set():
                    return
                hidden.set()
                root.destroy()
                on_close()

            canvas.bind("<Button-1>", clicked)
            root.bind("<Button-1>", clicked)
            holder["root"] = root

            def lift() -> None:
                if hidden.is_set():
                    return
                root.lift()
                root.attributes("-topmost", True)
                root.after(250, lift)

            lift()
            ready.set()
            root.mainloop()
        except Exception:
            ready.set()

    thread = threading.Thread(target=run, daemon=True, name="schoolbook-close")
    thread.start()
    ready.wait(timeout=2)

    def hide() -> None:
        if hidden.is_set():
            return
        hidden.set()
        root = holder.get("root")
        if root is None:
            return
        try:
            root.after(0, root.destroy)
        except Exception:
            return

    return hide
