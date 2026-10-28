"""Small thread-aware HTTP client for the standalone accounting API."""
import threading
import uuid

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
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._thread_local = threading.local()
        self._token_lock = threading.RLock()
        self._access_token = None
        self._last_idempotency_key = None

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

    def complete_setup(self, username, password, password_confirmation, schema_rows=None):
        payload = self._request(
            "POST", "/api/v1/setup",
            json_body={
                "username": username,
                "password": password,
                "password_confirmation": password_confirmation,
                "schema_rows": schema_rows or [],
            },
            authenticated=False,
        )
        self.set_access_token(payload["access_token"])
        return payload.get("user", payload)

    def login(self, username, password):
        payload = self._request(
            "POST", "/api/v1/auth/login",
            json_body={"username": username, "password": password},
            authenticated=False,
        )
        self.set_access_token(payload["access_token"])
        return self.me()

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

    def create_user(self, *, username, password, is_admin=False, buttons=""):
        return self._request(
            "POST", "/api/v1/users",
            json_body={
                "username": username, "password": password,
                "is_admin": is_admin, "buttons": buttons,
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
