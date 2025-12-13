"""
Configuration manager: Read and parse configuration files
"""
import re
import os
import shutil
import tempfile
from pathlib import Path
import sys
import time
import platform
from typing import Optional

from .app_list import AppConfig, AppList
from .remote_device import RemoteDeviceInterface, VMInstanceRemoteDevice
from .vm_mgr import VMManager, VMNodeList


def get_temp_dir() -> Path:
    """Return a temporary directory path as Path."""
    return Path(tempfile.gettempdir())


class Workspace:
    _VARIABLE_PATTERN = re.compile(r'\{\{(\w+)\.(\w+)\}\}')
    def __init__(self, workspace_dir: Path,base_dir:Optional[Path] = None):
        vm_mgr = VMManager.get_instance()
        vm_mgr.set_template_base_dir(workspace_dir / "templates")
        self.workspace_dir: Path = workspace_dir
        self.base_dir: Path = base_dir
        if self.base_dir is None:
            self.base_dir = Path(current_dir).parent.parent

        print(f"base_dir: {self.base_dir}")

        self.nodes: VMNodeList= None
        self.remote_devices: dict [str, RemoteDeviceInterface]= None
        self.app_list : AppList= None

    def load(self):
        # Load configuration from workspace
        nodes_config_path = self.workspace_dir / "nodes.json"
        self.nodes = VMNodeList()
        self.nodes.load_from_file(nodes_config_path)

        app_dir = self.workspace_dir / "apps"
        self.app_list = AppList(app_dir)
        self.app_list.load_app_list()

        self._create_remote_devices_by_vm_instances()

    def build_env_params(self,parent_env_params: Optional[dict] = None) -> dict:
        env_params = {}
        if parent_env_params is not None:
            env_params.update(parent_env_params)
        # Get all environment variables
        system_env_params = os.environ.copy()
        system_env_params["base_dir"] = str(self.base_dir)
        env_params["system"] = system_env_params
        # Build env_params based on configuration in self.nodes
        for node_id in self.nodes.get_all_node_ids():
            device_info = self.remote_devices[node_id].get_device_info()
            env_params[node_id] = device_info

        return env_params


    def _create_remote_devices_by_vm_instances(self):
        self.remote_devices = {}
        for node_id in self.nodes.get_all_node_ids():
            remote_device = VMInstanceRemoteDevice(node_id)
            self.remote_devices[node_id] = remote_device
        
    
    def clean_vms(self):
        # Delete VMs based on nodes configuration in workspace
        vm_mgr = VMManager.get_instance()
        for node_id,node_config in self.nodes.nodes.items():
            vm_mgr.delete_vm(node_id)

    def create_vms(self):
        # Create VMs based on nodes configuration in workspace
        vm_mgr = VMManager.get_instance()
        for node_id,node_config in self.nodes.nodes.items():
            vm_mgr.create_vm(node_id, node_config)
        # After all VMs are created, call init_commands in order
        print(f"all nodes created, call instance_commands after 10 seconds...")
        time.sleep(10)
        env_params = self.build_env_params()
        print(f"env_params: {env_params}")
        instance_order = self.nodes.get_node_id_by_init_orders()

        for node_id in instance_order:
            node_config = self.nodes.get_node(node_id)
            if node_config is None:
                continue
            if node_config.instance_commands is None:
                continue
            for command in node_config.instance_commands:
                self.run(node_id, [command], env_params)

    def stop_vms(self):
        # Stop VMs based on nodes configuration in workspace
        vm_mgr = VMManager.get_instance()
        for node_id,node_config in self.nodes.nodes.items():
            vm_mgr.stop_vm(node_id)

    def start_vms(self):
        # Start VMs based on nodes configuration in workspace
        vm_mgr = VMManager.get_instance()
        for node_id,node_config in self.nodes.nodes.items():
            vm_mgr.start_vm(node_id)

    def snapshot(self, snapshot_name: str):
        # Create snapshots based on nodes configuration in workspace
        vm_mgr = VMManager.get_instance()
        for node_id,node_config in self.nodes.nodes.items():
            print(f"create snapshot {snapshot_name} for node: {node_id}")
            vm_mgr.snapshot(node_id, snapshot_name)
        

    def restore(self, snapshot_name: str):
        # Restore snapshots based on nodes configuration in workspace
        vm_mgr = VMManager.get_instance()
        for node_id,node_config in self.nodes.nodes.items():
            vm_mgr.restore(node_id, snapshot_name)

    def info_vms(self):
        # View VM status based on nodes configuration in workspace
        info = {}
        for node_id,node_config in self.nodes.nodes.items():
            vm_mgr = VMManager.get_instance()
            vm_status = {}
            vm_status["ip_v4"] = vm_mgr.get_vm_ip(node_id)
            info[node_id] = vm_status

        env_params = self.build_env_params()
        print(f"env_params: {env_params}")
        
        return info

    def install(self, device_id: str,app_list:list[str] = None):
        # Install apps to remote_device based on app_list configuration in workspace
        if app_list is None:
            app_list = self.app_list.get_all_app_names()
        print(f"install apps to device: {device_id} with apps: {app_list}")
        remote_device = self.remote_devices[device_id]
        if remote_device is None:
            raise ValueError(f"Remote device '{device_id}' not found")

        for app_name in app_list:
            if not self.nodes.have_app(device_id, app_name):
                print(f"App '{app_name}' not found in node: {device_id}, SKIP")
                continue

            app_config = self.app_list.get_app(app_name)
            if app_config is None:
                raise ValueError(f"App '{app_name}' not found")
            source_dir = app_config.get_dir("source")
            source_dir_path = Path(source_dir);
            if not source_dir_path.is_absolute():
                source_dir_path = self.base_dir / source_dir_path
            target_dir = app_config.get_dir("target")
            self.execute_app_command(device_id, app_name, "build_all",True)
            
            # Push files from Host Source directory to remote_device target directory based on directory settings
            remote_device.push(source_dir, target_dir)
            self.execute_app_command(device_id, app_name, "install")
        

    def update(self, device_id: str,app_list:list[str] = None):
        # Update apps on remote_device based on app_list configuration in workspace
        # 
        # First run build script on host
        # Then push files from Host source_bin directory to remote_device target_bin directory based on directory settings
        if app_list is None:
            app_list = self.app_list.get_all_app_names()

        remote_device = self.remote_devices[device_id]
        if remote_device is None:
            raise ValueError(f"Remote device '{device_id}' not found")

        for app_name in app_list:
            app_config = self.app_list.get_app(app_name)
            if app_config is None:
                raise ValueError(f"App '{app_name}' not found")
            source_bin_dir = app_config.get_dir("source_bin")
            if source_bin_dir is None:
                print(f"App '{app_name}' not found source_bin_dir, SKIP update")
                continue
            source_bin_dir_path = Path(source_bin_dir);
            if not source_bin_dir_path.is_absolute():
                source_bin_dir_path = self.base_dir / source_bin_dir_path
            target_bin_dir = app_config.get_dir("target_bin")
            self.execute_app_command(device_id, app_name, "build",True)
            
            # Push files from Host Source directory to remote_device target directory based on directory settings
            remote_device.push(source_bin_dir, target_bin_dir)
            self.execute_app_command(device_id, app_name, "update")

    def execute_app_command(self, device_id: Optional[str],app_name: str,cmd_name: str ,run_in_host: bool = False):
        # Execute action on remote_device based on app_list configuration in workspace, internally calls run
        vm_config = self.nodes.get_node(device_id)
        if vm_config is None:
            raise ValueError(f"Node '{device_id}' not found")
        app_param = self.nodes.get_app_params(device_id, app_name)
        if app_param is None:
            raise ValueError(f"App '{app_name}' not found")
        app_env_params = {
            app_name: app_param
        }
        env_params = self.build_env_params(app_env_params)
        app_config = self.app_list.get_app(app_name)
        if app_config is None:
            raise ValueError(f"App '{app_name}' not found")
        
        command_config = app_config.get_command(cmd_name)
        if command_config is None:
            raise ValueError(f"Command '{cmd_name}' not found")
        
        if run_in_host:
            self.run(None, command_config, env_params)
        else:
            self.run(device_id, command_config, env_params)

    def resolve_string(self, text: str,env_params: dict) -> str:
        """
        Resolve all variable references in string
        
        Args:
            text: String containing variable references
            env_params: Environment parameters
        
        Returns:
            str: Resolved string
        """
        def replace_var(match):
            obj_id = match.group(1)
            attr = match.group(2)
            sub_obj = env_params.get(obj_id)
            if sub_obj is None:
                raise ValueError(f"Object '{obj_id}' not found in env_params")
            value = sub_obj.get(attr)
            if value is None:
                raise ValueError(f"Attribute '{attr}' not found in object '{obj_id}'")
            return value
        
        return self._VARIABLE_PATTERN.sub(replace_var, text)

    def run(self, device_id: Optional[str], cmds: list[str], env_params: dict):
        remote_device = None
        if device_id is not None:
            remote_device = self.remote_devices[device_id]
            if remote_device is None:
                raise ValueError(f"Remote device '{device_id}' not found")
        else:
            device_id = "localhost"

        for command in cmds:
            new_command = self.resolve_string(command, env_params)
            print(f"run resolved command: [ {new_command} ] on {device_id}")
            if remote_device is None:
                os.system(new_command)
            else:
                remote_device.run_command(new_command)

    def state(self,device_id: str):
        # View app status on remote_devices based on app_list configuration in workspace (actually viewed by executing actions)
        pass

    def clog(self,target_dir: Optional[Path] = None):
        # Collect logs from remote_devices to local based on remote_devices configuration in workspace
        # Collect system log directories defined in nodes to local
        if target_dir is None:
            if platform.system() == "Windows":
                target_dir = get_temp_dir().joinpath("clogs")
            else:
                target_dir = Path("/tmp/clogs")
        
        #remove target dir
        if target_dir.exists():
            shutil.rmtree(target_dir)
            
        for node_id in self.nodes.get_all_node_ids():
            node_config = self.nodes.get_node(node_id)
            if node_config is None:
                continue
            logs_dir = node_config.get_dir("logs")
            if logs_dir is None:
                continue
            real_target_dir = target_dir.joinpath(node_id)
            real_target_dir.mkdir(parents=True, exist_ok=True)
            print(f"collect logs from {node_id}:{logs_dir} to {real_target_dir} ...")
            self.remote_devices[node_id].pull(logs_dir, real_target_dir, True)
            print(f"collect logs from {node_id}:{logs_dir} to {real_target_dir} done")
        




        