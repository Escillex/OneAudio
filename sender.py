"""Capture what's playing on this PC (WASAPI loopback) and stream it over UDP."""
import argparse
import ctypes
import ipaddress
import select
import signal
import socket
import struct
import sys
import threading
import time
import uuid
from ctypes import POINTER, byref, c_int, c_uint, c_void_p

import pyaudiowpatch as pyaudio
import pystray

import instance
import settings
import tray
import updater

HEADER = struct.Struct("<IHI")  # sample_rate, channels, seq
DISCOVER = b"ONEAUDIO:DISCOVER"
HERE = b"ONEAUDIO:HERE:"


class _GUID(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]

    def __init__(self, s):
        super().__init__()
        self.bytes[:] = uuid.UUID(s).bytes_le


def _com(obj, index, *argtypes):
    """Bind method #index of a COM object's vtable (raises OSError on failure HRESULTs)."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)(vtbl[index])


class EndpointMute:
    """Mute toggle for the default output device (IAudioEndpointVolume), via raw COM."""

    def __init__(self):
        ole32 = ctypes.OleDLL("ole32")
        try:
            ole32.CoInitializeEx(None, 0)
        except OSError:
            pass  # already initialized on this thread (by PortAudio)
        enum = c_void_p()
        ole32.CoCreateInstance(
            byref(_GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")), None, 1,  # MMDeviceEnumerator
            byref(_GUID("A95664D2-9614-4F35-A746-DE8DB63617E6")), byref(enum))
        dev = c_void_p()
        _com(enum, 4, c_int, c_int, POINTER(c_void_p))(enum, 0, 0, byref(dev))  # eRender, eConsole
        self.vol = c_void_p()
        _com(dev, 3, POINTER(_GUID), c_uint, c_void_p, POINTER(c_void_p))(
            dev, byref(_GUID("5CDF2C82-841E-4546-9722-0CF74078229A")), 23, None, byref(self.vol))
        _com(dev, 2)(dev)  # Release
        _com(enum, 2)(enum)

    def get(self):
        muted = c_int()
        _com(self.vol, 15, POINTER(c_int))(self.vol, byref(muted))
        return bool(muted.value)

    def set(self, muted):
        _com(self.vol, 14, c_int, c_void_p)(self.vol, int(muted), None)


def ipv4(text):
    """Full dotted-quad only: Windows would silently read '192.168.128' as 192.168.0.128."""
    try:
        return str(ipaddress.IPv4Address(text))
    except ipaddress.AddressValueError:
        raise argparse.ArgumentTypeError(
            f"'{text}' is not a valid IPv4 address (4 numbers 0-255, e.g. 192.168.1.42)")


def discover(port, timeout=1.0):
    """Broadcast a probe out of every local interface; return {ip: pc_name} of receivers.
    A receiver reachable via several interfaces is listed once (first reply wins)."""
    local_ips = {ai[4][0] for ai in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    socks = []
    for ip in local_ips:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            if hasattr(socket, "SIO_UDP_CONNRESET"):
                s.ioctl(socket.SIO_UDP_CONNRESET, False)
            # Binding to the interface makes Windows send the broadcast out of it.
            s.bind((ip, 0))
            s.sendto(DISCOVER, ("255.255.255.255", port))
            socks.append(s)
        except OSError:
            s.close()
    found, seen = {}, set()
    end = time.monotonic() + timeout
    while socks and (left := end - time.monotonic()) > 0:
        ready, _, _ = select.select(socks, [], [], left)
        for s in ready:
            try:
                data, addr = s.recvfrom(1024)
            except OSError:
                continue
            if not data.startswith(HERE):
                continue
            instance, _, name = data[len(HERE):].decode(errors="replace").partition(":")
            if instance in seen:
                continue
            seen.add(instance)
            found[addr[0]] = name + (" (this PC)" if addr[0] in local_ips else "")
    for s in socks:
        s.close()
    return found


class LocalMute:
    """The speaker mute this program applied, so turning it off restores exactly what was there."""

    def __init__(self):
        self.ep = None
        self.was = None  # mute state before we muted; None = we haven't

    @property
    def on(self):
        return self.was is not None

    def set(self, on):
        if on and self.was is None:
            self.ep = self.ep or EndpointMute()
            self.was = self.ep.get()
            self.ep.set(True)
        elif not on and self.was is not None:
            self.ep.set(self.was)
            self.was = None


def choose(found, remembered):
    """The remembered receiver if it's online, else the only one found. None means ask."""
    if remembered in found:
        return remembered
    if len(found) == 1:
        return next(iter(found))
    return None


def pick_receiver(port, remembered):
    print("Looking for receivers...")
    found = discover(port)
    if not found:
        print("No receivers found. Is oneaudio-receive running on the other PC (same network, same port)?")
        print("You can also pass its IP directly: oneaudio-send 192.168.1.42")
        sys.exit(1)
    if ip := choose(found, remembered):
        print(f"Found {found[ip]} ({ip})")
        return ip
    items = sorted(found.items())
    for i, (ip, name) in enumerate(items, 1):
        print(f"  {i}. {name} ({ip})")
    while True:
        choice = input(f"Pick a receiver [1-{len(items)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(items):
            return items[int(choice) - 1][0]


def find_loopback(p):
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    for dev in p.get_loopback_device_info_generator():
        if default_out["name"] in dev["name"]:
            return dev
    raise RuntimeError(f"No loopback device found for '{default_out['name']}'")


def main():
    ap = argparse.ArgumentParser(description="Stream this PC's audio to a receiver.")
    ap.add_argument("receiver_ip", type=ipv4, nargs="?",
                    help="receiver's IP; omit to reconnect to the last one or find receivers automatically")
    ap.add_argument("--port", type=int, default=50007)
    ap.add_argument("-m", "--mute", action="store_true",
                    help="mute this PC's speakers while streaming (restored on exit)")
    ap.add_argument("-d", "--detach", action="store_true",
                    help="run in the background with a tray icon instead of this console")
    ap.add_argument(tray.TRAY_FLAG, action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--update", action="store_true", help="install the latest release")
    ap.add_argument("--version", action="version", version=f"OneAudio {updater.VERSION or 'dev'}")
    args = ap.parse_args()
    if args.update:
        sys.exit(updater.update())
    fail = tray.error if args.tray else print
    if not instance.acquire("send"):
        fail(instance.message("send"))
        sys.exit(1)
    if args.detach and not args.tray:
        instance.release()  # the tray copy claims it
        tray.detach(([args.receiver_ip] if args.receiver_ip else [])
                    + ["--port", str(args.port)] + (["-m"] if args.mute else []))
        print("Sender running in the tray. Quit it from the tray icon.")
        return
    saved = settings.load()

    dest = None  # (ip, port), or None while the tray waits for a pick
    found = {}  # ip -> PC name, from the last scan
    if not args.tray:
        try:
            ip = args.receiver_ip or pick_receiver(args.port, saved.get("receiver"))
        except (KeyboardInterrupt, EOFError):
            sys.exit(1)
        settings.save(receiver=ip)
        dest = (ip, args.port)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Don't let ICMP "port unreachable" (receiver not running yet) break later sends.
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        sock.ioctl(socket.SIO_UDP_CONNRESET, False)

    p = pyaudio.PyAudio()
    try:
        dev = find_loopback(p)
    except Exception as e:
        fail(str(e))
        p.terminate()
        sys.exit(1)

    rate = int(dev["defaultSampleRate"])
    channels = dev["maxInputChannels"]
    seq = 0

    # Callback mode keeps the main thread free, so Ctrl+C works even while
    # loopback is silent (WASAPI delivers no data then).
    def callback(in_data, frame_count, time_info, status):
        nonlocal seq
        to = dest
        if to:
            try:
                sock.sendto(HEADER.pack(rate, channels, seq) + in_data, to)
            except OSError:
                pass  # network hiccup / receiver gone; keep going
        seq = (seq + 1) & 0xFFFFFFFF
        return (None, pyaudio.paContinue)

    stream = p.open(
        format=pyaudio.paInt16,
        channels=channels,
        rate=rate,
        input=True,
        input_device_index=dev["index"],
        frames_per_buffer=rate // 100,
        stream_callback=callback,
    )

    def on_close(*_):
        raise KeyboardInterrupt  # closing the window / Ctrl+Break: still clean up (unmute)

    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, on_close)

    mute = LocalMute()
    mute_error = None
    if args.mute or saved.get("mute"):
        try:
            mute.set(True)
        except OSError as e:
            mute_error = f"Couldn't mute speakers: {e}"

    stop = threading.Event()
    icon = None
    if args.tray:
        waiting = "Looking for receivers..."

        def refresh():
            if dest:
                label = f"{found[dest[0]]} ({dest[0]})" if dest[0] in found else dest[0]
                icon.set_status(f"Streaming to {label}{', muted here' if mute.on else ''}")
            else:
                icon.set_status(waiting)

        def connect(ip):
            nonlocal dest
            dest = (ip, args.port)
            settings.save(receiver=ip)
            refresh()

        def rescan():
            nonlocal found, waiting
            waiting = "Looking for receivers..."
            refresh()
            found = discover(args.port)
            if not dest and (ip := choose(found, saved.get("receiver"))):
                connect(ip)
                return
            waiting = ("Pick a receiver from the menu" if found
                       else "No receivers found. Rescan from the menu")
            refresh()

        def toggle_mute():
            try:
                mute.set(not mute.on)
            except OSError as e:
                icon.notify(f"Couldn't mute speakers: {e}")
                return
            settings.save(mute=mute.on)
            refresh()

        def receiver_item(ip, name):
            return pystray.MenuItem(f"{name} ({ip})", lambda: connect(ip),
                                    checked=lambda _: bool(dest) and dest[0] == ip, radio=True)

        def receiver_items():
            for ip, name in sorted(found.items()):
                yield receiver_item(ip, name)
            if found:
                yield pystray.Menu.SEPARATOR
            yield pystray.MenuItem("Rescan", lambda: threading.Thread(target=rescan, daemon=True).start())

        # Logoff/shutdown would otherwise leave the speakers muted, since mute persists.
        icon = tray.Tray("OneAudio sender", (47, 129, 247), "send", on_quit=stop.set,
                         on_logoff=lambda: mute.set(False), items=[
                             pystray.MenuItem("Receiver", pystray.Menu(receiver_items)),
                             pystray.MenuItem("Mute this PC", toggle_mute, checked=lambda _: mute.on),
                             pystray.Menu.SEPARATOR])
        icon.start()
        if args.receiver_ip:
            connect(args.receiver_ip)
        if mute_error:
            icon.notify(mute_error)
        threading.Thread(target=rescan, daemon=True).start()
    else:
        if mute_error:
            print(mute_error)
        print(f"Capturing: {dev['name']}{' (muted locally)' if mute.on else ''}")
        print(f"Format: {rate} Hz, {channels} ch -> {dest[0]}:{dest[1]}")
        print("Ctrl+C to stop.")
        updater.check_in_background()
    try:
        while stream.is_active() and not stop.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        mute.set(False)
        stream.stop_stream()
        stream.close()
        p.terminate()
        sock.close()
        if icon:
            icon.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()
