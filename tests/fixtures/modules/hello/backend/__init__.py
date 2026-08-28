from __future__ import annotations

import json

from customization_center.core import (
    Capabilities, Capability, Plan, ResourceClaim, Status, ValidationIssue,
    ValidationResult, VerifyResult, ops,
)


class Hello:
    id = "hello"
    schema_version = 1

    def capabilities(self, ctx):
        available = ctx.commands.which("hello-command") is not None
        return Capabilities(self.id, (Capability("hello_command", available,
            "" if available else "hello-command is not on PATH"),), ctx.clock.now_iso())

    def status(self, ctx):
        path = ctx.paths.module_config(self.id) / "hello.json"
        value = ctx.paths.read_json(path, default=None)
        data = {"schemaVersion": 1, "message": value.get("message") if isinstance(value, dict) else None}
        return Status(self.id, ctx.revision_of(data), data, (), 1)

    def validate(self, ctx, draft, status):
        issues = ()
        if draft.get("schemaVersion") != 1 or not isinstance(draft.get("message"), str) or not draft["message"]:
            issues = (ValidationIssue("hello_invalid_message", "A message is required", "/message", "error"),)
        return ValidationResult(not issues, issues, dict(draft) if not issues else None)

    def plan(self, ctx, draft, status):
        path = ctx.paths.module_config(self.id) / "hello.json"
        write = ops.WriteFileAtomic(ctx, path,
            json.dumps({"schemaVersion": 1, "message": draft["message"]}, sort_keys=True) + "\n",
            "0600", summary="Write the hello message")
        command = ops.RunCommand(ctx, ["hello-command", draft["message"]], timeout_s=5,
            summary="Notify the hello command", inverse=["hello-command", "undo"])
        return Plan(self.id, status.revision, (write, command),
            (ResourceClaim(f"file:{path}", "exclusive"),), "Set the hello message", (), ())

    def verify(self, ctx, plan, status_after, results):
        expected = json.loads(plan.operations[0].params["content"])["message"]
        ok = status_after.data.get("message") == expected and plan.operations[1].id in results
        return VerifyResult("pass" if ok else "fail", "full", "" if ok else "Hello state did not match",
                            "" if ok else "hello_verification_failed", status_after.data)


MODULE = Hello()
