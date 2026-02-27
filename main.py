import os
import sys
import json
import threading
import time
import re
from turtle import delay

import requests
import webview
import pystray
from pystray import MenuItem as item
from PIL import Image
import speech_recognition as sr
from pynput import keyboard
from difflib import SequenceMatcher
import tkinter as tk
from tkinter import filedialog
import winsound
import winreg
import shutil
from winotify import Notification
import subprocess

sys.stdout.reconfigure(encoding="utf-8")

# ----------------------------
# PATH SETUP
# ----------------------------

BASE_PATH = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_PATH, "config.json")
SOUND_PATH = os.path.join(BASE_PATH, "sounds")

APP_VERSION = "v1.2"

# ----------------------------
# DEFAULT CONFIG
# ----------------------------

default_config = {
    "sound_enabled": True,
    "voice_commands": [
        {
            "command": "video speichern",
            "type": "hotkey",
            "value": "f8",
            "delay": 0
        }
    ]
}

config = {}

def load_config():
    global config
    if not os.path.exists(CONFIG_PATH):
        config = default_config.copy()
        save_config()
        print("📄 Neue config.json erstellt")
    else:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except:
            config = default_config.copy()
            save_config()
            print("⚠️ Config defekt – neu erstellt")

def save_config():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def set_autostart(enable=True):
    path = sys.executable
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, "Okay-Garmin", 0, winreg.REG_SZ, path)
        else:
            try:
                winreg.DeleteValue(key, "Okay-Garmin")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        print(f"Autostart {'aktiviert' if enable else 'deaktiviert'}")
    except Exception as e:
        print("❌ Autostart Fehler:", e)

def add_to_startup(enable=True):
    startup_dir = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
    exe_path = sys.executable
    shortcut_path = os.path.join(startup_dir, "Okay-Garmin.lnk")
    
    if enable:
        # Benutze winshell oder pywin32 für echte Shortcuts
        try:
            import pythoncom
            from win32com.shell import shell, shellcon
            shortcut = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink, None,
                pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
            )
            shortcut.SetPath(exe_path)
            shortcut.SetDescription("Okay-Garmin Autostart")
            persist_file = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
            persist_file.Save(shortcut_path, 0)
        except Exception as e:
            print("❌ Startup-Shortcut Fehler:", e)
    else:
        if os.path.exists(shortcut_path):
            os.remove(shortcut_path)

# ----------------------------
# GLOBAL STATE
# ----------------------------

WAKE_WORD = "okay garmin"
COOLDOWN = 2
last_trigger = 0
waiting_for_command = False

window = None
tray_icon = None


def run_path(path):
    if path.lower().endswith(".bat"):
        # Batch über cmd ausführen
        subprocess.Popen(["cmd", "/c", path], shell=True)
    else:
        # Normale Datei öffnen
        os.startfile(path)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = BASE_PATH

    return os.path.join(base_path, relative_path)

# ----------------------------
# SOUND
# ----------------------------

def play_sound(filename):
    if not config.get("sound_enabled", True):
        return
    try:
        path = os.path.join(SOUND_PATH, filename)
        if os.path.exists(path):
            winsound.PlaySound(path, winsound.SND_ASYNC | winsound.SND_FILENAME)
        else:
            print(f"❌ Sound nicht gefunden: {path}")
    except Exception as e:
        print("❌ Sound Fehler:", e)


# ----------------------------
# HOTKEY EXECUTION
# ----------------------------

def press_hotkey(combo_string):
    keys = combo_string.lower().split("+")
    controller = keyboard.Controller()

    key_map = {
        "ctrl": keyboard.Key.ctrl,
        "alt": keyboard.Key.alt,
        "shift": keyboard.Key.shift,
        "windows": keyboard.Key.cmd
    }

    modifiers = [key_map[k] for k in keys if k in key_map]
    main_key = next((k for k in keys if k not in key_map), None)

    for m in modifiers:
        controller.press(m)

    if main_key:
        try:
            if len(main_key) == 1:
                controller.press(main_key)
                controller.release(main_key)
            elif main_key.startswith("f"):
                f = getattr(keyboard.Key, main_key)
                controller.press(f)
                controller.release(f)
        except:
            pass

    for m in reversed(modifiers):
        controller.release(m)

# ----------------------------
# FUZZY MATCHING
# ----------------------------

def fuzzy_contains(text, phrase, threshold=0.7):
    words = text.split()
    phrase_words = phrase.split()
    n = len(phrase_words)

    for i in range(len(words) - n + 1):
        segment = " ".join(words[i:i+n])
        if SequenceMatcher(None, segment, phrase).ratio() >= threshold:
            return True
    return False


# ----------------------------
# VOICE LOOP
# ----------------------------


def voice_loop():
    global last_trigger, waiting_for_command

    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    with mic as source:
        recognizer.adjust_for_ambient_noise(source)

    print("🎙 Sprachüberwachung aktiv...")

    while True:
        try:
            with mic as source:
                audio = recognizer.listen(source)

            text = recognizer.recognize_google(audio, language="de-DE").lower()
            print("🗣 Erkannt:", text)

            now = time.time()
            if now - last_trigger < COOLDOWN:
                continue

            if not waiting_for_command and fuzzy_contains(text, WAKE_WORD):
                play_sound("trigger.wav")
                waiting_for_command = True
                last_trigger = now
                print("✅ Wakeword erkannt")

            elif waiting_for_command:
                executed = False

                for cmd in config.get("voice_commands", []):
                    if fuzzy_contains(text, cmd["command"]):
                        play_sound("action.wav")
                        delay_sec  = cmd.get("delay", 0)

                        if delay_sec  > 0:
                            print(f"⏳ Warte {delay_sec} Sekunden vor Ausführung...")
                            time.sleep(delay_sec)

                        if cmd["type"] == "hotkey":
                            press_hotkey(cmd["value"])

                        elif cmd["type"] in ["file", "folder", "run"]:
                            if os.path.exists(cmd["value"]):
                                run_path(cmd["value"])

                        executed = True
                        print(f"🎯 Befehl '{cmd['command']}' ausgeführt")
                        break

                if not executed:
                    print("❌ Unbekannter Befehl")

                waiting_for_command = False
                last_trigger = now

        except sr.UnknownValueError:
            pass
        except Exception as e:
            print("❌ Voice Fehler:", e)
            time.sleep(1)


# ----------------------------
# WEBVIEW API
# ----------------------------

class Api:

    def get_config(self):
        return config

    def save_config(self, new_config):
        global config
        config = new_config
        save_config()
        print("💾 Config gespeichert")
        return {"status": "ok"}

    def pick_path(self, type_):
        root = tk.Tk()
        root.withdraw()
        path = None

        try:
            if type_ in ["file", "run"]:
                path = filedialog.askopenfilename()
            elif type_ == "folder":
                path = filedialog.askdirectory()
        finally:
            root.destroy()

        return path

    def get_version(self):
        try:
            response = requests.get(
                "https://github.com/vxnsin/Okay-Garmin/releases/latest",
                timeout=5,
                allow_redirects=True
            )

            match = re.search(r'/tag/(v[\d.]+)', response.url)
            latest = match.group(1) if match else APP_VERSION

            return {
                "current": APP_VERSION,
                "latest": latest,
                "update_available": latest != APP_VERSION
            }

        except:
            return {
                "current": APP_VERSION,
                "latest": APP_VERSION,
                "update_available": False
            }
    def get_autostart(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "Okay-Garmin")
            winreg.CloseKey(key)
            return os.path.exists(value) or value == sys.executable
        except FileNotFoundError:
            return False
        except Exception as e:
            print("❌ Autostart Check Fehler:", e)
            return False

    def set_autostart(self, enable: bool):
        set_autostart(enable)
        return {"status": "ok", "enabled": enable}
    
    def run_updater(self):
        base_dir = os.path.dirname(sys.executable)
        updater_path = os.path.join(base_dir, "update.exe")

        if os.path.exists(updater_path):
            subprocess.Popen([updater_path])
            os._exit(0) 
        return {"status": "error"}
    
# ----------------------------
# TRAY ICON
# ----------------------------

def load_icon():
    path = resource_path("icon.ico")
    return Image.open(path)


def open_settings(icon=None, item=None):
    global window
    if window:
        window.show()
        window.restore()


def on_quit(icon, item):
    icon.stop()
    if window:
        try:
            window.destroy()
        except:
            pass
    os._exit(0)



def build_menu():
    return pystray.Menu(
        item("Made by Vensin", lambda: None, enabled=False),
        item("Einstellungen", open_settings),
        item("Beenden", on_quit)
    )


# ----------------------------
# WEBVIEW
# ----------------------------

def create_window():
    global window

    html_path = resource_path(os.path.join("web", "index.html"))

    window = webview.create_window(
        "Okay-Garmin Einstellungen",
        html_path,
        js_api=Api(),
        width=900,
        height=600,
        hidden=True,

    )

    def on_closing():
        window.hide()
        return False

    window.events.closing += on_closing

    return window


def check_for_updates():
    try:
        response = requests.get(
            "https://github.com/vxnsin/Okay-Garmin/releases/latest",
            timeout=5,
            allow_redirects=True
        )

        match = re.search(r'/tag/(v[\d.]+)', response.url)
        if not match:
            return

        latest_version = match.group(1)

        if latest_version != APP_VERSION:
            print(f"🆕 Update verfügbar: {latest_version}")

            toast = Notification(
                app_id="Okay-Garmin",
                title="Update verfügbar 🚀",
                msg=f"Neue Version {latest_version} ist verfügbar.",
                duration="short"
            )

            toast.show()

    except Exception as e:
        print("❌ Update Check Fehler:", e)

# ----------------------------
# START
# ----------------------------

if __name__ == "__main__":
    load_config()

    if getattr(sys, "frozen", False): 
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ
            )
            try:
                value, _ = winreg.QueryValueEx(key, "Okay-Garmin")
                print("✅ Autostart bereits gesetzt")
            except FileNotFoundError:
                set_autostart(True)
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            print("❌ Autostart Check Fehler:", e)

    create_window()

    tray_icon = pystray.Icon(
        "Okay-Garmin",
        load_icon(),
        "Okay-Garmin",
        menu=build_menu()
    )

    threading.Thread(target=tray_icon.run, daemon=True).start()
    threading.Thread(target=voice_loop, daemon=True).start()
    threading.Thread(target=check_for_updates, daemon=True).start()

    print("🚀 Okay-Garmin gestartet")

    try:
        webview.start(debug=False, menu=False)
    except TypeError:
        webview.start(debug=False)