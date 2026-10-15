# OneAudio

Streams whatever is playing on one PC's speakers to another PC on the same network, which plays it on its default speaker. Uncompressed PCM over UDP on port 50007. No accounts or setup: just an IP and a port.

> **Windows only (for now).** Current builds target Windows 10/11 x64 on both ends. Capture uses WASAPI loopback, which only exists on Windows. Other platforms aren't supported or tested.

## Install

Download `OneAudio-Setup-<version>.exe` from [Releases](https://github.com/Escillex/OneAudio/releases) and run it on **both** PCs. The installer:

- installs `oneaudio-send` and `oneaudio-receive`
- adds them to `PATH`, so they work from any terminal (restart your terminal app after installing, not just a new tab)
- optionally adds a Windows Firewall rule letting the receiver accept audio on Private networks
- adds **OneAudio Sender** and **OneAudio Receiver** to the Start menu (optional, on by default; desktop shortcuts are offered too). These run in the system tray, no terminal needed

Uninstalling from *Settings → Apps* removes the files, shortcuts, the `PATH` entry and the firewall rule.

Prefer no installer? The release also has standalone `oneaudio-send.exe` and `oneaudio-receive.exe`, which run from anywhere.

## Usage

1. On the receiving PC:
   ```
   oneaudio-receive
   ```
2. On the sending PC:
   ```
   oneaudio-send
   ```
   It reconnects to the receiver you used last if it's online. Otherwise it finds receivers on your network: with one, it connects right away; with several, it lists them by PC name so you can pick one.
3. Play something on the sending PC.

Ctrl+C stops either side, and the other side keeps running. Restart the sender any time and audio resumes on its own. Only one sender and one receiver run per PC at a time; starting a second one tells you where the first is.

### Tray mode

Open **OneAudio Sender** / **OneAudio Receiver** from the Start menu, or add `-d` to either command (the terminal is free again and you can close it). Right-click the tray icon for:

- **Sender:** the receiver to stream to (with **Rescan**), **Mute this PC**, **Quit**
- **Receiver:** the **Buffer** (raise it if audio crackles), **Quit**
- **Install update** when a new version is out. It reopens in the tray afterwards.

The receiver, the mute and the buffer you pick are remembered for next time, in tray and terminal alike.

| Command | Options |
|---|---|
| `oneaudio-send [receiver_ip]` | `--port 50007` `-m` / `--mute` `-d` / `--detach` |
| `oneaudio-receive` | `--port 50007` `--buffer-ms 40` `-d` / `--detach` |

- `-m` mutes the sending PC's speakers while streaming, so audio only plays on the receiver. The sender also mutes if you last left **Mute this PC** on in the tray. Unmuting happens when the sender stops (Ctrl+C, closing the window, Quit, or signing out / shutting down).
- `-d` runs it in the tray (see above).
- `--buffer-ms` overrides the remembered buffer for that run.
- If discovery can't find the receiver (some routers and guest Wi-Fi block broadcasts), pass its IP directly: `oneaudio-send 192.168.1.42`. Find it with `ipconfig` on the receiving PC (**IPv4 Address**).
- The receiver IP must be a full address like `192.168.1.42`. Short forms like `192.168.128` are rejected, because Windows would silently send them somewhere else.

## Updates

Both commands check for a new release when they start and print a notice if one exists (in tray mode, a notification and an **Install update** menu item). To install it from a terminal:

```
oneaudio-send --update
```

(`oneaudio-receive --update` works the same.) It downloads the latest installer and runs it silently after one admin prompt. Running the installer by hand also works: it detects the existing install and upgrades it in place. Check your version with `--version`.

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
pip install PyAudioWPatch pystray pillow pyinstaller
.\build.ps1 -Version 0.2.0
```

Output lands in `dist\`. To run without building: `python sender.py <ip>` / `python receiver.py`.

Releases are built by GitHub Actions: pushing a tag like `v0.2.0` builds the installer and both exes and publishes them as a release.
