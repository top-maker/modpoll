import copy
import unittest

from modpoll_wot import AcquisitionError, parse_acquisition


def model():
    return {
        "modpoll:version": "0.1",
        "properties": {"voltage": {"type": "number"}, "current": {"type": "number"}},
        "modpoll:acquisition": [
            {
                "modv:entity": "HoldingRegister",
                "modv:address": 40000,
                "modv:quantity": 6,
                "modv:mostSignificantByte": True,
                "modv:mostSignificantWord": True,
                "modpoll:members": [
                    {
                        "modpoll:property": "voltage",
                        "modpoll:offset": 0,
                        "modpoll:dataType": "float32",
                    },
                    {
                        "modpoll:property": "current",
                        "modpoll:offset": 4,
                        "modpoll:dataType": "float32",
                    },
                ],
            }
        ],
    }


class AcquisitionTests(unittest.TestCase):
    def test_preserves_declared_group_and_hole(self):
        (group,) = parse_acquisition(model())
        self.assertEqual(
            (group.start, group.quantity, group.table), (40000, 6, "holding_register")
        )
        self.assertEqual(
            [(m.property, m.offset) for m in group.members],
            [("voltage", 0), ("current", 4)],
        )

    def test_rejects_invalid_or_unimplemented_inputs(self):
        def duplicate(group):
            group["modpoll:members"].append(copy.deepcopy(group["modpoll:members"][0]))

        changes = [
            lambda g: g.update({"modv:quantity": 3}),
            lambda g: g.update({"modv:address": 65535}),
            lambda g: g.update({"modv:quantity": True}),
            lambda g: g.update({"modv:entity": "unknown"}),
            lambda g: g["modpoll:members"][0].update({"modpoll:property": "missing"}),
            lambda g: g["modpoll:members"][0].update({"modpoll:dataType": "unit32"}),
            lambda g: g["modpoll:members"][0].update({"modpoll:scale": 2}),
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
