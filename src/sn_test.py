import argparse
import os
import re
import shutil
import socket
import subprocess
from typing import Optional, Sequence, Tuple


DEFAULT_DNS_SERVER = "207.246.96.13"
DEFAULT_PORT_HOST = "207.246.96.13"


def _format_command(cmd: Sequence[str]) -> str:
    return " ".join(cmd)


def _run_command(cmd: Sequence[str], input_text: Optional[str] = None) -> Tuple[int, str]:
    try:
        result = subprocess.run(
            list(cmd),
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, str(exc)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def check_dig(label: str, cmd: Sequence[str], expect_regex: str) -> bool:
    print("")
    print(f"== {label}")
    print(f"$ {_format_command(cmd)}")
    code, output = _run_command(cmd)
    ok = code == 0 and output and re.search(expect_regex, output)
    if ok:
        print(f"✓ {label}")
        return True
    print(f"✗ {label}")
    print(output)
    return False


def check_port(label: str, host: str, port: int, timeout_sec: float = 2.0) -> bool:
    print("")
    print(f"== {label}")
    print(f"$ connect {host}:{port} (timeout {timeout_sec}s)")
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            print(f"✓ {label}")
            return True
    except OSError as exc:
        print(f"✗ {label}")
        print(str(exc))
        return False


def check_cert(label: str, host: str, port: int, verbose: bool) -> bool:
    cmd = [
        "openssl",
        "s_client",
        "-connect",
        f"{host}:{port}",
        "-servername",
        host,
        "-tls1_2",
        "-showcerts",
    ]
    print("")
    print(f"== {label}")
    print(f"$ {_format_command(cmd)}")
    code, output = _run_command(cmd, input_text="")
    cert_count = len(re.findall(r"BEGIN CERTIFICATE", output))
    verify_ok = "Verify return code: 0 (ok)" in output

    if code == 0 and cert_count >= 2 and verify_ok:
        print(f"✓ {label}")
        return True

    print(f"✗ {label}")
    print(f"cert_count={cert_count} verify_ok={'ok' if verify_ok else ''}")
    if verbose:
        print(output)
    return False


def main() -> None:
    example_text = (
        "examples:\n"
        "  buckyos-sn-test\n"
        "  buckyos-sn-test --dns-server 207.246.96.13 --port-host 207.246.96.13\n"
        "  VERBOSE=1 buckyos-sn-test\n"
        "  DNS_SERVER=8.8.8.8 PORT_HOST=207.246.96.13 buckyos-sn-test\n"
    )
    parser = argparse.ArgumentParser(
        description="Test SN service DNS, port, and TLS certificate.",
        epilog=example_text,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dns-server",
        default=os.environ.get("DNS_SERVER", DEFAULT_DNS_SERVER),
        help="DNS server IP for dig checks.",
    )
    parser.add_argument(
        "--port-host",
        default=os.environ.get("PORT_HOST", DEFAULT_PORT_HOST),
        help="Host IP used for port connectivity check.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=os.environ.get("VERBOSE", "0") == "1",
        help="Print full openssl output on certificate failure.",
    )
    args = parser.parse_args()

    if shutil.which("dig") is None:
        print("Warning: dig not found in PATH. DNS checks will fail.")
    if shutil.which("openssl") is None:
        print("Warning: openssl not found in PATH. Certificate check will fail.")

    check_dig(
        "指定sn IP dig",
        ["dig", f"@{args.dns_server}", "sn.buckyos.ai"],
        r"ANSWER SECTION",
    )
    check_dig(
        "local dns dig txt",
        ["dig", f"@{args.dns_server}", "-t", "A", "test-addr.web3.buckyos.ai"],
        r"ANSWER SECTION",
    )
    check_dig(
        "ns dig web3.buckyos.ai",
        ["dig", "-t", "NS", "web3.buckyos.ai"],
        r"status: NOERROR",
    )
    check_port("port 2980 open", args.port_host, 2980)
    check_cert("sn.buckyos.ai cert fullchain valid", "sn.buckyos.ai", 443, args.verbose)


if __name__ == "__main__":
    main()
