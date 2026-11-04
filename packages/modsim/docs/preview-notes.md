# Modsim 2.0.0a3 preview

This preview pins modpoll-wot 0.2.0a4. A local TCP simulator can load a full
profile 0.2 TM with an audit plan or its independently derived public audit TM.
Tests seed the same known values and verify the public model exposes only the
selected read spans.

### Previous preview

#### Modsim 2.0.0a2

This candidate uses published modpoll-wot 0.2.0a2 and immutable modbus-models-v1
inputs. Device mappings and contribution workflows now live in modbus-models;
examples pin a full data commit and individual content hashes. Vendor originals
are not copied. The tool and data releases remain independent.

Managed deployment version 2 supports local lifecycle and isolation on POSIX.
Single-device foreground mode supports fixed HTTPS TMs and local scenarios;
scripts require explicit --allow-scripts. Catalog acceptance compares raw Modbus
bytes, public modpoll 2.0.0a2 and node-wot 0.9.2 with asymmetric uint16 inputs,
and detects a deliberately wrong byte order. This is software evidence, not
hardware or engineering-unit certification.

Release gates cover independent wheel single-device startup/read/stop on Linux,
macOS and Windows. Managed deployments remain POSIX-only; Windows uses foreground
mode or WSL. A candidate is not accepted until its exact CI and preview publish,
image, docs and source-independent acceptance jobs all pass.

Expected install after publication: `uv tool install --prerelease allow modsim==2.0.0a2`.
The explicit preview image is `topmaker/modsim:2.0.0a2`; stable latest aliases stay
unchanged. Older 2.0.0a1 artifacts and historical contrib URLs remain immutable.
