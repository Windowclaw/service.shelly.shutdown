"""
tests/test_shelly_client.py
===========================
Unit tests for shelly_client.py.
Run with: python3 -m unittest tests.test_shelly_client -v
No Kodi installation required – xbmc is stubbed out.
"""
import sys, os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__),
                                 "..", "service.shelly.shutdown"))


import sys
import types
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

# ---------------------------------------------------------------------------
# Stub xbmc
# ---------------------------------------------------------------------------
xbmc_stub = types.ModuleType("xbmc")
xbmc_stub.LOGDEBUG   = 0
xbmc_stub.LOGINFO    = 1
xbmc_stub.LOGWARNING = 2
xbmc_stub.LOGERROR   = 3
xbmc_stub.log = lambda msg, level=0: None
sys.modules["xbmc"] = xbmc_stub

from shelly_client import (
    validate_shelly_url, ShellyURLError,
    detect_generation, trigger_timer, ShellyTimerError,
    SHELLY_GEN1, SHELLY_GEN2,
    _build_url_gen1, _build_url_gen2,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_response(status=200, body='{"ison":true}'):
    r = MagicMock()
    r.status = status
    r.read.return_value = body.encode("utf-8")
    r.__enter__ = lambda s: s
    r.__exit__ = MagicMock(return_value=False)
    return r


# ---------------------------------------------------------------------------
# URL builder tests
# ---------------------------------------------------------------------------
class TestBuildUrlGen1(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_build_url_gen1("http://192.168.1.100", 60),
                         "http://192.168.1.100/relay/0?turn=on&timer=60")

    def test_trailing_slash_stripped_by_caller(self):
        # builders receive already-stripped URL from trigger_timer
        url = _build_url_gen1("http://192.168.1.100", 30)
        self.assertIn("timer=30", url)

    def test_zero_timer(self):
        self.assertIn("timer=0", _build_url_gen1("http://10.0.0.1", 0))

    def test_max_timer(self):
        self.assertIn("timer=600", _build_url_gen1("http://10.0.0.1", 600))


class TestBuildUrlGen2(unittest.TestCase):
    def test_basic(self):
        url = _build_url_gen2("http://192.168.1.100", 60)
        self.assertIn("/rpc/Switch.Set", url)
        self.assertIn("on=true", url)
        self.assertIn("toggle_after=60", url)
        self.assertIn("id=0", url)

    def test_zero_timer(self):
        self.assertIn("toggle_after=0", _build_url_gen2("http://10.0.0.1", 0))


# ---------------------------------------------------------------------------
# URL validation / SSRF tests
# ---------------------------------------------------------------------------
class TestValidateShellyUrl(unittest.TestCase):

    def _patch_resolve(self, ip):
        """Patch _resolve_host to return a fixed IP without DNS."""
        return patch("shelly_client._resolve_host", return_value=ip)

    def test_private_192_accepted(self):
        with self._patch_resolve("192.168.1.100"):
            result = validate_shelly_url("http://192.168.1.100")
        self.assertEqual(result, "http://192.168.1.100")

    def test_private_10_accepted(self):
        with self._patch_resolve("10.0.0.5"):
            result = validate_shelly_url("http://10.0.0.5")
        self.assertEqual(result, "http://10.0.0.5")

    def test_loopback_accepted(self):
        with self._patch_resolve("127.0.0.1"):
            result = validate_shelly_url("http://127.0.0.1")
        self.assertEqual(result, "http://127.0.0.1")

    def test_trailing_slash_stripped(self):
        with self._patch_resolve("192.168.1.1"):
            result = validate_shelly_url("http://192.168.1.1/")
        self.assertFalse(result.endswith("/"))

    def test_public_ip_rejected(self):
        with self._patch_resolve("8.8.8.8"):
            with self.assertRaises(ShellyURLError):
                validate_shelly_url("http://8.8.8.8")

    def test_ftp_scheme_rejected(self):
        with self._patch_resolve("192.168.1.1"):
            with self.assertRaises(ShellyURLError):
                validate_shelly_url("ftp://192.168.1.1")

    def test_file_scheme_rejected(self):
        with self.assertRaises(ShellyURLError):
            validate_shelly_url("file:///etc/passwd")

    def test_empty_url_rejected(self):
        with self.assertRaises(ShellyURLError):
            validate_shelly_url("")

    def test_credentials_rejected(self):
        with self._patch_resolve("192.168.1.1"):
            with self.assertRaises(ShellyURLError):
                validate_shelly_url("http://admin:secret@192.168.1.1")

    def test_hostname_resolved(self):
        # Fritz!Box-style hostname resolves to private IP
        with self._patch_resolve("192.168.178.25"):
            result = validate_shelly_url("http://shellyplug-s.fritz.box")
        self.assertIn("shellyplug-s.fritz.box", result)

    def test_dns_failure_raises(self):
        import socket
        with patch("shelly_client._resolve_host",
                   side_effect=ShellyURLError("Cannot resolve")):
            with self.assertRaises(ShellyURLError):
                validate_shelly_url("http://nonexistent.local")


# ---------------------------------------------------------------------------
# detect_generation tests
# ---------------------------------------------------------------------------
class TestDetectGeneration(unittest.TestCase):

    @patch("shelly_client._http_get")
    def test_gen2_detected_from_gen_field(self, mock_get):
        mock_get.return_value = (200, '{"type":"SHPLG2","gen":2,"mac":"AA:BB"}')
        self.assertEqual(detect_generation("http://192.168.1.100"), SHELLY_GEN2)

    @patch("shelly_client._http_get")
    def test_gen3_detected(self, mock_get):
        mock_get.return_value = (200, '{"gen":3,"id":"shellyplugsg3"}')
        self.assertEqual(detect_generation("http://192.168.1.100"), SHELLY_GEN2)

    @patch("shelly_client._http_get")
    def test_gen1_detected_no_gen_field(self, mock_get):
        mock_get.return_value = (200, '{"type":"SHPLG-S","mac":"AA:BB","fw":"1.14"}')
        self.assertEqual(detect_generation("http://192.168.1.100"), SHELLY_GEN1)

    @patch("shelly_client._http_get")
    def test_network_error_falls_back_to_gen1(self, mock_get):
        mock_get.side_effect = ShellyTimerError("Connection refused")
        self.assertEqual(detect_generation("http://192.168.1.100"), SHELLY_GEN1)

    @patch("shelly_client._http_get")
    def test_probes_correct_endpoint(self, mock_get):
        mock_get.return_value = (200, '{}')
        detect_generation("http://192.168.1.100")
        called_url = mock_get.call_args[0][0]
        self.assertEqual(called_url, "http://192.168.1.100/shelly")


# ---------------------------------------------------------------------------
# trigger_timer tests
# ---------------------------------------------------------------------------
class TestTriggerTimer(unittest.TestCase):

    @patch("shelly_client._http_get")
    def test_gen1_success(self, mock_get):
        mock_get.return_value = (200, '{"ison":true}')
        result = trigger_timer("http://192.168.1.100", 60, SHELLY_GEN1)
        self.assertEqual(result["status"], 200)
        self.assertIn("relay/0", result["url"])

    @patch("shelly_client._http_get")
    def test_gen2_success(self, mock_get):
        mock_get.return_value = (200, '{"ison":true}')
        result = trigger_timer("http://192.168.1.100", 90, SHELLY_GEN2)
        self.assertIn("Switch.Set", result["url"])

    @patch("shelly_client.time.sleep")
    @patch("shelly_client._http_get")
    def test_retries_once_on_failure(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            ShellyTimerError("timeout"),   # first attempt fails
            (200, '{"ison":true}'),         # retry succeeds
        ]
        result = trigger_timer("http://192.168.1.100", 30, SHELLY_GEN1)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(result["status"], 200)
        mock_sleep.assert_called_once()

    @patch("shelly_client.time.sleep")
    @patch("shelly_client._http_get")
    def test_raises_after_all_retries_exhausted(self, mock_get, mock_sleep):
        mock_get.side_effect = ShellyTimerError("unreachable")
        with self.assertRaises(ShellyTimerError):
            trigger_timer("http://192.168.1.100", 30, SHELLY_GEN1)
        self.assertEqual(mock_get.call_count, 2)  # 1 attempt + 1 retry

    @patch("shelly_client._http_get")
    def test_negative_timer_raises(self, _):
        with self.assertRaises(ValueError):
            trigger_timer("http://192.168.1.100", -1, SHELLY_GEN1)

    @patch("shelly_client._http_get")
    def test_unknown_gen_raises(self, _):
        with self.assertRaises(ValueError):
            trigger_timer("http://192.168.1.100", 30, shelly_gen=99)

    @patch("shelly_client._http_get")
    def test_zero_timer_valid(self, mock_get):
        mock_get.return_value = (200, '{"ison":true}')
        result = trigger_timer("http://192.168.1.100", 0, SHELLY_GEN1)
        self.assertIn("timer=0", result["url"])




# ---------------------------------------------------------------------------
# Auth header tests
# ---------------------------------------------------------------------------
class TestBasicAuthHeader(unittest.TestCase):

    def test_returns_none_when_both_empty(self):
        from shelly_client import _basic_auth_header
        self.assertIsNone(_basic_auth_header(None, None))
        self.assertIsNone(_basic_auth_header("", ""))
        self.assertIsNone(_basic_auth_header("  ", "  "))

    def test_correct_base64_encoding(self):
        from shelly_client import _basic_auth_header
        import base64
        header = _basic_auth_header("admin", "secret")
        self.assertIsNotNone(header)
        self.assertTrue(header.startswith("Basic "))
        decoded = base64.b64decode(header[6:]).decode("utf-8")
        self.assertEqual(decoded, "admin:secret")

    def test_username_only(self):
        from shelly_client import _basic_auth_header
        header = _basic_auth_header("admin", "")
        self.assertIsNotNone(header)

    def test_special_characters_in_password(self):
        from shelly_client import _basic_auth_header
        import base64
        header = _basic_auth_header("admin", "p@ss:w0rd!")
        decoded = base64.b64decode(header[6:]).decode("utf-8")
        self.assertEqual(decoded, "admin:p@ss:w0rd!")


class TestHttpGetWithAuth(unittest.TestCase):

    @patch("shelly_client.urllib.request.urlopen")
    def test_auth_header_sent(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from shelly_client import _http_get
        _http_get("http://192.168.1.1/test", timeout=5,
                  auth_header="Basic dXNlcjpwYXNz")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("Authorization", req.headers)
        self.assertEqual(req.headers["Authorization"], "Basic dXNlcjpwYXNz")

    @patch("shelly_client.urllib.request.urlopen")
    def test_no_auth_header_when_none(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from shelly_client import _http_get
        _http_get("http://192.168.1.1/test", timeout=5, auth_header=None)
        req = mock_urlopen.call_args[0][0]
        self.assertNotIn("Authorization", {k.lower(): v
                                            for k, v in req.headers.items()})


class TestTriggerTimerWithAuth(unittest.TestCase):

    @patch("shelly_client._http_get")
    def test_credentials_passed_to_http_get(self, mock_get):
        mock_get.return_value = (200, '{"ison":true}')
        trigger_timer("http://192.168.1.1", 30, SHELLY_GEN1,
                      username="admin", password="secret")
        _, kwargs = mock_get.call_args
        auth = kwargs.get("auth_header") or mock_get.call_args[0][2]
        self.assertIsNotNone(auth)
        self.assertIn("Basic", auth)

    @patch("shelly_client._http_get")
    def test_no_auth_when_no_credentials(self, mock_get):
        mock_get.return_value = (200, '{"ison":true}')
        trigger_timer("http://192.168.1.1", 30, SHELLY_GEN1)
        # auth_header should be None -> not in headers
        call_args = mock_get.call_args
        auth_header = call_args[1].get("auth_header") if call_args[1] else None
        if auth_header is None and len(call_args[0]) > 2:
            auth_header = call_args[0][2]
        self.assertIsNone(auth_header)

    @patch("shelly_client._http_get")
    def test_401_raises_shelly_timer_error(self, mock_get):
        mock_get.side_effect = ShellyTimerError("HTTP 401: Unauthorized")
        with self.assertRaises(ShellyTimerError) as ctx:
            trigger_timer("http://192.168.1.1", 30, SHELLY_GEN1,
                          username="admin", password="wrong")
        self.assertIn("401", str(ctx.exception))


class TestDetectGenerationWithAuth(unittest.TestCase):

    @patch("shelly_client._http_get")
    def test_auth_forwarded_to_probe(self, mock_get):
        mock_get.return_value = (200, '{"type":"SHPLG-S"}')
        detect_generation("http://192.168.1.1", timeout=5,
                          username="admin", password="pass")
        call_args = mock_get.call_args
        auth_header = call_args[1].get("auth_header")
        self.assertIsNotNone(auth_header)
        self.assertIn("Basic", auth_header)

if __name__ == "__main__":
    unittest.main()
