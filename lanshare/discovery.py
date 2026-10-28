import json
import socket
import threading
import time
from typing import Callable

from .config import DISCOVERY_INTERVAL, DISCOVERY_PORT


def _broadcast_payload(name: str, port: int, ip: str) -> bytes:
    return json.dumps({"name": name, "port": port, "ip": ip}, ensure_ascii=False).encode("utf-8")


def start_announcer(name: str, port: int, ip: str, stop: threading.Event) -> threading.Thread:
    def run():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = _broadcast_payload(name, port, ip)
        while not stop.is_set():
            try:
                sock.sendto(payload, ("255.255.255.255", DISCOVERY_PORT))
            except OSError:
                pass
            stop.wait(DISCOVERY_INTERVAL)
        sock.close()

    t = threading.Thread(target=run, daemon=True, name="discovery-announcer")
    t.start()
    return t


def start_listener(on_host: Callable[[str, str, int], None], stop: threading.Event) -> threading.Thread:
    """on_host(name, ip, port) — called when a sharing PC is seen on the LAN."""

    def run():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", DISCOVERY_PORT))
        except OSError:
            return
        sock.settimeout(1.0)
        while not stop.is_set():
            try:
                data, _addr = sock.recvfrom(4096)
                info = json.loads(data.decode("utf-8"))
                name = str(info.get("name", "Unknown"))
                ip = str(info.get("ip", ""))
                port = int(info.get("port", 0))
                if ip and port:
                    on_host(name, ip, port)
            except (socket.timeout, json.JSONDecodeError, ValueError, OSError):
                continue
        sock.close()

    t = threading.Thread(target=run, daemon=True, name="discovery-listener")
    t.start()
    return t
