#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from fritzconnection import FritzConnection
except ImportError:  # Generic mode can run without the optional FRITZ!Box adapter.
    FritzConnection = None

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
EVENTS = DATA / "events"
DB = DATA / "linewatch.sqlite3"
DATA.mkdir(exist_ok=True)
EVENTS.mkdir(exist_ok=True)

POLL = float(os.getenv("LINEWATCH_POLL_SECONDS", "2"))
SAVE_EVERY = float(os.getenv("LINEWATCH_HEALTHY_PERSIST_SECONDS", "30"))
FRITZ_EVERY = float(os.getenv("LINEWATCH_FRITZ_POLL_SECONDS", "10"))
PUBLIC_IP_EVERY = float(os.getenv("LINEWATCH_PUBLIC_IP_SECONDS", "300"))
RING_SECONDS = float(os.getenv("LINEWATCH_RING_SECONDS", "120"))
ROUTER_MODE = os.getenv("LINEWATCH_ROUTER_MODE", "auto").strip().lower() or "auto"
GATEWAY_PROBE = os.getenv("LINEWATCH_GATEWAY_PROBE", "auto").strip().lower() or "auto"
FRITZ_HOST = os.getenv("FRITZ_HOST", "").strip()
FRITZ_USER = os.getenv("FRITZ_USER", "").strip()
FRITZ_PASSWORD = os.getenv("FRITZ_PASSWORD", "")
IFACE = os.getenv("LINEWATCH_INTERFACE", "").strip()
PING_TARGETS = [
    x.strip()
    for x in os.getenv("LINEWATCH_PING_TARGETS", "1.1.1.1,8.8.8.8").split(",")
    if x.strip()
]
DNS_NAME = os.getenv("LINEWATCH_DNS_NAME", "www.cloudflare.com")
HTTP_URL = os.getenv(
    "LINEWATCH_HTTP_URL", "https://connectivitycheck.gstatic.com/generate_204"
)
PUBLIC_IP_URL = os.getenv("LINEWATCH_PUBLIC_IP_URL", "https://api.ipify.org")
STOP = False

ROUTER_MODES = {"auto", "generic", "fritz"}
GATEWAY_PROBE_MODES = {"auto", "on", "off"}


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_route():
    """Return (gateway IPv4, interface) for the host default route."""
    try:
        out = subprocess.check_output(
            ["ip", "-4", "route", "show", "default"], text=True, timeout=2
        )
        line = next((line for line in out.splitlines() if line.strip()), "")
        gw_match = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)", line)
        dev_match = re.search(r"\bdev\s+(\S+)", line)
        return (
            gw_match.group(1) if gw_match else None,
            dev_match.group(1) if dev_match else None,
        )
    except Exception:
        return None, None


def carrier(interface):
    """Read Linux link carrier when sysfs exposes it; otherwise return unknown."""
    if not interface:
        return None
    try:
        return int(
            Path(f"/sys/class/net/{interface}/carrier").read_text().strip() == "1"
        )
    except Exception:
        return None


def ping(host):
    if not host:
        return 0, None
    try:
        p = subprocess.run(
            ["ping", "-n", "-c", "1", "-W", "1", host],
            capture_output=True,
            text=True,
            timeout=2.5,
        )
        if p.returncode:
            return 0, None
        m = re.search(r"time[=<]([\d.]+)\s*ms", p.stdout)
        return 1, float(m.group(1)) if m else None
    except Exception:
        return 0, None


def dns_check():
    t = time.monotonic()
    try:
        socket.getaddrinfo(DNS_NAME, 443, type=socket.SOCK_STREAM)
        return 1, round((time.monotonic() - t) * 1000, 2)
    except Exception:
        return 0, None


def http_check():
    t = time.monotonic()
    try:
        req = urllib.request.Request(HTTP_URL, headers={"User-Agent": "LineWatch/1.1"})
        with urllib.request.urlopen(req, timeout=3) as response:
            response.read(32)
        return 1, round((time.monotonic() - t) * 1000, 2)
    except Exception:
        return 0, None


def public_ip():
    try:
        req = urllib.request.Request(
            PUBLIC_IP_URL, headers={"User-Agent": "LineWatch/1.1"}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.read(128).decode().strip() or None
    except Exception:
        return None


def resolve_router_mode(mode=None, user=None, password=None):
    mode = ROUTER_MODE if mode is None else mode.strip().lower()
    user = FRITZ_USER if user is None else user
    password = FRITZ_PASSWORD if password is None else password
    if mode not in ROUTER_MODES:
        raise ValueError(
            f"Invalid LINEWATCH_ROUTER_MODE={mode!r}; expected auto, generic or fritz"
        )
    if mode == "generic":
        return "generic"
    if mode == "fritz":
        if not user or not password:
            raise ValueError("FRITZ mode requires FRITZ_USER and FRITZ_PASSWORD")
        return "fritz"
    return "fritz" if user and password else "generic"


def resolve_gateway_probe(mode=None):
    mode = GATEWAY_PROBE if mode is None else mode.strip().lower()
    if mode not in GATEWAY_PROBE_MODES:
        raise ValueError(
            f"Invalid LINEWATCH_GATEWAY_PROBE={mode!r}; expected auto, on or off"
        )
    if mode == "on":
        return True
    if mode == "off":
        return False
    return None


@dataclass
class Sample:
    ts: str
    carrier: Optional[int]
    gateway: str
    gateway_ok: int
    gateway_ms: Optional[float]
    internet_ok: int
    internet_ms: Optional[float]
    dns_ok: int
    dns_ms: Optional[float]
    http_ok: int
    http_ms: Optional[float]
    public_ip: Optional[str]
    router_uptime_s: Optional[int]
    router_model: Optional[str]
    fritzos: Optional[str]
    wan_status: Optional[str]
    wan_uptime_s: Optional[int]
    wan_ip: Optional[str]
    wan_last_error: Optional[str]
    wan_transport: Optional[str]
    pppoe_ac_name: Optional[str]
    fritz_error: Optional[str]


def connect_db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS samples(
          id INTEGER PRIMARY KEY, ts TEXT, carrier INTEGER, gateway TEXT, gateway_ok INTEGER, gateway_ms REAL,
          internet_ok INTEGER, internet_ms REAL, dns_ok INTEGER, dns_ms REAL, http_ok INTEGER, http_ms REAL,
          public_ip TEXT, router_uptime_s INTEGER, router_model TEXT, fritzos TEXT, wan_status TEXT,
          wan_uptime_s INTEGER, wan_ip TEXT, wan_last_error TEXT, wan_transport TEXT, pppoe_ac_name TEXT, fritz_error TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY, start_ts TEXT, end_ts TEXT, duration_s REAL, event_type TEXT, details_json TEXT)"""
    )
    conn.commit()
    return conn


def save_sample(conn, sample):
    data = asdict(sample)
    conn.execute(
        f"INSERT INTO samples({','.join(data)}) VALUES({','.join('?' for _ in data)})",
        list(data.values()),
    )
    conn.commit()


def add_event(conn, kind, details, start=None, end=None, duration=None):
    start = start or now()
    cur = conn.execute(
        "INSERT INTO events(start_ts,end_ts,duration_s,event_type,details_json) VALUES(?,?,?,?,?)",
        (start, end, duration, kind, json.dumps(details, ensure_ascii=False)),
    )
    conn.commit()
    return cur.lastrowid


def close_event(conn, event_id, details, duration, end=None):
    conn.execute(
        "UPDATE events SET end_ts=?,duration_s=?,details_json=? WHERE id=?",
        (
            end or now(),
            round(duration, 2),
            json.dumps(details, ensure_ascii=False),
            event_id,
        ),
    )
    conn.commit()


class Fritz:
    def __init__(self, host):
        self.host = host
        self.fc = None
        self.wan = None

    def _connect(self):
        if FritzConnection is None:
            raise RuntimeError(
                "FRITZ!Box support requires the 'fritzconnection' Python package"
            )
        self.fc = FritzConnection(
            address=self.host,
            user=FRITZ_USER,
            password=FRITZ_PASSWORD,
            timeout=4,
        )
        candidates = [
            service
            for service in self.fc.services
            if "WANPPPConnection" in service or "WANIPConnection" in service
        ]
        self.wan = None
        for service in candidates:
            try:
                info = self.fc.call_action(service, "GetInfo")
                if info.get("NewEnable") and str(info.get("NewName", "")).lower() == "internet":
                    self.wan = service
                    break
                if info.get("NewEnable") and not self.wan:
                    self.wan = service
            except Exception:
                pass

    def snapshot(self):
        try:
            if not self.fc:
                self._connect()
            device = self.fc.call_action("DeviceInfo1", "GetInfo")
            out = {
                "router_uptime_s": device.get("NewUpTime"),
                "router_model": device.get("NewModelName"),
                "fritzos": device.get("NewSoftwareVersion"),
            }
            if self.wan:
                wan = self.fc.call_action(self.wan, "GetInfo")
                out.update(
                    wan_status=wan.get("NewConnectionStatus"),
                    wan_uptime_s=wan.get("NewUptime"),
                    wan_ip=wan.get("NewExternalIPAddress"),
                    wan_last_error=wan.get("NewLastConnectionError"),
                    wan_transport=wan.get("NewTransportType"),
                    pppoe_ac_name=wan.get("NewPPPoEACName"),
                )
            try:
                log = self.fc.call_action("DeviceInfo1", "GetDeviceLog").get(
                    "NewDeviceLog"
                )
            except Exception:
                log = None
            out["fritz_error"] = None
            return out, log
        except Exception as exc:
            self.fc = None
            self.wan = None
            return {"fritz_error": f"{type(exc).__name__}: {exc}"}, None


def classify(sample, gateway_probe_active=True):
    """Classify an incident without assuming every network permits ICMP."""
    if sample.carrier == 0:
        return "NETWORK_LINK_DOWN"

    internet_paths_ok = bool(sample.internet_ok or sample.dns_ok or sample.http_ok)

    if gateway_probe_active and not sample.gateway_ok and not internet_paths_ok:
        return "GATEWAY_UNREACHABLE"
    if sample.wan_status and sample.wan_status != "Connected":
        return "WAN_SESSION_DOWN"
    if not sample.internet_ok and not sample.dns_ok and not sample.http_ok:
        return "INTERNET_UNREACHABLE"
    if not sample.dns_ok:
        return "DNS_FAILURE"
    if not sample.http_ok:
        return "HTTP_CONNECTIVITY_FAILURE"

    # ICMP may be blocked even when DNS and HTTP are healthy. Do not declare an
    # outage from a failed Internet ping alone.
    return "OK"


def bundle(event_id, samples, log, details):
    directory = EVENTS / f"event_{event_id:05d}"
    directory.mkdir(exist_ok=True)
    (directory / "details.json").write_text(
        json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "samples.jsonl").write_text(
        "".join(
            json.dumps(asdict(sample), ensure_ascii=False) + "\n" for sample in samples
        ),
        encoding="utf-8",
    )
    if log:
        (directory / "fritz_device_log.txt").write_text(log, encoding="utf-8")


def main():
    global STOP
    signal.signal(signal.SIGINT, lambda *_: globals().__setitem__("STOP", True))
    signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__("STOP", True))

    try:
        router_mode = resolve_router_mode()
        gateway_probe_active = resolve_gateway_probe()
    except ValueError as exc:
        raise SystemExit(str(exc))

    route_gateway, route_iface = default_route()
    if not route_gateway:
        raise SystemExit(
            "No IPv4 default gateway found. Ensure the host has an active network connection."
        )

    interface = IFACE or route_iface
    router_host = FRITZ_HOST or route_gateway
    fritz = Fritz(router_host) if router_mode == "fritz" else None
    ring_samples = max(1, int(max(RING_SECONDS, POLL) / max(POLL, 0.1)))

    probe_label = (
        "auto"
        if gateway_probe_active is None
        else ("on" if gateway_probe_active else "off")
    )
    print(
        f"[LineWatch] gateway: {route_gateway}; interface: {interface or 'unknown'}; "
        f"router mode: {router_mode}; gateway probe: {probe_label}",
        flush=True,
    )
    if fritz:
        print(f"[LineWatch] FRITZ!Box/TR-064 host: {router_host}", flush=True)

    conn = connect_db()
    state = {}
    last_log = None
    last_fritz = last_save = last_ip = 0.0
    pub = None
    prev_router = prev_wan = None
    prev_wan_ip = None
    open_event = None
    open_kind = None
    open_started = None
    open_details = {}
    history = []

    while not STOP:
        cycle = time.monotonic()
        ts = now()
        current_gateway, current_iface = default_route()
        gateway = current_gateway or route_gateway
        if current_gateway:
            route_gateway = current_gateway
        if not IFACE and current_iface:
            interface = current_iface

        car = carrier(interface)
        gok, gms = ping(gateway)

        iok = 0
        ims = None
        for target in PING_TARGETS:
            iok, ims = ping(target)
            if iok:
                break
        dok, dms = dns_check()
        hok, hms = http_check()
        mono = time.monotonic()

        if GATEWAY_PROBE == "auto" and gateway_probe_active is None:
            if gok:
                gateway_probe_active = True
                print(
                    "[LineWatch] gateway ICMP probe supported; using it for incident classification.",
                    flush=True,
                )
            elif iok or dok or hok:
                gateway_probe_active = False
                print(
                    "[LineWatch] gateway does not answer ICMP while Internet works; "
                    "gateway ping will not be used to declare outages.",
                    flush=True,
                )

        if mono - last_ip >= PUBLIC_IP_EVERY or pub is None:
            pub = public_ip() or pub
            last_ip = mono

        if fritz and mono - last_fritz >= FRITZ_EVERY:
            state, log = fritz.snapshot()
            last_log = log or last_log
            last_fritz = mono
        elif not fritz:
            state = {}

        sample = Sample(
            ts,
            car,
            gateway,
            gok,
            gms,
            iok,
            ims,
            dok,
            dms,
            hok,
            hms,
            pub,
            state.get("router_uptime_s"),
            state.get("router_model"),
            state.get("fritzos"),
            state.get("wan_status"),
            state.get("wan_uptime_s"),
            state.get("wan_ip"),
            state.get("wan_last_error"),
            state.get("wan_transport"),
            state.get("pppoe_ac_name"),
            state.get("fritz_error"),
        )
        history.append(sample)
        history = history[-ring_samples:]

        router_reboot = False
        if sample.router_uptime_s is not None:
            router_uptime = int(sample.router_uptime_s)
            if prev_router is not None and router_uptime + 30 < prev_router:
                router_reboot = True
                details = {
                    "previous_router_uptime_s": prev_router,
                    "current_router_uptime_s": router_uptime,
                    "wan_status": sample.wan_status,
                    "wan_ip": sample.wan_ip,
                }
                event_id = add_event(
                    conn,
                    "FRITZBOX_REBOOT_DETECTED",
                    details,
                    start=ts,
                    end=ts,
                    duration=0,
                )
                bundle(event_id, history, last_log, details)
            prev_router = router_uptime

        if sample.wan_uptime_s is not None:
            wan_uptime = int(sample.wan_uptime_s)
            if prev_wan is not None and wan_uptime + 30 < prev_wan and not router_reboot:
                details = {
                    "previous_wan_uptime_s": prev_wan,
                    "current_wan_uptime_s": wan_uptime,
                    "router_uptime_s": sample.router_uptime_s,
                    "wan_ip": sample.wan_ip,
                }
                event_id = add_event(
                    conn,
                    "WAN_SESSION_RESET_DETECTED",
                    details,
                    start=ts,
                    end=ts,
                    duration=0,
                )
                bundle(event_id, history, last_log, details)
            prev_wan = wan_uptime

        observed_wan_ip = sample.wan_ip or sample.public_ip
        if prev_wan_ip and observed_wan_ip and observed_wan_ip != prev_wan_ip:
            add_event(
                conn,
                "WAN_IP_CHANGED",
                {
                    "previous": prev_wan_ip,
                    "new": observed_wan_ip,
                    "source": "router" if sample.wan_ip else "public_probe",
                },
                start=ts,
                end=ts,
                duration=0,
            )
        if observed_wan_ip:
            prev_wan_ip = observed_wan_ip

        kind = classify(sample, gateway_probe_active is True)
        unhealthy = kind != "OK"
        if unhealthy and open_event is None:
            open_kind = kind
            open_started = cycle
            open_details = {"start_state": asdict(sample)}
            open_event = add_event(conn, kind, open_details, start=ts)
            bundle(open_event, history, last_log, open_details)
        elif not unhealthy and open_event is not None:
            duration = cycle - open_started
            open_details.update(
                end_state=asdict(sample), duration_s=round(duration, 2)
            )
            close_event(conn, open_event, open_details, duration, end=ts)
            bundle(open_event, history, last_log, open_details)
            open_event = open_kind = open_started = None
            open_details = {}

        if unhealthy or mono - last_save >= SAVE_EVERY:
            save_sample(conn, sample)
            last_save = mono

        time.sleep(max(0.1, POLL - (time.monotonic() - cycle)))

    conn.close()


if __name__ == "__main__":
    main()
