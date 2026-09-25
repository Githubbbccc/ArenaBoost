# ⚡ ArenaBoost – Safe Game Launcher & Booster (Windows 10/11)

## Quick start
1. Install **Python 3.10+** from python.org and tick **"Add Python to PATH"**.
2. Double-click **`RUN.bat`**. Click **Yes** when Windows asks for Administrator.
3. Optional: double-click **`BUILD_EXE.bat`** to make `dist\ArenaBoost.exe`, a single app you can open without Python.

## How to use
- **Games tab**: games are found automatically (Steam, Epic, Riot, BlueStacks, GameLoop, LDPlayer, MuMu). Use **➕ Add game** for anything else.
- Select a game and click **🚀 BOOST & LAUNCH**. When the game closes, **every change is undone automatically**.
- If auto-restore doesn't happen, click **✏ Edit** and fill in the game's `.exe` name, for example `FortniteClient-Win64-Shipping.exe`.
- **Monitor tab**: CPU, RAM, disk, network, top processes, a manual RAM purge button, and a stutter-cause check.
- **Network tab**: ping, jitter and packet loss for Bahrain, UAE, Mumbai, Singapore, Europe and the US, plus finding bandwidth hogs and flushing DNS.
- **Settings tab**: turn each tweak on or off, and edit the list of apps to suspend.

## What the boost does (all undone afterwards)
| Tweak | Why |
|---|---|
| Ultimate/High Performance power plan | The CPU stays at full speed, with no core parking |
| Game priority set to Above Normal | The game gets CPU time first. Realtime is never used because it's unsafe. |
| Suspends browsers, OneDrive, torrents, updaters, Teams, Spotify… | Frees CPU, RAM, disk and **bandwidth** (this is what lowers ping spikes). Suspended apps are paused, not closed, so no work is lost. |
| Pauses Windows Update, Delivery Optimization, Search, SysMain, BITS | Stops downloads and disk spikes in the background |
| One-time standby RAM purge | The same method ISLC uses. It is **not** a looping "RAM cleaner", because those cause stutter. |
| 0.5 ms timer resolution | Smoother frame pacing in some games |
| Overlay/recording warnings | Game Bar recording, NVIDIA Share and OBS are common stutter causes |

## Safety
- 🛡 **Anti-cheat safe**: it never touches game memory. Only Windows-level settings are changed.
- Windows system processes, anti-cheat, GPU drivers, Steam, Epic, Riot and Discord are **protected** and can't be suspended.
- **Crash-safe**: changes are saved to `%APPDATA%\ArenaBoost\restore_state.json`. If the PC or app crashes, everything is restored the next time you open ArenaBoost.
- Log file: `%APPDATA%\ArenaBoost\arenaboost.log`

## Honest note
No software can lower the physical distance to a game server. For the lowest ping, use an **Ethernet cable**, choose the closest server region, and pause downloads on other devices.
