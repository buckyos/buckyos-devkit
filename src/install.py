import os
import platform
import posixpath
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
from typing import Optional

from .buckyos_kit import ensure_executable, get_execute_name, get_buckyos_root
from .project import AppInfo, BuckyProject, WebModuleInfo

src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

buckyos_root = get_buckyos_root()

pre_install_apps = [
    {
        "app_id": "buckyos-filebrowser",
        "base_url": "https://github.com/buckyos/filebrowser/releases/download/",
    }
]


class RemoteInstallHost:
    def __init__(
        self,
        host: str,
        user: Optional[str] = None,
        port: Optional[int] = None,
        identity_file: Optional[Path] = None,
        ssh_options: Optional[list[str]] = None,
        use_sudo: bool = False,
    ) -> None:
        embedded_user, host = self._split_host(host)
        if user is not None and embedded_user is not None:
            raise ValueError("Specify the SSH user either in --remote or --ssh-user, not both")

        self.host = host
        self.user = user or embedded_user
        self.port = port
        self.identity_file = identity_file
        self.ssh_options = ssh_options or []
        self.use_sudo = use_sudo
        self._temp_dir: Optional[PurePosixPath] = None
        self._copy_index = 0
        self._remote_home: Optional[PurePosixPath] = None

        for command in ("ssh", "scp"):
            if shutil.which(command) is None:
                raise FileNotFoundError(f"Required command not found: {command}")

    @staticmethod
    def _split_host(value: str) -> tuple[Optional[str], str]:
        if not value or value.startswith("-") or any(char.isspace() for char in value):
            raise ValueError(f"Invalid remote host: {value!r}")

        user: Optional[str] = None
        host = value
        if "@" in value:
            user, host = value.rsplit("@", 1)
            if not user or not re.fullmatch(r"[A-Za-z0-9._-]+", user):
                raise ValueError(f"Invalid SSH user in remote host: {value!r}")

        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        if not host or not re.fullmatch(r"[A-Za-z0-9._:-]+", host):
            raise ValueError(f"Invalid remote host: {value!r}")
        return user, host

    @property
    def destination(self) -> str:
        if self.user is None:
            return self.host
        return f"{self.user}@{self.host}"

    @property
    def scp_destination(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        if self.user is None:
            return host
        return f"{self.user}@{host}"

    def _connection_args(self, scp: bool = False) -> list[str]:
        args: list[str] = []
        if self.port is not None:
            args.extend(["-P" if scp else "-p", str(self.port)])
        if self.identity_file is not None:
            args.extend(["-i", str(self.identity_file)])
        for option in self.ssh_options:
            args.extend(["-o", option])
        return args

    def run(self, script: str, capture_output: bool = False, sudo: bool = False) -> str:
        if sudo and self.use_sudo:
            remote_command = f"sudo -n sh -c {shlex.quote(script)}"
        else:
            remote_command = f"sh -c {shlex.quote(script)}"

        command = [
            "ssh",
            *self._connection_args(),
            self.destination,
            remote_command,
        ]
        print(f"+ ssh {self.destination}: {script}")
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=None,
        )
        if result.returncode != 0:
            detail = (result.stderr or "").strip()
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(
                f"SSH command on {self.destination} failed with exit code {result.returncode}{suffix}"
            )
        return (result.stdout or "").strip()

    def _ensure_temp_dir(self) -> PurePosixPath:
        if self._temp_dir is None:
            value = self.run(
                "umask 077 && mktemp -d /tmp/buckyos-install.XXXXXXXXXX",
                capture_output=True,
            )
            temp_dir = value.splitlines()[-1] if value else ""
            if not re.fullmatch(r"/tmp/buckyos-install\.[A-Za-z0-9]+", temp_dir):
                raise RuntimeError(f"Unexpected remote temporary directory: {temp_dir!r}")
            self._temp_dir = PurePosixPath(temp_dir)
        return self._temp_dir

    def close(self) -> None:
        if self._temp_dir is None:
            return
        temp_dir = self._temp_dir
        self._temp_dir = None
        try:
            self.run(f"rm -rf -- {shlex.quote(str(temp_dir))}", capture_output=True)
        except RuntimeError as error:
            print(f"Warning: failed to remove remote temporary directory {temp_dir}: {error}")

    def __enter__(self) -> "RemoteInstallHost":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _next_staging_path(self) -> PurePosixPath:
        self._copy_index += 1
        return self._ensure_temp_dir() / f"payload-{self._copy_index}"

    def _scp(self, source: Path, target: PurePosixPath, recursive: bool = False) -> None:
        command = ["scp", *self._connection_args(scp=True), "-p"]
        if recursive:
            command.append("-r")
        command.extend([str(source), f"{self.scp_destination}:{target}"])
        print(f"+ scp {source} => {self.destination}:{target}")
        result = subprocess.run(command)
        if result.returncode != 0:
            raise RuntimeError(
                f"SCP to {self.destination} failed with exit code {result.returncode}"
            )

    @staticmethod
    def _safe_path(path: PurePosixPath) -> PurePosixPath:
        normalized = PurePosixPath(posixpath.normpath(str(path)))
        if not normalized.is_absolute() or normalized == PurePosixPath("/"):
            raise ValueError(f"Remote install path must be an absolute non-root path: {path}")
        return normalized

    def resolve_target_path(self, value: str | Path | PurePosixPath) -> PurePosixPath:
        raw_path = os.fspath(value)
        raw_path = raw_path.replace("${BUCKYOS_ROOT}", "/opt/buckyos/")
        raw_path = raw_path.replace("$BUCKYOS_ROOT", "/opt/buckyos/")
        if raw_path == "~" or raw_path.startswith("~/"):
            if self._remote_home is None:
                home = self.run('printf "%s" "$HOME"', capture_output=True)
                self._remote_home = self._safe_path(PurePosixPath(home))
            suffix = raw_path[2:] if raw_path.startswith("~/") else ""
            return self._safe_path(self._remote_home / suffix)
        return self._safe_path(PurePosixPath(raw_path))

    @staticmethod
    def child_path(root: PurePosixPath, value: str | Path) -> PurePosixPath:
        child = PurePosixPath(os.fspath(value))
        if child.is_absolute() or ".." in child.parts or child == PurePosixPath("."):
            raise ValueError(f"Remote app path must stay below the target rootfs: {value}")
        return root / child

    def path_state(self, path: PurePosixPath) -> str:
        path = self._safe_path(path)
        quoted = shlex.quote(str(path))
        script = (
            f"if [ ! -e {quoted} ]; then printf absent; "
            f"elif [ -d {quoted} ] && "
            f"[ -z \"$(find {quoted} -mindepth 1 -maxdepth 1 -print -quit)\" ]; "
            "then printf empty; else printf present; fi"
        )
        state = self.run(script, capture_output=True, sudo=True).splitlines()[-1]
        if state not in {"absent", "empty", "present"}:
            raise RuntimeError(f"Unexpected state for remote path {path}: {state!r}")
        return state

    def exists(self, path: PurePosixPath) -> bool:
        path = self._safe_path(path)
        quoted = shlex.quote(str(path))
        return self.run(
            f"if [ -e {quoted} ]; then printf yes; else printf no; fi",
            capture_output=True,
            sudo=True,
        ).splitlines()[-1] == "yes"

    def make_directory(self, path: PurePosixPath) -> None:
        path = self._safe_path(path)
        self.run(f"mkdir -p -- {shlex.quote(str(path))}", sudo=True)

    def remove(self, path: PurePosixPath) -> None:
        path = self._safe_path(path)
        self.run(f"rm -rf -- {shlex.quote(str(path))}", sudo=True)

    def copy_file(self, source: Path, target: PurePosixPath, executable: bool = False) -> None:
        if not source.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")
        target = self._safe_path(target)
        staging_path = self._next_staging_path()
        self._scp(source, staging_path)
        script = (
            f"mkdir -p -- {shlex.quote(str(target.parent))} && "
            f"cp -- {shlex.quote(str(staging_path))} {shlex.quote(str(target))}"
        )
        if executable:
            script += f" && chmod +x -- {shlex.quote(str(target))}"
        self.run(script, sudo=True)

    def copy_directory(self, source: Path, target: PurePosixPath) -> None:
        if not source.is_dir():
            raise FileNotFoundError(f"Source directory not found: {source}")
        target = self._safe_path(target)
        staging_path = self._next_staging_path()
        self._scp(source, staging_path, recursive=True)
        script = (
            f"mkdir -p -- {shlex.quote(str(target.parent))} && "
            f"rm -rf -- {shlex.quote(str(target))} && "
            f"cp -R -- {shlex.quote(str(staging_path))} {shlex.quote(str(target))}"
        )
        executable_paths = []
        if platform.system().lower() == "linux":
            executable_paths = [
                target / path.relative_to(source)
                for path in source.rglob("*")
                if path.is_file()
                and _is_probably_executable(path)
                and not os.access(path, os.X_OK)
            ]
        if executable_paths:
            quoted_paths = " ".join(shlex.quote(str(path)) for path in executable_paths)
            script += f" && chmod +x -- {quoted_paths}"
        self.run(script, sudo=True)


def _is_probably_executable(file_path: Path) -> bool:
    # 通过文件头判断是否可能是可执行文件（脚本或 ELF）
    try:
        with open(file_path, "rb") as f:
            head = f.read(4)
        return head.startswith(b"#!") or head.startswith(b"\x7fELF")
    except OSError:
        return False

def _ensure_executable_files_in_dir(directory_path: Path) -> None:
    # 仅在 Linux 下扫描目录内文件，必要时补齐可执行权限
    if platform.system().lower() != "linux":
        return
    chmod_count = 0
    for root, _, files in os.walk(directory_path):
        for name in files:
            file_path = Path(root) / name
            if _is_probably_executable(file_path) and not os.access(file_path, os.X_OK):
                try:
                    mode = os.stat(file_path).st_mode
                    os.chmod(file_path, mode | 0o111)
                    chmod_count += 1
                except OSError as e:
                    print(f"Warning: chmod +x failed for {file_path}: {e}")
    if chmod_count:
        print(f"# set +x for {chmod_count} files under {directory_path}")

def _copy_dir_with_exec_fix(src_path: Path, target_path: Path) -> None:
    # 复制目录后，修复可执行文件权限
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        print(f"- Removing {target_path}")
        shutil.rmtree(target_path)
    print(f"+ Copying directory {src_path} => {target_path}")
    shutil.copytree(src_path, target_path)
    _ensure_executable_files_in_dir(target_path)

def _is_empty_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        return next(path.iterdir(), None) is None
    except OSError:
        return False


def unzip_to_dir(zip_path, target_dir):
    """Extract zip file to target directory, content directly in target directory"""
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    
    # First extract to temporary directory
    temp_dir = os.path.join(os.path.dirname(zip_path), f"temp_{os.path.basename(zip_path)}")
    shutil.unpack_archive(zip_path, temp_dir)
    
    # Move extracted content to target directory
    extracted_dir = os.path.join(temp_dir, os.listdir(temp_dir)[0])
    for item in os.listdir(extracted_dir):
        src_path = os.path.join(extracted_dir, item)
        dst_path = os.path.join(target_dir, item)
        if os.path.isfile(src_path):
            shutil.copy2(src_path, dst_path)
        elif os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path)
    
    # Clean up temporary directory
    shutil.rmtree(temp_dir)
    print(f"Extraction completed: {zip_path} -> {target_dir}")

def download_file(url, filepath):
    """Cross-platform file download using system built-in commands"""
    system = platform.system().lower()
    
    if system == "windows":
        # Windows uses PowerShell's Invoke-WebRequest
        cmd = f'powershell -Command "Invoke-WebRequest -Uri \'{url}\' -OutFile \'{filepath}\' -UseBasicParsing"'
    elif system == "darwin":  # macOS
        # macOS uses curl
        cmd = f"curl -L -o '{filepath}' '{url}'"
    else:  # Linux
        # Linux prioritizes wget, falls back to curl if not available
        cmd = f"wget -c -L -O '{filepath}' '{url}'"
    
    print(f"Downloading: {url}")
    print(f"Saving to: {filepath}")
    print(f"Executing command: {cmd}")
    
    result = os.system(cmd)
    if result == 0:
        print(f"Download completed: {filepath}")
        return True
    else:
        print(f"Download failed, exit code: {result}")
        # If wget fails, try using curl
        if system not in ["windows", "darwin"]:
            print("Trying curl...")
            curl_cmd = f"curl -L -o '{filepath}' '{url}'"
            result = os.system(curl_cmd)
            if result == 0:
                print(f"Download completed with curl: {filepath}")
                return True
        
        return False

# def copy_configs(config_group_name):
#     etc_dir = os.path.join(install_root_dir, "etc")
#     configs_dir = os.path.join(src_dir, "scripts","configs_group",config_group_name)
#     print(f"Copying configs from {configs_dir} to {etc_dir}")
#     for config_file in os.listdir(configs_dir):
#         config_path = os.path.join(configs_dir, config_file)
#         if os.path.isfile(config_path):
#             shutil.copy(config_path, etc_dir)
#             print(f"Copied file {config_path} to {etc_dir}")
#         #elif os.path.isdir(config_path):
#         #    shutil.copytree(config_path, os.path.join(etc_dir, config_file))
#         #    print(f"Copied directory {config_path} to {etc_dir}")

def install_buckyos_apps():
    temp_dir = os.environ.get('TEMP') or os.environ.get('TMP') or '/tmp'
    download_dir = os.path.join(temp_dir, "buckyos-apps")
    version = os.path.join(src_dir, "VERSION")
    with open(version, "r") as f:
        version = f.read().strip()
    print(f"current version: {version},download dir: {download_dir}")
    
    # check and download app_pkg_zips
    # unzip to dest dir
    os_name = platform.system().lower()
    arch = platform.machine().lower()
    if arch == "x86_64":
        arch = "amd64"

    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    #nightly-apple-aarch64.buckyos-filebrowser-bin.zip
    preifx = f"nightly-{os_name}-{arch}"
    img_prefix = f"nightly-linux-{arch}"
    print(f"app prefix is {preifx}")
    for app in pre_install_apps:
        if os_name == "windows" or os_name == "darwin":
            app_full_id = f"{preifx}.{app['app_id']}-bin.zip"
            download_url = f"{app['base_url']}{version}/{app_full_id}"
            download_path = os.path.join(download_dir, f"{app['app_id']}-bin.zip")
            if download_file(download_url, download_path):
                print(f"download {app_full_id} OK")
                unzip_dir = os.path.join(install_root_dir, "bin", f"{app['app_id']}-bin")
                unzip_to_dir(download_path, unzip_dir)
                print(f"unzip {app_full_id} OK")
            else:
                print(f"download {app_full_id} FAILED")
        #https://github.com/buckyos/filebrowser/releases/download/0.4.0/nightly-linux-amd64.buckyos-filebrowser-img.zip
        app_img_full_id = f"{img_prefix}.{app['app_id']}-img.zip"
        download_url = f"{app['base_url']}{version}/{app_img_full_id}"
        download_path = os.path.join(download_dir, f"{app['app_id']}-img.zip")
        if download_file(download_url, download_path):
            print(f"download {app_img_full_id} OK")
            unzip_dir = os.path.join(install_root_dir, "bin", f"{app['app_id']}-img")
            unzip_to_dir(download_path, unzip_dir)
            print(f"unzip {app_img_full_id} OK")
        else:
            print(f"download {app_img_full_id} FAILED")

        print(f"install {app['app_id']} OK")

    return
    
########################################################
def _resolve_app_target(
    project: BuckyProject,
    app_info: AppInfo,
    target_rootfs: Optional[Path | PurePosixPath],
    remote: Optional[RemoteInstallHost],
) -> Path | PurePosixPath:
    configured_target = app_info.default_target_rootfs if target_rootfs is None else target_rootfs
    if remote is not None:
        return remote.resolve_target_path(configured_target)
    if target_rootfs is None:
        return project.resolve_from_config(configured_target)
    return BuckyProject._expand_path(configured_target)


def _target_child(
    target_rootfs: Path | PurePosixPath,
    relative_path: str | Path,
    remote: Optional[RemoteInstallHost],
) -> Path | PurePosixPath:
    if remote is not None:
        return remote.child_path(target_rootfs, relative_path)
    return target_rootfs / relative_path


def update_app(
    project: BuckyProject,
    app_name: str,
    skip_web_module: bool = False,
    check_reinstall: bool = False,
    target_rootfs: Optional[Path | PurePosixPath] = None,
    remote: Optional[RemoteInstallHost] = None,
):
    # copy build modules to rootfs/
    app_info : Optional[AppInfo] = project.apps.get(app_name)
    if app_info is None:
        raise ValueError(f"App {app_name} not found")

    target_rootfs = _resolve_app_target(project, app_info, target_rootfs, remote)
    
    if check_reinstall:
        target_state = remote.path_state(target_rootfs) if remote is not None else None
        if (remote is not None and target_state == "absent") or (
            remote is None and not target_rootfs.exists()
        ):
            print(f"⚠️  App {app_name} target rootfs {target_rootfs} not exists, need reinstall...")
            return reinstall_app(project, app_name, skip_web_module, target_rootfs, remote)
        if (remote is not None and target_state == "empty") or (
            remote is None and _is_empty_dir(target_rootfs)
        ):
            print(f"⚠️  App {app_name} target rootfs {target_rootfs} is empty, need reinstall...")
            return reinstall_app(project, app_name, skip_web_module, target_rootfs, remote)

    print(f"🎯 Updating modules for app {app_name} to {target_rootfs}")

    for module_name, module_path in app_info.modules.items():
        if skip_web_module:
            module_info  = project.modules.get(module_name)
            if isinstance(module_info, WebModuleInfo):
                continue

        src_path = project.resolve_from_base_dir(app_info.rootfs) / module_path
        target_path = _target_child(target_rootfs, module_path, remote)
        
        if not module_path.endswith("/"):
            # 确保目标目录存在
            #print(f"target_path.parent: {target_path.parent}")
            src_path = get_execute_name(src_path)
            if remote is None:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path = get_execute_name(target_path)

            print(f"+ Copying file {src_path} => {target_path}")
            if remote is None:
                shutil.copy(src_path, target_path)
                ensure_executable(str(target_path))
            else:
                remote.copy_file(Path(src_path), target_path, executable=True)
        else:
            if remote is None:
                _copy_dir_with_exec_fix(src_path, target_path)
            else:
                remote.copy_directory(src_path, target_path)

    
    print(f"✅ Updating app {app_name} to {target_rootfs} OK")

def clean_app(
    project: BuckyProject,
    app_name: str,
    target_rootfs: Optional[Path | PurePosixPath] = None,
    remote: Optional[RemoteInstallHost] = None,
):
    app_info : Optional[AppInfo] = project.apps.get(app_name)
    if app_info is None:
        raise ValueError(f"App {app_name} not found")

    target_rootfs = _resolve_app_target(project, app_info, target_rootfs, remote)

    print(f"🧹 Cleaning app {app_name} from {target_rootfs}")
    for clean_path in app_info.clean_paths:
        real_path = _target_child(target_rootfs, clean_path, remote)
        path_exists = remote.exists(real_path) if remote is not None else real_path.exists()
        if path_exists:
            print(f"- Removing {real_path}")
            if remote is not None:
                remote.remove(real_path)
            elif real_path.is_file():
                real_path.unlink()
            elif real_path.is_dir():
                shutil.rmtree(real_path)


def install_app_data(
    project: BuckyProject,
    app_name: str,
    target_rootfs: Optional[Path | PurePosixPath] = None,
    remote: Optional[RemoteInstallHost] = None,
):
    app_info : AppInfo = project.apps.get(app_name)
    if app_info is None:
        raise ValueError(f"App {app_name} not found")

    target_rootfs = _resolve_app_target(project, app_info, target_rootfs, remote)

    print(f"📋 Installing data for app {app_name} to {target_rootfs}")

    for data_path in app_info.data_paths:
        src_path = project.resolve_from_base_dir(app_info.rootfs) / data_path
        target_path = _target_child(target_rootfs, data_path, remote)
        path_exists = remote.exists(target_path) if remote is not None else target_path.exists()
        if path_exists:
            print(f"⏭️ {target_path} already exists, keep user data.")
            continue;
            
        if src_path.exists():
            if src_path.is_file():
                print(f"+ Copying file {src_path} => {target_path}")
                if remote is None:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(src_path, target_path)
                else:
                    remote.copy_file(src_path, target_path)
            elif src_path.is_dir():
                if remote is None:
                    _copy_dir_with_exec_fix(src_path, target_path)
                else:
                    remote.copy_directory(src_path, target_path)
        else:
            # 数据路径可能还不存在，创建空目录
            print(f"+ Creating data directory {target_path}")
            if remote is None:
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                remote.make_directory(target_path)


def reinstall_app(
    bucky_project: BuckyProject,
    app_name: str,
    skip_web_module: bool = False,
    target_rootfs: Optional[Path | PurePosixPath] = None,
    remote: Optional[RemoteInstallHost] = None,
):
    print(f"🔄 Reinstalling app {app_name} to {target_rootfs} ... ")
    clean_app(bucky_project, app_name, target_rootfs, remote)
    install_app_data(bucky_project, app_name, target_rootfs, remote)
    update_app(
        bucky_project,
        app_name,
        skip_web_module,
        check_reinstall=False,
        target_rootfs=target_rootfs,
        remote=remote,
    )
    print(f"✅ Reinstalling app {app_name} OK")

INSTALL_HELP = """usage: {prog} [-h] [--all] [reinstall] [--app=APP]
                 [--skip-web] [--target-rootfs=DIR] [--remote=HOST]
                 [--ssh-user=USER] [--ssh-port=PORT] [--ssh-key=FILE]
                 [--ssh-option=OPTION] [--sudo] [--yes]

Install or update BuckyOS project apps.

positional arguments:
  reinstall             Reinstall apps instead of updating changed files

options:
  -h, --help            Show this help message and exit
  --all                 Reinstall all apps
  --app=APP             Limit the operation to one app
  --skip-web            Skip web modules while updating app files
  --target-rootfs=DIR   Override the target rootfs directory
  --remote=HOST         Install on a remote POSIX host through ssh/scp;
                        USER@HOST is also accepted
  --ssh-user=USER       SSH user (defaults to the SSH configuration)
  --ssh-port=PORT       SSH port (defaults to the SSH configuration)
  --ssh-key=FILE        SSH private key file
  --ssh-option=OPTION   Pass an -o option to ssh/scp; may be repeated
  --sudo                Run remote filesystem changes through passwordless sudo
  -y, --yes             Confirm reinstalling a non-empty remote target
"""


def _has_help_arg(args: list[str]) -> bool:
    return any(arg in ("-h", "--help") for arg in args)


def _print_install_help(prog: str) -> None:
    print(INSTALL_HELP.format(prog=prog))


def _option_values(args: list[str], option: str) -> list[str]:
    values: list[str] = []
    prefix = f"{option}="
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == option:
            if index + 1 >= len(args) or args[index + 1].startswith("--"):
                raise ValueError(f"{option} requires a value")
            values.append(args[index + 1])
            index += 2
            continue
        if arg.startswith(prefix):
            value = arg[len(prefix):]
            if not value:
                raise ValueError(f"{option} requires a value")
            values.append(value)
        index += 1
    return values


def _option_value(args: list[str], option: str) -> Optional[str]:
    values = _option_values(args, option)
    if len(values) > 1:
        raise ValueError(f"{option} may only be specified once")
    return values[0] if values else None


def _parse_ssh_port(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        port = int(value)
    except ValueError as error:
        raise ValueError(f"Invalid --ssh-port value: {value!r}") from error
    if port < 1 or port > 65535:
        raise ValueError(f"Invalid --ssh-port value: {value!r}")
    return port


def _confirm_remote_reinstall(
    remote: RemoteInstallHost,
    targets: list[tuple[str, PurePosixPath]],
) -> bool:
    print("⚠️  Full reinstall requested for existing remote installation(s):")
    for app_name, target in targets:
        print(f"  - {app_name}: {remote.destination}:{target}")
    try:
        answer = input("This may remove remote configuration and runtime data. Continue? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in {"y", "yes"}


def _run_install(
    bucky_project: BuckyProject,
    install_all: bool,
    app_name: Optional[str],
    skip_web_module: bool,
    target_rootfs: Optional[Path],
    remote: Optional[RemoteInstallHost] = None,
    assume_yes: bool = False,
) -> int:
    if app_name is not None and app_name not in bucky_project.apps:
        raise ValueError(f"App {app_name} not found")
    app_names = [app_name] if app_name is not None else list(bucky_project.apps.keys())

    if install_all and remote is not None and not assume_yes:
        existing_targets: list[tuple[str, PurePosixPath]] = []
        for selected_app in app_names:
            app_info = bucky_project.apps[selected_app]
            resolved_target = _resolve_app_target(
                bucky_project,
                app_info,
                target_rootfs,
                remote,
            )
            if remote.path_state(resolved_target) == "present":
                existing_targets.append((selected_app, resolved_target))
        if existing_targets and not _confirm_remote_reinstall(remote, existing_targets):
            print("Remote reinstall cancelled.")
            return 1

    if install_all:
        if app_name is None:
            print("Installing all apps ... 🚀")
        for selected_app in app_names:
            reinstall_app(
                bucky_project,
                selected_app,
                skip_web_module,
                target_rootfs,
                remote,
            )
        return 0

    if app_name is None:
        print("Updating all apps ... 🚀")
    for selected_app in app_names:
        update_app(
            bucky_project,
            selected_app,
            skip_web_module,
            check_reinstall=True,
            target_rootfs=target_rootfs,
            remote=remote,
        )
    return 0


def install_main(argv: list[str] | None = None):
    args = sys.argv[1:] if argv is None else list(argv)
    if _has_help_arg(args):
        prog = Path(sys.argv[0]).name if argv is None else "buckyos-install"
        _print_install_help(prog)
        return

    try:
        target_rootfs_value = _option_value(args, "--target-rootfs")
        app_name = _option_value(args, "--app")
        remote_host = _option_value(args, "--remote")
        ssh_user = _option_value(args, "--ssh-user")
        ssh_port = _parse_ssh_port(_option_value(args, "--ssh-port"))
        ssh_key_value = _option_value(args, "--ssh-key")
        ssh_options = _option_values(args, "--ssh-option")
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print(f"buckyos_root: {buckyos_root}")
    target_rootfs = Path(target_rootfs_value) if target_rootfs_value is not None else None
    install_all: bool = "--all" in args or "reinstall" in args
    skip_web_module = "--skip-web" in args
    assume_yes = "--yes" in args or "-y" in args
    use_sudo = "--sudo" in args
    if remote_host is None and any(
        value is not None for value in (ssh_user, ssh_port, ssh_key_value)
    ):
        print("Error: SSH options require --remote", file=sys.stderr)
        return 2
    if remote_host is None and (ssh_options or use_sudo or assume_yes):
        print("Error: remote-only options require --remote", file=sys.stderr)
        return 2

    # Load project configuration
    config_file : Optional[Path] = BuckyProject.get_project_config_file()
    if config_file is None:
        print("Error: No bucky_project.json or bucky_project.yaml configuration file found in current directory or current directory/src")
        sys.exit(1)
    
    print(f"Loading project configuration from: {config_file}")
    local_config_file = BuckyProject.get_project_local_config_file(config_file)
    overlay_files = []
    if local_config_file is not None:
        print(f"Loading local project configuration from: {local_config_file}")
        overlay_files.append(local_config_file)
    bucky_project = BuckyProject.from_file(config_file, overlay_files)
    os.environ["BUCKYOS_ROOT"] =  get_buckyos_root()
    if os.environ.get("APPDATA") is None:
        os.environ["APPDATA"] = "/opt/"

    if remote_host is None:
        return _run_install(
            bucky_project,
            install_all,
            app_name,
            skip_web_module,
            target_rootfs,
        )

    identity_file = Path(ssh_key_value).expanduser() if ssh_key_value is not None else None
    try:
        with RemoteInstallHost(
            remote_host,
            user=ssh_user,
            port=ssh_port,
            identity_file=identity_file,
            ssh_options=ssh_options,
            use_sudo=use_sudo,
        ) as remote:
            print(f"Installing on remote host {remote.destination} through ssh/scp")
            return _run_install(
                bucky_project,
                install_all,
                app_name,
                skip_web_module,
                target_rootfs,
                remote=remote,
                assume_yes=assume_yes,
            )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    install_main()

