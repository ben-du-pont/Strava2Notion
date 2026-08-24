"""
One-off OAuth helper: mint a Strava refresh token with the scopes this repo needs.

The token created during initial setup only had activity:read_all, so the
description write-back in sync.py fails with 401/403. Run this once to
re-authorize with activity:write included, then the new refresh token is
written back into .env.

Usage:
    cd src && python strava_auth.py           # opens the browser, waits for callback
    cd src && python strava_auth.py --print   # don't touch .env, just print the token

Requires the Strava app's "Authorization Callback Domain" to be `localhost`
(https://www.strava.com/settings/api).
"""

import os
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(ENV_PATH)

SCOPES = "read,activity:read_all,activity:write"
PORT = 8721
REDIRECT_URI = f"http://localhost:{PORT}/exchange_token"

_result = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        _result.update({k: v[0] for k, v in params.items()})

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if "code" in _result:
            body = "<h2>Authorized.</h2><p>You can close this tab and go back to the terminal.</p>"
        else:
            body = f"<h2>Authorization failed.</h2><pre>{_result}</pre>"
        self.write_body(body)

    def write_body(self, body):
        self.wfile.write(f"<html><body style='font-family:sans-serif'>{body}</body></html>".encode())

    def log_message(self, *args):
        pass  # keep the terminal clean


def wait_for_code(client_id: str) -> str:
    auth_url = "https://www.strava.com/oauth/authorize?" + urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "force",
        "scope": SCOPES,
    })

    print("Opening Strava authorization page. Approve ALL requested boxes:\n")
    print(f"  {auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("127.0.0.1", PORT), _CallbackHandler)
    print(f"Waiting for the callback on {REDIRECT_URI} ...")
    while "code" not in _result and "error" not in _result:
        server.handle_request()
    server.server_close()

    if "error" in _result:
        sys.exit(f"Strava returned an error: {_result['error']}")
    return _result["code"]


def exchange(client_id: str, client_secret: str, code: str) -> dict:
    response = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    })
    if not response.ok:
        sys.exit(f"Token exchange failed ({response.status_code}): {response.text}")
    return response.json()


def write_refresh_token(token: str) -> None:
    with open(ENV_PATH) as f:
        content = f.read()

    line = f"STRAVA_REFRESH_TOKEN={token}"
    if re.search(r"^STRAVA_REFRESH_TOKEN=.*$", content, flags=re.MULTILINE):
        content = re.sub(r"^STRAVA_REFRESH_TOKEN=.*$", line, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{line}\n"

    with open(ENV_PATH, "w") as f:
        f.write(content)


def main():
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET missing from .env")

    code = wait_for_code(client_id)
    tokens = exchange(client_id, client_secret, code)

    # Strava reports the granted scopes on the redirect, not in the token response
    granted = _result.get("scope", "")
    refresh_token = tokens["refresh_token"]

    print(f"\nGranted scopes: {granted}")
    if "activity:write" not in granted:
        print("[WARN] activity:write was NOT granted — description write-back will still fail.")

    if "--print" in sys.argv:
        print(f"\nSTRAVA_REFRESH_TOKEN={refresh_token}")
    else:
        write_refresh_token(refresh_token)
        print(f"\n✓ STRAVA_REFRESH_TOKEN updated in {os.path.normpath(ENV_PATH)}")
        print("  Remember to update the GitHub Actions secret too:")
        print(f"  gh secret set STRAVA_REFRESH_TOKEN --body '{refresh_token}'")


if __name__ == "__main__":
    main()
