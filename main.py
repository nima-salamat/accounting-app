"""API server launcher and lifecycle manager for the desktop application."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parent


def _reserve_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(process, base_url, timeout_seconds=30):
    deadline = time.monotonic() + timeout_seconds
    health_url = base_url.rstrip("/") + "/health"
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "سرور حسابداری پیش از آماده‌شدن متوقف شد (exit code {}).".format(process.returncode)
            )
        try:
            with urlopen(health_url, timeout=0.75) as response:
                if response.status == 200:
                    return
        except (URLError, OSError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(
        "سرور حسابداری در {} ثانیه آماده نشد. {}".format(timeout_seconds, last_error or "")
    )


def _start_local_server():
    port = _reserve_loopback_port()
    base_url = "http://127.0.0.1:{}".format(port)
    env = os.environ.copy()
    env.pop("ACCOUNTING_APP_API_URL", None)
    env["PYTHONUNBUFFERED"] = "1"
    kwargs = {
        "cwd": str(PROJECT_ROOT),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, "-m", "server", "--host", "127.0.0.1", "--port", str(port)],
        **kwargs
    )
    try:
        _wait_for_server(process, base_url)
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        raise
    return process, base_url


def _stop_local_server(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def run(argv=None):
    parser = argparse.ArgumentParser(description="Accounting App API-backed desktop client")
    parser.add_argument("--api-url", default=None, help="Existing API server URL; remote servers must use HTTPS.")
    args, _unknown = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    configured_url = args.api_url or os.environ.get("ACCOUNTING_APP_API_URL")
    local_process = None
    if configured_url:
        os.environ["ACCOUNTING_APP_API_URL"] = configured_url
    else:
        local_process, configured_url = _start_local_server()
        os.environ["ACCOUNTING_APP_API_URL"] = configured_url
    try:
        from client.desktop import main as run_desktop_client
        return run_desktop_client([sys.argv[0]])
    finally:
        if local_process is not None:
            _stop_local_server(local_process)


if __name__ == "__main__":
    raise SystemExit(run())
