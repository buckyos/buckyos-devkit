"""
Virtual machine management layer abstraction
Supports multiple backend implementations (multipass, docker, kvm, etc.)
"""
from pathlib import Path
import subprocess
import abc
import os
import shlex
import sys
import json
import re
import base64
import tempfile
import time

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
        self.app_configs : dict[str, str] = {}
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
        self.app_configs = data.get("app_configs", {})
        if not isinstance(self.app_configs, dict):
            raise ValueError(f"'app_configs' in {file_path} must be an object")
        for app_name, config_path in self.app_configs.items():
            if not isinstance(app_name, str) or not isinstance(config_path, str):
                raise ValueError(
                    f"'app_configs' in {file_path} must map app names to config path strings"
                )
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
            tuple: (stdout, stderr, returncode); returncode is None when the
            command could not be executed at all (timeout, backend error)
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
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return None, "Command execution timed out", None
        except Exception as e:
            return None, str(e), None
    
    # Host files go through `multipass transfer` stdin/stdout ("-") rather than host paths:
    # the Linux snap build of multipass can only open host files under $HOME, so staging
    # roots such as /opt/buckyosvm or /tmp/buckyos-vmtest are invisible to it. Large
    # streams must not be piped into `multipass exec` stdin, which truncates them (~2MB).

    def _pipe(self, producer: list[str], consumer: list[str], producer_cwd: str | None = None) -> None:
        env = os.environ.copy()
        env["COPYFILE_DISABLE"] = "1"  # keep macOS tar from emitting ._ AppleDouble files
        with tempfile.TemporaryFile() as prod_stderr:
            prod = subprocess.Popen(producer, cwd=producer_cwd, stdout=subprocess.PIPE, stderr=prod_stderr, env=env)
            cons = subprocess.Popen(consumer, stdin=prod.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            prod.stdout.close()
            _, cons_err = cons.communicate()
            prod.wait()
            prod_stderr.seek(0)
            prod_err = prod_stderr.read()
        if prod.returncode != 0 or cons.returncode != 0:
            message = (prod_err + cons_err).decode(errors="replace").strip()
            raise RuntimeError(message or f"exit codes {prod.returncode}/{cons.returncode}")

    def _exec_checked(self, vm_name: str, script: str) -> str:
        stdout, stderr, code = self.exec_command(vm_name, script)
        if code != 0:
            raise RuntimeError((stderr or stdout or f"exit code {code}").strip())
        return stdout

    def push_file(self, vm_name: str, local_path: str, remote_path: str, recursive: bool = False) -> bool:
        """Push a file into the VM; directories are delegated to push_dir"""
        if os.path.isdir(local_path):
            return self.push_dir(vm_name, local_path, remote_path)
        try:
            print(f"push file {local_path} to {vm_name}:{remote_path} ...")
            dst = self._exec_checked(
                vm_name,
                f"dst={shlex.quote(remote_path)}; "
                f"if [ -d \"$dst\" ]; then dst=\"$dst\"/{shlex.quote(os.path.basename(local_path))}; fi; "
                f"printf '%s' \"$dst\"",
            )
            # Write a sibling temp file and rename it over dst, so a running
            # executable can be replaced (writing it in place fails with ETXTBSY).
            tmp = f"{dst}.devtest-{os.getpid()}"
            mode = format(os.stat(local_path).st_mode & 0o7777, "o")
            try:
                with open(local_path, "rb") as f:
                    result = subprocess.run(
                        ["multipass", "transfer", "-", f"{vm_name}:{tmp}"],
                        stdin=f,
                        capture_output=True,
                    )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.decode(errors="replace").strip())
                self._exec_checked(
                    vm_name, f"chmod {mode} {shlex.quote(tmp)} && mv -f {shlex.quote(tmp)} {shlex.quote(dst)}"
                )
            except RuntimeError:
                self.exec_command(vm_name, f"rm -f {shlex.quote(tmp)}")
                raise
            return True
        except (OSError, RuntimeError) as e:
            print(f"Failed to push file to {vm_name}: {e}")
            return False

    def pull_file(self, vm_name: str, remote_path: str, local_path: str, recursive: bool = False) -> bool:
        """Pull a file from the VM"""
        try:
            print(f"pull file {vm_name}:{remote_path} to {local_path} ...")
            if os.path.isdir(local_path):
                local_path = os.path.join(local_path, os.path.basename(remote_path))
            with open(local_path, "wb") as f:
                result = subprocess.run(
                    ["multipass", "transfer", f"{vm_name}:{remote_path}", "-"],
                    stdout=f,
                    stderr=subprocess.PIPE,
                )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors="replace").strip())
            return True
        except (OSError, RuntimeError) as e:
            print(f"Failed to pull file from {vm_name}: {e}")
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
        """Recursively push directory (tar archive through multipass transfer stdin)"""
        try:
            quoted_remote_dir = shlex.quote(remote_dir)
            ready_marker = "__BUCKYOS_REMOTE_DIR_READY__"
            stdout, stderr, _ = self.exec_command(
                vm_name,
                (
                    f"sudo mkdir -p {quoted_remote_dir} && "
                    f"sudo chown -R $(id -u):$(id -g) {quoted_remote_dir} && "
                    f"test -d {quoted_remote_dir} && "
                    f"test -w {quoted_remote_dir} && "
                    f"echo {ready_marker}"
                ),
            )
            if stdout is None or ready_marker not in stdout:
                if stderr:
                    print(f"Failed to prepare remote directory {vm_name}:{remote_dir}: {stderr}")
                return False
            print(f"push dir {local_dir} to {vm_name}:{remote_dir} ...")
            # /var/tmp: recent Ubuntu images mount /tmp as a small tmpfs
            archive = f"/var/tmp/buckyos-push-{os.getpid()}.tar"
            try:
                self._pipe(
                    ["tar", "--no-xattrs", "-cf", "-", "."],
                    ["multipass", "transfer", "-", f"{vm_name}:{archive}"],
                    producer_cwd=local_dir,
                )
                self._exec_checked(vm_name, f"tar -C {quoted_remote_dir} -xpf {archive}")
            finally:
                self.exec_command(vm_name, f"rm -f {archive}")
            return True
        except Exception as e:
            print(f"Failed to push dir to {vm_name}: {e}")
            return False

    def pull_dir(self, vm_name: str, remote_dir: str, local_dir: str) -> bool:
        """Recursively pull directory (tar archive through multipass transfer stdout)"""
        try:
            print(f"pull dir {vm_name}:{remote_dir} to {local_dir} ...")
            os.makedirs(local_dir, exist_ok=True)
            archive = f"/var/tmp/buckyos-pull-{os.getpid()}.tar"
            # tar exits 1 when a file (e.g. a live log) changes while it is read
            self._exec_checked(
                vm_name,
                f"sudo tar -C {shlex.quote(remote_dir)} --warning=no-file-changed -cf {archive} .; "
                f"rc=$?; sudo chmod 644 {archive}; [ $rc -le 1 ]",
            )
            try:
                self._pipe(
                    ["multipass", "transfer", f"{vm_name}:{archive}", "-"],
                    ["tar", "-C", local_dir, "--no-same-owner", "-xf", "-"],
                )
            finally:
                self.exec_command(vm_name, f"sudo rm -f {archive}")
            return True
        except Exception as e:
            print(f"Failed to pull dir from {vm_name}: {e}")
            return False


class PVEVMBackend(VMBackend):
    """Proxmox VE backend using ``qm`` and the QEMU guest agent.

    ``vm_params`` accepts the common ``cpu``, ``memory`` and ``disk`` keys plus:
    ``template_vmid`` (recommended) or ``image``, ``storage`` (local-lvm),
    ``bridge`` (vmbr0), ``ciuser`` (root), ``sshkeys``, ``ipconfig0`` (ip=dhcp),
    and ``snippet_storage`` for custom ``vm_template`` cloud-init YAML.
    The guest image/template must have qemu-guest-agent installed and enabled.
    """

    def __init__(self):
        self.remote_username = "root"
        self.template_base_dir: Path = None
        self.node = self._detect_node()

    @staticmethod
    def _run(args, *, check=True, input_data=None, timeout=300):
        return subprocess.run(
            args, input=input_data, capture_output=True, text=True,
            check=check, timeout=timeout,
        )

    def _detect_node(self) -> str:
        try:
            result = self._run(["pvesh", "get", "/nodes", "--output-format", "json"])
            nodes = json.loads(result.stdout)
            online = [n["node"] for n in nodes if n.get("status") == "online"]
            if online:
                return online[0]
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            pass
        return os.uname().nodename.split(".")[0]

    def _resources(self) -> list[dict]:
        result = self._run([
            "pvesh", "get", "/cluster/resources", "--type", "vm",
            "--output-format", "json",
        ])
        return json.loads(result.stdout)

    def _vmid(self, vm_name: str) -> int:
        matches = [r for r in self._resources()
                   if r.get("type") == "qemu" and r.get("name") == vm_name]
        if not matches:
            raise ValueError(f"PVE VM not found: {vm_name}")
        if len(matches) > 1:
            raise ValueError(f"Multiple PVE VMs named {vm_name}; names must be unique")
        return int(matches[0]["vmid"])

    @staticmethod
    def _memory_mb(value) -> int:
        if isinstance(value, (int, float)):
            return int(value)
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGT]?)B?\s*", str(value), re.I)
        if not match:
            raise ValueError(f"Invalid memory value: {value}")
        number, unit = float(match.group(1)), match.group(2).upper()
        return max(1, int(number * {"": 1, "K": 1 / 1024, "M": 1, "G": 1024, "T": 1048576}[unit]))

    def create_vm(self, vm_name: str, config: VMConfig) -> bool:
        params = config.vm_params or {}
        vmid = None
        try:
            if self.is_vm_exists(vm_name):
                print(f"PVE VM {vm_name} already exists")
                return False
            vmid = int(self._run(["pvesh", "get", "/cluster/nextid"]).stdout.strip())
            template_vmid = params.get("template_vmid")
            storage = params.get("storage", "local-lvm")
            if template_vmid is not None:
                clone_cmd = ["qm", "clone", str(template_vmid), str(vmid),
                             "--name", vm_name, "--full", "1"]
                if storage:
                    clone_cmd += ["--storage", str(storage)]
                self._run(clone_cmd)
            else:
                image = params.get("image")
                if not image or not os.path.isfile(os.path.expanduser(str(image))):
                    raise ValueError("PVE creation requires vm_params.template_vmid or an existing vm_params.image")
                image = os.path.abspath(os.path.expanduser(str(image)))
                self._run(["qm", "create", str(vmid), "--name", vm_name,
                           "--ostype", "l26", "--scsihw", "virtio-scsi-pci"])
                self._run(["qm", "disk", "import", str(vmid), image, str(storage)])
                # The imported disk is recorded as unused0.
                cfg = self._run(["qm", "config", str(vmid)]).stdout
                unused = re.search(r"^unused\d+:\s*(\S+)", cfg, re.M)
                if not unused:
                    raise RuntimeError("PVE did not expose the imported disk")
                self._run(["qm", "set", str(vmid), "--scsi0", unused.group(1)])

            set_cmd = ["qm", "set", str(vmid),
                       "--cores", str(params.get("cpu", 1)),
                       "--memory", str(self._memory_mb(params.get("memory", "1G"))),
                       "--agent", "enabled=1", "--serial0", "socket",
                       "--vga", "serial0", "--boot", "order=scsi0",
                       "--net0", f"virtio,bridge={params.get('bridge', 'vmbr0')}",
                       "--ide2", f"{storage}:cloudinit",
                       "--ciuser", str(params.get("ciuser", "root")),
                       "--ipconfig0", str(params.get("ipconfig0", "ip=dhcp"))]
            if params.get("sshkeys"):
                set_cmd += ["--sshkeys", os.path.expanduser(str(params["sshkeys"]))]
            self._run(set_cmd)
            self._apply_cloud_init(
                vmid,
                config.vm_template,
                params.get("snippet_storage"),
                ensure_agent=template_vmid is None,
            )
            if params.get("disk"):
                self._run(["qm", "disk", "resize", str(vmid), "scsi0", str(params["disk"])])
            self._run(["qm", "start", str(vmid)])
            self._wait_for_agent(vmid, int(params.get("agent_timeout", 180)))
            stdout, stderr, code = self._exec_vmid(
                vmid, "cloud-init status --wait",
                timeout=int(params.get("cloud_init_timeout", 600)),
            )
            if code != 0:
                raise RuntimeError(f"cloud-init failed ({code}): {stderr or stdout}")
            for command in config.init_commands or []:
                stdout, stderr, code = self.exec_command(vm_name, command)
                if code != 0:
                    raise RuntimeError(f"init command failed ({code}): {stderr or stdout}")
            return True
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as e:
            print(f"Failed to create PVE VM {vm_name}: {e}")
            if vmid is not None:
                try:
                    self._run(["qm", "stop", str(vmid)], check=False)
                    self._run(["qm", "destroy", str(vmid), "--purge", "1",
                               "--destroy-unreferenced-disks", "1"], check=False)
                except OSError as cleanup_error:
                    print(f"Failed to clean up PVE VM {vmid}: {cleanup_error}")
            return False

    def _apply_cloud_init(self, vmid: int, template_name: str | None,
                          requested_storage: str | None,
                          ensure_agent: bool = False):
        if not template_name and not ensure_agent:
            return
        source = None
        if template_name:
            if self.template_base_dir is None:
                raise ValueError("template_base_dir must be set when vm_template is used")
            source = Path(self.template_base_dir) / f"{template_name}.yaml"
            if not source.is_file():
                raise ValueError(f"cloud-init template not found: {source}")
        result = self._run(["pvesh", "get", "/storage", "--output-format", "json"])
        stores = json.loads(result.stdout)
        candidates = [s for s in stores if "snippets" in str(s.get("content", "")).split(",")]
        if requested_storage:
            candidates = [s for s in candidates if s.get("storage") == requested_storage]
        if not candidates:
            hint = f" '{requested_storage}'" if requested_storage else ""
            raise ValueError(
                f"vm_template requires a PVE storage{hint} with snippets content enabled"
            )
        snippet_storage = candidates[0]["storage"]
        storage_path = candidates[0].get("path")
        if not storage_path:
            raise ValueError(f"snippet storage {snippet_storage} is not directory-backed")
        target_dir = Path(storage_path) / "snippets"
        target_dir.mkdir(parents=True, exist_ok=True)
        config_name = template_name or "pve-agent"
        target = target_dir / f"buckyos-{vmid}-{config_name}.yaml"
        cloud_config = source.read_text() if source else "#cloud-config\n"
        cloud_config = self._prepare_cloud_config(cloud_config, ensure_agent)
        target.write_text(cloud_config)
        self._run(["qm", "set", str(vmid), "--cicustom",
                   f"user={snippet_storage}:snippets/{target.name}"])

    @staticmethod
    def _prepare_cloud_config(cloud_config: str, ensure_agent: bool) -> str:
        """Normalize Multipass user-data and inject PVE's guest dependency."""
        if not cloud_config.lstrip().startswith("#cloud-config"):
            cloud_config = "#cloud-config\n" + cloud_config
        if not ensure_agent or re.search(r"\bqemu-guest-agent\b", cloud_config):
            return cloud_config

        # Preserve the template's package list. Cloud-init accepts both block and
        # flow-style YAML lists, which cover the formats used by Multipass files.
        block = re.search(r"(?m)^(packages\s*:\s*(?:#.*)?\n)", cloud_config)
        if block:
            return cloud_config[:block.end()] + "- qemu-guest-agent\n" + cloud_config[block.end():]
        flow = re.search(r"(?m)^(packages\s*:\s*)\[([^\n]*)\](\s*(?:#.*)?)$", cloud_config)
        if flow:
            existing = flow.group(2).strip()
            packages = "qemu-guest-agent" + (f", {existing}" if existing else "")
            return cloud_config[:flow.start()] + flow.group(1) + f"[{packages}]" + flow.group(3) + cloud_config[flow.end():]
        scalar = re.search(r"(?m)^packages\s*:\s*\S+", cloud_config)
        if scalar:
            raise ValueError("cloud-init 'packages' must be a YAML list")
        separator = "" if cloud_config.endswith("\n") else "\n"
        return cloud_config + separator + "packages:\n- qemu-guest-agent\n"

    def _wait_for_agent(self, vmid: int, timeout: int):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self._run(["qm", "guest", "cmd", str(vmid), "ping"], check=False)
            if result.returncode == 0:
                return
            time.sleep(2)
        raise TimeoutError(f"QEMU guest agent did not become ready for VM {vmid}")

    def delete_vm(self, vm_name: str) -> bool:
        try:
            vmid = self._vmid(vm_name)
            self._run(["qm", "stop", str(vmid)], check=False)
            self._run(["qm", "destroy", str(vmid), "--purge", "1", "--destroy-unreferenced-disks", "1"])
            return True
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print(f"Failed to delete PVE VM {vm_name}: {e}")
            return False

    def exec_command(self, vm_name: str, command: str) -> tuple:
        try:
            return self._exec_vmid(self._vmid(vm_name), command)
        except (OSError, ValueError) as e:
            return None, str(e), None

    def _exec_vmid(self, vmid: int, command: str, timeout: int = 300) -> tuple:
        try:
            result = self._run(["qm", "guest", "exec", str(vmid),
                                "--timeout", str(timeout), "--", "bash", "-c", command],
                               check=False, timeout=timeout + 10)
            if result.returncode != 0:
                return result.stdout, result.stderr, result.returncode
            data = json.loads(result.stdout)
            return data.get("out-data", ""), data.get("err-data", ""), data.get("exitcode", 0)
        except subprocess.TimeoutExpired:
            return None, "Command execution timed out", None
        except (OSError, ValueError, json.JSONDecodeError) as e:
            return None, str(e), None

    def _file_write(self, vmid: int, remote_path: str, data: bytes):
        # Keep request arguments below Linux's argv limit, then append in-guest.
        chunk_path = f"/tmp/buckyos-qga-{os.getpid()}"
        _, stderr, code = self._exec_vmid(vmid, f": > {shlex.quote(remote_path)}")
        if code != 0:
            raise RuntimeError(stderr or f"cannot create {remote_path}")
        try:
            for offset in range(0, len(data), 48 * 1024):
                encoded = base64.b64encode(data[offset:offset + 48 * 1024]).decode("ascii")
                self._run(["pvesh", "create", f"/nodes/{self.node}/qemu/{vmid}/agent/file-write",
                           "--file", chunk_path, "--content", encoded, "--encode", "0"])
                _, stderr, code = self._exec_vmid(
                    vmid, f"cat {shlex.quote(chunk_path)} >> {shlex.quote(remote_path)}")
                if code != 0:
                    raise RuntimeError(stderr or f"cannot append to {remote_path}")
        finally:
            self._exec_vmid(vmid, f"rm -f {shlex.quote(chunk_path)}")

    def _file_read(self, vmid: int, remote_path: str) -> bytes:
        chunks = []
        offset = 0
        count = 64 * 1024
        while True:
            result = self._run(["pvesh", "get", f"/nodes/{self.node}/qemu/{vmid}/agent/file-read",
                                "--file", remote_path, "--offset", str(offset),
                                "--count", str(count), "--decode", "0",
                                "--output-format", "json"])
            data = json.loads(result.stdout)
            content = data.get("content", "") if isinstance(data, dict) else data
            chunk = base64.b64decode(content)
            chunks.append(chunk)
            offset += len(chunk)
            if len(chunk) < count or (isinstance(data, dict) and data.get("eof")):
                break
        return b"".join(chunks)

    def push_file(self, vm_name: str, local_path: str, remote_path: str, recursive: bool = False) -> bool:
        if recursive or os.path.isdir(local_path):
            return self.push_dir(vm_name, local_path, remote_path)
        try:
            with open(local_path, "rb") as f:
                self._file_write(self._vmid(vm_name), remote_path, f.read())
            return True
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as e:
            print(f"Failed to push file to PVE VM {vm_name}: {e}")
            return False

    def pull_file(self, vm_name: str, remote_path: str, local_path: str, recursive: bool = False) -> bool:
        if recursive:
            return self.pull_dir(vm_name, remote_path, local_path)
        try:
            data = self._file_read(self._vmid(vm_name), remote_path)
            with open(local_path, "wb") as f:
                f.write(data)
            return True
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as e:
            print(f"Failed to pull file from PVE VM {vm_name}: {e}")
            return False

    def push_dir(self, vm_name: str, local_dir: str, remote_dir: str) -> bool:
        try:
            vmid = self._vmid(vm_name)
            with tempfile.NamedTemporaryFile(suffix=".tar.gz") as archive:
                subprocess.run(["tar", "-C", local_dir, "-czf", archive.name, "."], check=True)
                guest_archive = f"/tmp/buckyos-push-{os.getpid()}.tar.gz"
                with open(archive.name, "rb") as f:
                    self._file_write(vmid, guest_archive, f.read())
                _, err, code = self.exec_command(vm_name,
                    f"mkdir -p {shlex.quote(remote_dir)} && tar -xzf {shlex.quote(guest_archive)} -C {shlex.quote(remote_dir)}; rc=$?; rm -f {shlex.quote(guest_archive)}; exit $rc")
                return code == 0
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print(f"Failed to push directory to PVE VM {vm_name}: {e}")
            return False

    def pull_dir(self, vm_name: str, remote_dir: str, local_dir: str) -> bool:
        guest_archive = f"/tmp/buckyos-pull-{os.getpid()}.tar.gz"
        try:
            vmid = self._vmid(vm_name)
            _, err, code = self.exec_command(vm_name,
                f"tar -C {shlex.quote(remote_dir)} -czf {shlex.quote(guest_archive)} .")
            if code != 0:
                return False
            data = self._file_read(vmid, guest_archive)
            self.exec_command(vm_name, f"rm -f {shlex.quote(guest_archive)}")
            os.makedirs(local_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(suffix=".tar.gz") as archive:
                archive.write(data); archive.flush()
                subprocess.run(["tar", "-C", local_dir, "-xzf", archive.name], check=True)
            return True
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print(f"Failed to pull directory from PVE VM {vm_name}: {e}")
            return False

    def get_vm_ip(self, vm_name: str) -> list[str]:
        vmid = self._vmid(vm_name)
        result = self._run(["qm", "guest", "cmd", str(vmid), "network-get-interfaces"])
        data = json.loads(result.stdout)
        ips = []
        for interface in data:
            for item in interface.get("ip-addresses", []):
                address = item.get("ip-address")
                if item.get("ip-address-type") == "ipv4" and address != "127.0.0.1":
                    ips.append(address)
        return ips

    def is_vm_exists(self, vm_name: str) -> bool:
        try:
            self._vmid(vm_name)
            return True
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
            return False

    def snapshot(self, node_id: str, snapshot_name: str) -> bool:
        try:
            return self._lifecycle(["snapshot", str(self._vmid(node_id)), snapshot_name])
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print(f"Failed to snapshot PVE VM {node_id}: {e}")
            return False

    def restore(self, node_id: str, snapshot_name: str) -> bool:
        try:
            vmid = self._vmid(node_id)
            self._run(["qm", "stop", str(vmid)], check=False)
            self._run(["qm", "rollback", str(vmid), snapshot_name])
            self._run(["qm", "start", str(vmid)])
            return True
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print(f"Failed to restore PVE VM {node_id}: {e}")
            return False

    def _lifecycle(self, args) -> bool:
        try:
            self._run(["qm", *args])
            return True
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print(f"PVE operation failed: {e}")
            return False

    def stop_vm(self, node_id: str) -> bool:
        try:
            return self._lifecycle(["shutdown", str(self._vmid(node_id)), "--timeout", "60", "--forceStop", "1"])
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print(f"Failed to stop PVE VM {node_id}: {e}")
            return False

    def start_vm(self, node_id: str) -> bool:
        try:
            return self._lifecycle(["start", str(self._vmid(node_id))])
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print(f"Failed to start PVE VM {node_id}: {e}")
            return False

    def set_template_base_dir(self, template_base_dir: Path) -> bool:
        self.template_base_dir = Path(template_base_dir)
        return True
    
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
            backend_type: Backend type, supports "multipass" and "pve"
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
        elif backend_type == "pve":
            self.backend = PVEVMBackend()
        else:
            raise ValueError(f"Unsupported backend type: {backend_type}")

        VMManager._backend_type = backend_type
        self._initialized = True

    @classmethod
    def get_instance(cls):
        """Get singleton instance"""
        backend_type = cls._backend_type or os.environ.get("BUCKYOS_VM_BACKEND", "multipass")
        return cls(backend_type)

    @classmethod
    def get_backend_type(cls):
        """Get current singleton backend type"""
        return cls._backend_type or os.environ.get("BUCKYOS_VM_BACKEND", "multipass")

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
        """Execute command in virtual machine, returns (stdout, stderr, returncode)"""
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
