"""Configuration and transport-safety tests for the standalone HTTP client."""
import unittest
from unittest.mock import Mock, patch

from client.api_client import AccountingApiClient, ApiError


class ApiClientConfigurationTests(unittest.TestCase):
    def test_loopback_http_is_allowed(self):
        client = AccountingApiClient("http://127.0.0.1:8000/")
        self.assertEqual(client.base_url, "http://127.0.0.1:8000")
        self.assertEqual(
            AccountingApiClient("http://localhost:8000").base_url,
            "http://localhost:8000",
        )

    def test_validation_error_list_is_field_aware_and_never_echoes_input(self):
        response = Mock()
        response.status_code = 422
        response.ok = False
        response.headers = {}
        response.text = ""
        response.json.return_value = {
            "detail": [{
                "type": "string_too_short",
                "loc": ["body", "username"],
                "msg": "String should have at least 4 characters",
                "input": "ab-secret",
            }]
        }
        client = AccountingApiClient("http://127.0.0.1:8000")

        with patch("requests.Session.request", return_value=response):
            with self.assertRaises(ApiError) as raised:
                client._request(
                    "POST", "/api/v1/auth/login",
                    json_body={"username": "ab-secret"}, authenticated=False,
                )

        self.assertEqual(raised.exception.detail, "نام کاربری: باید حداقل 4 نویسه باشد.")
        self.assertNotIn("ab-secret", raised.exception.detail)
        self.assertNotIn("/api/v1/auth/login", raised.exception.detail)

    def test_backend_message_and_nested_error_objects_are_supported(self):
        response = Mock()
        response.status_code = 400
        response.ok = False
        response.headers = {}
        response.text = ""
        response.json.return_value = {"error": {"message": "درخواست از سمت سرور رد شد."}}
        client = AccountingApiClient("http://127.0.0.1:8000")

        with patch("requests.Session.request", return_value=response):
            with self.assertRaises(ApiError) as raised:
                client._request("POST", "/api/v1/auth/login", authenticated=False)

        self.assertEqual(raised.exception.detail, "درخواست از سمت سرور رد شد.")

    def test_remote_http_is_rejected_to_protect_bearer_tokens(self):
        with self.assertRaises(ValueError):
            AccountingApiClient("http://192.0.2.10:8000")

    def test_remote_https_is_allowed(self):
        client = AccountingApiClient("https://accounting.example.test")
        self.assertEqual(client.base_url, "https://accounting.example.test")

    def test_credentials_and_query_are_rejected_from_base_url(self):
        with self.assertRaises(ValueError):
            AccountingApiClient("https://user:password@accounting.example.test")
        with self.assertRaises(ValueError):
            AccountingApiClient("https://accounting.example.test?token=secret")


if __name__ == "__main__":
    unittest.main()
