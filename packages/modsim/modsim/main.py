#!/usr/bin/env python3
"""Pymodbus asynchronous Server Example.
An example of a multi threaded asynchronous server.
usage: server_async.py [-h] [--comm {tcp,udp,serial,tls}]
                       [--framer {ascii,binary,rtu,socket,tls}]
                       [--log {critical,error,warning,info,debug}]
                       [--port PORT] [--store {sequential,sparse,factory,none}]
                       [--slaves SLAVES]
Command line options for examples
options:
  -h, --help            show this help message and exit
  --comm {tcp,udp,serial,tls}
                        "serial", "tcp", "udp" or "tls"
  --framer {ascii,binary,rtu,socket,tls}
                        "ascii", "binary", "rtu", "socket" or "tls"
  --log {critical,error,warning,info,debug}
                        "critical", "error", "warning", "info" or "debug"
  --port PORT           the port to use
  --store {sequential,sparse,factory,none}
                        "sequential", "sparse", "factory" or "none"
  --slaves SLAVES       number of slaves to respond to
The corresponding client can be started as:
    python3 client_sync.py
"""

import os
import asyncio
from typing import Any

from pymodbus.constants import Endian
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
    ModbusSparseDataBlock,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.server import (
    StartAsyncSerialServer,
    StartAsyncTcpServer,
    StartAsyncTlsServer,
    StartAsyncUdpServer,
)

from .utils import __version__, get_commandline, get_utc_time, get_logger

_logger = get_logger()


def setup_server(args: Any) -> Any:
    """Run server setup."""
    # The datastores only respond to the addresses that are initialized
    # If you initialize a DataBlock to addresses of 0x00 to 0xFF, a request to
    # 0x100 will respond with an invalid address exception.
    # This is because many devices exhibit this kind of behavior (but not all)
    if not args.context:
        _logger.info("### Create datastore")
        # ----------------------------------------------------------------------- #
        # build your payload
        # ----------------------------------------------------------------------- #
        co_builder = BinaryPayloadBuilder(byteorder=Endian.BIG, wordorder=Endian.BIG)
        # address=0, bytes=3
        for i in range(3):
            # The bits within each byte are big-endian
            # The coils status (from the first position) = [1,0,1,0,0,0,0,1]
            co_builder.add_bits([True, False, False, False, False, True, False, True])

        hr_builder = BinaryPayloadBuilder(byteorder=Endian.BIG, wordorder=Endian.BIG)
        # address=0, bytes=8
        hr_builder.add_16bit_uint(1)
        hr_builder.add_16bit_uint(2)
        hr_builder.add_16bit_uint(3)
        hr_builder.add_16bit_uint(4)
        # address=8, bytes=8
        hr_builder.add_16bit_int(-1)
        hr_builder.add_16bit_int(-2)
        hr_builder.add_16bit_int(-3)
        hr_builder.add_16bit_int(-4)
        # address=16, bytes=8
        hr_builder.add_32bit_uint(12345678)
        hr_builder.add_32bit_uint(12345678)
        # address=24, bytes=8
        hr_builder.add_32bit_int(-12345678)
        hr_builder.add_32bit_int(-12345678)
        # address=32, bytes=8
        hr_builder.add_32bit_float(12.34)
        hr_builder.add_32bit_float(-12.34)
        # address=40, bytes=8
        hr_builder.add_64bit_uint(12345678900)
        # address=48, bytes=8
        hr_builder.add_64bit_int(-12345678900)
        # address=56, bytes=16
        hr_builder.add_64bit_float(123.45)
        hr_builder.add_64bit_float(-123.45)
        # address=72, bytes=?
        hr_builder.add_string("abcdefgh")

        # ----------------------------------------------------------------------- #
        # use that payload in the data store
        # ----------------------------------------------------------------------- #
        # Here we use the same reference block for each underlying store.
        # ----------------------------------------------------------------------- #
        co_values = co_builder.to_coils()
        hr_values = hr_builder.to_registers()
        store = ModbusSlaveContext(
            co=ModbusSequentialDataBlock(0, co_values),
            di=ModbusSequentialDataBlock(10000, co_values),
            ir=ModbusSequentialDataBlock(30000, hr_values),
            hr=ModbusSequentialDataBlock(40000, hr_values),
            zero_mode=True,
        )
        args.context = ModbusServerContext(slaves=store, single=True)

    # ----------------------------------------------------------------------- #
    # initialize the server information
    # ----------------------------------------------------------------------- #
    # If you don't set this or any fields, they are defaulted to empty strings.
    # ----------------------------------------------------------------------- #
    args.identity = ModbusDeviceIdentification(
        info_name={
            "VendorName": "Pymodbus",
            "ProductCode": "PM",
            "VendorUrl": "https://github.com/riptideio/pymodbus/",
            "ProductName": "Pymodbus Server",
            "ModelName": "Pymodbus Server",
        }
    )
    return args


async def run_async_server(args: Any) -> Any:
    """Run server."""
    txt = f"### start ASYNC server, listening on {args.port} - {args.comm}"
    _logger.info(txt)
    if args.comm == "tcp":
        address = ("", args.port) if args.port else None
        server = await StartAsyncTcpServer(
            context=args.context,  # Data storage
            identity=args.identity,  # server identify
            # TBD host=
            # TBD port=
            address=address,  # listen address
            # custom_functions=[],  # allow custom handling
            framer=args.framer,  # The framer strategy to use
            # ignore_missing_slaves=True,  # ignore request to a missing slave
            # broadcast_enable=False,  # treat slave_id 0 as broadcast address,
            # timeout=1,  # waiting time for request to complete
            # TBD strict=True,  # use strict timing, t1.5 for Modbus RTU
        )
    elif args.comm == "udp":
        address = ("127.0.0.1", args.port) if args.port else None
        server = await StartAsyncUdpServer(
            context=args.context,  # Data storage
            identity=args.identity,  # server identify
            address=address,  # listen address
            # custom_functions=[],  # allow custom handling
            framer=args.framer,  # The framer strategy to use
            # handler=None,  # handler for each session
            # ignore_missing_slaves=True,  # ignore request to a missing slave
            # broadcast_enable=False,  # treat unit_id 0 as broadcast address,
            # timeout=1,  # waiting time for request to complete
            # TBD strict=True,  # use strict timing, t1.5 for Modbus RTU
            # defer_start=False,  # Only define server do not activate
        )
    elif args.comm == "serial":
        # socat -d -d PTY,link=/tmp/ptyp0,raw,echo=0,ispeed=9600
        #             PTY,link=/tmp/ttyp0,raw,echo=0,ospeed=9600
        server = await StartAsyncSerialServer(
            context=args.context,  # Data storage
            identity=args.identity,  # server identify
            # timeout=1,  # waiting time for request to complete
            port=args.port,  # serial port
            # custom_functions=[],  # allow custom handling
            framer=args.framer,  # The framer strategy to use
            # handler=None,  # handler for each session
            # stopbits=1,  # The number of stop bits to use
            # bytesize=8,  # The bytesize of the serial messages
            # parity="N",  # Which kind of parity to use
            # baudrate=9600,  # The baud rate to use for the serial device
            # handle_local_echo=False,  # Handle local echo of the USB-to-RS485 adaptor
            # ignore_missing_slaves=True,  # ignore request to a missing slave
            # broadcast_enable=False,  # treat unit_id 0 as broadcast address,
            # strict=True,  # use strict timing, t1.5 for Modbus RTU
            # defer_start=False,  # Only define server do not activate
        )
    elif args.comm == "tls":
        address = ("", args.port) if args.port else None
        cwd = os.getcwd().split("/")[-1]
        if cwd == "examples":
            path = "."
        elif cwd == "test":
            path = "../examples"
        else:
            path = "examples"
        server = await StartAsyncTlsServer(
            context=args.context,  # Data storage
            host="localhost",  # define tcp address where to connect to.
            # port=port,  # on which port
            identity=args.identity,  # server identify
            # custom_functions=[],  # allow custom handling
            address=address,  # listen address
            framer=args.framer,  # The framer strategy to use
            # handler=None,  # handler for each session
            allow_reuse_address=True,  # allow the reuse of an address
            # The cert file path for TLS (used if sslctx is None)
            certfile=f"{path}/certificates/pymodbus.crt",
            # sslctx=sslctx,  # The SSLContext to use for TLS (default None and auto create)
            # The key file path for TLS (used if sslctx is None)
            keyfile=f"{path}/certificates/pymodbus.key",
            # password="none",  # The password for for decrypting the private key file
            # reqclicert=False,  # Force the sever request client"s certificate
            # ignore_missing_slaves=True,  # ignore request to a missing slave
            # broadcast_enable=False,  # treat unit_id 0 as broadcast address,
            # timeout=1,  # waiting time for request to complete
            # TBD strict=True,  # use strict timing, t1.5 for Modbus RTU
            defer_start=False,  # Only define server do not activate
        )
    return server


def app() -> None:
    _logger.info(
        f"Start modsim v{__version__} at {get_utc_time().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    run_args = setup_server(get_commandline())
    asyncio.run(run_async_server(run_args), debug=True)

    _logger.info("exiting.")


if __name__ == "__main__":
    app()
