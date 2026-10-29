"""Deployment v2: bounded YAML, TM instantiation and immutable input snapshots."""

from argparse import Namespace
from dataclasses import dataclass
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from jsonschema import Draft7Validator  # type: ignore[import-untyped]
from modpoll_wot import export_td, parse_model  # type: ignore[import-untyped]
from modpoll_wot.loading import MAX_BYTES, load_document  # type: ignore[import-untyped]

from .deployment import SCENARIO, STRING, obj
from .sources import local_path, model_document


class DeploymentLoader(yaml.SafeLoader):  # type: ignore[no-any-unimported]
    """Reject aliases and duplicate keys rather than expanding ambiguous YAML."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise ValueError("YAML aliases are unsupported")
        depth = getattr(self, "deployment_depth", 0)
        if depth >= 64:
            raise ValueError("deployment nesting exceeds 64 containers")
        self.deployment_depth = depth + 1
        try:
            return super().compose_node(parent, index)
        finally:
            self.deployment_depth = depth

    def construct_mapping(self, node: Any, deep: bool = False) -> dict:
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ValueError("YAML object keys must be strings")
            if key in result:
                raise ValueError(f"duplicate YAML key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


IDENTIFIER = {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,63}$"}
MANIFEST = obj(
    {
        "version": {"const": 2},
        "name": IDENTIFIER,
        "server": obj(
            {
                "bind": STRING,
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
            }
        ),
        "devices": {
            "type": "array",
            "maxItems": 254,
            "items": obj(
                {
                    "id": IDENTIFIER,
                    "model": STRING,
                    "parameters": {"type": "object"},
                    "scenario": STRING,
                },
                ("id", "model"),
            ),
        },
    },
    ("version", "devices"),
)


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def read_yaml(path: Path) -> dict:
    """Read JSON or safe YAML with bounded size, depth and JSON-compatible values."""
    if path.suffix.lower() == ".json":
        value = load_document(path)
    else:
        with path.open("rb") as stream:
            payload = stream.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("deployment exceeds 1 MiB")
        try:
            value = yaml.load(payload, Loader=DeploymentLoader)
        except yaml.YAMLError as exc:
            raise ValueError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    try:
        canonical(value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{path}: expected finite JSON-compatible values") from exc
    return value


def validate(value: dict, schema: dict) -> None:
    errors = sorted(
        Draft7Validator(schema).iter_errors(value), key=lambda e: str(e.path)
    )
    if errors:
        error = errors[0]
        raise ValueError(f"{'/'.join(map(str, error.path))}: {error.message}")


@dataclass
class Instance:
    id: str
    td: dict
    model: Any
    fingerprint: str
    scenario: dict
    script_path: str | None
    script_source: bytes | None

    def build(self, allow_scripts: bool = False, *, preview: bool = False) -> Any:
        """Construct isolated state from this snapshot, without reopening inputs."""
        from .deployment import apply_scenario
        from .wot import configure

        if self.script_source is not None:
            if not allow_scripts:
                raise ValueError("Python behavior scripts require --allow-scripts")
            if preview:
                compile(self.script_source, self.script_path or "<behavior>", "exec")
        args = Namespace(
            prepared_model=self.model,
            initial_file=None,
            initial=[],
            scenario=None,
            scenario_spec=copy.deepcopy(self.scenario),
            script=None if preview else self.script_path,
            script_source=self.script_source,
            allow_scripts=allow_scripts,
        )
        configure(args)
        args.runtime.name = self.id
        apply_scenario(args)
        return args.runtime


@dataclass
class Deployment:
    path: Path
    name: str
    bind: str
    port: int
    instances: dict[str, Instance]


def deployment_root(path: Path) -> Path:
    """Use the repository root for checked-in examples, config directory otherwise."""
    for parent in path.parent.parents:
        if (parent / ".git").exists():
            return parent
    if (path.parent / ".git").exists():
        return path.parent
    return path.parent


def load_deployment(path: Path, *, include_scenarios: bool = True) -> Deployment:
    """Resolve and validate every instance before the runtime can be changed."""
    path = path.resolve()
    if path.suffix.lower() not in (".yaml", ".yml"):
        raise ValueError("deployment file must use .yaml or .yml")
    spec = read_yaml(path)
    validate(spec, MANIFEST)
    name = spec.get("name", path.parent.name)
    validate({"name": name}, obj({"name": IDENTIFIER}, ("name",)))
    bind = spec.get("server", {}).get("bind", "127.0.0.1")
    port = spec.get("server", {}).get("port", 5020)
    root = deployment_root(path)
    instances: dict[str, Instance] = {}
    units: set[int] = set()
    identities: set[str] = set()
    for item in spec["devices"]:
        key = item["id"]
        if key in instances:
            raise ValueError(f"duplicate device id: {key}")
        source = item["model"]
        if not source.startswith("https://"):
            source = local_path(root, source)
        document = model_document(source)
        if not isinstance(document, dict):
            raise ValueError(f"{key}: model must be an object")
        types = document.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if "tm:ThingModel" not in types:
            raise ValueError(f"{key}: deployment v2 requires a TM; use --config for TD")
        parameters = dict(item.get("parameters", {}))
        if "AUTHORITY" in parameters:
            raise ValueError(
                "use HOST and PORT; AUTHORITY is derived by the interpreter"
            )
        # A TM need not declare a Thing ID. An explicit instance binding may
        # provide it without changing the reusable model or inventing identity.
        if "THING_ID" in parameters and "id" not in document:
            document = copy.deepcopy(document)
            document["id"] = "{{THING_ID}}"
        host = parameters.pop("HOST", None)
        if host is None:
            if bind in ("0.0.0.0", "::", "*"):
                raise ValueError(f"{key}: wildcard listener requires parameters.HOST")
            host = bind
        instance_port = parameters.pop("PORT", port)
        unit = parameters.pop("UNIT_ID", None)
        if not isinstance(host, str):
            raise ValueError(f"{key}: HOST must be a string")
        td = export_td(
            document, host=host, port=instance_port, unit_id=unit, parameters=parameters
        )
        if len(canonical(td)) > MAX_BYTES:
            raise ValueError(f"{key}: generated TD exceeds 1 MiB")
        model = parse_model(td)
        identity = td.get("id")
        if not isinstance(identity, str) or not identity:
            raise ValueError(f"{key}: TM must instantiate a stable TD id")
        if identity in identities or model.unit_id in units:
            raise ValueError(f"{key}: duplicate TD id or Unit ID")
        units.add(model.unit_id)
        identities.add(identity)
        scenario = {}
        script_path, script_source = None, None
        if include_scenarios and item.get("scenario"):
            scene_path = Path(local_path(root, item["scenario"]))
            scenario = read_yaml(scene_path)
            validate(scenario, SCENARIO)
            if scenario.get("script"):
                script_path = local_path(scene_path.parent, scenario["script"])
                with Path(script_path).open("rb") as stream:
                    script_source = stream.read(MAX_BYTES + 1)
                if len(script_source) > MAX_BYTES:
                    raise ValueError("script exceeds 1 MiB")
                # Resolved script is supplied separately to apply_scenario.
                scenario = {k: v for k, v in scenario.items() if k != "script"}
        fingerprint = hashlib.sha256(
            canonical([item, document, td, scenario, script_path])
            + (script_source or b"")
        ).hexdigest()
        instances[key] = Instance(
            key, td, model, fingerprint, scenario, script_path, script_source
        )
    return Deployment(path, name, bind, port, instances)
