# ⚡ ArenaBoost – Safe Game Launcher & Booster

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

## Tests
```
cd windows && pip install psutil pytest && python -m pytest -v   # 20 tests
cd mobile  && flutter test                                        # 12 tests
```
Every push to GitHub runs all tests on real Windows, Ubuntu and macOS, and builds the EXE and APK automatically.

## Honest note
No software can reduce the physical distance to a game server. Use a cable or 5 GHz Wi-Fi and the nearest server region for the lowest ping.
