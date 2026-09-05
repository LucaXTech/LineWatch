# Contributing to LineWatch

Thanks for helping improve LineWatch.

The project aims to keep a small, dependable generic Internet-monitoring core while adding deeper router diagnostics through optional adapters.

## Useful contributions

Especially useful contributions include:

- Linux distribution and hardware compatibility reports
- FRITZ!Box model / FRITZ!OS compatibility reports
- reproducible bug fixes
- unit and integration tests
- documentation improvements
- router adapters that preserve the vendor-neutral core

## Before opening a pull request

1. Open or reference an issue when the change is substantial.
2. Keep credentials, public IP addresses, event logs and other private network data out of commits.
3. Keep changes focused; avoid unrelated formatting or refactors in the same PR.
4. Run:

```bash
python -m unittest discover -s tests -v
python -m py_compile monitor.py dashboard.py
bash -n install.sh configure.sh run_monitor.sh run_dashboard.sh
```

5. Explain how the change was tested.

## Router integrations

New vendor integrations should not make the generic monitor depend on that vendor. Prefer an adapter boundary that exposes optional router/WAN telemetry to the existing classifier and dashboard.

Do not claim compatibility with hardware you have not tested or for which there is no reliable external report.

## Compatibility reports

Please include:

- Linux distribution and version
- CPU architecture
- wired or wireless connection
- router model
- router firmware, if relevant
- generic or enhanced mode
- LineWatch version/commit
- what worked and what failed

See [docs/TESTING.md](docs/TESTING.md) for the validation checklist.

## License

By contributing, you agree that your contribution will be distributed under the project's MIT License.
