import json
import os
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, timedelta, datetime
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
        results = []
        cursor = None
        label = ACCOUNT_LABELS.get(account_key, account_key)

        while True:
            api_params = [
                ("confirmed_at_ini", date_from),
                ("confirmed_at_end", date_to),
            ]
            if cursor:
                api_params.append(("cursor", cursor))

            url = f"{GURU_BASE_URL}/transactions/?" + urllib.parse.urlencode(api_params)
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
                raise Exception(f"HTTP {e.code}: {body[:300]}")

            if isinstance(data, list):
                items = data
                cursor = None
            elif "data" in data:
                items = data["data"]
                cursor = data.get("next_cursor") or None
            else:
                items = []
                cursor = None

            for t in items:
                # Valor real fica em payment.total
                payment = t.get("payment") or {}
                try:
                    amount = float(payment.get("total") or payment.get("gross") or 0)
                except (ValueError, TypeError):
                    amount = 0.0

                # Só mostra os valores de renovação
                if amount not in RENEWAL_AMOUNTS:
                    continue

                # Só renovações: subscription.charged_times >= 2
                subscription = t.get("subscription") or {}
                charged_times = subscription.get("charged_times") or 0
                if charged_times < 2:
                    continue

                # Dados do contato
                contact = t.get("contact") or {}
                phone_code = contact.get("phone_local_code", "") or ""
                phone_num  = contact.get("phone_number", "") or ""

                # Produto/oferta — pega do primeiro item ou do product
                items_list = t.get("items") or []
                offer_name = ""
                if items_list:
                    first = items_list[0]
                    offer_name = (first.get("offer") or {}).get("name") or first.get("name") or ""
                if not offer_name:
                    offer_name = (t.get("product") or {}).get("name") or "—"

                # Data confirmada (timestamp Unix → string)
                dates = t.get("dates") or {}
                confirmed_ts = dates.get("confirmed_at")
                if confirmed_ts:
                    try:
                        confirmed_str = datetime.utcfromtimestamp(confirmed_ts).strftime("%d/%m/%Y %H:%M")
                    except Exception:
                        confirmed_str = str(confirmed_ts)
                else:
                    confirmed_str = "—"

                # Status
                status = t.get("status") or "—"

                # Forma de pagamento
                pay_method = payment.get("method") or "—"

                results.append({
                    "account":        account_key,
                    "account_label":  label,
                    "charge_code":    t.get("id") or "—",
                    "status":         status,
                    "customer":       contact.get("name") or "—",
                    "email":          contact.get("email") or "—",
                    "phone":          f"{phone_code}{phone_num}".strip() or "—",
                    "offer":          offer_name,
                    "created_at":     confirmed_str,
                    "amount":         amount,
                    "payment_method": pay_method,
                    "charged_times":  charged_times,
                })

            if not cursor or not items:
                break

        return results

    def log_message(self, format, *args):
        pass
