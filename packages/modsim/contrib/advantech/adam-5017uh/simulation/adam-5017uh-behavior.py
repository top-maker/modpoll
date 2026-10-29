"""Synthetic raw words for all eight ADAM-5017UH analog input channels."""


def initialize(device):
    initial = device.parameters.get("initial", 200)
    device.set_many({f"AI{channel}_RAW": initial + channel * 1000 for channel in range(8)})


def tick(device, elapsed, dt):
    phase = int(elapsed) % 100
    device.set_many(
        {f"AI{channel}_RAW": 200 + channel * 1000 + phase for channel in range(8)}
    )
