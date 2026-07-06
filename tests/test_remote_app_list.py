import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from src.remote.app_list import AppList


def write_app_config(
    path: Path,
    name: str,
    version: str = "1.0.0",
    directories: Optional[dict[str, str]] = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "commands": {
                    "build_all": [],
                    "install": [],
                    "build": [],
                    "update": [],
                },
                "directories": directories
                or {
                    "source": "rootfs/app",
                    "target": "/opt/app",
                    "source_bin": "rootfs/app/bin",
                    "target_bin": "/opt/app/bin",
                },
            }
        ),
        encoding="utf-8",
    )


class RemoteAppListTests(unittest.TestCase):
    def test_loads_local_app_configs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            app_dir = Path(tmp_dir) / "dev_configs" / "apps"
            write_app_config(app_dir / "demo.json", "demo", version="local")

            app_list = AppList(app_dir)
            app_list.load_app_list()

            self.assertEqual(app_list.get_all_app_names(), ["demo"])
            self.assertEqual(app_list.get_app("demo").version, "local")

    def test_loads_external_app_config_from_relative_base_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            base_dir = root_dir / "buckyos" / "src"
            base_dir.mkdir(parents=True)
            app_dir = base_dir / "dev_configs" / "apps"
            external_path = (
                root_dir
                / "cyfs-gateway"
                / "src"
                / "dev_configs"
                / "apps"
                / "web3-gateway.json"
            )
            write_app_config(
                external_path,
                "web3-gateway",
                version="external",
                directories={"source": "gateway-rootfs", "target": "/opt/gateway"},
            )

            relative_path = os.path.relpath(external_path, base_dir)
            app_list = AppList(app_dir)
            app_list.load_app_list()
            app_list.load_external_app_configs(
                {"web3-gateway": relative_path},
                base_dir,
            )

            app_config = app_list.get_app("web3-gateway")
            self.assertIsNotNone(app_config)
            self.assertEqual(app_config.version, "external")
            self.assertEqual(app_config.get_dir("source"), "gateway-rootfs")

    def test_loads_external_app_config_from_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            base_dir = root_dir / "buckyos" / "src"
            external_path = root_dir / "external" / "apps" / "demo.json"
            write_app_config(external_path, "demo", version="absolute")

            app_list = AppList(base_dir / "dev_configs" / "apps")
            app_list.load_external_app_configs({"demo": str(external_path)}, base_dir)

            self.assertEqual(app_list.get_app("demo").version, "absolute")

    def test_external_app_configs_must_be_object(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            app_list = AppList(base_dir / "dev_configs" / "apps")

            with self.assertRaisesRegex(ValueError, "app_configs must be an object"):
                app_list.load_external_app_configs([], base_dir)

    def test_external_app_name_mismatch_includes_app_name_and_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            external_path = base_dir / "external" / "mismatch.json"
            write_app_config(external_path, "other")

            app_list = AppList(base_dir / "dev_configs" / "apps")
            with self.assertRaisesRegex(ValueError, r"demo.*mismatch\.json"):
                app_list.load_external_app_configs({"demo": "external/mismatch.json"}, base_dir)

    def test_external_missing_file_includes_app_name_and_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            app_list = AppList(base_dir / "dev_configs" / "apps")

            with self.assertRaisesRegex(ValueError, r"demo.*missing\.json"):
                app_list.load_external_app_configs({"demo": "external/missing.json"}, base_dir)

    def test_external_invalid_json_includes_app_name_and_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            invalid_path = base_dir / "external" / "invalid.json"
            invalid_path.parent.mkdir(parents=True, exist_ok=True)
            invalid_path.write_text("{not-json", encoding="utf-8")

            app_list = AppList(base_dir / "dev_configs" / "apps")
            with self.assertRaisesRegex(ValueError, r"demo.*invalid\.json"):
                app_list.load_external_app_configs({"demo": "external/invalid.json"}, base_dir)

    def test_explicit_external_config_overrides_local_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            app_dir = base_dir / "dev_configs" / "apps"
            write_app_config(app_dir / "demo.json", "demo", version="local")
            external_path = base_dir / "external" / "demo.json"
            write_app_config(external_path, "demo", version="external")

            app_list = AppList(app_dir)
            app_list.load_app_list()
            with patch("builtins.print") as print_mock:
                app_list.load_external_app_configs({"demo": "external/demo.json"}, base_dir)

            self.assertEqual(app_list.get_app("demo").version, "external")
            printed = "\n".join(call.args[0] for call in print_mock.call_args_list)
            self.assertIn("overrides local app config", printed)

    def test_duplicate_external_config_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            first_path = base_dir / "external" / "one" / "demo.json"
            second_path = base_dir / "external" / "two" / "demo.json"
            write_app_config(first_path, "demo", version="one")
            write_app_config(second_path, "demo", version="two")

            app_list = AppList(base_dir / "dev_configs" / "apps")
            app_list.load_external_app_configs({"demo": "external/one/demo.json"}, base_dir)
            with self.assertRaisesRegex(ValueError, r"Duplicate external app config.*demo.*two"):
                app_list.load_external_app_configs({"demo": "external/two/demo.json"}, base_dir)


if __name__ == "__main__":
    unittest.main()
