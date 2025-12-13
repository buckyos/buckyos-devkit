"""
Virtual machine management layer abstraction
Supports multiple backend implementations (multipass, docker, kvm, etc.)
"""
from pathlib import Path
import subprocess
import abc
import os
import sys
import json
import re

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

class VMConfig:
    """Virtual machine configuration"""
    def __init__(self, node_id: str):
        self.node_id : str = node_id
        self.vm_template : str = None
        self.vm_params : dict = None
        self.network : dict = None
        # app_name -> app_instance params
        self.apps : dict [str,dict]= None
        self.init_commands : list[str] = None  # init_commands will execute immediately after VM creation
        self.instance_commands : list[str] = None  # instance_commands execute after all instances are created, in instance_order, so can reference created VM instance properties

    def get_dir(self, dir_name: str) -> str:
        return self.directories.get(dir_name, None)


class VMNodeList:
    def __init__(self):
        self.nodes : dict [str, VMConfig]= None
        self.instance_order : list[str] = None
    def get_node(self, node_id: str) -> VMConfig:
        return self.nodes.get(node_id)
    
    def get_all_node_ids(self) -> list[str]:
        return list(self.nodes.keys())

    def get_node_id_by_init_orders(self) -> list[str]:
        return self.instance_order

    def get_app_params(self, node_id: str, app_name: str) -> dict:
        node_config = self.get_node(node_id)
        if node_config is None:
            return None
        return node_config.apps.get(app_name, None)

    def have_app(self, node_id: str, app_name: str) -> bool:
        node_config = self.get_node(node_id)
        if node_config is None:
            return False
        return node_config.apps.get(app_name, None) is not None


    def load_from_file(self, file_path: Path):
        with open(file_path, "r") as f:
            data = json.load(f)

        self.nodes = {}
        self.instance_order = data.get("instance_order", [])

        for node_id, cfg in data.get("nodes", {}).items():
            vm_cfg = VMConfig(node_id=cfg.get("node_id", node_id))
            vm_cfg.vm_template = cfg.get("vm_template")
            vm_cfg.vm_params = cfg.get("vm_params", {})
            vm_cfg.network = cfg.get("network", {})
            vm_cfg.apps = cfg.get("apps", {})
            vm_cfg.init_commands = cfg.get("init_commands", [])
            vm_cfg.instance_commands = cfg.get("instance_commands", [])
            vm_cfg.directories = cfg.get("directories", {})
            self.nodes[node_id] = vm_cfg

        return self


class VMBackend(abc.ABC):
    """Virtual machine backend abstract base class"""
    
    @abc.abstractmethod
    def create_vm(self, vm_name: str, config: VMConfig) -> bool:
        """
        Create a virtual machine
        
        Args:
            vm_name: Virtual machine name
            config: VM configuration (cpu, memory, disk, etc.)
        
        Returns:
            bool: Whether creation was successful
        """
        pass
    
    @abc.abstractmethod
    def delete_vm(self, vm_name: str) -> bool:
        """
        Delete a virtual machine
        
        Args:
            vm_name: Virtual machine name
        
        Returns:
            bool: Whether deletion was successful
        """
        pass
    
    @abc.abstractmethod
    def exec_command(self, vm_name: str, command: str) -> tuple:
        """
        Execute command in virtual machine
        
        Args:
            vm_name: Virtual machine name
            command: Command to execute
        
        Returns:
            tuple: (stdout, stderr)
        """
        pass
    
    @abc.abstractmethod
    def push_file(self, vm_name: str, local_path: str, remote_path: str, recursive: bool = False) -> bool:
        """
        Push local file to virtual machine
        
        Args:
            vm_name: Virtual machine name
            local_path: Local file path
            remote_path: Remote file path
            recursive: Whether to recursively copy directories
        
        Returns:
            bool: Whether operation was successful
        """
        pass
    
    @abc.abstractmethod
    def pull_file(self, vm_name: str, remote_path: str, local_path: str, recursive: bool = False) -> bool:
        """
        Pull file from virtual machine to local
        
        Args:
            vm_name: Virtual machine name
            remote_path: Remote file path
            local_path: Local file path
            recursive: Whether to recursively copy directories
        
        Returns:
            bool: Whether operation was successful
        """
        pass

    @abc.abstractmethod
    def push_dir(self, vm_name: str, local_dir: str, remote_dir: str) -> bool:
        """
        Recursively push local directory to virtual machine directory
        """
        pass

    @abc.abstractmethod
    def pull_dir(self, vm_name: str, remote_dir: str, local_dir: str) -> bool:
        """
        Recursively pull virtual machine directory to local directory
        """
        pass
    
    @abc.abstractmethod
    def get_vm_ip(self, vm_name: str) -> list:
        """
        Get virtual machine IP address
        
        Args:
            vm_name: Virtual machine name
        
        Returns:
            list: IP address list
        """
        pass
    
    @abc.abstractmethod
    def is_vm_exists(self, vm_name: str) -> bool:
        """
        Check if virtual machine exists
        
        Args:
            vm_name: Virtual machine name
        
        Returns:
            bool: Whether it exists
        """
        pass

    @abc.abstractmethod
    def snapshot(self, node_id: str, snapshot_name: str) -> bool:
        """Create snapshot"""
        pass
    
    @abc.abstractmethod
    def restore(self, node_id: str, snapshot_name: str) -> bool:
        """Restore snapshot"""
        pass

    @abc.abstractmethod
    def stop_vm(self, node_id: str) -> bool:
        """Stop virtual machine"""
        pass
    
    @abc.abstractmethod
    def start_vm(self, node_id: str) -> bool:
        """Start virtual machine"""
        pass

    @abc.abstractmethod
    def set_template_base_dir(self, template_base_dir: Path) -> bool:
        """Set template base directory"""
        pass

class MultipassVMBackend(VMBackend):
    """Multipass virtual machine backend implementation"""
    
    def __init__(self):
        self.remote_username = "root"
        self.template_base_dir: Path = None
    
    def create_vm(self, vm_name: str, config: VMConfig) -> bool:
        """Create virtual machine using multipass"""
        cpu = config.vm_params.get('cpu', 1)
        memory = config.vm_params.get('memory', '1G')
        disk = config.vm_params.get('disk', '5G')
        template_name = config.vm_template
        
        cmd = f"multipass launch --name {vm_name} --cpus {cpu} --memory {memory} --disk {disk}"
        
        # Add cloud-init config if config_base is provided
        if template_name:
            init_yaml = os.path.join(self.template_base_dir, f'{template_name}.yaml')
            cmd += f" --cloud-init {init_yaml}"
        print(f"create vm {vm_name} with config {config}")
        print(cmd)
        try:
            result = subprocess.run(
                cmd, shell=True, check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )


            print(f"create vm {vm_name} success,will execute init commands...")    

            init_cmds = config.init_commands
            if init_cmds is not None:
                for cmd in init_cmds:
                    self.exec_command(vm_name, cmd)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to create VM {vm_name}: {e.stderr}")
            return False
    
    def delete_vm(self, vm_name: str) -> bool:
        """Delete virtual machine using multipass"""
        print(f"delete vm {vm_name} ...")
        try:
            result = subprocess.run(
                ["multipass", "delete", vm_name],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # Execute purge to completely delete
            subprocess.run(
                ["multipass", "purge"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"delete vm {vm_name} success")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to delete VM {vm_name}: {e.stderr}")
            return False
    
    def exec_command(self, vm_name: str, command: str) -> tuple:
        """Execute command using multipass exec"""
        print(f"exec [ {command} ] on vm {vm_name} ...")
        try:
            result = subprocess.run(
                ["multipass", "exec", vm_name, "--", "bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return None, "Command execution timed out"
        except Exception as e:
            return None, str(e)
    
    def push_file(self, vm_name: str, local_path: str, remote_path: str, recursive: bool = False) -> bool:
        """Push file using multipass transfer"""
        try:
            print(f"push file {local_path} to {vm_name}:{remote_path} ...")
            cmd = ["multipass", "transfer"]
            if recursive:
                cmd.append("-r")
            cmd.extend([local_path, f"{vm_name}:{remote_path}"])
            
            result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to push file to {vm_name}: {e.stderr}")
            return False
    
    def pull_file(self, vm_name: str, remote_path: str, local_path: str, recursive: bool = False) -> bool:
        """Pull file using multipass transfer"""
        try:
            print(f"pull file {vm_name}:{remote_path} to {local_path} ...")
            cmd = ["multipass", "transfer"]
            if recursive:
                cmd.append("-r")
            cmd.extend([f"{vm_name}:{remote_path}", local_path])
            
            result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to pull file from {vm_name}: {e.stderr}")
            return False
    
    def get_vm_ip(self, vm_name: str) -> list[str]:
        """Get virtual machine IP address"""
        try:
            result = subprocess.run(
                ["multipass", "info", vm_name],
                capture_output=True,
                text=True,
                check=True,
            )
            # Match IPv4 list, compatible with multi-line
            ip_pattern = r"IPv4:\s+((?:\d+\.\d+\.\d+\.\d+\s*)+)"
            match = re.search(ip_pattern, result.stdout)
            if match:
                ips = [ip.strip() for ip in match.group(1).split()]
                if ips:
                    return ips
            raise RuntimeError(f"No IPv4 address found for VM {vm_name}")
        except subprocess.CalledProcessError as e:
            print(f"Failed to get IP for VM {vm_name}: {e.stderr}")
            raise
        except Exception as e:
            print(f"Unknown error getting IP for VM {vm_name}: {e}")
            raise

    
    def is_vm_exists(self, vm_name: str) -> bool:
        """Check if virtual machine exists"""
        try:
            result = subprocess.run(
                ["multipass", "list"],
                capture_output=True,
                text=True,
                check=True
            )
            return vm_name in result.stdout
        except subprocess.CalledProcessError:
            return False

    def snapshot(self, node_id: str, snapshot_name: str) -> bool:
        """Create snapshot"""
        try:
            print(f"create snapshot {snapshot_name} on vm {node_id} ...")
            subprocess.run(
                ["multipass", "stop", node_id],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["multipass", "snapshot", node_id, "--name", snapshot_name],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["multipass", "start", node_id],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            print(f"create snapshot {snapshot_name} on vm {node_id} success")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to snapshot VM {node_id}: {e.stderr}")
            return False
    
    def restore(self, node_id: str, snapshot_name: str) -> bool:
        """Restore snapshot"""
        try:
            print(f"restore vm {node_id} to snapshot {snapshot_name} ...")
            subprocess.run(
                ["multipass", "stop", node_id],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                # multipass restore requires "<instance>.<snapshot>" as single parameter
                ["multipass", "restore", f"{node_id}.{snapshot_name}","-d"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["multipass", "start", node_id],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            print(f"restore vm {node_id} to snapshot  {snapshot_name} success")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to restore VM {node_id} snapshot {snapshot_name}: {e.stderr}")
            return False
    
    def stop_vm(self, node_id: str) -> bool:
        """Stop virtual machine"""
        try:
            print(f"stop vm {node_id} ...")
            subprocess.run(
                ["multipass", "stop", node_id],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            print(f"stop vm {node_id} success")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to stop VM {node_id}: {e.stderr}")
            return False
    
    def start_vm(self, node_id: str) -> bool:
        """Start virtual machine"""
        try:
            print(f"start vm {node_id} ...")
            subprocess.run(
                ["multipass", "start", node_id],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            print(f"start vm {node_id} success")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to start VM {node_id}: {e.stderr}")
            return False

    def set_template_base_dir(self, template_base_dir: Path) -> bool:
        """Set template base directory"""
        self.template_base_dir = template_base_dir
        return True
    
    def push_dir(self, vm_name: str, local_dir: str, remote_dir: str) -> bool:
        """Recursively push directory (multipass transfer -r)"""
        try:
            # Ensure remote target directory exists
            self.exec_command(vm_name, f"mkdir -p {remote_dir}")
            # Use "<local_dir>/." to only copy directory contents, avoiding extra top-level directory on remote
            src_dir = os.path.join(local_dir, ".")
            return self.push_file(vm_name, src_dir, remote_dir, recursive=True)
        except Exception as e:
            print(f"Failed to push dir to {vm_name}: {e}")
            return False

    def pull_dir(self, vm_name: str, remote_dir: str, local_dir: str) -> bool:
        """Recursively pull directory (multipass transfer -r)"""
        try:
            # Ensure local target directory exists
            os.makedirs(local_dir, exist_ok=True)
            return self.pull_file(vm_name, remote_dir, local_dir, recursive=True)
        except Exception as e:
            print(f"Failed to pull dir from {vm_name}: {e}")
            return False
    
class VMManager:
    """Virtual machine manager, selects backend based on configuration (singleton)"""

    _instance = None
    _backend_type = None

    def __new__(cls, backend_type: str = "multipass"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, backend_type: str = "multipass"):
        """
        Initialize VM manager (singleton), backend type determined on first creation
        
        Args:
            backend_type: Backend type, currently supports "multipass"
        """
        if getattr(self, "_initialized", False):
            # Subsequent initializations keep backend consistent
            if backend_type != self._backend_type:
                raise ValueError(
                    f"VMManager is singleton with backend '{self._backend_type}', "
                    f"got '{backend_type}'"
                )
            return

        if backend_type == "multipass":
            self.backend = MultipassVMBackend()
        else:
            raise ValueError(f"Unsupported backend type: {backend_type}")

        VMManager._backend_type = backend_type
        self._initialized = True

    @classmethod
    def get_instance(cls):
        """Get singleton instance"""
        return cls("multipass")

    @classmethod
    def get_backend_type(cls):
        """Get current singleton backend type"""
        return cls._backend_type or "multipass"

    def set_template_base_dir(self, template_base_dir: Path):
        """Set template base directory"""
        self.backend.set_template_base_dir(template_base_dir)
    
    def snapshot(self, node_id: str, snapshot_name: str) -> bool:
        """Create snapshot"""
        return self.backend.snapshot(node_id, snapshot_name)
    
    def restore(self, node_id: str, snapshot_name: str) -> bool:
        """Restore snapshot"""
        return self.backend.restore(node_id, snapshot_name)
    
    def create_vm(self, vm_name: str, config: VMConfig) -> bool:
        """Create virtual machine"""
        return self.backend.create_vm(vm_name, config)
    
    def delete_vm(self, vm_name: str) -> bool:
        """Delete virtual machine"""
        return self.backend.delete_vm(vm_name)
    def stop_vm(self, node_id: str) -> bool:
        """Stop virtual machine"""
        return self.backend.stop_vm(node_id)
    
    def start_vm(self, node_id: str) -> bool:
        """Start virtual machine"""
        return self.backend.start_vm(node_id)
    
    def exec_command(self, vm_name: str, command: str) -> tuple:
        """Execute command in virtual machine"""
        return self.backend.exec_command(vm_name, command)
    
    def push_file(self, vm_name: str, local_path: str, remote_path: str, recursive: bool = False) -> bool:
        """Push file to virtual machine"""
        return self.backend.push_file(vm_name, local_path, remote_path, recursive)
    
    def pull_file(self, vm_name: str, remote_path: str, local_path: str, recursive: bool = False) -> bool:
        """Pull file from virtual machine"""
        return self.backend.pull_file(vm_name, remote_path, local_path, recursive)

    def push_dir(self, vm_name: str, local_dir: str, remote_dir: str) -> bool:
        """Recursively push directory"""
        return self.backend.push_dir(vm_name, local_dir, remote_dir)

    def pull_dir(self, vm_name: str, remote_dir: str, local_dir: str) -> bool:
        """Recursively pull directory"""
        return self.backend.pull_dir(vm_name, remote_dir, local_dir)
    
    def get_vm_ip(self, vm_name: str) -> list:
        """Get virtual machine IP"""
        return self.backend.get_vm_ip(vm_name)
    
    def is_vm_exists(self, vm_name: str) -> bool:
        """Check if virtual machine exists"""
        return self.backend.is_vm_exists(vm_name)

