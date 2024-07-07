# ModSim - A Simple Modbus TCP Device Simulator

*modsim* is a simple Modbus TCP device simulator deployed at `modsim.topmaker.net:502`.
It works as a remote Modbus-TCP (virtual) device, which has already been populated with all 4 types of registers, i.e.
- Coil Type
- Discrete input Type
- Input register Type
- Holding register Type

It is recommended to use [modpoll](https://github.com/gavinying/modpoll) tool to communicate with it, the example configuration is as following,

```
device,modsim001,1,,
poll,coil,0,12,BE_BE
ref,coil01-08,0,bool8,rw
ref,coil09-12,1,bool8,rw
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
poll,holding_register,40000,20,BE_BE
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
```

## Quick Start

A docker image has been provided for user to directly run the program,

```bash
docker run -p 5020:5020 helloysd/modsim:latest
```

The above one-line command will create a virtual Modbus TCP device running at `localhost:5020`.

To verify it, you can test by [modpoll](https://github.com/gavinying/modpoll) tool with the following command,

```bash
modpoll \
  --tcp localhost \
  --tcp-port 5020 \
  --config https://raw.githubusercontent.com/gavinying/modpoll/master/examples/modsim.csv
```

> **_Note_**: add `sudo` before `docker run` command if you want to use the Modbus TCP standard port `502`.
