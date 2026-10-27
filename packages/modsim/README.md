# ModSim - A Simple Modbus TCP Device Simulator

*modsim* is a Modbus device simulator that can run locally or in a container. A public simulator is available at `modsim.topmaker.net:502` for quick testing.
Its default datastore contains all four Modbus tables:
- Coil Type
- Discrete input Type
- Input register Type
- Holding register Type

It is recommended to use [modpoll](https://github.com/gavinying/modpoll) tool to communicate with it, the example configuration is as following,

```
device,modsim01,1,,
poll,coil,0,16,BE_BE
ref,coil01-08,0,bool8,rw
ref,coil09-16,1,bool8,rw
poll,discrete_input,10000,16,BE_BE
ref,di01-08,10000,bool8,rw
ref,di09-16,10001,bool8,rw
poll,input_register,30000,20,BE_BE
ref,input_reg01,30000,uint16,rw
ref,input_reg02,30001,uint16,rw
ref,input_reg03,30002,uint16,rw
ref,input_reg04,30003,uint16,rw
ref,input_reg05,30004,int16,rw
ref,input_reg06,30005,int16,rw
ref,input_reg07,30006,int16,rw
ref,input_reg08,30007,int16,rw
ref,input_reg09,30008,uint32,rw
ref,input_reg10,30010,uint32,rw
ref,input_reg11,30012,int32,rw
ref,input_reg12,30014,int32,rw
ref,input_reg13,30016,float32,rw
ref,input_reg14,30018,float32,rw
poll,holding_register,40000,44,BE_BE
ref,holding_reg01,40000,uint16,rw
ref,holding_reg02,40001,uint16,rw
ref,holding_reg03,40002,uint16,rw
ref,holding_reg04,40003,uint16,rw
ref,holding_reg05,40004,int16,rw
ref,holding_reg06,40005,int16,rw
ref,holding_reg07,40006,int16,rw
ref,holding_reg08,40007,int16,rw
ref,holding_reg09,40008,uint32,rw
ref,holding_reg10,40010,uint32,rw
ref,holding_reg11,40012,int32,rw
ref,holding_reg12,40014,int32,rw
ref,holding_reg13,40016,float32,rw
ref,holding_reg14,40018,float32,rw
ref,holding_reg15,40020,uint64,rw
ref,holding_reg16,40024,int64,rw
ref,holding_reg17,40028,float64,rw
ref,holding_reg18,40032,float64,rw
ref,holding_reg19,40036,string16,rw
```

## Quick Start

A docker image has been provided for user to directly run the program,

```bash
docker run -p 5020:5020 topmaker/modsim:latest
```

The above one-line command will create a virtual Modbus TCP device running at `localhost:5020`.

To verify it, you can test by [modpoll](https://github.com/gavinying/modpoll) tool with the following command,

```bash
modpoll \
  --tcp localhost \
  --tcp-port 5020 \
  --config https://raw.githubusercontent.com/gavinying/modpoll/main/examples/modsim.csv
```

To expose the standard Modbus TCP port on the host, use `docker run -p 502:5020 topmaker/modsim:latest`. Your system may require permission to bind port 502.

## Local server behavior

Run the simulator without Docker with `python -m modsim --comm tcp --port 5020`. The default server exposes the four Modbus tables with the sample data shown above. Coil and holding-register writes are supported; discrete inputs and input registers are read-only. Requests outside an initialized address range return a Modbus exception. The server handles SIGINT and SIGTERM by stopping its listener so the port can be reused after shutdown.

The default TCP simulator uses one sequential datastore shared by all Unit IDs.
The CLI currently supports only `--store sequential`; `--slaves` and `--context`
are not implemented and are rejected. TCP and UDP use the socket framer, TLS uses
the TLS framer, and serial accepts RTU, ASCII, or binary framing. Serial requires a suitable local device and is not covered by the local protocol regression suite. TLS uses `examples/certificates/pymodbus.crt` and `pymodbus.key` relative to the working directory. A local test covers a self-signed server certificate and a verified client connection; the server does not authenticate client certificates.

UDP mode (`--comm udp`) listens on the loopback address and has local read and
shutdown coverage. TCP and UDP report a startup error if the requested port is
already in use.
