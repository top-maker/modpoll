# Command line

modpoll-wot checks Thing Models (TM), Thing Descriptions (TD), simulation data and verification reports offline,
and creates and exports Thing Models. It executes no Modbus requests.

```sh
modpoll-wot new --title "meter"
modpoll-wot validate meter.tm.json
modpoll-wot validate meter.tm.json --kind tm --profile
modpoll-wot export meter.tm.json --host 127.0.0.1 --port 5020 --unit-id 7 -o meter.td.json
modpoll-wot validate meter.td.json
modpoll-wot fingerprint meter.tm.json
modpoll-wot validate-report report.json --model meter.tm.json
modpoll-wot validate meter.data.json --kind data
```

Validation reports each check separately with a tick or cross and an error detail on failure. Terminal markers
are colored; redirected output has no ANSI colors, and `NO_COLOR` disables colors. The exit status is zero only
on success. Structure validation is offline and rejects duplicate JSON keys; it does not check JSON-LD,
references, device behavior or complete W3C conformance. The kind is detected from the document, so use
`--kind tm` for a known TM whose type might be missing. `--profile` checks the executable subset, accepting
instance options and `--param NAME=JSON` when needed.

`new` writes `<title>.tm.json` in the current directory by default; use `-o` to choose another path. It never
overwrites a file. The starter is a standard TM skeleton; add [profile 0.2](profile.md) mappings before
executable validation or export. Export accepts `--target node-wot-0.9.2` for the documented subset and never
overwrites files.

The loader validates the bundled W3C TM/TD 1.1 schemas, the project extension schema and acquisition semantics.
The bundled W3C schemas identify themselves as 1.1-12-March-2025, retrieved from
<https://www.w3.org/2022/wot/td-schema/v1.1> and <https://www.w3.org/2022/wot/tm-schema/v1.1>. Standard
validation does not establish device correctness.

```{argparse}
:ref: modpoll_wot.__main__.get_parser
:prog: modpoll-wot
```
