"""Launch the desktop client only. Start the API server as a separate process."""
import argparse
import os
import sys


def run(argv=None):
    parser = argparse.ArgumentParser(description="Accounting App desktop client")
    parser.add_argument("--api-url", default=None, help="Existing API server URL")
    args, qt_args = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    if args.api_url:
        os.environ["ACCOUNTING_APP_API_URL"] = args.api_url
    from client.desktop import main as run_desktop_client
    return run_desktop_client([sys.argv[0], *qt_args])


if __name__ == "__main__":
    raise SystemExit(run())
