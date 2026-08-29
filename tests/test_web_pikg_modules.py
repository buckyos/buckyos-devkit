import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.project import AppInfo, BuckyProject, WebPikgModuleInfo

build_web_apps = importlib.import_module("src.build_web_apps")
prepare_rootfs = importlib.import_module("src.prepare_rootfs")


class WebPikgModuleTests(unittest.TestCase):
    def test_project_parses_and_serializes_web_pikg_module(self):
        project = BuckyProject.from_dict(
            {
                "name": "test-project",
                "modules": {
                    "package": {
                        "type": "web-pikg",
                        "name": "package",
                        "src_dir": "apps/package",
                    }
                },
            }
        )

        self.assertIsInstance(project.modules["package"], WebPikgModuleInfo)
        self.assertEqual(project.to_dict()["modules"]["package"]["type"], "web-pikg")

    def test_build_runs_web_dependency_flow_and_package_build(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_dir = Path(tmp_dir) / "apps" / "package"
            source_dir.mkdir(parents=True)
            (source_dir / "package.json").write_text(
                json.dumps(
                    {
                        "dependencies": {
                            "buckyos": "github:buckyos/buckyos-websdk#main",
                        }
                    }
                ),
                encoding="utf-8",
            )
            project = BuckyProject(
                name="test-project",
                version="0.1.0",
                base_dir=Path(tmp_dir),
                modules={
                    "package": WebPikgModuleInfo(
                        name="package",
                        src_dir=Path("apps/package"),
                    )
                },
            )

            with patch.object(build_web_apps.subprocess, "run") as run_mock:
                build_web_apps.build_web_pikg_module(project, "package")

        run_mock.assert_called_once_with(
            "pnpm install && pnpm update buckyos && pnpm run build",
            shell=True,
            cwd=source_dir,
            check=True,
        )

    def test_copy_build_results_does_not_apply_web_dist_copy(self):
        project = BuckyProject(
            name="test-project",
            version="0.1.0",
            modules={
                "package": WebPikgModuleInfo(
                    name="package",
                    src_dir=Path("apps/package"),
                )
            },
            apps={
                "system": AppInfo(
                    name="system",
                    rootfs=Path("rootfs"),
                    default_target_rootfs=Path("/opt/system"),
                    modules={"package": "data/cache/package.pikg"},
                )
            },
        )

        with patch.object(prepare_rootfs, "copy_web_module") as copy_web_mock:
            prepare_rootfs.copy_build_results(
                project,
                skip_web_module=False,
                selected_modules=["package"],
            )

        copy_web_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
