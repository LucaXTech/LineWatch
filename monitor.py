#!/usr/bin/env python3
from __future__ import annotations

import json, os, re, signal, socket, sqlite3, subprocess, time, urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fritzconnection import FritzConnection

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
EVENTS = DATA / "events"
DB = DATA / "linewatch.sqlite3"
DATA.mkdir(exist_ok=True); EVENTS.mkdir(exist_ok=True)

POLL = float(os.getenv("LINEWATCH_POLL_SECONDS", "2"))
SAVE_EVERY = float(os.getenv("LINEWATCH_HEALTHY_PERSIST_SECONDS", "30"))
FRITZ_EVERY = float(os.getenv("LINEWATCH_FRITZ_POLL_SECONDS", "10"))
FRITZ_HOST = os.getenv("FRITZ_HOST", "").strip()
FRITZ_USER = os.getenv("FRITZ_USER", "").strip()
FRITZ_PASSWORD = os.getenv("FRITZ_PASSWORD", "")
IFACE = os.getenv("LINEWATCH_INTERFACE", "eth0").strip() or "eth0"
PING_TARGETS = [x.strip() for x in os.getenv("LINEWATCH_PING_TARGETS", "1.1.1.1,8.8.8.8").split(",") if x.strip()]
DNS_NAME = os.getenv("LINEWATCH_DNS_NAME", "www.cloudflare.com")
HTTP_URL = os.getenv("LINEWATCH_HTTP_URL", "https://connectivitycheck.gstatic.com/generate_204")
PUBLIC_IP_URL = os.getenv("LINEWATCH_PUBLIC_IP_URL", "https://api.ipify.org")
STOP = False


def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def gateway():
    if FRITZ_HOST: return FRITZ_HOST
    try:
        out = subprocess.check_output(["ip", "-4", "route", "show", "default"], text=True, timeout=2)
        m = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except Exception: return None

def carrier():
    try: return int((Path(f"/sys/class/net/{IFACE}/carrier").read_text().strip() == "1"))
    except Exception: return None

def ping(host):
    try:
        p = subprocess.run(["ping", "-n", "-c", "1", "-W", "1", host], capture_output=True, text=True, timeout=2.5)
        if p.returncode: return 0, None
        m = re.search(r"time[=<]([\d.]+)\s*ms", p.stdout)
        return 1, float(m.group(1)) if m else None
    except Exception: return 0, None

def dns_check():
    t = time.monotonic()
    try:
        socket.getaddrinfo(DNS_NAME, 443, type=socket.SOCK_STREAM)
        return 1, round((time.monotonic()-t)*1000, 2)
    except Exception: return 0, None

def http_check():
    t = time.monotonic()
    try:
        req = urllib.request.Request(HTTP_URL, headers={"User-Agent":"LineWatch/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r: r.read(32)
        return 1, round((time.monotonic()-t)*1000, 2)
    except Exception: return 0, None

def public_ip():
    try:
        req = urllib.request.Request(PUBLIC_IP_URL, headers={"User-Agent":"LineWatch/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r: return r.read(128).decode().strip() or None
    except Exception: return None


@dataclass
class Sample:
    ts: str; carrier: Optional[int]; gateway: str; gateway_ok: int; gateway_ms: Optional[float]
    internet_ok: int; internet_ms: Optional[float]; dns_ok: int; dns_ms: Optional[float]
    http_ok: int; http_ms: Optional[float]; public_ip: Optional[str]
    router_uptime_s: Optional[int]; router_model: Optional[str]; fritzos: Optional[str]
    wan_status: Optional[str]; wan_uptime_s: Optional[int]; wan_ip: Optional[str]
    wan_last_error: Optional[str]; wan_transport: Optional[str]; pppoe_ac_name: Optional[str]
    fritz_error: Optional[str]


def connect_db():
    c = sqlite3.connect(DB, timeout=30); c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS samples(
      id INTEGER PRIMARY KEY, ts TEXT, carrier INTEGER, gateway TEXT, gateway_ok INTEGER, gateway_ms REAL,
      internet_ok INTEGER, internet_ms REAL, dns_ok INTEGER, dns_ms REAL, http_ok INTEGER, http_ms REAL,
      public_ip TEXT, router_uptime_s INTEGER, router_model TEXT, fritzos TEXT, wan_status TEXT,
      wan_uptime_s INTEGER, wan_ip TEXT, wan_last_error TEXT, wan_transport TEXT, pppoe_ac_name TEXT, fritz_error TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY, start_ts TEXT, end_ts TEXT, duration_s REAL, event_type TEXT, details_json TEXT)""")
    c.commit(); return c

def save_sample(c, s):
    d=asdict(s); c.execute(f"INSERT INTO samples({','.join(d)}) VALUES({','.join('?' for _ in d)})", list(d.values())); c.commit()

def add_event(c, kind, details, start=None, end=None, duration=None):
    start=start or now(); cur=c.execute("INSERT INTO events(start_ts,end_ts,duration_s,event_type,details_json) VALUES(?,?,?,?,?)",
        (start,end,duration,kind,json.dumps(details,ensure_ascii=False))); c.commit(); return cur.lastrowid

def close_event(c, event_id, details, duration):
    c.execute("UPDATE events SET end_ts=?,duration_s=?,details_json=? WHERE id=?", (now(),round(duration,2),json.dumps(details,ensure_ascii=False),event_id)); c.commit()


class Fritz:
    def __init__(self, host): self.host=host; self.fc=None; self.wan=None
    def _connect(self):
        self.fc=FritzConnection(address=self.host,user=FRITZ_USER,password=FRITZ_PASSWORD,timeout=4)
        candidates=[s for s in self.fc.services if "WANPPPConnection" in s or "WANIPConnection" in s]
        self.wan=None
        for s in candidates:
            try:
                x=self.fc.call_action(s,"GetInfo")
                if x.get("NewEnable") and str(x.get("NewName","")).lower()=="internet": self.wan=s; break
                if x.get("NewEnable") and not self.wan: self.wan=s
            except Exception: pass
    def snapshot(self):
        try:
            if not self.fc: self._connect()
            d=self.fc.call_action("DeviceInfo1","GetInfo")
            out={"router_uptime_s":d.get("NewUpTime"),"router_model":d.get("NewModelName"),"fritzos":d.get("NewSoftwareVersion")}
            if self.wan:
                w=self.fc.call_action(self.wan,"GetInfo")
                out.update(wan_status=w.get("NewConnectionStatus"),wan_uptime_s=w.get("NewUptime"),wan_ip=w.get("NewExternalIPAddress"),
                           wan_last_error=w.get("NewLastConnectionError"),wan_transport=w.get("NewTransportType"),pppoe_ac_name=w.get("NewPPPoEACName"))
            try:
                log=self.fc.call_action("DeviceInfo1","GetDeviceLog").get("NewDeviceLog")
            except Exception: log=None
            out["fritz_error"]=None; return out,log
        except Exception as e:
            self.fc=None; self.wan=None; return {"fritz_error":f"{type(e).__name__}: {e}"},None


def classify(s):
    if s.carrier == 0: return "ETHERNET_LINK_DOWN"
    if not s.gateway_ok: return "ROUTER_UNREACHABLE"
    if s.wan_status and s.wan_status != "Connected": return "WAN_SESSION_DOWN"
    if not s.internet_ok: return "INTERNET_UNREACHABLE"
    if not s.dns_ok: return "DNS_FAILURE"
    if not s.http_ok: return "HTTP_CONNECTIVITY_FAILURE"
    return "OK"

def bundle(event_id, samples, log, details):
    d=EVENTS/f"event_{event_id:05d}"; d.mkdir(exist_ok=True)
    (d/"details.json").write_text(json.dumps(details,indent=2,ensure_ascii=False),encoding="utf-8")
    (d/"samples.jsonl").write_text("".join(json.dumps(asdict(s),ensure_ascii=False)+"\n" for s in samples[-60:]),encoding="utf-8")
    if log: (d/"fritz_device_log.txt").write_text(log,encoding="utf-8")


def main():
    global STOP
    signal.signal(signal.SIGINT,lambda *_: globals().__setitem__("STOP",True)); signal.signal(signal.SIGTERM,lambda *_: globals().__setitem__("STOP",True))
    host=gateway()
    if not host or not FRITZ_USER or not FRITZ_PASSWORD: raise SystemExit("Configure FRITZ_USER/FRITZ_PASSWORD and ensure a default gateway is available.")
    print(f"[LineWatch] FRITZ!Box/gateway: {host}",flush=True)
    c=connect_db(); fritz=Fritz(host); state={}; last_log=None; last_fritz=last_save=last_ip=0.0; pub=None
    prev_router=prev_wan=None; prev_wan_ip=None; open_event=None; open_kind=None; open_started=None; open_details={}; history=[]
    while not STOP:
        cycle=time.monotonic(); ts=now(); host=gateway() or host
        car=carrier(); gok,gms=ping(host)
        iok=0; ims=None
        for target in PING_TARGETS:
            iok,ims=ping(target)
            if iok: break
        dok,dms=dns_check(); hok,hms=http_check(); mono=time.monotonic()
        if mono-last_ip>=300 or pub is None: pub=public_ip() or pub; last_ip=mono
        if mono-last_fritz>=FRITZ_EVERY: state,log=fritz.snapshot(); last_log=log or last_log; last_fritz=mono
        s=Sample(ts,car,host,gok,gms,iok,ims,dok,dms,hok,hms,pub,state.get("router_uptime_s"),state.get("router_model"),state.get("fritzos"),
                 state.get("wan_status"),state.get("wan_uptime_s"),state.get("wan_ip"),state.get("wan_last_error"),state.get("wan_transport"),state.get("pppoe_ac_name"),state.get("fritz_error"))
        history.append(s); history=history[-120:]
        router_reboot=False
        if s.router_uptime_s is not None:
            ru=int(s.router_uptime_s)
            if prev_router is not None and ru+30<prev_router:
                router_reboot=True; details={"previous_router_uptime_s":prev_router,"current_router_uptime_s":ru,"wan_status":s.wan_status,"wan_ip":s.wan_ip}
                eid=add_event(c,"FRITZBOX_REBOOT_DETECTED",details,start=ts,end=ts,duration=0); bundle(eid,history,last_log,details)
            prev_router=ru
        if s.wan_uptime_s is not None:
            wu=int(s.wan_uptime_s)
            if prev_wan is not None and wu+30<prev_wan and not router_reboot:
                details={"previous_wan_uptime_s":prev_wan,"current_wan_uptime_s":wu,"router_uptime_s":s.router_uptime_s,"wan_ip":s.wan_ip}
                eid=add_event(c,"WAN_SESSION_RESET_DETECTED",details,start=ts,end=ts,duration=0); bundle(eid,history,last_log,details)
            prev_wan=wu
        if prev_wan_ip and s.wan_ip and s.wan_ip!=prev_wan_ip: add_event(c,"WAN_IP_CHANGED",{"previous":prev_wan_ip,"new":s.wan_ip},start=ts,end=ts,duration=0)
        if s.wan_ip: prev_wan_ip=s.wan_ip
        kind=classify(s); unhealthy=kind!="OK"
        if unhealthy and open_event is None:
            open_kind=kind; open_started=mono; open_details={"start_state":asdict(s)}; open_event=add_event(c,kind,open_details,start=ts); bundle(open_event,history,last_log,open_details)
        elif not unhealthy and open_event is not None:
            duration=mono-open_started; open_details.update(end_state=asdict(s),duration_s=round(duration,2)); close_event(c,open_event,open_details,duration); bundle(open_event,history,last_log,open_details)
            open_event=open_kind=open_started=None; open_details={}
        if unhealthy or mono-last_save>=SAVE_EVERY: save_sample(c,s); last_save=mono
        time.sleep(max(.1,POLL-(time.monotonic()-cycle)))
    c.close()

if __name__ == "__main__": main()
