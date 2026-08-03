import importlib
import unittest
from unittest.mock import patch

vm_mgr = importlib.import_module("src.remote.vm_mgr")


class MultipassPushDirTests(unittest.TestCase):
    def test_push_dir_prepares_root_owned_target_with_sudo(self):
        backend = vm_mgr.MultipassVMBackend()

        with patch.object(
            backend,
            "exec_command",
            return_value=("__BUCKYOS_REMOTE_DIR_READY__\n", "", 0),
        ) as exec_mock, patch.object(backend, "push_file", return_value=True) as push_mock:
            result = backend.push_dir("sn", "/opt/web3-gateway", "/opt/web3-gateway")

        self.assertTrue(result)
        command = exec_mock.call_args.args[1]
        self.assertIn("sudo mkdir -p /opt/web3-gateway", command)
        self.assertIn("sudo chown -R $(id -u):$(id -g) /opt/web3-gateway", command)
        self.assertIn("test -w /opt/web3-gateway", command)
        push_mock.assert_called_once_with(
            "sn",
            "/opt/web3-gateway/.",
            "/opt/web3-gateway",
            recursive=True,
        )

    def test_push_dir_stops_when_remote_target_is_not_writable(self):
        backend = vm_mgr.MultipassVMBackend()

        with patch.object(
            backend,
            "exec_command",
            return_value=("", "permission denied", 1),
        ), patch.object(backend, "push_file") as push_mock:
            result = backend.push_dir("sn", "/opt/web3-gateway", "/opt/web3-gateway")

        self.assertFalse(result)
        push_mock.assert_not_called()


class PVEBackendTests(unittest.TestCase):
    def _backend(self):
        with patch.object(vm_mgr.PVEVMBackend, "_detect_node", return_value="pve1"):
            return vm_mgr.PVEVMBackend()

    def test_memory_values_are_converted_to_megabytes(self):
        self.assertEqual(vm_mgr.PVEVMBackend._memory_mb("1G"), 1024)
        self.assertEqual(vm_mgr.PVEVMBackend._memory_mb("512M"), 512)
        self.assertEqual(vm_mgr.PVEVMBackend._memory_mb(2048), 2048)

    def test_cloud_config_transparently_adds_guest_agent(self):
        source = "packages:\n- docker.io\n- curl\nruncmd:\n- echo ready\n"
        result = vm_mgr.PVEVMBackend._prepare_cloud_config(source, True)
        self.assertTrue(result.startswith("#cloud-config\n"))
        self.assertIn("packages:\n- qemu-guest-agent\n- docker.io\n- curl\n", result)
        self.assertIn("runcmd:\n- echo ready\n", result)

    def test_cloud_config_does_not_duplicate_guest_agent(self):
        source = "#cloud-config\npackages: [curl, qemu-guest-agent]\n"
        result = vm_mgr.PVEVMBackend._prepare_cloud_config(source, True)
        self.assertEqual(result.count("qemu-guest-agent"), 1)

    def test_agent_only_cloud_config_is_supported(self):
        result = vm_mgr.PVEVMBackend._prepare_cloud_config("#cloud-config\n", True)
        self.assertEqual(result, "#cloud-config\npackages:\n- qemu-guest-agent\n")

    def test_vmid_lookup_matches_exact_qemu_name(self):
        backend = self._backend()
        with patch.object(backend, "_resources", return_value=[
            {"type": "qemu", "name": "node-a-old", "vmid": 100},
            {"type": "lxc", "name": "node-a", "vmid": 101},
            {"type": "qemu", "name": "node-a", "vmid": 102},
        ]):
            self.assertEqual(backend._vmid("node-a"), 102)

    def test_guest_agent_command_result_matches_backend_contract(self):
        backend = self._backend()
        completed = vm_mgr.subprocess.CompletedProcess(
            [], 0, '{"exitcode":2,"out-data":"out","err-data":"err"}', ""
        )
        with patch.object(backend, "_vmid", return_value=102), patch.object(
            backend, "_run", return_value=completed
        ):
            self.assertEqual(backend.exec_command("node-a", "false"), ("out", "err", 2))

    def test_manager_accepts_pve_backend(self):
        old_instance = vm_mgr.VMManager._instance
        old_type = vm_mgr.VMManager._backend_type
        try:
            vm_mgr.VMManager._instance = None
            vm_mgr.VMManager._backend_type = None
            with patch.object(vm_mgr.PVEVMBackend, "_detect_node", return_value="pve1"):
                manager = vm_mgr.VMManager("pve")
            self.assertIsInstance(manager.backend, vm_mgr.PVEVMBackend)
        finally:
            vm_mgr.VMManager._instance = old_instance
            vm_mgr.VMManager._backend_type = old_type

    def test_get_instance_honors_backend_environment(self):
        old_instance = vm_mgr.VMManager._instance
        old_type = vm_mgr.VMManager._backend_type
        try:
            vm_mgr.VMManager._instance = None
            vm_mgr.VMManager._backend_type = None
            with patch.dict(vm_mgr.os.environ, {"BUCKYOS_VM_BACKEND": "pve"}), patch.object(
                vm_mgr.PVEVMBackend, "_detect_node", return_value="pve1"
            ):
                manager = vm_mgr.VMManager.get_instance()
            self.assertIsInstance(manager.backend, vm_mgr.PVEVMBackend)
        finally:
            vm_mgr.VMManager._instance = old_instance
            vm_mgr.VMManager._backend_type = old_type


if __name__ == "__main__":
    unittest.main()
