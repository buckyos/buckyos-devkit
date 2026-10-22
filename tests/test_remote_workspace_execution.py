import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.remote.worksapce import Workspace
import src.remote.worksapce as workspace_module
import src.remote.main as remote_main


class FailingRemoteDevice:
    def __init__(self):
        self.commands = []

    def get_device_info(self):
        return {"device_id": "sn", "ip": "127.0.0.1"}

    def run_command(self, command):
        self.commands.append(command)
        return "", "failed", 1


class RemoteWorkspaceExecutionTests(unittest.TestCase):
    def make_creation_workspace(self):
        workspace = object.__new__(Workspace)
        nodes = {
            node_id: SimpleNamespace(instance_commands=[f"echo {node_id}"])
            for node_id in ["alice-ood1", "sn", "bob-ood1"]
        }
        workspace.nodes = SimpleNamespace(
            nodes=nodes,
            get_node=nodes.get,
            get_node_id_by_init_orders=lambda: ["sn", "alice-ood1", "bob-ood1"],
        )
        workspace.build_env_params = Mock(return_value={"sn": {"ip": "192.0.2.1"}})
        workspace.run = Mock()
        return workspace

    def test_create_vms_reports_all_failed_nodes_and_exits_before_initialization(self):
        workspace = self.make_creation_workspace()
        vm_manager = Mock()
        vm_manager.create_vm.side_effect = [False, True, OSError("guest unavailable")]
        stderr = io.StringIO()

        with patch.object(workspace_module.VMManager, "get_instance", return_value=vm_manager), \
                patch.object(workspace_module.time, "sleep") as sleep_mock, \
                patch.object(remote_main, "build_workspace", return_value=workspace), \
                contextlib.redirect_stderr(stderr):
            result = remote_main.main(["test_group", "create_vms"])

        self.assertEqual(result, 1)
        self.assertEqual(vm_manager.create_vm.call_count, 3)
        self.assertIn("VM creation failed for nodes: alice-ood1, bob-ood1", stderr.getvalue())
        self.assertIn("skipping instance_commands", stderr.getvalue())
        workspace.build_env_params.assert_not_called()
        workspace.run.assert_not_called()
        sleep_mock.assert_not_called()

    def test_create_vms_runs_checked_instance_commands_in_initialization_order(self):
        workspace = self.make_creation_workspace()
        vm_manager = Mock()
        vm_manager.create_vm.return_value = True

        with patch.object(workspace_module.VMManager, "get_instance", return_value=vm_manager), \
                patch.object(workspace_module.time, "sleep"):
            workspace.create_vms()

        self.assertEqual([call.args[0] for call in workspace.run.call_args_list],
                         ["sn", "alice-ood1", "bob-ood1"])
        for call in workspace.run.call_args_list:
            self.assertTrue(call.kwargs["check"])
            self.assertEqual(call.args[2], workspace.build_env_params.return_value)

    def test_instance_command_failure_stops_initialization_and_returns_nonzero(self):
        workspace = self.make_creation_workspace()
        workspace.run.side_effect = RuntimeError("instance command exited with 1")
        vm_manager = Mock()
        vm_manager.create_vm.return_value = True
        stderr = io.StringIO()

        with patch.object(workspace_module.VMManager, "get_instance", return_value=vm_manager), \
                patch.object(workspace_module.time, "sleep"), \
                patch.object(remote_main, "build_workspace", return_value=workspace), \
                contextlib.redirect_stderr(stderr):
            result = remote_main.main(["test_group", "create_vms"])

        self.assertEqual(result, 1)
        self.assertIn("instance command exited with 1", stderr.getvalue())
        workspace.run.assert_called_once()

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
