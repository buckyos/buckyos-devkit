import argparse
import json
import os
from pathlib import Path
import sys

from .worksapce import Workspace


def build_parser() -> argparse.ArgumentParser:
    """Build an argparse parser with modular subcommands."""
    parser = argparse.ArgumentParser(
        description="Manage remote VMs and apps for a workspace group."
    )
    parser.add_argument("group_name", help="Workspace group name.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    clean_parser = subparsers.add_parser(
        "clean_vms", help="Remove all Multipass instances for this group."
    )
    clean_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts (behavior depends on implementation).",
    )
    clean_parser.set_defaults(handler=handle_clean_vms)

    create_parser = subparsers.add_parser(
        "create_vms", help="Create VMs from workspace configuration."
    )
    create_parser.set_defaults(handler=handle_create_vms)

    snapshot_parser = subparsers.add_parser(
        "snapshot", help="Create snapshots for all VMs."
    )
    snapshot_parser.add_argument("snapshot_name", help="Snapshot name.")
    snapshot_parser.set_defaults(handler=handle_snapshot)

    restore_parser = subparsers.add_parser(
        "restore", help="Restore snapshots for all VMs."
    )
    restore_parser.add_argument("snapshot_name", help="Snapshot name.")
    restore_parser.set_defaults(handler=handle_restore)

    info_parser = subparsers.add_parser(
        "info_vms", help="Show VM status information."
    )
    info_parser.set_defaults(handler=handle_info_vms)

    start_vms_parser = subparsers.add_parser(
        "start_vms", help="Start all Multipass instances for this group."
    )
    start_vms_parser.set_defaults(handler=handle_start_vms)

    stop_vms_parser = subparsers.add_parser(
        "stop_vms", help="Stop all Multipass instances for this group."
    )
    stop_vms_parser.set_defaults(handler=handle_stop_vms)

    install_parser = subparsers.add_parser(
        "install", help="Install apps to a device based on configuration."
    )
    install_parser.add_argument(
        "device_id",
        nargs="?",
        default=None,
        help="Target device id; omit to install to all devices.",
    )
    install_parser.add_argument(
        "--apps",
        nargs="+",
        help="Specify app names to install; defaults to all configured apps.",
    )
    install_parser.set_defaults(handler=handle_install)

    update_parser = subparsers.add_parser(
        "update", help="Update apps on a device based on configuration."
    )
    update_parser.add_argument(
        "device_id",
        nargs="?",
        default=None,
        help="Target device id; omit to update all devices.",
    )
    update_parser.add_argument(
        "--apps",
        nargs="+",
        help="Specify app names to update; defaults to all configured apps.",
    )
    update_parser.set_defaults(handler=handle_update)

    start_parser = subparsers.add_parser(
        "start", help="Start buckyos on all VMs (SN not started)."
    )
    start_parser.add_argument(
        "device_id",
        nargs="?",
        default=None,
        help="Target device id; omit to start all devices.",
    )
    start_parser.add_argument(
        "--apps",
        nargs="+",
        help="Specify app names to start; defaults to all configured apps.",
    )
    start_parser.set_defaults(handler=handle_start)

    stop_parser = subparsers.add_parser(
        "stop", help="Stop buckyos on all VMs."
    )
    stop_parser.set_defaults(handler=handle_stop)

    clog_parser = subparsers.add_parser(
        "clog", help="Collect logs from nodes."
    )
    clog_parser.set_defaults(handler=handle_clog)

    run_parser = subparsers.add_parser(
        "run", help="Execute commands on a specific node."
    )
    run_parser.add_argument("node_id", help="Target node id.")
    run_parser.add_argument(
        "cmds",
        nargs="+",
        help="Command(s) to execute; provide multiple to run sequentially.",
    )
    run_parser.set_defaults(handler=handle_run)

    exec_parser = subparsers.add_parser(
        "exec", help="Execute app command on a device."
    )
    exec_parser.add_argument(
        "app_cmd",
        help="App and command in format 'appname.cmdname' (e.g., 'buckyos.build_all')."
    )
    exec_parser.add_argument(
        "--device",
        dest="device_id",
        default=None,
        help="Target device id; omit to use default device."
    )
    exec_parser.add_argument(
        "params",
        nargs="*",
        help="Additional parameters to pass to the command."
    )
    exec_parser.set_defaults(handler=handle_exec_app)

    return parser


def build_workspace(group_name: str) -> Workspace:
    """Create and load a workspace instance."""
    workspace_dir = os.path.join(os.getcwd(), "dev_configs")
    print(f"load workspace from {workspace_dir}/{group_name}.json ...")
    workspace = Workspace(group_name, Path(workspace_dir))
    workspace.load()
    return workspace


def handle_clean_vms(workspace: Workspace, args: argparse.Namespace) -> None:
    workspace.clean_vms()


def handle_create_vms(workspace: Workspace, args: argparse.Namespace) -> None:
    workspace.create_vms()


def handle_snapshot(workspace: Workspace, args: argparse.Namespace) -> None:
    workspace.snapshot(args.snapshot_name)


def handle_restore(workspace: Workspace, args: argparse.Namespace) -> None:
    workspace.restore(args.snapshot_name)


def handle_info_vms(workspace: Workspace, args: argparse.Namespace) -> None:
    info = workspace.info_vms()
    if info is not None:
        print(json.dumps(info, indent=2, ensure_ascii=False))


def handle_start_vms(workspace: Workspace, args: argparse.Namespace) -> None:
    workspace.start_vms()


def handle_stop_vms(workspace: Workspace, args: argparse.Namespace) -> None:
    workspace.stop_vms()


def handle_install(workspace: Workspace, args: argparse.Namespace) -> None:
    print(f"install apps to device: {args.device_id} with apps: {args.apps}")
    if args.device_id is None:
        for device_id in workspace.remote_devices.keys():
            workspace.install(device_id, args.apps)
        return
    else:
        workspace.install(args.device_id, args.apps)


def handle_update(workspace: Workspace, args: argparse.Namespace) -> None:
    print(f"update apps on device: {args.device_id} with apps: {args.apps}")
    if args.device_id is None:
        for device_id in workspace.remote_devices.keys():
            workspace.update(device_id, args.apps)
        return
    workspace.update(args.device_id, args.apps)

def handle_start(workspace: Workspace, args: argparse.Namespace) -> None:
    print(f"start apps on device: {args.device_id} with apps: {args.apps}")
    if args.device_id is None:
        for device_id in workspace.remote_devices.keys():
            workspace.start(device_id, args.apps)
        return
    workspace.start(args.device_id, args.apps)

def handle_exec_app(workspace: Workspace, args: argparse.Namespace) -> None:
    """
    Execute an app command on a device or all devices.
    
    Command format: exec appname.cmdname [--device=device_id] [params...]
    Example: exec buckyos.build_all --device=bob-ood1
    If --device is not specified, the command will be executed on all devices.
    """
    # Parse appname.cmdname format
    if "." not in args.app_cmd:
        print(f"Error: Invalid format. Expected 'appname.cmdname', got '{args.app_cmd}'")
        print("Example: buckyos.build_all")
        return
    
    app_name, cmd_name = args.app_cmd.split(".", 1)
    device_id = args.device_id
    
    # Determine target devices
    if device_id is None:
        # Execute on all devices
        target_devices = list(workspace.remote_devices.keys())
        if not target_devices:
            print("Error: No devices available in workspace.")
            return
        print(f"Executing app command: {app_name}.{cmd_name} on all devices: {target_devices}")
    else:
        # Validate device_id
        if device_id not in workspace.remote_devices:
            print(f"Error: Device '{device_id}' not found in workspace.")
            print(f"Available devices: {list(workspace.remote_devices.keys())}")
            return
        target_devices = [device_id]
        print(f"Executing app command: {app_name}.{cmd_name} on device: {device_id}")
    
    if args.params:
        print(f"Command parameters: {args.params}")
        # Note: Additional params are captured but not directly passed to execute_app_command
        # They could be used via environment variables in command templates if needed
    
    # Execute the command on each target device
    for target_device_id in target_devices:
        try:
            print(f"\n--- Executing on device: {target_device_id} ---")
            workspace.execute_app_command(target_device_id, app_name, cmd_name, run_in_host=False)
        except ValueError as e:
            print(f"Error on device {target_device_id}: {e}")
            continue
        except Exception as e:
            print(f"Unexpected error on device {target_device_id}: {e}")
            import traceback
            traceback.print_exc()
            continue





def handle_stop(workspace: Workspace, args: argparse.Namespace) -> None:
    workspace.stop()


def handle_clog(workspace: Workspace, args: argparse.Namespace) -> None:
    workspace.clog()


def handle_run(workspace: Workspace, args: argparse.Namespace) -> None:
    workspace.run(args.node_id, args.cmds)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    workspace = build_workspace(args.group_name)
    #workspace.execute_app_command("bob-ood1", "buckyos", "build_all",True)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1

    handler(workspace, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())