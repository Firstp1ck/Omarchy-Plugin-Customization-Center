import json
from pathlib import Path

import pytest

from customization_center.core import ApplyLock, Locked, Paths


def test_lock_contention_holder_and_stale_file(isolated_home):
    paths = Paths.from_env()
    first = ApplyLock(paths, "tx1", "menu").acquire()
    try:
        with pytest.raises(Locked) as caught:
            ApplyLock(paths, "tx2", "bar").acquire()
        assert caught.value.data["transactionId"] == "tx1"
    finally:
        first.release()
    lock_file = paths.runtime / "apply.lock"
    lock_file.write_text("stale junk")
    with ApplyLock(paths, "tx3", "themes"):
        holder = json.loads(lock_file.read_text())
        assert holder["transactionId"] == "tx3"
