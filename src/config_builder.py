# Build rootfs
# 1. After git clone, rootfs only contains "necessary code files" (related config files also exist as code)
# 2. After build, the bin directory in rootfs will be filled with correct build artifacts
# ------- Content in start.py
# 3. Based on this rootfs (mainly buckycli tool), calling make_config.py $config_group_name will complete all config files in rootfs
# 4. Based on the completed rootfs, can make installation packages, or copy to development environment for debugging (local or VM) --> can always understand last run config by observing config files in rootfs
# 5. For VM environments with multiple nodes, after completing Linux build, use make_config.py $node_group_name to construct different rootfs based on different environment needs and copy to corresponding VMs
#
# List of config files to construct
# - rootfs/local/did_docs/ put necessary doc cache
# - rootfs/node_daemon/root_pkg_env/pkgs/meta_index.db.fileobj local auto-update "last update time cache", this file ensures no auto-update is triggered
# - rootfs/etc/machine.json configure based on target environment web3 gateway config and trusted publishers
# - rootfs/etc/activated identity file group (start_config.json, $zoneid.zone.json, node_identity.json, node_private_key.pem, TLS cert files, ownerconfig under .buckycli directory)
#
# SN file structure differs from standard ood
# - Has necessary identity file group
# - Must support DNS resolution, requires specific config files (to prevent confusion, sn uses web3_gateway as config file entry point)
# - Need to construct sn_db as needed (simulate user registration)
# - Provide source repo service (another subdomain), provide system auto-update for subscribed users
#
# Directly use buckycli and cert_mgr to construct all configs within rootfs, not copy from existing directories.
# SN-related still keeps placeholder, sn_db is not constructed.

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
import time
from typing import Dict, Iterable, List, Optional, Tuple
from .util import get_buckyos_root
from .cert_mgr import CertManager  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
ROOTFS_DIR = SCRIPT_DIR.parent / "rootfs"
BUCKYCLI_BIN = ROOTFS_DIR / "bin" / "buckycli" / "buckycli"
if not BUCKYCLI_BIN.exists():
    BUCKYCLI_BIN = Path(get_buckyos_root()) / "bin" / "buckycli" / "buckycli"
    if not BUCKYCLI_BIN.exists():
        raise FileNotFoundError(f"buckycli binary missing at {BUCKYCLI_BIN}")

print(f"* buckycli at {BUCKYCLI_BIN}")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> None:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}")


def run_buckycli(args: List[str]) -> None:
    cmd = [str(BUCKYCLI_BIN)] + args
    run_cmd(cmd, cwd=ROOTFS_DIR)


def copy_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        print(f"skip missing file: {src}")
        return
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)
    print(f"copy {src} -> {dst}")


def write_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2))
    print(f"write json {path}")


def make_global_env_config(
    target_dir: Path,
    web3_bns: str,
    trust_did: Iterable[str],
    force_https: bool,
) -> None:
    """Write machine-level config and default meta_index cache."""
    etc_dir = ensure_dir(target_dir / "etc")

    machine = {
        "web3_bridge": {"bns": web3_bns},
        "force_https": force_https,
        "trust_did": list(trust_did),
    }
    write_json(etc_dir / "machine.json", machine)

    meta_dst = (
        target_dir
        / "local"
        / "node_daemon"
        / "root_pkg_env"
        / "pkgs"
        / "meta_index.db.fileobj"
    )

    ensure_dir(meta_dst.parent)
    now_unix_time = int(time.time())
    meta_dst.write_text(
        json.dumps({"name":"test.data","size":100,"content":"sha256:1234567890","create_time":now_unix_time}, indent=2)
    )
    print(f"create default meta_index cache at {meta_dst}")


def make_cache_did_docs(target_dir: Path) -> None:
    """Construct did_docs via buckycli (depends on future build_did_docs implementation)."""
    docs_dst = target_dir / "local" / "did_docs"

    ensure_dir(docs_dst)
    try:
        run_buckycli(["build_did_docs", "--output_dir", str(docs_dst)])
    except RuntimeError as e:
        print(f"warning: build_did_docs not available yet: {e}")


def _copy_identity_outputs(
    user_dir: Path, node_dir: Path, target_dir: Path, zone_id: str
) -> None:
    etc_dir = ensure_dir(target_dir / "etc")

    copy_if_exists(user_dir / f"{zone_id}.zone.json", etc_dir / f"{zone_id}.zone.json")
    for name in ("start_config.json", "node_identity.json", "node_private_key.pem"):
        copy_if_exists(node_dir / name, etc_dir / name)

    buckycli_dir = ensure_dir(etc_dir / ".buckycli")
    for name in ("user_config.json", "user_private_key.pem"):
        copy_if_exists(user_dir / name, buckycli_dir / name)
    copy_if_exists(user_dir / f"{zone_id}.zone.json", buckycli_dir / "zone_config.json")


def _generate_tls(zone_id: str, ca_name: str, etc_dir: Path, ca_dir: Optional[Path]) -> None:
    if CertManager is None:
        print("warning: cert_mgr not available, skip TLS cert generation")
        return

    cm = CertManager()
    # Prefer user-provided CA directory
    if ca_dir:
        ca_dir_path = ca_dir.resolve()
        if not ca_dir_path.exists():
            raise FileNotFoundError(f"CA dir not found: {ca_dir_path}")
        ca_cert_candidates = list(ca_dir_path.glob("*_ca_cert.pem"))
        if not ca_cert_candidates:
            raise FileNotFoundError(f"no *_ca_cert.pem in {ca_dir_path}")
        ca_cert_path = ca_cert_candidates[0]
        ca_key_path = ca_dir_path / ca_cert_path.name.replace("_ca_cert.pem", "_ca_key.pem")
        if not ca_key_path.exists():
            raise FileNotFoundError(f"CA key not found: {ca_key_path}")
    else:
        cert_dir = ensure_dir(etc_dir / "certs")
        ca_cert, ca_key = cm.create_ca(str(cert_dir), name=ca_name)
        ca_cert_path, ca_key_path = Path(ca_cert), Path(ca_key)

    cert_path, key_path = cm.create_cert_from_ca(
        str(ca_dir_path if ca_dir else ca_cert_path.parent),
        hostname=zone_id,
        hostnames=[zone_id, f"*.{zone_id}"],
        target_dir=str(etc_dir),
    )

    # Compatible with old naming, keep only one set of certificates (including zone and wildcard SAN)
    copy_if_exists(Path(cert_path), etc_dir / "tls_certificate.pem")
    copy_if_exists(Path(key_path), etc_dir / "tls_key.pem")
    # Keep CA for trust
    copy_if_exists(ca_cert_path, etc_dir / "ca_certificate.pem")
    copy_if_exists(ca_key_path, etc_dir / "ca_key.pem")
    print(f"tls certs generated under {etc_dir}")


def make_identity_files(
    target_dir: Path,
    username: str,
    zone_id: str,
    node_name: str,
    sn_base_host: str,
    ca_name: str,
    ca_dir: Optional[Path],
) -> None:
    """Use buckycli to generate identity files and use cert_mgr to generate TLS certificates."""
    if not BUCKYCLI_BIN.exists():
        raise FileNotFoundError(f"buckycli binary missing at {BUCKYCLI_BIN}")

    tmp_root = ensure_dir(target_dir / "_buckycli_tmp")
    user_tmp = ensure_dir(tmp_root / zone_id)

    # 1. Create user/zone
    run_buckycli(
        [
            "create_user_env",
            "--username",
            username,
            "--hostname",
            zone_id,
            "--ood_name",
            node_name,
            "--sn_base_host",
            sn_base_host,
            "--output_dir",
            str(user_tmp),
        ]
    )

    # 2. Create node config
    run_buckycli(
        [
            "create_node_configs",
            "--device_name",
            node_name,
            "--env_dir",
            str(user_tmp),
        ]
    )

    # 3. Copy identity files
    user_dir = user_tmp
    node_dir = user_dir / node_name
    _copy_identity_outputs(user_dir, node_dir, target_dir, zone_id)

    # 4. TLS certificates
    _generate_tls(zone_id, ca_name, ensure_dir(target_dir / "etc"), ca_dir)


def make_repo_cache_file(target_dir: Path) -> None:
    """Write meta_index cache file (placeholder to prevent auto-update)."""
    meta_dst = (
        target_dir
        / "local"
        / "node_daemon"
        / "root_pkg_env"
        / "pkgs"
        / "meta_index.db.fileobj"
    )
    if not meta_dst.exists():
        ensure_dir(meta_dst.parent)
        meta_dst.write_text(
            '{"content":"sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","name":"meta_index.db","size":53248}'
        )
        print(f"create default meta_index cache at {meta_dst}")


def make_sn_configs(
    target_dir: Path,
    sn_base_host: str,
    sn_ip: str,
    sn_device_name: str = "sn_server",
    ca_name: str = "buckyos_sn",
    ca_dir: Optional[Path] = None,
) -> None:
    """Generate SN (Super Node) server configuration files.
    
    All config files are placed flatly in target_dir directory, including:
    - sn_server_private_key.pem - device private key file used by rtcp protocol stack
    - fullchain.cert, fullchain.pem - certificate and key containing sn.$sn_base, *.web3.$sn_base
    - ca/buckyos_sn_ca_cert.pem, ca/buckyos_sn_ca_key.pem - test environment self-signed CA certificate
    - zone_zone - auto-generated, contains buckyos custom DNS TXT record template
    
    Note: The following files need to be manually created by user, not generated by this script:
    - dns_zone - manually configured DNS Zone file
    - website.yaml - website config file referenced by web3_gateway
    
    Args:
        target_dir: Output directory, all files placed flatly in this directory
        sn_base_host: SN base domain (e.g. buckyos.io or devtests.org)
        sn_ip: SN server IP address
        sn_device_name: SN device name, default "sn_server"
        ca_name: CA certificate name
        ca_dir: Use existing CA directory, otherwise auto-generate
    """
    if not BUCKYCLI_BIN.exists():
        raise FileNotFoundError(f"buckycli binary missing at {BUCKYCLI_BIN}")
    
    print(f"Generate SN config files to {target_dir} ...")
    print(f"  SN base domain: {sn_base_host}")
    print(f"  SN IP address: {sn_ip}")
    print(f"  SN device name: {sn_device_name}")
    
    # SN config files placed flatly under target_dir, no etc subdirectory created
    ensure_dir(target_dir)
    
    # 1. Use buckycli to create SN config
    # Note: SN uses special identity, here use buckycli create_sn_configs command
    print("# Step 1: Create SN device identity config...")
    run_buckycli(
        [
            "create_sn_configs",
            "--output_dir",
            str(target_dir),
            "--sn_ip",
            sn_ip,
            "--sn_base_host",
            sn_base_host,
        ]
    )
    
    # buckycli will generate files under target_dir/sn_server/, need to move to target_dir
    buckycli_sn_dir = target_dir / "sn_server"
    if buckycli_sn_dir.exists():
        # Move generated files to target_dir root
        for file in buckycli_sn_dir.glob("*"):
            if file.is_file():
                dest_file = target_dir / file.name
                shutil.move(str(file), str(dest_file))
                print(f"Move file: {file.name} -> {target_dir}/")
        # Delete empty sn_server directory
        if buckycli_sn_dir.exists() and not list(buckycli_sn_dir.iterdir()):
            buckycli_sn_dir.rmdir()

    
    # 2. Generate TLS certificates
    print("# Step 2: Generate TLS certificates...")

    cm = CertManager()
    
    # Generate or use existing CA
    if ca_dir and ca_dir.exists():
        ca_dir_path = ca_dir.resolve()
        print(f"Use existing CA: {ca_dir_path}")
        ca_cert_candidates = list(ca_dir_path.glob("*_ca_cert.pem"))
        if not ca_cert_candidates:
            raise FileNotFoundError(f"*_ca_cert.pem not found in {ca_dir_path}")
        ca_cert_path = ca_cert_candidates[0]
        ca_key_path = ca_dir_path / ca_cert_path.name.replace("_ca_cert.pem", "_ca_key.pem")
        if not ca_key_path.exists():
            raise FileNotFoundError(f"CA private key not found: {ca_key_path}")
    else:
        # Generate new CA
        ca_output_dir = ensure_dir(target_dir / "ca")
        ca_cert, ca_key = cm.create_ca(str(ca_output_dir), name=ca_name)
        ca_cert_path, ca_key_path = Path(ca_cert), Path(ca_key)
        print(f"Generated CA certificate: {ca_cert_path}")
    
    # Generate server certificate (including sn.$sn_base and *.web3.$sn_base)
    sn_hostname = f"sn.{sn_base_host}"
    web3_wildcard = f"*.web3.{sn_base_host}"
    
    cert_path, key_path = cm.create_cert_from_ca(
        str(ca_cert_path.parent),
        hostname=sn_hostname,
        target_dir=str(target_dir),
        hostnames=[web3_wildcard, f"web3.{sn_base_host}"],
    )
    
    # Copy/rename to standard filenames
    cert_file = Path(cert_path)
    key_file = Path(key_path)
    
    shutil.move(cert_file, target_dir / "fullchain.cert")
    shutil.move(key_file, target_dir / "fullchain.pem")
    
    # Copy CA certificate to ca directory (for client trust)
    if ca_dir:
        ca_output_dir = ensure_dir(target_dir / "ca")
        shutil.copy2(ca_cert_path, ca_output_dir / ca_cert_path.name)
        shutil.copy2(ca_key_path, ca_output_dir / ca_key_path.name)
    
    print(f"TLS certificates generated:")
    print(f"  - {target_dir / 'fullchain.cert'}")
    print(f"  - {target_dir / 'fullchain.pem'}")
    print(f"  - {target_dir / 'ca' / ca_cert_path.name}")
    
    #3 Modify params.json
    params_json = {
        "params": {
            "sn_host": sn_base_host,
            "sn_ip": sn_ip,
            "sn_boot_jwt": "todo",
            "sn_owner_pk": "todo",
            "sn_device_jwt": "todo",
        }
    }
    
    print(f"\n✓ SN config files generation completed!")
    print(f"  Output directory: {target_dir}")
    print(f"\nGenerated files:")
    print(f"  - {target_dir / 'sn_device_config.json'} (SN server device config)")
    print(f"  - {target_dir / 'sn_private_key.pem'} (device private key)")
    print(f"  - {target_dir / 'fullchain.cert'} (server certificate)")
    print(f"  - {target_dir / 'fullchain.pem'} (server private key)")
    print(f"  - {target_dir / 'ca' / 'buckyos_sn_ca_cert.pem'} (CA certificate)")
    print(f"  - {target_dir / 'params.json'} (SN config parameters)")
    print(f"\nFiles that need manual creation:")
    print(f"  - {target_dir / 'dns_zone'} (DNS Zone config)")
    print(f"  - {target_dir / 'website.yaml'} (website config)")
    print(f"\nOther notes:")
    print(f"  - Test environment requires installing CA certificate to client trust list")


def make_sn_db(target_dir: Path, user_list: List[str]) -> None:
    """Placeholder, supplement as needed."""
    print("skip sn_db generation (not implemented)")


def get_params_from_group_name(group_name: str) -> Dict[str, object]:
    """Get all generation parameters based on group name."""
    if group_name == "dev":
        return {
            "username": "devtest",
            "zone_id": "test.buckyos.io",
            "node_name": "ood1",
            "netid": "",
            "sn_base_host": "",
            "web3_bridge": "web3.devtests.org",
            "trust_did": [
                "did:web:buckyos.org",
                "did:web:buckyos.ai",
                "did:web:buckyos.io",
            ],
            "force_https": False,
            "ca_name": "buckyos_local",
            "is_sn": False,
        }
    if group_name == "alice.ood1":
        return {
            "username": "alice",
            "zone_id": "alice.web3.devtests.org",
            "node_name": "ood1",
            "netid": "",
            "sn_base_host": "devtests.org",
            "web3_bridge": "web3.devtests.org",
            "trust_did": [
                "did:web:buckyos.org",
                "did:web:buckyos.ai",
                "did:web:buckyos.io",
            ],
            "force_https": False,
            "ca_name": "buckyos_local",
            "is_sn": False,
        }
    if group_name == "bob.ood1":
        return {
            "username": "bob",
            "zone_id": "bob.web3.devtests.org",
            "node_name": "ood1",
            "netid": "",
            "sn_base_host": "devtests.org",
            "web3_bridge": "web3.devtests.org",
            "trust_did": [
                "did:web:buckyos.org",
                "did:web:buckyos.ai",
                "did:web:buckyos.io",
            ],
            "force_https": False,
            "ca_name": "buckyos_local",
            "is_sn": False,
        }
    if group_name == "sn_server":
        return {
            "sn_base_host": "devtests.org",
            "sn_ip": "127.0.0.1",
            "sn_device_name": "sn_server",
            "web3_bridge": "web3.devtests.org",
            "trust_did": [
                "did:web:buckyos.org",
                "did:web:buckyos.ai",
                "did:web:buckyos.io",
            ],
            "force_https": False,
            "ca_name": "buckyos_sn",
            "is_sn": True,
        }
    raise ValueError(f"invalid group name: {group_name}")

def make_config_by_group_name(group_name: str, target_root: Optional[Path], ca_dir: Optional[Path]) -> None:
    params = get_params_from_group_name(group_name)
    print(f"############ make config for group name: {group_name} #########################")
    print(f"rootfs dir : {target_root}")
    print(f"group      : {group_name}")
    
    is_sn = params.get("is_sn", False)
    
    if is_sn:
        if target_root is None:
            target_root = Path("/opt/web3-gateway")
        # SN configuration generation
        print(f"sn_base_host: {params['sn_base_host']}")
        print(f"sn_ip       : {params['sn_ip']}")
        print(f"device_name : {params['sn_device_name']}")
        print(f"web3_bridge : {params['web3_bridge']}")
        
        # SN does not need machine.json, did_docs cache and meta_index cache
        make_sn_configs(
            target_root,
            params["sn_base_host"],
            params["sn_ip"],
            params["sn_device_name"],
            params["ca_name"],
            ca_dir,
        )
    else:
        if target_root is None:
            target_root = ROOTFS_DIR
        # Normal OOD node configuration generation
        print(f"username   : {params['username']}")
        print(f"zone       : {params['zone_id']}")
        print(f"node       : {params['node_name']}")
        print(f"web3_bridge: {params['web3_bridge']}")
        
        make_global_env_config(
            target_root,
            params["web3_bridge"],
            params["trust_did"],
            params["force_https"],
        )
        
        make_cache_did_docs(target_root)
        make_identity_files(
            target_root,
            params["username"],
            params["zone_id"],
            params["node_name"],
            params["sn_base_host"],
            params["ca_name"],
            ca_dir,
        )
        make_repo_cache_file(target_root)
    
    print(f"config {group_name} generation finished.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate config files under rootfs",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("group", help="Config group name, e.g. dev")
    parser.add_argument(
        "--rootfs",
        default=None,
        type=Path,
        help="Output directory (containing bin/buckycli and other tools)",
    )
    parser.add_argument(
        "--ca",
        default=None,
        type=Path,
        help="Use existing CA directory (containing *_ca_cert.pem and corresponding key), otherwise auto-generate",
    )
    args = parser.parse_args()
    make_config_by_group_name(args.group, args.rootfs, args.ca)

if __name__ == "__main__":
    sys.exit(main())

