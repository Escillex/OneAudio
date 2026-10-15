"""Remembered choices (last receiver, mute, buffer), shared by console and tray runs."""
import json
import os

PATH = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "OneAudio", "settings.json")


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(**changes):
    """Merge changes into the file (sender and receiver share it). Silent on failure."""
    data = load()
    data.update(changes)
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, PATH)
    except OSError:
        pass
