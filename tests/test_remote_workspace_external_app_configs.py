import json
import os
import tempfile
import unittest
from pathlib import Path

from src.remote.vm_mgr import VMNodeList
from src.remote.worksapce import Workspace


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_app_config(path: Path, name: str, directories: dict[str, str]) -> None:
    write_json(
        path,
        {
            "name": name,
            "version": "1.0.0",
            "commands": {
                "build_all": [],
                "install": [],
                "build": [],
                "update": [],
            },
            "directories": directories,
        },
    )


class FakeRemoteDevice:
    def __init__(self):
        self.pushes = []

    def push(self, local_path: str, remote_path: str, recursive: bool = False) -> None:
        self.pushes.append((local_path, remote_path, recursive))

    def get_device_info(self) -> dict:
        return {"device_id": "sn", "ip": "127.0.0.1"}


class RemoteWorkspaceExternalAppConfigTests(unittest.TestCase):
    def test_workspace_loads_external_app_config_and_preserves_instance_params(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            base_dir = root_dir / "buckyos" / "src"
            workspace_dir = base_dir / "dev_configs"
            external_path = (
                root_dir
                / "cyfs-gateway"
                / "src"
                / "dev_configs"
                / "apps"
                / "web3-gateway.json"
            )
            write_app_config(
                external_path,
                "web3-gateway",
                {"source": "gateway-rootfs", "target": "/opt/web3-gateway"},
            )
            write_json(
                workspace_dir / "sntest.json",
                {
                    "app_configs": {
                        "web3-gateway": os.path.relpath(external_path, base_dir)
                    },
                    "nodes": {
                        "sn": {
                            "apps": {
                                "web3-gateway": {
                                    "node_group_name": "sn_server",
                                }
                            }
                        }
                    },
                    "instance_order": ["sn"],
                },
            )

            workspace = Workspace("sntest", workspace_dir, base_dir)
            workspace.load()

            self.assertIn("web3-gateway", workspace.app_list.get_all_app_names())
            self.assertEqual(
                workspace.app_list.get_app("web3-gateway").get_dir("source"),
                "gateway-rootfs",
            )
            self.assertEqual(
                workspace.nodes.get_app_params("sn", "web3-gateway"),
                {"node_group_name": "sn_server"},
            )

    def test_vm_node_list_rejects_non_object_app_configs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "dev_configs" / "bad.json"
            write_json(
                config_path,
                {
                    "app_configs": ["demo"],
                    "nodes": {},
                },
            )

            with self.assertRaisesRegex(ValueError, "app_configs.*must be an object"):
                VMNodeList().load_from_file(config_path)

    def test_install_pushes_resolved_source_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "src"
            workspace_dir = base_dir / "dev_configs"
            write_json(
                workspace_dir / "devtest.json",
                {
                    "nodes": {"sn": {"apps": {"demo": {}}}},
                    "instance_order": ["sn"],
                },
            )
            write_app_config(
                workspace_dir / "apps" / "demo.json",
                "demo",
                {
                    "source": "rootfs/demo",
                    "target": "/opt/demo",
                    "source_bin": "rootfs/demo/bin",
                    "target_bin": "/opt/demo/bin",
                },
            )

            workspace = Workspace("devtest", workspace_dir, base_dir)
            workspace.load()
            fake_device = FakeRemoteDevice()
            workspace.remote_devices["sn"] = fake_device
            workspace.execute_app_command = lambda *args, **kwargs: None

            workspace.install("sn", ["demo"])

            self.assertEqual(
                fake_device.pushes,
                [(str(base_dir / "rootfs" / "demo"), "/opt/demo", False)],
            )

    def test_update_pushes_resolved_source_bin_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "src"
            workspace_dir = base_dir / "dev_configs"
            write_json(
                workspace_dir / "devtest.json",
                {
                    "nodes": {"sn": {"apps": {"demo": {}}}},
                    "instance_order": ["sn"],
                },
            )
            write_app_config(
                workspace_dir / "apps" / "demo.json",
                "demo",
                {
                    "source": "rootfs/demo",
                    "target": "/opt/demo",
                    "source_bin": "rootfs/demo/bin",
                    "target_bin": "/opt/demo/bin",
                },
            )

            workspace = Workspace("devtest", workspace_dir, base_dir)
            workspace.load()
            fake_device = FakeRemoteDevice()
            workspace.remote_devices["sn"] = fake_device
            workspace.execute_app_command = lambda *args, **kwargs: None

            workspace.update("sn", ["demo"])

            self.assertEqual(
                fake_device.pushes,
                [(str(base_dir / "rootfs" / "demo" / "bin"), "/opt/demo/bin", False)],
            )


if __name__ == "__main__":
    unittest.main()
