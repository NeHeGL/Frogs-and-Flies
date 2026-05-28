# Frogs and Flies - Configuration File

import os
import sys
import json

# Configuration file path - always next to the exe/script, not inside the bundle
def _get_config_path():
    """Return the config file path next to the exe (or script in dev mode)."""
    if hasattr(sys, '_MEIPASS'):
        # Running as PyInstaller bundle - use the folder containing the exe
        return os.path.join(os.path.dirname(sys.executable), "frogs and flies.cfg")
    # Running as a script - use the folder containing config.py
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "frogs and flies.cfg")

CONFIG_FILE = _get_config_path()

# Default settings
DEFAULT_CONFIG = {
    "PLAYER_0_EASY_MODE": True,   # Left frog (Arrow keys) - Easy by default
    "PLAYER_1_EASY_MODE": True,   # Right frog (WASD) - Easy by default
    "FULLSCREEN": False,
    "RESIZABLE": True,
    "CRT": True,                  # CRT effect on by default (toggle with C key)
    "JOYSTICK_P0": -1,            # Joystick index for Player 0 (-1 = keyboard only)
    "JOYSTICK_P1": -1             # Joystick index for Player 1 (-1 = keyboard only)
}

def load_config():
    """Load configuration from file, or create default if it doesn't exist."""
    global PLAYER_0_EASY_MODE, PLAYER_1_EASY_MODE, FULLSCREEN, RESIZABLE, CRT
    global JOYSTICK_P0, JOYSTICK_P1

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                PLAYER_0_EASY_MODE = config.get("PLAYER_0_EASY_MODE", DEFAULT_CONFIG["PLAYER_0_EASY_MODE"])
                PLAYER_1_EASY_MODE = config.get("PLAYER_1_EASY_MODE", DEFAULT_CONFIG["PLAYER_1_EASY_MODE"])
                FULLSCREEN = config.get("FULLSCREEN", DEFAULT_CONFIG["FULLSCREEN"])
                RESIZABLE = config.get("RESIZABLE", DEFAULT_CONFIG["RESIZABLE"])
                # Support both old "SCANLINES" key and new "CRT" key for backwards compat
                CRT = config.get("CRT", config.get("SCANLINES", DEFAULT_CONFIG["CRT"]))
                JOYSTICK_P0 = config.get("JOYSTICK_P0", DEFAULT_CONFIG["JOYSTICK_P0"])
                JOYSTICK_P1 = config.get("JOYSTICK_P1", DEFAULT_CONFIG["JOYSTICK_P1"])
                print(f"Configuration loaded from {CONFIG_FILE}")
        except Exception as e:
            print(f"Error loading config: {e}, using defaults")
            PLAYER_0_EASY_MODE = DEFAULT_CONFIG["PLAYER_0_EASY_MODE"]
            PLAYER_1_EASY_MODE = DEFAULT_CONFIG["PLAYER_1_EASY_MODE"]
            FULLSCREEN = DEFAULT_CONFIG["FULLSCREEN"]
            RESIZABLE = DEFAULT_CONFIG["RESIZABLE"]
            CRT = DEFAULT_CONFIG["CRT"]
            JOYSTICK_P0 = DEFAULT_CONFIG["JOYSTICK_P0"]
            JOYSTICK_P1 = DEFAULT_CONFIG["JOYSTICK_P1"]
            save_config()
    else:
        # File doesn't exist, create it with defaults
        print(f"{CONFIG_FILE} not found, creating with default settings")
        PLAYER_0_EASY_MODE = DEFAULT_CONFIG["PLAYER_0_EASY_MODE"]
        PLAYER_1_EASY_MODE = DEFAULT_CONFIG["PLAYER_1_EASY_MODE"]
        FULLSCREEN = DEFAULT_CONFIG["FULLSCREEN"]
        RESIZABLE = DEFAULT_CONFIG["RESIZABLE"]
        CRT = DEFAULT_CONFIG["CRT"]
        JOYSTICK_P0 = DEFAULT_CONFIG["JOYSTICK_P0"]
        JOYSTICK_P1 = DEFAULT_CONFIG["JOYSTICK_P1"]
        save_config()

def save_config():
    """Save current configuration to file."""
    config = {
        "PLAYER_0_EASY_MODE": PLAYER_0_EASY_MODE,
        "PLAYER_1_EASY_MODE": PLAYER_1_EASY_MODE,
        "FULLSCREEN": FULLSCREEN,
        "RESIZABLE": RESIZABLE,
        "CRT": CRT,
        "JOYSTICK_P0": JOYSTICK_P0,
        "JOYSTICK_P1": JOYSTICK_P1
    }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"Configuration saved to {CONFIG_FILE}")
    except Exception as e:
        print(f"Error saving config: {e}")

# Initialize configuration variables
PLAYER_0_EASY_MODE = DEFAULT_CONFIG["PLAYER_0_EASY_MODE"]
PLAYER_1_EASY_MODE = DEFAULT_CONFIG["PLAYER_1_EASY_MODE"]
FULLSCREEN = DEFAULT_CONFIG["FULLSCREEN"]
RESIZABLE = DEFAULT_CONFIG["RESIZABLE"]
CRT = DEFAULT_CONFIG["CRT"]
JOYSTICK_P0 = DEFAULT_CONFIG["JOYSTICK_P0"]
JOYSTICK_P1 = DEFAULT_CONFIG["JOYSTICK_P1"]

# Load configuration on module import
load_config()
