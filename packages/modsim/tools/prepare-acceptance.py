"""Prepare immutable release fixtures outside Git without changing model bytes."""

from pathlib import Path
import subprocess
import sys

import yaml

TOOLS = Path(__file__).resolve().parent


def prepare(root):
    root = Path(root).resolve()
    lock = root / "examples/model-source.yaml"
    if not lock.exists():
        return  # Historical releases carry their own original contrib fixtures.
    subprocess.run(
        [
            sys.executable,
            str(TOOLS / "fetch-models.py"),
            "--lock",
            str(lock),
            "--output",
            str(root / "examples/models"),
        ],
        check=True,
    )
    manifest = root / "examples/deployment.yaml"
    document = yaml.safe_load(manifest.read_text())
    # The source example uses repository-root paths. A detached acceptance tree
    # has no Git root, so make that original base explicit in the staged copy.
    for device in document["devices"]:
        for key in ("model", "data", "script"):
            if key in device and not device[key].startswith("https://"):
                device[key] = str((root / device[key]).resolve())
    manifest.write_text(yaml.safe_dump(document, sort_keys=False))


if __name__ == "__main__":
    prepare(sys.argv[1])
