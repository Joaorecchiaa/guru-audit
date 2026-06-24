import json
import os
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler

GURU_BASE_URL = "https://digitalmanager.guru/api/v2"

TOKENS = {
    "ba":    os.environ.get("GURU_TOKEN_BA", ""),
    "ibrem": os.environ.get("GURU_TOKEN_IBREM", ""),
}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        account  = params.get("account", ["ba"])[0].lower()
        token    = TOKENS.get(account, TOKENS["ba"])
        date_from = params.get("next_cycle_at_ini", [""])[0]
        date_to   = params.get("next_cycle_at_end", [""])[0]
        cursor    = params.get("cursor", [""])[0]
        status    = params.get("subscription_status", ["active"])[0]

        api_params = [
            ("subscription_status[]", status),
            ("next_cycle_at_ini", date_from),
            ("next_cycle_at_end", date_to),
            ("cursor", cursor),
        ]
        url = f"{GURU_BASE_URL}/subscriptions/?" + urllib.parse.urlencode(
            [(k, v) for k, v in api_params if v]
        )

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            if isinstance(data, list):
                items = data
                next_cursor = None
            elif "data" in data:
                items = data["data"]
                next_cursor = data.get("next_cursor") or None
            else:
                items = []
                next_cursor = None

            out = json.dumps({"items": items, "next_cursor": next_cursor})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(out.encode())

        except urllib.error.HTTPError as e:
            body = e.read().decode()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Guru API {e.code}: {body}"}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
