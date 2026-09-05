# UplinkWitness

[![CI](https://github.com/LucaXTech/UplinkWitness/actions/workflows/ci.yml/badge.svg)](https://github.com/LucaXTech/UplinkWitness/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/LucaXTech/UplinkWitness)](https://github.com/LucaXTech/UplinkWitness/releases/latest)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Linux](https://img.shields.io/badge/Linux-self--hosted-success)
![License](https://img.shields.io/badge/license-MIT-green)

> **Know what actually went down.**

**UplinkWitness is a self-hosted Internet connection black box for Linux.** Most uptime monitors tell you that something stopped answering; UplinkWitness tries to preserve enough local evidence to tell you **where the failure was**: local link, gateway, upstream Internet, DNS, HTTP, or — with optional router telemetry — the router/WAN session itself.

It works with ordinary routers in **generic Linux mode** and becomes more diagnostic with a **FRITZ!Box** through TR-064. A Raspberry Pi is a convenient always-on deployment target, **not a requirement**.

**Current stable release:** [v1.1.0](https://github.com/LucaXTech/UplinkWitness/releases/tag/v1.1.0) · [Quick install](#quick-install) · [Compatibility](docs/COMPATIBILITY.md) · [Roadmap](ROADMAP.md) · [Contributing](CONTRIBUTING.md)

> **Project rename:** releases through v1.1.0 were published as **LineWatch**. The public project is now **UplinkWitness**. Existing runtime identifiers such as `linewatch.service`, `LINEWATCH_*` environment variables and `data/linewatch.sqlite3` are intentionally retained for upgrade compatibility.

## Screenshots

### Desktop dashboard

![UplinkWitness desktop dashboard](docs/screenshots/dashboard-desktop.png)

### Mobile dashboard

<p align="center">
  <img src="docs/screenshots/dashboard-mobile.png" alt="UplinkWitness mobile dashboard" width="360">
</p>

> The screenshots currently show the FRITZ!Box-enhanced dashboard. In generic mode, FRITZ-specific cards are replaced by gateway and generic connectivity diagnostics. Screenshots from v1.1 may still show the former LineWatch name while the rebrand is being completed.

## Why UplinkWitness?

A normal uptime check can tell you that a target stopped answering. That is useful, but it often does not tell you **which part of a home Internet connection failed**.

UplinkWitness combines multiple signals and keeps the evidence locally:

- Linux network-link state when available
- default-gateway reachability
- multiple Internet ICMP targets
- DNS resolution
- HTTP connectivity
- public IP changes
- outage duration and availability
- optional router/WAN telemetry

This is particularly useful for short or intermittent faults that disappear before ISP support looks at the line.

## Two operating modes

| Capability | Generic Linux | FRITZ!Box enhanced |
| --- | :---: | :---: |
| Internet reachability | ✅ | ✅ |
| DNS / HTTP checks | ✅ | ✅ |
| Latency history | ✅ | ✅ |
| Gateway monitoring | ✅ | ✅ |
| Public IP changes | ✅ | ✅ |
| Outage / downtime history | ✅ | ✅ |
| ISP report + CSV export | ✅ | ✅ |
| Router model / firmware | — | ✅ |
| Router uptime / reboot detection | — | ✅ |
| WAN-session uptime | — | ✅ |
| WAN / PPPoE reset detection | — | ✅ |
| FRITZ!Box event log around incidents | — | ✅ |

`LINEWATCH_ROUTER_MODE=auto` selects FRITZ!Box enhanced mode when credentials are configured; otherwise it runs generically.

## What it detects

### On any supported Linux host

- local network-link loss when exposed by Linux sysfs
- gateway reachability changes
- complete Internet loss
- DNS failures
- HTTP connectivity failures
- public IP changes
- latency trends
- outage duration, total downtime and observed-period availability

UplinkWitness does **not** assume that every router or Internet path answers ICMP. In automatic gateway-probe mode, a router that drops ping while DNS/HTTP remain healthy is not incorrectly classified as down.

### With FRITZ!Box telemetry

- FRITZ!Box reboot through router-uptime reset
- WAN / PPPoE session reset without a router reboot
- WAN connection state
- WAN IP and transport details
- PPPoE access concentrator when exposed
- FRITZ!Box device logs around incidents when available

## Dashboard

The responsive local dashboard provides:

- current connection health
- automatic generic / FRITZ-enhanced presentation
- latency with 24 h min / average / P95 / max
- outage counters and downtime statistics
- observed-period availability
- event timeline
- Italian / English UI
- CSV event export
- human-readable ISP diagnostic report

Availability is calculated only over the period UplinkWitness has actually observed. A new installation does not pretend to have 30 days of monitoring history.

## Where it can run

The monitor is designed for an **always-on Linux host**. Good deployment targets include:

- Raspberry Pi
- Debian / Ubuntu mini-PC
- home server
- Linux VM
- other ARM or x86 Linux systems with the required networking tools

For meaningful line diagnostics, an **Ethernet-connected always-on machine is recommended**. Wi-Fi can work, but then local wireless problems become part of what UplinkWitness observes.

The automatic installer currently targets systems with `apt` and `systemd`, including Debian, Ubuntu and Raspberry Pi OS. Other Linux distributions can use the manual setup path once Python, `iproute2` and `ping` are available.

## Compatibility status

v1.1.0 has been validated on a physical ARM64 Raspberry Pi running Debian 13, including a controlled Ethernet disconnect/recovery test in generic mode. FRITZ!Box enhanced mode has been validated with a FRITZ!Box 5530 Fiber on FRITZ!OS 8.20 and PPPoE. WSL2/Ubuntu on x86_64 is also used for generic/install regression testing.

See [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) for the current matrix and [docs/TESTING.md](docs/TESTING.md) for the validation checklist. Compatibility reports from other Linux machines and router models are especially useful.

## Quick install

Recommended: an always-on Debian/Ubuntu/Raspberry Pi OS machine connected by Ethernet.

```bash
git clone https://github.com/LucaXTech/UplinkWitness.git
cd UplinkWitness
chmod +x install.sh
./install.sh
```

The installer asks whether you want FRITZ!Box enhanced diagnostics.

### Generic mode

Choose **No** when asked about FRITZ!Box integration. No router credentials are required.

UplinkWitness will monitor the Linux default gateway and external connectivity probes.

### FRITZ!Box enhanced mode

Choose **Yes** and provide a FRITZ!Box account allowed to access router settings through TR-064.

A dedicated account is optional. Remote/Internet access for that account is not required.

After installation, open the dashboard on port `8080` of the Linux host. For example:

```text
http://<host-lan-ip>:8080
```

If the machine is already reachable as `linewatch.local`, that hostname continues to work; the project rename does not change your host's network name.

## Manual configuration

```bash
cp .env.example .env
chmod 600 .env
```

The most relevant options are:

```text
LINEWATCH_ROUTER_MODE=auto
LINEWATCH_INTERFACE=
LINEWATCH_GATEWAY_PROBE=auto

FRITZ_USER=
FRITZ_PASSWORD=
FRITZ_HOST=
```

### Router modes

`auto`
: Use FRITZ!Box telemetry when credentials are present; otherwise generic mode.

`generic`
: Never use router-specific telemetry.

`fritz`
: Require FRITZ!Box credentials and enable TR-064 diagnostics.

### Gateway probe modes

`auto`
: Learn whether the gateway responds to ICMP. If Internet/DNS/HTTP work while gateway ping does not, gateway ICMP is excluded from outage classification.

`on`
: Always use gateway ICMP for incident classification.

`off`
: Never use gateway ICMP to classify an outage.

Leaving `LINEWATCH_INTERFACE` empty lets UplinkWitness detect the interface associated with the Linux IPv4 default route.

## Services

Existing service identifiers deliberately retain the original internal name:

```bash
systemctl status linewatch
systemctl status linewatch-dashboard
```

Live monitor log:

```bash
journalctl -u linewatch -f
```

## Remote access

The dashboard deliberately has no public-Internet authentication layer. **Do not expose port 8080 with router port forwarding.**

For private remote access, use a VPN or mesh VPN such as Tailscale.

## Data and privacy

Runtime data stays on the machine running UplinkWitness:

- `data/linewatch.sqlite3` — SQLite database; legacy-compatible filename
- `data/events/` — incident bundles and optional FRITZ!Box logs

The repository ignores `.env`, runtime databases and logs. Do not commit real router credentials, event logs, public IP addresses or personal network data.

## Architecture

```text
                  UplinkWitness Core
                          │
         ┌────────────────┼────────────────┐
         │                │                │
   Linux / gateway    Internet probes   Router adapter
         │            ICMP · DNS · HTTP       │
         │                │                   └── FRITZ!Box / TR-064
         │                │
         └────────────────┴───────────────┐
                                          │
                                  Incident classifier
                                          │
                              SQLite + event bundles
                                          │
                               Web dashboard :8080
```

The router integration boundary is intentionally narrow so additional router adapters can be added in the future without replacing the generic monitoring core.

Potential future integrations include OpenWrt, MikroTik, UniFi and standards-based telemetry where reliable interfaces exist. They are **not currently advertised as supported**.

## Development

CI currently checks Python 3.11 and 3.13, compiles the monitor/dashboard, runs unit tests and validates the shell scripts.

Run tests locally with:

```bash
python -m unittest discover -s tests -v
```

## Contributing

Bug reports, Linux compatibility results, FRITZ!Box model reports, tests and router-adapter contributions are welcome.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. The current development priorities are tracked in [ROADMAP.md](ROADMAP.md).

If you test UplinkWitness on different hardware, include:

- Linux distribution and version
- architecture (`x86_64`, `aarch64`, etc.)
- wired or wireless connection
- router model
- whether generic or FRITZ-enhanced mode was used

## Author

Created and maintained by **Luca Serioli** ([@LucaXTech](https://github.com/LucaXTech)).

See [AUTHORS.md](AUTHORS.md) for project attribution and contributor information.

## License

UplinkWitness is open-source software released under the **MIT License**. See [LICENSE](LICENSE).

## Status

Active early-stage open-source project. The goal is to keep the generic monitoring core small and dependable while adding deeper router diagnostics through optional adapters.
