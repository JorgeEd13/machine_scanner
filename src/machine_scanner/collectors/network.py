"""Network collector — interfaces, addresses (MAC / IPv4 / IPv6) and link state.

Per-interface addresses and up/down/speed come from psutil cross-platform. The
primary outbound IP is found with the classic UDP-socket trick (no packet is
actually sent — connecting a datagram socket just makes the OS pick the source
address it *would* use for that route). Gateway/DNS/Wi-Fi SSID need OS-specific
commands and are deferred to a later phase.
"""

from __future__ import annotations

import socket

from ..core.models import Section, Status
from ..core.registry import register
from . import _psutil


def _primary_ip() -> str | None:
    """Source IP the OS would use to reach the internet (no traffic sent)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return None
    finally:
        sock.close()


@register("network")
def collect() -> Section:
    data: dict = {"hostname": socket.gethostname(), "primary_ip": _primary_ip()}
    notes = []

    ps = _psutil.get()
    if ps is None:
        notes.append(_psutil.MISSING_NOTE)
        return Section("network", "Network", Status.PARTIAL, data, notes)

    stats = ps.net_if_stats()
    interfaces = []
    for name, addrs in ps.net_if_addrs().items():
        addresses = []
        for addr in addrs:
            family = getattr(addr.family, "name", str(addr.family))
            addresses.append({"family": family, "address": addr.address})
        entry = {"name": name, "addresses": addresses}
        if name in stats:
            st = stats[name]
            entry["is_up"] = st.isup
            entry["speed_mbps"] = st.speed or None
            entry["mtu"] = st.mtu
        interfaces.append(entry)

    data["interfaces"] = interfaces
    return Section("network", "Network", Status.OK, data, notes)
