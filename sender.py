"""Capture what's playing on this PC (WASAPI loopback) and stream it over UDP."""
import argparse
import ctypes
import ipaddress
import select
import signal
import socket
import struct
import sys
import time
import uuid
from ctypes import POINTER, byref, c_int, c_uint, c_void_p

import pyaudiowpatch as pyaudio

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


def pick_receiver(port):
    print("Looking for receivers...")
    found = discover(port)
    if not found:
        print("No receivers found. Is oneaudio-receive running on the other PC (same network, same port)?")
        print("You can also pass its IP directly: oneaudio-send 192.168.1.42")
        sys.exit(1)
    items = sorted(found.items())
    if len(items) == 1:
        ip, name = items[0]
        print(f"Found {name} ({ip})")
        return ip
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
                    help="receiver's IP; omit to find receivers on the network automatically")
    ap.add_argument("--port", type=int, default=50007)
    ap.add_argument("-m", "--mute", action="store_true",
                    help="mute this PC's speakers while streaming (restored on exit)")
    ap.add_argument("--update", action="store_true", help="install the latest release")
    ap.add_argument("--version", action="version", version=f"OneAudio {updater.VERSION or 'dev'}")
    args = ap.parse_args()
    if args.update:
        sys.exit(updater.update())
    try:
        receiver_ip = args.receiver_ip or pick_receiver(args.port)
    except (KeyboardInterrupt, EOFError):
        sys.exit(1)
    updater.check_in_background()
    dest = (receiver_ip, args.port)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Don't let ICMP "port unreachable" (receiver not running yet) break later sends.
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        sock.ioctl(socket.SIO_UDP_CONNRESET, False)

    p = pyaudio.PyAudio()
    try:
        dev = find_loopback(p)
    except Exception as e:
        print(e)
        p.terminate()
        sys.exit(1)

    rate = int(dev["defaultSampleRate"])
    channels = dev["maxInputChannels"]
    seq = 0

    # Callback mode keeps the main thread free, so Ctrl+C works even while
    # loopback is silent (WASAPI delivers no data then).
    def callback(in_data, frame_count, time_info, status):
        nonlocal seq
        try:
            sock.sendto(HEADER.pack(rate, channels, seq) + in_data, dest)
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

    mute = None
    if args.mute:
        try:
            mute = EndpointMute()
            was_muted = mute.get()
            mute.set(True)
        except OSError as e:
            mute = None
            print(f"Couldn't mute speakers: {e}")

    print(f"Capturing: {dev['name']}{' (muted locally)' if mute else ''}")
    print(f"Format: {rate} Hz, {channels} ch -> {dest[0]}:{dest[1]}")
    print("Ctrl+C to stop.")
    try:
        while stream.is_active():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if mute:
            mute.set(was_muted)
        stream.stop_stream()
        stream.close()
        p.terminate()
        sock.close()
        print("Stopped.")


if __name__ == "__main__":
    main()
