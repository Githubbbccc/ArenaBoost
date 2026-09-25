"""
ArenaBoost - Safe Game Launcher & Booster for Windows 10/11
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
import ctypes, json, os, re, socket, subprocess, sys, threading, time, glob, logging
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
    def suspend_hogs(hogs, game_pids):
        hogs = {h.lower() for h in hogs}
        done = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                n = (p.info["name"] or "").lower()
                if n in hogs and n not in PROTECTED and p.pid not in game_pids:
                    p.suspend()
                    done.append(p.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return done

    @staticmethod
    def resume_pids(pids):
        for pid in pids:
            try:
                psutil.Process(pid).resume()
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
        advapi = ctypes.windll.advapi32
        k32 = ctypes.windll.kernel32

        class LUID(ctypes.Structure):
            _fields_ = [("Low", ctypes.c_ulong), ("High", ctypes.c_long)]

        class TP(ctypes.Structure):
            _fields_ = [("Count", ctypes.c_ulong), ("Luid", LUID), ("Attr", ctypes.c_ulong)]

        tok = ctypes.c_void_p()
        advapi.OpenProcessToken(k32.GetCurrentProcess(), 0x0020 | 0x0008, ctypes.byref(tok))
        luid = LUID()
        advapi.LookupPrivilegeValueW(None, name, ctypes.byref(luid))
        tp = TP(1, luid, 0x2)
        advapi.AdjustTokenPrivileges(tok, False, ctypes.byref(tp), 0, None, None)
        k32.CloseHandle(tok)

    @staticmethod
    def purge_standby():
        if not (IS_WIN and is_admin()):
            return "Needs Administrator"
        try:
            WinTweaks._enable_privilege("SeProfileSingleProcessPrivilege")
            before = psutil.virtual_memory().available
            cmd = ctypes.c_int(4)  # MemoryPurgeStandbyList
            st = ctypes.windll.ntdll.NtSetSystemInformation(80, ctypes.byref(cmd), ctypes.sizeof(cmd))
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
        ctypes.windll.ntdll.NtSetTimerResolution(5000, bool(enable), ctypes.byref(cur))

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
BG, CARD, ACC, FG, MUTED, GOOD, BAD = "#0f1117", "#1a1d27", "#7c5cff", "#e8e8f0", "#8a8fa3", "#3ddc97", "#ff5c7a"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ArenaBoost – Game Launcher & Booster")
        self.geometry("1000x680")
        self.minsize(900, 600)
        self.configure(bg=BG)
        self.cfg = load_cfg()
        self.engine = BoostEngine(self.cfg, self.log)
        self.watch_thread = None
        self._style()
        self._build()
        BoostEngine.crash_recover(self.log)
        if not is_admin():
            self.log("⚠ Not running as Administrator: service pause & RAM purge disabled.")
        if not self.cfg["games"]:
            self.scan()
        self.refresh_games()
        self.after(1000, self.update_monitor)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- style
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=CARD, font=("Segoe UI", 10))
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD, foreground=MUTED, padding=(18, 8))
        s.map("TNotebook.Tab", background=[("selected", ACC)], foreground=[("selected", "white")])
        s.configure("Card.TFrame", background=CARD)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG)
        s.configure("Card.TLabel", background=CARD)
        s.configure("Big.TLabel", background=CARD, font=("Segoe UI", 20, "bold"))
        s.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        s.configure("TButton", background=CARD, foreground=FG, borderwidth=0, padding=8)
        s.map("TButton", background=[("active", "#2a2e3d")])
        s.configure("Accent.TButton", background=ACC, foreground="white", font=("Segoe UI", 11, "bold"), padding=12)
        s.map("Accent.TButton", background=[("active", "#6848f0")])
        s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=FG, rowheight=30, borderwidth=0)
        s.configure("Treeview.Heading", background="#232736", foreground=MUTED, borderwidth=0)
        s.map("Treeview", background=[("selected", ACC)])
        s.configure("TCheckbutton", background=CARD, foreground=FG)
        s.map("TCheckbutton", background=[("active", CARD)])
        s.configure("Horizontal.TProgressbar", background=ACC, troughcolor="#232736", borderwidth=0)

    # ---------- layout
    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(top, text="⚡ ArenaBoost", bg=BG, fg=FG, font=("Segoe UI", 18, "bold")).pack(side="left")
        self.status = tk.Label(top, text="● Idle", bg=BG, fg=MUTED, font=("Segoe UI", 11, "bold"))
        self.status.pack(side="right")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=16, pady=6)
        self.tab_games, self.tab_mon, self.tab_net, self.tab_set = (ttk.Frame(nb) for _ in range(4))
        nb.add(self.tab_games, text="🎮  Games")
        nb.add(self.tab_mon, text="📊  Monitor")
        nb.add(self.tab_net, text="🌐  Network")
        nb.add(self.tab_set, text="⚙  Settings")
        self._games_tab()
        self._monitor_tab()
        self._net_tab()
        self._settings_tab()

        lf = ttk.Frame(self, style="Card.TFrame")
        lf.pack(fill="x", padx=16, pady=(4, 14))
        self.logbox = tk.Text(lf, height=7, bg=CARD, fg=MUTED, bd=0, font=("Consolas", 9), wrap="word")
        self.logbox.pack(fill="x", padx=10, pady=8)

    def log(self, msg):
        log.info(msg)

        def _w():
            self.logbox.insert("end", time.strftime("[%H:%M:%S] ") + msg + "\n")
            self.logbox.see("end")
        try:
            self.after(0, _w)
        except Exception:
            pass

    # ---------- games tab
    def _games_tab(self):
        f = self.tab_games
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="🚀  BOOST & LAUNCH", style="Accent.TButton", command=self.boost_launch).pack(side="left")
        ttk.Button(bar, text="Boost only", command=self.boost_only).pack(side="left", padx=6)
        ttk.Button(bar, text="Restore now", command=self.restore_now).pack(side="left")
        ttk.Button(bar, text="🔍 Scan games", command=lambda: (self.scan(), self.refresh_games())).pack(side="right")
        ttk.Button(bar, text="➕ Add game", command=self.add_game).pack(side="right", padx=6)
        ttk.Button(bar, text="✏ Edit", command=self.edit_game).pack(side="right")
        ttk.Button(bar, text="🗑", command=self.remove_game).pack(side="right", padx=6)
        self.tree = ttk.Treeview(f, columns=("src", "proc", "folder"), show="tree headings")
        self.tree.heading("#0", text="Game")
        self.tree.heading("src", text="Source")
        self.tree.heading("proc", text="Game .exe (for auto-restore)")
        self.tree.heading("folder", text="Install folder")
        self.tree.column("#0", width=260)
        self.tree.column("src", width=90)
        self.tree.column("proc", width=200)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.boost_launch())

    def scan(self):
        found = scan_all()
        known = {g["name"] for g in self.cfg["games"]}
        new = [g for g in found if g["name"] not in known]
        self.cfg["games"] += new
        save_cfg(self.cfg)
        self.log(f"🔍 Scan complete: {len(new)} new games found ({len(self.cfg['games'])} total)")

    def refresh_games(self):
        self.tree.delete(*self.tree.get_children())
        for i, g in enumerate(self.cfg["games"]):
            self.tree.insert("", "end", iid=str(i), text="  " + g["name"],
                             values=(g["source"], g.get("process") or "(auto: folder)", g.get("folder", "")))

    def selected_game(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("ArenaBoost", "Select a game first.")
            return None
        return self.cfg["games"][int(sel[0])]

    def add_game(self):
        p = filedialog.askopenfilename(title="Select game .exe", filetypes=[("Programs", "*.exe")])
        if not p:
            return
        name = os.path.splitext(os.path.basename(p))[0]
        self.cfg["games"].append({"name": name, "source": "Manual", "launch": p,
                                  "folder": os.path.dirname(p), "process": os.path.basename(p)})
        save_cfg(self.cfg)
        self.refresh_games()

    def edit_game(self):
        g = self.selected_game()
        if not g:
            return
        w = tk.Toplevel(self, bg=BG)
        w.title("Edit game")
        w.geometry("560x260")
        entries = {}
        for i, (k, lbl) in enumerate([("name", "Name"), ("launch", "Launch command / exe / URL"),
                                      ("folder", "Install folder"), ("process", "Game process .exe (optional)")]):
            tk.Label(w, text=lbl, bg=BG, fg=MUTED).grid(row=i, column=0, sticky="w", padx=10, pady=6)
            e = tk.Entry(w, width=52, bg=CARD, fg=FG, insertbackground=FG, bd=0)
            e.insert(0, g.get(k, ""))
            e.grid(row=i, column=1, padx=10, pady=6)
            entries[k] = e

        def ok():
            for k, e in entries.items():
                g[k] = e.get().strip()
            save_cfg(self.cfg)
            self.refresh_games()
            w.destroy()
        ttk.Button(w, text="Save", style="Accent.TButton", command=ok).grid(row=5, column=1, sticky="e", padx=10, pady=10)

    def remove_game(self):
        sel = self.tree.selection()
        if sel:
            del self.cfg["games"][int(sel[0])]
            save_cfg(self.cfg)
            self.refresh_games()

    # ---------- boost flow
    def set_status(self, text, color):
        self.after(0, lambda: self.status.config(text=text, fg=color))

    def boost_only(self):
        if self.engine.active:
            return self.log("Already boosted.")
        threading.Thread(target=lambda: (self.engine.apply(), self.set_status("● BOOSTED", GOOD)), daemon=True).start()

    def restore_now(self):
        threading.Thread(target=lambda: (self.engine.restore(), self.set_status("● Idle", MUTED)), daemon=True).start()

    def boost_launch(self):
        g = self.selected_game()
        if not g:
            return
        if self.engine.active:
            return self.log("Already boosted – restore first or wait for game to close.")
        threading.Thread(target=self._boost_launch_worker, args=(g,), daemon=True).start()

    def _boost_launch_worker(self, g):
        self.log(f"🚀 Boosting for {g['name']}…")
        self.set_status("● Boosting…", ACC)
        self.engine.apply()
        self.set_status("● BOOSTED", GOOD)
        launch = g["launch"]
        try:
            if "://" in launch and not launch.startswith('"'):
                os.startfile(launch) if IS_WIN else None
            elif launch.startswith('"') or " --" in launch:
                subprocess.Popen(launch, shell=True, cwd=g.get("folder") or None)
            else:
                subprocess.Popen([launch], cwd=os.path.dirname(launch) or None)
        except Exception as e:
            self.log(f"❌ Launch failed: {e}")
            self.engine.restore()
            self.set_status("● Idle", MUTED)
            return
        self.log("⏳ Waiting for game process (up to 3 min)…")
        procs, t0 = [], time.time()
        while time.time() - t0 < 180 and not procs:
            time.sleep(2)
            procs = find_game_procs(g)
        if not procs:
            self.log("⚠ Game process not detected. Tweaks stay ON – press 'Restore now' when done "
                     "(tip: set the game .exe in Edit).")
            return
        main = max(procs, key=lambda p: (p.memory_info().rss if p.is_running() else 0))
        self.log(f"🎮 Detected {main.name()} (PID {main.pid})")
        if self.cfg["opt"]["priority"]:
            for p in procs:
                try:
                    p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS if IS_WIN else -5)
                except Exception:
                    pass
            self.log("⬆ Game priority -> Above Normal (safe, never Realtime)")
        # keep re-suspending hogs that respawn, until game exits
        while True:
            time.sleep(5)
            alive = find_game_procs(g)
            if not alive:
                break
            if self.cfg["opt"]["suspend"]:
                pids = {p.pid for p in alive}
                extra = WinTweaks.suspend_hogs(self.cfg["hogs"], pids)
                extra = [x for x in extra if x not in self.engine.state.get("suspended", [])]
                if extra:
                    self.engine.state.setdefault("suspended", []).extend(extra)
                    self.engine._save_state()
        self.log(f"🏁 {g['name']} closed.")
        self.engine.restore()
        self.set_status("● Idle", MUTED)

    # ---------- monitor tab
    def _monitor_tab(self):
        f = self.tab_mon
        grid = ttk.Frame(f)
        grid.pack(fill="x", pady=10)
        self.cards = {}
        for i, k in enumerate(["CPU", "RAM", "Disk", "Network"]):
            c = ttk.Frame(grid, style="Card.TFrame")
            c.grid(row=0, column=i, sticky="nsew", padx=6)
            grid.columnconfigure(i, weight=1)
            ttk.Label(c, text=k, style="Muted.TLabel").pack(anchor="w", padx=14, pady=(12, 0))
            v = ttk.Label(c, text="–", style="Big.TLabel")
            v.pack(anchor="w", padx=14)
            sub = ttk.Label(c, text="", style="Muted.TLabel")
            sub.pack(anchor="w", padx=14)
            pb = ttk.Progressbar(c, maximum=100)
            pb.pack(fill="x", padx=14, pady=(6, 14))
            self.cards[k] = (v, sub, pb)
        rowf = ttk.Frame(f)
        rowf.pack(fill="x")
        ttk.Button(rowf, text="🧹 Purge standby RAM now", command=lambda: self.log(
            "🧹 " + WinTweaks.purge_standby())).pack(side="left", padx=6)
        ttk.Button(rowf, text="⚠ Check overlays/stutter causes", command=self.check_overlays).pack(side="left")
        ttk.Label(f, text="Top processes by CPU / RAM", foreground=MUTED).pack(anchor="w", pady=(12, 2))
        self.ptree = ttk.Treeview(f, columns=("cpu", "ram"), show="tree headings", height=9)
        self.ptree.heading("#0", text="Process")
        self.ptree.heading("cpu", text="CPU %")
        self.ptree.heading("ram", text="RAM MB")
        self.ptree.pack(fill="both", expand=True)
        self._last_net = psutil.net_io_counters()
        self._last_disk = psutil.disk_io_counters()
        self._tick = 0

    def check_overlays(self):
        w = WinTweaks.overlay_warnings()
        for x in w or ["No common overlay problems found."]:
            self.log("⚠ " + x)
        disk = psutil.disk_usage(os.environ.get("SystemDrive", "/") + os.sep)
        if disk.percent > 90:
            self.log("⚠ System drive over 90% full - can cause stutter.")
        if psutil.virtual_memory().total < 8.5 * 2**30:
            self.log("ℹ Under 8 GB RAM: close browsers before gaming; standby purge helps you most.")

    def update_monitor(self):
        try:
            cpu = psutil.cpu_percent()
            vm = psutil.virtual_memory()
            n = psutil.net_io_counters()
            d = psutil.disk_io_counters()
            down = (n.bytes_recv - self._last_net.bytes_recv) / 1024
            up = (n.bytes_sent - self._last_net.bytes_sent) / 1024
            dmb = ((d.read_bytes + d.write_bytes) - (self._last_disk.read_bytes + self._last_disk.write_bytes)) / 2**20 if d else 0
            self._last_net, self._last_disk = n, d
            freq = psutil.cpu_freq()
            self._card("CPU", f"{cpu:.0f}%", f"{psutil.cpu_count()} threads" + (f" • {freq.current:.0f} MHz" if freq else ""), cpu)
            self._card("RAM", f"{vm.percent:.0f}%", f"{vm.used/2**30:.1f} / {vm.total/2**30:.1f} GB", vm.percent)
            self._card("Disk", f"{dmb:.1f} MB/s", "read + write", min(100, dmb))
            self._card("Network", f"↓{down:.0f} KB/s", f"↑{up:.0f} KB/s", min(100, down / 50))
            self._tick += 1
            if self._tick % 3 == 0:
                procs = []
                for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
                    try:
                        procs.append((p.info["name"], p.info["cpu_percent"] or 0, p.info["memory_info"].rss / 2**20))
                    except Exception:
                        pass
                procs.sort(key=lambda x: (-x[1], -x[2]))
                self.ptree.delete(*self.ptree.get_children())
                for name, c, r in procs[:12]:
                    self.ptree.insert("", "end", text="  " + str(name), values=(f"{c:.1f}", f"{r:.0f}"))
        except Exception as e:
            log.error("monitor %s", e)
        self.after(1000, self.update_monitor)

    def _card(self, k, v, sub, pct):
        a, b, pb = self.cards[k]
        a.config(text=v)
        b.config(text=sub)
        pb["value"] = pct

    # ---------- network tab
    def _net_tab(self):
        f = self.tab_net
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="📡 Test ping to regions", style="Accent.TButton", command=self.ping_all).pack(side="left")
        ttk.Button(bar, text="🔎 Find bandwidth hogs", command=self.find_hogs).pack(side="left", padx=6)
        ttk.Button(bar, text="Flush DNS", command=lambda: self.log(run("ipconfig /flushdns").strip()[:120])).pack(side="left")
        self.ntree = ttk.Treeview(f, columns=("ping", "jit", "loss", "q"), show="tree headings", height=8)
        for c, t in [("#0", "Region"), ("ping", "Ping ms"), ("jit", "Jitter ms"), ("loss", "Loss %"), ("q", "Quality")]:
            self.ntree.heading(c, text=t)
        self.ntree.pack(fill="x")
        tips = ("Honest tips: Software cannot shorten the distance to a server. Real ping wins come from: "
                "Ethernet cable instead of Wi-Fi • 5 GHz Wi-Fi if no cable • choosing the closest region "
                "(for Pakistan usually Bahrain/UAE/Mumbai) • pausing downloads/streams on ALL devices • "
                "a routing service (ExitLag/Mudfish) if your ISP routes badly. ArenaBoost pauses local "
                "bandwidth hogs (browsers, torrents, updates, OneDrive) while you play.")
        tk.Label(f, text=tips, bg=CARD, fg=MUTED, wraplength=920, justify="left", padx=12, pady=10).pack(fill="x", pady=10)
        self.htree = ttk.Treeview(f, columns=("pid", "conn"), show="tree headings", height=6)
        self.htree.heading("#0", text="Process with most connections")
        self.htree.heading("pid", text="PID")
        self.htree.heading("conn", text="Connections")
        self.htree.pack(fill="both", expand=True)

    def ping_all(self):
        self.ntree.delete(*self.ntree.get_children())
        self.log("📡 Testing ping… (TCP, no admin needed)")

        def work():
            for region, host in PING_TARGETS.items():
                r = tcp_ping(host)
                if r:
                    avg, jit, loss = r
                    q = "Excellent" if avg < 50 else "Good" if avg < 90 else "OK" if avg < 150 else "Poor"
                    vals = (f"{avg:.0f}", f"{jit:.1f}", f"{loss:.0f}", q)
                else:
                    vals = ("timeout", "-", "100", "Unreachable")
                self.after(0, lambda reg=region, v=vals: self.ntree.insert("", "end", text="  " + reg, values=v))
            self.log("📡 Ping test done. High jitter = Wi-Fi or someone downloading.")
        threading.Thread(target=work, daemon=True).start()

    def find_hogs(self):
        self.htree.delete(*self.htree.get_children())
        for name, pid, n in top_network_users():
            self.htree.insert("", "end", text="  " + name, values=(pid, n))

    # ---------- settings tab
    def _settings_tab(self):
        f = ttk.Frame(self.tab_set, style="Card.TFrame")
        f.pack(fill="both", expand=True, pady=10)
        self.vars = {}
        opts = [("power", "Switch to Ultimate/High Performance power plan (restored after)"),
                ("priority", "Raise game priority to Above Normal (never Realtime)"),
                ("suspend", "Suspend background hogs (resumed after, no data loss)"),
                ("services", "Pause Windows Update / Delivery Optimization / Search / SysMain / BITS (admin)"),
                ("standby", "One-time standby RAM purge before launch (admin) – no looping 'RAM cleaner'"),
                ("timer", "0.5 ms timer resolution while boosted (smoother frame pacing in some games)"),
                ("gamebar_warn", "Warn about overlays/recording that cause stutter")]
        for k, t in opts:
            v = tk.BooleanVar(value=self.cfg["opt"].get(k, True))
            self.vars[k] = v
            ttk.Checkbutton(f, text=t, variable=v, command=self.save_opts).pack(anchor="w", padx=16, pady=5)
        ttk.Label(f, text="Background apps to suspend (one per line):", style="Card.TLabel").pack(anchor="w", padx=16, pady=(12, 2))
        self.hogtext = tk.Text(f, height=8, bg="#232736", fg=FG, bd=0, insertbackground=FG, font=("Consolas", 9))
        self.hogtext.insert("1.0", "\n".join(self.cfg["hogs"]))
        self.hogtext.pack(fill="x", padx=16)
        ttk.Button(f, text="Save list", command=self.save_hogs).pack(anchor="e", padx=16, pady=8)
        ttk.Label(f, text="🛡 Anti-cheat safe: ArenaBoost never reads, writes or injects into game memory. "
                          "System & anti-cheat processes are protected.", style="Muted.TLabel").pack(anchor="w", padx=16)
        ttk.Label(f, text=f"Config & logs: {APP_DIR}", style="Muted.TLabel").pack(anchor="w", padx=16, pady=4)

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

    def on_close(self):
        if self.engine.active:
            self.engine.restore()
        self.destroy()


def main():
    if IS_WIN and not is_admin() and "--no-admin" not in sys.argv:
        try:
            if relaunch_as_admin():
                return  # elevated copy started; if UAC declined we continue without admin
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
