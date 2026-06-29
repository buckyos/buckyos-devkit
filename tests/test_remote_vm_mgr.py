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
            return_value=("__BUCKYOS_REMOTE_DIR_READY__\n", ""),
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
            return_value=("", "permission denied"),
        ), patch.object(backend, "push_file") as push_mock:
            result = backend.push_dir("sn", "/opt/web3-gateway", "/opt/web3-gateway")

        self.assertFalse(result)
        push_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
