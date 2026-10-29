# Community device models and behaviors

Organize contributions as `contrib/<vendor>/<model>/`. Maintain one profile 0.2
TM as the register mapping source. Scenarios and scripts reference property names
and do not duplicate addresses. Generated TDs are derived by
`poetry run python tools/generate-td.py`; do not edit them by hand.

Include a README with model/firmware scope, public mapping sources, startup
commands, author/license attribution and verification status: hardware-tested,
manual-derived, or synthetic. Existing ADAM mappings are manual-derived and
have protocol validation, not a claim of physical hardware verification.
Do not include credentials or deployment-specific network addresses.

Prefer declarative scenarios. Python scripts must be local and require explicit
`--allow-scripts`; they run with the invoking user's permissions. Document hooks,
parameters and assumptions. Keep callbacks synchronous and nonblocking. A script
must use `device.get`, `set`, or `set_many`, rather than PyModbus internals.
Include a repeatable read/write example and a meaningful test for custom behavior.

- [ADAM-5017UH](advantech/adam-5017uh/): raw input mapping, bounded sine and Python example.
- [ADAM-6024](advantech/adam-6024/): raw I/O mapping with synthetic AO→AI and DO→DI loopback.

Loopback and generated raw counts demonstrate software behavior; they do not
represent the internal behavior or calibrated engineering units of real hardware.
