# ⚡ ArenaBoost – Safe Game Launcher & Booster

**Created by Ghost** · v2.2.0 · [MIT License](LICENSE) · © 2026 Ghost

| Folder | Platform | Tech |
|---|---|---|
| [`windows/`](windows) | Windows 10/11 | Python + Tkinter (builds to `.exe`) |
| [`mobile/`](mobile) | Android + iOS | Flutter + Kotlin |

## Download ready-made builds
Open the **Actions** tab, choose the latest green run, and download from **Artifacts**:
- `ArenaBoost-Windows` → `ArenaBoost.exe`
- `ArenaBoost-Android` → `app-release.apk`

## Features
**Windows:** finds Steam, Epic, Riot and emulator games • one-click Boost & Launch • Ultimate/High Performance power plan • pauses background apps and services • one-time standby RAM purge • 0.5 ms timer resolution • Above Normal priority • **automatic undo when the game closes, and after a crash** • CPU/RAM/disk/network monitor • ping test by region • **floating game bar over your game (live CPU · RAM · net · time, one-click restore)**.

**Android:** finds installed games • clears background apps • Do Not Disturb that turns back off when you return • warnings for heat, Battery Saver and mobile data • RAM, temperature, battery and storage monitor • ping test with a live graph • **game bar overlay over your game (live CPU · RAM · temp · time, tap to come back & restore)**.

**iOS:** game launcher, ping test and checklist. Apple blocks booster functions.

🛡 **Anti-cheat safe:** it never touches game files or memory.

## What's new in v2.2
- 🎮 **Game bar**: while boosted, a floating bar hovers over your game with live **CPU · RAM · temperature · session time** — drag it on Windows, tap it on Android to come back (everything restores automatically). Toggle in Settings
- 🔒 **Security hardening**:
  - Windows config/state/log files are now **owner-only** — the app runs elevated, and its launch commands execute as admin, so this closes a local privilege-escalation path
  - more anti-cheat service names added to the never-touch list
  - Android: **no cleartext traffic**, app data **excluded from cloud backups**, least-privilege permissions (each granted by you)
  - no telemetry — no data ever leaves your PC / phone
- Windows: 26 unit + 11 real system tests · Mobile: 23 widget tests (incl. the game bar)

## What's new in v2.1 (reliability fixes)
- **The Boost button can no longer lock up**: if any tweak ever fails mid-boost, everything is restored and the button works again (before, one error could leave it dead until restart)
- **Configs always load**: options missing from an older/hand-edited `config.json` fall back to defaults, and invalid entries are dropped instead of crashing the app
- **A corrupted boost-state file is removed with a log message** instead of failing silently on every start
- **Android**: Boost & quick clean no longer freeze the screen for ~1–2 s (the heavy work now runs in the background)
- **iOS**: tapping a game that was uninstalled shows a message instead of failing silently
- **Windows**: `--selftest` and the test suite now run on machines without Tk (e.g. headless PCs)

## What's new in v2
- A new sleek design: a sidebar dashboard with a glowing Boost button on Windows, and a boost orb with quick launch on mobile
- Screen orientation control on mobile: keep ArenaBoost **vertical** (default), horizontal or auto, and **lock rotation while gaming** so the screen can't flip mid-match. Your setting comes back automatically afterwards.
- Game search, a best-server suggestion, and a built-in `--selftest` for Windows
- Bug fixes found by testing: the boost thread could crash if a game closed during detection, and the mobile layout could overflow on small screens or with large text

## Testing: does it really work for people?
Every push runs these on GitHub:

| Test | Where | What is real |
|---|---|---|
| Windows unit tests (26) | Windows | game scanning, pause/resume of real processes, crash recovery, config security |
| **Windows real system tests (11)** | Windows, **as Administrator** | real power plan switch and restore, real ping to every region, repeated pauses fully resumed, real service pause and restart, real standby RAM purge, real timer, **owner-only file ACLs**, **the real app window with every page**, a **full Boost & Launch of a real process** checked while it runs (incl. the game bar) and after it closes |
| **EXE self-test** | Windows | the built `ArenaBoost.exe --selftest` |
| Mobile widget tests (23) | Linux | every screen, the boost flow, orientation, warnings, error handling, game bar |
| **Android real-device test (11)** | **Android 14 emulator** | real app list, RAM, battery, temperature, cleaning, Do Not Disturb, rotation lock, app launch, and the real UI |
| iOS compile check | macOS | the build compiles |

Run locally:
```
cd windows && pip install psutil pytest && python -m pytest -v
ArenaBoost.exe --selftest          # on any PC; the report goes to %APPDATA%\ArenaBoost\selftest.txt
cd mobile && flutter test && flutter test integration_test   # the second one needs a phone connected
```

## Security
- 🛡 **Anti-cheat safe:** never reads, writes or injects into game memory; never touches game files. System and anti-cheat processes (Vanguard, EAC, BattlEye, launchers…) are on a protected list that can't even be removed from settings
- 🔒 **Windows: owner-only data files.** The app runs as Administrator and its launch commands execute as admin — so `config.json`, `restore_state.json` and the log are locked to your user account (no other local account can read or tamper with them). Launch commands come **only from your own config file**
- 🔒 **Android:** no cleartext traffic, app data excluded from cloud backups, and every extra capability (Do Not Disturb, rotation lock, game bar overlay) is a **least-privilege permission you grant once** in system settings
- 📴 **No telemetry, no accounts, no uploads** — no data ever leaves your PC or phone. The only network calls are your own ping tests to public endpoints

## Honest note
No software can reduce the physical distance to a game server. Use a cable or 5 GHz Wi-Fi and the nearest server region for the lowest ping.
