from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .atomic import mkdir_durable, write_bytes_atomic
from .errors import CcError
from .types import Transaction

_TRANSITIONS = {
    "applying": {"committed", "awaiting_confirmation", "pending_handoff", "rolling_back"},
    "awaiting_confirmation": {"applying", "rolling_back"},
    "pending_handoff": {"committed", "rolling_back", "rolled_back"},
    "rolling_back": {"rolled_back", "rollback_failed"},
    "committed": set(), "rolled_back": set(), "rollback_failed": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Journal:
    def __init__(self, state_or_paths: str | Path | Any, runtime: str | Path | None = None,
                 now: Callable[[], str] | None = None) -> None:
        self.state = Path(state_or_paths.state if hasattr(state_or_paths, "state") else state_or_paths)
        if runtime is None and hasattr(state_or_paths, "runtime"):
            runtime = state_or_paths.runtime
        self.runtime = Path(runtime) if runtime is not None else self.state / "runtime"
        self.transactions = self.state / "transactions"
        self._now = now or _now

    def create(self, transaction: Transaction) -> Transaction:
        path = self.transactions / f"{transaction.id}.json"
        if path.exists():
            raise CcError("transaction_state_invalid", f"Transaction already exists: {transaction.id}")
        self.save(transaction)
        return transaction

    def load(self, txid: str) -> Transaction:
        try:
            data = json.loads((self.transactions / f"{txid}.json").read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise CcError("transaction_not_found", f"Unknown transaction: {txid}") from error
        except json.JSONDecodeError as error:
            raise CcError("unsupported_config", f"Transaction journal is malformed: {txid}") from error
        if data.get("schemaVersion") != 1:
            raise CcError("schema_version_unsupported", f"Unsupported transaction schema: {data.get('schemaVersion')}")
        return Transaction.from_json(data)

    def save(self, transaction: Transaction) -> None:
        mkdir_durable(self.transactions, 0o700)
        payload = json.dumps(transaction.to_json(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
        write_bytes_atomic(self.transactions / f"{transaction.id}.json", payload, 0o600)

    def transition(self, txid: str, new_state: str, reason: str | None = None) -> Transaction:
        current = self.load(txid)
        if new_state not in _TRANSITIONS.get(current.state, set()):
            raise CcError("transaction_state_invalid", f"Cannot transition {current.state} to {new_state}",
                          {"transactionId": txid, "state": current.state, "requestedState": new_state})
        if current.state == "pending_handoff" and new_state == "rolled_back" and reason != "user":
            raise CcError("transaction_state_invalid", "A pending handoff may be abandoned only by the user")
        updated = replace(current, state=new_state, updated_at=self._now(), reason=reason or current.reason)
        self.save(updated)
        return updated

    def history(self, module: str | None = None, limit: int = 50,
                state: str | None = None) -> list[Transaction]:
        if limit < 0:
            raise ValueError("limit cannot be negative")
        records: list[Transaction] = []
        if not self.transactions.exists():
            return records
        for path in self.transactions.glob("*.json"):
            try:
                record = self.load(path.stem)
            except CcError:
                continue
            if module is not None and record.module_id != module:
                continue
            if state is not None and record.state != state:
                continue
            records.append(record)
        records.sort(key=lambda item: item.created_at, reverse=True)
        return records[:limit]

    def current_transaction_id(self) -> str | None:
        try:
            value = (self.runtime / "current-transaction").read_text(encoding="utf-8").strip()
            return value or None
        except FileNotFoundError:
            return None

    def set_current(self, txid: str) -> None:
        mkdir_durable(self.runtime, 0o700)
        write_bytes_atomic(self.runtime / "current-transaction", (txid + "\n").encode(), 0o600)

    def clear_current(self, txid: str | None = None) -> None:
        path = self.runtime / "current-transaction"
        if txid is not None and self.current_transaction_id() != txid:
            return
        try:
            path.unlink()
            fd = os.open(self.runtime, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except FileNotFoundError:
            pass

    def pending_recovery(self) -> list[Transaction]:
        now = _parse_time(self._now())
        pending: list[Transaction] = []
        for record in self.history(limit=1_000_000):
            if record.state in {"applying", "rolling_back"}:
                pending.append(record)
            elif record.state == "awaiting_confirmation":
                deadline = (record.confirmation or {}).get("deadline")
                if deadline and _parse_time(deadline) <= now:
                    pending.append(record)
            elif record.state == "pending_handoff" and (self.state / "handoffs" / f"{record.id}.json").is_file():
                pending.append(record)
        return pending


class JournalReader:
    def __init__(self, journal: Journal) -> None:
        self._journal = journal

    def history(self, module: str | None = None, limit: int = 50, state: str | None = None) -> list[Transaction]:
        return self._journal.history(module, limit, state)

    def transaction(self, txid: str) -> Transaction:
        return self._journal.load(txid)

    def current_transaction_id(self) -> str | None:
        return self._journal.current_transaction_id()
