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


class BuildRustTimingsTests(unittest.TestCase):
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
                    timings=True,
                )

        cargo_args = run_mock.call_args.args[0]
        self.assertIn("--timings", cargo_args)
        self.assertEqual(cargo_args.count("-p"), 1)
        self.assertIn("daemon", cargo_args)
        self.assertNotIn("frontend", cargo_args)

    def test_build_rust_modules_copies_new_timings_report(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project = BuckyProject(
                name="test-project",
                version="0.1.0",
                base_dir=Path(tmp_dir),
                modules={
                    "daemon": RustModuleInfo(name="daemon"),
                },
            )
            project.rust_target_dir = Path(tmp_dir) / "target"
            output_dir = Path(tmp_dir) / "timings-output"

            def make_timing_report(*args, **kwargs):
                report_dir = project.rust_target_dir / "cargo-timings"
                report_dir.mkdir(parents=True, exist_ok=True)
                (report_dir / "cargo-timing-test.html").write_text("<html></html>", encoding="utf-8")

            with patch.object(build_rust, "get_build_metadata", return_value={}), patch.object(
                build_rust, "get_env_vars_by_target", return_value={}
            ), patch.object(build_rust, "get_cross_compile_env_vars_by_target", return_value=None), patch.object(
                build_rust.subprocess, "run", side_effect=make_timing_report
            ) as run_mock:
                build_rust.build_rust_modules(
                    project,
                    "x86_64-unknown-linux-gnu",
                    selected_modules=["daemon"],
                    timings_dir=output_dir,
                )

            cargo_args = run_mock.call_args.args[0]
            self.assertIn("--timings", cargo_args)
            self.assertTrue((output_dir / "cargo-timing-test.html").exists())


if __name__ == "__main__":
    unittest.main()
