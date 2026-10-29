# Model-driven simulator validation

The `v2` development branch has a candidate `--config` path for profile 0.2 TM
and TD documents. The shared `modpoll-wot` interpreter detects the document type
from its contents. This first slice supports TCP, native uint16/int16 values and
scalar physical booleans. Scaling, extracted register bits and wider types are
not supported yet. Unsupported models fail before the listener starts.

## Prepare an isolated candidate environment

The candidate SDK is not yet a published consumer dependency. Keep this local
validation environment separate from the normal installation. Run these commands
from sibling `modpoll` and `modsim` checkouts on `v2`:

```sh
cd /path/to/modpoll/packages/modpoll-wot
mise exec -- poetry build
cd /path/to/modsim
mise exec -- python -m venv /tmp/adam5017-modsim-env
mise exec -- /tmp/adam5017-modsim-env/bin/python -m pip install \
  ../modpoll/packages/modpoll-wot/dist/modpoll_wot-0.2.0a1-py3-none-any.whl \
  pymodbus==3.16.1
```

## Start the ADAM-5017UH simulator

From the modsim repository:

```sh
PYTHONPATH="$PWD" mise exec -- /tmp/adam5017-modsim-env/bin/python -m modsim \
  --config examples/adam-5017uh/adam-5017uh-slot-0.tm.json \
  --initial-file examples/adam-5017uh/demo-initial.json \
  --bind 127.0.0.1 --port 15020 --unit-id 1
```

The fixture declares slot 0, eight read-only input registers at PDU addresses
1–8. Its initial values are synthetic raw counts 1000, 2000, …, 8000; they do
not assert a manufacturer's voltage/current range or ADC encoding.

`--bind` controls the listener, independently of the document's remote endpoint.
A configured listener defaults to loopback. `--initial NAME=JSON` or
`--initial-file` supplies values by property name. Otherwise initialization uses
`const`, `default`, `enum`, then a type/constraint-valid synthetic fallback.
Unknown names, duplicate overrides and invalid values fail startup.

## Read with modpoll

In another terminal, from the modpoll repository:

```sh
PYTHONPATH="$PWD/packages/modpoll-wot" mise exec -- poetry run python -m modpoll \
  --config ../modsim/examples/adam-5017uh/adam-5017uh-slot-0.tm.json \
  --tcp 127.0.0.1 --tcp-port 15020 --unit-id 1 \
  --once --interval 0 --export /tmp/adam5017-virtual.json
cat /tmp/adam5017-virtual.json
```

Expect `AI0_RAW` through `AI7_RAW` to contain 1000 through 8000. Replace the TM
filename with `adam-5017uh-slot-0.generated.td.json` to check the generated TD.
Each poll reads the eight input registers in one FC4 request.

The model-driven context rejects unconfigured tables/addresses, out-of-block
requests and writes to read-only addresses. ADAM-5017UH exposes input registers;
Modbus defines no write operation for that table. Virtual negative tests against
unconfigured holding registers use FC6/FC16, and must not be copied to hardware:
the same addresses in another table could control device settings.

## Read hardware manually

Set `ADAM_HOST` to your device address and confirm its TCP port and Unit ID.
From the modpoll repository, use the same TM:

```sh
PYTHONPATH="$PWD/packages/modpoll-wot" mise exec -- poetry run python -m modpoll \
  --config ../modsim/examples/adam-5017uh/adam-5017uh-slot-0.tm.json \
  --tcp "$ADAM_HOST" --tcp-port 502 --unit-id 1 \
  --once --interval 0 --export /tmp/adam5017-real.json
```

Hardware values will differ from the synthetic values. Compare raw words with
the vendor utility and verify the channel range/data format before interpreting
physical units. A successful simulator run does not validate the hardware map.
Stop the simulator with Ctrl+C when finished.
