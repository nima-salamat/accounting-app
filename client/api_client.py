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

    def _request(self, method, path, *, json_body=None, params=None, headers=None, authenticated=True):
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
            return None
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
        return payload

    def setup_status(self):
        return self._request("GET", "/api/v1/setup/status", authenticated=False)

    def complete_setup(self, username, password, password_confirmation, schema_rows=None, setup_token=None):
        payload = self._request(
            "POST", "/api/v1/setup",
            json_body={
                "username": username,
                "password": password,
                "password_confirmation": password_confirmation,
                "schema_rows": schema_rows or [],
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

    def create_category(self, name):
        return self._request("POST", "/api/v1/categories", json_body={"name": name})

    def update_category(self, category_id, **values):
        return self._request("PATCH", "/api/v1/categories/{}".format(category_id), json_body=values)

    def delete_category(self, category_id):
        return self._request("DELETE", "/api/v1/categories/{}".format(category_id))

    def list_products(self, q=None, category_id=None, page=1, page_size=100):
        params = {"q": q, "category_id": category_id, "page": page, "page_size": page_size}
        return self._request("GET", "/api/v1/products", params=params)

    def create_product(self, *, name, buy_price, sell_price, category_id=None,
                       image_path=None, custom_product=False):
        return self._request(
            "POST", "/api/v1/products",
            json_body={
                "name": name,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "category_id": str(category_id) if category_id else None,
                "image_path": image_path,
                "custom_product": custom_product,
            },
        )

    def update_product(self, product_id, **values):
        return self._request("PATCH", "/api/v1/products/{}".format(product_id), json_body=values)

    def delete_product(self, product_id):
        return self._request("DELETE", "/api/v1/products/{}".format(product_id))

    def list_warehouses(self):
        return self._request("GET", "/api/v1/warehouses")

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

    def list_users(self):
        return self._request("GET", "/api/v1/users")

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

    def get_receipt(self, receipt_id):
        return self._request("GET", "/api/v1/receipts/{}".format(receipt_id))

    def delete_receipt(self, receipt_id):
        return self._request("DELETE", "/api/v1/receipts/{}".format(receipt_id))

    def create_sale(self, items, paid=False, idempotency_key=None):
        """Create a sale. Reuse last_idempotency_key if the result of a request is uncertain."""
        key = idempotency_key or uuid.uuid4().hex
        self._last_idempotency_key = key
        return self._request(
            "POST", "/api/v1/sales",
            json_body={"items": items, "paid": bool(paid)},
            headers={"Idempotency-Key": key},
        )

    def update_sale(self, receipt_id, items, paid=False):
        return self._request(
            "PUT", "/api/v1/sales/{}".format(receipt_id),
            json_body={"items": items, "paid": bool(paid)},
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

    def register_schema_fields(self, rows):
        return self._request("POST", "/api/v1/schemas/fields", json_body={"rows": rows})

    def entity_values(self, entity_type, record_id):
        return self._request("GET", "/api/v1/schemas/values/{}/{}".format(entity_type, record_id))

    def save_entity_values(self, entity_type, record_id, values):
        return self._request(
            "PATCH", "/api/v1/schemas/values/{}/{}".format(entity_type, record_id),
            json_body={"values": values},
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
