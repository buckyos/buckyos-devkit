import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.module_build import (
    BuildResult,
    BuildResultSpec,
    BuilderRegistry,
    FormatterRegistry,
    InstallReference,
)
from src.project import (
    AppInfo,
    BuckyProject,
    NoneModuleInfo,
    PikgModuleConfig,
    RustModuleInfo,
    WebModuleInfo,
)

build_pipeline = importlib.import_module("src.build")
build_none = importlib.import_module("src.build_none")
build_web_apps = importlib.import_module("src.build_web_apps")
formatters = importlib.import_module("src.formatters")


class ModuleFormatConfigTests(unittest.TestCase):
    def test_files_is_the_implicit_default_and_is_not_serialized(self):
        project = BuckyProject.from_dict(
            {
                "name": "test-project",
                "modules": {
                    "frontend": {
                        "type": "web",
                        "name": "frontend",
                        "src_dir": "apps/frontend",
                    }
                },
            }
        )

        module = project.modules["frontend"]
        self.assertEqual(module.format, "files")
        self.assertNotIn("format", project.to_dict()["modules"]["frontend"])

    def test_omitted_type_defaults_to_none_and_is_not_serialized(self):
        project = BuckyProject.from_dict(
            {
                "name": "test-project",
                "modules": {
                    "package": {
                        "format": "pikg",
                        "name": "package",
                        "src_dir": "apps/package",
                    }
                },
                "apps": {
                    "system": {
                        "name": "system",
                        "rootfs": "rootfs",
                        "default_target_rootfs": "/opt/system",
                        "modules": {"package": "data/cache/package.pikg"},
                    }
                },
            }
        )
        self.assertIsInstance(project.modules["package"], NoneModuleInfo)
        self.assertNotIn("type", project.to_dict()["modules"]["package"])

    def test_explicit_none_is_accepted_and_serialized_as_the_default(self):
        project = BuckyProject.from_dict(
            {
                "name": "test-project",
                "modules": {
                    "static": {
                        "type": "none",
                        "name": "static",
                        "src_dir": "apps/static",
                    }
                },
            }
        )
        self.assertIsInstance(project.modules["static"], NoneModuleInfo)
        self.assertNotIn("type", project.to_dict()["modules"]["static"])

    def test_pikg_options_must_be_an_object_with_non_empty_string_meta_dir(self):
        base = {
            "name": "test-project",
            "modules": {
                "package": {
                    "type": "web",
                    "format": "pikg",
                    "name": "package",
                    "src_dir": "apps/package",
                }
            },
            "apps": {
                "system": {
                    "name": "system",
                    "rootfs": "rootfs",
                    "default_target_rootfs": "/opt/system",
                    "modules": {"package": "data/cache/package.pikg"},
                }
            },
        }
        for invalid in ([], "dapp_meta", {"meta_dir": ""}, {"meta_dir": []}):
            data = json.loads(json.dumps(base))
            data["modules"]["package"]["pikg"] = invalid
            with self.subTest(pikg=invalid):
                with self.assertRaisesRegex(ValueError, "pikg"):
                    BuckyProject.from_dict(data)

    def test_project_parses_and_serializes_web_pikg_format(self):
        project = BuckyProject.from_dict(
            {
                "name": "test-project",
                "modules": {
                    "package": {
                        "type": "web",
                        "format": "pikg",
                        "name": "package",
                        "src_dir": "apps/package",
                    }
                },
                "apps": {
                    "system": {
                        "name": "system",
                        "rootfs": "rootfs",
                        "default_target_rootfs": "/opt/system",
                        "modules": {"package": "data/cache/package.pikg"},
                    }
                },
            }
        )

        module = project.modules["package"]
        self.assertIsInstance(module, WebModuleInfo)
        self.assertEqual(module.format, "pikg")
        self.assertEqual(module.pikg, PikgModuleConfig())
        serialized = project.to_dict()["modules"]["package"]
        self.assertEqual(serialized["type"], "web")
        self.assertEqual(serialized["format"], "pikg")
        self.assertNotIn("pikg", serialized)

    def test_custom_pikg_meta_dir_round_trips(self):
        project = BuckyProject.from_dict(
            {
                "name": "test-project",
                "modules": {
                    "package": {
                        "type": "web",
                        "format": "pikg",
                        "name": "package",
                        "src_dir": "apps/package",
                        "pikg": {"meta_dir": "release-meta"},
                    }
                },
                "apps": {
                    "system": {
                        "name": "system",
                        "rootfs": "rootfs",
                        "default_target_rootfs": "/opt/system",
                        "modules": {"package": "data/cache/package.pikg"},
                    }
                },
            }
        )

        self.assertEqual(
            project.to_dict()["modules"]["package"]["pikg"],
            {"meta_dir": "release-meta"},
        )

    def test_web_pikg_type_is_rejected_without_compatibility(self):
        with self.assertRaisesRegex(ValueError, "type: web with format: pikg"):
            BuckyProject.from_dict(
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

    def test_rust_pikg_is_accepted(self):
        project = BuckyProject.from_dict(
            {
                "name": "test-project",
                "modules": {
                    "package": {
                        "type": "rust",
                        "format": "pikg",
                        "name": "package",
                    }
                },
                "apps": {
                    "system": {
                        "name": "system",
                        "rootfs": "rootfs",
                        "default_target_rootfs": "/opt/system",
                        "modules": {"package": "data/cache/package.pikg"},
                    }
                },
            },
        )

        module = project.modules["package"]
        self.assertIsInstance(module, RustModuleInfo)
        self.assertEqual(module.format, "pikg")
        self.assertEqual(project.to_dict()["modules"]["package"]["format"], "pikg")

    def test_pikg_requires_same_key_install_entry(self):
        project = BuckyProject(
            name="test-project",
            version="0.1.0",
            modules={
                "package": WebModuleInfo(
                    name="package",
                    src_dir=Path("apps/package"),
                    format="pikg",
                    pikg=PikgModuleConfig(),
                )
            },
        )
        with self.assertRaisesRegex(ValueError, "same-key"):
            project.validate()


class WebBuilderTests(unittest.TestCase):
    def test_web_builder_uses_no_lockfile_and_returns_work_dir_without_dist(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_dir = Path(tmp_dir) / "apps" / "package"
            source_dir.mkdir(parents=True)
            (source_dir / "package.json").write_text(
                json.dumps({"dependencies": {"buckyos": "latest"}}),
                encoding="utf-8",
            )
            project = BuckyProject(
                name="test-project",
                version="0.1.0",
                base_dir=Path(tmp_dir),
                modules={
                    "package": WebModuleInfo(
                        name="package",
                        src_dir=Path("apps/package"),
                        format="pikg",
                    )
                },
            )

            with patch.object(build_web_apps.subprocess, "run") as run_mock:
                result = build_web_apps.build_web_module(project, "package")

        self.assertEqual(result.work_dir, source_dir)
        self.assertEqual(result.artifacts, [])
        self.assertEqual(
            [call.args[0] for call in run_mock.call_args_list],
            ["pnpm install --no-lockfile", "pnpm run build"],
        )
        for call in run_mock.call_args_list:
            self.assertTrue(call.kwargs["shell"])
            self.assertEqual(call.kwargs["cwd"], source_dir)
            self.assertTrue(call.kwargs["check"])


class NoneBuilderTests(unittest.TestCase):
    def test_none_builder_only_returns_the_resolved_source_work_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_dir = root / "apps" / "package"
            source_dir.mkdir(parents=True)
            project = BuckyProject(
                name="test-project",
                version="0.1.0",
                base_dir=root,
                modules={
                    "package": NoneModuleInfo(
                        name="package",
                        src_dir=Path("apps/package"),
                        format="pikg",
                    )
                },
            )

            results = build_none.build_none_modules(project, ["package"])

        result = results["package"]
        self.assertEqual(result.build_type, "none")
        self.assertEqual(result.work_dir, source_dir)
        self.assertEqual(result.artifacts, [])


class FilesFormatterTests(unittest.TestCase):
    def test_web_files_requires_dist_but_web_build_result_does_not(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir) / "web"
            work_dir.mkdir()
            formatter = formatters.FilesFormatter()
            result = BuildResult(
                module_key="frontend",
                build_type="web",
                work_dir=work_dir,
            )
            with self.assertRaisesRegex(FileNotFoundError, "requires a dist directory"):
                formatter.materialize(
                    BuckyProject(name="test", version="0.1.0"),
                    "frontend",
                    result,
                    [],
                )


class BuildPipelineTests(unittest.TestCase):
    def test_files_formatter_rejects_none_before_build(self):
        project = BuckyProject(
            name="test-project",
            version="0.1.0",
            modules={
                "static": NoneModuleInfo(
                    name="static",
                    src_dir=Path("apps/static"),
                )
            },
        )

        with self.assertRaisesRegex(ValueError, "does not support builder type none"):
            build_pipeline.build(project, "", skip_web_module=False)

    def test_new_pikg_module_is_discovered_by_format_and_built_once(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            work_dir = root / "apps" / "future"
            work_dir.mkdir(parents=True)
            project = BuckyProject(
                name="test-project",
                version="0.1.0",
                base_dir=root,
                modules={
                    "future_package": WebModuleInfo(
                        name="future_package",
                        src_dir=Path("apps/future"),
                        format="pikg",
                        pikg=PikgModuleConfig(),
                    )
                },
                apps={
                    "system": AppInfo(
                        name="system",
                        rootfs=Path("rootfs-system"),
                        default_target_rootfs=Path("/opt/system"),
                        modules={"future_package": "data/cache/future.pikg"},
                    ),
                    "recovery": AppInfo(
                        name="recovery",
                        rootfs=Path("rootfs-recovery"),
                        default_target_rootfs=Path("/opt/recovery"),
                        modules={"future_package": "data/cache/future.pikg"},
                    ),
                },
            )
            calls = {"build": [], "format": []}

            class TestBuilder:
                build_type = "web"

                def plan(self, module_key, module):
                    return BuildResultSpec(build_type="web")

                def build_modules(self, selected_project, module_keys, context):
                    calls["build"].append(list(module_keys))
                    return {
                        module_key: BuildResult(module_key, "web", work_dir)
                        for module_key in module_keys
                    }

            class TestFormatter:
                format_name = "pikg"
                supported_build_types = None

                def materialize(
                    self,
                    selected_project,
                    module_key,
                    result,
                    install_references,
                ):
                    calls["format"].append(
                        (module_key, [reference.app_name for reference in install_references])
                    )
                    return []

            with (
                patch.object(
                    build_pipeline,
                    "BUILDERS",
                    BuilderRegistry([TestBuilder()]),
                ),
                patch.object(
                    build_pipeline,
                    "FORMATTERS",
                    FormatterRegistry([TestFormatter()]),
                ),
            ):
                build_pipeline.build(project, "", skip_web_module=False)

        self.assertEqual(calls["build"], [["future_package"]])
        self.assertEqual(
            calls["format"],
            [("future_package", ["system", "recovery"])],
        )


class PikgFormatterTests(unittest.TestCase):
    def _fixture(self, root: Path):
        work_dir = root / "apps" / "package"
        meta_dir = work_dir / "dapp_meta"
        dist_dir = work_dir / "dapp_dist"
        source_dir = root / "external-source"
        source_dir.mkdir(parents=True)
        meta_dir.mkdir(parents=True)
        dist_dir.mkdir()
        (meta_dir / "app.json").write_text(
            json.dumps({"did": "did:bns:package.buckyos", "version": "1.2.3"}),
            encoding="utf-8",
        )
        (meta_dir / "pikg.json").write_text(
            json.dumps(
                {
                    "output_dir": "../dapp_dist",
                    "pikg_file": "package.pikg",
                    "sub_pkgs": {
                        "script": {
                            "source": {"type": "path", "path": str(source_dir)}
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        pikg_path = dist_dir / "package.pikg"
        pikg_path.write_bytes(b"verified-pikg")
        project = BuckyProject(
            name="test-project",
            version="0.1.0",
            base_dir=root,
            modules={
                "package": NoneModuleInfo(
                    name="package",
                    src_dir=Path("apps/package"),
                    format="pikg",
                    pikg=PikgModuleConfig(),
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
        reference = InstallReference(
            app_name="system",
            install_path="data/cache/package.pikg",
            staging_path=root / "rootfs" / "data" / "cache" / "package.pikg",
        )
        return project, work_dir, dist_dir, source_dir, pikg_path, reference

    def test_pikg_uses_metadata_sources_without_requiring_dist(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            project, work_dir, dist_dir, source_dir, pikg_path, reference = self._fixture(root)
            size = pikg_path.stat().st_size
            digest = formatters._sha256(pikg_path)
            app_doc_id = "appdoc:" + "a" * 64
            responses = [
                {
                    "dist_dir": str(dist_dir),
                    "app_doc_object_id": app_doc_id,
                    "ready_for_pack": True,
                },
                {
                    "dist_dir": str(dist_dir),
                    "pikg_path": str(pikg_path),
                    "size": size,
                    "pikg_digest": digest,
                    "app_doc_object_id": app_doc_id,
                    "validation": "passed",
                },
                {
                    "schema_version": 1,
                    "pikg_path": str(pikg_path),
                    "size": size,
                    "pikg_digest": digest,
                    "valid": True,
                    "app": {
                        "did": "did:bns:package.buckyos",
                        "version": "1.2.3",
                        "app_doc_object_id": app_doc_id,
                    },
                },
            ]
            result = BuildResult(
                module_key="package",
                build_type="none",
                work_dir=work_dir,
            )

            with patch.object(
                formatters,
                "_run_buckyos_json",
                side_effect=responses,
            ) as run_mock:
                records = formatters.PikgFormatter().materialize(
                    project,
                    "package",
                    result,
                    [reference],
                )

            staging = reference.staging_path
            self.assertEqual(staging.read_bytes(), b"verified-pikg")
            self.assertEqual(records[0].digest, digest)
            build_argv = run_mock.call_args_list[0].args[0]
            for call in run_mock.call_args_list:
                self.assertEqual(call.args[0][:3], ["npx", "--yes", "buckyos@latest"])
            self.assertIn("--allow-read", build_argv)
            self.assertIn(str(source_dir.resolve()), build_argv)
            self.assertEqual(
                build_argv[-5:],
                ["--output", "json", "pikg", "build", str(work_dir / "dapp_meta")],
            )
            self.assertFalse((work_dir / "dist").exists())
            self.assertFalse((work_dir / "node_modules").exists())

    def test_pikg_uses_the_same_path_for_a_rust_build_result(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            project, work_dir, _, _, _, reference = self._fixture(root)
            project.modules["package"] = RustModuleInfo(
                name="package",
                format="pikg",
                pikg=PikgModuleConfig(),
            )
            result = BuildResult(
                module_key="package",
                build_type="rust",
                work_dir=work_dir,
            )

            with patch.object(
                formatters,
                "_run_buckyos_json",
                side_effect=RuntimeError("reached common pikg CLI path"),
            ) as run_mock:
                with self.assertRaisesRegex(RuntimeError, "reached common"):
                    formatters.PikgFormatter().materialize(
                        project, "package", result, [reference]
                    )

            run_mock.assert_called_once()

    def test_cli_runner_requires_success_envelope_and_uses_shell_string(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "data": {"value": 1},
                    "meta": {},
                }
            ),
            stderr="",
        )
        with patch.object(formatters.subprocess, "run", return_value=completed) as run_mock:
            data = formatters._run_buckyos_json(
                ["npx", "--yes", "buckyos@latest", "--output", "json", "pikg", "info", "a.pikg"],
                Path.cwd(),
            )

        self.assertEqual(data, {"value": 1})
        self.assertIsInstance(run_mock.call_args.args[0], str)
        self.assertTrue(run_mock.call_args.kwargs["shell"])
        self.assertEqual(run_mock.call_args.kwargs["stdout"], formatters.subprocess.PIPE)
        self.assertEqual(run_mock.call_args.kwargs["stderr"], formatters.subprocess.PIPE)

    def test_cli_runner_rejects_stdout_noise(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout='log line\n{"schema_version":1,"ok":true,"data":{},"meta":{}}',
            stderr="",
        )
        with patch.object(formatters.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                formatters._run_buckyos_json(
                    ["npx", "--yes", "buckyos@latest", "--output", "json", "pikg", "info", "a.pikg"],
                    Path.cwd(),
                )

    def test_cli_runner_preserves_json_error_on_nonzero_exit(self):
        completed = SimpleNamespace(
            returncode=2,
            stdout=json.dumps({
                "schema_version": 1,
                "ok": False,
                "error": {
                    "code": "SCHEMA_VALIDATION_FAILED",
                    "message": "app.json.content_handlers is not allowed",
                },
            }),
            stderr="",
        )
        with patch.object(formatters.subprocess, "run", return_value=completed):
            with self.assertRaises(RuntimeError) as failure:
                formatters._run_buckyos_json(["buckyos", "pikg", "build"], Path.cwd())
        self.assertIn("exit code 2", str(failure.exception))
        self.assertIn("SCHEMA_VALIDATION_FAILED", str(failure.exception))
        self.assertIn("app.json.content_handlers is not allowed", str(failure.exception))

    def test_transaction_rolls_back_all_targets(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "new.pikg"
            source.write_bytes(b"new")
            targets = [root / "one.pikg", root / "two.pikg"]
            targets[0].write_bytes(b"old-one")
            targets[1].write_bytes(b"old-two")
            real_replace = os.replace
            calls = 0

            def fail_second_install(source_path, target_path):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("injected replace failure")
                return real_replace(source_path, target_path)

            with patch.object(formatters.os, "replace", side_effect=fail_second_install):
                with self.assertRaisesRegex(OSError, "injected"):
                    formatters._transactional_install(
                        source,
                        targets,
                        source.stat().st_size,
                        formatters._sha256(source),
                    )

            self.assertEqual(targets[0].read_bytes(), b"old-one")
            self.assertEqual(targets[1].read_bytes(), b"old-two")


if __name__ == "__main__":
    unittest.main()

class LocalSdkCommandTests(unittest.TestCase):
    def test_local_cli_preserves_argument_boundaries(self):
        command = ['node', '/tmp/sdk with spaces/launcher.mjs']
        with patch.dict(os.environ, {'BUCKYOS_PIKG_COMMAND': json.dumps(command)}):
            self.assertEqual(formatters._buckyos_command(), command)

    def test_invalid_cli_commands_fail_before_execution(self):
        for value in ['[]', '{}', '"node"', '["node", ""]', '[1]']:
            with self.subTest(value=value), patch.dict(os.environ, {'BUCKYOS_PIKG_COMMAND': value}):
                with self.assertRaises(ValueError):
                    formatters._buckyos_command()
