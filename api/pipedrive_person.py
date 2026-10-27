import json
import os
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler

PIPEDRIVE_BASE = "https://boardacademy.pipedrive.com/api/v1"
TOKEN = os.environ.get("PIPEDRIVE_TOKEN", "")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        query = params.get("q", [""])[0].strip()

        if not query:
            self._json(400, {"error": "Parâmetro 'q' obrigatório"})
            return

        if not TOKEN:
            self._json(500, {"error": "PIPEDRIVE_TOKEN não configurado"})
            return

        # Busca pelo termo (email ou telefone)
        url = f"{PIPEDRIVE_BASE}/persons/search?" + urllib.parse.urlencode({
            "term": query,
            "fields": "email,phone",
            "exact_match": "true",
            "limit": 1,
            "api_token": TOKEN,
        })

        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            items = data.get("data", {}).get("items", [])
            if items:
                person_id = items[0]["item"]["id"]
                self._json(200, {"id": person_id, "url": f"https://boardacademy.pipedrive.com/person/{person_id}"})
            else:
                # Tenta busca sem exact_match como fallback
                url2 = f"{PIPEDRIVE_BASE}/persons/search?" + urllib.parse.urlencode({
                    "term": query,
                    "fields": "email,phone",
                    "exact_match": "false",
                    "limit": 1,
                    "api_token": TOKEN,
                })
                with urllib.request.urlopen(url2, timeout=10) as resp2:
                    data2 = json.loads(resp2.read().decode())
                items2 = data2.get("data", {}).get("items", [])
                if items2:
                    person_id = items2[0]["item"]["id"]
                    self._json(200, {"id": person_id, "url": f"https://boardacademy.pipedrive.com/person/{person_id}"})
                else:
                    self._json(404, {"error": "Pessoa não encontrada"})

        except urllib.error.HTTPError as e:
            self._json(e.code, {"error": e.read().decode()})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, status, body):
        out = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(out)
