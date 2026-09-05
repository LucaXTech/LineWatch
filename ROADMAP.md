# UplinkWitness roadmap

UplinkWitness is intentionally developed as a small, dependable Internet-connection black box rather than a general-purpose observability platform.

The roadmap is ordered by reliability and evidence quality first, feature count second.

## Current baseline — v1.1.x

The current stable baseline, originally released under the LineWatch name, provides:

- vendor-neutral Linux monitoring
- physical/link carrier detection where Linux exposes it
- gateway, Internet, DNS and HTTP probes
- public-IP change tracking
- outage classification and local SQLite history
- responsive dashboard and ISP-oriented reports
- optional FRITZ!Box/TR-064 telemetry for deeper WAN diagnostics

The immediate priority is to harden this baseline through real-world compatibility reports rather than rapidly adding new features.

## Near term

### 1. Broaden real-world Linux validation

Collect repeatable compatibility results across:

- Debian and Ubuntu releases
- Raspberry Pi / ARM64 and x86_64 hardware
- wired and wireless hosts
- routers that answer gateway ICMP and routers that do not

The validation procedure lives in [`docs/TESTING.md`](docs/TESTING.md) and verified results are tracked in [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

### 2. Stabilize the router-adapter boundary

Keep vendor-specific code out of the generic monitoring core and define a small, testable contract for optional router telemetry such as:

- router identity / firmware
- router uptime
- WAN state and uptime
- WAN transport
- WAN/public IP where available
- vendor event/log context around incidents

This should be completed before adding several router vendors.

### 3. Improve failure evidence, not just alert volume

Prioritize changes that make an incident easier to explain after the fact, including clearer event context, exports and regression coverage for ambiguous failure cases.

### 4. Complete the brand transition without breaking upgrades

The public project is now **UplinkWitness**. Existing runtime identifiers such as `linewatch.service`, `LINEWATCH_*` environment variables and the historical SQLite filename remain intentionally stable for compatibility. Any future internal-identifier migration should be explicit, documented and backward-compatible rather than bundled into the public rename.

## Next integrations

After the adapter contract is stable, candidate enhanced integrations include:

- OpenWrt
- MikroTik RouterOS
- UniFi gateways

A vendor is only listed as supported after a real implementation has been validated against actual hardware or a strong external compatibility report. Planned integrations are not advertised as current support.

## Packaging and portability

The automatic installer currently targets `apt` + `systemd` systems. Future portability work may include cleaner manual-install documentation and packaging/service recipes for additional Linux distributions.

Containerization is not automatically considered a win for UplinkWitness: network namespaces can hide the host link and default-route state that the monitor is specifically trying to observe. Any container deployment must preserve diagnostic fidelity.

## Non-goals

UplinkWitness is not trying to become:

- a hosted SaaS monitoring service
- a replacement for Prometheus/Grafana or full infrastructure observability
- a public Internet status page
- a router-management suite
- a cloud-dependent agent

The project should remain useful when the Internet is failing, keep its evidence local, and make unsupported claims conservatively.

## How to help

Useful contributions include compatibility reports, reproducible failure cases, tests, documentation and focused router-adapter work. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
