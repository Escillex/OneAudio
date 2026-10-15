"""Update check / self-update against the latest GitHub release."""
import json
import os
import tempfile
import threading
import urllib.request

try:
    from _version import VERSION  # written by build.ps1
except ImportError:
    VERSION = None  # running from source

API = "https://api.github.com/repos/Escillex/OneAudio/releases/latest"


def _latest(timeout):
    req = urllib.request.Request(API, headers={"User-Agent": "OneAudio"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _ver(text):
    return tuple(int(x) for x in text.lstrip("v").split(".")[:3])


def check_in_background(on_found=None):
    """If a newer release exists, call on_found(tag), or print a one-line notice.
    Silent on any failure."""
    if not VERSION:
        return

    def run():
        try:
            tag = _latest(5)["tag_name"]
            if _ver(tag) > _ver(VERSION):
                if on_found:
                    on_found(tag)
                else:
                    print(f"Update available: {tag} (you have v{VERSION}). Run with --update to install it.")
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


def update(out=print, relaunch=None):
    """Download the latest installer and launch it silently. Returns an exit code.
    relaunch ("send" / "receive"): have the installer reopen that role in the tray afterwards."""
    if not VERSION:
        out("Running from source; pull the repo instead.")
        return 1
    try:
        rel = _latest(10)
    except Exception as e:
        out(f"Couldn't reach GitHub: {e}")
        return 1
    if _ver(rel["tag_name"]) <= _ver(VERSION):
        out(f"Already up to date (v{VERSION}).")
        return 0
    asset = next((a for a in rel["assets"]
                  if a["name"].startswith("OneAudio-Setup-") and a["name"].endswith(".exe")), None)
    if not asset:
        out(f"Release {rel['tag_name']} has no installer attached.")
        return 1
    path = os.path.join(tempfile.gettempdir(), asset["name"])
    out(f"Downloading {asset['name']}...")
    try:
        urllib.request.urlretrieve(asset["browser_download_url"], path)
    except Exception as e:
        out(f"Download failed: {e}")
        return 1
    out(f"Installing {rel['tag_name']} (approve the admin prompt)...")
    # ShellExecute (not subprocess) so Windows shows the UAC prompt the installer needs.
    args = "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS"
    if relaunch:
        args += f" /RELAUNCH={relaunch}"
    os.startfile(path, arguments=args)
    return 0
