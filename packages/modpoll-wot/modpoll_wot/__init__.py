"""Modpoll's versioned executable subset of WoT TM/TD and Modbus metadata.

Consumers import from this package only; its submodules are not a public interface.
"""

from importlib.metadata import version as _version

from .acquisition import AcquisitionError, Group, Member, parse_acquisition, type_width
from .loading import MAX_BYTES, Model, load_document, load_model, loads_model, parse_model
from .validation import ModelValidationError, validate_standard
from .profile import instantiate, export_td, parse_parameters
from .delivery import project_point_table
from .simulation import DataError, SimulationData, load_simulation_data, scaled_raw
from .session import (
    REFERENCE_PREFIX,
    CredentialError,
    Reference,
    Session,
    active_server,
    forget_session,
    load_session,
    parse_reference,
    save_session,
    server_url,
)
from .verification import (
    ReportError,
    model_fingerprint,
    point_fingerprints,
    validate_report,
)

__version__ = _version("modpoll-wot")

__all__ = [
    "__version__",
    "MAX_BYTES",
    "load_document",
    "type_width",
    "REFERENCE_PREFIX",
    "CredentialError",
    "Reference",
    "Session",
    "active_server",
    "forget_session",
    "load_session",
    "parse_reference",
    "save_session",
    "server_url",
    "DataError",
    "SimulationData",
    "load_simulation_data",
    "scaled_raw",
    "parse_parameters",
    "ReportError",
    "model_fingerprint",
    "point_fingerprints",
    "validate_report",
    "project_point_table",
    "instantiate",
    "export_td",
    "AcquisitionError",
    "Group",
    "Member",
    "Model",
    "ModelValidationError",
    "parse_acquisition",
    "load_model",
    "loads_model",
    "parse_model",
    "validate_standard",
]
