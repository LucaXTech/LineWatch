#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "data" / "linewatch.sqlite3"

app = Flask(__name__)


@app.after_request
def disable_browser_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Keep the v1.0 event names for backwards-compatible history while v1.1 uses
# router-agnostic names for newly recorded generic Linux incidents.
OUTAGE_TYPES = {
    "ETHERNET_LINK_DOWN",
    "ROUTER_UNREACHABLE",
    "NETWORK_LINK_DOWN",
    "GATEWAY_UNREACHABLE",
    "WAN_SESSION_DOWN",
    "INTERNET_UNREACHABLE",
    "DNS_FAILURE",
    "HTTP_CONNECTIVITY_FAILURE",
}

LABELS_IT = {
    "FRITZBOX_REBOOT_DETECTED": "Riavvio FRITZ!Box rilevato",
    "WAN_SESSION_RESET_DETECTED": "Reset sessione WAN/PPPoE",
    "WAN_IP_CHANGED": "Cambio IP WAN/pubblico",
    "ETHERNET_LINK_DOWN": "Collegamento Ethernet caduto",
    "ROUTER_UNREACHABLE": "Router non raggiungibile",
    "NETWORK_LINK_DOWN": "Collegamento di rete caduto",
    "GATEWAY_UNREACHABLE": "Gateway non raggiungibile",
    "WAN_SESSION_DOWN": "Sessione Internet disconnessa",
    "INTERNET_UNREACHABLE": "Internet non raggiungibile",
    "DNS_FAILURE": "Problema DNS",
    "HTTP_CONNECTIVITY_FAILURE": "Problema connettività web",
}

LABELS_EN = {
    "FRITZBOX_REBOOT_DETECTED": "FRITZ!Box reboot detected",
    "WAN_SESSION_RESET_DETECTED": "WAN/PPPoE session reset",
    "WAN_IP_CHANGED": "WAN/public IP changed",
    "ETHERNET_LINK_DOWN": "Ethernet link down",
    "ROUTER_UNREACHABLE": "Router unreachable",
    "NETWORK_LINK_DOWN": "Network link down",
    "GATEWAY_UNREACHABLE": "Gateway unreachable",
    "WAN_SESSION_DOWN": "Internet session disconnected",
    "INTERNET_UNREACHABLE": "Internet unreachable",
    "DNS_FAILURE": "DNS failure",
    "HTTP_CONNECTIVITY_FAILURE": "Web connectivity failure",
}


def db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def fmt_duration(seconds):
    if seconds is None:
        return "-"
    try:
        seconds = int(float(seconds))
    except Exception:
        return "-"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {mins}m"
    if hours:
        return f"{hours}h {mins}m {secs}s"
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def since_iso(days):
    return (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).astimezone().isoformat(timespec="seconds")


def event_row(row):
    return {
        "id": row["id"],
        "start_ts": row["start_ts"],
        "end_ts": row["end_ts"],
        "duration_s": row["duration_s"],
        "duration_human": fmt_duration(row["duration_s"]),
        "event_type": row["event_type"],
    }


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def percentile(sorted_values, p):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * p
    floor_index = int(k)
    ceil_index = min(floor_index + 1, len(sorted_values) - 1)
    if floor_index == ceil_index:
        return sorted_values[floor_index]
    return (
        sorted_values[floor_index] * (ceil_index - k)
        + sorted_values[ceil_index] * (k - floor_index)
    )


def latency_stats(conn, hours=24):
    since = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).astimezone().isoformat(timespec="seconds")
    rows = conn.execute(
        """
        SELECT internet_ms
        FROM samples
        WHERE ts >= ? AND internet_ok=1 AND internet_ms IS NOT NULL
        ORDER BY ts ASC
        """,
        (since,),
    ).fetchall()
    vals = sorted(float(row["internet_ms"]) for row in rows if row["internet_ms"] is not None)
    if not vals:
        return {"min": None, "avg": None, "max": None, "p95": None, "samples": 0}
    return {
        "min": round(min(vals), 2),
        "avg": round(sum(vals) / len(vals), 2),
        "max": round(max(vals), 2),
        "p95": round(percentile(vals, 0.95), 2),
        "samples": len(vals),
    }


def fritz_telemetry_present(sample):
    if sample is None:
        return False
    return any(
        sample[key] not in (None, "")
        for key in (
            "router_model",
            "fritzos",
            "router_uptime_s",
            "wan_status",
            "wan_uptime_s",
            "wan_ip",
            "fritz_error",
        )
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    if not DB_PATH.exists():
        return jsonify({"ready": False, "reason": "Database not created yet."})

    conn = db()
    sample = conn.execute("SELECT * FROM samples ORDER BY id DESC LIMIT 1").fetchone()
    if sample is None:
        conn.close()
        return jsonify({"ready": False, "reason": "No samples available yet."})

    first_sample = conn.execute("SELECT ts FROM samples ORDER BY id ASC LIMIT 1").fetchone()
    first_sample_dt = parse_iso(first_sample["ts"]) if first_sample else None
    now_dt = datetime.now(timezone.utc).astimezone()

    windows = {}
    for days in (1, 7, 30):
        requested_start = now_dt - timedelta(days=days)
        observed_start = max(requested_start, first_sample_dt or requested_start)
        observed_s = max(1.0, (now_dt - observed_start).total_seconds())

        rows = conn.execute(
            """
            SELECT event_type, start_ts, end_ts, duration_s
            FROM events
            WHERE start_ts <= ?
              AND (end_ts IS NULL OR end_ts >= ?)
            """,
            (
                now_dt.isoformat(timespec="seconds"),
                observed_start.isoformat(timespec="seconds"),
            ),
        ).fetchall()

        downtime_s = 0.0
        for row in rows:
            if row["event_type"] not in OUTAGE_TYPES:
                continue
            start = parse_iso(row["start_ts"])
            end = parse_iso(row["end_ts"]) if row["end_ts"] else now_dt
            if not start or not end:
                continue
            overlap_start = max(start, observed_start)
            overlap_end = min(end, now_dt)
            if overlap_end > overlap_start:
                downtime_s += (overlap_end - overlap_start).total_seconds()

        downtime_s = round(downtime_s, 1)
        availability = max(
            0.0,
            100.0 * (1.0 - min(downtime_s, observed_s) / observed_s),
        )
        windows[str(days)] = {
            "reboots": sum(
                1
                for row in rows
                if row["event_type"] == "FRITZBOX_REBOOT_DETECTED"
                and (parse_iso(row["start_ts"]) or observed_start) >= observed_start
            ),
            "wan_resets": sum(
                1
                for row in rows
                if row["event_type"] == "WAN_SESSION_RESET_DETECTED"
                and (parse_iso(row["start_ts"]) or observed_start) >= observed_start
            ),
            "outages": sum(1 for row in rows if row["event_type"] in OUTAGE_TYPES),
            "downtime_s": downtime_s,
            "availability_pct": round(availability, 5),
            "observed_s": round(observed_s, 1),
            "observed_since": observed_start.isoformat(timespec="seconds"),
        }

    last_reboot = conn.execute(
        """
        SELECT * FROM events
        WHERE event_type='FRITZBOX_REBOOT_DETECTED'
        ORDER BY start_ts DESC LIMIT 1
        """
    ).fetchone()

    outage_placeholders = ",".join("?" for _ in OUTAGE_TYPES)
    last_problem = conn.execute(
        f"SELECT * FROM events WHERE event_type IN ({outage_placeholders}) ORDER BY start_ts DESC LIMIT 1",
        tuple(OUTAGE_TYPES),
    ).fetchone()
    outage_rows = conn.execute(
        f"SELECT duration_s FROM events WHERE event_type IN ({outage_placeholders}) AND duration_s IS NOT NULL",
        tuple(OUTAGE_TYPES),
    ).fetchall()
    outage_durations = [
        float(row["duration_s"]) for row in outage_rows if row["duration_s"] is not None
    ]
    outage_stats = {
        "count": len(outage_durations),
        "avg_s": round(sum(outage_durations) / len(outage_durations), 1)
        if outage_durations
        else 0,
        "max_s": round(max(outage_durations), 1) if outage_durations else 0,
    }

    # A failed ICMP probe alone does not make the connection unhealthy. Many
    # routers or upstream networks intentionally drop ping while DNS/HTTP work.
    current_ok = (
        sample["carrier"] != 0
        and sample["dns_ok"] == 1
        and sample["http_ok"] == 1
        and (sample["wan_status"] in (None, "", "Connected"))
    )

    sample_dt = parse_iso(sample["ts"])
    router_boot_iso = None
    wan_start_iso = None
    reconnect_delay_s = None
    if sample_dt is not None:
        if sample["router_uptime_s"] is not None:
            router_boot_iso = (
                sample_dt - timedelta(seconds=int(sample["router_uptime_s"]))
            ).isoformat(timespec="seconds")
        if sample["wan_uptime_s"] is not None:
            wan_start_iso = (
                sample_dt - timedelta(seconds=int(sample["wan_uptime_s"]))
            ).isoformat(timespec="seconds")
        if sample["router_uptime_s"] is not None and sample["wan_uptime_s"] is not None:
            reconnect_delay_s = max(
                0,
                int(sample["router_uptime_s"]) - int(sample["wan_uptime_s"]),
            )

    fritz_enhanced = fritz_telemetry_present(sample)
    payload = {
        "ready": True,
        "current_ok": current_ok,
        "router_mode": "fritz" if fritz_enhanced else "generic",
        "fritz_enhanced": fritz_enhanced,
        "monitoring_since": first_sample["ts"] if first_sample else None,
        "ts": sample["ts"],
        "gateway": sample["gateway"],
        "router_model": sample["router_model"],
        "fritzos": sample["fritzos"],
        "router_uptime_s": sample["router_uptime_s"],
        "router_uptime": fmt_duration(sample["router_uptime_s"]),
        "router_boot_iso": router_boot_iso,
        "wan_status": sample["wan_status"],
        "wan_uptime_s": sample["wan_uptime_s"],
        "wan_uptime": fmt_duration(sample["wan_uptime_s"]),
        "wan_start_iso": wan_start_iso,
        "reconnect_delay_s": reconnect_delay_s,
        "wan_ip": sample["wan_ip"],
        "effective_wan_ip": sample["wan_ip"] or sample["public_ip"],
        "public_ip": sample["public_ip"],
        "wan_last_error": sample["wan_last_error"],
        "wan_transport": sample["wan_transport"],
        "pppoe_ac_name": sample["pppoe_ac_name"],
        "gateway_ok": bool(sample["gateway_ok"]),
        "gateway_ms": sample["gateway_ms"],
        "internet_ok": bool(sample["internet_ok"]),
        "internet_ms": sample["internet_ms"],
        "dns_ok": bool(sample["dns_ok"]),
        "dns_ms": sample["dns_ms"],
        "http_ok": bool(sample["http_ok"]),
        "http_ms": sample["http_ms"],
        "carrier": sample["carrier"],
        "fritz_error": sample["fritz_error"],
        "last_reboot": event_row(last_reboot) if last_reboot else None,
        "last_problem": event_row(last_problem) if last_problem else None,
        "windows": windows,
        "latency_24h": latency_stats(conn, 24),
        "outage_stats": outage_stats,
    }
    conn.close()
    return jsonify(payload)


@app.route("/api/events")
def api_events():
    limit = min(max(int(request.args.get("limit", "50")), 1), 200)
    conn = db()
    rows = conn.execute(
        "SELECT * FROM events ORDER BY start_ts DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return jsonify([event_row(row) for row in rows])


@app.route("/api/history")
def api_history():
    hours = min(max(int(request.args.get("hours", "24")), 1), 168)
    since = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).astimezone().isoformat(timespec="seconds")
    conn = db()
    rows = conn.execute(
        """
        SELECT ts, gateway_ms, internet_ms, gateway_ok, internet_ok,
               dns_ok, http_ok, wan_status
        FROM samples
        WHERE ts >= ?
        ORDER BY ts ASC
        """,
        (since,),
    ).fetchall()
    conn.close()

    if len(rows) > 1200:
        step = max(1, len(rows) // 1200)
        rows = rows[::step]

    return jsonify([dict(row) for row in rows])


@app.route("/export/events.csv")
def export_events():
    days = min(max(int(request.args.get("days", "30")), 1), 3650)
    conn = db()
    rows = conn.execute(
        """
        SELECT id,start_ts,end_ts,duration_s,event_type,details_json
        FROM events WHERE start_ts >= ?
        ORDER BY start_ts ASC
        """,
        (since_iso(days),),
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [
            "ID",
            "Start",
            "End",
            "Duration_s",
            "Technical_type",
            "Description_IT",
            "Description_EN",
            "Details",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["start_ts"],
                row["end_ts"],
                row["duration_s"],
                row["event_type"],
                LABELS_IT.get(row["event_type"], row["event_type"]),
                LABELS_EN.get(row["event_type"], row["event_type"]),
                row["details_json"],
            ]
        )

    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="linewatch_events_{days}days.csv"'
        },
    )


@app.route("/export/isp.txt")
@app.route("/export/aruba.txt")
def export_isp():
    days = min(max(int(request.args.get("days", "30")), 1), 3650)
    lang = request.args.get("lang", "it").lower()
    labels = LABELS_EN if lang == "en" else LABELS_IT

    conn = db()
    rows = conn.execute(
        "SELECT * FROM events WHERE start_ts >= ? ORDER BY start_ts ASC",
        (since_iso(days),),
    ).fetchall()
    sample = conn.execute("SELECT * FROM samples ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    reboots = [row for row in rows if row["event_type"] == "FRITZBOX_REBOOT_DETECTED"]
    wan_resets = [row for row in rows if row["event_type"] == "WAN_SESSION_RESET_DETECTED"]
    outages = [row for row in rows if row["event_type"] in OUTAGE_TYPES]
    downtime = sum(float(row["duration_s"] or 0) for row in outages)
    enhanced = fritz_telemetry_present(sample)

    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    if lang == "en":
        lines = [
            "UPLINKWITNESS - ISP CONNECTION DIAGNOSTIC REPORT",
            "=" * 48,
            f"Period analysed: last {days} days",
            f"Generated: {generated}",
            "",
        ]
        if sample:
            lines += [
                f"Gateway: {sample['gateway'] or '-'}",
                f"Public IP: {sample['public_ip'] or '-'}",
            ]
            if enhanced:
                lines += [
                    f"Router: {sample['router_model'] or '-'}",
                    f"FRITZ!OS: {sample['fritzos'] or '-'}",
                    f"Current WAN status: {sample['wan_status'] or '-'}",
                    f"Current router uptime: {fmt_duration(sample['router_uptime_s'])}",
                    f"Current WAN uptime: {fmt_duration(sample['wan_uptime_s'])}",
                    f"Current WAN IP: {sample['wan_ip'] or '-'}",
                    f"Transport: {sample['wan_transport'] or '-'}",
                    f"PPPoE AC/PoP: {sample['pppoe_ac_name'] or '-'}",
                ]
            lines.append("")
        if enhanced:
            lines += [
                f"FRITZ!Box reboots detected: {len(reboots)}",
                f"WAN/PPPoE session resets: {len(wan_resets)}",
            ]
        lines += [
            f"Recorded outages: {len(outages)}",
            f"Total recorded downtime: {fmt_duration(downtime)}",
            "",
            "EVENT TIMELINE",
            "-" * 48,
        ]
    else:
        lines = [
            "UPLINKWITNESS - REPORT DIAGNOSTICO CONNESSIONE / ISP",
            "=" * 46,
            f"Periodo analizzato: ultimi {days} giorni",
            f"Generato: {generated}",
            "",
        ]
        if sample:
            lines += [
                f"Gateway: {sample['gateway'] or '-'}",
                f"IP pubblico: {sample['public_ip'] or '-'}",
            ]
            if enhanced:
                lines += [
                    f"Router: {sample['router_model'] or '-'}",
                    f"FRITZ!OS: {sample['fritzos'] or '-'}",
                    f"Stato WAN attuale: {sample['wan_status'] or '-'}",
                    f"Uptime router attuale: {fmt_duration(sample['router_uptime_s'])}",
                    f"Uptime WAN attuale: {fmt_duration(sample['wan_uptime_s'])}",
                    f"IP WAN attuale: {sample['wan_ip'] or '-'}",
                    f"Trasporto: {sample['wan_transport'] or '-'}",
                    f"PPPoE AC/PoP: {sample['pppoe_ac_name'] or '-'}",
                ]
            lines.append("")
        if enhanced:
            lines += [
                f"Riavvii FRITZ!Box rilevati: {len(reboots)}",
                f"Reset sessione WAN/PPPoE: {len(wan_resets)}",
            ]
        lines += [
            f"Interruzioni registrate: {len(outages)}",
            f"Downtime totale registrato: {fmt_duration(downtime)}",
            "",
            "CRONOLOGIA EVENTI",
            "-" * 46,
        ]

    if not rows:
        lines.append(
            "No events in the selected period."
            if lang == "en"
            else "Nessun evento nel periodo selezionato."
        )
    else:
        for row in rows:
            line = f"{row['start_ts']} | {labels.get(row['event_type'], row['event_type'])}"
            if row["duration_s"]:
                line += f" | {fmt_duration(row['duration_s'])}"
            lines.append(line)

    suffix = "en" if lang == "en" else "it"
    return Response(
        "\n".join(lines) + "\n",
        mimetype="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="linewatch_isp_report_{suffix}_{days}days.txt"'
        },
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
