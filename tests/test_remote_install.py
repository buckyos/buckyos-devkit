import tempfile
import unittest
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src import install
from src.project import AppInfo, BuckyProject


class FakeRemoteHost:
    destination = "deploy@example.test"

    def __init__(self, state: str = "absent") -> None:
        self.state = state
        self.checked_paths = []

    def resolve_target_path(self, value):
        return PurePosixPath(str(value))

    def path_state(self, path):
        self.checked_paths.append(path)
        return self.state


class RecordingRemoteHost(FakeRemoteHost):
    def __init__(self, state: str = "present") -> None:
        super().__init__(state)
        self.copied_files = []
        self.copied_directories = []

    @staticmethod
    def child_path(root, value):
        return root / PurePosixPath(str(value))

    def copy_file(self, source, target, executable=False):
        self.copied_files.append((source, target, executable))

    def copy_directory(self, source, target):
        self.copied_directories.append((source, target))


class RemoteInstallModeTests(unittest.TestCase):
    def make_project(self) -> BuckyProject:
        return BuckyProject(
            name="test-project",
            version="0.1.0",
            apps={
                "buckyos": AppInfo(
                    name="buckyos",
                    rootfs=Path("rootfs"),
                    default_target_rootfs=Path("/opt/buckyos"),
                )
            },
        )

    def test_fresh_remote_reinstall_runs_without_confirmation(self):
        remote = FakeRemoteHost("absent")
        with patch.object(install, "reinstall_app") as reinstall_mock, patch(
            "builtins.input", side_effect=AssertionError("confirmation is not expected")
        ):
            result = install._run_install(
                self.make_project(),
                install_all=True,
                app_name="buckyos",
                skip_web_module=False,
                target_rootfs=None,
                remote=remote,
            )

        self.assertEqual(result, 0)
        reinstall_mock.assert_called_once()
        self.assertEqual(remote.checked_paths, [PurePosixPath("/opt/buckyos")])

    def test_binary_update_runs_without_confirmation(self):
        remote = FakeRemoteHost("present")
        with patch.object(install, "update_app") as update_mock, patch(
            "builtins.input", side_effect=AssertionError("confirmation is not expected")
        ):
            result = install._run_install(
                self.make_project(),
                install_all=False,
                app_name="buckyos",
                skip_web_module=False,
                target_rootfs=None,
                remote=remote,
            )

        self.assertEqual(result, 0)
        update_mock.assert_called_once()
        self.assertEqual(remote.checked_paths, [])

    def test_binary_update_copies_modules_to_remote_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            source_file = base_dir / "rootfs" / "bin" / "daemon"
            source_file.parent.mkdir(parents=True)
            source_file.write_bytes(b"binary")
            project = BuckyProject(
                name="test-project",
                version="0.1.0",
                base_dir=base_dir,
                apps={
                    "buckyos": AppInfo(
                        name="buckyos",
                        rootfs=Path("rootfs"),
                        default_target_rootfs=Path("/opt/buckyos"),
                        modules={"daemon": "bin/daemon"},
                    )
                },
            )
            remote = RecordingRemoteHost()

            install.update_app(
                project,
                "buckyos",
                check_reinstall=True,
                remote=remote,
            )

        self.assertEqual(
            remote.copied_files,
            [(source_file, PurePosixPath("/opt/buckyos/bin/daemon"), True)],
        )
        self.assertEqual(remote.copied_directories, [])

    def test_existing_remote_reinstall_requires_confirmation(self):
        remote = FakeRemoteHost("present")
        with patch.object(install, "reinstall_app") as reinstall_mock, patch(
            "builtins.input", return_value="no"
        ) as input_mock:
            result = install._run_install(
                self.make_project(),
                install_all=True,
                app_name="buckyos",
                skip_web_module=False,
                target_rootfs=None,
                remote=remote,
            )

        self.assertEqual(result, 1)
        input_mock.assert_called_once()
        reinstall_mock.assert_not_called()

    def test_yes_confirms_existing_remote_reinstall_noninteractively(self):
        remote = FakeRemoteHost("present")
        with patch.object(install, "reinstall_app") as reinstall_mock, patch(
            "builtins.input", side_effect=AssertionError("confirmation is not expected")
        ):
            result = install._run_install(
                self.make_project(),
                install_all=True,
                app_name="buckyos",
                skip_web_module=False,
                target_rootfs=None,
                remote=remote,
                assume_yes=True,
            )

        self.assertEqual(result, 0)
        reinstall_mock.assert_called_once()
        self.assertEqual(remote.checked_paths, [])


class RemoteInstallCommandTests(unittest.TestCase):
    def test_ssh_and_scp_receive_connection_options(self):
        completed = SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
        with patch.object(install.shutil, "which", return_value="/usr/bin/tool"), patch.object(
            install.subprocess, "run", return_value=completed
        ) as run_mock:
            remote = install.RemoteInstallHost(
                "example.test",
                user="deploy",
                port=2222,
                identity_file=Path("/tmp/deploy-key"),
                ssh_options=["ProxyJump=bastion", "StrictHostKeyChecking=no"],
                use_sudo=True,
            )
            output = remote.run("mkdir -p /opt/buckyos", capture_output=True, sudo=True)
            remote._scp(Path("payload"), PurePosixPath("/tmp/payload"), recursive=True)

        self.assertEqual(output, "ok")
        ssh_command = run_mock.call_args_list[0].args[0]
        self.assertEqual(ssh_command[0], "ssh")
        self.assertIn("-p", ssh_command)
        self.assertIn("2222", ssh_command)
        self.assertIn("/tmp/deploy-key", ssh_command)
        self.assertEqual(ssh_command[-2], "deploy@example.test")
        self.assertTrue(ssh_command[-1].startswith("sudo -n sh -c "))

        scp_command = run_mock.call_args_list[1].args[0]
        self.assertEqual(scp_command[0], "scp")
        self.assertIn("-P", scp_command)
        self.assertIn("-r", scp_command)
        self.assertEqual(scp_command[-1], "deploy@example.test:/tmp/payload")

    def test_remote_target_rejects_relative_and_root_paths(self):
        with patch.object(install.shutil, "which", return_value="/usr/bin/tool"):
            remote = install.RemoteInstallHost("example.test")

        for path in ("relative/path", "/"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                remote.resolve_target_path(path)

    def test_install_main_accepts_space_separated_remote_options(self):
        project = BuckyProject(name="test", version="0.1.0")
        remote_instance = MagicMock()
        remote_instance.destination = "deploy@192.0.2.10"
        remote_instance.__enter__.return_value = remote_instance
        remote_instance.__exit__.return_value = None

        with patch.object(
            install.BuckyProject,
            "get_project_config_file",
            return_value=Path("/tmp/bucky_project.yaml"),
        ), patch.object(
            install.BuckyProject, "get_project_local_config_file", return_value=None
        ), patch.object(
            install.BuckyProject, "from_file", return_value=project
        ), patch.object(
            install, "RemoteInstallHost", return_value=remote_instance
        ) as remote_class, patch.object(
            install, "_run_install", return_value=0
        ) as run_install_mock:
            result = install.install_main(
                [
                    "--remote",
                    "192.0.2.10",
                    "--ssh-user",
                    "deploy",
                    "--ssh-port",
                    "2222",
                    "--ssh-key",
                    "/tmp/deploy-key",
                    "--ssh-option",
                    "ProxyJump=bastion",
                    "--sudo",
                    "--yes",
                ]
            )

        self.assertEqual(result, 0)
        remote_class.assert_called_once_with(
            "192.0.2.10",
            user="deploy",
            port=2222,
            identity_file=Path("/tmp/deploy-key"),
            ssh_options=["ProxyJump=bastion"],
            use_sudo=True,
        )
        self.assertIs(run_install_mock.call_args.kwargs["remote"], remote_instance)
        self.assertTrue(run_install_mock.call_args.kwargs["assume_yes"])


if __name__ == "__main__":
    unittest.main()
