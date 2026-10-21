# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""A separate close-button process works even when the daemon Python lacks Tk."""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

CLOSE_SIZE = 72
CLOSE_MARGIN = 16


def close_button_geometry(screen_w: int, screen_h: int) -> tuple[int, int, int, int]:
    # Keep GCompris' top-right repeat-letter speaker and bottom-left controls usable.
    return (screen_w - CLOSE_SIZE - CLOSE_MARGIN, screen_h - CLOSE_SIZE - CLOSE_MARGIN,
            CLOSE_SIZE, CLOSE_SIZE)


def show_close_overlay(on_close: Callable[[], None]) -> Callable[[], None]:
    if not os.environ.get('DISPLAY'):
        return lambda: None
    try:
        process = subprocess.Popen(['/usr/bin/python3', str(Path(__file__).resolve())],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return lambda: None
    hidden = threading.Event()

    def wait() -> None:
        if process.wait() == 0 and not hidden.is_set():
            hidden.set()
            on_close()

    threading.Thread(target=wait, daemon=True, name='schoolbook-close').start()

    def hide() -> None:
        hidden.set()
        if process.poll() is None:
            process.terminate()

    return hide


def main() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.configure(bg='#d12c2c')
    left, top, width, height = close_button_geometry(root.winfo_screenwidth(), root.winfo_screenheight())
    root.geometry(f'{width}x{height}+{left}+{top}')
    canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0, bg='#d12c2c')
    canvas.pack(fill='both', expand=True)
    pad = 20
    canvas.create_line(pad, pad, width-pad, height-pad, fill='#ffffff', width=6)
    canvas.create_line(width-pad, pad, pad, height-pad, fill='#ffffff', width=6)
    canvas.bind('<Button-1>', lambda _event: root.destroy())

    def lift() -> None:
        # Also close if the daemon has died or the kiosk was restarted with F11.
        if os.getppid() == 1:
            root.destroy()
            return
        root.lift()
        root.attributes('-topmost', True)
        root.after(500, lift)

    lift()
    root.mainloop()


if __name__ == '__main__':
    main()
