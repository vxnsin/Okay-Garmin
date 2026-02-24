import os
import sys
import json
import time
import threading
from pathlib import Path
import tkinter as tk

from PIL import Image
import pystray
from pystray import MenuItem as item

import speech_recognition as sr
from pynput import keyboard
from difflib import SequenceMatcher

# Soundabspielung
try:
    import simpleaudio as sa
except ImportError:
    sa = None
    print("❌ simpleaudio nicht gefunden. Soundeffekte werden nicht abgespielt.")

# ----------------------------
# CONFIG
# ----------------------------
WAKE_WORD = "okay garmin video speichern"
COOLDOWN = 2
last_pressed = 0

CONFIG_PATH = Path(os.environ["APPDATA"]) / "GarminVoiceKey" / "config.json"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {"hotkey": ["ctrl", "alt", "f8"], "voice_enabled": True}


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


config = load_config()
current_hotkey = config.get("hotkey", ["ctrl", "alt", "f8"])
sound_enabled = config.get("sound_enabled", True)

# ----------------------------
# SOUND
# ----------------------------
def play_sound():
    if not sa:
        return
    try:
        if getattr(sys, "frozen", False):
            base = sys._MEIPASS
        else:
            base = os.path.abspath(".")
        sound_path = os.path.join(base, "sound.wav")
        if os.path.exists(sound_path):
            wave_obj = sa.WaveObject.from_wave_file(sound_path)
            wave_obj.play()
    except Exception as e:
        print("❌ Fehler beim Abspielen des Sounds:", e)

# ----------------------------
# KEY NAMING
# ----------------------------
def key_to_name(key):
    if isinstance(key, keyboard.Key):
        mapping = {
            "cmd": "windows",
            "cmd_r": "windows",
            "cmd_l": "windows",
            "alt_l": "alt",
            "alt_r": "alt",
            "ctrl_l": "ctrl",
            "ctrl_r": "ctrl",
            "shift_l": "shift",
            "shift_r": "shift",
        }
        name = str(key).replace("Key.", "")
        return mapping.get(name, name)

    if isinstance(key, keyboard.KeyCode):
        if key.char and key.char.isprintable():
            return key.char.lower()
        if key.vk:
            if 65 <= key.vk <= 90:
                return chr(key.vk).lower()
            if 48 <= key.vk <= 57:
                return chr(key.vk)
            if 112 <= key.vk <= 123:
                return f"f{key.vk - 111}"
        return f"vk_{key.vk}"

    return str(key).lower()


def hotkey_to_string(hotkey):
    return "+".join(hotkey).lower()


# ----------------------------
# GUI for Hotkey selection
# ----------------------------
def show_hotkey_window():
    win = tk.Toplevel()
    win.title("Hotkey einstellen")
    win.geometry("280x140")
    win.attributes("-topmost", True)
    win.resizable(False, False)
    win.grab_set()

    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.abspath(".")
    icon_path = os.path.join(base, "icon.ico")
    if os.path.exists(icon_path):
        win.iconbitmap(icon_path)

    tk.Label(win, text="Drücke den gewünschten Hotkey:", font=("Segoe UI", 10)).pack(pady=10)
    var = tk.StringVar(value="– warte auf Eingabe –")
    tk.Label(win, textvariable=var, font=("Segoe UI", 14, "bold"), fg="#0078d7").pack(pady=4)
    tk.Label(win, text="Modifier (Strg/Alt/Shift/Win) und eine Taste.", font=("Segoe UI", 8), fg="gray").pack()

    modifiers = set()
    current_key = [None]
    finished = [False]

    def on_press(key):
        if finished[0]:
            return
        name = key_to_name(key)
        if name in ["ctrl", "alt", "shift", "windows"]:
            modifiers.add(name)
        else:
            current_key[0] = name

        combo = list(modifiers)
        if current_key[0]:
            combo.append(current_key[0])
        var.set("+".join(combo) if combo else "– warte auf Eingabe –")

    def on_release(key):
        name = key_to_name(key)
        if current_key[0] and name == current_key[0]:
            final_hotkey = list(modifiers)
            final_hotkey.append(current_key[0])
            finished[0] = True

            config["hotkey"] = final_hotkey
            save_config(config)

            global current_hotkey
            current_hotkey = final_hotkey

            combo_str = hotkey_to_string(final_hotkey)
            var.set("Gespeichert: " + combo_str)

            try:
                icon.menu = build_menu()
                icon.update_menu()
            except:
                pass

            listener.stop()
            win.after(1000, win.destroy)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    win.protocol("WM_DELETE_WINDOW", lambda: (listener.stop(), win.destroy()))

# ----------------------------
# MAIN UI
# ----------------------------
root = tk.Tk()
root.withdraw()

# ----------------------------
# TRAY ICON
# ----------------------------
def load_tray_icon():
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.abspath(".")
    icon_path = os.path.join(base, "icon.ico")
    if not os.path.exists(icon_path):
        img = Image.new("RGB", (64, 64), color=(0, 120, 215))
        return img
    return Image.open(icon_path)


def on_quit(icon, item):
    icon.stop()
    root.after(0, root.destroy)
    os._exit(0)


def toggle_sound(icon, item):
    global sound_enabled
    sound_enabled = not sound_enabled
    config["sound_enabled"] = sound_enabled
    save_config(config)
    icon.menu = build_menu()
    icon.update_menu()

def on_change_hotkey(icon, item):
    root.after(0, show_hotkey_window)


def build_menu():
    return pystray.Menu(
        item("Hotkey ändern", on_change_hotkey),
        item(f"Soundeffekt {'✅' if sound_enabled else '❌'}", toggle_sound),
        item(f"Aktueller Hotkey: {hotkey_to_string(current_hotkey)}", lambda: None, enabled=False),
        item("Beenden", on_quit)
    )

icon = pystray.Icon("GarminVoiceKey", load_tray_icon(), "Okay Garmin - by Vensin", menu=build_menu())

# ----------------------------
# VOICE THREAD
# ----------------------------
def press_hotkey():
    combo = list(current_hotkey)
    ctrl = keyboard.Controller()

    if "ctrl" in combo:
        ctrl.press(keyboard.Key.ctrl)
    if "alt" in combo:
        ctrl.press(keyboard.Key.alt)
    if "shift" in combo:
        ctrl.press(keyboard.Key.shift)
    if "windows" in combo:
        ctrl.press(keyboard.Key.cmd)

    main_keys = [k for k in combo if k not in ["ctrl", "alt", "shift", "windows"]]
    if main_keys:
        key_name = main_keys[0]
        try:
            if len(key_name) == 1:
                ctrl.press(key_name)
                ctrl.release(key_name)
            elif key_name.startswith("vk_"):
                vk = int(key_name[3:])
                k = keyboard.KeyCode.from_vk(vk)
                ctrl.press(k)
                ctrl.release(k)
            else:
                k = getattr(keyboard.Key, key_name)
                ctrl.press(k)
                ctrl.release(k)
        except:
            pass

    if "ctrl" in combo:
        ctrl.release(keyboard.Key.ctrl)
    if "alt" in combo:
        ctrl.release(keyboard.Key.alt)
    if "shift" in combo:
        ctrl.release(keyboard.Key.shift)
    if "windows" in combo:
        ctrl.release(keyboard.Key.cmd)


def contains_wakeword(text, wake_word, threshold=0.7):
    words = text.split()
    wake_words = wake_word.split()
    n = len(wake_words)
    for i in range(len(words) - n + 1):
        segment = " ".join(words[i:i+n])
        ratio = SequenceMatcher(None, segment, wake_word).ratio()
        if ratio >= threshold:
            return True
    return False


def voice_thread():
    global last_pressed
    r = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        r.adjust_for_ambient_noise(source)
        print("🎙️ - Sprachüberwachung aktiv...")

    while True:
        try:
            with mic as source:
                audio = r.listen(source)
            text = r.recognize_google(audio, language="de-DE").lower()
            print("🗣️ Erkannt:", text)

            if contains_wakeword(text, WAKE_WORD, threshold=0.7):
                now = time.time()
                if now - last_pressed >= COOLDOWN:
                    press_hotkey()
                    last_pressed = now
                    if sound_enabled:
                        play_sound()

                    print(f"✅ Wakeword erkannt! Hotkey '{hotkey_to_string(current_hotkey)}' ausgeführt")
                else:
                    print("⏳ Cooldown aktiv")
        except sr.UnknownValueError:
            pass
        except Exception as e:
            print("❌ Fehler bei Spracherkennung:", e)
            time.sleep(1)


# ----------------------------
# START THREADS
# ----------------------------
threading.Thread(target=voice_thread, daemon=True).start()
threading.Thread(target=icon.run, daemon=True).start()

root.mainloop()