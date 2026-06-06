import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.project import AppInfo, BuckyProject, RustModuleInfo, WebModuleInfo

build = importlib.import_module("src.build")
build_rust = importlib.import_module("src.build_rust")


class BuildAppOptionTests(unittest.TestCase):
    def make_project(self) -> BuckyProject:
        return BuckyProject(
            name="test-project",
            version="0.1.0",
            modules={
                "daemon": RustModuleInfo(name="daemon"),
                "frontend": WebModuleInfo(name="frontend", src_dir=Path("web/frontend")),
                "unused": RustModuleInfo(name="unused"),
            },
            apps={
                "system": AppInfo(
                    name="system",
                    rootfs=Path("rootfs/system"),
                    default_target_rootfs=Path("/opt/system"),
                    modules={
                        "daemon": "bin",
                        "frontend": "www",
                        "missing": "bin",
                    },
                ),
                "tools": AppInfo(
                    name="tools",
                    rootfs=Path("rootfs/tools"),
                    default_target_rootfs=Path("/opt/tools"),
                    modules={
                        "unused": "bin",
                    },
                ),
            },
        )

    def test_collect_app_modules_intersects_with_project_modules(self):
        with patch("builtins.print"):
            selected_modules = build._collect_app_modules(self.make_project(), ["system", "tools"])

        self.assertEqual(selected_modules, {"daemon", "frontend", "unused"})

    def test_collect_app_modules_rejects_unknown_app(self):
        with self.assertRaisesRegex(ValueError, "missing-app"):
            build._collect_app_modules(self.make_project(), ["missing-app"])


class BuildRustTimingTests(unittest.TestCase):
    def test_build_rust_modules_adds_cargo_timings_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project = BuckyProject(
                name="test-project",
                version="0.1.0",
                base_dir=Path(tmp_dir),
                modules={
                    "daemon": RustModuleInfo(name="daemon"),
                    "frontend": WebModuleInfo(name="frontend", src_dir=Path("web/frontend")),
                },
            )
            project.rust_target_dir = Path(tmp_dir) / "target"

            with patch.object(build_rust, "get_build_metadata", return_value={}), patch.object(
                build_rust, "get_env_vars_by_target", return_value={}
            ), patch.object(build_rust, "get_cross_compile_env_vars_by_target", return_value=None), patch.object(
                build_rust.subprocess, "run"
            ) as run_mock:
                build_rust.build_rust_modules(
                    project,
                    "x86_64-unknown-linux-gnu",
                    selected_modules=["daemon"],
                    timing=True,
                )

        cargo_args = run_mock.call_args.args[0]
        self.assertIn("--timings", cargo_args)
        self.assertEqual(cargo_args.count("-p"), 1)
        self.assertIn("daemon", cargo_args)
        self.assertNotIn("frontend", cargo_args)


if __name__ == "__main__":
    unittest.main()
