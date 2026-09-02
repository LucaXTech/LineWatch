#!/usr/bin/env python3
from __future__ import annotations

import csv, io, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import Flask, Response, jsonify, render_template, request

ROOT=Path(__file__).resolve().parent; DB=ROOT/"data"/"linewatch.sqlite3"; app=Flask(__name__)
OUTAGES={"ETHERNET_LINK_DOWN","ROUTER_UNREACHABLE","WAN_SESSION_DOWN","INTERNET_UNREACHABLE","DNS_FAILURE","HTTP_CONNECTIVITY_FAILURE"}
IT={"FRITZBOX_REBOOT_DETECTED":"Riavvio modem rilevato","WAN_SESSION_RESET_DETECTED":"Reset connessione Internet (PPPoE)","WAN_IP_CHANGED":"Cambio IP WAN","ETHERNET_LINK_DOWN":"Collegamento Ethernet caduto","ROUTER_UNREACHABLE":"FRITZ!Box non raggiungibile","WAN_SESSION_DOWN":"Sessione Internet disconnessa","INTERNET_UNREACHABLE":"Internet non raggiungibile","DNS_FAILURE":"Problema DNS","HTTP_CONNECTIVITY_FAILURE":"Problema connettività web"}
EN={"FRITZBOX_REBOOT_DETECTED":"Modem reboot detected","WAN_SESSION_RESET_DETECTED":"Internet session reset (PPPoE)","WAN_IP_CHANGED":"WAN IP changed","ETHERNET_LINK_DOWN":"Ethernet link down","ROUTER_UNREACHABLE":"FRITZ!Box unreachable","WAN_SESSION_DOWN":"Internet session disconnected","INTERNET_UNREACHABLE":"Internet unreachable","DNS_FAILURE":"DNS failure","HTTP_CONNECTIVITY_FAILURE":"Web connectivity failure"}

def conn():
    c=sqlite3.connect(DB,timeout=5); c.row_factory=sqlite3.Row; return c

def dt(v):
    try:return datetime.fromisoformat(v) if v else None
    except Exception:return None

def since(days): return (datetime.now(timezone.utc)-timedelta(days=days)).astimezone().isoformat(timespec="seconds")

def duration(s):
    if s is None:return "-"
    s=int(float(s)); d,s=divmod(s,86400); h,s=divmod(s,3600); m,s=divmod(s,60)
    if d:return f"{d}d {h}h {m}m"
    if h:return f"{h}h {m}m {s}s"
    if m:return f"{m}m {s}s"
    return f"{s}s"

def ev(r): return {"id":r["id"],"start_ts":r["start_ts"],"end_ts":r["end_ts"],"duration_s":r["duration_s"],"event_type":r["event_type"]}

def p95(values):
    if not values:return None
    x=sorted(values); k=(len(x)-1)*.95; a=int(k); b=min(a+1,len(x)-1); return x[a] if a==b else x[a]*(b-k)+x[b]*(k-a)

@app.route("/")
def index(): return render_template("index.html")

@app.route("/api/status")
def status():
    if not DB.exists():return jsonify(ready=False,reason="Database not created yet")
    c=conn(); s=c.execute("SELECT * FROM samples ORDER BY id DESC LIMIT 1").fetchone(); first=c.execute("SELECT ts FROM samples ORDER BY id ASC LIMIT 1").fetchone()
    if not s:c.close();return jsonify(ready=False,reason="No samples yet")
    now=datetime.now(timezone.utc).astimezone(); first_dt=dt(first["ts"]) if first else now
    windows={}
    for days in (1,7,30):
        start=max(now-timedelta(days=days),first_dt); rows=c.execute("SELECT * FROM events WHERE start_ts>=?",(start.isoformat(timespec="seconds"),)).fetchall(); observed=max(1,(now-start).total_seconds()); down=0.0
        for r in rows:
            if r["event_type"] not in OUTAGES:continue
            if r["duration_s"] is not None:down+=float(r["duration_s"])
            elif r["end_ts"] is None and dt(r["start_ts"]):down+=max(0,(now-dt(r["start_ts"])).total_seconds())
        windows[str(days)]={"reboots":sum(r["event_type"]=="FRITZBOX_REBOOT_DETECTED" for r in rows),"wan_resets":sum(r["event_type"]=="WAN_SESSION_RESET_DETECTED" for r in rows),"outages":sum(r["event_type"] in OUTAGES for r in rows),"downtime_s":round(down,1),"availability_pct":round(max(0,100*(1-min(down,observed)/observed)),5),"observed_s":round(observed,1)}
    last_reboot=c.execute("SELECT * FROM events WHERE event_type='FRITZBOX_REBOOT_DETECTED' ORDER BY start_ts DESC LIMIT 1").fetchone()
    last_problem=c.execute("SELECT * FROM events WHERE event_type IN ('ETHERNET_LINK_DOWN','ROUTER_UNREACHABLE','WAN_SESSION_DOWN','INTERNET_UNREACHABLE','DNS_FAILURE','HTTP_CONNECTIVITY_FAILURE') ORDER BY start_ts DESC LIMIT 1").fetchone()
    completed=c.execute("SELECT duration_s FROM events WHERE event_type IN ('ETHERNET_LINK_DOWN','ROUTER_UNREACHABLE','WAN_SESSION_DOWN','INTERNET_UNREACHABLE','DNS_FAILURE','HTTP_CONNECTIVITY_FAILURE') AND duration_s IS NOT NULL").fetchall(); ds=[float(x[0]) for x in completed]
    hs=(now-timedelta(hours=24)).isoformat(timespec="seconds"); lat=[float(x[0]) for x in c.execute("SELECT internet_ms FROM samples WHERE ts>=? AND internet_ok=1 AND internet_ms IS NOT NULL",(hs,)).fetchall()]
    sample_dt=dt(s["ts"]); boot=wan_start=None; delay=None
    if sample_dt:
        if s["router_uptime_s"] is not None:boot=(sample_dt-timedelta(seconds=int(s["router_uptime_s"]))).isoformat(timespec="seconds")
        if s["wan_uptime_s"] is not None:wan_start=(sample_dt-timedelta(seconds=int(s["wan_uptime_s"]))).isoformat(timespec="seconds")
        if s["router_uptime_s"] is not None and s["wan_uptime_s"] is not None:delay=max(0,int(s["router_uptime_s"])-int(s["wan_uptime_s"]))
    ok=s["carrier"]!=0 and s["gateway_ok"]==1 and s["internet_ok"]==1 and s["dns_ok"]==1 and s["http_ok"]==1 and s["wan_status"] in (None,"","Connected")
    out={"ready":True,"current_ok":ok,"ts":s["ts"],"monitoring_since":first["ts"] if first else None,"router_model":s["router_model"],"fritzos":s["fritzos"],"router_uptime_s":s["router_uptime_s"],"router_boot_iso":boot,"wan_status":s["wan_status"],"wan_uptime_s":s["wan_uptime_s"],"wan_start_iso":wan_start,"reconnect_delay_s":delay,"wan_ip":s["wan_ip"],"public_ip":s["public_ip"],"wan_last_error":s["wan_last_error"],"wan_transport":s["wan_transport"],"pppoe_ac_name":s["pppoe_ac_name"],"gateway_ms":s["gateway_ms"],"internet_ms":s["internet_ms"],"dns_ms":s["dns_ms"],"http_ms":s["http_ms"],"fritz_error":s["fritz_error"],"last_reboot":ev(last_reboot) if last_reboot else None,"last_problem":ev(last_problem) if last_problem else None,"windows":windows,"outage_stats":{"count":len(ds),"avg_s":round(sum(ds)/len(ds),1) if ds else 0,"max_s":round(max(ds),1) if ds else 0},"latency_24h":{"min":round(min(lat),2) if lat else None,"avg":round(sum(lat)/len(lat),2) if lat else None,"p95":round(p95(lat),2) if lat else None,"max":round(max(lat),2) if lat else None}}
    c.close();return jsonify(out)

@app.route("/api/events")
def events():
    c=conn(); rows=c.execute("SELECT * FROM events ORDER BY start_ts DESC LIMIT ?",(min(int(request.args.get("limit",50)),200),)).fetchall();c.close();return jsonify([ev(r) for r in rows])

@app.route("/api/history")
def history():
    hours=min(max(int(request.args.get("hours",24)),1),168); start=(datetime.now(timezone.utc)-timedelta(hours=hours)).astimezone().isoformat(timespec="seconds");c=conn();rows=c.execute("SELECT ts,internet_ms,internet_ok FROM samples WHERE ts>=? ORDER BY ts",(start,)).fetchall();c.close(); step=max(1,len(rows)//1200);return jsonify([dict(r) for r in rows[::step]])

@app.route("/export/events.csv")
def export_csv():
    days=min(max(int(request.args.get("days",30)),1),3650);c=conn();rows=c.execute("SELECT * FROM events WHERE start_ts>=? ORDER BY start_ts",(since(days),)).fetchall();c.close();b=io.StringIO();w=csv.writer(b,delimiter=";");w.writerow(["ID","Start","End","Duration_s","Technical_type","Description_IT","Description_EN","Details"])
    for r in rows:w.writerow([r["id"],r["start_ts"],r["end_ts"],r["duration_s"],r["event_type"],IT.get(r["event_type"],r["event_type"]),EN.get(r["event_type"],r["event_type"]),r["details_json"]])
    return Response("\ufeff"+b.getvalue(),mimetype="text/csv",headers={"Content-Disposition":f'attachment; filename="linewatch_events_{days}days.csv"'})

@app.route("/export/isp.txt")
def export_isp():
    days=min(max(int(request.args.get("days",30)),1),3650);lang=request.args.get("lang","it");labels=EN if lang=="en" else IT;c=conn();rows=c.execute("SELECT * FROM events WHERE start_ts>=? ORDER BY start_ts",(since(days),)).fetchall();s=c.execute("SELECT * FROM samples ORDER BY id DESC LIMIT 1").fetchone();c.close();reboots=sum(r["event_type"]=="FRITZBOX_REBOOT_DETECTED" for r in rows);resets=sum(r["event_type"]=="WAN_SESSION_RESET_DETECTED" for r in rows);outs=[r for r in rows if r["event_type"] in OUTAGES];down=sum(float(r["duration_s"] or 0) for r in outs)
    if lang=="en": lines=["LINEWATCH - ISP CONNECTION DIAGNOSTIC REPORT",f"Period: last {days} days",f"Generated: {now().isoformat(timespec='seconds')}","",f"Router: {s['router_model'] if s else '-'}",f"FRITZ!OS: {s['fritzos'] if s else '-'}",f"Reboots detected: {reboots}",f"WAN/PPPoE resets: {resets}",f"Outages: {len(outs)}",f"Recorded downtime: {duration(down)}","","EVENT TIMELINE"]
    else: lines=["LINEWATCH - REPORT DIAGNOSTICO CONNESSIONE / ISP",f"Periodo: ultimi {days} giorni",f"Generato: {now().isoformat(timespec='seconds')}","",f"Router: {s['router_model'] if s else '-'}",f"FRITZ!OS: {s['fritzos'] if s else '-'}",f"Riavvii rilevati: {reboots}",f"Reset WAN/PPPoE: {resets}",f"Interruzioni: {len(outs)}",f"Downtime registrato: {duration(down)}","","CRONOLOGIA EVENTI"]
    lines += [f"{r['start_ts']} | {labels.get(r['event_type'],r['event_type'])} | {duration(r['duration_s'])}" for r in rows] or ["No events." if lang=="en" else "Nessun evento."]
    return Response("\n".join(lines)+"\n",mimetype="text/plain",headers={"Content-Disposition":f'attachment; filename="linewatch_isp_report_{lang}_{days}days.txt"'})

def now(): return datetime.now(timezone.utc).astimezone()

if __name__=="__main__":app.run(host="0.0.0.0",port=8080)
