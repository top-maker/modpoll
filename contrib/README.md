# Contributed device references

This directory retains vendor register documentation and contributed mappings.
CSV files are v1 migration sources; modpoll 2.x loads them again through the
same `--config` content detection, and new configurations should still be
written as profile 0.2 Thing Models. Use the
[migration guide and AI prompt](../docs/site/csv-migration.rst), then validate the new
file with `modpoll-wot validate MODEL --profile` and compare known device
readings.

The maintainer confirmed successful polling of an Eastron meter over physical
RS485 on 2026-10-28. This is manual hardware evidence in addition to automated
simulator and virtual-serial tests. The Eastron directory contains the contributed
SDM72D-M TD and vendor reference documents; validate a mapping for your device
model and selected Unit ID before use.

Contributed configurations are examples, not a required configuration library or
release gate. See the [validation record](../docs/validation.rst) for scope.
