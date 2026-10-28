"""Configuration and transport-safety tests for the standalone HTTP client."""
import unittest

from client.api_client import AccountingApiClient


class ApiClientConfigurationTests(unittest.TestCase):
    def test_loopback_http_is_allowed(self):
        client = AccountingApiClient("http://127.0.0.1:8000/")
        self.assertEqual(client.base_url, "http://127.0.0.1:8000")
        self.assertEqual(
            AccountingApiClient("http://localhost:8000").base_url,
            "http://localhost:8000",
        )

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
