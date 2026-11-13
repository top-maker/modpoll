import copy
import unittest

from modpoll_wot import AcquisitionError, parse_acquisition


def model():
    from pathlib import Path
    import json

    d = json.loads((Path(__file__).parent / "fixtures/numeric.tm.json").read_text())
    return d


class AcquisitionTests(unittest.TestCase):
    def test_preserves_declared_group_and_hole(self):
        (group,) = parse_acquisition(model())
        self.assertEqual(
            (group.start, group.quantity, group.table), (40000, 8, "holding_register")
        )
        self.assertEqual(
            [(m.property, m.offset) for m in group.members],
            [("counter", 0), ("signed", 2), ("measurement", 4)],
        )

    def test_rejects_invalid_or_unimplemented_inputs(self):
        def duplicate(group):
            group["modpoll:members"].append(copy.deepcopy(group["modpoll:members"][0]))

        changes = [
            lambda g: g.update({"modv:quantity": 3}),
            lambda g: g.update({"modv:address": 65535}),
            lambda g: g.update({"modv:quantity": True}),
            lambda g: g.update({"modv:entity": "unknown"}),
            lambda g: g["modpoll:members"].__setitem__(0, "missing"),
            lambda g: g.update({"modpoll:scale": 2}),
            duplicate,
        ]
        for change in changes:
            with self.subTest(change=change):
                document = model()
                change(document["modpoll:acquisition"][0])
                with self.assertRaises(AcquisitionError):
                    parse_acquisition(document)


if __name__ == "__main__":
    unittest.main()
