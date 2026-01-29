import os
import sys
import time
import threading
from pathlib import Path

import speech_recognition as sr
import keyboard
import pystray
from pystray import MenuItem as item
from PIL import Image

WAKE_WORD = "okay garmin video speichern"
COOLDOWN = 2
last_pressed = 0

def add_to_autostart():
    startup = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup"
    exe_path = sys.executable
    shortcut = startup / "GarminVoiceKey.lnk"
    startup.mkdir(parents=True, exist_ok=True)
    if not shortcut.exists():
        try:
            import pythoncom
            from win32com.shell import shell
            pythoncom.CoInitialize()
            link = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink, None,
                pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
            )
            link.SetPath(str(exe_path))
            link.SetWorkingDirectory(str(Path(exe_path).parent))
            persist_file = link.QueryInterface(pythoncom.IID_IPersistFile)
            persist_file.Save(str(shortcut), 0)
            print("✅ Autostart eingerichtet")
        except Exception as e:
            print("❌ Autostart fehlgeschlagen:", e)

add_to_autostart()

def load_tray_icon():
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    ico_path = os.path.join(base_path, "icon.ico")
    return Image.open(ico_path)

def on_quit(icon, item):
    icon.stop()
    os._exit(0)

icon = pystray.Icon(
    "GarminVoiceKey",
    load_tray_icon(),
    "Okay Garmin - by Vensin",
    menu=pystray.Menu(
        item("Beenden", on_quit)
    )
)

def voice_thread():
    global last_pressed
    r = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        r.adjust_for_ambient_noise(source)

    while True:
        try:
            with mic as source:
                audio = r.listen(source)
            text = r.recognize_google(audio, language="de-DE").lower()
            print("🗣️", text)

            if WAKE_WORD in text:
                now = time.time()
                if now - last_pressed >= COOLDOWN:
                    keyboard.press_and_release("f8")
                    last_pressed = now
                    print("✅ Wakeword erkannt! F8 gedrückt")
                else:
                    print("⏳ Cooldown aktiv")
        except sr.UnknownValueError:
            pass
        except Exception as e:
            print("❌ Fehler:", e)

threading.Thread(target=voice_thread, daemon=True).start()
icon.run()
