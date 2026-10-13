# OneAudio

Streams whatever is playing on one PC's speakers to another PC on the same network, which plays it on its default speaker. Uncompressed PCM over UDP on port 50007. No accounts or setup: just an IP and a port.

> **Windows only (for now).** Current builds target Windows 10/11 x64 on both ends. Capture uses WASAPI loopback, which only exists on Windows. Other platforms aren't supported or tested.

## Install

Download `OneAudio-Setup-<version>.exe` from [Releases](https://github.com/Escillex/OneAudio/releases) and run it on **both** PCs. The installer:

- installs `oneaudio-send` and `oneaudio-receive`
- adds them to `PATH`, so they work from any terminal (open a new one after installing)
- optionally adds a Windows Firewall rule letting the receiver accept audio on Private networks

Uninstalling from *Settings → Apps* removes the files, the `PATH` entry and the firewall rule.

Prefer no installer? The release also has standalone `oneaudio-send.exe` and `oneaudio-receive.exe`, which run from anywhere.

## Usage

1. On the receiving PC, find its IP: run `ipconfig` and note the **IPv4 Address** (e.g. `192.168.1.42`).
2. On the receiving PC:
   ```
   oneaudio-receive
   ```
3. On the sending PC, pass the receiver's IP:
   ```
   oneaudio-send 192.168.1.42
   ```
4. Play something on the sending PC.

Ctrl+C stops either side, and the other side keeps running. Restart the sender any time and audio resumes on its own.

| Command | Options |
|---|---|
| `oneaudio-send <receiver_ip>` | `--port 50007` |
| `oneaudio-receive` | `--port 50007` `--buffer-ms 40` |

## Firewall

If you skipped the installer's firewall option, Windows Firewall prompts the first time the receiver runs. Allow it on **Private** networks. If you missed the prompt, or your network is set to Public, allow inbound UDP 50007 from an admin prompt:

```
netsh advfirewall firewall add rule name="OneAudio Receiver" dir=in action=allow protocol=UDP localport=50007
```

## Tips

- **Wired is best.** On Wi-Fi, if audio crackles or drops out, raise the buffer with `oneaudio-receive --buffer-ms 80` (try 60–100). More buffer means more delay but fewer glitches.
- Nothing is sent while the sending PC is silent. That's normal; the receiver plays silence until audio comes back.
- The sender captures the *default* output device at the moment it starts. If you switch speakers or headphones, restart the sender.
- If the receiving PC's speaker uses a different sample rate or channel count, the receiver converts automatically (it prints `converting`).

## Building from source

Requires Python 3.11+ and [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

```
pip install PyAudioWPatch pyinstaller
.\build.ps1 -Version 0.2.0
```

Output lands in `dist\`. To run without building: `python sender.py <ip>` / `python receiver.py`.

Releases are built by GitHub Actions: pushing a tag like `v0.2.0` builds the installer and both exes and publishes them as a release.
