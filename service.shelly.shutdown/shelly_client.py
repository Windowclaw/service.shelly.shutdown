"""
shelly_client.py  -  Shelly HTTP API abstraction
=================================================
Copyright (C) 2026 Windowclaw
Licensed under GPL-2.0-or-later (see LICENSE.txt)

Supports:
  Gen1 (Plug, Plug S, 1, 2, ...)      -> /relay/0?turn=on&timer=<s>
  Gen2 / Gen3 (Plus Plug S, Pro, ...) -> /rpc/Switch.Set?id=0&on=true&toggle_after=<s>

Authentication
--------------
Both Gen1 and Gen2/3 (fw >= 1.0.0) support HTTP Basic Auth.
Credentials are passed via the Authorization header and are NEVER
written to the Kodi log.

Security
--------
- URL validated against private/local network allowlist (SSRF protection).
- Inline credentials in the URL (user:pass@host) are rejected; they must
  be supplied separately via the username/password parameters.

Reliability
-----------
- trigger_timer() retries once after a short delay on transient failures.
- All network calls carry an explicit timeout.
"""

import base64
import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xbmc

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ADDON_ID    = "service.shelly.shutdown"
SHELLY_GEN1 = 0
SHELLY_GEN2 = 1

_RETRY_COUNT   = 1      # one automatic retry on transient failure
_RETRY_DELAY_S = 0.5    # seconds between attempts

# Private / link-local IPv4 ranges permitted as Shelly targets (SSRF guard)
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local (Fritz!Box etc.)
    ipaddress.ip_network("127.0.0.0/8"),       # loopback (testing)
]


# ---------------------------------------------------------------------------
# Logging  (credentials are never passed to this function)
# ---------------------------------------------------------------------------
def _log(msg, level=xbmc.LOGDEBUG):
    xbmc.log("[{}] shelly_client: {}".format(ADDON_ID, msg), level=level)


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------
class ShellyURLError(ValueError):
    """Raised when the configured Shelly URL fails security validation."""


class ShellyTimerError(Exception):
    """Raised when the Shelly HTTP request fails (after all retries)."""


# ---------------------------------------------------------------------------
# Security: URL validation
# ---------------------------------------------------------------------------
def _resolve_host(hostname):
    """Return the first IPv4 address for hostname, or raise ShellyURLError."""
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
        return infos[0][4][0]
    except socket.gaierror as exc:
        raise ShellyURLError(
            "Cannot resolve hostname '{}': {}".format(hostname, exc)
        ) from exc


def validate_shelly_url(url):
    """
    Validate *url* for use as a Shelly base URL.

    Rules:
      1. Must start with http:// or https://.
      2. Must NOT contain inline credentials (user:pass@host) – they would
         appear in log output. Credentials must be supplied separately.
      3. Host must resolve to a private/link-local IPv4 address (SSRF guard).

    Returns the stripped, normalised URL (trailing slash removed).
    Raises ShellyURLError on any violation.
    """
    url = url.strip().rstrip("/")

    if not url:
        raise ShellyURLError("Shelly URL must not be empty.")

    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ShellyURLError(
            "URL scheme must be 'http' or 'https', got '{}'.".format(parsed.scheme)
        )

    if parsed.username or parsed.password:
        raise ShellyURLError(
            "Inline credentials in the URL are not supported. "
            "Use the username/password fields in the addon settings instead."
        )

    host = parsed.hostname
    if not host:
        raise ShellyURLError("URL contains no hostname.")

    ip_str = _resolve_host(host)
    ip     = ipaddress.ip_address(ip_str)

    if not any(ip in net for net in _PRIVATE_NETS):
        raise ShellyURLError(
            "Host '{}' resolves to {}, which is not a private/local address. "
            "Only devices on the local network are permitted.".format(host, ip_str)
        )

    _log("URL validated: {} -> {}".format(url, ip_str), xbmc.LOGDEBUG)
    return url


# ---------------------------------------------------------------------------
# Auth header builder
# ---------------------------------------------------------------------------
def _basic_auth_header(username, password):
    """
    Build an HTTP Basic Auth header value for the given credentials.
    Returns None when both username and password are empty/None so callers
    can skip adding the header entirely in the unauthenticated case.

    The credentials are base64-encoded but NOT logged anywhere.
    """
    u = (username or "").strip()
    p = (password or "").strip()
    if not u and not p:
        return None
    token = base64.b64encode("{}:{}".format(u, p).encode("utf-8")).decode("ascii")
    return "Basic {}".format(token)


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------
def _build_url_gen1(base_url, timer_seconds):
    """GET /relay/0?turn=on&timer=<s>  (Gen1)"""
    params = urllib.parse.urlencode({"turn": "on", "timer": str(timer_seconds)})
    return "{}/relay/0?{}".format(base_url, params)


def _build_url_gen2(base_url, timer_seconds):
    """GET /rpc/Switch.Set?id=0&on=true&toggle_after=<s>  (Gen2/3)"""
    params = urllib.parse.urlencode({
        "id": "0",
        "on": "true",
        "toggle_after": str(timer_seconds),
    })
    return "{}/rpc/Switch.Set?{}".format(base_url, params)


# ---------------------------------------------------------------------------
# Low-level HTTP helper
# ---------------------------------------------------------------------------
def _http_get(url, timeout, auth_header=None):
    """
    Perform a GET request. Returns (status_code, body_str).
    Raises ShellyTimerError on any network or HTTP error.

    auth_header : str or None – pre-built Authorization header value.
                  Never logged.
    """
    headers = {"User-Agent": "Kodi-addon/{}".format(ADDON_ID)}
    if auth_header:
        headers["Authorization"] = auth_header

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        raise ShellyTimerError("HTTP {}: {}".format(exc.code, exc.reason)) from exc
    except urllib.error.URLError as exc:
        raise ShellyTimerError("Network error: {}".format(exc.reason)) from exc
    except OSError as exc:
        raise ShellyTimerError("OS error: {}".format(exc)) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def detect_generation(base_url, timeout=5, username=None, password=None):
    """
    Auto-detect whether the Shelly at base_url is Gen1 or Gen2/3.

    Probes GET /shelly (with auth if supplied). Gen2/3 devices report
    "gen":2 or "gen":3 in the JSON body; Gen1 devices do not.

    Falls back to SHELLY_GEN1 on any error.
    Returns SHELLY_GEN1 (0) or SHELLY_GEN2 (1).
    """
    probe_url   = "{}/shelly".format(base_url.rstrip("/"))
    auth_header = _basic_auth_header(username, password)
    _log("Probing generation: GET {}".format(probe_url), xbmc.LOGINFO)
    try:
        status, body = _http_get(probe_url, timeout=timeout, auth_header=auth_header)
        _log("Probe response {}: {}".format(status, body[:200]), xbmc.LOGDEBUG)
        if status == 200:
            body_nospace = body.replace(" ", "")
            if '"gen":2' in body_nospace or '"gen":3' in body_nospace:
                _log("Detected Gen2/3 device", xbmc.LOGINFO)
                return SHELLY_GEN2
            _log("Detected Gen1 device", xbmc.LOGINFO)
            return SHELLY_GEN1
    except ShellyTimerError as exc:
        _log("Generation probe failed: {} - defaulting to Gen1".format(exc),
             xbmc.LOGWARNING)
    return SHELLY_GEN1


def trigger_timer(base_url, timer_seconds, shelly_gen=SHELLY_GEN1,
                  timeout=5, username=None, password=None):
    """
    Send the timer-start command to the Shelly device, with one automatic retry.

    Parameters
    ----------
    base_url      : str       - Validated base URL (no trailing slash).
    timer_seconds : int       - Seconds until power-off (0 = immediate).
    shelly_gen    : int       - SHELLY_GEN1 or SHELLY_GEN2.
    timeout       : int       - Per-attempt HTTP timeout in seconds.
    username      : str|None  - HTTP Basic Auth username (not logged).
    password      : str|None  - HTTP Basic Auth password (not logged).

    Returns dict { url, status, body } on success.
    Raises ShellyTimerError after all retries are exhausted.
    Raises ValueError on invalid parameter values.
    """
    if timer_seconds < 0:
        raise ValueError("timer_seconds must be >= 0, got {}".format(timer_seconds))

    if shelly_gen == SHELLY_GEN1:
        url = _build_url_gen1(base_url, timer_seconds)
    elif shelly_gen == SHELLY_GEN2:
        url = _build_url_gen2(base_url, timer_seconds)
    else:
        raise ValueError("Unknown shelly_gen value: {}".format(shelly_gen))

    auth_header = _basic_auth_header(username, password)
    auth_active = auth_header is not None

    # Log URL but never credentials
    _log("Sending timer request: {} (auth={})".format(url, auth_active), xbmc.LOGINFO)

    last_exc = None
    for attempt in range(1 + _RETRY_COUNT):
        if attempt > 0:
            _log("Retry {}/{} after {}s ...".format(
                attempt, _RETRY_COUNT, _RETRY_DELAY_S), xbmc.LOGWARNING)
            time.sleep(_RETRY_DELAY_S)
        try:
            status, body = _http_get(url, timeout, auth_header=auth_header)
            _log("Response {}: {}".format(status, body[:200]), xbmc.LOGDEBUG)
            return {"url": url, "status": status, "body": body}
        except ShellyTimerError as exc:
            last_exc = exc
            _log("Attempt {} failed: {}".format(attempt + 1, exc), xbmc.LOGWARNING)

    raise last_exc
