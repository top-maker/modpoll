"""Docker readiness must survive a socket proxy becoming ready first."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock


spec = importlib.util.spec_from_file_location(
    "acceptance", Path(__file__).resolve().parents[1] / "tools/preview-acceptance.py"
)
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def test_connection_reset_during_readiness_reconnects(monkeypatch):
    client = Mock()
    client.connect.return_value = True
    ready = Mock(registers=[0] * 8)
    ready.isError.return_value = False
    input_value = Mock(registers=[432])
    input_value.isError.return_value = False
    missing = Mock()
    missing.isError.return_value = True
    client.read_input_registers.side_effect = [
        ConnectionResetError(),
        ready,
        input_value,
        missing,
    ]
    client.write_register.return_value.isError.return_value = False
    client.write_coil.return_value.isError.return_value = False
    client.read_discrete_inputs.return_value.bits = [True]
    monkeypatch.setattr(acceptance, "ModbusTcpClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(acceptance.time, "sleep", lambda duration: None)
    acceptance.main()
    assert client.connect.call_count == 2
    assert client.close.call_count == 2
