import os
import sys
import requests
import zipfile
import io
import shutil
import subprocess
import time
import re

def get_latest_release():
    response = requests.get(
        f"https://github.com/vxnsin/Okay-Garmin/releases/latest",
        allow_redirects=True
    )

    match = re.search(r'/tag/(v[\d.]+)', response.url)
    if not match:
        print("❌ Could not detect latest version")
        sys.exit(1)

    latest_version = match.group(1)
    print(f"🔍 Latest version: {latest_version}")

    zip_url = f"https://github.com/vxnsin/Okay-Garmin/releases/download/{latest_version}/Okay-Garmin.zip"
    return zip_url


def download_and_extract(zip_url):
    print("⬇ Downloading update...")
    response = requests.get(zip_url)

    if response.status_code != 200:
        print("❌ Download failed")
        sys.exit(1)

    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        print("📦 Extracting...")
        z.extractall("update_temp")

def is_main_running():
    result = subprocess.run(
        ["tasklist"],
        capture_output=True,
        text=True
    )
    return "main.exe" in result.stdout


def wait_for_main_to_close():
    print("⏳ Waiting for main.exe to fully close...")

    while is_main_running():
        print("...still running")
        time.sleep(1)

    print("✅ main.exe is closed.")

def replace_files():
    print("♻ Replacing main.exe and update.exe...")

    base_dir = os.path.dirname(sys.executable)
    allowed_files = ["main.exe", "update.exe"]

    for file in allowed_files:
        src = os.path.join("update_temp", file)
        dst = os.path.join(base_dir, file)

        if os.path.exists(src):
            try:
                if os.path.exists(dst):
                    os.remove(dst)

                shutil.move(src, dst)
                print(f"✅ Updated {file}")

            except PermissionError:
                print(f"❌ Could not replace {file} (still in use)")
                sys.exit(1)

        else:
            print(f"⚠ {file} not found in update package")

    shutil.rmtree("update_temp")

def restart_app():
    print("🚀 Restarting...")
    subprocess.Popen(["main.exe"])
    sys.exit(0)

if __name__ == "__main__":
    print("=== Okay-Garmin Updater ===")

    time.sleep(2)

    wait_for_main_to_close()

    zip_url = get_latest_release()
    download_and_extract(zip_url)
    replace_files()
    restart_app()
