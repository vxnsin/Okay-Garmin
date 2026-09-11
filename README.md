<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wordmark-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/wordmark-light.svg">
  <img src="assets/wordmark-dark.svg" alt="Okay-Garmin" width="380">
</picture>

**Say _“Okay Garmin”_, then tell your PC what to do.**
Voice control for Windows that runs entirely on your machine — no cloud, no account, no API key.

[![Release](https://img.shields.io/github/v/release/vxnsin/Okay-Garmin?style=flat-square&color=6366f1)](https://github.com/vxnsin/Okay-Garmin/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/vxnsin/Okay-Garmin/total?style=flat-square&color=8b5cf6)](https://github.com/vxnsin/Okay-Garmin/releases)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-informational?style=flat-square)
![Offline](https://img.shields.io/badge/speech-100%25%20offline-34d399?style=flat-square)

</div>

---

## What it does

Say the wake word, say a command, and Okay-Garmin presses a key, opens a file, starts a program, skips a track, or puts on a song.

```
"Okay Garmin"  →  "Video speichern"          →  presses F8
"Okay Garmin"  →  "spiel Bohemian Rhapsody"  →  Spotify starts playing, cover appears on screen
"Okay Garmin"  →  "nächster Song"            →  next track, in any player
```

Everything about recognition happens locally. v1 sent your microphone to Google's web speech API and stopped working without internet; v2 does not talk to anyone about what you say.

## Highlights

| | |
|---|---|
| 🔒 **Fully offline** | Vosk listens for the wake word, Whisper transcribes the command. Nothing leaves your PC. |
| ⚡ **Light on the machine** | The wake word runs against a restricted grammar — a few percent of one core while idle. Whisper only wakes up after you do. |
| 🎙️ **Push-to-talk** | Hold a key instead of saying the wake word. Useful in voice chat. |
| 🖥️ **On-screen display** | A small HUD shows what it heard and what it matched — drag it anywhere, scale it to taste. |
| 🎵 **Spotify & media keys** | `spiel {}` plays a song, album or playlist and shows the artwork. Media-key commands work with any player, no account needed. |
| 🌍 **German & English** | Interface in both, chosen during installation and switchable any time. |
| 📦 **Installer & updater** | Proper setup, Start-menu entry, uninstaller, and one-click updates with checksum verification. |

## Install

Download **`Okay-Garmin-Setup-x.y.z.exe`** from the [latest release](https://github.com/vxnsin/Okay-Garmin/releases/latest) and run it.

It installs per user (no administrator needed), asks whether to start with Windows, and lets you pick German or English.

> **First start downloads about 190 MB of speech models**
> `vosk-model-small-de` (~45 MB) for the wake word and `faster-whisper base` (~145 MB) for commands, into `%APPDATA%\Okay-Garmin\models`. This happens once. After that everything is offline.

## Using it

Open the settings from the tray icon.

**Commands** — each has a spoken phrase, optional alternative wordings, and an action:

| Action | What it does |
|---|---|
| Hotkey | Presses a key combination (`f8`, `ctrl+shift+s`, `mediaplay`, …) |
| Media key | Play/pause, next, previous, volume, mute — works with any player |
| Spotify | 19 actions: play by name, queue, shuffle, repeat, like, volume, what's playing |
| File / Folder / Program | Opens it |

Write `{}` in a phrase to leave a gap for free text:

```
spiel {}                        →  "spiel Tocotronic"  puts on Tocotronic
mach {} an                      →  "mach Deep Focus an"  starts that playlist
stell {} in die warteschlange   →  "stell Africa von Toto in die warteschlange"
```

**The wake word is fixed at “Okay Garmin”** — that is the point of the project.

### What ships preconfigured

These exist after installation. The media ones work immediately; the Spotify ones
need a connection (below).

| Say | What happens |
|---|---|
| „spiel {}“ · „spiele {}“ · „mach {} an“ | Plays that song, album, artist or playlist |
| „stell {} in die warteschlange“ | Queues a track instead of interrupting |
| „wie heißt der song“ · „was läuft gerade“ · „was für ein song ist das“ | Shows title, artist and cover |
| „song merken“ · „zu lieblingssongs hinzufügen“ · „das gefällt mir“ | Adds the current track to your liked songs |
| „shuffle an“ · „shuffle aus“ · „zufallswiedergabe an/aus“ | Shuffle |
| „wiederholen an“ · „wiederholen aus“ | Repeat the playlist, or stop repeating |
| „musik pause“ · „stopp die musik“ | Play/pause, any player |
| „nächster song“ · „skip“ · „letzter song“ | Skip, any player |
| „video speichern“ | Presses F8 |

Not enabled by default, but available in the dropdown: toggle shuffle, repeat a
single track, cycle repeat, remove from liked songs, and Spotify's own volume up
and down (separate from the system volume).

Edit, rename or delete any of them — they are only a starting point.

### Spotify

Media-key commands need nothing at all. Playing a *specific* song by name needs a Spotify connection:

1. Create an app at the [Spotify developer dashboard](https://developer.spotify.com/dashboard).
2. Add `http://127.0.0.1:8888/callback` as a redirect URI.
3. Paste the client ID into **Music → Client ID** and press **Connect**.

Authorisation uses PKCE, so there is no client secret to store. Tokens live in `%APPDATA%\Okay-Garmin\spotify.json`, separate from `config.json` so the settings file stays safe to attach to a bug report.

> Starting playback is a **Spotify Premium** feature, and Spotify has to be running on some device. Without Premium, use the media-key commands.

Scopes requested: playback state, playback control, currently playing, and your
library (liking a song needs it). If you connected before v2.1 you have to press
**Connect** once more — the older grant has no library access.

## How it works

Two stages, because one model cannot be both cheap enough to run forever and good enough to understand a sentence:

```
microphone ─┬─→ Vosk, restricted to "okay garmin"        (always on, very cheap)
            │        └─ wake word hit
            └─→ record until 0.8 s of silence
                     └─→ faster-whisper base, int8, CPU  (only now, ~0.3 s)
                              └─→ fuzzy match against your commands
                                       └─→ press keys / open / play
```

Restricting the Vosk grammar to the wake word plus `[unk]` is what makes stage one affordable — it decodes against two options instead of a full vocabulary, which also makes false triggers rare.

## Where things live

| | |
|---|---|
| Program | `%LOCALAPPDATA%\Programs\Okay-Garmin` |
| Settings | `%APPDATA%\Okay-Garmin\config.json` |
| Logs | `%APPDATA%\Okay-Garmin\logs\okay-garmin.log` |
| Models | `%APPDATA%\Okay-Garmin\models` |

Uninstalling keeps `%APPDATA%\Okay-Garmin` unless you say otherwise, so your commands survive a reinstall.

## Building from source

Needs [uv](https://docs.astral.sh/uv/). No system Python required.

```powershell
git clone https://github.com/vxnsin/Okay-Garmin.git
cd Okay-Garmin
uv sync --extra build

uv run python -m okay_garmin          # run it
uv run python scripts/try_stt.py      # recognition only, on the console
uv run python scripts/make_preview.py # render the settings UI without the app
uv run python scripts/check_i18n.py   # verify translations

.\build.ps1                           # executables (+ installer if Inno Setup 6 is present)
```

Releases are built by [`.github/workflows/release.yml`](.github/workflows/release.yml) on a `v*` tag: it builds both executables, compiles the Inno Setup installer, writes `latest.json` with the setup's SHA-256, and attaches both to the release. The updater refuses to install anything whose hash does not match.

## Troubleshooting

**It does not react.** Check the microphone under *Voice*, and watch the level meter on the *Overview* page while you speak. Then `scripts/try_stt.py` shows the same thing on the console.

**It hears the wrong thing.** The *Overview* page lists the last recognitions with their match score. Add the wording it actually heard as an alternative wording, or lower the match threshold.

**It triggers by itself.** Raise the match threshold, or turn on push-to-talk and leave the wake word out of it.

**Spotify says `premium-required` or `no-active-device`.** The playback API needs Premium and an active Spotify device. Media-key commands do not.

---

## 📒 Todo

- [x] Settings
- [x] Sounds
- [x] Installer + Updater
- [x] Fix Autostart recognition
- [x] UI Update
- [x] Adding new Voice recognition
- [x] Push-to-talk
- [x] On-screen display
- [x] Spotify + media keys
- [x] Spotify: shuffle, repeat, liked songs, queue, now playing
- [ ] More command types: type text, open URL
- [ ] Command history and undo
- [ ] More interface languages

## 👤 Author

A project by **Vensin** · [vensin.dev](https://vensin.dev)

Based on the idea from [this video](https://www.youtube.com/embed/QeX0wYlnUt0).
