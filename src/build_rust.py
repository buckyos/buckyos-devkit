
import os
import tempfile
import sys
import subprocess
import platform
import shutil
from typing import Optional,Dict

from .project import BuckyProject

def check_musl_gcc():
    if shutil.which('musl-gcc') is None:
        print("Error: musl-gcc not found. Please install musl-tools.")
        sys.exit(1)

def check_aarch64_toolchain():
    if shutil.which('aarch64-linux-gnu-gcc') is None:
        print("Error: aarch64-linux-gnu-gcc not found. Please install gcc-aarch64-linux-gnu.")
        sys.exit(1)

def clean_rust_build(project: BuckyProject):
    print(f"Cleaning build artifacts at ${project.rust_target_dir}")
    subprocess.run(["cargo", "clean", "--target-dir", project.rust_target_dir], check=True, cwd=project.rust_target_dir)

def get_env_vars_by_target(target: str) -> Dict[str, str]:
    env_vars = {}
    if target == "x86_64-unknown-linux-musl":
        env_vars["RUSTFLAGS"] = "-C target-feature=+crt-static"
    elif target == "aarch64-unknown-linux-gnu":
        env_vars["RUSTFLAGS"] = "-C target-feature=+crt-static"
    return env_vars

def get_cross_compile_env_vars_by_target(target: str) -> Optional[Dict[str, str]]:
    # TODO: properly implement cross-compilation checks
    env_vars = None
    if target == "aarch64-unknown-linux-gnu":
        env_vars = {}
        env_vars["CC_aarch64_unknown_linux_gnu"] = "aarch64-linux-gnu-gcc"
        env_vars["CXX_aarch64_unknown_linux_gnu"] = "aarch64-linux-gnu-g++"
        env_vars["AR_aarch64_unknown_linux_gnu"] = "aarch64-linux-gnu-ar"
        env_vars["CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER"] = "aarch64-linux-gnu-gcc"
    return env_vars

def build_rust_modules(project: BuckyProject,rust_target: str):
    print(f"🚀 Building Rust code,target_dir is {project.rust_target_dir},target is {rust_target}")
    env = os.environ.copy()
    env.update(project.rust_env)

    env_vars = get_env_vars_by_target(rust_target)
    env.update(env_vars)
    
    cross_compile_env_vars = get_cross_compile_env_vars_by_target(rust_target)
    if cross_compile_env_vars:
        print("⚠️ cross compile enabled for target: ", rust_target)
        env.update(env_vars)
        print("* cargo build --release --target", rust_target, "--target-dir", project.rust_target_dir)
        subprocess.run(["cargo", "build", "--release", "--target", rust_target, "--target-dir", project.rust_target_dir], 
                    check=True, 
                    cwd=project.base_dir, 
                    env=env)
    else:
        print("* cargo build --release --target-dir", project.rust_target_dir)
        subprocess.run(["cargo", "build", "--release", "--target-dir", project.rust_target_dir], 
                    check=True, 
                    cwd=project.base_dir, 
                    env=env)

    print(f'✅ Build Rust Modules completed')

