"""Start Balanza on this computer and open it in the browser.

    python run.py

Balanza uses port 8010. If another program is already using it, Balanza
takes the next free one, so it never collides with other local servers.
"""
import socket
import threading
import time
import webbrowser

import uvicorn

from balanza import __version__

FIRST_PORT = 8010
TRIES = 20


def free_port() -> int:
    """The first port from 8010 upwards that nobody is using."""
    for port in range(FIRST_PORT, FIRST_PORT + TRIES):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue  # busy: try the next one
            return port
    raise SystemExit(f"No free port between {FIRST_PORT} and {FIRST_PORT + TRIES - 1}. Close other local servers and try again.")


def open_when_ready(port: int, address: str) -> None:
    """Open the browser only once Balanza answers, so it never shows a half-loaded page."""
    for _ in range(150):  # up to 30 seconds
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                break
        except OSError:
            time.sleep(0.2)
    # The version in the address makes the browser fetch the page again after an update.
    webbrowser.open(f"{address}/?v={__version__}")


def main() -> None:
    port = free_port()
    address = f"http://127.0.0.1:{port}"
    print(f"\nBalanza is starting at {address}")
    print("Keep this window open. Close it (or press Ctrl+C) to stop Balanza.\n")
    threading.Thread(target=open_when_ready, args=(port, address), daemon=True).start()
    uvicorn.run("balanza.main:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
