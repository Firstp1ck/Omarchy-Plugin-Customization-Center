from customization_center.core import (Capabilities, Capability, Operation, Plan, ResourceClaim, Status,
                                       ValidationIssue, ValidationResult, VerifyResult, Warning)
from customization_center.core.errors import CcError


def test_types_round_trip_and_camel_case():
    warning = Warning("menu_notice", "notice", ack=True)
    operation = Operation("menu.1", "menu", "WriteFileAtomic", {"path": "/x"}, "write", (), ("/x",),
                          inverse_after=("menu.0",))
    plan = Plan("menu", "r1", (operation,), (ResourceClaim("file:x", "exclusive"),), "summary", (warning,), ())
    assert Plan.from_json(plan.to_json()) == plan
    assert plan.to_json()["expectedRevision"] == "r1"
    assert plan.to_json()["operations"][0]["inverseAfter"] == ["menu.0"]
    assert ValidationResult.from_json(ValidationResult(True, (ValidationIssue("menu_x", "x", "/x", "warning"),), {}).to_json()).ok
    assert VerifyResult.from_json(VerifyResult("pass", "full", "").to_json()).state == "pass"
    assert Status.from_json(Status("menu", "r", {}, (), 1).to_json()).module_id == "menu"


def test_capabilities_get_and_require():
    caps = Capabilities("menu", (Capability("bash", False, "missing"),), "now")
    assert not caps.get("unknown").available
    try:
        caps.require("bash")
    except CcError as error:
        assert error.code == "capability_missing"
    else:
        raise AssertionError("require did not fail")
