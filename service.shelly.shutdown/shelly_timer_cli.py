#!/usr/bin/env python3
"""
shelly_timer_cli.py  –  Shelly Timer CLI Launcher for remote.xml
==================================================================
Copyright (C) 2026 Windowclaw
Licensed under GPL-2.0-or-later (see LICENSE.txt)

Purpose
-------
This script is designed to be called from Kodi's remote.xml <power> action.
It reads the Shelly configuration from the addon settings and triggers the
Shelly timer BEFORE initiating the system shutdown.

Usage from remote.xml
---------------------
Add this to ~/.kodi/userdata/keymaps/remote.xml in the <power> section:

    <power>RunScript(special://home/addons/service.shelly.shutdown/shelly_timer_cli.py)</power>

Or using a shortcut if available:

    <power>RunScript(~/.kodi/addons/service.shelly.shutdown/shelly_timer_cli.py)</power>

Behavior
--------
1. Load Shelly configuration from addon settings
2. Trigger Shelly timer with configured delay
3. Show OSD notification
4. Return immediately (does not block shutdown - Kodi will handle it)

Note: The actual system shutdown is handled by Kodi's default shutdown logic,
which processes after the script returns. The small delay (timer_seconds)
allows the Shelly to receive the command before power loss.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xbmc
import xbmcaddon

# Try to import shelly_client from the same directory
try:
    from shelly_client import (
        detect_generation,
        trigger_timer,
        validate_shelly_url,
        ShellyTimerError,
        ShellyURLError,
        SHELLY_GEN1,
        SHELLY_GEN2,
    )
except ImportError:
    # Fallback: add the script's directory to sys.path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    from shelly_client import (
        detect_generation,
        trigger_timer,
        validate_shelly_url,
        ShellyTimerError,
        ShellyURLError,
        SHELLY_GEN1,
        SHELLY_GEN2,
    )

# Import keymap installer for lazy setup
try:
    from install_keymap import ensure_remote_keymap
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    from install_keymap import ensure_remote_keymap

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
    """Show an OSD notification."""
    try:
        if ADDON.getSetting("show_notifications").lower() == "true":
            xbmcgui.Dialog().notification(
                ADDON_NAME,
                message,
                xbmcgui.NOTIFICATION_INFO,
                3000,  # duration ms
            )
    except (RuntimeError, AttributeError, NameError):
        pass


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------
def _read_settings() -> dict:
    """Read all relevant settings and return as a plain dict."""
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
# Main execution
# ---------------------------------------------------------------------------
def trigger_shelly_from_remote() -> None:
    """
    Trigger Shelly timer when called from remote.xml <power> action.
    
    This function:
    1. Ensures remote.xml is installed (auto-setup on first run)
    2. Reads addon configuration
    3. Validates the Shelly URL
    4. Sends the timer request to the Shelly device
    5. Shows notification on completion
    
    Returns immediately after sending the request (non-blocking).
    """
    # --- Ensure remote.xml is properly set up (lazy initialization) ---
    try:
        if not ensure_remote_keymap():
            _log("Warning: Could not ensure remote.xml, but continuing anyway", xbmc.LOGWARNING)
    except Exception as e:
        _log(f"Warning during remote.xml setup: {e}", xbmc.LOGWARNING)
    
    _log("Power button handler: Triggering Shelly timer", xbmc.LOGINFO)
    
    # --- Read settings ---
    try:
        settings = _read_settings()
    except (RuntimeError, AttributeError) as exc:
        _log(f"Cannot read settings: {exc}", xbmc.LOGERROR)
        return
    
    # --- Check if enabled ---
    if not settings["enabled"]:
        _log("Addon is disabled - skipping Shelly trigger", xbmc.LOGINFO)
        try:
            _notify(ADDON.getLocalizedString(32103))
        except AttributeError:
            pass
        return
    
    _log("✓ Power button detected - triggering Shelly timer", xbmc.LOGINFO)
    
    # --- URL validation (SSRF guard) ---
    raw_url = settings["shelly_url"]
    try:
        url_info = validate_shelly_url(raw_url)
        url = url_info["ip_url"]  # Use IP-based URL
    except ShellyURLError as exc:
        _log(f"URL validation failed: {exc}", xbmc.LOGERROR)
        try:
            _notify(ADDON.getLocalizedString(32104))
        except AttributeError:
            pass
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
        _log(f"Auto-detected gen={gen}", xbmc.LOGINFO)
    
    _log(
        f"Trigger: url={url}, gen={gen}, timer={timer_s}s, timeout={timeout}s, auth={settings['auth_enabled']}",
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
        _log(f"Shelly responded {result['status']}: {result['body'][:200]}", xbmc.LOGINFO)
        try:
            _notify(ADDON.getLocalizedString(32101).format(timer_s))
        except (AttributeError, IndexError):
            pass
    
    except ShellyTimerError as exc:
        _log(f"Shelly request failed: {exc}", xbmc.LOGERROR)
        try:
            _notify(ADDON.getLocalizedString(32102).format(str(exc)))
        except (AttributeError, IndexError):
            pass
    
    except ValueError as exc:
        _log(f"Configuration error: {exc}", xbmc.LOGERROR)
        try:
            _notify(ADDON.getLocalizedString(32102).format(str(exc)))
        except (AttributeError, IndexError):
            pass
    
    finally:
        # Clear credentials from memory immediately after use
        if settings["auth_enabled"]:
            settings["auth_password"] = ""
            settings["auth_username"] = ""
            _log("✓ Credentials cleared from memory", xbmc.LOGDEBUG)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    _log(f"Shelly Timer CLI starting (version {ADDON.getAddonInfo('version')})", xbmc.LOGINFO)
    trigger_shelly_from_remote()
    _log("Shelly Timer CLI finished", xbmc.LOGINFO)
