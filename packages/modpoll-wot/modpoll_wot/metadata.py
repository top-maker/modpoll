"""Offline device-record schema and safe YAML loading; no file-reference I/O."""

from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry
import yaml

from .validation import ModelValidationError


class _RecordLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise ModelValidationError(f"duplicate YAML key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _load_yaml(text):
    try:
        for event in yaml.parse(text):
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
                raise ModelValidationError("YAML anchors and aliases are not supported")
        return yaml.load(text, Loader=_RecordLoader)
    except (yaml.YAMLError, TypeError, RecursionError) as exc:
        raise ModelValidationError(f"invalid device YAML: {exc}") from exc


def device_schema():
    """Return the bundled metadata schema, independent of the TM/profile version."""
    resource = files("modpoll_wot").joinpath("schemas", "device-schema.yaml")
    # Hatch embeds the canonical source schema at this resource path in wheels.
    source_root = Path(__file__).resolve().parents[1]
    if not resource.is_file() and (source_root / "pyproject.toml").is_file():
        resource = source_root / "schemas/device-schema.yaml"
    text = resource.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _no_remote(uri):
    raise ModelValidationError(f"remote schema resolution is disabled: {uri}")


@lru_cache(maxsize=1)
def _device_validator():
    schema = device_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(
        schema,
        registry=Registry(retrieve=_no_remote),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def validate_device_record(document):
    """Check metadata structure only; references and license claims need review."""
    error = next(_device_validator().iter_errors(document), None)
    if error is not None:
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise ModelValidationError(f"{path}: {error.message}")


def load_device_record(path):
    """Load one local YAML record, rejecting duplicate keys, tags and aliases."""
    document = _load_yaml(Path(path).read_text(encoding="utf-8"))
    validate_device_record(document)
    return document
