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


def check_in_background():
    """Print a one-line notice if a newer release exists. Silent on any failure."""
    if not VERSION:
        return

    def run():
        try:
            tag = _latest(5)["tag_name"]
            if _ver(tag) > _ver(VERSION):
                print(f"Update available: {tag} (you have v{VERSION}). Run with --update to install it.")
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


def update():
    """Download the latest installer and launch it silently. Returns an exit code."""
    if not VERSION:
        print("Running from source; pull the repo instead.")
        return 1
    try:
        rel = _latest(10)
    except Exception as e:
        print(f"Couldn't reach GitHub: {e}")
        return 1
    if _ver(rel["tag_name"]) <= _ver(VERSION):
        print(f"Already up to date (v{VERSION}).")
        return 0
    asset = next((a for a in rel["assets"]
                  if a["name"].startswith("OneAudio-Setup-") and a["name"].endswith(".exe")), None)
    if not asset:
        print(f"Release {rel['tag_name']} has no installer attached.")
        return 1
    path = os.path.join(tempfile.gettempdir(), asset["name"])
    print(f"Downloading {asset['name']}...")
    try:
        urllib.request.urlretrieve(asset["browser_download_url"], path)
    except Exception as e:
        print(f"Download failed: {e}")
        return 1
    print(f"Installing {rel['tag_name']} (approve the admin prompt)...")
    # ShellExecute (not subprocess) so Windows shows the UAC prompt the installer needs.
    os.startfile(path, arguments="/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS")
    return 0
