"""Tray mode (-d): run in the background without a console, controlled from a tray icon."""
import ctypes
import os
import subprocess
import sys
import threading

import pystray
from PIL import Image, ImageDraw

import updater

WM_QUERYENDSESSION = 0x11
WM_ENDSESSION = 0x16
TRAY_FLAG = "--tray"  # internal: set on the detached copy


def detach(args):
    """Start a console-less copy of this program in tray mode, then return to the shell."""
    cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, sys.argv[0]]
    # Onefile exes: make the copy unpack its own files instead of sharing ours,
    # which are deleted when this process exits.
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen(
        cmd + [*args, TRAY_FLAG], env=env, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def error(message):
    """There's no console in tray mode, so fatal errors get a message box."""
    ctypes.windll.user32.MessageBoxW(None, message, "OneAudio", 0x10)  # MB_ICONERROR


def _image(color):
    """A speaker with sound waves."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(6, 24), (18, 24), (32, 10), (32, 54), (18, 40), (6, 40)], fill=color)
    for r in (12, 22):
        d.arc((32 - r, 32 - r, 32 + r, 32 + r), -45, 45, fill=color, width=5)
    return img


class Tray:
    """Tray icon: status line, the caller's items, Install update (when there is one), Quit.
    Runs its own message loop on a background thread so the main thread stays free for
    audio (WASAPI wants streams opened there)."""

    def __init__(self, name, color, role, on_quit, on_logoff=None, items=()):
        self.name = name
        self.role = role
        self.on_quit = on_quit
        self.status = ""
        self.update_tag = None
        self.icon = pystray.Icon("oneaudio", _image(color), name, pystray.Menu(
            pystray.MenuItem(lambda _: self.status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            *items,
            pystray.MenuItem(lambda _: f"Install update ({self.update_tag})", self._install,
                             visible=lambda _: bool(self.update_tag)),
            pystray.MenuItem("Quit", lambda: on_quit())))
        # Unhandled messages return 0, which for WM_QUERYENDSESSION would block shutdown.
        self.icon._message_handlers[WM_QUERYENDSESSION] = lambda w, l: 1
        if on_logoff:
            # The process is killed right after this returns: clean up synchronously.
            self.icon._message_handlers[WM_ENDSESSION] = lambda w, l: w and on_logoff()

    def start(self):
        self.icon.run_detached()
        updater.check_in_background(self._offer_update)

    def _offer_update(self, tag):
        self.update_tag = tag
        self.icon.update_menu()
        self.notify(f"Update {tag} is available. Right-click the tray icon to install it.")

    def _install(self):
        def run():
            # The installer reopens us in the tray afterwards; quit so it can replace our files.
            if updater.update(out=self.notify, relaunch=self.role) == 0:
                self.on_quit()
        threading.Thread(target=run, daemon=True).start()

    def set_status(self, text):
        self.status = text
        self.icon.title = f"{self.name}: {text}"[:127]  # Windows tooltip limit
        self.icon.update_menu()

    def notify(self, text):
        try:
            self.icon.notify(text, self.name)
        except Exception:
            pass

    def stop(self):
        self.icon.stop()
