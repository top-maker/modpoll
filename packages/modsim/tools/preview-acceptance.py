"""Protocol readiness and two-device loopback check for the published container."""

import time

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException


def main():
    client = ModbusTcpClient("127.0.0.1", port=5020, timeout=1, retries=0)
    deadline = time.monotonic() + 30
    try:
        while True:
            try:
                if client.connect():
                    response = client.read_input_registers(1, count=8, device_id=1)
                    if not response.isError():
                        break
            except (OSError, ModbusException):
                # Docker's proxy may accept a socket before the application is
                # listening. Reconnect until an actual Modbus response arrives.
                client.close()
            if time.monotonic() >= deadline:
                raise RuntimeError("published container failed protocol readiness")
            time.sleep(0.1)
        assert len(response.registers) == 8
        assert not client.write_register(10, 432, device_id=2).isError()
        assert client.read_input_registers(0, device_id=2).registers == [432]
        assert not client.write_coil(16, True, device_id=2).isError()
        assert client.read_discrete_inputs(0, device_id=2).bits[0]
        assert client.read_input_registers(0, device_id=3).isError()
        print("Published image: two isolated Unit IDs and I/O loopback passed")
    finally:
        client.close()


if __name__ == "__main__":
    main()
