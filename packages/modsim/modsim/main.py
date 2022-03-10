from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.server.asynchronous import StartTcpServer
from pymodbus.server.asynchronous import StartUdpServer
from pymodbus.server.asynchronous import StartSerialServer

from pymodbus.device import ModbusDeviceIdentification
from pymodbus.datastore import ModbusSequentialDataBlock
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext

from . import __version__

# --------------------------------------------------------------------------- # 
# configure the service logging
# --------------------------------------------------------------------------- # 
import logging

FORMAT = ('%(asctime)-15s %(threadName)-15s'
          ' %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
logging.basicConfig(format=FORMAT)
log = logging.getLogger()
log.setLevel(logging.DEBUG)

log.info(f"====== Start modsim v{__version__} ======")


def app():
    # ----------------------------------------------------------------------- #
    # build your payload
    # ----------------------------------------------------------------------- #
    coil_builder = BinaryPayloadBuilder(byteorder=Endian.Big,
                                        wordorder=Endian.Big)
    # address=0, bytes=8
    for i in range(8):
        coil_builder.add_bits([0, 1, 0, 1, 1, 0, 1, 0])

    builder = BinaryPayloadBuilder(byteorder=Endian.Big,
                                   wordorder=Endian.Big)
    # address=0, bytes=8
    builder.add_16bit_uint(1)
    builder.add_16bit_uint(2)
    builder.add_16bit_uint(3)
    builder.add_16bit_uint(4)
    # address=8, bytes=8
    builder.add_16bit_int(-1)
    builder.add_16bit_int(-2)
    builder.add_16bit_int(-3)
    builder.add_16bit_int(-4)
    # address=16, bytes=8
    builder.add_32bit_uint(12345678)
    builder.add_32bit_uint(12345678)
    # address=24, bytes=8
    builder.add_32bit_int(-12345678)
    builder.add_32bit_int(-12345678)
    # address=32, bytes=8
    builder.add_32bit_float(12.34)
    builder.add_32bit_float(-12.34)
    # address=40, bytes=8
    builder.add_64bit_uint(12345678900)
    # address=48, bytes=8
    builder.add_64bit_int(-12345678900)
    # address=56, bytes=16
    builder.add_64bit_float(123.45)
    builder.add_64bit_float(-123.45)
    # address=72, bytes=?
    builder.add_string('abcdefgh')

    # ----------------------------------------------------------------------- #
    # use that payload in the data store
    # ----------------------------------------------------------------------- #
    # Here we use the same reference block for each underlying store.
    # ----------------------------------------------------------------------- #

    co_values = coil_builder.to_registers()
    hr_values = builder.to_registers()
    store = ModbusSlaveContext(
        co=ModbusSequentialDataBlock(0, co_values),
        di=ModbusSequentialDataBlock(10000, co_values),
        ir=ModbusSequentialDataBlock(30000, hr_values),
        hr=ModbusSequentialDataBlock(40000, hr_values),
        zero_mode=True)
    context = ModbusServerContext(slaves=store, single=True)

    # ----------------------------------------------------------------------- #
    # initialize the server information
    # ----------------------------------------------------------------------- # 
    # If you don't set this or any fields, they are defaulted to empty strings.
    # ----------------------------------------------------------------------- # 
    identity = ModbusDeviceIdentification()
    identity.VendorName = 'helloysd'
    identity.ProductCode = 'modsim'
    identity.VendorUrl = 'https://gitlab.com/helloysd/modpoll'
    identity.ProductName = 'Modbus Simulator'
    identity.ModelName = 'Modbus Simulator'
    identity.MajorMinorRevision = __version__

    # ----------------------------------------------------------------------- # 
    # run the server you want
    # ----------------------------------------------------------------------- # 

    # TCP Server

    StartTcpServer(context, identity=identity, address=("", 5020))

    # TCP Server with deferred reactor run

    # from twisted.internet import reactor
    # StartTcpServer(context, identity=identity, address=("localhost", 5020),
    #                defer_reactor_run=True)
    # reactor.run()

    # Server with RTU framer
    # StartTcpServer(context, identity=identity, address=("localhost", 5020),
    #                framer=ModbusRtuFramer)

    # UDP Server
    # StartUdpServer(context, identity=identity, address=("127.0.0.1", 5020))

    # RTU Server
    # StartSerialServer(context, identity=identity,
    #                   port='/dev/ttyp0', framer=ModbusRtuFramer)

    # ASCII Server
    # StartSerialServer(context, identity=identity,
    #                   port='/dev/ttyp0', framer=ModbusAsciiFramer)

    # Binary Server
    # StartSerialServer(context, identity=identity,
    #                   port='/dev/ttyp0', framer=ModbusBinaryFramer)


if __name__ == "__main__":
    app()
