"""Single source of truth for the application version.

Read by pyproject.toml (hatch), the updater, the installer script and the UI.
v1.x kept this in three places that drifted apart -- don't reintroduce that.
"""

__version__ = "2.0.0"

APP_NAME = "Okay-Garmin"

# Fixed on purpose: "Okay Garmin" is the whole point of the project, so it is
# deliberately not configurable.
WAKE_WORD = "okay garmin"
GITHUB_OWNER = "vxnsin"
GITHUB_REPO = "Okay-Garmin"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
GITHUB_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
