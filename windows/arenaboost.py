"""
ArenaBoost - Safe Game Launcher & Booster for Windows 10/11
Created by Ghost - Copyright (c) 2026 Ghost - MIT License
-----------------------------------------------------------
Design rules (from our research):
  * Only OS-level tweaks. NEVER touches game memory -> anti-cheat safe
    (Vanguard, EAC, BattlEye, PUBG).
  * Everything changed is saved to a state file and RESTORED when the game
    closes, when the app closes, or on next start after a crash.
  * Suspends (not kills) background hogs -> no lost work.
  * RAM: one-time standby-list purge before launch (no loop "cleaning").
  * Honest network tools: ping test + pausing bandwidth hogs.
Run as Administrator for full features (app asks automatically).
"""
import ctypes, json, os, re, socket, subprocess, sys, threading, time, glob, logging, queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import psutil
except ImportError:
    print("Please run: pip install psutil"); sys.exit(1)

IS_WIN = os.name == "nt"
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ArenaBoost")
os.makedirs(APP_DIR, exist_ok=True)
CFG_FILE = os.path.join(APP_DIR, "config.json")
STATE_FILE = os.path.join(APP_DIR, "restore_state.json")
logging.basicConfig(filename=os.path.join(APP_DIR, "arenaboost.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ab")

# ---------------------------------------------------------------- constants
HIGH_PERF = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
ULTIMATE = "e9a42b02-d5df-448d-aa00-03f14749eb61"
CREATE_NO_WINDOW = 0x08000000

# Processes we must NEVER touch
PROTECTED = {n.lower() for n in [
    "system", "idle", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe",
    "audiodg.exe", "msmpeng.exe", "securityhealthservice.exe", "nissrv.exe", "spoolsv.exe",
    "ctfmon.exe", "sihost.exe", "taskhostw.exe", "runtimebroker.exe", "conhost.exe",
    "vgc.exe", "vgtray.exe", "easyanticheat.exe", "easyanticheat_eos.exe", "beservice.exe",
    "python.exe", "pythonw.exe", "arenaboost.exe", "nvcontainer.exe", "nvdisplay.container.exe",
    "amdrsserv.exe", "atiesrxx.exe", "atieclxx.exe", "steam.exe", "steamwebhelper.exe",
    "epicgameslauncher.exe", "riotclientservices.exe", "discord.exe"]}

# Default background hogs to suspend during gaming (user editable)
DEFAULT_HOGS = [
    "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe",
    "onedrive.exe", "googledrivefs.exe", "dropbox.exe", "qbittorrent.exe", "utorrent.exe",
    "bittorrent.exe", "idman.exe", "adobeupdateservice.exe", "adobearm.exe",
    "creative cloud.exe", "ccxprocess.exe", "teams.exe", "ms-teams.exe", "skype.exe",
    "spotify.exe", "searchapp.exe", "searchhost.exe", "phoneexperiencehost.exe",
    "yourphone.exe", "widgets.exe", "gamebar.exe", "xboxgamebarwidgets.exe"]

# Services to pause while gaming (restored afterwards)
DEFAULT_SERVICES = ["wuauserv", "DoSvc", "WSearch", "SysMain", "BITS"]

PING_TARGETS = {
    "Bahrain (ME)": "dynamodb.me-south-1.amazonaws.com",
    "UAE / Dubai": "dynamodb.me-central-1.amazonaws.com",
    "Mumbai": "dynamodb.ap-south-1.amazonaws.com",
    "Singapore": "dynamodb.ap-southeast-1.amazonaws.com",
    "Frankfurt (EU)": "dynamodb.eu-central-1.amazonaws.com",
    "London (EU)": "dynamodb.eu-west-2.amazonaws.com",
    "Virginia (US)": "dynamodb.us-east-1.amazonaws.com",
}

EMULATORS = {
    "BlueStacks 5": [r"C:\Program Files\BlueStacks_nxt\HD-Player.exe"],
    "GameLoop": [r"C:\Program Files\TxGameAssistant\ui\AndroidEmulatorEn.exe",
                 r"C:\Program Files\TxGameAssistant\ui\AndroidEmulatorEx.exe",
                 r"C:\Program Files (x86)\TxGameAssistant\ui\AndroidEmulatorEn.exe"],
    "LDPlayer 9": [r"C:\LDPlayer\LDPlayer9\dnplayer.exe"],
    "MSI App Player": [r"C:\Program Files\BlueStacks_msi5\HD-Player.exe"],
    "MuMu Player": [r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuPlayer.exe"],
}


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, shell=isinstance(cmd, str),
                           creationflags=CREATE_NO_WINDOW if IS_WIN else 0, timeout=30)
        return r.stdout + r.stderr
    except Exception as e:
        return str(e)


def is_admin():
    if not IS_WIN:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    params = " ".join(f'"{a}"' for a in sys.argv[1:])
    exe = sys.executable
    if not getattr(sys, "frozen", False):
        params = f'"{os.path.abspath(sys.argv[0])}" ' + params
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params + " --no-admin", None, 1) > 32


# ================================================================ CONFIG
def load_cfg():
    cfg = {"games": [], "hogs": DEFAULT_HOGS, "services": DEFAULT_SERVICES,
           "opt": {"power": True, "priority": True, "suspend": True, "services": True,
                   "standby": True, "timer": True, "gamebar_warn": True}}
    if os.path.exists(CFG_FILE):
        try:
            with open(CFG_FILE, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            log.error("cfg load %s", e)
    return cfg


def save_cfg(cfg):
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ================================================================ GAME SCAN
def _vdf_values(text, key):
    return re.findall(r'"%s"\s+"([^"]*)"' % re.escape(key), text, re.I)


def scan_steam(steam=None):
    games = []
    if not IS_WIN and not steam:
        return games
    if not steam:
      try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam = winreg.QueryValueEx(k, "SteamPath")[0]
      except Exception:
        for p in [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]:
            if os.path.isdir(p):
                steam = p
    if not steam:
        return games
    libs = {os.path.normpath(steam)}
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        txt = open(vdf, encoding="utf-8", errors="ignore").read()
        for p in _vdf_values(txt, "path"):
            libs.add(os.path.normpath(p.replace("\\\\", "\\")))
    skip = ("steamworks", "redistributable", "proton", "steam linux runtime")
    for lib in libs:
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                t = open(acf, encoding="utf-8", errors="ignore").read()
                name = _vdf_values(t, "name")[0]
                appid = _vdf_values(t, "appid")[0]
                inst = _vdf_values(t, "installdir")[0]
                if any(s in name.lower() for s in skip):
                    continue
                games.append({"name": name, "source": "Steam",
                              "launch": f"steam://rungameid/{appid}",
                              "folder": os.path.join(lib, "steamapps", "common", inst),
                              "process": ""})
            except Exception:
                pass
    return games


def scan_epic(d=r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"):
    games = []
    for item in glob.glob(os.path.join(d, "*.item")):
        try:
            j = json.load(open(item, encoding="utf-8"))
            if "games" not in [c.lower() for c in j.get("AppCategories", ["games"])]:
                continue
            loc = j["InstallLocation"]
            games.append({"name": j["DisplayName"], "source": "Epic",
                          "launch": f"com.epicgames.launcher://apps/{j['AppName']}?action=launch&silent=true",
                          "folder": loc,
                          "process": os.path.basename(j.get("LaunchExecutable", ""))})
        except Exception:
            pass
    return games


def scan_riot():
    games = []
    rc = r"C:\Riot Games\Riot Client\RiotClientServices.exe"
    if os.path.exists(rc):
        if os.path.isdir(r"C:\Riot Games\VALORANT"):
            games.append({"name": "VALORANT", "source": "Riot",
                          "launch": f'"{rc}" --launch-product=valorant --launch-patchline=live',
                          "folder": r"C:\Riot Games\VALORANT", "process": "VALORANT-Win64-Shipping.exe"})
        if os.path.isdir(r"C:\Riot Games\League of Legends"):
            games.append({"name": "League of Legends", "source": "Riot",
                          "launch": f'"{rc}" --launch-product=league_of_legends --launch-patchline=live',
                          "folder": r"C:\Riot Games\League of Legends", "process": "League of Legends.exe"})
    return games


def scan_emulators():
    out = []
    for name, paths in EMULATORS.items():
        for p in paths:
            if os.path.exists(p):
                out.append({"name": name, "source": "Emulator", "launch": p,
                            "folder": os.path.dirname(p), "process": os.path.basename(p)})
                break
    return out


def scan_all():
    res = []
    for fn in (scan_steam, scan_epic, scan_riot, scan_emulators):
        try:
            res += fn()
        except Exception as e:
            log.error("scan %s: %s", fn.__name__, e)
    return res


# ================================================================ WIN TWEAKS
class WinTweaks:
    """Every function returns info needed to undo it."""

    @staticmethod
    def get_power_plan():
        m = re.search(r"([0-9a-fA-F\-]{36})", run("powercfg /getactivescheme"))
        return m.group(1) if m else None

    @staticmethod
    def set_best_power_plan():
        schemes = run("powercfg /list").lower()
        if ULTIMATE not in schemes:
            run(f"powercfg -duplicatescheme {ULTIMATE}")
            schemes = run("powercfg /list").lower()
        # ultimate duplicated gets a new GUID; find by name
        m = re.search(r"([0-9a-f\-]{36})\s+\((ultimate performance)\)", schemes)
        guid = m.group(1) if m else HIGH_PERF
        run(f"powercfg /setactive {guid}")
        return guid

    @staticmethod
    def set_power_plan(guid):
        if guid:
            run(f"powercfg /setactive {guid}")

    # ---- process suspend / resume (NtSuspendProcess via psutil)
    @staticmethod
    def suspend_hogs(hogs, game_pids, already=()):
        """Suspend matching processes. `already` = PIDs we suspended before.
        IMPORTANT: Windows counts suspends (NtSuspendProcess). Suspending twice needs two
        resumes, so we never suspend a PID twice."""
        hogs = {h.lower() for h in hogs}
        already = set(already)
        done = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                n = (p.info["name"] or "").lower()
                if (n in hogs and n not in PROTECTED and p.pid not in game_pids
                        and p.pid not in already and p.pid != os.getpid()):
                    p.suspend()
                    done.append(p.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return done

    @staticmethod
    def resume_pids(pids):
        for pid in pids:
            try:
                p = psutil.Process(pid)
                p.resume()
                for _ in range(8):  # safety net: fully resume even if suspended multiple times
                    if p.status() != psutil.STATUS_STOPPED:
                        break
                    p.resume()
            except Exception:
                pass

    # ---- services
    @staticmethod
    def stop_services(names):
        stopped = []
        for s in names:
            try:
                svc = psutil.win_service_get(s)
                if svc.status() == "running":
                    run(f'sc stop "{s}"')
                    stopped.append(s)
            except Exception:
                pass
        return stopped

    @staticmethod
    def start_services(names):
        for s in names:
            run(f'sc start "{s}"')

    # ---- standby list purge (same method as ISLC / RAMMap)
    @staticmethod
    def _enable_privilege(name):
        """Enable a privilege on our process token. Uses correct 64-bit handle types
        (a plain int handle gets truncated on x64 -> STATUS_PRIVILEGE_NOT_HELD)."""
        from ctypes import wintypes
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

        class LUID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

        class TOKEN_PRIVILEGES(ctypes.Structure):
            _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi.OpenProcessToken.restype = wintypes.BOOL
        advapi.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(LUID)]
        advapi.LookupPrivilegeValueW.restype = wintypes.BOOL
        advapi.AdjustTokenPrivileges.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(TOKEN_PRIVILEGES),
                                                 wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        advapi.AdjustTokenPrivileges.restype = wintypes.BOOL

        tok = wintypes.HANDLE()
        if not advapi.OpenProcessToken(k32.GetCurrentProcess(), 0x0020 | 0x0008, ctypes.byref(tok)):
            raise OSError(ctypes.get_last_error(), "OpenProcessToken failed")
        try:
            luid = LUID()
            if not advapi.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
                raise OSError(ctypes.get_last_error(), "LookupPrivilegeValue failed")
            tp = TOKEN_PRIVILEGES(1, (LUID_AND_ATTRIBUTES * 1)(LUID_AND_ATTRIBUTES(luid, 0x2)))
            advapi.AdjustTokenPrivileges(tok, False, ctypes.byref(tp), 0, None, None)
            err = ctypes.get_last_error()
            if err:  # 1300 = ERROR_NOT_ALL_ASSIGNED
                raise OSError(err, f"privilege {name} not granted")
        finally:
            k32.CloseHandle(tok)

    @staticmethod
    def purge_standby():
        if not (IS_WIN and is_admin()):
            return "Needs Administrator"
        try:
            WinTweaks._enable_privilege("SeProfileSingleProcessPrivilege")
            before = psutil.virtual_memory().available
            cmd = ctypes.c_int(4)  # MemoryPurgeStandbyList
            nt = ctypes.WinDLL("ntdll")
            nt.NtSetSystemInformation.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
            nt.NtSetSystemInformation.restype = ctypes.c_long
            st = nt.NtSetSystemInformation(80, ctypes.byref(cmd), ctypes.sizeof(cmd))
            after = psutil.virtual_memory().available
            if st != 0:
                return f"Failed (NTSTATUS {st & 0xffffffff:#x})"
            return f"OK, +{max(0, after - before) // 2**20} MB available"
        except Exception as e:
            return f"Error: {e}"

    # ---- timer resolution (0.5ms) - held only while game runs
    @staticmethod
    def set_timer(enable):
        if not IS_WIN:
            return
        cur = ctypes.c_ulong()
        nt = ctypes.WinDLL("ntdll")
        nt.NtSetTimerResolution.argtypes = [ctypes.c_ulong, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ulong)]
        nt.NtSetTimerResolution.restype = ctypes.c_long
        return nt.NtSetTimerResolution(5000, 1 if enable else 0, ctypes.byref(cur)) == 0

    # ---- game bar / overlay checks
    @staticmethod
    def overlay_warnings():
        warn = []
        if not IS_WIN:
            return warn
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore")
            if winreg.QueryValueEx(k, "GameDVR_Enabled")[0] == 1:
                warn.append("Xbox Game Bar background recording is ON (can cause stutter). "
                            "Settings > Gaming > Captures > turn off 'Record what happened'.")
        except Exception:
            pass
        names = {(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])}
        if "nvidia share.exe" in names:
            warn.append("NVIDIA overlay (Share) is running - disable Instant Replay if not needed.")
        if "obs64.exe" in names:
            warn.append("OBS is running - uses CPU/GPU encoding.")
        return warn


# ================================================================ BOOST ENGINE
class BoostEngine:
    def __init__(self, cfg, logfn):
        self.cfg, self.say = cfg, logfn
        self.state = {}
        self.active = False

    def _save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f)

    def apply(self):
        o = self.cfg["opt"]
        self.state = {"time": time.time()}
        self._save_state()
        if o["power"] and IS_WIN:
            self.state["power"] = WinTweaks.get_power_plan()
            self._save_state()
            g = WinTweaks.set_best_power_plan()
            self.say(f"⚡ Power plan -> performance ({g[:8]}…)")
        if o["services"] and IS_WIN and is_admin():
            self.state["services"] = WinTweaks.stop_services(self.cfg["services"])
            self._save_state()
            self.say(f"🛑 Paused services: {', '.join(self.state['services']) or 'none running'}")
        if o["suspend"]:
            self.state["suspended"] = WinTweaks.suspend_hogs(self.cfg["hogs"], set())
            self._save_state()
            self.say(f"⏸ Suspended {len(self.state['suspended'])} background processes")
        if o["standby"]:
            self.say(f"🧹 Standby RAM purge: {WinTweaks.purge_standby()}")
        if o["timer"]:
            WinTweaks.set_timer(True)
            self.state["timer"] = True
            self.say("⏱ Timer resolution 0.5 ms")
        if o.get("gamebar_warn"):
            for w in WinTweaks.overlay_warnings():
                self.say("⚠ " + w)
        self.active = True
        self._save_state()

    def restore(self, state=None):
        s = state or self.state
        if not s:
            return
        if s.get("suspended"):
            WinTweaks.resume_pids(s["suspended"])
            self.say(f"▶ Resumed {len(s['suspended'])} processes")
        if s.get("services"):
            WinTweaks.start_services(s["services"])
            self.say("▶ Services restarted")
        if s.get("power"):
            WinTweaks.set_power_plan(s["power"])
            self.say("⚡ Power plan restored")
        if s.get("timer"):
            WinTweaks.set_timer(False)
        self.state = {}
        self.active = False
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        self.say("✅ All tweaks restored")

    @staticmethod
    def crash_recover(logfn):
        if os.path.exists(STATE_FILE):
            try:
                st = json.load(open(STATE_FILE))
                logfn("♻ Found tweaks from a previous session - restoring…")
                BoostEngine({}, logfn).restore(st)
            except Exception as e:
                log.error("recover %s", e)


def find_game_procs(game):
    folder = os.path.normcase(os.path.normpath(game.get("folder") or "")) if game.get("folder") else ""
    pname = (game.get("process") or "").lower()
    found = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            n = (p.info["name"] or "").lower()
            if n in PROTECTED and n != pname:
                continue
            if pname and n == pname:
                found.append(p)
            elif folder and p.info["exe"] and os.path.normcase(p.info["exe"]).startswith(folder + os.sep):
                found.append(p)
        except Exception:
            pass
    return found


# ================================================================ NETWORK
def tcp_ping(host, port=443, count=5):
    times = []
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        return None
    for _ in range(count):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        t = time.perf_counter()
        try:
            s.connect((ip, port))
            times.append((time.perf_counter() - t) * 1000)
        except Exception:
            pass
        finally:
            s.close()
        time.sleep(0.15)
    if not times:
        return None
    avg = sum(times) / len(times)
    jitter = sum(abs(times[i] - times[i - 1]) for i in range(1, len(times))) / max(1, len(times) - 1)
    return avg, jitter, (count - len(times)) / count * 100


def top_network_users():
    """Processes with most open connections (bandwidth hog hint)."""
    counts = {}
    try:
        for c in psutil.net_connections("inet"):
            if c.pid and c.status == "ESTABLISHED":
                counts[c.pid] = counts.get(c.pid, 0) + 1
    except Exception:
        return []
    out = []
    for pid, n in sorted(counts.items(), key=lambda x: -x[1])[:8]:
        try:
            out.append((psutil.Process(pid).name(), pid, n))
        except Exception:
            pass
    return out


# ================================================================ UI

# ================================================================ UI (v2 sleek design)
APP_NAME, APP_VERSION, AUTHOR = "ArenaBoost", "2.0.0", "Ghost"
BG, SIDE, CARD, CARD2 = "#0b0d14", "#10131c", "#161a26", "#1e2333"
ACC, ACC2, FG, MUTED = "#8b5cf6", "#22d3ee", "#eef0f7", "#8a90a6"
GOOD, WARN, BAD = "#34d399", "#fbbf24", "#f87171"
FONT = "Segoe UI" if IS_WIN else "DejaVu Sans"


def _mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Ring(tk.Canvas):
    """Circular gauge."""

    def __init__(self, master, label, size=132, **kw):
        super().__init__(master, width=size, height=size, bg=CARD, highlightthickness=0, **kw)
        self.size, self.label = size, label
        self.set(0, "–")

    def set(self, pct, text, sub=""):
        s, w = self.size, 11
        self.delete("all")
        self.create_oval(w, w, s - w, s - w, outline=CARD2, width=w)
        pct = max(0.0, min(100.0, float(pct)))
        col = GOOD if pct < 60 else WARN if pct < 85 else BAD
        if pct > 0:
            self.create_arc(w, w, s - w, s - w, start=90, extent=-3.6 * pct, style="arc", outline=col, width=w)
        self.create_text(s / 2, s / 2 - 8, text=text, fill=FG, font=(FONT, 17, "bold"))
        self.create_text(s / 2, s / 2 + 16, text=self.label, fill=MUTED, font=(FONT, 9))
        if sub:
            self.create_text(s / 2, s - 4, text=sub, fill=MUTED, font=(FONT, 8), anchor="s")


class BoostButton(tk.Canvas):
    """Big glowing circular boost button."""

    def __init__(self, master, command, size=210):
        super().__init__(master, width=size, height=size, bg=BG, highlightthickness=0, cursor="hand2")
        self.size, self.command, self.state_txt, self.phase, self.active = size, command, "BOOST", 0, False
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self._draw(hover=True))
        self.bind("<Leave>", lambda e: self._draw())
        self._draw()

    def set_active(self, active, text):
        self.active, self.state_txt = active, text
        self._draw()

    def pulse(self):
        self.phase = (self.phase + 1) % 40
        self._draw()

    def _draw(self, hover=False):
        s = self.size
        self.delete("all")
        base = GOOD if self.active else ACC
        glow = 6 + (abs(20 - self.phase) / 20 * 8 if self.active else 0)
        for i in range(10, 0, -1):  # glow rings
            t = i / 10
            self.create_oval(s / 2 - (70 + glow * t + i * 2.2), s / 2 - (70 + glow * t + i * 2.2),
                             s / 2 + (70 + glow * t + i * 2.2), s / 2 + (70 + glow * t + i * 2.2),
                             outline=_mix(BG, base, 0.10 + (1 - t) * 0.25), width=2)
        r = 74 if hover else 70
        for i in range(r, 0, -2):  # radial gradient fill
            self.create_oval(s / 2 - i, s / 2 - i, s / 2 + i, s / 2 + i, outline="",
                             fill=_mix(base, _mix(base, ACC2 if not self.active else "#065f46", 0.6), i / r))
        self.create_text(s / 2, s / 2 - 10, text="⚡", fill="white", font=(FONT, 26))
        self.create_text(s / 2, s / 2 + 26, text=self.state_txt, fill="white", font=(FONT, 14, "bold"))


class App(tk.Tk):
    PAGES = [("home", "🏠", "Dashboard"), ("games", "🎮", "Games"), ("monitor", "📊", "Monitor"),
             ("network", "🌐", "Network"), ("settings", "⚙", "Settings"), ("about", "ⓘ", "About")]

    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION} – Game Launcher & Booster · Created by {AUTHOR}")
        self.geometry("1120x720")
        self.minsize(980, 640)
        self.configure(bg=BG)
        self.cfg = load_cfg()
        self._uiq = queue.Queue()  # background threads NEVER touch Tk directly
        self.engine = BoostEngine(self.cfg, self.log)
        self._busy = False
        self._style()
        self._build()
        BoostEngine.crash_recover(self.log)
        if not is_admin():
            self.log("⚠ Not running as Administrator: service pause & RAM purge disabled.")
        if not self.cfg["games"]:
            self.scan()
        self.refresh_games()
        self.show("home")
        self._last_net = psutil.net_io_counters()
        self._last_disk = psutil.disk_io_counters()
        self._tick = 0
        self.after(800, self.update_monitor)
        self.after(60, self._animate)
        self.after(40, self._drain_ui)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def ui(self, fn):
        """Thread-safe: schedule fn to run on the Tk main thread."""
        self._uiq.put(fn)

    def _drain_ui(self):
        try:
            while True:
                fn = self._uiq.get_nowait()
                try:
                    fn()
                except tk.TclError:
                    pass
        except queue.Empty:
            pass
        try:
            self.after(40, self._drain_ui)
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- style
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=CARD, font=(FONT, 10))
        s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=FG, rowheight=34, borderwidth=0)
        s.configure("Treeview.Heading", background=CARD2, foreground=MUTED, borderwidth=0, font=(FONT, 9, "bold"))
        s.map("Treeview", background=[("selected", ACC)], foreground=[("selected", "white")])
        s.configure("TCheckbutton", background=CARD, foreground=FG, font=(FONT, 10))
        s.map("TCheckbutton", background=[("active", CARD)])
        s.configure("Vertical.TScrollbar", background=CARD2, troughcolor=CARD, borderwidth=0, arrowcolor=MUTED)

    def btn(self, parent, text, cmd, kind="ghost", **kw):
        colors = {"primary": (ACC, "#7c3aed", "white"), "ghost": (CARD2, "#2a3046", FG), "danger": ("#3a1d25", "#522530", BAD)}
        bg, hov, fg = colors[kind]
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=(FONT, 10, "bold" if kind == "primary" else "normal"),
                     padx=16, pady=9, cursor="hand2", **kw)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.config(bg=hov))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def card(self, parent, **kw):
        return tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground="#232a3d", **kw)

    def h1(self, parent, text, sub=None):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", pady=(0, 14))
        tk.Label(f, text=text, bg=BG, fg=FG, font=(FONT, 20, "bold")).pack(anchor="w")
        if sub:
            tk.Label(f, text=sub, bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor="w")
        return f

    # ---------------------------------------------------------------- layout
    def _build(self):
        side = tk.Frame(self, bg=SIDE, width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        logo = tk.Frame(side, bg=SIDE)
        logo.pack(fill="x", pady=(22, 26), padx=18)
        tk.Label(logo, text="⚡", bg=SIDE, fg=ACC, font=(FONT, 22, "bold")).pack(side="left")
        tk.Label(logo, text=APP_NAME, bg=SIDE, fg=FG, font=(FONT, 16, "bold")).pack(side="left", padx=6)
        self.nav = {}
        for key, icon, label in self.PAGES:
            b = tk.Label(side, text=f"  {icon}   {label}", anchor="w", bg=SIDE, fg=MUTED, font=(FONT, 11),
                         padx=14, pady=10, cursor="hand2")
            b.pack(fill="x", padx=10, pady=2)
            b.bind("<Button-1>", lambda e, k=key: self.show(k))
            self.nav[key] = b
        foot = tk.Frame(side, bg=SIDE)
        foot.pack(side="bottom", fill="x", padx=18, pady=16)
        self.status = tk.Label(foot, text="● Idle", bg=SIDE, fg=MUTED, font=(FONT, 10, "bold"))
        self.status.pack(anchor="w")
        tk.Label(foot, text="🛡 Admin" if is_admin() else "⚠ Limited mode", bg=SIDE,
                 fg=GOOD if is_admin() else WARN, font=(FONT, 9)).pack(anchor="w", pady=(4, 8))
        tk.Label(foot, text=f"Created by {AUTHOR}", bg=SIDE, fg=ACC, font=(FONT, 9, "bold")).pack(anchor="w")
        tk.Label(foot, text=f"v{APP_VERSION} · MIT License", bg=SIDE, fg=MUTED, font=(FONT, 8)).pack(anchor="w")

        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        self.pages_host = tk.Frame(main, bg=BG)
        self.pages_host.pack(fill="both", expand=True, padx=26, pady=(22, 8))
        self.pages = {k: tk.Frame(self.pages_host, bg=BG) for k, _, _ in self.PAGES}
        self._home_page(self.pages["home"])
        self._games_page(self.pages["games"])
        self._monitor_page(self.pages["monitor"])
        self._net_page(self.pages["network"])
        self._settings_page(self.pages["settings"])
        self._about_page(self.pages["about"])

        lf = self.card(main)
        lf.pack(fill="x", padx=26, pady=(0, 18))
        tk.Label(lf, text="ACTIVITY", bg=CARD, fg=MUTED, font=(FONT, 8, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        self.logbox = tk.Text(lf, height=6, bg=CARD, fg="#b7bdd1", bd=0, font=("Consolas", 9), wrap="word",
                              highlightthickness=0)
        self.logbox.pack(fill="x", padx=12, pady=(2, 10))

    def show(self, key):
        for k, f in self.pages.items():
            f.pack_forget()
            self.nav[k].config(bg=SIDE, fg=MUTED)
        self.pages[key].pack(fill="both", expand=True)
        self.nav[key].config(bg=CARD2, fg=FG)
        self.current = key

    def log(self, msg):
        log.info(msg)

        def _w():
            self.logbox.insert("end", time.strftime("%H:%M:%S  ") + msg + "\n")
            self.logbox.see("end")
        self.ui(_w)

    def set_status(self, text, color):
        def _u():
            self.status.config(text=text, fg=color)
            active = "BOOSTED" in text
            self.boost_btn.set_active(active, "BOOSTED" if active else ("…" if "Boost" in text else "BOOST"))
            self.hero_state.config(text="Your PC is boosted 🚀" if active else "Ready to boost",
                                   fg=GOOD if active else FG)
        self.ui(_u)

    def _animate(self):
        if self.engine.active:
            self.boost_btn.pulse()
        self.after(60, self._animate)

    # ---------------------------------------------------------------- dashboard
    def _home_page(self, p):
        top = tk.Frame(p, bg=BG)
        top.pack(fill="x")
        left = tk.Frame(top, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="Welcome back, gamer", bg=BG, fg=MUTED, font=(FONT, 11)).pack(anchor="w")
        self.hero_state = tk.Label(left, text="Ready to boost", bg=BG, fg=FG, font=(FONT, 26, "bold"))
        self.hero_state.pack(anchor="w", pady=(2, 6))
        tk.Label(left, text="One click frees CPU, RAM, disk and bandwidth for your game —\n"
                            "and everything is restored automatically when you stop.",
                 bg=BG, fg=MUTED, justify="left", font=(FONT, 10)).pack(anchor="w")
        row = tk.Frame(left, bg=BG)
        row.pack(anchor="w", pady=16)
        self.btn(row, "🎮  Launch a game", lambda: self.show("games"), "primary").pack(side="left")
        self.btn(row, "↺  Restore now", self.restore_now).pack(side="left", padx=8)
        self.btn(row, "📡  Test ping", lambda: (self.show("network"), self.ping_all())).pack(side="left")
        self.boost_btn = BoostButton(top, self.toggle_boost)
        self.boost_btn.pack(side="right", padx=10)

        rings = self.card(p)
        rings.pack(fill="x", pady=(14, 0))
        self.rings = {}
        for i, k in enumerate(["CPU", "RAM", "Disk", "Net"]):
            r = Ring(rings, k)
            r.grid(row=0, column=i, padx=18, pady=16)
            rings.columnconfigure(i, weight=1)
            self.rings[k] = r

        tips = self.card(p)
        tips.pack(fill="x", pady=12)
        self.tip_lbl = tk.Label(tips, text="", bg=CARD, fg=MUTED, font=(FONT, 10), justify="left", wraplength=780)
        self.tip_lbl.pack(anchor="w", padx=16, pady=12)
        self._tips = ["💡 Ethernet beats Wi-Fi for ping and stability.", "💡 Close the browser — it's the #1 RAM hog.",
                      "💡 Keep your game on an SSD to stop open-world stutter.",
                      "💡 Pick the closest server region (Bahrain / UAE / Mumbai for Pakistan).",
                      "💡 Over 90°C? Clean the dust — no software fixes throttling."]
        self._tip_i = 0
        self._rotate_tip()

    def _rotate_tip(self):
        self.tip_lbl.config(text=self._tips[self._tip_i % len(self._tips)])
        self._tip_i += 1
        self.after(6000, self._rotate_tip)

    def toggle_boost(self):
        (self.restore_now if self.engine.active else self.boost_only)()

    # ---------------------------------------------------------------- games
    def _games_page(self, p):
        hdr = self.h1(p, "Games", "Double-click a game to Boost & Launch. Settings restore when it closes.")
        bar = tk.Frame(p, bg=BG)
        bar.pack(fill="x", pady=(0, 10))
        self.btn(bar, "🚀  BOOST & LAUNCH", self.boost_launch, "primary").pack(side="left")
        self.btn(bar, "🔍 Scan", lambda: (self.scan(), self.refresh_games())).pack(side="right")
        self.btn(bar, "➕ Add", self.add_game).pack(side="right", padx=6)
        self.btn(bar, "✏ Edit", self.edit_game).pack(side="right")
        self.btn(bar, "🗑 Remove", self.remove_game, "danger").pack(side="right", padx=6)
        self.search = tk.StringVar()
        e = tk.Entry(bar, textvariable=self.search, bg=CARD2, fg=FG, insertbackground=FG, bd=0, width=24,
                     font=(FONT, 10))
        e.pack(side="left", padx=12, ipady=8)
        e.insert(0, "")
        self.search.trace_add("write", lambda *a: self.refresh_games())
        box = self.card(p)
        box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(box, columns=("src", "proc", "folder"), show="tree headings")
        for c, t, w in [("#0", "GAME", 260), ("src", "SOURCE", 90), ("proc", "GAME EXE (auto-restore)", 220),
                        ("folder", "INSTALL FOLDER", 300)]:
            self.tree.heading(c, text=t, anchor="w")
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=2, pady=2)
        self.tree.bind("<Double-1>", lambda e: self.boost_launch())

    def scan(self):
        found = scan_all()
        known = {g["name"] for g in self.cfg["games"]}
        new = [g for g in found if g["name"] not in known]
        self.cfg["games"] += new
        save_cfg(self.cfg)
        self.log(f"🔍 Scan complete: {len(new)} new games found ({len(self.cfg['games'])} total)")

    def refresh_games(self):
        q = self.search.get().lower().strip() if hasattr(self, "search") else ""
        self.tree.delete(*self.tree.get_children())
        for i, g in enumerate(self.cfg["games"]):
            if q and q not in g["name"].lower():
                continue
            self.tree.insert("", "end", iid=str(i), text="  " + g["name"],
                             values=(g["source"], g.get("process") or "(auto: folder)", g.get("folder", "")))

    def selected_game(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a game first.")
            return None
        return self.cfg["games"][int(sel[0])]

    def add_game(self):
        p = filedialog.askopenfilename(title="Select game .exe", filetypes=[("Programs", "*.exe")])
        if p:
            self.add_game_path(p)

    def add_game_path(self, p):
        name = os.path.splitext(os.path.basename(p))[0]
        self.cfg["games"].append({"name": name, "source": "Manual", "launch": p,
                                  "folder": os.path.dirname(p), "process": os.path.basename(p)})
        save_cfg(self.cfg)
        self.refresh_games()
        return self.cfg["games"][-1]

    def edit_game(self):
        g = self.selected_game()
        if not g:
            return
        w = tk.Toplevel(self, bg=BG)
        w.title("Edit game")
        w.geometry("600x300")
        entries = {}
        for i, (k, lbl) in enumerate([("name", "Name"), ("launch", "Launch command / exe / URL"),
                                      ("folder", "Install folder"), ("process", "Game process .exe (optional)")]):
            tk.Label(w, text=lbl, bg=BG, fg=MUTED).grid(row=i, column=0, sticky="w", padx=14, pady=8)
            e = tk.Entry(w, width=50, bg=CARD2, fg=FG, insertbackground=FG, bd=0)
            e.insert(0, g.get(k, ""))
            e.grid(row=i, column=1, padx=10, pady=8, ipady=6)
            entries[k] = e

        def ok():
            for k, e in entries.items():
                g[k] = e.get().strip()
            save_cfg(self.cfg)
            self.refresh_games()
            w.destroy()
        self.btn(w, "Save", ok, "primary").grid(row=5, column=1, sticky="e", padx=10, pady=12)

    def remove_game(self):
        sel = self.tree.selection()
        if sel:
            del self.cfg["games"][int(sel[0])]
            save_cfg(self.cfg)
            self.refresh_games()

    # ---------------------------------------------------------------- boost flow
    def boost_only(self):
        if self.engine.active or self._busy:
            return self.log("Already boosted.")
        self._busy = True

        def w():
            self.set_status("● Boosting…", ACC)
            self.engine.apply()
            self._busy = False
            self.set_status("● BOOSTED", GOOD)
        threading.Thread(target=w, daemon=True).start()

    def restore_now(self):
        def w():
            self.engine.restore()
            self.set_status("● Idle", MUTED)
        threading.Thread(target=w, daemon=True).start()

    def boost_launch(self):
        g = self.selected_game()
        if not g:
            return
        if self.engine.active or self._busy:
            return self.log("Already boosted – restore first or wait for game to close.")
        threading.Thread(target=self._boost_launch_worker, args=(g,), daemon=True).start()

    def _boost_launch_worker(self, g, detect_timeout=180, poll=5):
        """Returns a result string (used by self-test)."""
        self._busy = True
        try:
            self.log(f"🚀 Boosting for {g['name']}…")
            self.set_status("● Boosting…", ACC)
            self.engine.apply()
            self.set_status("● BOOSTED", GOOD)
            launch = g["launch"]
            try:
                if "://" in launch and not launch.startswith('"'):
                    if IS_WIN:
                        os.startfile(launch)
                elif launch.startswith('"') or " --" in launch:
                    subprocess.Popen(launch, shell=True, cwd=g.get("folder") or None)
                else:
                    subprocess.Popen([launch], cwd=os.path.dirname(launch) or None)
            except Exception as e:
                self.log(f"❌ Launch failed: {e}")
                self.engine.restore()
                self.set_status("● Idle", MUTED)
                return "launch_failed"
            self.log("⏳ Waiting for game process…")
            procs, t0 = [], time.time()
            while time.time() - t0 < detect_timeout and not procs:
                time.sleep(min(2, poll))
                procs = find_game_procs(g)
            if not procs:
                self.log("⚠ Game process not detected. Tweaks stay ON – press 'Restore now' when done "
                         "(tip: set the game .exe in Edit).")
                return "not_detected"

            def rss(p):
                try:
                    return p.memory_info().rss
                except Exception:
                    return 0
            main = max(procs, key=rss)
            try:
                self.log(f"🎮 Detected {main.name()} (PID {main.pid})")
            except Exception:
                pass
            if self.cfg["opt"]["priority"]:
                for p in procs:
                    try:
                        p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS if IS_WIN else 5)
                    except Exception:
                        pass
                self.log("⬆ Game priority -> Above Normal (safe, never Realtime)")
            while True:
                time.sleep(poll)
                alive = find_game_procs(g)
                if not alive:
                    break
                if self.cfg["opt"]["suspend"]:
                    pids = {p.pid for p in alive}
                    extra = WinTweaks.suspend_hogs(self.cfg["hogs"], pids,
                                                   already=self.engine.state.get("suspended", []))
                    if extra:
                        self.engine.state.setdefault("suspended", []).extend(extra)
                        self.engine._save_state()
            self.log(f"🏁 {g['name']} closed.")
            self.engine.restore()
            self.set_status("● Idle", MUTED)
            return "ok"
        except Exception as e:  # never leave the PC in boosted state because of a bug
            log.exception("boost worker")
            self.log(f"❌ Error: {e} – restoring")
            self.engine.restore()
            self.set_status("● Idle", MUTED)
            return "error"
        finally:
            self._busy = False

    # ---------------------------------------------------------------- monitor
    def _monitor_page(self, p):
        self.h1(p, "Monitor", "Live system usage. Top processes refresh every 3 seconds.")
        grid = tk.Frame(p, bg=BG)
        grid.pack(fill="x")
        self.cards = {}
        for i, k in enumerate(["CPU", "RAM", "Disk", "Network"]):
            c = self.card(grid)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            grid.columnconfigure(i, weight=1)
            tk.Label(c, text=k.upper(), bg=CARD, fg=MUTED, font=(FONT, 8, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
            v = tk.Label(c, text="–", bg=CARD, fg=FG, font=(FONT, 20, "bold"))
            v.pack(anchor="w", padx=14)
            sub = tk.Label(c, text="", bg=CARD, fg=MUTED, font=(FONT, 9))
            sub.pack(anchor="w", padx=14)
            bar = tk.Canvas(c, height=6, bg=CARD2, highlightthickness=0)
            bar.pack(fill="x", padx=14, pady=(8, 14))
            self.cards[k] = (v, sub, bar)
        rowf = tk.Frame(p, bg=BG)
        rowf.pack(fill="x", pady=12)
        self.btn(rowf, "🧹 Purge standby RAM", lambda: self.log("🧹 " + WinTweaks.purge_standby())).pack(side="left")
        self.btn(rowf, "⚠ Find stutter causes", self.check_overlays).pack(side="left", padx=8)
        box = self.card(p)
        box.pack(fill="both", expand=True)
        self.ptree = ttk.Treeview(box, columns=("cpu", "ram"), show="tree headings")
        self.ptree.heading("#0", text="PROCESS", anchor="w")
        self.ptree.heading("cpu", text="CPU %")
        self.ptree.heading("ram", text="RAM MB")
        self.ptree.pack(fill="both", expand=True, padx=2, pady=2)

    def check_overlays(self):
        w = WinTweaks.overlay_warnings()
        for x in w or ["No common overlay problems found."]:
            self.log("⚠ " + x)
        try:
            disk = psutil.disk_usage(os.environ.get("SystemDrive", "/") + os.sep)
            if disk.percent > 90:
                self.log("⚠ System drive over 90% full - can cause stutter.")
        except Exception:
            pass
        if psutil.virtual_memory().total < 8.5 * 2**30:
            self.log("ℹ Under 8 GB RAM: close browsers before gaming; standby purge helps you most.")
        return w

    def update_monitor(self):
        try:
            cpu = psutil.cpu_percent()
            vm = psutil.virtual_memory()
            n = psutil.net_io_counters()
            d = psutil.disk_io_counters()
            down = (n.bytes_recv - self._last_net.bytes_recv) / 1024
            up = (n.bytes_sent - self._last_net.bytes_sent) / 1024
            dmb = (((d.read_bytes + d.write_bytes) - (self._last_disk.read_bytes + self._last_disk.write_bytes)) / 2**20
                   if d and self._last_disk else 0)
            self._last_net, self._last_disk = n, d
            freq = psutil.cpu_freq()
            self._card("CPU", f"{cpu:.0f}%", f"{psutil.cpu_count()} threads" + (f" · {freq.current:.0f} MHz" if freq else ""), cpu)
            self._card("RAM", f"{vm.percent:.0f}%", f"{vm.used/2**30:.1f} / {vm.total/2**30:.1f} GB", vm.percent)
            self._card("Disk", f"{dmb:.1f} MB/s", "read + write", min(100, dmb))
            self._card("Network", f"↓ {down:.0f} KB/s", f"↑ {up:.0f} KB/s", min(100, down / 50))
            self.rings["CPU"].set(cpu, f"{cpu:.0f}%")
            self.rings["RAM"].set(vm.percent, f"{vm.percent:.0f}%", f"{vm.available/2**30:.1f} GB free")
            self.rings["Disk"].set(min(100, dmb), f"{dmb:.0f}", "MB/s")
            self.rings["Net"].set(min(100, down / 50), f"{down:.0f}", "KB/s down")
            self._tick += 1
            if self._tick % 3 == 0 and self.current == "monitor":
                procs = []
                for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
                    try:
                        procs.append((p.info["name"], p.info["cpu_percent"] or 0, p.info["memory_info"].rss / 2**20))
                    except Exception:
                        pass
                procs.sort(key=lambda x: (-x[1], -x[2]))
                self.ptree.delete(*self.ptree.get_children())
                for name, c, r in procs[:14]:
                    self.ptree.insert("", "end", text="  " + str(name), values=(f"{c:.1f}", f"{r:.0f}"))
        except Exception as e:
            log.error("monitor %s", e)
        self.after(1000, self.update_monitor)

    def _card(self, k, v, sub, pct):
        a, b, bar = self.cards[k]
        a.config(text=v)
        b.config(text=sub)
        bar.update_idletasks()
        w = max(1, bar.winfo_width())
        bar.delete("all")
        col = GOOD if pct < 60 else WARN if pct < 85 else BAD
        bar.create_rectangle(0, 0, w * max(0, min(100, pct)) / 100, 6, fill=col, outline="")

    # ---------------------------------------------------------------- network
    def _net_page(self, p):
        self.h1(p, "Network", "Ping, jitter and packet loss to game regions (TCP, no admin needed).")
        bar = tk.Frame(p, bg=BG)
        bar.pack(fill="x", pady=(0, 10))
        self.btn(bar, "📡  Test all regions", self.ping_all, "primary").pack(side="left")
        self.btn(bar, "🔎 Bandwidth hogs", self.find_hogs).pack(side="left", padx=8)
        self.btn(bar, "Flush DNS", lambda: self.log(run("ipconfig /flushdns").strip()[:120])).pack(side="left")
        box = self.card(p)
        box.pack(fill="x")
        self.ntree = ttk.Treeview(box, columns=("ping", "jit", "loss", "q"), show="tree headings", height=7)
        for c, t in [("#0", "REGION"), ("ping", "PING ms"), ("jit", "JITTER ms"), ("loss", "LOSS %"), ("q", "QUALITY")]:
            self.ntree.heading(c, text=t, anchor="w")
        self.ntree.pack(fill="x", padx=2, pady=2)
        tip = self.card(p)
        tip.pack(fill="x", pady=10)
        tk.Label(tip, text="Honest note: software can't shorten the distance to a server. Real ping wins: Ethernet cable • "
                           "5 GHz Wi-Fi • closest region • pause downloads on ALL devices • a routing service if your ISP "
                           "routes badly. ArenaBoost pauses local bandwidth hogs while you play.",
                 bg=CARD, fg=MUTED, wraplength=820, justify="left").pack(anchor="w", padx=14, pady=10)
        box2 = self.card(p)
        box2.pack(fill="both", expand=True)
        self.htree = ttk.Treeview(box2, columns=("pid", "conn"), show="tree headings", height=5)
        self.htree.heading("#0", text="PROCESS WITH MOST CONNECTIONS", anchor="w")
        self.htree.heading("pid", text="PID")
        self.htree.heading("conn", text="CONNECTIONS")
        self.htree.pack(fill="both", expand=True, padx=2, pady=2)

    def ping_all(self, targets=None, done=None):
        self.ntree.delete(*self.ntree.get_children())
        self.log("📡 Testing ping…")
        targets = targets or PING_TARGETS

        def work():
            for region, host in targets.items():
                r = tcp_ping(host)
                if r:
                    avg, jit, loss = r
                    q = "Excellent" if avg < 50 else "Good" if avg < 90 else "OK" if avg < 150 else "Poor"
                    vals = (f"{avg:.0f}", f"{jit:.1f}", f"{loss:.0f}", q)
                else:
                    vals = ("timeout", "-", "100", "Unreachable")
                self.ui(lambda reg=region, v=vals: self.ntree.insert("", "end", text="  " + reg, values=v))
            self.log("📡 Ping test done. High jitter = Wi-Fi or someone downloading.")
            if done:
                self.ui(done)
        threading.Thread(target=work, daemon=True).start()

    def find_hogs(self):
        self.htree.delete(*self.htree.get_children())
        for name, pid, n in top_network_users():
            self.htree.insert("", "end", text="  " + name, values=(pid, n))

    # ---------------------------------------------------------------- settings
    def _settings_page(self, p):
        self.h1(p, "Settings", "Choose what Boost does. Every change is undone automatically.")
        f = self.card(p)
        f.pack(fill="x")
        self.vars = {}
        opts = [("power", "Ultimate / High Performance power plan"),
                ("priority", "Game priority → Above Normal (never Realtime)"),
                ("suspend", "Suspend background apps (resumed after, no data loss)"),
                ("services", "Pause Windows Update, Delivery Optimization, Search, SysMain, BITS (admin)"),
                ("standby", "One-time standby RAM purge before launch (admin)"),
                ("timer", "0.5 ms timer resolution while boosted"),
                ("gamebar_warn", "Warn about overlays / recording that cause stutter")]
        for k, t in opts:
            v = tk.BooleanVar(value=self.cfg["opt"].get(k, True))
            self.vars[k] = v
            ttk.Checkbutton(f, text="  " + t, variable=v, command=self.save_opts).pack(anchor="w", padx=16, pady=6)
        f2 = self.card(p)
        f2.pack(fill="both", expand=True, pady=12)
        tk.Label(f2, text="APPS TO SUSPEND WHILE GAMING (one per line)", bg=CARD, fg=MUTED,
                 font=(FONT, 8, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.hogtext = tk.Text(f2, height=7, bg=CARD2, fg=FG, bd=0, insertbackground=FG, font=("Consolas", 9),
                               highlightthickness=0)
        self.hogtext.insert("1.0", "\n".join(self.cfg["hogs"]))
        self.hogtext.pack(fill="both", expand=True, padx=16)
        self.btn(f2, "Save list", self.save_hogs, "primary").pack(anchor="e", padx=16, pady=10)

    def save_opts(self):
        for k, v in self.vars.items():
            self.cfg["opt"][k] = v.get()
        save_cfg(self.cfg)

    def save_hogs(self):
        lst = [l.strip().lower() for l in self.hogtext.get("1.0", "end").splitlines() if l.strip()]
        bad = [l for l in lst if l in PROTECTED]
        self.cfg["hogs"] = [l for l in lst if l not in PROTECTED]
        save_cfg(self.cfg)
        self.log(f"Saved {len(self.cfg['hogs'])} apps." + (f" Ignored protected: {bad}" if bad else ""))

    # ---------------------------------------------------------------- about
    def _about_page(self, p):
        self.h1(p, "About")
        c = self.card(p)
        c.pack(fill="x")
        tk.Label(c, text=f"⚡ {APP_NAME}", bg=CARD, fg=FG, font=(FONT, 22, "bold")).pack(anchor="w", padx=20, pady=(18, 0))
        tk.Label(c, text=f"Version {APP_VERSION}", bg=CARD, fg=MUTED).pack(anchor="w", padx=20)
        tk.Label(c, text=f"Created by {AUTHOR}", bg=CARD, fg=ACC, font=(FONT, 13, "bold")).pack(anchor="w", padx=20, pady=(10, 0))
        tk.Label(c, text=f"© 2026 {AUTHOR}. Released under the MIT License.", bg=CARD, fg=MUTED).pack(anchor="w", padx=20)
        tk.Label(c, text="🛡 Anti-cheat safe: never reads, writes or injects into game memory.\n"
                         "♻ Crash-safe: every tweak is saved and restored automatically.\n"
                         f"📁 Config & logs: {APP_DIR}",
                 bg=CARD, fg=MUTED, justify="left").pack(anchor="w", padx=20, pady=(12, 18))

    def on_close(self):
        if self.engine.active:
            self.engine.restore()
        self.destroy()


# ================================================================ SELF-TEST (real system)
def selftest():
    """Runs the REAL functions on this PC and prints PASS/FAIL. Use: ArenaBoost.exe --selftest"""
    results = []
    report = open(os.path.join(APP_DIR, "selftest.txt"), "w", encoding="utf-8")

    def out(line):
        report.write(line + "\n"); report.flush()
        if sys.stdout is not None:  # windowed .exe has no console
            try:
                sys.stdout.write(line.encode(sys.stdout.encoding or "utf-8", "replace").decode(sys.stdout.encoding or "utf-8") + "\n")
                sys.stdout.flush()
            except Exception:
                pass

    def check(name, fn):
        try:
            ok, info = fn()
        except Exception as e:
            ok, info = False, f"{type(e).__name__}: {e}"
        results.append((name, ok, info))
        out(f"[{'PASS' if ok else 'FAIL'}] {name} - {info}")

    admin = is_admin()
    out(f"[INFO] Administrator rights - {'yes' if admin else 'no (service pause & RAM purge limited)'}")
    check("Game scan", lambda: (True, f"{len(scan_all())} games found"))
    if IS_WIN:
        def power():
            old = WinTweaks.get_power_plan()
            new = WinTweaks.set_best_power_plan()
            now = WinTweaks.get_power_plan()
            WinTweaks.set_power_plan(old)
            back = WinTweaks.get_power_plan()
            return (bool(now) and now.lower() == new.lower() and back == old, f"{old[:8]} -> {now[:8]} -> {back[:8]}")
        check("Power plan switch + restore", power)
        check("Timer resolution 0.5ms", lambda: ((WinTweaks.set_timer(True), WinTweaks.set_timer(False))[0], "set & released"))
        if admin:
            check("Standby RAM purge", lambda: ((r := WinTweaks.purge_standby()).startswith("OK"), r))
    def ping():
        for host in ["1.1.1.1", "dns.google", "www.microsoft.com"]:
            r = tcp_ping(host, count=3)
            if r:
                return True, f"{host}: {r[0]:.0f} ms"
        return False, "no internet connection"
    check("Ping (network)", ping)
    fails = [r for r in results if not r[1]]
    out(f"\n{len(results) - len(fails)}/{len(results)} checks passed")
    report.close()
    return 1 if fails else 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if IS_WIN and not is_admin() and "--no-admin" not in sys.argv:
        try:
            if relaunch_as_admin():
                return
        except Exception:
            pass
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
