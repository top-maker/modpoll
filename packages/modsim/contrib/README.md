# Community device models and behaviors

Start with [Contributing to modsim](../CONTRIBUTING.md). For a new executable
model, submit `contrib/<vendor>/<model>/<model>.tm.json` and identify the source,
permission basis and known limits in the PR. A focused correction only needs the
relevant change. README text, reference files, images, scenarios and hardware
evidence are optional submission materials; maintainers can help complete the
information needed for publication. Do not include private device information.

Maintain one profile 0.2 TM as the register mapping source. Scenarios reference
property names and do not duplicate addresses. Prefer declarative scenarios;
local Python requires explicit `--allow-scripts` and meaningful behavior tests.
See [model-driven simulation](../docs/site/model-validation.md).

Keep models, original references and optional maintainer-reviewed `device.yaml`
records together in each device directory. Contributors can use existing devices
as examples, but are not required to fill complete product records. Maintainers
may help curate them. There is no separate `catalog/` contribution tree; generated
website indexes/build outputs belong outside device directories. The convention
does not imply implemented metadata schemas or website ingestion. Generate deployment-specific TDs on demand. The existing
checked-in ADAM-6024 TD is derived by `uv run python tools/generate-td.py`; if its
inputs change, regenerate it rather than editing it by hand.

Evidence categories are configuration checks, software interoperability and
hardware communication. Describe exactly what was tested, with versions and
limitations. Existing ADAM mappings are manual-derived; loopback and generated
raw counts do not establish real hardware behavior or calibrated engineering
units. Device-specific evidence may document narrower hardware observations.

- [ADAM-5017UH](advantech/adam-5017uh/): raw input mapping, bounded sine and Python example.
- [ADAM-6024](advantech/adam-6024/): raw I/O mapping with synthetic AO-to-AI and DO-to-DI loopback.
