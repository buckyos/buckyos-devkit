import importlib
import json
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
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

    def test_host_vm_params_are_defaults_under_group_params(self):
        backend = self._backend()
        config = vm_mgr.VMConfig("sn")
        config.vm_params = {"disk": "8G", "storage": "group-store"}
        env = {"BUCKYOS_PVE_VM_PARAMS": '{"template_vmid": 9000, "storage": "local-lvm", "bridge": "vmbr1"}'}
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            if args[:3] == ["pvesh", "get", "/cluster/nextid"]:
                return vm_mgr.subprocess.CompletedProcess(args, 0, "120\n", "")
            return vm_mgr.subprocess.CompletedProcess(args, 0, "", "")

        with patch.dict(vm_mgr.os.environ, env), patch.object(backend, "is_vm_exists", return_value=False), \
                patch.object(backend, "_run", side_effect=run), patch.object(backend, "_apply_cloud_init"), \
                patch.object(backend, "_wait_for_agent"), patch.object(backend, "_exec_vmid", return_value=("", "", 0)):
            self.assertTrue(backend.create_vm("sn", config))

        clone = next(c for c in calls if c[:2] == ["qm", "clone"])
        self.assertEqual(clone[2], "9000")
        self.assertEqual(clone[clone.index("--storage") + 1], "group-store")
        set_cmd = next(c for c in calls if c[:2] == ["qm", "set"] and "--net0" in c)
        self.assertEqual(set_cmd[set_cmd.index("--net0") + 1], "virtio,bridge=vmbr1")
        self.assertIn(["qm", "disk", "resize", "120", "scsi0", "8G"], calls)

    def test_creation_waits_fifteen_minutes_by_default_and_accepts_override(self):
        backend = self._backend()
        for overrides, expected_timeout in [({}, 900), ({"agent_timeout": 45}, 45)]:
            with self.subTest(overrides=overrides):
                config = vm_mgr.VMConfig("sn")
                config.vm_params = {"template_vmid": 9000, **overrides}
                completed = subprocess.CompletedProcess([], 0, "120\n", "")
                with patch.dict(vm_mgr.os.environ, {"BUCKYOS_PVE_VM_PARAMS": "{}"}), \
                        patch.object(backend, "is_vm_exists", return_value=False), \
                        patch.object(backend, "_run", return_value=completed), \
                        patch.object(backend, "_apply_cloud_init"), \
                        patch.object(backend, "_wait_for_agent") as wait_mock, \
                        patch.object(backend, "_exec_vmid", return_value=("", "", 0)):
                    self.assertTrue(backend.create_vm("sn", config))
                wait_mock.assert_called_once_with(120, expected_timeout)

    def test_guest_agent_timeout_fails_creation_and_skips_init_commands(self):
        backend = self._backend()
        config = vm_mgr.VMConfig("sn")
        config.vm_params = {"template_vmid": 9000}
        config.init_commands = ["echo must-not-run"]
        completed = subprocess.CompletedProcess([], 0, "120\n", "")

        with patch.dict(vm_mgr.os.environ, {"BUCKYOS_PVE_VM_PARAMS": "{}"}), \
                patch.object(backend, "is_vm_exists", return_value=False), \
                patch.object(backend, "_run", return_value=completed) as run_mock, \
                patch.object(backend, "_apply_cloud_init"), \
                patch.object(backend, "_wait_for_agent", side_effect=TimeoutError("agent unavailable")), \
                patch.object(backend, "_exec_vmid") as guest_mock, \
                patch.object(backend, "exec_command") as init_mock:
            self.assertFalse(backend.create_vm("sn", config))

        guest_mock.assert_not_called()
        init_mock.assert_not_called()
        self.assertIn(["qm", "stop", "120"], [call.args[0] for call in run_mock.call_args_list])
        self.assertIn(["qm", "destroy", "120", "--purge", "1", "--destroy-unreferenced-disks", "1"],
                      [call.args[0] for call in run_mock.call_args_list])

    def test_cleanup_timeout_does_not_hide_creation_failure(self):
        backend = self._backend()
        config = vm_mgr.VMConfig("sn")
        config.vm_params = {"template_vmid": 9000}

        def run(args, **kwargs):
            if args[:2] == ["qm", "stop"]:
                raise subprocess.TimeoutExpired(args, 300)
            return subprocess.CompletedProcess(args, 0, "120\n", "")

        with patch.dict(vm_mgr.os.environ, {"BUCKYOS_PVE_VM_PARAMS": "{}"}), \
                patch.object(backend, "is_vm_exists", return_value=False), \
                patch.object(backend, "_run", side_effect=run), \
                patch.object(backend, "_apply_cloud_init"), \
                patch.object(backend, "_wait_for_agent", side_effect=TimeoutError("agent unavailable")):
            self.assertFalse(backend.create_vm("sn", config))

    def test_agent_upload_streams_one_mib_chunks(self):
        backend = self._backend()
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "archive"
            local.write_bytes(b"x" * (2 * 1024 * 1024 + 5))
            with patch.object(backend, "_exec_vmid", return_value=("", "", 0)) as exec_mock:
                backend._upload_agent(102, str(local), "/var/tmp/a.tar.gz")

        chunks = [call.kwargs["input_data"] for call in exec_mock.call_args_list if "input_data" in call.kwargs]
        self.assertEqual([len(c) for c in chunks], [1024 * 1024, 1024 * 1024, 5])
        self.assertEqual(exec_mock.call_args_list[0].args[1], ": > /var/tmp/a.tar.gz")

    def test_upload_falls_back_to_agent_and_renames_over_target(self):
        backend = self._backend()
        with patch.object(backend, "_upload_http", return_value=False), patch.object(
            backend, "_upload_agent"
        ) as agent_mock, patch.object(backend, "_exec_vmid", return_value=("", "", 0)) as exec_mock:
            backend._upload(102, "/local/web3_gateway", "/opt/web3-gateway/web3_gateway")

        tmp = agent_mock.call_args.args[2]
        self.assertTrue(tmp.startswith("/opt/web3-gateway/web3_gateway.devtest-"))
        self.assertEqual(exec_mock.call_args.args[1], f"mv -f {tmp} /opt/web3-gateway/web3_gateway")

    def test_host_address_skips_addresses_local_to_this_host(self):
        backend = self._backend()
        routes = {
            "172.17.0.1": "local 172.17.0.1 dev lo table local src 172.17.0.1 uid 0\n",
            "192.168.1.118": "192.168.1.118 dev vmbr0 src 192.168.1.165 uid 0\n",
        }

        def run(args, **kwargs):
            return vm_mgr.subprocess.CompletedProcess(args, 0, routes[args[-1]], "")

        with patch.object(backend, "_vm_ipv4", return_value=["172.17.0.1", "192.168.1.118"]), patch.object(
            backend, "_run", side_effect=run
        ):
            self.assertEqual(backend._host_address_for(102), "192.168.1.165")

    def test_one_file_http_endpoint_serves_and_receives_by_token_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file"
            path.write_bytes(b"payload")
            with vm_mgr._one_file_http_endpoint("127.0.0.1", str(path)) as url:
                with urllib.request.urlopen(url) as response:
                    self.assertEqual(response.read(), b"payload")
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(url.rsplit("/", 1)[0] + "/other")
                request = urllib.request.Request(url, data=b"uploaded", method="PUT")
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.status, 200)
            self.assertEqual(path.read_bytes(), b"uploaded")

    def test_guest_exec_passes_stdin_as_bytes(self):
        backend = self._backend()
        completed = vm_mgr.subprocess.CompletedProcess([], 0, b'{"exitcode":0}', b"")
        with patch.object(backend, "_run", return_value=completed) as run_mock:
            self.assertEqual(backend._exec_vmid(102, "cat >> /f", input_data=b"abc"), ("", "", 0))

        args = run_mock.call_args.args[0]
        self.assertIn("--pass-stdin", args)
        self.assertEqual(run_mock.call_args.kwargs["input_data"], b"abc")
        self.assertFalse(run_mock.call_args.kwargs["text"])

    def test_delete_vm_removes_its_cloud_init_snippet(self):
        backend = self._backend()
        with tempfile.TemporaryDirectory() as tmp:
            snippet = Path(tmp) / "buckyos-107-ubuntu_sn.yaml"
            snippet.write_text("#cloud-config\n")
            outputs = {
                "config": "cicustom: user=local:snippets/buckyos-107-ubuntu_sn.yaml\nname: sn\n",
                "path": f"{snippet}\n",
            }

            def run(args, **kwargs):
                key = "config" if args[:2] == ["qm", "config"] else "path" if args[:2] == ["pvesm", "path"] else None
                return vm_mgr.subprocess.CompletedProcess(args, 0, outputs.get(key, ""), "")

            with patch.object(backend, "_vmid", return_value=107), patch.object(backend, "_run", side_effect=run):
                self.assertTrue(backend.delete_vm("sn"))
            self.assertFalse(snippet.exists())

    def test_guest_exec_restores_utf8_output_and_encodes_non_ascii_commands(self):
        backend = self._backend()
        latin1_view = "\u2192 \u4e2d".encode("utf-8").decode("latin-1")
        completed = vm_mgr.subprocess.CompletedProcess(
            [], 0, json.dumps({"exitcode": 0, "out-data": latin1_view}), ""
        )
        with patch.object(backend, "_run", return_value=completed) as run_mock:
            out, _, _ = backend._exec_vmid(102, "echo '\u2192 \u4e2d'")

        self.assertEqual(out, "\u2192 \u4e2d")
        command = run_mock.call_args.args[0][-1]
        self.assertTrue(command.isascii())
        self.assertIn("base64 -d", command)

    def test_restore_waits_until_guest_is_reachable(self):
        backend = self._backend()
        with patch.object(backend, "_vmid", return_value=108), patch.object(backend, "_run"), patch.object(
            backend, "_wait_for_agent"
        ) as agent_mock, patch.object(
            backend, "_host_address_for", side_effect=[None, "192.168.1.165"]
        ) as host_mock, patch.object(vm_mgr.time, "sleep"):
            self.assertTrue(backend.restore("alice-ood1", "installed"))

        agent_mock.assert_called_once()
        self.assertEqual(host_mock.call_count, 2)

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
