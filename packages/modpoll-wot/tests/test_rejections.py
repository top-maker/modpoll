"""Rejection vectors: documents another implementation must refuse as well."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from modpoll_wot import AcquisitionError
from modpoll_wot.profile import instantiate
from modpoll_wot.validation import ModelValidationError

FIXTURES = Path(__file__).parent / "fixtures"
VECTORS = json.loads((FIXTURES / "conformance.rejections.json").read_bytes())
MODEL = json.loads((FIXTURES / VECTORS["model"]).read_bytes())
# What the loader answers for each rule. A vector that is refused for another reason than its
# own rule would stop testing that rule, so the answer is part of the check.
ANSWERS = {
    "profile-version": "unsupported executable profile",
    "document-kind": "'href' is a required property",
    "placeholder-unbound": "unbound TM placeholder",
    "placeholder-malformed": "malformed TM placeholder",
    "title-blank": "title cannot be empty",
    "security-scheme": "supports only nosec",
    "root-feature": "unsupported executable profile feature",
    "root-modbus-field": "root Modbus fields are unsupported",
    "root-project-extension": "unsupported root project extension",
    "vocabulary-alias": "unsupported fixed vocabulary aliases",
    "property-protocol-metadata": "protocol metadata belongs in Forms",
    "href-invalid": "invalid concrete Modbus TCP href",
    "href-disagrees": "href disagrees with",
    "unit-id-inconsistent": "inconsistent Unit IDs",
    "span": "invalid Modbus span",
    "codec": "unsupported or redundant codec",
    "bit-raw-type": "bit extraction requires a register unsignedShort",
    "boolean-property": "invalid boolean property",
    "boolean-scalar-quantity": "scalar boolean requires quantity 1",
    "boolean-multiplier": "booleans cannot be multiplied",
    "raw-type-missing": "unsupported or missing raw type",
    "byte-length-not-string": "byteLength only applies to strings",
    "bit-packing-missing": "requires explicit legacy-msb packing",
    "bit-packing-misplaced": "bitPacking is only for",
    "quantity-width": "quantity disagrees with raw codec width",
    "media-type": "binary media parameter",
    "operation": "ambiguous or invalid operation",
    "forms-disagree": "read/write Forms disagree",
    "forms-cover-access": "Forms must cover property access",
    "read-only-table": "read-only table requires readOnly",
    "multiplier": "multiplier",
    "property-type": "property type disagrees",
    "group-span": "invalid group span",
    "group-member": "unknown or duplicate member",
    "group-member-span": "member outside group or wrong entity",
    "property-ungrouped": "exactly one acquisition group",
}


def patched(document, patch):
    """Apply the add, replace and remove operations of a JSON Patch (RFC 6902)."""
    document = deepcopy(document)
    for operation in patch:
        *parents, last = [
            token.replace("~1", "/").replace("~0", "~")
            for token in operation["path"].split("/")[1:]
        ]
        node = document
        for token in parents:
            node = node[int(token)] if isinstance(node, list) else node[token]
        if isinstance(node, list):
            index = int(last)
            if operation["op"] == "add":
                node.insert(index, operation["value"])
            elif operation["op"] == "replace":
                node[index] = operation["value"]
            else:
                del node[index]
        elif operation["op"] == "remove":
            del node[last]
        else:
            assert (last in node) == (operation["op"] == "replace"), operation
            node[last] = operation["value"]
    return document


def test_the_unchanged_model_is_accepted():
    instantiate(deepcopy(MODEL))
    instantiate(deepcopy(MODEL), host="device.example")


# A TCP host binds more placeholders but must never turn a refusal into an acceptance.
@pytest.mark.parametrize(
    "instance", [{}, {"host": "device.example"}], ids=["unbound", "tcp"]
)
@pytest.mark.parametrize(
    "vector",
    VECTORS["vectors"],
    ids=[f"{i}-{vector['rule']}" for i, vector in enumerate(VECTORS["vectors"])],
)
def test_each_vector_is_rejected_by_its_rule(vector, instance):
    document = patched(MODEL, vector["patch"])
    with pytest.raises(AcquisitionError) as refusal:
        instantiate(document, **instance)
    if vector["rule"] == "schema":
        assert isinstance(refusal.value, ModelValidationError)
    else:
        assert ANSWERS[vector["rule"]] in str(refusal.value)


def test_every_rule_has_a_vector():
    assert {vector["rule"] for vector in VECTORS["vectors"]} == {*ANSWERS, "schema"}
