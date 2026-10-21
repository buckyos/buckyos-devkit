import importlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

vm_mgr = importlib.import_module("src.remote.vm_mgr")


class MultipassPushDirTests(unittest.TestCase):
    def test_push_dir_prepares_root_owned_target_with_sudo(self):
        backend = vm_mgr.MultipassVMBackend()

        with patch.object(
            backend,
            "exec_command",
            return_value=("__BUCKYOS_REMOTE_DIR_READY__\n", "", 0),
        ) as exec_mock, patch.object(backend, "_pipe"):
            result = backend.push_dir("sn", "/opt/web3-gateway", "/opt/web3-gateway")

        self.assertTrue(result)
        command = exec_mock.call_args_list[0].args[1]
        self.assertIn("sudo mkdir -p /opt/web3-gateway", command)
        self.assertIn("sudo chown -R $(id -u):$(id -g) /opt/web3-gateway", command)
        self.assertIn("test -w /opt/web3-gateway", command)

    def test_push_dir_streams_tar_through_transfer_stdin(self):
        # The Linux snap of multipass cannot open host paths outside $HOME, and
        # `multipass exec` truncates large stdin streams.
        backend = vm_mgr.MultipassVMBackend()

        with patch.object(
            backend,
            "exec_command",
            return_value=("__BUCKYOS_REMOTE_DIR_READY__\n", "", 0),
        ) as exec_mock, patch.object(backend, "_pipe") as pipe_mock:
            result = backend.push_dir("sn", "/opt/buckyosvm/current", "/opt/buckyos")

        self.assertTrue(result)
        producer, consumer = pipe_mock.call_args.args
        self.assertEqual(producer, ["tar", "--no-xattrs", "-cf", "-", "."])
        self.assertEqual(pipe_mock.call_args.kwargs["producer_cwd"], "/opt/buckyosvm/current")
        self.assertEqual(consumer[:3], ["multipass", "transfer", "-"])
        archive = consumer[3].split(":", 1)[1]
        self.assertTrue(consumer[3].startswith("sn:/var/tmp/"))
        commands = [call.args[1] for call in exec_mock.call_args_list]
        self.assertIn(f"tar -C /opt/buckyos -xpf {archive}", commands)
        self.assertEqual(commands[-1], f"rm -f {archive}")

    def test_push_dir_removes_archive_when_extract_fails(self):
        backend = vm_mgr.MultipassVMBackend()
        results = [("__BUCKYOS_REMOTE_DIR_READY__\n", "", 0), ("", "tar: write error", 2), ("", "", 0)]

        with patch.object(backend, "exec_command", side_effect=results) as exec_mock, patch.object(
            backend, "_pipe"
        ):
            result = backend.push_dir("sn", "/opt/buckyosvm/current", "/opt/buckyos")

        self.assertFalse(result)
        self.assertTrue(exec_mock.call_args_list[-1].args[1].startswith("rm -f /var/tmp/"))

    def test_push_dir_stops_when_remote_target_is_not_writable(self):
        backend = vm_mgr.MultipassVMBackend()

        with patch.object(
            backend,
            "exec_command",
            return_value=("", "permission denied", 1),
        ), patch.object(backend, "_pipe") as pipe_mock:
            result = backend.push_dir("sn", "/opt/web3-gateway", "/opt/web3-gateway")

        self.assertFalse(result)
        pipe_mock.assert_not_called()

    def test_push_file_sends_content_through_transfer_stdin_and_keeps_mode(self):
        backend = vm_mgr.MultipassVMBackend()
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "web3_gateway"
            local.write_bytes(b"binary")
            local.chmod(0o755)
            with patch.object(
                backend, "exec_command", side_effect=[("/opt/web3-gateway/web3_gateway", "", 0), ("", "", 0)]
            ) as exec_mock, patch.object(
                vm_mgr.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")
            ) as run_mock:
                result = backend.push_file("sn", str(local), "/opt/web3-gateway/web3_gateway")

        self.assertTrue(result)
        target = run_mock.call_args.args[0][3]
        self.assertTrue(target.startswith("sn:/opt/web3-gateway/web3_gateway.devtest-"))
        tmp = target.split(":", 1)[1]
        self.assertEqual(
            exec_mock.call_args_list[-1].args[1],
            f"chmod 755 {tmp} && mv -f {tmp} /opt/web3-gateway/web3_gateway",
        )

    def test_pull_dir_extracts_archive_from_transfer_stdout(self):
        backend = vm_mgr.MultipassVMBackend()
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            backend, "exec_command", return_value=("", "", 0)
        ) as exec_mock, patch.object(backend, "_pipe") as pipe_mock:
            result = backend.pull_dir("sn", "/opt/buckyos/logs", tmp)

        self.assertTrue(result)
        self.assertIn("sudo tar -C /opt/buckyos/logs", exec_mock.call_args_list[0].args[1])
        producer, consumer = pipe_mock.call_args.args
        self.assertEqual(producer[:2], ["multipass", "transfer"])
        self.assertTrue(producer[2].startswith("sn:/var/tmp/"))
        self.assertEqual(producer[3], "-")
        self.assertEqual(consumer, ["tar", "-C", tmp, "--no-same-owner", "-xf", "-"])
        self.assertTrue(exec_mock.call_args_list[-1].args[1].startswith("sudo rm -f /var/tmp/"))


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
