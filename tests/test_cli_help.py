import contextlib
import importlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

build = importlib.import_module("src.build")
cert_mgr = importlib.import_module("src.cert_mgr")
install = importlib.import_module("src.install")
remote_main = importlib.import_module("src.remote.main")
sn_test = importlib.import_module("src.sn_test")


class CliHelpTests(unittest.TestCase):
    def capture_stdout(self, func, *args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = func(*args)
        return result, stdout.getvalue()

    def assert_exits_zero_with_help(self, func, *args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout) as output:
            with self.assertRaises(SystemExit) as raised:
                func(*args)
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("usage:", output.getvalue())

    def test_build_help_does_not_load_project_config(self):
        with patch.object(
            build.BuckyProject,
            "get_project_config_file",
            side_effect=AssertionError("project config should not be loaded for help"),
        ):
            _, output = self.capture_stdout(build.build_main, ["--help"])

        self.assertIn("usage: buckyos-build", output)
        self.assertIn("-h, --help", output)
        self.assertIn("--skip-web", output)
        self.assertIn("-s, --select", output)
        self.assertNotIn("DEBUG:", output)

    def test_install_help_does_not_load_project_config(self):
        with patch.object(
            install.BuckyProject,
            "get_project_config_file",
            side_effect=AssertionError("project config should not be loaded for help"),
        ):
            _, output = self.capture_stdout(install.install_main, ["-h"])

        self.assertIn("usage:", output)
        self.assertIn("-h, --help", output)
        self.assertIn("--all", output)
        self.assertIn("--target-rootfs", output)
        self.assertNotIn("buckyos_root:", output)

    def test_remote_subcommands_accept_help(self):
        subcommands = [
            "clean_vms",
            "create_vms",
            "snapshot",
            "restore",
            "info_vms",
            "start_vms",
            "stop_vms",
            "install",
            "update",
            "start",
            "stop",
            "uninstall",
            "clog",
            "run",
            "exec",
        ]
        for subcommand in subcommands:
            with self.subTest(subcommand=subcommand):
                self.assert_exits_zero_with_help(
                    remote_main.main,
                    ["dev_group", subcommand, "--help"],
                )

    def test_remote_stop_without_device_stops_all_devices(self):
        calls = []
        workspace = SimpleNamespace(
            remote_devices={"sn": object(), "alice-ood1": object()},
            stop=lambda device_id, apps=None: calls.append((device_id, apps)),
        )

        with patch.object(remote_main, "build_workspace", return_value=workspace):
            result = remote_main.main(["dev_group", "stop"])

        self.assertEqual(result, 0)
        self.assertEqual(calls, [("sn", None), ("alice-ood1", None)])

    def test_remote_stop_accepts_device_and_apps_filter(self):
        calls = []
        workspace = SimpleNamespace(
            remote_devices={"sn": object(), "alice-ood1": object()},
            stop=lambda device_id, apps=None: calls.append((device_id, apps)),
        )

        with patch.object(remote_main, "build_workspace", return_value=workspace):
            result = remote_main.main(
                ["dev_group", "stop", "alice-ood1", "--apps", "buckyos"]
            )

        self.assertEqual(result, 0)
        self.assertEqual(calls, [("alice-ood1", ["buckyos"])])

    def test_remote_run_passes_workspace_env_params(self):
        calls = []
        env_params = {"system": {"base_dir": "/tmp/devkit"}}
        workspace = SimpleNamespace(
            build_env_params=lambda: env_params,
            run=lambda device_id, cmds, params: calls.append((device_id, cmds, params)),
        )

        with patch.object(remote_main, "build_workspace", return_value=workspace):
            result = remote_main.main(["dev_group", "run", "sn", "echo {{system.base_dir}}"])

        self.assertEqual(result, 0)
        self.assertEqual(calls, [("sn", ["echo {{system.base_dir}}"], env_params)])

    def test_remote_uninstall_without_device_uninstalls_all_devices(self):
        calls = []
        workspace = SimpleNamespace(
            remote_devices={"sn": object(), "alice-ood1": object()},
            uninstall=lambda device_id, apps=None: calls.append((device_id, apps)),
        )

        with patch.object(remote_main, "build_workspace", return_value=workspace):
            result = remote_main.main(["dev_group", "uninstall"])

        self.assertEqual(result, 0)
        self.assertEqual(calls, [("sn", None), ("alice-ood1", None)])

    def test_remote_uninstall_accepts_device_and_apps_filter(self):
        calls = []
        workspace = SimpleNamespace(
            remote_devices={"sn": object(), "alice-ood1": object()},
            uninstall=lambda device_id, apps=None: calls.append((device_id, apps)),
        )

        with patch.object(remote_main, "build_workspace", return_value=workspace):
            result = remote_main.main(
                ["dev_group", "uninstall", "alice-ood1", "--apps", "buckyos"]
            )

        self.assertEqual(result, 0)
        self.assertEqual(calls, [("alice-ood1", ["buckyos"])])

    def test_cert_subcommands_accept_help(self):
        for subcommand in ["create_ca", "create_cert", "install_ca"]:
            with self.subTest(subcommand=subcommand):
                with patch("sys.argv", ["buckyos-cert", subcommand, "--help"]):
                    self.assert_exits_zero_with_help(cert_mgr.main)

    def test_sn_test_accepts_help(self):
        with patch("sys.argv", ["buckyos-sn-test", "--help"]):
            self.assert_exits_zero_with_help(sn_test.main)


if __name__ == "__main__":
    unittest.main()
