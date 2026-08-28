from pathlib import Path

from customization_center.core import BackupStore, Paths


def test_backup_restore_existing_absent_and_mode(isolated_home):
    paths = Paths.from_env()
    store = BackupStore(paths)
    existing = isolated_home / "existing"
    absent = isolated_home / "absent"
    existing.write_bytes(b"before"); existing.chmod(0o640)
    records = store.take("tx", [existing, absent])
    assert records[str(absent)]["existed"] is False
    existing.write_bytes(b"after"); absent.write_text("created")
    store.restore("tx", existing); store.restore("tx", absent)
    assert existing.read_bytes() == b"before"
    assert existing.stat().st_mode & 0o777 == 0o640
    assert not absent.exists()
    manifest = store.read_manifest("tx")
    assert {item["path"] for item in manifest.values()} == {str(existing), str(absent)}
