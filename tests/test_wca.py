import base64
from io import BytesIO
import json
import socket
import ssl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPSHandler

import wca
from wca import WCA, WCAAPIError, WCAConfigError, WCAConflictError, WCANotFoundError
from wca.client import _NoRedirect

KEY = "_".join(("sb", "secret", "offline_test_value_never_a_real_credential"))
ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ID2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TOKEN = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def row(identifier=ID, name="홍길동", result="X", size=3):
    return {"id": identifier, "team_name": name, "file_name": "solution.py", "file_size": size, "created_at": "2026-10-14T04:05:06Z", "result": result}


class Response(BytesIO):
    pass


class ScriptedOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Unexpected request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if not isinstance(response, bytes):
            response = json.dumps(response, ensure_ascii=False).encode()
        return Response(response)


def configured(*responses, download_dir=None, key=KEY):
    client = WCA(secret_key=key, download_dir=download_dir)
    opener = ScriptedOpener(*responses)
    client._transport.opener = opener
    return client, opener


def params(request):
    return {key: values[0] for key, values in parse_qs(urlsplit(request.full_url).query).items()}


class WCATests(unittest.TestCase):
    def test_list_paginates_all_metadata_without_storage_calls(self):
        page = [row() for _ in range(500)]
        client, opener = configured(page, [row(ID2, result="100")], [])
        records = client.list()
        self.assertEqual(len(records), 501)
        self.assertEqual(records[-1]["name"], "홍길동")
        self.assertEqual(records[-1]["result"], "100")
        self.assertNotIn("storage_path", records[-1])
        self.assertEqual(params(opener.requests[0])["order"], "created_at.asc,id.asc")
        self.assertEqual(params(opener.requests[1])["offset"], "500")
        self.assertTrue(all("/rest/v1/team_submissions" in req.full_url for req in opener.requests))

    def test_list_handles_server_page_limit_smaller_than_requested(self):
        client, opener = configured([row()], [row(ID2)], [])
        self.assertEqual(len(client.list()), 2)
        self.assertEqual([params(req)["offset"] for req in opener.requests], ["0", "1", "2"])

    def test_frist_downloads_pending_opaque_bytes_with_name(self):
        content = b"\0\xff\x80\n"
        original = {**row(size=len(content)), "storage_bucket": "team-python-files", "storage_path": f"public/{TOKEN}/{ID}.py"}
        with tempfile.TemporaryDirectory() as directory:
            client, opener = configured([original], content, download_dir=directory)
            item = client.frist()
            self.assertEqual(item["name"], "홍길동")
            self.assertEqual(item["team_name"], "홍길동")
            self.assertEqual(item["path"], Path(directory).resolve() / f"{ID}.py")
            self.assertEqual(item["path"].read_bytes(), content)
            self.assertEqual(params(opener.requests[0])["result"], "eq.X")
            self.assertEqual(params(opener.requests[0])["order"], "created_at.asc,id.asc")
            self.assertEqual(params(opener.requests[0])["limit"], "1")
            self.assertIn("/storage/v1/object/authenticated/team-python-files/public/", opener.requests[1].full_url)
            self.assertEqual(len(opener.requests), 2)
            self.assertFalse(list(Path(directory).glob(".wca-*")))

    def test_frist_empty_returns_none_without_downloading(self):
        client, opener = configured([])
        self.assertIsNone(client.frist())
        self.assertEqual(len(opener.requests), 1)

    def test_first_alias_is_available(self):
        client, _ = configured([])
        self.assertIsNone(client.first())

    def test_module_first_accepts_key_without_environment_and_reuses_it(self):
        old = wca._default
        opener = ScriptedOpener([], [], [], [row()], [row(result="100")])
        try:
            wca._default = None
            with patch.dict("os.environ", {}, clear=True), patch("wca.client.build_opener", return_value=opener):
                self.assertIsNone(wca.first(KEY))
                self.assertEqual(wca.list(), [])
                self.assertIsNone(wca.frist())
                self.assertEqual(wca.spend("홍길동", 100)["result"], "100")
            self.assertTrue(all(req.get_header("Apikey") == KEY for req in opener.requests))
        finally:
            wca._default = old

    def test_module_first_preserves_settings_when_changing_key(self):
        old = wca._default
        client = WCA(url="https://configured-project.supabase.co", secret_key=KEY, download_dir="received", timeout=47)
        opener = ScriptedOpener([])
        client._transport.opener = opener
        changed_key = KEY + "_changed"
        try:
            wca._default = client
            self.assertIsNone(wca.first(changed_key))
            self.assertIs(wca._default, client)
            self.assertEqual(client.download_dir, Path("received"))
            self.assertEqual(client._transport.timeout, 47)
            self.assertTrue(opener.requests[0].full_url.startswith("https://configured-project.supabase.co/"))
            self.assertEqual(opener.requests[0].get_header("Apikey"), changed_key)
        finally:
            wca._default = old

    def test_first_key_downloads_to_keyword_directory(self):
        original = {**row(), "storage_bucket": "team-python-files", "storage_path": f"public/{TOKEN}/{ID}.py"}
        changed_key = KEY + "_download"
        with tempfile.TemporaryDirectory() as directory:
            client, opener = configured([original], b"abc")
            item = client.first(changed_key, download_dir=directory)
            self.assertEqual(item["path"].parent, Path(directory).resolve())
            self.assertEqual(item["path"].read_bytes(), b"abc")
            self.assertEqual([req.get_header("Apikey") for req in opener.requests], [changed_key, changed_key])
            self.assertEqual([path.name for path in Path(directory).iterdir()], [ID + ".py"])

    def test_blank_explicit_key_does_not_fall_back_or_change_saved_key(self):
        client, opener = configured()
        old = wca._default
        try:
            with patch.dict("os.environ", {"WCA_SUPABASE_SECRET_KEY": KEY}):
                with self.assertRaises(WCAConfigError):
                    WCA(secret_key="")
                for default in (None, client):
                    wca._default = default
                    with self.assertRaises(WCAConfigError):
                        wca.first("")
            self.assertEqual(client._transport.key, KEY)
            self.assertEqual(opener.requests, [])
        finally:
            wca._default = old

    def test_frist_checks_download_size_before_creating_files(self):
        record = {**row(size=10), "storage_bucket": "team-python-files", "storage_path": f"public/{TOKEN}/{ID}.py"}
        with tempfile.TemporaryDirectory() as directory:
            client, _ = configured([record], b"abc", download_dir=directory)
            with self.assertRaises(WCAAPIError):
                client.frist()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_original_filename_cannot_choose_local_output_path(self):
        record = {**row(size=0), "file_name": "../../escape.py", "storage_bucket": "team-python-files", "storage_path": f"public/{TOKEN}/{ID}.py"}
        with tempfile.TemporaryDirectory() as directory:
            client, _ = configured([record], b"", download_dir=directory)
            item = client.frist()
            self.assertEqual(item["path"].parent, Path(directory).resolve())
            self.assertEqual(item["path"].name, f"{ID}.py")

    def test_spend_updates_one_oldest_pending_id_not_every_matching_name(self):
        client, opener = configured([row()], [row(result="100")])
        updated = client.spend("홍길동", 100)
        self.assertEqual(updated["result"], "100")
        lookup, update = opener.requests
        self.assertEqual(params(lookup)["limit"], "1")
        self.assertEqual(params(lookup)["order"], "created_at.asc,id.asc")
        self.assertEqual(update.get_method(), "PATCH")
        self.assertEqual(params(update)["id"], "eq." + ID)
        self.assertEqual(params(update)["result"], "eq.X")
        self.assertEqual(json.loads(update.data), {"result": "100"})
        self.assertEqual(update.get_header("Prefer"), "return=representation")

    def test_spend_exact_id_and_reserved_name_characters(self):
        name = '한, "사람"\\이름'
        client, opener = configured([row(ID2, name)], [row(ID2, name, "정답")])
        self.assertEqual(client.spend(name, "정답", submission_id=ID2)["id"], ID2)
        expected = 'eq."한, \\"사람\\"\\\\이름"'
        self.assertEqual(params(opener.requests[0])["id"], "eq." + ID2)
        self.assertEqual(params(opener.requests[0])["team_name"], expected)
        self.assertEqual(params(opener.requests[1])["team_name"], expected)

    def test_spend_has_no_pending_row(self):
        client, opener = configured([])
        with self.assertRaises(WCANotFoundError):
            client.spend("홍길동", 100)
        self.assertEqual(len(opener.requests), 1)

    def test_concurrent_result_change_is_not_overwritten(self):
        client, _ = configured([row()], [])
        with self.assertRaises(WCAConflictError):
            client.spend("홍길동", 100)

    def test_modern_secret_is_only_sent_in_apikey_header(self):
        client, opener = configured([])
        client.list()
        self.assertEqual(opener.requests[0].get_header("Apikey"), KEY)
        self.assertIsNone(opener.requests[0].get_header("Authorization"))
        self.assertNotIn(KEY, opener.requests[0].full_url)

    def test_legacy_service_role_jwt_headers(self):
        payload = base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip("=")
        key = "header." + payload + ".fake-signature"
        client, opener = configured([], key=key)
        client.list()
        self.assertEqual(opener.requests[0].get_header("Authorization"), "Bearer " + key)

    def test_public_key_plain_http_and_foreign_host_are_rejected(self):
        with self.assertRaises(WCAConfigError):
            WCA(secret_key="sb_publishable_public_key_test_only")
        with self.assertRaises(WCAConfigError):
            WCA(url="http://test.supabase.co", secret_key=KEY)
        with self.assertRaises(WCAConfigError):
            WCA(url="https://example.com", secret_key=KEY)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_invalid_result_rejected_without_any_request(self):
        client, opener = configured()
        for value in [None, True, {}, [], float("nan"), float("inf"), "", "x" * 1025]:
            with self.subTest(value=type(value).__name__), self.assertRaises(ValueError):
                client.spend("홍길동", value)
        self.assertEqual(opener.requests, [])

    def test_server_error_redacts_secret_key(self):
        body = BytesIO(json.dumps({"message": "invalid " + KEY, "code": "test_error"}).encode())
        error = HTTPError("https://test.supabase.co/rest/v1/team_submissions", 401, "Unauthorized", {}, body)
        client, _ = configured(error)
        with self.assertRaises(WCAAPIError) as caught:
            client.list()
        self.assertNotIn(KEY, str(caught.exception))
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(caught.exception.code, "test_error")

    def test_network_and_malformed_response_errors(self):
        for response in [URLError("offline"), b"not json", {"unexpected": "object"}]:
            with self.subTest(response=type(response).__name__):
                client, _ = configured(response)
                with self.assertRaises(WCAAPIError):
                    client.list()

    def test_empty_system_trust_store_gets_verified_ca_bundle(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(context.cert_store_stats()["x509_ca"], 0)
        with patch("wca.client.ssl.create_default_context", return_value=context):
            client = WCA(secret_key=KEY)
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        handlers = [handler for handler in client._transport.opener.handlers if isinstance(handler, HTTPSHandler)]
        self.assertEqual(len(handlers), 1)
        self.assertIs(handlers[0]._context, context)

    def test_network_errors_are_classified_without_exposing_credentials(self):
        errors = [
            (URLError(ssl.SSLCertVerificationError(1, KEY)), "TLS_CERTIFICATE_ERROR"),
            (URLError(socket.gaierror(-2, KEY)), "DNS_ERROR"),
            (URLError(TimeoutError(KEY)), "TIMEOUT"),
            (URLError(ConnectionRefusedError(KEY)), "CONNECTION_ERROR"),
        ]
        for error, expected in errors:
            with self.subTest(code=expected):
                client, _ = configured(error)
                with self.assertRaises(WCAAPIError) as caught:
                    client.list()
                self.assertEqual(caught.exception.code, expected)
                self.assertNotIn(KEY, str(caught.exception))

    def test_module_api_uses_environment_and_has_no_import_side_effects(self):
        old = wca._default
        try:
            with patch.dict("os.environ", {"WCA_SUPABASE_SECRET_KEY": KEY}):
                client = wca.configure()
                client._transport.opener = ScriptedOpener([], [], [])
                self.assertEqual(wca.list(), [])
                self.assertIsNone(wca.frist())
                self.assertIsNone(wca.first())
        finally:
            wca._default = old


if __name__ == "__main__":
    unittest.main()
