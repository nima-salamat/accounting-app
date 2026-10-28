"""Launch the API-only desktop client; the server is started separately."""
import argparse
import os
import sys

from client.desktop import main as run_desktop_client


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Accounting App desktop client")
    parser.add_argument("--api-url", default=None, help="Existing API server URL")
    options, qt_arguments = parser.parse_known_args(arguments)
    if options.api_url:
        os.environ["ACCOUNTING_APP_API_URL"] = options.api_url
    return run_desktop_client([sys.argv[0], *qt_arguments])


if __name__ == "__main__":
    raise SystemExit(main())
