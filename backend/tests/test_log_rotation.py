"""Tests for external log rotation (rotate_external_logs)."""

import gzip
import os

import pytest

from app.main import rotate_external_logs


class TestRotateExternalLogs:
    """Tests for the rotate_external_logs function."""

    def test_noop_when_file_does_not_exist(self, tmp_path):
        rotate_external_logs(log_dir=str(tmp_path), max_bytes=100, backup_count=3)
        # No files created, no errors
        assert not list(tmp_path.iterdir())

    def test_noop_when_file_under_max_bytes(self, tmp_path):
        log_file = tmp_path / "postgres.log"
        log_file.write_text("small content")
        rotate_external_logs(log_dir=str(tmp_path), max_bytes=1000, backup_count=3)
        # File unchanged
        assert log_file.read_text() == "small content"
        # No backups created
        assert not list(tmp_path.glob("*.gz"))

    def test_rotates_file_exceeding_max_bytes(self, tmp_path):
        log_file = tmp_path / "postgres.log"
        log_file.write_text("x" * 200)
        rotate_external_logs(log_dir=str(tmp_path), max_bytes=100, backup_count=3)
        # .1.gz created
        gz1 = tmp_path / "postgres.log.1.gz"
        assert gz1.exists()
        # Original truncated
        assert log_file.read_text() == ""
        # .1.gz contains original content
        with gzip.open(str(gz1), "rb") as f:
            assert f.read() == b"x" * 200

    def test_shifts_existing_backups(self, tmp_path):
        log_file = tmp_path / "postgres.log"
        log_file.write_text("x" * 200)

        # Create existing .1.gz backup
        gz1 = tmp_path / "postgres.log.1.gz"
        with gzip.open(str(gz1), "wb") as f:
            f.write(b"old backup 1")

        rotate_external_logs(log_dir=str(tmp_path), max_bytes=100, backup_count=3)
        # .1.gz → .2.gz (shifted)
        gz2 = tmp_path / "postgres.log.2.gz"
        assert gz2.exists()
        with gzip.open(str(gz2), "rb") as f:
            assert f.read() == b"old backup 1"
        # New .1.gz contains current content
        with gzip.open(str(gz1), "rb") as f:
            assert f.read() == b"x" * 200

    def test_removes_oldest_backup(self, tmp_path):
        log_file = tmp_path / "postgres.log"
        log_file.write_text("x" * 200)

        # Create .1.gz, .2.gz, .3.gz backups
        for i in range(1, 4):
            gz = tmp_path / f"postgres.log.{i}.gz"
            with gzip.open(str(gz), "wb") as f:
                f.write(f"old backup {i}".encode())

        rotate_external_logs(log_dir=str(tmp_path), max_bytes=100, backup_count=3)
        # Original .3.gz content is gone (oldest removed)
        # .2.gz → .3.gz (old backup 2 is now in .3.gz)
        gz3 = tmp_path / "postgres.log.3.gz"
        assert gz3.exists()
        with gzip.open(str(gz3), "rb") as f:
            assert f.read() == b"old backup 2"
        # .1.gz → .2.gz (old backup 1 is now in .2.gz)
        gz2 = tmp_path / "postgres.log.2.gz"
        with gzip.open(str(gz2), "rb") as f:
            assert f.read() == b"old backup 1"
        # New .1.gz contains current log content
        gz1 = tmp_path / "postgres.log.1.gz"
        with gzip.open(str(gz1), "rb") as f:
            assert f.read() == b"x" * 200

    def test_rotates_both_log_files(self, tmp_path):
        for name in ("postgres.log", "letta.log"):
            (tmp_path / name).write_text("y" * 200)
        rotate_external_logs(log_dir=str(tmp_path), max_bytes=100, backup_count=3)
        for name in ("postgres.log", "letta.log"):
            assert (tmp_path / name).read_text() == ""
            assert (tmp_path / f"{name}.1.gz").exists()

    def test_handles_oserror_on_getsize(self, tmp_path):
        log_file = tmp_path / "postgres.log"
        log_file.write_text("content")
        # Make getsize fail by removing the file between exists check and getsize
        # Instead, just test that a permission error doesn't crash
        with pytest.MonkeyPatch.context() as m:
            original_getsize = os.path.getsize

            def failing_getsize(path):
                if "postgres.log" in path:
                    raise OSError("permission denied")
                return original_getsize(path)

            m.setattr(os.path, "getsize", failing_getsize)
            # Should not crash
            rotate_external_logs(log_dir=str(tmp_path), max_bytes=100, backup_count=3)
