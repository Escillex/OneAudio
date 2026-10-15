"""One sender and one receiver at a time per user, whether run from a console or the tray."""
import ctypes

ERROR_ALREADY_EXISTS = 183
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.restype = ctypes.c_void_p
_handle = None


def acquire(role):
    """Claim the role ("send" / "receive"). False if another copy holds it.
    The claim lasts until release() or process exit."""
    global _handle
    h = _k32.CreateMutexW(None, False, f"Local\\OneAudio-{role}")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _k32.CloseHandle(ctypes.c_void_p(h))
        return False
    _handle = h
    return True


def release():
    global _handle
    if _handle:
        _k32.CloseHandle(ctypes.c_void_p(_handle))
        _handle = None


def message(role):
    what = "sender" if role == "send" else "receiver"
    return (f"OneAudio {what} is already running. "
            f"Quit it from its tray icon (or press Ctrl+C in its terminal) first.")
