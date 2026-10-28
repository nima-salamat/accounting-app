"""Authenticated adapter protocol for a local vendor-specific POS terminal bridge.

This is not a generic card-reader driver. A local bridge must translate these
signed JSON messages to the manufacturer's payment SDK and return a signed result.
The kiosk never treats a TCP connect or an unsigned reply as proof of payment.
"""
import hashlib
import hmac
import json
import socket
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP


class PaymentTerminalError(RuntimeError):
    pass


class PaymentDeclined(PaymentTerminalError):
    pass


def _sign(secret, parts):
    message = "|".join(str(part) for part in parts).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _read_message(connection):
    stream = connection.makefile("rb")
    raw = stream.readline(8193)
    if not raw or len(raw) > 8192 or not raw.endswith(b"\n"):
        raise PaymentTerminalError("پاسخ پل پرداخت خالی یا بیش از حد بزرگ است.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PaymentTerminalError("پاسخ پل پرداخت JSON معتبر نیست.") from exc
    if not isinstance(value, dict):
        raise PaymentTerminalError("پاسخ پل پرداخت باید یک شیء JSON باشد.")
    return value


def _request_bridge(operation, amount, reference, settings, transaction_id=None):
    mode = settings.get("terminal_mode")
    if mode != "tcp":
        raise PaymentTerminalError("پل پرداخت امضاشده پیکربندی نشده است.")
    host = str(settings.get("terminal_host") or "").strip()
    port = int(settings.get("terminal_port") or 0)
    secret = str(settings.get("terminal_secret") or "")
    if not host or not 1 <= port <= 65535 or len(secret) < 24:
        raise PaymentTerminalError("میزبان، پورت یا کلید امن پل پرداخت معتبر نیست.")
    cents = int((Decimal(str(amount)) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    timestamp = int(time.time())
    nonce = uuid.uuid4().hex
    request_signature = _sign(
        secret,
        ("accounting-app", "v1", "request", operation, timestamp, nonce, reference, cents, transaction_id or ""),
    )
    request_payload = {
        "protocol": "accounting-app.payment-bridge.v1",
        "operation": operation,
        "timestamp": timestamp,
        "nonce": nonce,
        "reference": reference,
        "amount_minor_units": cents,
        "currency": "LOCAL",
        "transaction_id": transaction_id,
        "signature": request_signature,
    }
    try:
        with socket.create_connection((host, port), timeout=5.0) as connection:
            connection.settimeout(90.0)
            connection.sendall(
                json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            )
            response = _read_message(connection)
    except (OSError, TimeoutError) as exc:
        raise PaymentTerminalError("ارتباط با پل پرداخت ناموفق بود: {}".format(exc)) from exc

    if response.get("protocol") != "accounting-app.payment-bridge.v1":
        raise PaymentTerminalError("نسخهٔ پروتکل پل پرداخت با این برنامه سازگار نیست.")
    status_value = str(response.get("status") or "").lower()
    response_timestamp = response.get("timestamp")
    response_nonce = str(response.get("nonce") or "")
    response_reference = str(response.get("reference") or "")
    response_amount = response.get("amount_minor_units")
    response_transaction = str(response.get("transaction_id") or "")
    signature = str(response.get("signature") or "")
    try:
        response_timestamp = int(response_timestamp)
        response_amount = int(response_amount)
    except (TypeError, ValueError) as exc:
        raise PaymentTerminalError("پاسخ پل پرداخت فاقد مبلغ یا زمان معتبر است.") from exc
    if abs(int(time.time()) - response_timestamp) > 60:
        raise PaymentTerminalError("زمان پاسخ پل پرداخت خارج از بازهٔ اعتبار است.")
    if response_nonce != nonce or response_reference != reference or response_amount != cents:
        raise PaymentTerminalError("مبلغ، nonce یا مرجع پاسخ پل پرداخت با درخواست منطبق نیست.")
    expected = _sign(
        secret,
        (
            "accounting-app", "v1", "response", operation, status_value,
            response_timestamp, response_nonce, response_reference, response_amount,
            response_transaction,
        ),
    )
    if not signature or not hmac.compare_digest(signature, expected):
        raise PaymentTerminalError("امضای پاسخ پل پرداخت معتبر نیست.")
    if operation == "authorize":
        if status_value != "approved" or not response_transaction:
            raise PaymentDeclined(str(response.get("message") or "تراکنش توسط کارت‌خوان تأیید نشد."))
        return {"transaction_id": response_transaction, "amount_minor_units": cents, "reference": reference}
    if status_value != "voided":
        raise PaymentTerminalError(str(response.get("message") or "لغو/برگشت تراکنش توسط پل پرداخت تأیید نشد."))
    return {"transaction_id": response_transaction, "amount_minor_units": cents, "reference": reference}


def authorize_payment(amount, reference, settings):
    return _request_bridge("authorize", amount, reference, settings)


def void_payment(amount, reference, transaction_id, settings):
    return _request_bridge("void", amount, reference, settings, transaction_id=transaction_id)
