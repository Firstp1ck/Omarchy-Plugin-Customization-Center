from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any, Protocol


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


def _wire(value: Any) -> Any:
    if is_dataclass(value):
        return {_camel(f.name): _wire(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if isinstance(value, list):
        return [_wire(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _wire(item) for key, item in value.items()}
    return value


def _get(data: dict[str, Any], name: str, default: Any = None) -> Any:
    return data.get(_camel(name), data.get(name, default))


class JsonType:
    def to_json(self) -> dict[str, Any]:
        return _wire(self)


@dataclass(frozen=True)
class Capability(JsonType):
    name: str
    available: bool
    reason: str
    readonly_check: bool = False
    argv_prefix: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Capability":
        return cls(str(data["name"]), bool(data["available"]), str(data.get("reason", "")),
                   bool(_get(data, "readonly_check", False)), tuple(_get(data, "argv_prefix", ())))


@dataclass(frozen=True)
class Capabilities(JsonType):
    module_id: str
    items: tuple[Capability, ...]
    probed_at: str

    def get(self, name: str) -> Capability:
        for item in self.items:
            if item.name == name:
                return item
        return Capability(name, False, f"Capability {name} was not probed")

    def require(self, *names: str) -> None:
        from .errors import CcError
        missing = [self.get(name) for name in names if not self.get(name).available]
        if missing:
            raise CcError("capability_missing", "; ".join(item.reason or item.name for item in missing),
                          {"capabilities": [item.to_json() for item in missing]})

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Capabilities":
        return cls(str(_get(data, "module_id")), tuple(Capability.from_json(x) for x in data.get("items", [])),
                   str(_get(data, "probed_at", "")))


@dataclass(frozen=True)
class Warning(JsonType):
    code: str
    message: str
    path: str = ""
    recovery: str = ""
    ack: bool = False

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Warning":
        return cls(str(data["code"]), str(data["message"]), str(data.get("path", "")),
                   str(data.get("recovery", "")), bool(data.get("ack", False)))


@dataclass(frozen=True)
class Status(JsonType):
    module_id: str
    revision: str
    data: dict[str, Any]
    warnings: tuple[Warning, ...]
    schema_version: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Status":
        return cls(str(_get(data, "module_id")), str(data["revision"]), dict(data.get("data", {})),
                   tuple(Warning.from_json(x) for x in data.get("warnings", [])), int(_get(data, "schema_version", 1)))


@dataclass(frozen=True)
class OperationResult(JsonType):
    operation_id: str
    exit_code: int | None
    stdout_head: str
    stderr_head: str
    timed_out: bool
    duration_ms: int
    written_sha256: str | None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "OperationResult":
        return cls(str(_get(data, "operation_id")), _get(data, "exit_code"), str(_get(data, "stdout_head", "")),
                   str(_get(data, "stderr_head", "")), bool(_get(data, "timed_out", False)),
                   int(_get(data, "duration_ms", 0)), _get(data, "written_sha256"))


@dataclass(frozen=True)
class ValidationIssue(JsonType):
    code: str
    message: str
    pointer: str
    severity: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ValidationIssue":
        return cls(str(data["code"]), str(data["message"]), str(data.get("pointer", "")), str(data["severity"]))


@dataclass(frozen=True)
class ValidationResult(JsonType):
    ok: bool
    issues: tuple[ValidationIssue, ...]
    normalized_draft: dict[str, Any] | None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ValidationResult":
        draft = _get(data, "normalized_draft")
        return cls(bool(data["ok"]), tuple(ValidationIssue.from_json(x) for x in data.get("issues", [])),
                   dict(draft) if isinstance(draft, dict) else None, dict(data.get("details", {})))


@dataclass(frozen=True)
class Operation(JsonType):
    id: str
    module_id: str
    kind: str
    params: dict[str, Any]
    summary: str
    inverse: "Operation | tuple[Operation, ...] | None"
    backup_paths: tuple[str, ...]
    timeout_s: float = 30.0
    detail: dict[str, Any] | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Operation":
        raw_inverse = data.get("inverse")
        if isinstance(raw_inverse, list):
            inverse: Operation | tuple[Operation, ...] | None = tuple(cls.from_json(x) for x in raw_inverse)
        elif isinstance(raw_inverse, dict):
            inverse = cls.from_json(raw_inverse)
        else:
            inverse = None
        return cls(str(data["id"]), str(_get(data, "module_id")), str(data["kind"]), dict(data.get("params", {})),
                   str(data.get("summary", "")), inverse, tuple(_get(data, "backup_paths", ())),
                   float(_get(data, "timeout_s", 30.0)), data.get("detail"))


@dataclass(frozen=True)
class ResourceClaim(JsonType):
    key: str
    access: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ResourceClaim":
        return cls(str(data["key"]), str(data["access"]))


@dataclass(frozen=True)
class PlanSegment(JsonType):
    module_id: str
    expected_revision: str
    operation_ids: tuple[str, ...]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PlanSegment":
        return cls(str(_get(data, "module_id")), str(_get(data, "expected_revision")),
                   tuple(str(x) for x in _get(data, "operation_ids", ())))


@dataclass(frozen=True)
class Plan(JsonType):
    module_id: str
    expected_revision: str
    operations: tuple[Operation, ...]
    claims: tuple[ResourceClaim, ...]
    summary: str
    warnings: tuple[Warning, ...]
    requires_confirmation: tuple[str, ...]
    residual_side_effects: tuple[str, ...] = ()
    segments: tuple[PlanSegment, ...] = ()
    plan_digest: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"schemaVersion": 1, **_wire(self)}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Plan":
        return cls(str(_get(data, "module_id")), str(_get(data, "expected_revision")),
                   tuple(Operation.from_json(x) for x in data.get("operations", [])),
                   tuple(ResourceClaim.from_json(x) for x in data.get("claims", [])), str(data.get("summary", "")),
                   tuple(Warning.from_json(x) for x in data.get("warnings", [])),
                   tuple(str(x) for x in _get(data, "requires_confirmation", ())),
                   tuple(str(x) for x in _get(data, "residual_side_effects", ())),
                   tuple(PlanSegment.from_json(x) for x in data.get("segments", [])), str(_get(data, "plan_digest", "")))


@dataclass(frozen=True)
class VerifyResult(JsonType):
    state: str
    level: str
    reason: str
    code: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "VerifyResult":
        return cls(str(data["state"]), str(data["level"]), str(data.get("reason", "")),
                   str(data.get("code", "")), dict(data.get("evidence", {})))


@dataclass(frozen=True)
class Transaction(JsonType):
    id: str
    module_id: str
    state: str
    created_at: str
    updated_at: str
    plan: Plan
    before_revision: str
    after_revision: str | None
    completed_operation_ids: tuple[str, ...]
    rolled_back_operation_ids: tuple[str, ...]
    backups: dict[str, Any]
    verify: VerifyResult | None
    confirmation: dict[str, Any] | None
    errors: tuple[dict[str, Any], ...]
    rollback_errors: tuple[dict[str, Any], ...]
    reason: str | None = None
    skipped_inverse_ids: tuple[dict[str, Any], ...] = ()
    command_log: tuple[dict[str, Any], ...] = ()

    def to_json(self) -> dict[str, Any]:
        out = _wire(self)
        out["schemaVersion"] = 1
        out["module"] = out.pop("moduleId")
        out["plan"] = self.plan.to_json()
        out["residualSideEffects"] = list(self.plan.residual_side_effects)
        return out

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Transaction":
        return cls(str(data["id"]), str(data.get("module", _get(data, "module_id"))), str(data["state"]),
                   str(_get(data, "created_at")), str(_get(data, "updated_at")), Plan.from_json(data["plan"]),
                   str(_get(data, "before_revision")), _get(data, "after_revision"),
                   tuple(_get(data, "completed_operation_ids", ())), tuple(_get(data, "rolled_back_operation_ids", ())),
                   dict(data.get("backups", {})), VerifyResult.from_json(data["verify"]) if data.get("verify") else None,
                   data.get("confirmation"), tuple(data.get("errors", ())), tuple(_get(data, "rollback_errors", ())),
                   data.get("reason"), tuple(_get(data, "skipped_inverse_ids", ())), tuple(_get(data, "command_log", ())))


@dataclass(frozen=True)
class Context:
    paths: Any
    capabilities: Capabilities
    commands: Any
    cache: dict[str, Any]
    shell: Any
    hyprctl: Any
    journal: Any
    registry: Any
    clock: Any
    log: Any
    mode: str
    module_id: str


class Module(Protocol):
    id: str
    schema_version: int
    def capabilities(self, ctx: Context) -> Capabilities: ...
    def status(self, ctx: Context) -> Status: ...
    def validate(self, ctx: Context, draft: dict[str, Any], status: Status) -> ValidationResult: ...
    def plan(self, ctx: Context, draft: dict[str, Any], status: Status) -> Plan: ...
    def verify(self, ctx: Context, plan: Plan, status_after: Status,
               results: dict[str, OperationResult]) -> VerifyResult: ...
    def query(self, ctx: Context, name: str, args: dict[str, Any]) -> dict[str, Any]: ...
    def migrate(self, ctx: Context, kind: str, document: dict[str, Any], from_version: int) -> dict[str, Any]: ...
