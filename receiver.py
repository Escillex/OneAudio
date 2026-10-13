"""Receive audio from sender.py over UDP and play it on the default speaker."""
import argparse
import queue
import socket
import struct
import threading
import time
import uuid
from array import array

import pyaudiowpatch as pyaudio

import updater

HEADER = struct.Struct("<IHI")  # sample_rate, channels, seq
# Discovery (see sender.discover): broadcast probe in, "here" + PC name back.
DISCOVER = b"ONEAUDIO:DISCOVER"
HERE = b"ONEAUDIO:HERE:"
INSTANCE = uuid.uuid4().hex[:8]  # lets the sender dedupe replies arriving via several interfaces
RESET_GAP = 50  # seq jumping back more than this = sender restarted


class Converter:
    """Channel remap + linear resample, used only if the speaker can't take the
    sender's format directly (e.g. 48 kHz -> 44.1 kHz, or 7.1 -> stereo)."""

    def __init__(self, src_rate, src_ch, dst_rate, dst_ch):
        self.src_ch, self.dst_ch = src_ch, dst_ch
        self.step = src_rate / dst_rate
        self.resample = src_rate != dst_rate
        self.pos = 1.0  # read position; index 0 is the previous chunk's last frame
        self.prev = [0] * dst_ch

    def __call__(self, data):
        a = array("h", data)
        # One list per output channel (extra source channels dropped, missing ones repeated).
        chans = [a[c % self.src_ch :: self.src_ch] for c in range(self.dst_ch)]
        if self.resample:
            n = len(chans[0]) + 1
            idx, t = [], self.pos
            while t < n - 1:
                idx.append(t)
                t += self.step
            self.pos = t - (n - 1)
            new = []
            for c, ch in enumerate(chans):
                x = [self.prev[c]] + ch.tolist()
                self.prev[c] = x[-1]
                out = []
                for t in idx:
                    i = int(t)
                    out.append(int(x[i] + (x[i + 1] - x[i]) * (t - i)))
                new.append(out)
            chans = new
        frames = len(chans[0])
        out = array("h", bytes(frames * self.dst_ch * 2))
        for c, ch in enumerate(chans):
            out[c :: self.dst_ch] = ch if isinstance(ch, array) else array("h", ch)
        return out.tobytes()


class Player:
    def __init__(self, p, buffer_ms):
        self.p = p
        self.target = max(1, buffer_ms // 10)  # packets are ~10 ms each
        self.max_len = self.target * 3
        self.q = queue.Queue()
        self.stream = None
        self.fmt = None  # (rate, channels) the stream is open for
        self.wanted = None  # format requested by the receive thread
        self.convert = None
        self.frame_bytes = 4
        self.leftover = b""
        self.buffering = True

    def _callback(self, in_data, frame_count, time_info, status):
        need = frame_count * self.frame_bytes
        if self.buffering:
            if self.q.qsize() < self.target:
                return (bytes(need), pyaudio.paContinue)
            self.buffering = False
        buf = self.leftover
        while len(buf) < need:
            try:
                buf += self.q.get_nowait()
            except queue.Empty:
                # Underrun: pad with silence and wait for the buffer to refill.
                buf += bytes(need - len(buf))
                self.buffering = True
                break
        self.leftover = buf[need:]
        return (buf[:need], pyaudio.paContinue)

    def _try_open(self, dev, rate, channels):
        return self.p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            output=True,
            output_device_index=dev["index"],
            frames_per_buffer=rate // 100,
            stream_callback=self._callback,
        )

    def open(self, rate, channels):
        self.close()
        wasapi = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
        dev = self.p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        out_rate, out_ch = rate, channels
        try:
            self.stream = self._try_open(dev, rate, channels)
            self.convert = None
        except OSError:
            # Speaker doesn't accept this format in shared mode; use its own and convert.
            out_rate = int(dev["defaultSampleRate"])
            out_ch = min(channels, dev["maxOutputChannels"]) or 2
            self.convert = Converter(rate, channels, out_rate, out_ch)
            self.stream = self._try_open(dev, out_rate, out_ch)
        self.frame_bytes = out_ch * 2
        self.fmt = (rate, channels)
        print(f"Output: {dev['name']} ({out_rate} Hz, {out_ch} ch"
              f"{', converting' if self.convert else ''})")

    def flush(self):
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self.buffering = True

    def push(self, payload):
        if self.convert:
            payload = self.convert(payload)
        self.q.put(payload)
        # Keep latency from creeping up: drop the oldest packets.
        while self.q.qsize() > self.max_len:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

    def close(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        self.flush()
        self.leftover = b""


def receive_loop(sock, player, stop):
    last_seq = None
    source = None
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            continue
        if data == DISCOVER:
            try:
                sock.sendto(HERE + f"{INSTANCE}:{socket.gethostname()}".encode(), addr)
            except OSError:
                pass
            continue
        if len(data) <= HEADER.size:
            continue
        rate, channels, seq = HEADER.unpack_from(data)
        payload = data[HEADER.size:]
        if not rate or not channels or len(payload) % (channels * 2):
            continue

        new_source = addr[0] != source
        restarted = last_seq is not None and seq <= last_seq and last_seq - seq > RESET_GAP
        if (rate, channels) != player.fmt:
            # WASAPI streams must be opened on the main thread; ask it and wait.
            player.wanted = (rate, channels)
            source = last_seq = None
            continue
        if new_source or restarted:
            player.flush()
        elif last_seq is not None and seq <= last_seq:
            continue  # late / duplicate packet
        if new_source or restarted:
            source = addr[0]
            print(f"Receiving: {rate} Hz, {channels} ch from {source}")
        last_seq = seq
        player.push(payload)


def main():
    ap = argparse.ArgumentParser(description="Play audio streamed by oneaudio-send.")
    ap.add_argument("--port", type=int, default=50007)
    ap.add_argument("--buffer-ms", type=int, default=40)
    ap.add_argument("--update", action="store_true", help="install the latest release")
    ap.add_argument("--version", action="version", version=f"OneAudio {updater.VERSION or 'dev'}")
    args = ap.parse_args()
    if args.update:
        raise SystemExit(updater.update())

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    # We reply to discovery probes; don't let an ICMP error from that break recvfrom.
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        sock.ioctl(socket.SIO_UDP_CONNRESET, False)
    try:
        sock.bind(("0.0.0.0", args.port))
    except OSError as e:
        print(f"Can't listen on port {args.port} (another receiver running?): {e}")
        return
    sock.settimeout(0.5)

    p = pyaudio.PyAudio()
    player = Player(p, args.buffer_ms)
    stop = threading.Event()
    t = threading.Thread(target=receive_loop, args=(sock, player, stop), daemon=True)
    t.start()

    print(f"Listening on port {args.port} (buffer {args.buffer_ms} ms). Ctrl+C to stop.")
    updater.check_in_background()
    try:
        while t.is_alive():
            if player.wanted and player.wanted != player.fmt:
                try:
                    player.open(*player.wanted)
                except OSError as e:
                    print(f"Can't open output for {player.wanted}: {e}")
                    player.fmt = player.wanted  # don't retry in a loop
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        t.join(timeout=2)
        player.close()
        p.terminate()
        sock.close()
        print("Stopped.")


if __name__ == "__main__":
    main()
