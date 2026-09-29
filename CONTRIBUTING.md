# Contributing

This is an experimental hardware project. Distinguish observations on a physical camera from assumptions, and describe which hardware/OS combinations were actually tested.

## Development

```sh
python -m venv .venv
# Activate the environment using your shell's normal activation command.
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m build
```

The normal tests require no USB hardware, vendor application, network connection, or private recordings. The optional recorded-session test uses the `THERMAL_BRIDGE_TEST_CAPTURE` environment variable to point to a local capture in the documented format. Never commit that recording.

## Boundaries

- Put OS/device I/O in a transport adapter.
- Put camera IDs, commands, framing, geometry and device-specific timing in a camera adapter.
- Keep processing independent of USB and video delivery.
- Route commands through the acquisition owner. HTTP handlers must never open the camera themselves.
- Expose new video delivery mechanisms through output adapters.
- Preserve sensor precision independently of the display palette. Never label unvalidated signal as Celsius.

For a change, explain the observable behavior, add tests for meaningful failure modes, and report hardware validation separately from unit-test results. Do not contribute vendor binaries, copied decompiled source, private images, stream keys, or local configuration.
