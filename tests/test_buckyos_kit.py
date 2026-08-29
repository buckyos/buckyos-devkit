import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import buckyos_kit


class WindowsExecuteNameTests(unittest.TestCase):
    def test_finds_windows_launchers_in_priority_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            command = Path(temporary) / "buckyos"
            command.with_suffix(".exe").touch()
            command.with_suffix(".cmd").touch()
            command.with_suffix(".ps1").touch()

            with patch.object(buckyos_kit, "_system_name", "Windows"):
                self.assertEqual(
                    buckyos_kit.get_execute_name(command),
                    str(command.with_suffix(".ps1")),
                )
                command.with_suffix(".ps1").unlink()
                self.assertEqual(
                    buckyos_kit.get_execute_name(command),
                    str(command.with_suffix(".cmd")),
                )
                command.with_suffix(".cmd").unlink()
                self.assertEqual(
                    buckyos_kit.get_execute_name(command),
                    str(command.with_suffix(".exe")),
                )

    def test_defaults_to_exe_when_no_candidate_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            command = Path(temporary) / "missing"
            with patch.object(buckyos_kit, "_system_name", "Windows"):
                self.assertEqual(
                    buckyos_kit.get_execute_name(command),
                    str(command.with_suffix(".exe")),
                )

    def test_preferred_source_extension_is_used_for_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "buckyos"
            with patch.object(buckyos_kit, "_system_name", "Windows"):
                self.assertEqual(
                    buckyos_kit.get_execute_name(target, ".cmd"),
                    str(target.with_suffix(".cmd")),
                )

    def test_explicit_extension_is_unchanged(self):
        with patch.object(buckyos_kit, "_system_name", "Windows"):
            self.assertEqual(
                buckyos_kit.get_execute_name("C:/tools/buckyos.cmd"),
                "C:/tools/buckyos.cmd",
            )


if __name__ == "__main__":
    unittest.main()
