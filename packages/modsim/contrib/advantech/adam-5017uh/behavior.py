"""Synthetic raw counts, not a physical voltage/temperature conversion."""


def initialize(device):
    device.set("AI1_RAW", device.parameters.get("initial", 200))


def tick(device, elapsed, dt):
    device.set("AI1_RAW", 200 + int(elapsed) % 100)
