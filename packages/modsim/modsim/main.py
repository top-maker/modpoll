#!/usr/bin/env python3
"""Modbus simulator server and process lifecycle."""

import os
import json
import ssl
import asyncio
import signal
import logging
from contextlib import suppress
from typing import Any

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.pdu.device import ModbusDeviceIdentification
from pymodbus.server import (
    StartAsyncSerialServer,
    ModbusTcpServer,
    ModbusTlsServer,
    ModbusUdpServer,
    ServerAsyncStop,
)

from . import __version__
from .compat import BinaryPayloadBuilder, Endian
from .utils import get_commandline, get_utc_time, get_logger

_logger = logging.getLogger(__name__)


def setup_server(args: Any) -> Any:
    """Run server setup."""
    # The datastores only respond to the addresses that are initialized
    # If you initialize a DataBlock to addresses of 0x00 to 0xFF, a request to
    # 0x100 will respond with an invalid address exception.
    # This is because many devices exhibit this kind of behavior (but not all)
    if getattr(args, "config", None):
        from .wot import configure

        args.context = configure(args)
        _logger.info(
            "Model initialization: %s",
            json.dumps(args.model_initialization, sort_keys=True),
        )
    if not args.context:
        _logger.info("Create datastore")
        # build your payload
        co_builder = BinaryPayloadBuilder(byteorder=Endian.BIG, wordorder=Endian.BIG)
        # address=0, bytes=3
        for _ in range(3):
            # The bits within each byte are big-endian
            # The coils status (from the first position) = [1,0,1,0,0,0,0,1]
            co_builder.add_bits([True, False, True, False, False, False, False, True])

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
        hr_builder.add_string("this is a string")

        # use that payload in the data store
        co_values = co_builder.to_coils()
        hr_values = hr_builder.to_registers()
        # Note: In PyModbus 3.16.1+, ModbusSequentialDataBlock uses address - 1 internally
        # to convert to SimData. To maintain address ranges, we use address + 1 here.
        # This maps Modbus addresses the same way as zero_mode=True did in older versions.
        device_context = ModbusDeviceContext(
            co=ModbusSequentialDataBlock(1, co_values),
            di=ModbusSequentialDataBlock(10001, co_values),
            ir=ModbusSequentialDataBlock(30001, hr_values),
            hr=ModbusSequentialDataBlock(40001, hr_values),
        )
        args.context = ModbusServerContext(devices=device_context, single=True)

    # initialize the server information
    # If you don't set this or any fields, they are defaulted to empty strings.
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
    txt = f"Start ASYNC server, listening on {args.port} - {args.comm}"
    _logger.info(txt)
    server: Any
    if args.comm == "tcp":
        address: tuple[str, int] = (
            getattr(args, "bind", None)
            or ("127.0.0.1" if getattr(args, "config", None) else ""),
            args.port,
        )
        server = ModbusTcpServer(
            context=args.context,
            identity=args.identity,
            address=address,
            framer=args.framer,
        )
        if hasattr(args, "model_access"):
            from .wot import GuardedContext

            server.context = GuardedContext(server.context, args.model_access)
        try:
            if not await server.listen():
                raise OSError(
                    "Could not start Modbus TCP listener on port %s" % args.port
                )
            await server.serving
        finally:
            await server.shutdown()
        return server
    elif args.comm == "udp":
        address = ("127.0.0.1", args.port)
        server = ModbusUdpServer(
            context=args.context,
            identity=args.identity,
            address=address,
            framer=args.framer,
        )
        try:
            if not await server.listen():
                raise OSError(
                    "Could not start Modbus UDP listener on port %s" % args.port
                )
            await server.serving
        finally:
            await server.shutdown()
        return server
    elif args.comm == "serial":
        await StartAsyncSerialServer(
            context=args.context,
            identity=args.identity,
            port=args.port,
            framer=args.framer,
        )
        return None
    elif args.comm == "tls":
        address = ("", args.port)
        cwd = os.getcwd().split("/")[-1]
        if cwd == "examples":
            path = "."
        elif cwd == "test":
            path = "../examples"
        else:
            path = "examples"

        # Create SSL context from cert and key files
        sslctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        sslctx.load_cert_chain(
            certfile=f"{path}/certificates/pymodbus.crt",
            keyfile=f"{path}/certificates/pymodbus.key",
        )

        server = ModbusTlsServer(
            context=args.context,
            identity=args.identity,
            address=address,
            framer=args.framer,
            sslctx=sslctx,
        )
        try:
            if not await server.listen():
                raise OSError(
                    "Could not start Modbus TLS listener on port %s" % args.port
                )
            await server.serving
        finally:
            await server.shutdown()
        return server
    raise ValueError(f"Unknown communication type: {args.comm}")


def app() -> None:
    args = get_commandline()
    global _logger
    _logger = get_logger(args.log)
    _logger.info(
        f"Starting modsim v{__version__} at {get_utc_time().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    try:
        run_args = setup_server(args)
    except ValueError as exc:
        _logger.error("Invalid model configuration: %s", exc)
        raise SystemExit(2) from exc
    asyncio.run(_run_server_with_signals(run_args), debug=True)

    _logger.info("exiting.")


async def _run_server_with_signals(args: Any) -> None:
    """Run the server and close its listener when the process is signaled."""
    loop = asyncio.get_running_loop()
    server_task = asyncio.create_task(run_async_server(args))
    stop_requested = False

    async def stop_server() -> None:
        for _ in range(100):
            if server_task.done():
                return
            try:
                await ServerAsyncStop()
                return
            except (AttributeError, RuntimeError):
                await asyncio.sleep(0.01)

    def request_stop() -> None:
        nonlocal stop_requested
        if not stop_requested:
            stop_requested = True
            if args.comm in ("tcp", "udp", "tls"):
                server_task.cancel()
            else:
                loop.create_task(stop_server())

    installed_signals = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, request_stop)
            installed_signals.append(signum)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await server_task
    except asyncio.CancelledError:
        if not stop_requested:
            raise
    finally:
        for signum in installed_signals:
            loop.remove_signal_handler(signum)
        if not server_task.done():
            server_task.cancel()
            with suppress(asyncio.CancelledError):
                await server_task


if __name__ == "__main__":
    app()
