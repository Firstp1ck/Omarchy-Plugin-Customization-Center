import os
from dataclasses import replace
from pathlib import Path

import pytest

from customization_center.core import CcError, Journal, JournalReader, Paths, Plan, Transaction


def transaction(txid="tx", state="applying", created="2026-01-01T00:00:00Z"):
    plan = Plan("menu", "before", (), (), "none", (), ())
    return Transaction(txid, "menu", state, created, created, plan, "before", None, (), (), {}, None, None, (), ())


def test_journal_transitions_history_and_current(isolated_home):
    paths = Paths.from_env(); journal = Journal(paths, now=lambda: "2026-01-01T00:00:01Z")
    journal.create(transaction())
    assert journal.transition("tx", "awaiting_confirmation").state == "awaiting_confirmation"
    assert journal.transition("tx", "applying").state == "applying"
    assert journal.transition("tx", "committed").state == "committed"
    with pytest.raises(CcError): journal.transition("tx", "rolling_back")
    assert JournalReader(journal).transaction("tx").state == "committed"
    journal.set_current("tx"); assert journal.current_transaction_id() == "tx"
    journal.clear_current("tx"); assert journal.current_transaction_id() is None


def test_pending_recovery_states(isolated_home):
    paths = Paths.from_env(); journal = Journal(paths)
    journal.create(transaction("applying"))
    expired = replace(transaction("expired", "awaiting_confirmation"), confirmation={"deadline": "2000-01-01T00:00:00Z"})
    journal.create(expired)
    orphan = replace(transaction("orphan", "awaiting_confirmation"), confirmation={"deadline": "2099-01-01T00:00:00Z"})
    journal.create(orphan)
    handoff = transaction("handoff", "pending_handoff"); journal.create(handoff)
    sentinel = paths.state / "handoffs/handoff.json"; sentinel.parent.mkdir(parents=True); sentinel.write_text("{}")
    assert {item.id for item in journal.pending_recovery()} == {"applying", "expired", "orphan", "handoff"}


@pytest.mark.parametrize(("source", "target", "reason"), [
    ("applying", "committed", None),
    ("applying", "awaiting_confirmation", None),
    ("applying", "pending_handoff", None),
    ("applying", "rolling_back", "operation"),
    ("awaiting_confirmation", "applying", None),
    ("awaiting_confirmation", "rolling_back", "timeout"),
    ("pending_handoff", "committed", None),
    ("pending_handoff", "rolling_back", "handoff_failed"),
    ("pending_handoff", "rolled_back", "user"),
    ("rolling_back", "rolled_back", None),
    ("rolling_back", "rollback_failed", None),
])
def test_every_legal_transition(isolated_home, source, target, reason):
    journal = Journal(Paths.from_env())
    txid = source + "-" + target
    journal.create(transaction(txid, source))
    assert journal.transition(txid, target, reason).state == target


@pytest.mark.parametrize(("source", "target", "reason"), [
    ("applying", "rolled_back", None),
    ("committed", "rolling_back", "user"),
    ("awaiting_confirmation", "committed", None),
    ("pending_handoff", "rolled_back", None),
])
def test_illegal_transitions(isolated_home, source, target, reason):
    journal = Journal(Paths.from_env())
    journal.create(transaction("illegal", source))
    with pytest.raises(CcError) as caught:
        journal.transition("illegal", target, reason)
    assert caught.value.code == "transaction_state_invalid"


def test_direct_save_enforces_state_machine(isolated_home):
    journal = Journal(Paths.from_env())
    original = transaction("direct", "committed")
    journal.create(original)
    with pytest.raises(CcError) as caught:
        journal.save(replace(original, state="rolling_back", reason="user"))
    assert caught.value.code == "transaction_state_invalid"
    assert journal.load("direct").state == "committed"


def test_save_fsync_order_includes_new_directory_parents(isolated_home, monkeypatch):
    import customization_center.core.atomic as atomic

    targets = []

    def record(fd):
        targets.append(os.readlink(f"/proc/self/fd/{fd}"))

    monkeypatch.setattr(atomic.os, "fsync", record)
    paths = Paths.from_env()
    Journal(paths).create(transaction())
    state_home = paths.state.parents[1]
    assert targets[:3] == [str(state_home), str(state_home / "omarchy"), str(paths.state)]
    assert Path(targets[3]).parent == paths.state / "transactions"
    assert Path(targets[3]).name.startswith(".tx.")
    assert targets[4] == str(paths.state / "transactions")
    assert len(targets) == 5
