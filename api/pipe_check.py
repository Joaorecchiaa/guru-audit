import json
import os
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler

PIPEDRIVE_BASE = "https://api.pipedrive.com/v1"
TOKEN = os.environ.get("PIPEDRIVE_TOKEN", "")
FENIX_PIPELINE_ID = 42

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        emails_raw = params.get("emails", [""])[0].strip()

        if not emails_raw:
            self._json(400, {"error": "Parâmetro 'emails' obrigatório"})
            return
        if not TOKEN:
            self._json(500, {"error": "PIPEDRIVE_TOKEN não configurado"})
            return

        emails = [e.strip().lower() for e in emails_raw.split(",") if e.strip()]

        found = []
        not_found = []

        for email in emails:
            person = self._find_person_by_email(email)
            if not person:
                not_found.append({"email": email, "reason": "Pessoa não encontrada no Pipedrive"})
                continue

            person_id = person["id"]
            person_name = person.get("name", "—")
            person_phone = ""
            phones = person.get("phone", [])
            if phones:
                person_phone = phones[0].get("value", "")

            deals = self._get_open_deals_fenix(person_id)
            if not deals:
                not_found.append({
                    "email": email,
                    "person_name": person_name,
                    "person_id": person_id,
                    "person_phone": person_phone,
                    "reason": "Pessoa encontrada mas sem deals abertos no FENIX"
                })
            else:
                for deal in deals:
                    found.append({
                        "email": email,
                        "person_name": person_name,
                        "person_id": person_id,
                        "person_phone": person_phone,
                        "deal_id": deal["id"],
                        "deal_title": deal.get("title", "—"),
                        "deal_stage": deal.get("stage_id", "—"),
                        "deal_stage_name": deal.get("stage_order_nr", "—"),
                        "deal_value": deal.get("value", 0),
                        "deal_owner": deal.get("owner_name", "—"),
                        "deal_updated": deal.get("update_time", "—"),
                        "deal_url": f"https://boardacademy.pipedrive.com/deal/{deal['id']}",
                        "person_url": f"https://boardacademy.pipedrive.com/person/{person_id}",
                    })

        self._json(200, {"found": found, "not_found": not_found, "total": len(emails)})

    def _find_person_by_email(self, email):
        url = f"{PIPEDRIVE_BASE}/persons/search?" + urllib.parse.urlencode({
            "term": email,
            "fields": "email",
            "exact_match": "true",
            "limit": 1,
            "api_token": TOKEN,
        })
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            items = data.get("data", {}).get("items", [])
            if items:
                return items[0]["item"]
        except:
            pass
        return None

    def _get_open_deals_fenix(self, person_id):
        url = f"{PIPEDRIVE_BASE}/persons/{person_id}/deals?" + urllib.parse.urlencode({
            "status": "open",
            "api_token": TOKEN,
            "limit": 50,
        })
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            deals = data.get("data") or []
            # Filtra só funil FENIX (id 42)
            return [d for d in deals if d.get("pipeline_id") == FENIX_PIPELINE_ID]
        except:
            return []

    def _json(self, status, body):
        out = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(out)
