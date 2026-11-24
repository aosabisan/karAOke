"""Start Aosabi Karaoke:  python -m karaoke [--port 5290] [--no-browser]"""
import argparse
import os
import webbrowser

from aiohttp import web

from . import __version__
from .server import make_app


def main() -> None:
    ap = argparse.ArgumentParser(description="Aosabi Karaoke, a karaoke plugin for VTube Pro")
    ap.add_argument("--port", type=int, default=int(os.environ.get("AOSABI_KARAOKE_PORT", "5290")))
    ap.add_argument("--no-browser", action="store_true", help="do not open the page by itself")
    a = ap.parse_args()
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Aosabi Karaoke {__version__} is running. Its page: {url}\nKeep this window open while you sing. Close it to stop.")
    if not a.no_browser:
        webbrowser.open(url)
    web.run_app(make_app(), host="127.0.0.1", port=a.port, print=None)


if __name__ == "__main__":
    main()
