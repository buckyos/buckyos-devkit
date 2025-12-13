# Extracted from make_deb logic, platform-independent preparation work before packaging
# 1. Copy rootfs to a specified folder, usually an Installer-related folder under /tmp
# 2. Clear the copied rootfs/bin, to be reorganized later
# 3. Call prepare_packages to prepare new PackageMeta
# 4. Download current meta db file from official source
# 5. Add new version PackageMeta to local meta db and re-"install" bin folder
# 6. Organize and remove unnecessary files
import os
import shutil
import json
import subprocess
import time
import glob
import platform
from urllib.request import urlretrieve
from . import prepare_packages

src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
rootfs_dir = os.path.join(src_dir, "rootfs")
base_meta_db_url = "https://buckyos.ai/ndn/repo/meta_index.db/content"

# If BUCKYCLI_PATH environment variable is defined, use it as the CLI executable
def default_buckycli_path():
    buckycli_path = os.path.join(src_dir, "rootfs/bin/buckycli", "buckycli")
    if platform.system() == "Windows":
        buckycli_path += ".exe"
    return buckycli_path
buckycli_path = os.getenv("BUCKYCLI_PATH", default_buckycli_path())
print(f'use buckycli at {buckycli_path}')

def prepare_meta_db(rootfs_dir):
    # 1 download base meta db
    print(f"# download base meta db from {base_meta_db_url}")
    os.makedirs(os.path.join(rootfs_dir, "local", "node_daemon", "root_pkg_env","pkgs"), exist_ok=True)
    root_env_db_path = os.path.join(rootfs_dir, "local", "node_daemon", "root_pkg_env","pkgs","meta_index.db")
    urlretrieve(base_meta_db_url, root_env_db_path)
    # subprocess.run(["wget",base_meta_db_url,"-O",root_env_db_path], check=True)
    print(f"# download base meta db to {root_env_db_path}")
    # 2 scan packed pkgs dir, add pkg_meta_info to meta db
    packed_pkgs_dir = os.path.join(rootfs_dir, "bin")
    print(f"# packed_pkgs_dir: {packed_pkgs_dir}")
    pkg_items = glob.glob(os.path.join(packed_pkgs_dir, "*"))
    for pkg_item in pkg_items:
        print(f"# add pkg_meta_info to meta db from {pkg_item}")
        if os.path.isdir(pkg_item):
            pkg_item = os.path.join(pkg_item, "pkg_meta.json")
            if os.path.exists(pkg_item):
                subprocess.run([buckycli_path,"set_pkg_meta",pkg_item,root_env_db_path], check=True)
                print(f"# add pkg_meta_info to meta db from {pkg_item}")
        else:
            # Why does this scenario exist?
            if pkg_item.endswith(".json") and not pkg_item.endswith("pkg.cfg.json"):
                subprocess.run([buckycli_path,"set_pkg_meta",pkg_item,root_env_db_path], check=True)
                print(f"# add pkg_meta_info to meta db from {pkg_item}")

    fileobj_path = os.path.join(rootfs_dir, "local", "node_daemon", "root_pkg_env","pkgs", "meta_index.db.fileobj")
    fileobj = json.load(open(fileobj_path))
    
    current_time = int(time.time())
    fileobj["create_time"] = current_time
    json.dump(fileobj, open(fileobj_path, "w"))
    fileobj_path = os.path.join(rootfs_dir, "data", "repo-service", "default_meta_index.db.fileobj")
    json.dump(fileobj, open(fileobj_path, "w"))
    print(f"# update fileobj create_time to {current_time} for {fileobj_path}")
    os.makedirs(os.path.join(rootfs_dir, "bin", "pkgs"), exist_ok=True)
    shutil.copy(root_env_db_path, os.path.join(rootfs_dir, "bin", "pkgs", "meta_index.db"))
    shutil.copy(root_env_db_path, os.path.join(rootfs_dir, "data", "repo-service", "default_meta_index.db"))
    print(f"# save meta db to {os.path.join(rootfs_dir, 'bin', 'pkgs', 'meta_index.db')}")

def prepare_installer(target_dir, channel, os_name, arch, version, builddate):
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    shutil.copytree(rootfs_dir, target_dir, dirs_exist_ok=True)
    print(f"# copy rootfs to {target_dir}")

    bin_dir = os.path.join(target_dir, "bin")
    # write pkg.cfg.json to bin_dir
    pkg_cfg_path = os.path.join(src_dir, "publish", "buckyos_pkgs","pkg.cfg.json")
    pkg_cfg = json.load(open(pkg_cfg_path))
    pkg_cfg["prefix"] = f"${channel}-{os_name}-{arch}"
    pkg_cfg["parent"] = None
    json.dump(pkg_cfg, open(os.path.join(bin_dir, "pkg.cfg.json"), "w"))
    print(f"# write pkg.cfg.json to {bin_dir} OK ")

    # perpare packages
    prepare_packages.perpare_all(channel, os_name, arch, version, builddate, target_dir=bin_dir, no_copy_app=True)

    prepare_meta_db(target_dir)
    print(f"# prepare meta db to {target_dir}")
    

    # perpare parent path:
    # windows: c:\buckyos\local\node_daemon\root_pkg_env
    # non-windows: /opt/buckyos/local/node_daemon/root_pkg_env
    if os_name == "windows":
        pkg_cfg["parent"] = "c:\\buckyos\\local\\node_daemon\\root_pkg_env"
    else:
        pkg_cfg["parent"] = "/opt/buckyos/local/node_daemon/root_pkg_env"
    json.dump(pkg_cfg, open(os.path.join(bin_dir, "pkg.cfg.json"), "w"))

    os.remove(os.path.join(bin_dir, "pkgs", "meta_index.db"))
    print(f"# remove meta_index.db from {bin_dir}")

    clean_dir = os.path.join(target_dir, "etc")
    print(f"clean all .pem and .toml files and start_config.json in {clean_dir}")
    for file in glob.glob(os.path.join(clean_dir, "*.pem")):
        os.remove(file)
    for file in glob.glob(os.path.join(clean_dir, "*.toml")):
        os.remove(file)
    os.remove(os.path.join(clean_dir, "start_config.json"))
    os.remove(os.path.join(clean_dir, "node_identity.json"))
    for file in glob.glob(os.path.join(clean_dir, "*.zone.json")):
        os.remove(file)
    os.remove(os.path.join(clean_dir, "scheduler", "boot.template.toml"))
    shutil.move(os.path.join(clean_dir, "scheduler", "nightly.template.toml"), os.path.join(clean_dir, "scheduler", "boot.template.toml"))
    shutil.move(os.path.join(clean_dir, "machine.json"), os.path.join(clean_dir, "machine_config.json"))