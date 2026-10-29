"""Small thread-aware HTTP client for the standalone accounting API."""
import ipaddress
import threading
import uuid
from urllib.parse import urlsplit

import requests


class ApiError(RuntimeError):
    """An HTTP/API error with a stable status code and safe display message."""

    def __init__(self, status_code, detail, method=None, path=None):
        self.status_code = status_code
        self.detail = detail
        self.method = method
        self.path = path
        context = " ".join(part for part in (method, path) if part)
        super().__init__("{}{}: {}".format(
            str(status_code), " " + context if context else "", detail
        ))


class AccountingApiClient:
    """Client API wrapper. Network operations should be called from a Qt worker thread."""

    def __init__(self, base_url="http://127.0.0.1:8000", timeout=(3.05, 30.0)):
        self.base_url = self._validate_base_url(base_url)
        self.timeout = timeout
        self._thread_local = threading.local()
        self._token_lock = threading.RLock()
        self._access_token = None
        self._last_idempotency_key = None

    @staticmethod
    def _validate_base_url(base_url):
        parsed = urlsplit(str(base_url).strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("نشانی API باید یک URL معتبر HTTP یا HTTPS باشد.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("نشانی API نباید اطلاعات ورود، query یا fragment داشته باشد.")
        if parsed.scheme == "http":
            try:
                local_only = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                local_only = parsed.hostname.lower() == "localhost"
            if not local_only:
                raise ValueError("برای سرور راه دور فقط HTTPS مجاز است.")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("شماره پورت نشانی API معتبر نیست.") from exc
        return parsed.geturl().rstrip("/")

    @property
    def access_token(self):
        with self._token_lock:
            return self._access_token

    @property
    def last_idempotency_key(self):
        """Key used by the most recent sale request; reuse it to safely retry that request."""
        return self._last_idempotency_key

    def set_access_token(self, token):
        with self._token_lock:
            self._access_token = token

    def clear_session(self):
        """Clear only this client's credentials; signed server tokens expire automatically."""
        self.set_access_token(None)

    def _session(self):
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    def _request(self, method, path, *, json_body=None, params=None, headers=None, authenticated=True, include_headers=False):
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if authenticated:
            token = self.access_token
            if token:
                request_headers["Authorization"] = "Bearer {}".format(token)
        try:
            response = self._session().request(
                method,
                "{}{}".format(self.base_url, path),
                json=json_body,
                params=params,
                headers=request_headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ApiError(0, "اتصال به سرور برقرار نشد؛ نشانی و وضعیت شبکه را بررسی کنید.", method, path) from exc

        if response.status_code == 204:
            return {"data": None, "headers": {str(k).lower(): str(v) for k, v in response.headers.items()}} if include_headers else None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not response.ok:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if isinstance(detail, list):
                detail = "؛ ".join(
                    str(item.get("msg", item)) if isinstance(item, dict) else str(item)
                    for item in detail
                )
            if not detail:
                detail = "درخواست ناموفق بود."
            if response.status_code == 401:
                self.clear_session()
            raise ApiError(response.status_code, str(detail), method, path)
        if include_headers:
            return {"data": payload, "headers": {str(k).lower(): str(v) for k, v in response.headers.items()}}
        return payload

    def _request_page(self, method, path, *, page, page_size, params=None):
        query = dict(params or {})
        query.update({"page": page, "page_size": page_size})
        result = self._request(method, path, params=query, include_headers=True)
        items = result["data"] or []
        headers = result["headers"]
        try:
            total = int(headers.get("x-total-count", len(items)))
        except (TypeError, ValueError):
            total = len(items)
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": max(0, total),
        }

    def setup_status(self):
        return self._request("GET", "/api/v1/setup/status", authenticated=False)

    def complete_setup(self, username, password, password_confirmation, schema_rows=None, setup_token=None, company_name="کسب‌وکار من", business_profile="general", product_buy_price_required=None):
        payload = self._request(
            "POST", "/api/v1/setup",
            json_body={
                "username": username,
                "password": password,
                "password_confirmation": password_confirmation,
                "schema_rows": schema_rows or [],
                "company_name": company_name,
                "business_profile": business_profile,
                "product_buy_price_required": product_buy_price_required,
                "setup_token": setup_token,
            },
            authenticated=False,
        )
        self.set_access_token(payload["access_token"])
        return payload.get("user", payload)

    def login(self, username, password, client_name="Desktop client"):
        payload = self._request(
            "POST", "/api/v1/auth/login",
            json_body={"username": username, "password": password, "client_name": client_name},
            authenticated=False,
        )
        if payload.get("status", "active") == "active" and payload.get("access_token"):
            self.set_access_token(payload["access_token"])
            payload["user"] = self.me()
        return payload

    def check_session_status(self, ticket):
        payload = self._request("POST", "/api/v1/auth/session-status",
                                json_body={"ticket": ticket}, authenticated=False)
        if payload.get("status") == "active" and payload.get("access_token"):
            self.set_access_token(payload["access_token"])
        return payload

    def logout(self):
        try:
            return self._request("POST", "/api/v1/auth/logout") if self.access_token else {"status": "logged_out"}
        finally:
            self.clear_session()

    def admin_overview(self):
        return self._request("GET", "/api/v1/admin/overview")

    def list_admin_sessions(self, state="all", q=None, limit=200):
        return self._request("GET", "/api/v1/admin/sessions",
                             params={"state": state, "q": q, "limit": limit})

    def activate_session(self, session_id):
        return self._request("POST", "/api/v1/admin/sessions/{}/activate".format(session_id))

    def revoke_session(self, session_id, reason="revoked_by_admin"):
        return self._request("POST", "/api/v1/admin/sessions/{}/revoke".format(session_id),
                             json_body={"reason": reason})

    def revoke_all_sessions(self):
        return self._request("POST", "/api/v1/admin/sessions/revoke-all")

    def me(self):
        return self._request("GET", "/api/v1/auth/me")

    def list_categories(self, q=None, page=1, page_size=100):
        return self._request(
            "GET", "/api/v1/categories",
            params={"q": q, "page": page, "page_size": page_size},
        )

    def list_categories_page(self, q=None, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/categories", page=page, page_size=page_size, params={"q": q}
        )

    def create_category(self, name):
        return self._request("POST", "/api/v1/categories", json_body={"name": name})

    def update_category(self, category_id, **values):
        return self._request("PATCH", "/api/v1/categories/{}".format(category_id), json_body=values)

    def delete_category(self, category_id):
        return self._request("DELETE", "/api/v1/categories/{}".format(category_id))

    def list_products(self, q=None, category_id=None, page=1, page_size=100):
        params = {"q": q, "category_id": category_id, "page": page, "page_size": page_size}
        return self._request("GET", "/api/v1/products", params=params)

    def list_products_page(self, q=None, category_id=None, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/products", page=page, page_size=page_size,
            params={"q": q, "category_id": category_id},
        )

    def get_product(self, product_id):
        """Fetch the current product, including stock, for editing a saved receipt."""
        return self._request("GET", "/api/v1/products/{}".format(product_id))

    def upload_product_image(self, product_id, image_path):
        """Upload a selected local photo to the authenticated server."""
        import mimetypes
        import os

        content_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
        if content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            raise ValueError("فرمت عکس باید JPEG، PNG، WebP یا GIF باشد.")
        token = self.access_token
        if not token:
            raise ApiError(401, "برای ارسال عکس ابتدا وارد شوید.", "POST", "/products/{}/image".format(product_id))
        try:
            with open(image_path, "rb") as stream:
                response = self._session().post(
                    "{}/api/v1/products/{}/image".format(self.base_url, product_id),
                    files={"file": (os.path.basename(image_path), stream, content_type)},
                    headers={"Authorization": "Bearer {}".format(token), "Accept": "application/json"},
                    timeout=self.timeout,
                )
        except OSError as exc:
            raise ApiError(0, "فایل عکس خوانده نشد: {}".format(exc), "POST", "/products/{}/image".format(product_id)) from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not response.ok:
            detail = payload.get("detail", "ارسال عکس ناموفق بود.") if isinstance(payload, dict) else "ارسال عکس ناموفق بود."
            raise ApiError(response.status_code, str(detail), "POST", "/products/{}/image".format(product_id))
        return payload

    def get_product_image_bytes(self, product_id):
        """Download an image through the protected API route."""
        token = self.access_token
        if not token:
            raise ApiError(401, "برای دریافت عکس باید وارد شوید.", "GET", "/products/{}/image".format(product_id))
        try:
            response = self._session().get(
                "{}/api/v1/products/{}/image".format(self.base_url, product_id),
                headers={"Authorization": "Bearer {}".format(token), "Accept": "image/*"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ApiError(0, "دریافت عکس از سرور ناموفق بود.", "GET", "/products/{}/image".format(product_id)) from exc
        if response.status_code == 404:
            return None
        if not response.ok:
            try:
                detail = response.json().get("detail", "دریافت عکس ناموفق بود.")
            except ValueError:
                detail = "دریافت عکس ناموفق بود."
            if response.status_code == 401:
                self.clear_session()
            raise ApiError(response.status_code, str(detail), "GET", "/products/{}/image".format(product_id))
        return response.content

    def create_product(self, *, name, sell_price, buy_price=None, category_id=None,
                       image_path=None, custom_product=False, track_stock=False, reorder_level=0):
        return self._request(
            "POST", "/api/v1/products",
            json_body={
                "name": name,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "category_id": str(category_id) if category_id else None,
                "image_path": image_path,
                "custom_product": custom_product,
                "track_stock": bool(track_stock),
                "reorder_level": reorder_level,
            },
        )

    def update_product(self, product_id, **values):
        return self._request("PATCH", "/api/v1/products/{}".format(product_id), json_body=values)

    def delete_product(self, product_id):
        return self._request("DELETE", "/api/v1/products/{}".format(product_id))

    def list_warehouses(self):
        return self._request("GET", "/api/v1/warehouses")

    def list_warehouses_page(self, q=None, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/warehouses", page=page, page_size=page_size, params={"q": q}
        )

    def create_warehouse(self, *, name, price, amount, unit):
        return self._request(
            "POST", "/api/v1/warehouses",
            json_body={"name": name, "price": price, "amount": amount, "unit": unit},
        )

    def list_checks(self, direction="in", q=None, page=1, page_size=100):
        if direction not in ("in", "out"):
            raise ValueError("direction must be 'in' or 'out'")
        return self._request(
            "GET", "/api/v1/checks/{}".format(direction),
            params={"q": q, "page": page, "page_size": page_size},
        )

    def list_checks_page(self, direction="in", q=None, page=1, page_size=25):
        if direction not in ("in", "out"):
            raise ValueError("direction must be 'in' or 'out'")
        return self._request_page(
            "GET", "/api/v1/checks/{}".format(direction),
            page=page, page_size=page_size, params={"q": q},
        )

    def list_users(self, page=1, page_size=100, q=None):
        return self._request(
            "GET", "/api/v1/users",
            params={"page": page, "page_size": page_size, "q": q},
        )

    def list_users_page(self, q=None, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/users", page=page, page_size=page_size, params={"q": q}
        )

    def create_user(
        self, *, username, password, is_admin=False, buttons="",
        is_active=True, requires_session_activation=True,
    ):
        return self._request(
            "POST", "/api/v1/users",
            json_body={
                "username": username,
                "password": password,
                "is_admin": is_admin,
                "buttons": buttons,
                "is_active": is_active,
                "requires_session_activation": requires_session_activation,
            },
        )

    def list_receipts(self, page=1, page_size=100):
        return self._request(
            "GET", "/api/v1/receipts",
            params={"page": page, "page_size": page_size},
        )

    def list_receipts_page(self, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/receipts", page=page, page_size=page_size
        )

    def get_receipt(self, receipt_id):
        return self._request("GET", "/api/v1/receipts/{}".format(receipt_id))

    def delete_receipt(self, receipt_id):
        return self._request("DELETE", "/api/v1/receipts/{}".format(receipt_id))

    def quote_sale(self, items, paid=False, payment_method="cash", seat_number=None):
        return self._request(
            "POST", "/api/v1/sales/quote",
            json_body={
                "items": items, "paid": bool(paid), "payment_method": payment_method,
                "seat_number": seat_number,
            },
        )

    def create_sale(self, items, paid=False, idempotency_key=None, payment_method="cash", seat_number=None):
        """Create a sale. Reuse last_idempotency_key if the result of a request is uncertain."""
        key = idempotency_key or uuid.uuid4().hex
        self._last_idempotency_key = key
        return self._request(
            "POST", "/api/v1/sales",
            json_body={
                "items": items, "paid": bool(paid), "payment_method": payment_method,
                "seat_number": seat_number,
            },
            headers={"Idempotency-Key": key},
        )

    def update_sale(self, receipt_id, items, paid=False, payment_method="cash", seat_number=None):
        return self._request(
            "PUT", "/api/v1/sales/{}".format(receipt_id),
            json_body={
                "items": items, "paid": bool(paid), "payment_method": payment_method,
                "seat_number": seat_number,
            },
        )

    def sales_summary(self, start_at=None, end_at=None):
        return self._request(
            "GET", "/api/v1/reports/summary",
            params={"start_at": start_at, "end_at": end_at},
        )

    def list_schema_entities(self):
        return self._request("GET", "/api/v1/schemas/entities")

    def list_schema_fields(self, entity_type):
        return self._request("GET", "/api/v1/schemas/fields/{}".format(entity_type))

    def get_custom_table_data(self, entity_type, record_ids):
        """Fetch custom-column definitions and values for a bounded batch of rows."""
        ids = [str(record_id) for record_id in record_ids if record_id]
        if not ids:
            return {"fields": [], "values": {}}
        return self._request(
            "GET", "/api/v1/schemas/table/{}".format(entity_type),
            params=[("record_ids", record_id) for record_id in ids],
        )

    def register_schema_fields(self, rows):
        return self._request("POST", "/api/v1/schemas/fields", json_body={"rows": rows})

    def entity_values(self, entity_type, record_id):
        return self._request("GET", "/api/v1/schemas/values/{}/{}".format(entity_type, record_id))

    def save_entity_values(self, entity_type, record_id, values):
        return self._request(
            "PATCH", "/api/v1/schemas/values/{}/{}".format(entity_type, record_id),
            json_body={"values": values},
        )


    def list_inventory(self, q=None, low_stock_only=False, page=1, page_size=50):
        return self._request(
            "GET", "/api/v1/inventory",
            params={"q": q, "low_stock_only": bool(low_stock_only),
                    "page": page, "page_size": page_size},
        )

    def list_stock_movements(self, product_id=None, page=1, page_size=50):
        return self._request(
            "GET", "/api/v1/inventory/movements",
            params={"product_id": str(product_id) if product_id else None,
                    "page": page, "page_size": page_size},
        )

    def adjust_inventory(self, product_id, quantity_change, reason="correction", notes=None):
        return self._request(
            "POST", "/api/v1/inventory/adjustments",
            json_body={
                "product_id": str(product_id), "quantity_change": quantity_change,
                "reason": reason, "notes": notes,
            },
        )

    def create_return(self, receipt_id, items, refund_method="cash", reason="customer_return", notes=None):
        return self._request(
            "POST", "/api/v1/returns",
            json_body={
                "receipt_id": str(receipt_id),
                "items": [
                    {"original_line_id": str(item["original_line_id"]), "quantity": int(item["quantity"])}
                    for item in items
                ],
                "refund_method": refund_method,
                "reason": reason,
                "notes": notes,
            },
        )

    def list_returns_page(self, page=1, page_size=25):
        return self._request_page("GET", "/api/v1/returns", page=page, page_size=page_size)

    def get_return(self, return_id):
        return self._request("GET", "/api/v1/returns/{}".format(return_id))

    def list_fiscal_years(self):
        return self._request("GET", "/api/v1/fiscal-years")

    def create_fiscal_year(self, name, start_date, end_date):
        return self._request(
            "POST", "/api/v1/fiscal-years",
            json_body={"name": name, "start_date": start_date, "end_date": end_date},
        )

    def close_fiscal_year(self, year_id):
        return self._request("POST", "/api/v1/fiscal-years/{}/close".format(year_id))

    def reopen_fiscal_year(self, year_id, reason):
        return self._request(
            "POST", "/api/v1/fiscal-years/{}/reopen".format(year_id),
            json_body={"reason": reason},
        )

    def list_accounts(self):
        return self._request("GET", "/api/v1/accounts")

    def create_account(self, code, name, account_type, description=None):
        return self._request(
            "POST", "/api/v1/accounts",
            json_body={"code": code, "name": name, "account_type": account_type, "description": description},
        )

    def list_journals_page(self, q=None, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/journals", page=page, page_size=page_size, params={"q": q}
        )

    def get_journal(self, entry_id):
        return self._request("GET", "/api/v1/journals/{}".format(entry_id))

    def create_journal(self, entry_date, description, lines, reference=None):
        return self._request(
            "POST", "/api/v1/journals",
            json_body={
                "entry_date": entry_date,
                "description": description,
                "reference": reference,
                "lines": [
                    {
                        "account_id": str(line["account_id"]),
                        "description": line.get("description", ""),
                        "debit": str(line.get("debit", 0)),
                        "credit": str(line.get("credit", 0)),
                    }
                    for line in lines
                ],
            },
        )

    def accounting_summary(self, start_date=None, end_date=None):
        return self._request(
            "GET", "/api/v1/reports/accounting-summary",
            params={"start_date": start_date, "end_date": end_date},
        )

    def list_stocktakes_page(self, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/stocktakes", page=page, page_size=page_size
        )

    def get_stocktake(self, stocktake_id):
        return self._request("GET", "/api/v1/stocktakes/{}".format(stocktake_id))

    def create_stocktake(self, name, product_ids, notes=None):
        return self._request(
            "POST", "/api/v1/stocktakes",
            json_body={"name": name, "product_ids": [str(item) for item in product_ids], "notes": notes},
        )

    def update_stocktake_count(self, stocktake_id, line_id, counted_quantity):
        return self._request(
            "PATCH", "/api/v1/stocktakes/{}/lines/{}".format(stocktake_id, line_id),
            json_body={"counted_quantity": str(counted_quantity)},
        )

    def apply_stocktake(self, stocktake_id):
        return self._request("POST", "/api/v1/stocktakes/{}/apply".format(stocktake_id))

    def list_audit_events_page(self, q=None, resource=None, page=1, page_size=50):
        return self._request_page(
            "GET", "/api/v1/audit", page=page, page_size=page_size,
            params={"q": q, "resource": resource},
        )

    def get_company_profile(self):
        return self._request("GET", "/api/v1/company-profile")

    def get_kiosk_settings(self):
        return self._request("GET", "/api/v1/kiosk/settings")

    def save_kiosk_settings(self, **values):
        return self._request("PUT", "/api/v1/kiosk/settings", json_body=values)

    def get_kiosk_config(self):
        return self._request("GET", "/api/v1/kiosk/config")

    def list_recent_receipts_page(self, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/sales/recent-receipts", page=page, page_size=page_size
        )

    def list_partners_page(self, q=None, partner_type=None, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/partners", page=page, page_size=page_size,
            params={"q": q, "partner_type": partner_type},
        )

    def create_partner(self, **values):
        return self._request("POST", "/api/v1/partners", json_body=values)

    def update_partner(self, partner_id, **values):
        return self._request("PATCH", "/api/v1/partners/{}".format(partner_id), json_body=values)

    def delete_partner(self, partner_id):
        return self._request("DELETE", "/api/v1/partners/{}".format(partner_id))

    def list_purchase_invoices_page(self, q=None, status_filter=None, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/purchase-invoices", page=page, page_size=page_size,
            params={"q": q, "status_filter": status_filter},
        )

    def get_purchase_invoice(self, invoice_id):
        return self._request("GET", "/api/v1/purchase-invoices/{}".format(invoice_id))

    def create_purchase_invoice(self, supplier_id, invoice_number, invoice_date, items,
                                due_date=None, notes=None):
        return self._request(
            "POST", "/api/v1/purchase-invoices",
            json_body={
                "supplier_id": str(supplier_id),
                "invoice_number": invoice_number,
                "invoice_date": invoice_date,
                "due_date": due_date,
                "items": [
                    {
                        "product_id": str(item["product_id"]) if item.get("product_id") else None,
                        "description": item.get("description", ""),
                        "quantity": str(item["quantity"]),
                        "unit_cost": str(item["unit_cost"]),
                    }
                    for item in items
                ],
                "notes": notes,
            },
        )

    def add_purchase_payment(self, invoice_id, amount, paid_on, payment_method="bank_transfer",
                             reference=None, notes=None):
        return self._request(
            "POST", "/api/v1/purchase-invoices/{}/payments".format(invoice_id),
            json_body={
                "amount": str(amount), "paid_on": paid_on,
                "payment_method": payment_method, "reference": reference, "notes": notes,
            },
        )

    def list_expenses_page(self, q=None, page=1, page_size=25):
        return self._request_page(
            "GET", "/api/v1/expenses", page=page, page_size=page_size, params={"q": q},
        )

    def create_expense(self, **values):
        return self._request("POST", "/api/v1/expenses", json_body=values)

    def get_appearance_settings(self):
        """Fetch shared UI design tokens stored in the server database (login is not required)."""
        return self._request("GET", "/api/v1/appearance-settings", authenticated=False)

    def save_appearance_settings(self, **values):
        """Update shared UI design tokens; the API restricts this to administrators."""
        return self._request("PUT", "/api/v1/appearance-settings", json_body=values)

    def get_invoice_template(self, *, kind="invoice"):
        return self._request(
            "GET", "/api/v1/invoices/template",
            params={"kind": kind},
        )

    def save_invoice_template(self, *, kind="invoice", **values):
        return self._request(
            "PUT", "/api/v1/invoices/template",
            params={"kind": kind},
            json_body=values,
        )

    def update_warehouse(self, record_id, **values):
        return self._request("PATCH", "/api/v1/warehouses/{}".format(record_id), json_body=values)

    def delete_warehouse(self, record_id):
        return self._request("DELETE", "/api/v1/warehouses/{}".format(record_id))

    def create_check(self, direction, *, name, check_id, price, date, payed=False):
        self._validate_check_direction(direction)
        return self._request("POST", "/api/v1/checks/{}".format(direction),
            json_body={"name": name, "check_id": check_id, "price": price, "date": date, "payed": bool(payed)})

    def update_check(self, direction, record_id, **values):
        self._validate_check_direction(direction)
        return self._request("PATCH", "/api/v1/checks/{}/{}".format(direction, record_id), json_body=values)

    def delete_check(self, direction, record_id):
        self._validate_check_direction(direction)
        return self._request("DELETE", "/api/v1/checks/{}/{}".format(direction, record_id))

    @staticmethod
    def _validate_check_direction(direction):
        if direction not in ("in", "out"):
            raise ValueError("direction must be in or out")

    def update_user(self, user_id, **values):
        return self._request("PATCH", "/api/v1/users/{}".format(user_id), json_body=values)

    def delete_user(self, user_id):
        return self._request("DELETE", "/api/v1/users/{}".format(user_id))

    def list_schema_records(self, entity_type, limit=200):
        return self._request("GET", "/api/v1/schemas/records/{}".format(entity_type), params={"limit": limit})

    def create_custom_record(self, entity_type, values):
        return self._request("POST", "/api/v1/schemas/records/{}".format(entity_type), json_body={"values": values})

    def delete_schema_record(self, entity_type, record_id):
        return self._request("DELETE", "/api/v1/schemas/records/{}/{}".format(entity_type, record_id))

    def sales_trend(self, days=30):
        return self._request("GET", "/api/v1/reports/sales-trend", params={"days": days})

    def product_performance(self, limit=20):
        return self._request("GET", "/api/v1/reports/product-performance", params={"limit": limit})
