import json
import os
import subprocess
import sys
from typing import Protocol, runtime_checkable, Tuple

from .vm_mgr import VMManager




@runtime_checkable
class RemoteDeviceInterface(Protocol):
    """
    Minimal remote device operations.
    Implementations can be SSH-based or VM-backend based.
    """

    def run_command(self, command: str) -> Tuple[str | None, str | None]:
        ...

    def push(self, local_path: str, remote_path: str, recursive: bool = False) -> None:
        ...

    def pull(self, remote_path: str, local_path: str, recursive: bool = False) -> None:
        ...

    def get_device_info(self) -> dict:
        ...


class RemoteDevice(RemoteDeviceInterface):
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.remote_port = 22
        self.remote_username = "root"
        
        config = self._load_config()
        if config is None:
            raise Exception("device config not found")
        self.remote_port = config.get('port', 22)
        self.remote_username = config.get('username', 'root')
        self.apps = config.get('apps', {})
        self.config = config

        device_info = self._load_device_info()
        if device_info is None:
            raise Exception("device info not found")
        self.remote_ip = device_info.get('ipv4', ['127.0.0.1'])[0]
        
        # Detect device type: if vm config exists, use vm_mgr; otherwise use SSH
        self.is_vm = 'vm' in config
        if self.is_vm:
            # Select backend type based on vm config, default is multipass
            vm_config = config.get('vm', {})
            backend_type = vm_config.get('backend', 'multipass')
            self.vm_manager = VMManager(backend_type=backend_type)
        else:
            self.vm_manager = None

    def has_app(self, app_name: str):
        return app_name in self.apps
    
    def get_app_config(self, app_name: str):
        return self.apps.get(app_name,)


    def _load_device_info(self):
        print(f"load device info from {VM_DEVICE_CONFIG}")
        try:
            with open(VM_DEVICE_CONFIG, 'r') as f:
                configs = json.load(f)
                return configs.get(self.device_id, {})
        except FileNotFoundError:
            print(f"{VM_DEVICE_CONFIG} not found")
            return None    
        
    def _load_config(self):
        # First try loading from new config system (nodes.json)
        try:
            import config_mgr
            config_manager = config_mgr.ConfigManager()
            node_config = config_manager.get_node(self.device_id)
            
            # Convert to old format for compatibility
            config = {
                'username': 'root',
                'port': 22,
                'zone_id': node_config.get('zone_id', ''),
                'node_id': node_config.get('node_id', self.device_id),
                'vm': {
                    'backend': 'multipass'
                },
                'apps': {}
            }
            
            # Convert apps list to dictionary format
            apps_list = node_config.get('apps', [])
            for app_name in apps_list:
                try:
                    app_config = config_manager.get_app(app_name)
                    config['apps'][app_name] = {
                        'start': app_config.get('commands', {}).get('start', ''),
                        'stop': app_config.get('commands', {}).get('stop', '')
                    }
                except ValueError:
                    pass
            
            return config
        except (ImportError, ValueError, FileNotFoundError):
            # If new config system is unavailable, fall back to old config
            pass
        
        # Fall back to old config system
        try:
            with open(ENV_CONFIG, 'r') as f:
                configs = json.load(f)
                return configs.get(self.device_id, {})
        except FileNotFoundError:
            print(f"{ENV_CONFIG} not found")
            return None
    
    def pull(self, remote_path, local_path, recursive=False):
        """
        Pull file or directory from remote device to local (generic interface)
        Automatically select vm_mgr or SSH based on device type
        
        Args:
            remote_path: Remote file or directory path
            local_path: Local target path
            recursive: Whether to recursively copy directories
        """
        if self.is_vm and self.vm_manager:
            # Use vm_mgr interface
            success = self.vm_manager.pull_file(self.device_id, remote_path, local_path, recursive)
            if not success:
                raise Exception(f"Failed to pull file from VM {self.device_id}")
        else:
            # Use SSH/SCP
            self._scp_pull(remote_path, local_path, recursive)
    
    def push(self, local_path, remote_path, recursive=False):
        """
        Push local file or directory to remote device (generic interface)
        Automatically select vm_mgr or SSH based on device type
        
        Args:
            local_path: Local file or directory path
            remote_path: Remote target path
            recursive: Whether to recursively copy directories
        """
        if self.is_vm and self.vm_manager:
            # Use vm_mgr interface
            success = self.vm_manager.push_file(self.device_id, local_path, remote_path, recursive)
            if not success:
                raise Exception(f"Failed to push file to VM {self.device_id}")
        else:
            # Use SSH/SCP
            self._scp_put(local_path, remote_path, recursive)
    
    def _scp_pull(self, remote_path, local_path, recursive=False):
        """
        Copy remote file or directory to local using scp (internal method)
        
        Args:
            remote_path: Remote file or directory path
            local_path: Local target path
            recursive: Whether to recursively copy directories
        """
        scp_command = [
            "scp",
            '-i', id_rsa_path,
        ]
        if recursive:
            scp_command.append("-r")
        
        scp_command.extend([
            f"{self.remote_username}@{self.remote_ip}:{remote_path}",
            local_path
        ])
        
        result = subprocess.run(scp_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"SCP failed: {result.stderr}")

    def _scp_put(self, local_path, remote_path, recursive=False):
        """
        Copy local file or directory to remote device using scp (internal method)
        
        Args:
            local_path: Local file or directory path
            remote_path: Remote target path
            recursive: Whether to recursively copy directories
        """
        scp_command = [
            "scp",
            '-i', id_rsa_path,
        ]
        if recursive:
            scp_command.append("-r")
        
        scp_command.extend([
            local_path,
            f"{self.remote_username}@{self.remote_ip}:{remote_path}"
        ])
        
        result = subprocess.run(scp_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"SCP failed: {result.stderr}")
    
    def scp_pull(self, remote_path, local_path, recursive=False):
        """
        [Deprecated] Copy remote file or directory to local using scp
        Please use pull() method instead
        
        Args:
            remote_path: Remote file or directory path
            local_path: Local target path
            recursive: Whether to recursively copy directories
        """
        import warnings
        warnings.warn("scp_pull() is deprecated, use pull() instead", DeprecationWarning, stacklevel=2)
        self.pull(remote_path, local_path, recursive)

    def scp_put(self, local_path, remote_path, recursive=False):
        """
        [Deprecated] Copy local file or directory to remote device using scp
        Please use push() method instead
        
        Args:
            local_path: Local file or directory path
            remote_path: Remote target path
            recursive: Whether to recursively copy directories
        """
        import warnings
        warnings.warn("scp_put() is deprecated, use push() instead", DeprecationWarning, stacklevel=2)
        self.push(local_path, remote_path, recursive)

    def run_command(self, command: str):
        """
        Execute command on remote device
        Automatically select vm_mgr or SSH based on device type
        """
        if self.is_vm and self.vm_manager:
            # Use vm_mgr interface
            print(f"run_command (VM): {command}")
            return self.vm_manager.exec_command(self.device_id, command)
        else:
            # Use SSH
            ssh_command = [
                'ssh',
                '-o', 'StrictHostKeyChecking=no',
                '-p', str(self.remote_port),
                '-i', id_rsa_path,
                f"{self.remote_username}@{self.remote_ip}",
                command
            ]
            print(f"run_command: {ssh_command}")
            
            try:
                result = subprocess.run(
                    ssh_command,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                return result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                return None, "Command execution timed out"
            except Exception as e:
                return None, str(e)

    def get_device_info(self):
        return {
            'device_id': self.device_id,
            'ip': self.remote_ip,
        }


class VMRemoteDevice(RemoteDeviceInterface):
    """
    RemoteDevice implementation backed by VMManager (VMInstance-like backend).
    Use this when you already know the VM name and want to operate via the
    VM backend instead of SSH.
    """

    def __init__(self, vm_name: str, backend_type: str = "multipass"):
        self.device_id = vm_name
        self.remote_username = "root"
        self.remote_port = 22
        # Via singleton manager, but still validate backend_type consistency
        self.vm_manager = VMManager(backend_type)


    def _resolve_ip(self) -> str:
        ips = self.vm_manager.get_vm_ip(self.device_id)
        for ip in ips:
            if ip.startswith("10.") or  ip.startswith("192."):
                return ip

        if ips.length > 0:
            return ips[0]



    def run_command(self, command: str):
        """Execute command inside the VM."""
        return self.vm_manager.exec_command(self.device_id, command)

    def push(self, local_path, remote_path, recursive: bool = False):
        """
        Push file or directory into the VM.
        Prefer push_dir/push_file based on local type; recursive parameter kept for backward compatibility only.
        """
        if os.path.isdir(local_path):
            success = self.vm_manager.push_dir(self.device_id, local_path, remote_path)
        else:
            success = self.vm_manager.push_file(
                self.device_id, local_path, remote_path, recursive
            )
        if not success:
            raise Exception(f"Failed to push {local_path} to VM {self.device_id}")

    def pull(self, remote_path, local_path, recursive: bool = False):
        """
        Pull file or directory from the VM.
        Select pull_dir/pull_file based on remote type; recursive parameter kept for backward compatibility only.
        """
        if self._remote_is_dir(remote_path):
            success = self.vm_manager.pull_dir(self.device_id, remote_path, local_path)
        else:
            success = self.vm_manager.pull_file(
                self.device_id, remote_path, local_path, recursive
            )
        if not success:
            raise Exception(f"Failed to pull {remote_path} from VM {self.device_id}")

    def get_device_info(self):
        """Return basic VM info."""
        return {
            'device_id': self.device_id,
            'ip': self._resolve_ip()
        }

    def _remote_is_dir(self, remote_path: str) -> bool:
        """Best-effort check if remote path is a directory."""
        cmd = f"if [ -d '{remote_path}' ]; then echo DIR; else echo FILE; fi"
        stdout, stderr = self.vm_manager.exec_command(self.device_id, cmd)
        if stdout and "DIR" in stdout:
            return True
        return False


# Backward compatibility alias
VMInstanceRemoteDevice = VMRemoteDevice
