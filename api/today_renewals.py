import json
import os
import urllib.request
import urllib.parse
import urllib.error
from datetime import date
from http.server import BaseHTTPRequestHandler

GURU_BASE_URL = "https://digitalmanager.guru/api/v2"

TOKENS = {
    "ba":    os.environ.get("GURU_TOKEN_BA", ""),
    "ibrem": os.environ.get("GURU_TOKEN_IBREM", ""),
}

ACCOUNT_LABELS = {
    "ba":    "Board Academy",
    "ibrem": "IBREM",
}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        today = date.today().isoformat()  # YYYY-MM-DD

        all_items = []
        errors = []

        for account_key, token in TOKENS.items():
            if not token:
                continue
            try:
                items = self._fetch_all(token, today, account_key)
                all_items.extend(items)
            except Exception as e:
                errors.append(f"{account_key}: {str(e)}")

        out = json.dumps({
            "date": today,
            "total": len(all_items),
            "items": all_items,
            "errors": errors,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(out.encode())

    def _fetch_all(self, token, today, account_key):
        """Busca todas as assinaturas com next_cycle_at = hoje, filtra renovações (charged_times >= 2)."""
        results = []
        cursor = None
        label = ACCOUNT_LABELS.get(account_key, account_key)

        # Busca todos os status relevantes
        statuses = ["active", "pastdue", "canceled", "inactive", "expired"]

        while True:
            api_params = []
            for st in statuses:
                api_params.append(("subscription_status[]", st))
            api_params += [
                ("next_cycle_at_ini", today),
                ("next_cycle_at_end", today),
            ]
            if cursor:
                api_params.append(("cursor", cursor))

            url = f"{GURU_BASE_URL}/subscriptions/?" + urllib.parse.urlencode(api_params)
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            if isinstance(data, list):
                items = data
                cursor = None
            elif "data" in data:
                items = data["data"]
                cursor = data.get("next_cursor") or None
            else:
                items = []
                cursor = None

            for sub in items:
                charged = sub.get("charged_times", 0) or 0
                # Apenas renovações: já cobrou pelo menos 1 vez antes (ciclo >= 2)
                if charged < 2:
                    continue

                phone_code = sub.get("contact", {}).get("phone_local_code", "") or ""
                phone_num  = sub.get("contact", {}).get("phone_number", "") or ""

                results.append({
                    "account":      account_key,
                    "account_label": label,
                    "subscription_code": sub.get("subscription_code") or sub.get("id") or "—",
                    "status":       sub.get("last_status") or "—",
                    "charged_times": charged,
                    "customer":     (sub.get("contact") or {}).get("name") or "—",
                    "email":        (sub.get("contact") or {}).get("email") or "—",
                    "phone":        f"{phone_code}{phone_num}".strip() or "—",
                    "offer":        (sub.get("product") or {}).get("name") or "—",
                    "next_cycle_at": sub.get("next_cycle_at") or "—",
                    "amount":       sub.get("amount") or 0,
                })

            if not cursor or not items:
                break

        return results

    def log_message(self, format, *args):
        pass
