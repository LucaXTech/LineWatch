# LineWatch → UplinkWitness rename

The project was originally published as **LineWatch** and was renamed to **UplinkWitness** before broader public launch.

## What changed

The public project identity changed:

- GitHub repository: `LucaXTech/LineWatch` → `LucaXTech/UplinkWitness`
- README, dashboard, reports and user-facing documentation use **UplinkWitness**
- new clones should use the UplinkWitness repository URL

GitHub redirects the former repository URL, but existing clones should update their `origin` explicitly:

```bash
git remote set-url origin https://github.com/LucaXTech/UplinkWitness.git
```

## What intentionally did not change

To preserve upgrades and historical data, the rename does **not** change existing runtime identifiers:

- `linewatch.service`
- `linewatch-dashboard.service`
- `LINEWATCH_*` environment variables
- `data/linewatch.sqlite3`
- existing event/database schemas
- an installation directory that a current systemd unit already points to

These names are implementation-level compatibility identifiers, not the public product name.

## Existing installations

No database migration is required solely because of the rename. An existing v1.0/v1.1 installation can keep its directory, `.env`, systemd units and SQLite history.

Do **not** manually rename an existing production directory or systemd unit just to match the new public brand. A path change can break the `WorkingDirectory` or executable paths stored in systemd.

## New installations

Use:

```bash
git clone https://github.com/LucaXTech/UplinkWitness.git
cd UplinkWitness
chmod +x install.sh
./install.sh
```

The installer still creates the stable `linewatch` service identifiers for compatibility.

## Releases

Releases through **v1.1.0** were published under the LineWatch name. Their tags and history remain part of the same repository. Subsequent releases use the UplinkWitness public identity.
