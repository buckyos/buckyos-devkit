import os
from pathlib import Path
import shutil
import platform
import sys
from typing import Optional

from .buckyos_kit import ensure_executable
from .project import AppInfo, BuckyProject

src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

install_root_dir = os.environ.get("BUCKYOS_ROOT", "")

pre_install_apps = [
    {
        "app_id": "buckyos-filebrowser",
        "base_url": "https://github.com/buckyos/filebrowser/releases/download/",
    }
]

if install_root_dir == "":
    if platform.system() == "Windows":
        install_root_dir = os.path.join(os.path.expandvars("%AppData%"), "buckyos")
    else:
        install_root_dir = "/opt/buckyos"

def get_install_root_dir():
    return install_root_dir

def set_data_dir_permissions():
    if platform.system() != "Windows":  # Windows doesn't need permission setting
        import pwd
        import grp
        
        # Get SUDO_USER environment variable, which is the actual user running sudo
        real_user = os.environ.get('SUDO_USER')
        if real_user:
            data_dir = os.path.join(install_root_dir, "data")
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
            
            # Get the real user's uid and gid
            uid = pwd.getpwnam(real_user).pw_uid
            gid = pwd.getpwnam(real_user).pw_gid
            
            # Recursively set directory permissions
            for root, dirs, files in os.walk(data_dir):
                os.chown(root, uid, gid)
                for d in dirs:
                    os.chown(os.path.join(root, d), uid, gid)
                for f in files:
                    os.chown(os.path.join(root, f), uid, gid)
            
            # Set directory permissions to 755 (rwxr-xr-x)
            os.chmod(data_dir, 0o755)

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
def update_app(project:BuckyProject,app_name:str,target_rootfs:Optional[Path]=None):
    # copy build modules to rootfs/
    app_info : Optional[AppInfo] = project.apps.get(app_name)
    if app_info is None:
        raise ValueError(f"App {app_name} not found")

    if target_rootfs is None:
        target_rootfs = app_info.default_target_rootfs

    print(f"🎯 Updating modules for app {app_name} to {target_rootfs}")

    for module_name, module_path in app_info.modules.items():
        src_path = Path(project.base_dir) / app_info.rootfs / module_path
        target_path = Path(target_rootfs) / module_path
        
        if src_path.is_file():
            # 确保目标目录存在
            target_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"+ Copying file {src_path} => {target_path}")
            shutil.copy(src_path, target_path)
            ensure_executable(str(target_path))
        elif src_path.is_dir():
            # 确保目标父目录存在
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                print(f"- Removing {target_path}")
                shutil.rmtree(target_path)
            print(f"+ Copying directory {src_path} => {target_path}")
            shutil.copytree(src_path, target_path)
        else:
            print(f"⚠️  Source path not found: {src_path}")
    
    print(f"✅ Updating app {app_name} to {target_rootfs} OK")

def clean_app(project:BuckyProject,app_name:str,target_rootfs:Optional[Path]=None):
    app_info : Optional[AppInfo] = project.apps.get(app_name)
    if app_info is None:
        raise ValueError(f"App {app_name} not found")

    if target_rootfs is None:
        target_rootfs = app_info.default_target_rootfs

    print(f"🧹 Cleaning app {app_name} from {target_rootfs}")
    for clean_path in app_info.clean_paths:
        real_path = Path(target_rootfs) / clean_path
        if real_path.exists():
            print(f"- Removing {real_path}")
            if real_path.is_file():
                real_path.unlink()
            elif real_path.is_dir():
                shutil.rmtree(real_path)


def install_app_data(project:BuckyProject,app_name:str,target_rootfs:Optional[Path]=None):
    app_info : AppInfo = project.apps.get(app_name)
    if app_info is None:
        raise ValueError(f"App {app_name} not found")

    if target_rootfs is None:
        target_rootfs = app_info.default_target_rootfs

    print(f"📋 Installing data for app {app_name} to {target_rootfs}")

    for data_path in app_info.data_paths:
        src_path = Path(project.base_dir) / app_info.rootfs / data_path
        target_path = Path(target_rootfs) / data_path
        
        if src_path.exists():
            if src_path.is_file():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"+ Copying file {src_path} => {target_path}")
                shutil.copy(src_path, target_path)
            elif src_path.is_dir():
                if target_path.exists():
                    print(f"- Removing {target_path}")
                    shutil.rmtree(target_path)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"+ Copying directory {src_path} => {target_path}")
                shutil.copytree(src_path, target_path)
        else:
            # 数据路径可能还不存在，创建空目录
            print(f"+ Creating data directory {target_path}")
            target_path.mkdir(parents=True, exist_ok=True)


def reinstall_app(bucky_project:BuckyProject, app_name:str, target_rootfs:Optional[Path]=None):
    print(f"🔄 Reinstalling app {app_name} to {target_rootfs} ... ")
    clean_app(bucky_project, app_name, target_rootfs)
    install_app_data(bucky_project, app_name, target_rootfs)
    update_app(bucky_project, app_name, target_rootfs)
    print(f"✅ Reinstalling app {app_name} to {target_rootfs} OK")


def install_main():
    install_all: bool = "--all" in sys.argv or "reinstall" in sys.argv
    app_name : Optional[str] = None
    for arg in sys.argv:
        if arg.startswith("--app="):
            app_name = arg.split("=")[1]

    bucky_project: BuckyProject = BuckyProject.from_file(os.path.join(src_dir, "bucky_project.json"))
    
    if install_all:
        if app_name is None:
            print("Installing all apps ... 🚀")
            for app_name in bucky_project.apps.keys():
                reinstall_app(bucky_project, app_name)
            return
        else:
            reinstall_app(bucky_project, app_name)
    else:
        if app_name is None:
            print("Updating all apps ... 🚀")
            for app_name in bucky_project.apps.keys():
                update_app(bucky_project, app_name)
            return
        else:
            update_app(bucky_project, app_name)

if __name__ == "__main__":
    install_main()