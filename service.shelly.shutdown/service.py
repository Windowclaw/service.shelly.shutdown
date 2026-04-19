"""
service.py  –  Shelly Shutdown Timer  (Kodi Service Add-on)
============================================================
Entry point for the xbmc.service extension point.

Lifecycle
---------
1. Kodi starts the service at login.
2. The service registers a custom Monitor that overrides onAbortRequested().
3. The service loop sleeps in 1-second increments (waitForAbort) so it does
   not waste CPU.
4. When Kodi requests an abort (= system shutdown / reboot), onAbortRequested
   is called. Before the shutdown completes we have ~5 seconds (Kodi's
   force-kill grace period) to fire the Shelly HTTP request.
5. If the addon is disabled in settings, the request is skipped and the
   service exits cleanly.

Thread safety
-------------
The Monitor callback (onAbortRequested) may be called from a different thread.
We use a threading.Event to signal the main loop so network I/O happens on the
main service thread, well within the 5-second window.
"""

import threading
import xbmc
import xbmcaddon
import xbmcgui

from shelly_client import (
    detect_generation,
    trigger_timer,
    validate_shelly_url,
    ShellyTimerError,
    ShellyURLError,
    SHELLY_GEN1,
    SHELLY_GEN2,
)

# ---------------------------------------------------------------------------
# Addon reference
# ---------------------------------------------------------------------------
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
def _log(msg: str, level: int = xbmc.LOGDEBUG) -> None:
    xbmc.log(f"[{ADDON_ID}] {msg}", level=level)


def _notify(message: str) -> None:
    """Show an OSD notification if enabled in settings."""
    if ADDON.getSetting("show_notifications").lower() == "true":
        xbmcgui.Dialog().notification(
            ADDON_NAME,
            message,
            xbmcgui.NOTIFICATION_INFO,
            3000,  # duration ms
        )


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------
def _read_settings() -> dict:
    """Read all relevant settings and return as a plain dict.

    Uses getSetting() (returns strings) instead of the typed getters so that
    the code works with both the legacy settings.xml format (Kodi v17+) and
    the new format.  Bool values are stored as the strings "true"/"false".
    Slider values may be stored as floats ("60.000000"), so we cast via float.
    """
    addon = xbmcaddon.Addon()

    def _bool(key: str) -> bool:
        return addon.getSetting(key).lower() == "true"

    def _int(key: str) -> int:
        try:
            return int(float(addon.getSetting(key)))
        except (ValueError, TypeError):
            return 0

    return {
        "enabled":            _bool("addon_enabled"),
        "shelly_url":         addon.getSetting("shelly_url").strip(),
        "auto_detect_gen":    _bool("auto_detect_gen"),
        "shelly_gen":         _int("shelly_gen"),
        "timer_seconds":      _int("timer_seconds"),
        "request_timeout":    _int("request_timeout"),
        "show_notifications": _bool("show_notifications"),
        "auth_enabled":       _bool("auth_enabled"),
        "auth_username":      addon.getSetting("auth_username").strip(),
        "auth_password":      addon.getSetting("auth_password"),   # never logged
    }


# ---------------------------------------------------------------------------
# Monitor subclass
# ---------------------------------------------------------------------------
class ShellyShutdownMonitor(xbmc.Monitor):
    """
    Extends xbmc.Monitor to catch the abort/shutdown event.

    When Kodi is about to exit, onAbortRequested() is called on a background
    thread.  We set an Event so the main service loop can react immediately.
    """

    def __init__(self) -> None:
        super().__init__()
        self.abort_event = threading.Event()

    def onAbortRequested(self) -> None:  # noqa: N802  (Kodi API name)
        _log("onAbortRequested received – signalling main loop", xbmc.LOGINFO)
        self.abort_event.set()

    def onSettingsChanged(self) -> None:  # noqa: N802  (Kodi API name)
        """Called by Kodi whenever the user saves changes in the addon settings UI.
        Settings are intentionally re-read at shutdown time (not cached here),
        so no action is needed – we just confirm the change in the log.
        """
        s = _read_settings()
        _log(
            "Settings updated - enabled={}, url={}, gen={}, timer={}s, auth={}".format(
                s["enabled"], s["shelly_url"], s["shelly_gen"],
                s["timer_seconds"], s["auth_enabled"]
            ),
            xbmc.LOGINFO,
        )


# ---------------------------------------------------------------------------
# Core shutdown action
# ---------------------------------------------------------------------------
def _execute_shelly_timer(settings: dict) -> None:
    """
    Validate settings, optionally auto-detect Shelly generation,
    then fire the HTTP timer request (with automatic retry).
    Called once immediately after Kodi requests an abort.
    """
    _log("Executing Shelly timer on shutdown ...", xbmc.LOGINFO)

    if not settings["enabled"]:
        _log("Addon is disabled - skipping Shelly trigger", xbmc.LOGINFO)
        _notify(ADDON.getLocalizedString(32103))
        return

    # --- URL validation (SSRF guard) ---
    raw_url = settings["shelly_url"]
    try:
        url = validate_shelly_url(raw_url)
    except ShellyURLError as exc:
        _log("URL validation failed: {}".format(exc), xbmc.LOGERROR)
        _notify(ADDON.getLocalizedString(32104))
        return

    timer_s = settings["timer_seconds"]
    gen     = settings["shelly_gen"]
    timeout = settings["request_timeout"]

    # --- Credentials (never logged) ---
    username = settings["auth_username"] if settings["auth_enabled"] else None
    password = settings["auth_password"] if settings["auth_enabled"] else None

    # --- Optional auto-detection of Shelly generation ---
    if settings.get("auto_detect_gen"):
        _log("Auto-detecting Shelly generation ...", xbmc.LOGINFO)
        gen = detect_generation(url, timeout=timeout,
                                username=username, password=password)
        _log("Auto-detected gen={}".format(gen), xbmc.LOGINFO)

    _log(
        "Trigger: url={}, gen={}, timer={}s, timeout={}s, auth={}".format(
            url, gen, timer_s, timeout, settings["auth_enabled"]),
        xbmc.LOGINFO,
    )

    try:
        result = trigger_timer(
            base_url=url,
            timer_seconds=timer_s,
            shelly_gen=gen,
            timeout=timeout,
            username=username,
            password=password,
        )
        _log("Shelly responded {}: {}".format(
            result["status"], result["body"][:200]), xbmc.LOGINFO)
        _notify(ADDON.getLocalizedString(32101).format(timer_s))

    except ShellyTimerError as exc:
        _log("Shelly request failed: {}".format(exc), xbmc.LOGERROR)
        _notify(ADDON.getLocalizedString(32102).format(str(exc)))

    except ValueError as exc:
        _log("Configuration error: {}".format(exc), xbmc.LOGERROR)
        _notify(ADDON.getLocalizedString(32102).format(str(exc)))


# ---------------------------------------------------------------------------
# Service main loop
# ---------------------------------------------------------------------------
def run() -> None:
    _log(f"Service starting (version {ADDON.getAddonInfo('version')})", xbmc.LOGINFO)

    monitor = ShellyShutdownMonitor()

    # Keep the service alive; waitForAbort returns True when Kodi is exiting.
    # Using 1-second slices lets us respond quickly without hammering the CPU.
    while not monitor.waitForAbort(1):
        pass  # Nothing to do while Kodi is running normally.

    # --- Kodi abort has been requested ---
    # Read settings at shutdown time (user may have changed them since startup).
    settings = _read_settings()
    _execute_shelly_timer(settings)

    _log("Service exiting cleanly", xbmc.LOGINFO)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run()
