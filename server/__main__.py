"""Run the API server with an explicit, safe default bind address."""
import argparse
import os
import ipaddress

import uvicorn


def _validate_bind(host):
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = host.lower() == "localhost"
    if not is_loopback:
        secret = os.environ.get("ACCOUNTING_APP_SECRET_KEY", "")
        if len(secret) < 32:
            raise SystemExit(
                "Remote binds require ACCOUNTING_APP_SECRET_KEY with at least 32 characters."
            )


def main():
    parser = argparse.ArgumentParser(description="Accounting App API server")
    parser.add_argument("--host", default=os.environ.get("ACCOUNTING_APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ACCOUNTING_APP_PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="Development only")
    args = parser.parse_args()
    _validate_bind(args.host)
    uvicorn.run("server.app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
