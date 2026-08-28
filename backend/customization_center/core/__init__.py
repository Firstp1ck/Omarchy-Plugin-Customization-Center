from .types import (Capability, Capabilities, Context, Module, Operation, OperationResult, Plan, PlanSegment,
                    ResourceClaim, Status, Transaction, ValidationIssue, ValidationResult, VerifyResult, Warning)
from .errors import CcError, SHARED_CODES, is_shared_code, validate_code
from .result import JsonEncoder, Result, emit
from .paths import Paths, expand_template, no_symlink_components
from .locking import ApplyLock, Locked, flock, lock
from .atomic import DirectoryReplacement, mkdir_durable, remove_file, replace_directory_atomic, write_bytes_atomic
from .backup import BackupStore
from .journal import Journal, JournalReader
from .commands import CommandResult, CommandRunner, redact
from .shell_ipc import IpcResult, ShellIpc
from .hyprctl import Hyprctl
from . import catalog, jsonc, lua, managed_block, settings_schema, toml_writer
from .managed_block import comment_prefix_for, extract as extract_managed_block, inspect as inspect_managed_block, markers, replace as replace_managed_block
from .jsonc import Diagnostic, Diagnostics, dumps_canonical, parse as parse_jsonc
from .lua import lua_string, luac_check
from .capabilities import CapabilityCache, STANDARD_CAPABILITIES, probe_command, probe_shell, standard_capabilities
from .catalog import CatalogRead

# Part 2 adds `from . import operations as ops` here; no placeholder is provided because modules must never plan against fake operations.

__all__ = [
    "Capability", "Capabilities", "Context", "Module", "Operation", "OperationResult", "Plan", "PlanSegment",
    "ResourceClaim", "Status", "Transaction", "ValidationIssue", "ValidationResult", "VerifyResult", "Warning",
    "CcError", "SHARED_CODES", "is_shared_code", "validate_code", "JsonEncoder", "Result", "emit", "Paths",
    "expand_template", "no_symlink_components", "ApplyLock", "Locked", "flock", "lock", "DirectoryReplacement", "remove_file",
    "replace_directory_atomic", "write_bytes_atomic", "mkdir_durable", "BackupStore", "Journal", "JournalReader", "CommandResult",
    "CommandRunner", "redact", "IpcResult", "ShellIpc", "Hyprctl", "catalog", "jsonc", "lua", "managed_block",
    "settings_schema", "toml_writer", "comment_prefix_for", "extract_managed_block", "inspect_managed_block", "markers",
    "replace_managed_block", "Diagnostic", "Diagnostics", "dumps_canonical", "parse_jsonc", "lua_string", "luac_check",
    "CapabilityCache", "STANDARD_CAPABILITIES", "probe_command", "probe_shell", "standard_capabilities", "CatalogRead",
]
