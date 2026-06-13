"""
service.py  –  Shelly Shutdown Timer  (Kodi Service Add-on)
============================================================
Copyright (C) 2026 Windowclaw
Licensed under GPL-2.0-or-later (see LICENSE.txt)

Entry point for the xbmc.service extension point.

Use Case
--------
Trigger a Shelly smart plug timer ONLY when user initiates shutdown via Kodi UI
(menu or remote control). Do NOT trigger on reboot or other shutdown sources.

Lifecycle
---------
1. Kodi starts the service at login.
2. The service registers a custom Monitor that overrides onAction() and 
   onAbortRequested().
3. The service loop sleeps in 1-second increments (waitForAbort) so it does
   not waste CPU.
4. When user initiates shutdown/reboot via Kodi UI:
   a) onAction() is called FIRST with action id 13 (reboot) or 19/20 (shutdown)
      → Sets _reboot_action_detected flag
   b) onAbortRequested() is called next
      → Signals main loop to check action type and trigger timer if needed
5. Before the shutdown completes we have ~5 seconds (Kodi's force-kill grace 
   period) to fire the Shelly HTTP request.
6. If the addon is disabled in settings, the request is skipped and the
   service exits cleanly.

Scope
-----
This addon handles ONLY Kodi UI actions:
  - User presses Shutdown in Kodi menu
  - User presses Shutdown on remote control
  - User presses Reboot in Kodi menu
  - User presses Reboot on remote control

NOT handled (and not required for use case):
  - systemctl shutdown, systemctl reboot
  - Power button on system
  - SSH commands
  - cron jobs
  (These are considered out-of-scope as they don't match typical media center usage)

Thread safety
-------------
The Monitor callbacks (onAction, onAbortRequested) may be called from different 
threads. We use a threading.Event to signal the main loop so network I/O 
happens on the main service thread, well within the 5-second window.
The global _reboot_action_detected flag is set once by onAction and read once
by _is_system_reboot(), so no explicit locking is needed.
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
# Global state for action detection
# ---------------------------------------------------------------------------
# Flag to track if a reboot action was detected (set by onAction callback)
_reboot_action_detected = False

# Cache previous toggle state to detect changes (for settings refresh workaround)
# Set to False initially so first change detection works properly
_last_toggle_state = {
    "auth_enabled": False,
    "auto_detect_gen": False,
    "_initialized": False,  # Flag to track if we've initialized the state
}


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
def _log(msg: str, level: int = xbmc.LOGDEBUG) -> None:
    xbmc.log(f"[{ADDON_ID}] {msg}", level=level)


def _notify(message: str) -> None:
    """Show an OSD notification if enabled in settings."""
    try:
        if ADDON.getSetting("show_notifications").lower() == "true":
            xbmcgui.Dialog().notification(
                ADDON_NAME,
                message,
                xbmcgui.NOTIFICATION_INFO,
                3000,  # duration ms
            )
    except (RuntimeError, AttributeError):
        # Addon not available during shutdown
        pass


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------
def _trigger_settings_refresh() -> None:
    """
    Workaround for Kodi 21+ bug: enable="" conditions in settings.xml are not
    dynamically re-evaluated when boolean settings change.
    
    Smart approach: Only refresh if a toggle-field (auth_enabled, auto_detect_gen)
    has changed. This avoids annoying dialog re-opens when other settings change.
    First call initializes the state without triggering a refresh.
    
    Solution: Re-open the settings dialog immediately after saving.
    This causes settings.xml to be re-parsed and all enable conditions to be
    re-evaluated. User will see the conditional fields (username/password,
    shelly_gen) become enabled/disabled based on their toggle selections.
    """
    global _last_toggle_state
    
    try:
        current_auth = ADDON.getSetting("auth_enabled").lower() == "true"
        current_auto_detect = ADDON.getSetting("auto_detect_gen").lower() == "true"
        
        # First initialization: just store the state, don't refresh yet
        if not _last_toggle_state["_initialized"]:
            _last_toggle_state["auth_enabled"] = current_auth
            _last_toggle_state["auto_detect_gen"] = current_auto_detect
            _last_toggle_state["_initialized"] = True
            _log("Settings cache initialized (auth={}, autodetect={})".format(
                current_auth, current_auto_detect), xbmc.LOGDEBUG)
            return
        
        # Check if any toggle changed
        auth_changed = _last_toggle_state["auth_enabled"] != current_auth
        autodetect_changed = _last_toggle_state["auto_detect_gen"] != current_auto_detect
        
        # Update cache
        _last_toggle_state["auth_enabled"] = current_auth
        _last_toggle_state["auto_detect_gen"] = current_auto_detect
        
        # Only refresh if a toggle actually changed
        if auth_changed or autodetect_changed:
            _log("Toggle field changed (auth={}, autodetect={}) - refreshing settings UI".format(
                auth_changed, autodetect_changed), xbmc.LOGINFO)
            ADDON.openSettings()
        
    except Exception as exc:
        _log("Could not trigger settings refresh: {}".format(exc), xbmc.LOGWARNING)


def _read_settings() -> dict:
    """Read all relevant settings and return as a plain dict.

    Uses getSetting() (returns strings) instead of the typed getters so that
    the code works with both the legacy settings.xml format (Kodi v17+) and
    the new format.  Bool values are stored as the strings "true"/"false".
    Slider values may be stored as floats ("60.000000"), so we cast via float.
    """
    addon = ADDON

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
    Extends xbmc.Monitor to catch the abort/shutdown event AND detect
    reboot actions BEFORE the abort signal arrives.

    Kodi Action IDs:
    - ACTION_SHUTDOWN_REBOOT = 13 → User/system initiated reboot
    - ACTION_SHUTDOWN = 19, 20 → Shutdown
    
    onAction() is called BEFORE onAbortRequested(), so we can detect
    which action triggered the shutdown and set a flag accordingly.
    """

    def __init__(self) -> None:
        super().__init__()
        self.abort_event = threading.Event()

    def onAction(self, action) -> None:  # noqa: N802  (Kodi API name)
        """Called when Kodi receives an action (shutdown, reboot, etc.)
        
        This is called BEFORE onAbortRequested(), allowing us to detect
        the specific action type (reboot vs shutdown).
        """
        global _reboot_action_detected
        
        action_id = action.getId()
        
        # ACTION_SHUTDOWN_REBOOT = 13
        if action_id == 13:
            _log("✗ onAction: Detected REBOOT action (id=13)", xbmc.LOGINFO)
            _reboot_action_detected = True
        # ACTION_SHUTDOWN = 19, 20
        elif action_id in (19, 20):
            _log("✓ onAction: Detected SHUTDOWN action (id={})".format(action_id), xbmc.LOGINFO)
            _reboot_action_detected = False
        # Other actions (ignore)
        else:
            _log("onAction: Other action received (id={})".format(action_id), xbmc.LOGDEBUG)

    def onAbortRequested(self) -> None:  # noqa: N802  (Kodi API name)
        _log("onAbortRequested received – signalling main loop", xbmc.LOGINFO)
        self.abort_event.set()

    def onSettingsChanged(self) -> None:  # noqa: N802  (Kodi API name)
        """Called by Kodi whenever the user saves changes in the addon settings UI.
        This is where we handle dependency refreshes for conditional settings.
        """
        try:
            s = _read_settings()
            _log(
                "Settings updated - enabled={}, url={}, gen={}, timer={}s, auth={}".format(
                    s["enabled"], s["shelly_url"], s["shelly_gen"],
                    s["timer_seconds"], s["auth_enabled"]
                ),
                xbmc.LOGINFO,
            )
            
            # Kodi 21+ bug: enable="" conditions don't refresh after toggle changes.
            # Workaround: Force a settings re-evaluation by opening and closing the dialog.
            # This ensures conditional fields (user/password, shelly_gen) are properly enabled/disabled.
            _trigger_settings_refresh()
            
        except RuntimeError:
            _log("Settings change event received but addon not available", xbmc.LOGWARNING)


# ---------------------------------------------------------------------------
# System detection
# ---------------------------------------------------------------------------
def _is_system_reboot() -> bool:
    """
    Detect if user initiated a REBOOT action via Kodi UI.
    
    onAction() callback sets _reboot_action_detected BEFORE onAbortRequested()
    is called, so we can reliably distinguish:
    - ACTION_SHUTDOWN_REBOOT (id=13) → True (don't trigger timer)
    - ACTION_SHUTDOWN (id=19/20)    → False (trigger timer)
    
    Returns True if reboot action was detected, False for shutdown.
    """
    global _reboot_action_detected
    
    if _reboot_action_detected:
        _log("✗ Kodi reboot action detected - Shelly timer will be skipped", xbmc.LOGINFO)
        return True
    
    _log("✓ Kodi shutdown action detected", xbmc.LOGINFO)
    return False


# ---------------------------------------------------------------------------
# Core shutdown action
# ---------------------------------------------------------------------------
def _execute_shelly_timer(settings: dict) -> None:
    """
    Trigger Shelly timer ONLY when:
    - Addon is enabled in settings
    - User initiated shutdown (not reboot) via Kodi UI
    
    Skip conditions:
    - User initiated reboot (onAction detected ACTION_SHUTDOWN_REBOOT)
    - Addon is disabled in settings
    - Addon is being uninstalled (error on read_settings)
    
    Use case scope: Kodi UI actions only (menu or remote control).
    External shutdown sources (systemctl, power button, etc.) are out of scope.
    """
    _log("Abort signal received from Kodi", xbmc.LOGINFO)
    
    # --- Check if user initiated REBOOT (skip timer) ---
    if _is_system_reboot():
        _log("User initiated reboot - skipping Shelly timer", xbmc.LOGINFO)
        return
    
    # --- Addon disabled check ---
    if not settings["enabled"]:
        _log("Addon is disabled - skipping Shelly trigger", xbmc.LOGINFO)
        _notify(ADDON.getLocalizedString(32103))
        return
    
    _log("✓ Triggering Shelly timer (shutdown detected, addon enabled)", xbmc.LOGINFO)

    # --- URL validation (SSRF guard) ---
    raw_url = settings["shelly_url"]
    try:
        url_info = validate_shelly_url(raw_url)
        url = url_info["ip_url"]  # Use IP-based URL (DNS rebinding mitigation)
    except ShellyURLError as exc:
        _log("URL validation failed: {}".format(exc), xbmc.LOGERROR)
        _notify(ADDON.getLocalizedString(32104))
        return

    timer_s = settings["timer_seconds"]
    gen     = settings["shelly_gen"]
    timeout = settings["request_timeout"]
    
    # During shutdown, cap timeout to ensure Kodi doesn't kill us (it allows ~5s)
    # Use max 3 seconds to stay well within the safety window
    shutdown_timeout = min(3, timeout)

    # --- Credentials (never logged) ---
    username = settings["auth_username"] if settings["auth_enabled"] else None
    password = settings["auth_password"] if settings["auth_enabled"] else None

    # --- Optional auto-detection of Shelly generation ---
    if settings.get("auto_detect_gen"):
        _log("Auto-detecting Shelly generation ...", xbmc.LOGINFO)
        # Use SHORT timeout for auto-detection during shutdown (Kodi only gives ~5s total)
        # Fallback to Gen1 on timeout/error is handled inside detect_generation()
        autodetect_timeout = min(2, shutdown_timeout)  # Max 2 seconds for probe
        gen = detect_generation(url, timeout=autodetect_timeout,
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
            timeout=shutdown_timeout,  # ← Use capped timeout during shutdown
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

    finally:
        # Clear credentials from memory immediately after use (security: prevent memory exposure)
        if settings["auth_enabled"]:
            settings["auth_password"] = ""
            settings["auth_username"] = ""
            _log("✓ Credentials cleared from memory", xbmc.LOGDEBUG)


# ---------------------------------------------------------------------------
# Service main loop
# ---------------------------------------------------------------------------
def run() -> None:
    try:
        _log(f"Service starting (version {ADDON.getAddonInfo('version')})", xbmc.LOGINFO)
    except RuntimeError:
        _log("Service starting (version unknown - addon being uninstalled?)", xbmc.LOGINFO)

    monitor = ShellyShutdownMonitor()

    # Keep the service alive; waitForAbort returns True when Kodi is exiting.
    # Using 1-second slices lets us respond quickly without hammering the CPU.
    while not monitor.waitForAbort(1):
        pass  # Nothing to do while Kodi is running normally.

    # --- Kodi abort has been requested ---
    # Read settings at shutdown time (user may have changed them since startup).
    # Protected by try/except in case addon is being uninstalled.
    try:
        settings = _read_settings()
    except (RuntimeError, AttributeError) as exc:
        _log("Cannot read settings during abort - addon being uninstalled or unavailable: {}".format(exc), 
             xbmc.LOGWARNING)
        return
    
    _execute_shelly_timer(settings)

    _log("Service exiting cleanly", xbmc.LOGINFO)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run()
