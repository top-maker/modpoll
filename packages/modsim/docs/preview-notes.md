# Modsim 2.0.0a1 preview

Profile 0.2 TM/TD models now drive the simulator, using published
`modpoll-wot==0.2.0a1`. A local deployment runs multiple isolated Unit IDs on one
TCP listener. Models may be local or HTTPS URLs. Local scenarios support initial
values, seeded generators and bindings; Python initialize/tick/on_write hooks
require `--allow-scripts`.

The property codec covers integers, IEEE floats, strings, native/legacy booleans,
byte/word orders, inverse multipliers and bit selectors. Partial writes validate
overlapping properties and roll back on failure. Integer inverse transforms must
be exact; constraints also apply after IEEE quantization.

Install the CLI: `uv tool install modsim==2.0.0a1`.
Image: `topmaker/modsim:2.0.0a1` (amd64/arm64).
Documentation: <https://top-maker.github.io/modsim/v2/>.
The published 2.0.0a1 image includes contrib ADAM models and its original
`examples/lab.sim.json` version 1 deployment. Current development uses version 2.
Models are manual-derived and synthetic-tested; no hardware certification is
claimed. This preview leaves stable latest aliases unchanged.
