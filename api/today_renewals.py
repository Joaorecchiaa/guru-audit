import json
import os
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
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

        # Ordena por next_cycle_at decrescente (mais recente primeiro)
        all_items.sort(key=lambda x: x.get("next_cycle_at") or "", reverse=True)

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
        """Busca todas as assinaturas com next_cycle_at no range, sem filtro de ciclo."""
        results = []
        cursor = None
        label = ACCOUNT_LABELS.get(account_key, account_key)

        statuses = ["active", "pastdue", "canceled", "inactive", "expired"]

        while True:
            api_params = []
            for st in statuses:
                api_params.append(("subscription_status[]", st))
            api_params += [
                ("next_cycle_at_ini", date_from),
                ("next_cycle_at_end", date_to),
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
                if charged < 2:
                    continue  # ignora novas assinaturas (1º ciclo ainda não concluído)

                phone_code = (sub.get("contact") or {}).get("phone_local_code", "") or ""
                phone_num  = (sub.get("contact") or {}).get("phone_number", "") or ""

                results.append({
                    "account":           account_key,
                    "account_label":     label,
                    "subscription_code": sub.get("subscription_code") or sub.get("id") or "—",
                    "status":            sub.get("last_status") or "—",
                    "charged_times":     charged,
                    "customer":          (sub.get("contact") or {}).get("name") or "—",
                    "email":             (sub.get("contact") or {}).get("email") or "—",
                    "phone":             f"{phone_code}{phone_num}".strip() or "—",
                    "offer":             (sub.get("product") or {}).get("name") or "—",
                    "next_cycle_at":     sub.get("next_cycle_at") or "—",
                    "amount":            0,  # será preenchido abaixo
                })

            if not cursor or not items:
                break

        # Busca next_cycle_value de cada assinatura em paralelo (igual à aba principal)
        def fetch_detail(item):
            code = item["subscription_code"]
            url = f"{GURU_BASE_URL}/subscriptions/{urllib.parse.quote(str(code), safe='')}/"
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    d = json.loads(resp.read().decode())
                val = d.get("next_cycle_value")
                if val is not None:
                    item["amount"] = float(val)
            except Exception:
                pass
            return item

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(fetch_detail, r): r for r in results}
            for f in as_completed(futures):
                pass  # atualiza in-place

        return results

    def log_message(self, format, *args):
        pass
