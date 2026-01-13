
import os
import tempfile
import sys
import subprocess
import platform
import shutil
import re
from datetime import datetime
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

def _git_output(base_dir: str, args: list[str]) -> Optional[str]:
    if shutil.which("git") is None:
        return None
    result = subprocess.run(
        ["git", *args],
        cwd=base_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()

def get_build_metadata(base_dir: str) -> Dict[str, str]:
    now = datetime.utcnow()
    env = {
        "BUCKYOS_BUILD_DATE": now.strftime("%Y-%m-%d"),
        "BUCKYOS_BUILD_TIMESTAMP": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    in_repo = _git_output(base_dir, ["rev-parse", "--is-inside-work-tree"])
    if in_repo != "true":
        env.update({
            "BUCKYOS_GIT_COMMIT": "unknown",
            "BUCKYOS_GIT_BRANCH": "unknown",
            "BUCKYOS_GIT_DESCRIBE": "unknown",
            "BUCKYOS_GIT_DIRTY": "0",
        })
        return env

    env.update({
        "BUCKYOS_GIT_COMMIT": _git_output(base_dir, ["rev-parse", "--short=12", "HEAD"]) or "unknown",
        "BUCKYOS_GIT_BRANCH": _git_output(base_dir, ["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown",
        "BUCKYOS_GIT_DESCRIBE": _git_output(base_dir, ["describe", "--tags", "--always", "--dirty"]) or "unknown",
    })
    dirty = _git_output(base_dir, ["status", "--porcelain"])
    env["BUCKYOS_GIT_DIRTY"] = "1" if dirty else "0"
    return env

def _sanitize_version_token(value: str) -> str:
    token = re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip("-.")
    return token or "unknown"

def make_version_extend(build_env: Dict[str, str]) -> str:
    branch = build_env.get("BUCKYOS_GIT_BRANCH", "unknown")
    commit = build_env.get("BUCKYOS_GIT_COMMIT", "unknown")
    dirty = build_env.get("BUCKYOS_GIT_DIRTY", "0")

    parts = [branch, commit]
    if dirty == "1":
        parts.append("dirty")
    suffix = _sanitize_version_token(".".join(parts))
    return suffix

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

def get_host_target() -> str:
    """Get the Rust target triple for the current host"""
    machine = platform.machine().lower()
    system = platform.system().lower()
    
    # Normalize architecture names
    arch_map = {
        'x86_64': 'x86_64',
        'amd64': 'x86_64',
        'aarch64': 'aarch64',
        'arm64': 'aarch64',
        'armv7l': 'armv7',
    }
    arch = arch_map.get(machine, machine)
    
    # Map to Rust target triple
    if system == 'linux':
        if arch == 'x86_64':
            return 'x86_64-unknown-linux-gnu'
        elif arch == 'aarch64':
            return 'aarch64-unknown-linux-gnu'
        elif arch == 'armv7':
            return 'armv7-unknown-linux-gnueabihf'
    elif system == 'darwin':
        if arch == 'x86_64':
            return 'x86_64-apple-darwin'
        elif arch == 'aarch64':
            return 'aarch64-apple-darwin'
    elif system == 'windows':
        if arch == 'x86_64':
            return 'x86_64-pc-windows-msvc'
        elif arch == 'aarch64':
            return 'aarch64-pc-windows-msvc'
    
    # Fallback: return as-is
    return f'{arch}-unknown-{system}'

def parse_rust_target(target: str) -> tuple[str, str]:
    """Parse Rust target triple to extract arch and OS
    
    Returns:
        (arch, os) tuple, e.g., ('aarch64', 'linux'), ('x86_64', 'darwin')
    """
    parts = target.split('-')
    if len(parts) < 3:
        return ('unknown', 'unknown')
    
    arch = parts[0]
    
    # Extract OS from target triple
    if 'linux' in target:
        os_type = 'linux'
    elif 'darwin' in target or 'apple' in target:
        os_type = 'darwin'
    elif 'windows' in target:
        os_type = 'windows'
    else:
        os_type = parts[2] if len(parts) > 2 else 'unknown'
    
    return (arch, os_type)

def get_cross_compile_env_vars_by_target(target: str) -> Optional[Dict[str, str]]:
    """Get cross-compilation environment variables for the given Rust target
    
    Args:
        target: Rust target triple (e.g., 'aarch64-unknown-linux-gnu')
    
    Returns:
        Dictionary of environment variables if cross-compilation is needed, None otherwise
    """
    host_target = get_host_target()
    
    # If target matches host, no cross-compilation needed
    if target == host_target:
        return None
    
    host_arch, host_os = parse_rust_target(host_target)
    target_arch, target_os = parse_rust_target(target)
    
    # Special case: macOS supports building for both x86_64 and aarch64 natively
    if host_os == 'darwin' and target_os == 'darwin':
        # macOS can cross-compile between x86_64 and aarch64 without special tools
        return None
    
    # If OS differs, cross-compilation is complex and may not be supported
    if host_os != target_os:
        if host_os != 'darwin' and target_os != 'linux': # only support cross-OS compilation from darwin to linux
            print(f"⚠️ Cross-OS compilation from {host_os} to {target_os} detected.")
            print(f"   This may require Docker or other specialized tools.")
            return None
    
    # Same OS, different arch - set up cross-compilation toolchain
    print(f"* Cross-compilation from {host_arch}@{host_os} to {target_arch}@{target_os} detected.")
    env_vars = {}
    
    # Linux cross-compilation configurations
    if target_os == 'linux':
        if target_arch == 'aarch64' and host_arch == 'x86_64':
            # x86_64 -> aarch64 Linux
            env_vars["CC_aarch64_unknown_linux_gnu"] = "aarch64-linux-gnu-gcc"
            env_vars["CXX_aarch64_unknown_linux_gnu"] = "aarch64-linux-gnu-g++"
            env_vars["AR_aarch64_unknown_linux_gnu"] = "aarch64-linux-gnu-ar"
            env_vars["CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER"] = "aarch64-linux-gnu-gcc"
            
        elif target_arch == 'x86_64' and host_arch == 'aarch64':
            # aarch64 -> x86_64 Linux
            env_vars["CC_x86_64_unknown_linux_gnu"] = "x86_64-linux-gnu-gcc"
            env_vars["CXX_x86_64_unknown_linux_gnu"] = "x86_64-linux-gnu-g++"
            env_vars["AR_x86_64_unknown_linux_gnu"] = "x86_64-linux-gnu-ar"
            env_vars["CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER"] = "x86_64-linux-gnu-gcc"
            
        elif target_arch == 'armv7':
            # -> armv7 Linux
            env_vars["CC_armv7_unknown_linux_gnueabihf"] = "arm-linux-gnueabihf-gcc"
            env_vars["CXX_armv7_unknown_linux_gnueabihf"] = "arm-linux-gnueabihf-g++"
            env_vars["AR_armv7_unknown_linux_gnueabihf"] = "arm-linux-gnueabihf-ar"
            env_vars["CARGO_TARGET_ARMV7_UNKNOWN_LINUX_GNUEABIHF_LINKER"] = "arm-linux-gnueabihf-gcc"
        
        # Handle musl targets
        if 'musl' in target:
            if target_arch == 'x86_64':
                env_vars["CC_x86_64_unknown_linux_musl"] = "musl-gcc"
                env_vars["CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER"] = "musl-gcc"
            elif target_arch == 'aarch64':
                env_vars["CC_aarch64_unknown_linux_musl"] = "aarch64-linux-musl-gcc"
                env_vars["CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER"] = "aarch64-linux-musl-gcc"
    
    return env_vars

def build_rust_modules(project: BuckyProject,rust_target: str):
    print(f"🚀 Building Rust code,target_dir is {project.rust_target_dir},target is {rust_target}")
    env = os.environ.copy()
    build_env = get_build_metadata(str(project.base_dir))
    for key, value in build_env.items():
        env.setdefault(key, value)
    env.setdefault("VERSION", project.version)
    env.setdefault("VERSION_EXTEND", make_version_extend(build_env))
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

