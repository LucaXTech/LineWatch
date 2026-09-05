# Linux validation checklist

Use this checklist before claiming a Linux distribution or device class as tested with UplinkWitness.

## Fresh install

- Start from a clean Linux installation.
- Connect the test machine by Ethernet when possible.
- Run `./install.sh` as a normal user.
- Verify both systemd services start and remain active.

```bash
systemctl status linewatch
systemctl status linewatch-dashboard
journalctl -u linewatch -n 100 --no-pager
```

The `linewatch` service names are intentionally retained as stable runtime identifiers during the UplinkWitness rename.

## Generic mode

Configure `LINEWATCH_ROUTER_MODE=generic` and verify:

- default IPv4 gateway is detected
- active network interface is detected
- dashboard loads on port 8080
- Internet latency samples appear when ICMP is available
- DNS and HTTP checks are healthy
- public IP is populated
- FRITZ-specific fields are not presented as available

## Gateway ICMP behavior

If the gateway answers ping, verify UplinkWitness logs that gateway ICMP is supported.

If the gateway does not answer ping while Internet access works, verify automatic mode disables gateway-based outage classification instead of reporting a false outage.

## Controlled network faults

Where safe and practical, test one fault at a time and restore connectivity after each test:

- disconnect the Ethernet cable briefly -> `NETWORK_LINK_DOWN`
- disable upstream Internet while keeping the LAN/router available -> `INTERNET_UNREACHABLE`
- configure or simulate a DNS failure -> `DNS_FAILURE`
- block the configured HTTP connectivity endpoint -> `HTTP_CONNECTIVITY_FAILURE`

Confirm each event opens and closes with a sensible duration and appears in the dashboard/export.

## FRITZ!Box enhanced mode

On a compatible FRITZ!Box, configure TR-064 credentials and verify:

- router model and FRITZ!OS appear
- router uptime and WAN uptime are populated
- WAN status is available
- generic Internet probes continue to work when TR-064 temporarily fails

Do not deliberately reboot production networking equipment just to complete this checklist unless disruption is acceptable.

## Persistence

Reboot the Linux host and verify the monitor/dashboard return automatically and the previous SQLite history is preserved.

## Report compatibility

Export both CSV and ISP text reports. Check that generic mode does not invent FRITZ-specific telemetry and enhanced mode includes it when available.

When opening a compatibility issue, include distribution/version, architecture, network interface type, router model, UplinkWitness commit/version, and which checklist sections passed.
