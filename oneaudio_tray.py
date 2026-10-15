"""oneaudio-tray.exe: windowed (no console) launcher used by the Start menu shortcuts.
Usage: oneaudio-tray send|receive [options of that command]"""
import sys

import tray


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    if role not in ("send", "receive"):
        tray.error("Usage: oneaudio-tray send|receive")
        return
    sys.argv = [sys.argv[0], *sys.argv[2:], tray.TRAY_FLAG]
    if role == "send":
        import sender
        sender.main()
    else:
        import receiver
        receiver.main()


if __name__ == "__main__":
    main()
