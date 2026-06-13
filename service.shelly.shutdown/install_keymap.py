#!/usr/bin/env python3
"""
install_keymap.py  –  Automatic remote.xml Installation
========================================================
Copyright (C) 2026 Windowclaw
Licensed under GPL-2.0-or-later (see LICENSE.txt)

This script is called during addon installation to set up the remote.xml keymap.
It creates/updates the minimal remote.xml in ~/.kodi/userdata/keymaps/ without
overwriting other remote control configurations.

Usage
-----
  python3 install_keymap.py    # Installs remote.xml
  python3 install_keymap.py --uninstall    # Removes remote.xml
"""

import os
import sys
import argparse

try:
    import xbmc
    import xbmcaddon
    IN_KODI = True
except ImportError:
    IN_KODI = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ADDON_ID = "service.shelly.shutdown"
SCRIPT_NAME = "shelly_timer_cli.py"

# Remote.xml content - minimal keymap with only Power button override
REMOTE_XML_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Shelly Shutdown Timer Remote Keymap (v2.0.0) -->
<!-- Generated automatically by service.shelly.shutdown addon -->
<!-- Edit this file to add additional remote control customizations -->
<keymap>
    <remote>
        <power>
            RunScript(special://home/addons/service.shelly.shutdown/shelly_timer_cli.py)
        </power>
    </remote>
</keymap>
"""


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def log_msg(msg: str, is_error: bool = False) -> None:
    """Log to console and Kodi if available."""
    prefix = "[ERROR]" if is_error else "[INFO]"
    print(f"{prefix} {msg}", file=sys.stderr if is_error else sys.stdout)
    
    if IN_KODI:
        try:
            level = xbmc.LOGERROR if is_error else xbmc.LOGINFO
            xbmc.log(f"[{ADDON_ID}] {msg}", level=level)
        except (RuntimeError, AttributeError):
            pass


# ---------------------------------------------------------------------------
# Directory and file helpers
# ---------------------------------------------------------------------------
def get_kodi_userdata_path() -> str:
    """Get the Kodi userdata directory path."""
    if IN_KODI:
        try:
            addon = xbmcaddon.Addon()
            # Use xbmc.translatePath to get the actual path
            userdata_path = xbmc.translatePath("special://userdata")
            if userdata_path:
                return userdata_path
        except (RuntimeError, AttributeError):
            pass
    
    # Fallback: use standard Linux/macOS path
    home = os.path.expanduser("~")
    return os.path.join(home, ".kodi", "userdata")


def get_keymaps_dir() -> str:
    """Get the keymaps directory, creating it if necessary."""
    userdata = get_kodi_userdata_path()
    keymaps_dir = os.path.join(userdata, "keymaps")
    
    if not os.path.exists(keymaps_dir):
        try:
            os.makedirs(keymaps_dir, mode=0o755, exist_ok=True)
            log_msg(f"✓ Created keymaps directory: {keymaps_dir}")
        except OSError as e:
            log_msg(f"Failed to create keymaps directory: {e}", is_error=True)
            raise
    
    return keymaps_dir


def get_remote_xml_path() -> str:
    """Get the full path to remote.xml."""
    return os.path.join(get_keymaps_dir(), "remote.xml")


# ---------------------------------------------------------------------------
# Installation and uninstallation
# ---------------------------------------------------------------------------
def is_our_remote_xml(file_path: str) -> bool:
    """Check if the remote.xml file was created by this addon."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Check for our signature comment
            return "service.shelly.shutdown" in content
    except (IOError, OSError):
        return False


def install_remote_keymap() -> bool:
    """Install or update the remote.xml keymap."""
    remote_xml_path = get_remote_xml_path()
    
    try:
        # Check if remote.xml already exists
        if os.path.exists(remote_xml_path):
            # If it's ours, update it
            if is_our_remote_xml(remote_xml_path):
                log_msg(f"Updating existing remote.xml: {remote_xml_path}")
            else:
                # If it's not ours, don't overwrite it - just inform the user
                log_msg(f"⚠ remote.xml already exists (not created by this addon): {remote_xml_path}")
                log_msg("To use this addon with your remote, add this line to the <power> section:")
                log_msg(f"    RunScript(special://home/addons/{ADDON_ID}/{SCRIPT_NAME})")
                return True  # Not a failure, just user action needed
        
        # Write the remote.xml
        with open(remote_xml_path, "w", encoding="utf-8") as f:
            f.write(REMOTE_XML_CONTENT)
        
        log_msg(f"✓ Successfully installed remote keymap: {remote_xml_path}")
        log_msg("✓ Power button is now mapped to Shelly timer")
        log_msg("ℹ Restart Kodi for changes to take effect")
        return True
    
    except (IOError, OSError) as e:
        log_msg(f"Failed to install remote.xml: {e}", is_error=True)
        return False


def uninstall_remote_keymap() -> bool:
    """Remove the remote.xml keymap if it was created by us."""
    remote_xml_path = get_remote_xml_path()
    
    try:
        if not os.path.exists(remote_xml_path):
            log_msg(f"remote.xml not found: {remote_xml_path}")
            return True
        
        # Only delete if it's ours
        if is_our_remote_xml(remote_xml_path):
            os.remove(remote_xml_path)
            log_msg(f"✓ Successfully removed remote keymap: {remote_xml_path}")
            return True
        else:
            log_msg(f"⚠ remote.xml was not created by this addon, keeping it: {remote_xml_path}")
            return True
    
    except (IOError, OSError) as e:
        log_msg(f"Failed to remove remote.xml: {e}", is_error=True)
        return False


def ensure_remote_keymap() -> bool:
    """
    Ensure remote.xml exists (called at runtime).
    Creates it if missing, but doesn't overwrite existing non-addon files.
    """
    remote_xml_path = get_remote_xml_path()
    
    if os.path.exists(remote_xml_path):
        if is_our_remote_xml(remote_xml_path):
            # Already ours, nothing to do
            return True
        else:
            # Not ours, don't touch it
            return True
    
    # Create new remote.xml
    try:
        with open(remote_xml_path, "w", encoding="utf-8") as f:
            f.write(REMOTE_XML_CONTENT)
        
        if IN_KODI:
            xbmc.log(f"[{ADDON_ID}] ✓ Auto-created remote.xml: {remote_xml_path}", xbmc.LOGINFO)
        else:
            log_msg(f"✓ Auto-created remote.xml: {remote_xml_path}")
        return True
    
    except (IOError, OSError) as e:
        if IN_KODI:
            xbmc.log(f"[{ADDON_ID}] Failed to auto-create remote.xml: {e}", xbmc.LOGERROR)
        else:
            log_msg(f"Failed to auto-create remote.xml: {e}", is_error=True)
        return False


# ---------------------------------------------------------------------------
# CLI Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Install/uninstall Shelly Shutdown Timer remote keymap"
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Uninstall the remote.xml keymap instead of installing"
    )
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="Ensure remote.xml exists (lazy creation at runtime)"
    )
    
    args = parser.parse_args()
    
    try:
        if args.uninstall:
            success = uninstall_remote_keymap()
        elif args.ensure:
            success = ensure_remote_keymap()
        else:
            success = install_remote_keymap()
        
        return 0 if success else 1
    
    except Exception as e:
        log_msg(f"Unexpected error: {e}", is_error=True)
        return 2


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sys.exit(main())
