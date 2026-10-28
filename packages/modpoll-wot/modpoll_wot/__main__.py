"""Validate a concrete executable TM/TD without contacting a device."""

import argparse
import json
import sys

from . import AcquisitionError, load_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("--unit-id", type=int, default=None)
    args = parser.parse_args()
    try:
        model = load_model(args.model, unit_id=args.unit_id)
    except AcquisitionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "title": model.title,
                "kind": model.kind,
                "unit_id": model.unit_id,
                "groups": len(model.groups),
                "properties": sum(len(g.members) for g in model.groups),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
