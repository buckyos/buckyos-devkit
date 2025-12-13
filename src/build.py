import sys
import platform

from .build_web_apps import build_web_apps
from .build_rust import build_rust_apps
from .project import BuckyProject
from .prepare_rootfs import copy_build_results

def build(project: BuckyProject,rust_target:str,skip_web_app:bool):
    if not skip_web_app:
        build_web_apps(project)
    build_rust_apps(project, rust_target)
    copy_build_results(project, skip_web_app)

def build_main():
    skip_web_app = False
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
        if arg == "--no-build-web-apps":
            skip_web_app = True
        if arg == "amd64":
            target = "x86_64-unknown-linux-musl"
        if arg == "aarch64":
            target = "aarch64-unknown-linux-musl"
        if arg.startswith("--target="):
            target = arg.split("=")[1]

    print(f"Rust target is : {target}")
    build(project, target, skip_web_app)
    
if __name__ == "__main__":
    build_main()