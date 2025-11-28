from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
from dataclasses import dataclass
from typing import Iterable, List

import requests


@dataclass
class SnapshotHost:
    ip: str
    url: str
    status_code: int
    content_type: str | None
    content_length: int | None


DEFAULT_PORT = 8080
DEFAULT_PATH = '/last.jpg'
DEFAULT_TIMEOUT = 1.0


def _primary_ipv4_address() -> str | None:
    """Best-effort detection of the primary IPv4 address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            candidate = socket.gethostbyname(socket.gethostname())
            if candidate.startswith('127.'):
                return None
            return candidate
        except OSError:
            return None


def detect_ipv4_prefix() -> str | None:
    """Return the leading three octets for the current LAN (e.g., '192.168.1')."""
    ip = _primary_ipv4_address()
    if not ip:
        return None
    parts = ip.split('.')
    if len(parts) != 4:
        return None
    return '.'.join(parts[:3])


def _build_targets(prefix: str) -> Iterable[str]:
    """Yield every host address within the /24 for the prefix (1..254)."""
    network = ipaddress.ip_network(f'{prefix}.0/24', strict=False)
    for host in network.hosts():
        yield str(host)


def _probe_snapshot_host(ip: str, port: int, path: str, timeout: float) -> SnapshotHost | None:
    url = f'http://{ip}:{port}{path}'
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    content_type = response.headers.get('Content-Type')
    content_length = None
    try:
        if 'Content-Length' in response.headers:
            content_length = int(response.headers['Content-Length'])
    except (ValueError, TypeError):
        content_length = None
    if not response.content:
        return None
    if content_type and 'image' not in content_type.lower():
        return None
    return SnapshotHost(
        ip=ip,
        url=url,
        status_code=response.status_code,
        content_type=content_type,
        content_length=content_length,
    )


def scan_snapshot_hosts(
    prefix: str,
    port: int = DEFAULT_PORT,
    path: str = DEFAULT_PATH,
    timeout: float = DEFAULT_TIMEOUT,
) -> List[SnapshotHost]:
    """Probe the /24 for HTTP snapshot endpoints."""
    targets = list(_build_targets(prefix))
    hosts: List[SnapshotHost] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        future_to_ip = {
            executor.submit(_probe_snapshot_host, ip, port, path, timeout): ip
            for ip in targets
        }
        for future in concurrent.futures.as_completed(future_to_ip):
            result = future.result()
            if result:
                hosts.append(result)
    hosts.sort(key=lambda host: host.ip)
    return hosts
