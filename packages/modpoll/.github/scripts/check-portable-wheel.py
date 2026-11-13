"""Fail if an application wheel has local URLs or an unpinned interpreter."""

import email
import re
import sys
import zipfile


def check(path):
    with zipfile.ZipFile(path) as wheel:
        metadata = [p for p in wheel.namelist() if p.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("expected one wheel metadata record")
        info = email.message_from_bytes(wheel.read(metadata[0]))
        requirements = info.get_all("Requires-Dist", [])
    if any(
        "@" in requirement or "file:" in requirement for requirement in requirements
    ):
        raise ValueError("application wheel contains a non-registry dependency")
    core = [r for r in requirements if re.match(r"modpoll[-_]wot\b", r)]
    if len(core) != 1 or not re.fullmatch(
        r"modpoll[-_]wot\s*\(?==[0-9]+\.[0-9]+\.[0-9]+(?:a|b|rc)?[0-9]*\)?", core[0]
    ):
        raise ValueError("modpoll-wot must have one exact registry version")
    print(info["Name"], info["Version"], core[0])


if __name__ == "__main__":
    check(sys.argv[1])
