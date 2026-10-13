"""Capture what's playing on this PC (WASAPI loopback) and stream it over UDP."""
import argparse
import socket
import struct
import sys
import time

import pyaudiowpatch as pyaudio

HEADER = struct.Struct("<IHI")  # sample_rate, channels, seq


def find_loopback(p):
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    for dev in p.get_loopback_device_info_generator():
        if default_out["name"] in dev["name"]:
            return dev
    raise RuntimeError(f"No loopback device found for '{default_out['name']}'")


def main():
    ap = argparse.ArgumentParser(description="Stream this PC's audio to a receiver.")
    ap.add_argument("receiver_ip")
    ap.add_argument("--port", type=int, default=50007)
    args = ap.parse_args()
    dest = (args.receiver_ip, args.port)

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

    print(f"Capturing: {dev['name']}")
    print(f"Format: {rate} Hz, {channels} ch -> {dest[0]}:{dest[1]}")
    print("Ctrl+C to stop.")
    try:
        while stream.is_active():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        sock.close()
        print("Stopped.")


if __name__ == "__main__":
    main()
