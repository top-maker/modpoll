"""Prepare bounded, hash-verified public example inputs; never execute them."""

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlparse
from urllib.request import urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2 * 1024 * 1024


def fetch(lock_path, destination):
    lock = yaml.safe_load(Path(lock_path).read_text())
    if not re.fullmatch(r"[0-9a-f]{40}", lock["revision"]):
        raise ValueError("Catalog revision must be a full commit SHA")
    if not re.fullmatch(r"[\w-]+/[\w.-]+", lock["repository"]):
        raise ValueError("Invalid public repository")
    destination = Path(destination).resolve()
    pending = []
    for name, digest in lock["files"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("Catalog path must remain relative")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid content hash")
        target = destination / name
        if not target.resolve().is_relative_to(destination):
            raise ValueError("Catalog destination leaves output directory")
        url = f"https://raw.githubusercontent.com/{lock['repository']}/{lock['revision']}/{name}"
        with urlopen(url, timeout=20) as response:
            if urlparse(response.geturl()).scheme != "https":
                raise ValueError("Catalog redirects must use HTTPS")
            payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES or hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError(f"Catalog content/hash mismatch: {name}")
        pending.append((target, payload))
    if not pending:
        raise ValueError("No locked input files")
    # Verify every input before replacing any existing example file.
    for target, payload in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return [str(target) for target, _ in pending]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock", type=Path, default=ROOT / "examples/model-source.yaml"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "examples/models")
    args = parser.parse_args()
    paths = fetch(args.lock, args.output)
    print(f"Prepared {len(paths)} verified files; no scripts executed")


if __name__ == "__main__":
    main()
