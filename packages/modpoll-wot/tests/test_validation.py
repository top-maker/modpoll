import unittest

from modpoll_wot.validation import ModelValidationError, validate_standard


class StandardValidationTests(unittest.TestCase):
    def test_tm_valid(self):
        validate_standard(
            {
                "@context": "https://www.w3.org/2022/wot/td/v1.1",
                "@type": "tm:ThingModel",
                "title": "Meter",
                "properties": {"power": {"type": "number"}},
            },
            kind="tm",
        )

    def test_missing_title_rejected(self):
        with self.assertRaises(ModelValidationError):
            validate_standard(
                {"@context": "https://www.w3.org/2022/wot/td/v1.1"}, kind="tm"
            )

    def test_wrong_kind(self):
        with self.assertRaises(ValueError):
            validate_standard({}, kind="other")

    def test_td_requires_security(self):
        with self.assertRaises(ModelValidationError):
            validate_standard(
                {"@context": "https://www.w3.org/2022/wot/td/v1.1", "title": "Meter"},
                kind="td",
            )
