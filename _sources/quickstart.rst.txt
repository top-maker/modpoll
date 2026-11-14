Quickstart
==========

Use the public Modbus TCP simulator at ``modsim.topmaker.net:502`` to try
modpoll without starting a local server:

.. code-block:: shell

    modpoll --once --tcp modsim.topmaker.net --tcp-port 502 --config https://raw.githubusercontent.com/top-maker/modpoll/main/examples/modsim.csv

Run a local simulator
---------------------

Start a local `modsim <https://github.com/top-maker/modsim>`_ simulator in one
terminal:

.. code-block:: shell

    docker run --rm -p 5020:5020 topmaker/modsim:latest

In another terminal, poll its sample data once:

.. code-block:: shell

    modpoll --once --tcp 127.0.0.1 --tcp-port 5020 --config examples/modsim.csv

The command assumes you are in the modpoll repository. You can instead provide
the published configuration URL or your own local CSV file.

The simulator's default datastore uses literal Modbus addresses:

.. csv-table:: Default simulator tables
   :header: "Table", "Access", "Addresses"
   :widths: 25, 20, 25

   "Coils", "Read/write", "0–31"
   "Discrete inputs", "Read-only", "10000–10031"
   "Input registers", "Read-only", "30000–30043"
   "Holding registers", "Read/write", "40000–40043"

Coil and discrete input blocks contain 32 bits including padding. All Unit IDs
share the default simulator datastore. See the modsim documentation for other
transports and their limitations.
