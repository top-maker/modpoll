# ModSim - A Simple Modbus TCP Device Simulator

*modsim* is a very simple Modbus TCP device simulator deployed on cloud, which populates a few registers for each type of Coil / Discrete input / Input register / Holding register. 

It is recommended to use [modpoll](https://github.com/gavinying/modpoll) to test with it, the example configuration is as following,

```
device,modsim001,1,,
poll,holding_register,40000,20,BE_BE
ref,value1,40000,uint16,rw
ref,value2,40001,uint16,rw
ref,value3,40002,uint16,rw
ref,value4,40003,uint16,rw
ref,value5,40004,int16,rw
ref,value6,40005,int16,rw
ref,value7,40006,int16,rw
ref,value8,40007,int16,rw
ref,value9,40008,uint32,rw
ref,value10,40010,uint32,rw
ref,value11,40012,int32,rw
ref,value12,40014,int32,rw
ref,value13,40016,float32,rw
ref,value14,40018,float32,rw
poll,coil,0,24,BE_BE
ref,coil1-8,0,bool,rw
ref,coil9-24,8,bool16,rw
```

## Quick Start

A docker image has been provided for user to directly run the program, 

```bash
docker run -p 5020:5020 helloysd/modsim
```

It will create a virtual Modbus TCP device running at `localhost:5020`, and then you can poll it using *modpoll* tool, 

```bash
modpoll --tcp localhost --tcp-port 5020 --config https://raw.githubusercontent.com/gavinying/modpoll/master/examples/modsim.csv
```

> Use `sudo` before the docker command if you want to use the standard port `502`.

```bash
sudo docker run -p 502:5020 helloysd/modsim
modpoll --tcp localhost --config https://raw.githubusercontent.com/gavinying/modpoll/master/examples/modsim.csv
```
