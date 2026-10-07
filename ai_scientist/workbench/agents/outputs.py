"""Small, shared output contracts for the three research roles."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from typing import Any


EDITABLE_WORKLOAD_RUNNER_REFERENCE: dict[str, Any] = {
    "context_fields": [
        "config", "input_dir", "output_dir", "run_id", "source_sha256", "data_sha256", "inputs",
        "task_subtype", "result_schema", "evaluation_sha256", "compatibility_sha256", "environment",
        "resume_state",
    ],
    "environment_fields": ["python", "device", "amp"],
    "output_directory": {
        "run": "context['output_dir'] is already the bundle/output directory; write files directly there.",
        "preflight": "preflight(context) receives the same context fields plus preflight=True, with temporary input_dir/output_dir paths rather than final bundle paths.",
        "pinned_path_rule": "For pinned output/NAME, write NAME under context['output_dir'] and return path NAME; the runner adds the output/ prefix when recording the artifact.",
        "artifact_paths": "Each artifacts item uses a safe relative path under context['output_dir']; never return an absolute path or append another output/ directory.",
    },
    "preflight_result": {
        "required": {"passed": True},
        "optional_fields": {"scope": "object", "checks": "object"},
    },
    "run_result": {
        "required_fields": {"measurements": "object", "payload": "object", "artifacts": "array of {kind, path} objects"},
        "etc_processing_example": {
            "measurements": {},
            "payload": {"rows": 3, "synthetic": False},
            "artifacts": [
                {"kind": "dataset", "path": "processed.csv"},
                {"kind": "summary", "path": "summary.json"},
                {"kind": "report", "path": "report.json"},
            ],
        },
        "etc_processing_rules": "ETC Processing requires dataset, summary and report artifacts plus integer payload.rows and boolean payload.synthetic. Measurements stay empty; do not report metrics or an official score. Preserve the request's pinned expected_outputs; the normal request pins output/processed.csv and output/report.json, and summary.json is also required by result_schema.",
    },
    "proposal_validation": "The research proposal path performs Python syntax and AST structure checks only; it does not execute proposed source or establish runtime acceptance.",
}


# Self-contained contract for a proposed TRAINING workload. It is deliberately
# separate from the ETC reference: a training proposal must know its registered
# metric, its explicitly synthetic scope and its hash-pinned checkpoint shape,
# and the reviewed ETC prompt contract stays byte-for-byte unchanged.
TRAINING_WORKLOAD_RUNNER_REFERENCE: dict[str, Any] = {
    "context_fields": [
        "config", "input_dir", "output_dir", "run_id", "source_sha256", "data_sha256", "inputs",
        "task_subtype", "result_schema", "evaluation_sha256", "compatibility_sha256", "environment",
        "resume_state",
    ],
    "environment_fields": ["python", "device", "amp"],
    "output_directory": {
        "run": "context['output_dir'] is already the bundle/output directory; write files directly there.",
        "preflight": "preflight(context) receives the same context fields plus preflight=True with temporary input_dir/output_dir paths; keep preflight scratch files there and never write them into the final bundle.",
        "pinned_path_rule": "For a pinned output/NAME, write NAME under context['output_dir'] and return path NAME; the runner adds the output/ prefix when recording the artifact.",
        "artifact_paths": "Each artifacts item uses a safe relative path under context['output_dir']; never return an absolute path or append another output/ directory.",
    },
    "preflight_result": {
        "required": {"passed": True},
        "optional_fields": {"scope": "object", "checks": "object"},
        "rule": "Exercise at most the first 5 steps in the isolated preflight scope, including one atomic checkpoint round-trip; return passed False instead of raising when the pinned configuration cannot run.",
    },
    "run_result": {
        "required_fields": {"measurements": "object", "payload": "object", "artifacts": "array of {kind, path} objects"},
        "training_example": {
            "measurements": {"mse": 0.032},
            "payload": {"steps": 40, "seed": 17, "history": [{"step": 1, "loss": 1.21}]},
            "artifacts": [
                {"kind": "checkpoint", "path": "checkpoint.json"},
                {"kind": "report", "path": "report.json"},
            ],
        },
        "training_rules": "measurements must carry exactly the pinned evaluation metric as one finite number: no other metric, no official score. This contract is explicitly synthetic, so never read a dataset file, install or download anything, or call a network service; stay CPU-only, stdlib-only and deterministic for the pinned seed.",
        "data_scope": "context['inputs'] describes synthetic data; context['config'] carries the pinned steps/seed/learning_rate/step_delay_seconds only.",
    },
    "checkpoint_record": {
        "required": True,
        "path": "checkpoint.json under context['output_dir']",
        "minimum_steps_before_first_write": 5,
        "json_shape": {"state": "object", "sha256": "sha256 of the canonical state JSON, json.dumps(state, sort_keys=True, separators=(',', ':'))"},
        "state_fields": ["schema_version", "step", "epoch", "model", "optimizer", "sampler_position", "config",
                         "code_sha256", "data_sha256", "evaluation_sha256", "compatibility_sha256", "environment"],
        "pin_rule": "state.code_sha256, state.data_sha256, state.evaluation_sha256 and state.compatibility_sha256 must be copied from context['source_sha256'], context['data_sha256'], context['evaluation_sha256'] and context['compatibility_sha256']; a checkpoint that disagrees with those pins is refused and can never be resumed.",
        "frequency": "write the checkpoint at least every 5 steps and at the final step",
        "resume_contract": "An owner-approved attempt that stopped FAILED or CANCELLED may be resumed only inside this same bounded local CPU contract: read context['resume_state'], verify its pins, continue from exactly state['step'] keeping the same state shape, and stay within the same total step limit. Saved source is not resume-compatible by itself and no other recipe may be mixed in; the resumed attempt runs the parent's frozen source and pinned inputs, never a later edit of research-proposals/ or of current resources.",
    },
    "proposal_validation": "The research proposal path performs Python syntax and AST structure checks only; it does not execute proposed source or establish runtime acceptance. A measured metric exists only after the owner-approved run actually executes.",
}


RESEARCH_OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "planner": {
        "type": "object",
        "properties": {
            "objective": {"type": "string"},
            "scope": {"type": "string"},
            "change_summary": {"type": "string"},
        },
        "required": ["objective", "scope", "change_summary"],
        "additionalProperties": False,
    },
    "coder": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "pattern": r"^(?:workload\.py|source/.+\.py)$"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["files"],
        "additionalProperties": False,
    },
    "analyst": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "recommendations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "metrics": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
        "required": ["summary", "recommendations", "metrics"],
        "additionalProperties": False,
    },
}

_ROLE_INSTRUCTIONS = {
    "planner": (
        "Return exactly one JSON object with required string fields objective, scope, and change_summary. "
        "Do not add other fields, Markdown, or prose. Keep each field non-empty and within 4000 characters."
    ),
    "coder": (
        "Return exactly one JSON object with a required files object. Include the complete UTF-8 source for "
        "the root workload.py module and only optional Python helpers under source/. The workload module must "
        "define preflight(context) and run(context). Do not return a notebook, documentation, or other non-Python "
        "file. Each key is a relative proposed file path and each value is its complete source as a plain string, "
        "not base64. For Processing requests, follow the supplied runner_contract reference for the exact runner "
        "context, output directory, preflight response and run-result envelope. Do not claim the proposed source "
        "was executed or runtime-verified. "
        "Do not add other fields, Markdown, or prose."
    ),
    "analyst": (
        "Return exactly one JSON object with required fields summary (non-empty string), recommendations "
        "(array of at most 50 strings), and metrics (an empty object). Do not invent or report metric values: "
        "there is no measured run evidence. Do not add other fields, Markdown, or prose."
    ),
}

_ROLE_FIELDS = {
    "planner": {
        "required": ("objective", "scope", "change_summary"),
        "types": {"objective": "string", "scope": "string", "change_summary": "string"},
    },
    "coder": {
        "required": ("files",),
        "types": {"files": "array"},
    },
    "analyst": {
        "required": ("summary", "recommendations", "metrics"),
        "types": {"summary": "string", "recommendations": "array", "metrics": "object"},
    },
}


class ResearchOutputValidationError(ValueError):
    """A safe, structured diagnostic for a malformed role output."""

    def __init__(self, role: str, code: str, field: str, *,
                 expected_type: str | None = None, actual_type: str | None = None,
                 decode_position: int | None = None):
        self.role = role
        self.code = code
        self.field = field
        self.expected_type = expected_type
        self.actual_type = actual_type
        self.decode_position = decode_position
        super().__init__(f"{role} output validation failed ({code})")

    def diagnostic(self) -> dict[str, Any]:
        value: dict[str, Any] = {"role": self.role, "code": self.code, "field": self.field}
        if self.decode_position is not None:
            value["decode_position"] = self.decode_position
        else:
            value["expected_type"] = self.expected_type
            value["actual_type"] = self.actual_type
        return value


def research_output_schema(role: str) -> dict[str, Any] | None:
    """Return the typed schema for a research role, or None for other runtime roles."""
    return RESEARCH_OUTPUT_SCHEMAS.get(role)


def research_role_instruction(role: str) -> str:
    return _ROLE_INSTRUCTIONS.get(role, "")


def structured_role_instruction(role: str) -> str:
    """Describe the native structured-output wire shape without changing role semantics."""
    if role == "coder":
        return (
            "Return exactly one JSON object with a required files array. Include exactly one root workload.py "
            "module and only optional Python helper modules beneath source/. The workload.py module must define "
            "preflight(context) and run(context); do not return a notebook, documentation, or other non-Python file. "
            "Each item must contain exactly "
            "path (a non-empty relative path string) and content (the complete UTF-8 file content string); "
            "both fields are required and no other item fields are allowed. Return 1 to 100 items with unique paths. "
            "For Processing requests, follow the supplied runner_contract reference for the exact runner context, "
            "output directory, preflight response and run-result envelope. Do not claim the proposed source was "
            "executed or runtime-verified. "
            "This array is the native wire form for the existing RuntimeResult.files path-to-bytes map; do not "
            "return a files object or base64 content. Do not add other top-level fields, Markdown, or prose."
        )
    return research_role_instruction(role)


def structured_role_prompt(role: str, prompt: str) -> str:
    """Replace the generic role instruction with its native structured-output wire form."""
    generic = research_role_instruction(role)
    structured = structured_role_instruction(role)
    if not structured:
        return prompt
    if generic and prompt.startswith(generic):
        return structured + prompt[len(generic):]
    return f"{structured}\n\n{prompt}"


def coder_wire_files(value: dict[str, Any]) -> dict[str, str]:
    """Normalize the strict native Coder array into the shared semantic file mapping."""
    return {item["path"]: item["content"] for item in value["files"]}


def validate_editable_workload_files(files: dict[str, bytes],
                                     module_contract: dict[str, Any] | None = None) -> None:
    """Check the generated workload source interface without importing or executing proposed code.

    With a normalized ``module_contract`` the owner's exact editable filenames and
    byte caps replace the two built-in shapes; every declared file is required and
    nothing else may be returned.
    """
    if "workload.py" not in files:
        raise ResearchOutputValidationError(
            "coder", "required_module_missing", "$.files",
            expected_type="root workload.py module", actual_type="missing",
        )

    if module_contract is not None:
        allowed = list(module_contract["editable_files"])
        undeclared = sorted(set(files) - set(allowed))
        if undeclared:
            raise ResearchOutputValidationError(
                "coder", "unsupported_proposal_path", "$.files.path",
                expected_type="declared editable files: " + ", ".join(allowed),
                actual_type="undeclared file " + undeclared[0],
            )
        if set(files) != set(allowed):
            missing = sorted(set(allowed) - set(files))
            raise ResearchOutputValidationError(
                "coder", "declared_file_missing", "$.files.path",
                expected_type="every declared editable file: " + ", ".join(allowed),
                actual_type="missing " + missing[0],
            )
        per_file = module_contract["max_file_bytes"]
        total = sum(len(content) for content in files.values())
        oversized = sorted(path for path, content in files.items() if len(content) > per_file)
        if oversized:
            raise ResearchOutputValidationError(
                "coder", "declared_file_too_large", "$.files.path",
                expected_type=f"at most {per_file} bytes per declared file",
                actual_type=oversized[0],
            )
        if total > module_contract["max_total_bytes"]:
            raise ResearchOutputValidationError(
                "coder", "declared_total_too_large", "$.files",
                expected_type=f"at most {module_contract['max_total_bytes']} bytes in total",
                actual_type=f"{total} bytes",
            )
    else:
        for path in files:
            helper = (
                path.startswith("source/") and path.endswith(".py") and "\\" not in path
                and all(part not in {"", ".", ".."} for part in path.split("/"))
            )
            if path != "workload.py" and not helper:
                raise ResearchOutputValidationError(
                    "coder", "unsupported_proposal_path", "$.files.path",
                    expected_type="workload.py or source/*.py", actual_type="unsupported path",
                )

    for path, content in files.items():
        field = "$.files.workload.py" if path == "workload.py" else "$.files.source"
        try:
            source = content.decode("utf-8")
        except UnicodeDecodeError:
            raise ResearchOutputValidationError(
                "coder", "invalid_python_encoding", field,
                expected_type="UTF-8 Python source", actual_type="invalid encoding",
            ) from None
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            raise ResearchOutputValidationError(
                "coder", "invalid_python_syntax", field,
                expected_type="valid Python syntax", actual_type="syntax error",
            ) from None
        if path != "workload.py":
            continue

        functions = {
            node.name: node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name, signature in (("preflight", "preflight(context)"), ("run", "run(context)")):
            function = functions.get(name)
            if not isinstance(function, ast.FunctionDef):
                raise ResearchOutputValidationError(
                    "coder", "missing_required_entrypoint", "$.files.workload.py",
                    expected_type="preflight(context) and run(context)", actual_type=f"missing {name}",
                )
            positional = function.args.posonlyargs + function.args.args
            required_positional = len(positional) - len(function.args.defaults)
            required_keyword_only = any(default is None for default in function.args.kw_defaults)
            accepts_one_context = bool(positional) or function.args.vararg is not None
            if not accepts_one_context or required_positional > 1 or required_keyword_only:
                raise ResearchOutputValidationError(
                    "coder", "invalid_entrypoint_signature", "$.files.workload.py",
                    expected_type=signature, actual_type="entrypoint cannot accept one context argument",
                )


MODULE_CONTRACT_VERSION = 1
MODULE_CONTRACT_MAX_FILES = 6
# The declared editable set may never exceed the existing global aggregate bounds
# of one local bundle (workload source plus pinned helper modules: 5 MB each).
MODULE_CONTRACT_GLOBAL_MAX_FILE_BYTES = 5_000_000
MODULE_CONTRACT_GLOBAL_MAX_TOTAL_BYTES = 5_000_000
MODULE_CONTRACT_KEYS = (
    "version", "recipe", "task_kind", "template", "editable_files", "max_file_bytes",
    "max_total_bytes", "run_config", "preflight", "result_schema", "dependencies",
)
MODULE_CONTRACT_PAYLOAD_TYPES = {"integer", "number", "boolean", "string", "object", "array"}
_MODULE_TASK_KINDS = {"Processing": "Processing", "ETC": "Processing", "Training": "TRAINING",
                      "TRAINING": "TRAINING"}
_MODULE_DEPENDENCY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-")
_HEX = set("0123456789abcdef")
# Exact grammar parity with the filesystem adapter that reads these files: a helper is
# a flat ASCII source/<identifier>.py name of 1..64 characters, and a template is one
# flat ASCII .py name directly under agent_platform/workloads. A declaration this port
# accepts is therefore one the reader can read, and nothing broader.
_MODULE_HELPER_PATH = re.compile(r"^source/[A-Za-z_][A-Za-z0-9_]{0,63}\.py$")
_MODULE_TEMPLATE_PATH = re.compile(r"^agent_platform/workloads/[A-Za-z0-9_][A-Za-z0-9_.-]{0,120}\.py$")
# The canonical structural checkpoint validator name is owned by the execution layer
# (execution.bundle.CHECKPOINT_VALIDATION_STRUCTURED == "structured-record-v1"); this
# port accepts only that exact spelling and never invents a second one.
MODULE_CHECKPOINT_VALIDATION_STRUCTURED = "structured-record-v1"
_MODULE_TRAINING_SCHEMA_KEYS = {"kind", "checkpoint_validation"}
_MODULE_ETC_SCHEMA_KEYS = {"kind", "task_subtype", "metrics_allowed", "required_artifact_kinds",
                           "required_payload_fields", "required_payload_types"}
# Owner run configuration is local CPU work only: a key naming a provider, endpoint,
# credential, accelerator or remote/paid target is refused rather than silently carried
# into a bundle. This is a refusal list for an honest local-only contract, not a
# security boundary against an owner who edits the contract and the source together.
_MODULE_REMOTE_KEYS = {"provider", "providers", "model", "models", "endpoint", "endpoints", "base_url",
                       "api_base", "api_key", "apikey", "key", "secret", "token", "credentials",
                       "credential", "vendor", "account", "account_ref", "region", "url", "uri", "host",
                       "port", "gpu", "accelerator", "kaggle", "wandb", "notion", "organization", "org"}


def _module_text(value: Any, limit: int) -> str | None:
    if isinstance(value, str) and value.strip() and len(value) <= limit:
        return value
    return None


def _module_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in _HEX for char in value)


def _module_editable_names(value: Any) -> list[str] | None:
    """Exact unique filenames: root workload.py plus flat source/<identifier>.py helpers.

    The helper grammar is the adapter's own grammar, so a declaration accepted here is
    one the reader can actually read: flat ASCII, 1..64 identifier characters.
    """
    if not isinstance(value, list) or not 1 <= len(value) <= MODULE_CONTRACT_MAX_FILES:
        return None
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or item in names:
            return None
        if item == "workload.py":
            names.append(item)
            continue
        if _MODULE_HELPER_PATH.fullmatch(item) is None:
            return None
        names.append(item)
    return names if "workload.py" in names else None


def _module_result_schema(value: Any, task_kind: str) -> dict[str, Any] | None:
    """The declared schema must satisfy the existing bundle-side schema checks.

    Unknown nested keys are refused instead of being silently discarded, so an owner
    declaration is either honoured exactly or reported as invalid. The Training schema
    is deliberately minimal: the registered metric plus, at most, the existing
    structural checkpoint validator, and requesting that validator requires both the
    checkpoint and the report artifacts in the execution spec.
    """
    if not isinstance(value, dict):
        return None
    if task_kind == "TRAINING":
        if set(value) - _MODULE_TRAINING_SCHEMA_KEYS or value.get("kind") != "registered-training-metric":
            return None
        checkpoint = value.get("checkpoint_validation")
        if checkpoint is None:
            return {"kind": "registered-training-metric", "required_artifact_kinds": ["report"]}
        if checkpoint != MODULE_CHECKPOINT_VALIDATION_STRUCTURED:
            return None
        return {"kind": "registered-training-metric",
                "required_artifact_kinds": ["checkpoint", "report"],
                "checkpoint_validation": checkpoint}
    if set(value) - _MODULE_ETC_SCHEMA_KEYS:
        return None
    kinds = value.get("required_artifact_kinds")
    fields = value.get("required_payload_fields")
    types = value.get("required_payload_types")
    if value.get("kind") != "etc-task-output" or value.get("task_subtype") != "Processing":
        return None
    if value.get("metrics_allowed") is not False:
        return None
    if not isinstance(kinds, list) or not kinds or any(_module_text(kind, 64) is None for kind in kinds):
        return None
    if not isinstance(fields, list) or not fields or any(_module_text(field, 64) is None for field in fields):
        return None
    if not isinstance(types, dict) or set(fields) != set(types):
        return None
    schema: dict[str, Any] = {"kind": "etc-task-output", "task_subtype": "Processing",
                              "metrics_allowed": False,
                              "required_artifact_kinds": list(dict.fromkeys(kinds)),
                              "required_payload_fields": list(dict.fromkeys(fields)),
                              "required_payload_types": {}}
    for field in schema["required_payload_fields"]:
        declared = types.get(field)
        # A JSON list, object or number is not a declared payload type name: it is
        # reported as an invalid contract rather than raising out of the validation.
        if not isinstance(declared, str) or declared not in MODULE_CONTRACT_PAYLOAD_TYPES:
            return None
        schema["required_payload_types"][field] = declared
    return schema


def _module_dependencies(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list) or len(value) > 8:
        return None
    records: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "version", "wheel_path", "sha256"}:
            return None
        name, version = _module_text(item.get("name"), 64), _module_text(item.get("version"), 64)
        wheel = _module_text(item.get("wheel_path"), 240)
        if (name is None or version is None or not set(name) <= _MODULE_DEPENDENCY_CHARS
                or not set(version) <= _MODULE_DEPENDENCY_CHARS or not _module_sha256(item.get("sha256"))
                or wheel is None or not wheel.startswith("agent_platform/wheelhouse/")
                or not wheel.endswith(".whl") or "\\" in wheel or ".." in wheel):
            return None
        records.append({"name": name, "version": version, "wheel_path": wheel,
                        "sha256": item["sha256"]})
    return records


def module_contract_findings(value: Any, *, task_kind: str) -> list[str]:
    """Exact owner-facing findings for one baseline.module_contract value.

    An absent contract is not this function's concern: the caller only calls it when
    the owner declared the key. An empty or incomplete object yields findings, which
    park the request in WAITING_USER before any runtime or bundle work.
    """
    findings: list[str] = []
    if not isinstance(value, dict):
        return ["baseline.module_contract must be an owner-declared JSON object"]
    unknown = sorted(set(value) - set(MODULE_CONTRACT_KEYS))
    if unknown:
        findings.append("baseline.module_contract." + unknown[0] + " is not a supported contract key")
    for key in MODULE_CONTRACT_KEYS:
        if key not in value:
            findings.append("baseline.module_contract." + key + " is required")
    if findings:
        return findings
    if type(value["version"]) is not int or value["version"] != MODULE_CONTRACT_VERSION:
        findings.append(f"baseline.module_contract.version must be the integer {MODULE_CONTRACT_VERSION}")
    recipe = value["recipe"]
    # The recipe name must satisfy the bundle's own ASCII recipe grammar
    # (execution.bundle._RECIPE), so an admitted contract can never name a recipe the
    # execution layer would refuse.
    if (not isinstance(recipe, str) or not recipe.startswith("project.")
            or re.fullmatch(r"[a-z][a-z0-9_]{0,47}", recipe[len("project."):]) is None
            or recipe != recipe.lower() or len(recipe) > 56):
        findings.append("baseline.module_contract.recipe must be a bounded project.<ascii identifier> name")
    declared_kind = _MODULE_TASK_KINDS.get(value["task_kind"]) if isinstance(value["task_kind"], str) else None
    if declared_kind is None:
        findings.append("baseline.module_contract.task_kind must be Training or Processing")
    elif declared_kind != task_kind:
        findings.append("baseline.module_contract.task_kind must match the requested task kind")
    template = value["template"]
    if not isinstance(template, dict) or set(template) != {"path", "sha256"}:
        findings.append("baseline.module_contract.template requires exactly path and sha256")
    elif (not isinstance(template["path"], str)
          or _MODULE_TEMPLATE_PATH.fullmatch(template["path"]) is None
          or not _module_sha256(template["sha256"])):
        findings.append("baseline.module_contract.template must pin one flat "
                        "agent_platform/workloads/<name>.py file and its sha256")
    if _module_editable_names(value["editable_files"]) is None:
        findings.append("baseline.module_contract.editable_files must list unique declared filenames "
                        "with workload.py plus flat source/<identifier>.py helpers, at most "
                        f"{MODULE_CONTRACT_MAX_FILES} files")
    per_file, total = value["max_file_bytes"], value["max_total_bytes"]
    if (type(per_file) is not int or not 1 <= per_file <= MODULE_CONTRACT_GLOBAL_MAX_FILE_BYTES
            or type(total) is not int or not 1 <= total <= MODULE_CONTRACT_GLOBAL_MAX_TOTAL_BYTES
            or per_file > total):
        findings.append("baseline.module_contract.max_file_bytes/max_total_bytes must be positive "
                        "integers within the existing local bundle bounds")
    run_config = value["run_config"]
    if not isinstance(run_config, dict) or not run_config or len(run_config) > 32:
        findings.append("baseline.module_contract.run_config must be a non-empty declared object")
    else:
        for key, item in sorted(run_config.items()):
            if str(key).strip().lower() in _MODULE_REMOTE_KEYS:
                findings.append("baseline.module_contract.run_config." + str(key)
                                + " cannot declare a provider, endpoint, credential or remote target")
                break
            if not isinstance(key, str) or not key.isidentifier() or type(item) not in (str, int, float, bool):
                findings.append("baseline.module_contract.run_config." + str(key) + " must be a declared scalar")
                break
        if type(run_config.get("synthetic_data")) is not bool:
            findings.append("baseline.module_contract.run_config.synthetic_data must be an owner-declared boolean")
    preflight = value["preflight"]
    if not isinstance(preflight, dict) or set(preflight) - {"enabled", "scope", "rows"}:
        findings.append("baseline.module_contract.preflight supports only enabled, scope and rows")
    else:
        if preflight.get("enabled") is not True:
            findings.append("baseline.module_contract.preflight.enabled must be true for a custom module")
        if _module_text(preflight.get("scope"), 240) is None:
            findings.append("baseline.module_contract.preflight.scope must describe the bounded preflight")
        rows = preflight.get("rows")
        if rows is not None and (type(rows) is not int or not 1 <= rows <= 1_000):
            findings.append("baseline.module_contract.preflight.rows must be a bounded positive integer")
    if _module_result_schema(value["result_schema"], declared_kind or "") is None:
        findings.append("baseline.module_contract.result_schema must declare this task kind's existing "
                        "result contract shape")
    if _module_dependencies(value["dependencies"]) is None:
        findings.append("baseline.module_contract.dependencies must list only existing "
                        "name/version/wheel_path/sha256 local wheels")
    return findings


def normalize_module_contract(value: Any, *, task_kind: str) -> dict[str, Any]:
    """Return the immutable normalized contract, or raise the exact owner-facing findings."""
    findings = module_contract_findings(value, task_kind=task_kind)
    if findings:
        raise ResearchOutputValidationError(
            "owner", "invalid_module_contract", "baseline.module_contract",
            expected_type="complete baseline.module_contract", actual_type=findings[0],
        )
    template = value["template"]
    preflight = value["preflight"]
    normalized: dict[str, Any] = {
        "version": MODULE_CONTRACT_VERSION,
        "recipe": value["recipe"],
        "task_kind": _MODULE_TASK_KINDS[value["task_kind"]],
        "template": {"path": template["path"], "sha256": template["sha256"]},
        "editable_files": _module_editable_names(value["editable_files"]),
        "max_file_bytes": value["max_file_bytes"],
        "max_total_bytes": value["max_total_bytes"],
        "run_config": {key: value["run_config"][key] for key in sorted(value["run_config"])},
        "preflight": {"enabled": True, "scope": preflight["scope"],
                      "rows": preflight.get("rows", 5)},
        "result_schema": _module_result_schema(value["result_schema"], _MODULE_TASK_KINDS[value["task_kind"]]),
        "dependencies": _module_dependencies(value["dependencies"]),
        "synthetic_data": value["run_config"]["synthetic_data"],
    }
    normalized["contract_sha256"] = module_contract_sha256(normalized)
    return normalized


def module_contract_sha256(contract: dict[str, Any]) -> str:
    """Canonical digest over everything the owner declared, minus the digest itself."""
    declared = {key: item for key, item in contract.items() if key != "contract_sha256"}
    return hashlib.sha256(json.dumps(declared, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def proposal_helper_names(contract: dict[str, Any]) -> list[str]:
    """The declared helper files (everything except the mandatory root workload.py)."""
    return [name for name in contract["editable_files"] if name != "workload.py"]


def parse_research_output(role: str, text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ResearchOutputValidationError(role, "invalid_json", "$", decode_position=exc.pos) from None
    return validate_research_output(role, value)


def validate_research_output(role: str, value: Any) -> dict[str, Any]:
    """Validate only the known, narrow Planner/Coder/Analyst contracts."""
    contract = _ROLE_FIELDS.get(role)
    if contract is None:
        if not isinstance(value, dict):
            raise ResearchOutputValidationError(role, "wrong_type", "$", expected_type="object",
                                                actual_type=_type_name(value))
        return value
    if not isinstance(value, dict):
        raise ResearchOutputValidationError(role, "wrong_type", "$", expected_type="object",
                                            actual_type=_type_name(value))
    required = contract["required"]
    types = contract["types"]
    for key in required:
        if key not in value:
            raise ResearchOutputValidationError(role, "missing_field", _field_path(role, key),
                                                expected_type=types[key], actual_type="missing")
    allowed = set(types)
    if set(value) - allowed:
        raise ResearchOutputValidationError(role, "unexpected_field", "$",
                                            expected_type="object with declared fields", actual_type="object")
    for key, expected in types.items():
        if key not in value:
            continue
        item = value[key]
        if _type_name(item) != expected:
            raise ResearchOutputValidationError(role, "wrong_type", _field_path(role, key),
                                                expected_type=expected, actual_type=_type_name(item))
    if role == "coder":
        files = value["files"]
        if len(files) < 1 or len(files) > 100:
            raise ResearchOutputValidationError(role, "invalid_file_count", "$.files",
                                                expected_type="array with 1 to 100 entries",
                                                actual_type="empty array" if not files else "array")
        seen_paths: set[str] = set()
        for index, entry in enumerate(files):
            entry_path = f"$.files[{index}]"
            if not isinstance(entry, dict):
                raise ResearchOutputValidationError(role, "wrong_type", entry_path,
                                                    expected_type="object", actual_type=_type_name(entry))
            for key in ("path", "content"):
                if key not in entry:
                    raise ResearchOutputValidationError(role, "missing_field", f"{entry_path}.{key}",
                                                        expected_type="string", actual_type="missing")
            if set(entry) - {"path", "content"}:
                raise ResearchOutputValidationError(role, "unexpected_field", entry_path,
                                                    expected_type="object with declared fields", actual_type="object")
            for key in ("path", "content"):
                if not isinstance(entry[key], str):
                    raise ResearchOutputValidationError(role, "wrong_type", f"{entry_path}.{key}",
                                                        expected_type="string", actual_type=_type_name(entry[key]))
            if not entry["path"]:
                raise ResearchOutputValidationError(role, "invalid_path", f"{entry_path}.path",
                                                    expected_type="non-empty string", actual_type="empty string")
            if entry["path"] in seen_paths:
                raise ResearchOutputValidationError(role, "duplicate_file_path", "$.files",
                                                    expected_type="unique paths", actual_type="duplicate path")
            seen_paths.add(entry["path"])
    elif role == "analyst":
        for index, recommendation in enumerate(value["recommendations"]):
            if not isinstance(recommendation, str):
                raise ResearchOutputValidationError(role, "wrong_type", f"$.recommendations[{index}]",
                                                    expected_type="string", actual_type=_type_name(recommendation))
        if value["metrics"]:
            raise ResearchOutputValidationError(role, "metrics_not_allowed", "$.metrics",
                                                expected_type="empty object", actual_type="non-empty object")
    return value


def _field_path(role: str, key: str) -> str:
    if role == "planner" and key in {"objective", "scope", "change_summary"}:
        return f"$.{key}"
    if role == "coder" and key == "files":
        return "$.files"
    if role == "analyst" and key in {"summary", "recommendations", "metrics"}:
        return f"$.{key}"
    return "$"


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "unknown"
