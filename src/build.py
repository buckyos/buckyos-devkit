import sys
import platform
from typing import Optional

from .build_web_apps import build_web_modules
from .build_rust import build_rust_modules
from .project import BuckyProject
from .prepare_rootfs import copy_build_results

def build(project: BuckyProject,rust_target:str,skip_web_module:bool):
    if not skip_web_module:
        build_web_modules(project)
    build_rust_modules(project, rust_target)
    copy_build_results(project, skip_web_module)

def build_main():
    from pathlib import Path
    
    skip_web_module = False
    system = platform.system() # Linux / Windows / Darwin
    arch = platform.machine() # x86_64 / AMD64 / arm64 / arm
    print(f"DEBUG: system:{system},arch:{arch}")
    target = ""
    if system == "Linux" and (arch == "x86_64" or arch == "AMD64"):
        target = "x86_64-unknown-linux-musl"
    elif system == "Windows" and (arch == "x86_64" or arch == "AMD64"):
        target = "x86_64-pc-windows-msvc"
#     elif system == "Linux" and (arch == "x86_64" or arch == "AMD64"):
#         target = "aarch64-unknown-linux-gnu"
    elif system == "Darwin" and (arch == "arm64" or arch == "arm"):
        target = "aarch64-apple-darwin"

    for arg in sys.argv:
        if arg == "--skip-web":
            skip_web_module = True
        if arg == "amd64":
            target = "x86_64-unknown-linux-musl"
        if arg == "aarch64":
            target = "aarch64-unknown-linux-musl"
        if arg.startswith("--target="):
            target = arg.split("=")[1]

    # Load project configuration
    # Load project configuration
    config_file : Optional[Path] = BuckyProject.get_project_config_file()
    if config_file is None:
        print("Error: No bucky_project.json or bucky_project.yaml configuration file found in current directory")
        sys.exit(1)
    
    print(f"Loading project configuration from: {config_file}")
    bucky_project = BuckyProject.from_file(config_file)

    print(f"Rust target is : {target}")
    build(bucky_project, target, skip_web_module)
    
if __name__ == "__main__":
    build_main()