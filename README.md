# ⚡ ArenaBoost – Safe Game Launcher & Booster

**Created by Ghost** · v2.0.0 · [MIT License](LICENSE) · © 2026 Ghost

| Folder | Platform | Tech |
|---|---|---|
| [`windows/`](windows) | Windows 10/11 | Python + Tkinter (builds to `.exe`) |
| [`mobile/`](mobile) | Android + iOS | Flutter + Kotlin |

## Download ready-made builds
Open the **Actions** tab, choose the latest green run, and download from **Artifacts**:
- `ArenaBoost-Windows` → `ArenaBoost.exe`
- `ArenaBoost-Android` → `app-release.apk`

## Features
**Windows:** finds Steam, Epic, Riot and emulator games • one-click Boost & Launch • Ultimate/High Performance power plan • pauses background apps and services • one-time standby RAM purge • 0.5 ms timer resolution • Above Normal priority • **automatic undo when the game closes, and after a crash** • CPU/RAM/disk/network monitor • ping test by region.

**Android:** finds installed games • clears background apps • Do Not Disturb that turns back off when you return • warnings for heat, Battery Saver and mobile data • RAM, temperature, battery and storage monitor • ping test with a live graph.

**iOS:** game launcher, ping test and checklist. Apple blocks booster functions.

🛡 **Anti-cheat safe:** it never touches game files or memory.

## What's new in v2
- A new sleek design: a sidebar dashboard with a glowing Boost button on Windows, and a boost orb with quick launch on mobile
- Screen orientation control on mobile: keep ArenaBoost **vertical** (default), horizontal or auto, and **lock rotation while gaming** so the screen can't flip mid-match. Your setting comes back automatically afterwards.
- Game search, a best-server suggestion, and a built-in `--selftest` for Windows
- Bug fixes found by testing: the boost thread could crash if a game closed during detection, and the mobile layout could overflow on small screens or with large text

## Testing: does it really work for people?
Every push runs these on GitHub:

| Test | Where | What is real |
|---|---|---|
| Windows unit tests (21) | Windows | game scanning, pause/resume of real processes, crash recovery |
| **Windows real system tests (10)** | Windows, **as Administrator** | real power plan switch and restore, real ping to every region, repeated pauses fully resumed, real service pause and restart, real standby RAM purge, real timer, **the real app window with every page**, a **full Boost & Launch of a real process** checked while it runs and after it closes |
| **EXE self-test** | Windows | the built `ArenaBoost.exe --selftest` |
| Mobile widget tests (20) | Linux | every screen, the boost flow, orientation, warnings, error handling |
| **Android real-device test (11)** | **Android 14 emulator** | real app list, RAM, battery, temperature, cleaning, Do Not Disturb, rotation lock, app launch, and the real UI |
| iOS compile check | macOS | the build compiles |

Run locally:
```
cd windows && pip install psutil pytest && python -m pytest -v
ArenaBoost.exe --selftest          # on any PC; the report goes to %APPDATA%\ArenaBoost\selftest.txt
cd mobile && flutter test && flutter test integration_test   # the second one needs a phone connected
```

## Honest note
No software can reduce the physical distance to a game server. Use a cable or 5 GHz Wi-Fi and the nearest server region for the lowest ping.
