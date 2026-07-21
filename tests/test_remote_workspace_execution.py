import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.remote.worksapce import Workspace
import src.remote.worksapce as workspace_module


class FailingRemoteDevice:
    def __init__(self):
        self.commands = []

    def get_device_info(self):
        return {"device_id": "sn", "ip": "127.0.0.1"}

    def run_command(self, command):
        self.commands.append(command)
        return "", "failed", 1


class RemoteWorkspaceExecutionTests(unittest.TestCase):
    def test_execute_app_command_propagates_first_command_failure(self):
        workspace = object.__new__(Workspace)
        workspace.base_dir = None
        workspace.nodes = SimpleNamespace(
            get_node=lambda device_id: object(),
            get_all_node_ids=lambda: ["sn"],
            get_app_params=lambda device_id, app_name: {},
        )
        remote_device = FailingRemoteDevice()
        workspace.remote_devices = {"sn": remote_device}
        workspace.app_list = SimpleNamespace(
            get_app=lambda app_name: SimpleNamespace(
                config_dir=None,
                get_command=lambda command_name: ["false", "echo should-not-run"],
            )
        )

        with self.assertRaisesRegex(RuntimeError, "exited with 1"):
            workspace.execute_app_command("sn", "demo", "start")

        self.assertEqual(remote_device.commands, ["false"])

    def test_info_vms_does_not_build_or_print_environment(self):
        workspace = object.__new__(Workspace)
        workspace.nodes = SimpleNamespace(nodes={"sn": object()})
        workspace.build_env_params = lambda: (_ for _ in ()).throw(
            AssertionError("environment must not be read")
        )
        vm_manager = SimpleNamespace(get_vm_ip=lambda node_id: ["192.0.2.1"])
        output = io.StringIO()

        with patch.object(
            workspace_module.VMManager, "get_instance", return_value=vm_manager
        ), contextlib.redirect_stdout(output):
            info = workspace.info_vms()

        self.assertEqual(info, {"sn": {"ip_v4": ["192.0.2.1"]}})
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
