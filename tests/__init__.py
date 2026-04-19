import sys
import os

# Make service.shelly.shutdown/ importable from the tests/ directory
_addon_dir = os.path.join(os.path.dirname(__file__), "..", "service.shelly.shutdown")
sys.path.insert(0, os.path.abspath(_addon_dir))
