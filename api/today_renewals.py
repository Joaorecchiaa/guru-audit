import json
import os
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, timedelta
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

# Valores que identificam cobranças de renovação de assinatura
RENEWAL_AMOUNTS = {990.0, 997.0, 1990.0}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        today     = date.today()
        yesterday = today - timedelta(days=1)
        date_from = yesterday.isoformat()
        date_to   = today.isoformat()

        all_items = []
        errors = []

        for account_key, token in TOKENS.items():
            if not token:
                continue
            try:
                items = self._fetch_all(token, date_from, date_to, account_key)
                all_items.extend(items)
            except Exception as e:
                errors.append(f"{account_key}: {str(e)}")

        # Ordena por created_at decrescente (mais recente primeiro)
        all_items.sort(key=lambda x: x.get("created_at") or "", reverse=True)

        out = json.dumps({
            "date_from": date_from,
            "date_to":   date_to,
            "total":     len(all_items),
            "items":     all_items,
            "errors":    errors,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(out.encode())

    def _fetch_all(self, token, date_from, date_to, account_key):
        """Busca charges (transações) de hoje/ontem e filtra pelos valores de renovação."""
        results = []
        cursor = None
        label = ACCOUNT_LABELS.get(account_key, account_key)

        while True:
            api_params = [
                ("created_at_ini", date_from),
                ("created_at_end", date_to),
            ]
            if cursor:
                api_params.append(("cursor", cursor))

            url = f"{GURU_BASE_URL}/sales/?" + urllib.parse.urlencode(api_params)
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
            except urllib.error.HTTPError as e:
                body = e.read().decode()
                raise Exception(f"HTTP {e.code} em /sales/: {body[:300]}")

            if isinstance(data, list):
                items = data
                cursor = None
            elif "data" in data:
                items = data["data"]
                cursor = data.get("next_cursor") or None
            else:
                items = []
                cursor = None

            for charge in items:
                # Filtra pelo valor de renovação
                try:
                    amount = float(charge.get("amount") or charge.get("total") or 0)
                except (ValueError, TypeError):
                    amount = 0.0

                if amount not in RENEWAL_AMOUNTS:
                    continue

                # Status da transação
                status = charge.get("status") or "—"

                sale = charge  # alias para legibilidade
                contact = sale.get("contact") or sale.get("customer") or sale.get("buyer") or {}
                phone_code = contact.get("phone_local_code", "") or ""
                phone_num  = contact.get("phone_number", "") or ""

                product = sale.get("product") or {}
                offer   = sale.get("offer") or {}

                results.append({
                    "account":        account_key,
                    "account_label":  label,
                    "charge_code":    sale.get("code") or sale.get("id") or "—",
                    "status":         status,
                    "customer":       contact.get("name") or "—",
                    "email":          contact.get("email") or "—",
                    "phone":          f"{phone_code}{phone_num}".strip() or "—",
                    "offer":          offer.get("name") or product.get("name") or "—",
                    "created_at":     sale.get("created_at") or sale.get("approved_at") or "—",
                    "amount":         amount,
                    "payment_method": sale.get("payment_method") or sale.get("payment_type") or "—",
                })

            if not cursor or not items:
                break

        return results

    def log_message(self, format, *args):
        pass
