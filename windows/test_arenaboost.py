"""Automated tests for ArenaBoost (Windows). Run:  python -m pytest -v
Windows-only system calls (powercfg, sc, ntdll) are mocked on non-Windows CI;
process suspend/resume, detection, ping, config, scanning run for real."""
import json, os, socket, subprocess, sys, time, threading, shutil
from unittest import mock
import psutil, pytest

sys.argv = ["arenaboost.py"]
import arenaboost as ab


@pytest.fixture(autouse=True)
def tmp_appdir(tmp_path, monkeypatch):
    monkeypatch.setattr(ab, "CFG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(ab, "STATE_FILE", str(tmp_path / "state.json"))
    yield tmp_path


def spawn_sleeper(folder=None, name="abtestproc"):
    """Start a real child process with a custom exe name (copy of python)."""
    folder = folder or os.path.dirname(sys.executable)
    exe = os.path.join(folder, name + (".exe" if os.name == "nt" else ""))
    if not os.path.exists(exe):
        shutil.copy(sys.executable, exe)
    return subprocess.Popen([exe, "-c", "import time; time.sleep(60)"]), exe


def cleanup(p, exe):
    try:
        psutil.Process(p.pid).resume()
    except Exception:
        pass
    p.kill(); p.wait(timeout=10)
    for _ in range(20):  # Windows keeps the exe locked briefly after exit
        try:
            os.remove(exe); return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.25)


# ------------------------------------------------------------ config
def test_config_defaults_and_roundtrip():
    cfg = ab.load_cfg()
    assert cfg["opt"]["power"] and "chrome.exe" in cfg["hogs"]
    cfg["games"].append({"name": "X", "source": "Manual", "launch": "x.exe", "folder": "", "process": "x.exe"})
    ab.save_cfg(cfg)
    assert ab.load_cfg()["games"][0]["name"] == "X"


def test_corrupt_config_does_not_crash():
    open(ab.CFG_FILE, "w").write("{broken")
    assert "games" in ab.load_cfg()


def test_protected_never_in_default_hogs():
    assert not set(h.lower() for h in ab.DEFAULT_HOGS) & ab.PROTECTED
    for must in ["csrss.exe", "lsass.exe", "dwm.exe", "vgc.exe", "easyanticheat.exe", "beservice.exe", "explorer.exe"]:
        assert must in ab.PROTECTED


# ------------------------------------------------------------ scanning
def test_scan_steam_libraries(tmp_path):
    steam = tmp_path / "Steam"; lib2 = tmp_path / "Lib2"
    for base in (steam, lib2):
        (base / "steamapps").mkdir(parents=True)
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n "0" { "path" "%s" }\n "1" { "path" "%s" }\n}' % (steam, lib2))
    (steam / "steamapps" / "appmanifest_730.acf").write_text('"AppState"{ "appid" "730" "name" "Counter-Strike 2" "installdir" "Counter-Strike Global Offensive" }')
    (lib2 / "steamapps" / "appmanifest_570.acf").write_text('"AppState"{ "appid" "570" "name" "Dota 2" "installdir" "dota 2 beta" }')
    (lib2 / "steamapps" / "appmanifest_228980.acf").write_text('"AppState"{ "appid" "228980" "name" "Steamworks Common Redistributables" "installdir" "x" }')
    games = {g["name"]: g for g in ab.scan_steam(str(steam))}
    assert set(games) == {"Counter-Strike 2", "Dota 2"}
    assert games["Dota 2"]["launch"] == "steam://rungameid/570"
    assert games["Dota 2"]["folder"].endswith(os.path.join("common", "dota 2 beta"))


def test_scan_epic(tmp_path):
    (tmp_path / "a.item").write_text(json.dumps({"DisplayName": "Fortnite", "AppName": "Fortnite",
        "InstallLocation": "C:/Fortnite", "LaunchExecutable": "FortniteGame/Binaries/Win64/FortniteLauncher.exe",
        "AppCategories": ["public", "games"]}))
    (tmp_path / "b.item").write_text(json.dumps({"DisplayName": "Unreal Engine", "AppName": "UE",
        "InstallLocation": "C:/UE", "AppCategories": ["engines"]}))
    (tmp_path / "c.item").write_text("garbage")
    g = ab.scan_epic(str(tmp_path))
    assert [x["name"] for x in g] == ["Fortnite"]
    assert g[0]["process"] == "FortniteLauncher.exe"
    assert "com.epicgames.launcher://apps/Fortnite" in g[0]["launch"]


def test_scan_all_never_crashes():
    assert isinstance(ab.scan_all(), list)


# ------------------------------------------------------------ process control (REAL)
def test_suspend_and_resume_real_process():
    p, exe = spawn_sleeper(name="abhogtest")
    try:
        time.sleep(0.5)
        pids = ab.WinTweaks.suspend_hogs([os.path.basename(exe)], set())
        assert p.pid in pids
        assert psutil.Process(p.pid).status() == psutil.STATUS_STOPPED or os.name == "nt"
        ab.WinTweaks.resume_pids(pids)
        time.sleep(0.2)
        assert psutil.Process(p.pid).status() != psutil.STATUS_STOPPED
    finally:
        cleanup(p, exe)


def test_suspend_skips_game_and_protected():
    p, exe = spawn_sleeper(name="abhogtest2")
    try:
        time.sleep(0.5)
        assert ab.WinTweaks.suspend_hogs([os.path.basename(exe)], {p.pid}) == []
        assert ab.WinTweaks.suspend_hogs(["csrss.exe", "explorer.exe", "systemd"] if os.name != "nt" else ["csrss.exe"], set()) == [] or os.name != "nt"
    finally:
        cleanup(p, exe)


def test_find_game_by_folder_and_by_name(tmp_path):
    gdir = tmp_path / "MyGame"; gdir.mkdir()
    p, exe = spawn_sleeper(str(gdir), "mygame")
    try:
        time.sleep(0.5)
        by_folder = ab.find_game_procs({"folder": str(gdir), "process": ""})
        assert p.pid in [x.pid for x in by_folder]
        by_name = ab.find_game_procs({"folder": "", "process": os.path.basename(exe)})
        assert p.pid in [x.pid for x in by_name]
        assert ab.find_game_procs({"folder": str(tmp_path / "Nope"), "process": ""}) == []
    finally:
        p.kill()
    p.wait(); time.sleep(0.3)
    assert ab.find_game_procs({"folder": str(gdir), "process": ""}) == []


# ------------------------------------------------------------ boost engine
def make_engine(opts=None):
    cfg = ab.load_cfg()
    cfg["opt"].update(opts or {})
    msgs = []
    return ab.BoostEngine(cfg, msgs.append), msgs


def test_engine_apply_and_restore_everything(monkeypatch):
    monkeypatch.setattr(ab, "IS_WIN", True)
    monkeypatch.setattr(ab, "is_admin", lambda: True)
    W = ab.WinTweaks
    calls = []
    monkeypatch.setattr(W, "get_power_plan", staticmethod(lambda: "old-guid"))
    monkeypatch.setattr(W, "set_best_power_plan", staticmethod(lambda: (calls.append("perf"), "e9a42b02-new")[1]))
    monkeypatch.setattr(W, "set_power_plan", staticmethod(lambda g: calls.append(("restore_power", g))))
    monkeypatch.setattr(W, "stop_services", staticmethod(lambda n: ["wuauserv", "WSearch"]))
    monkeypatch.setattr(W, "start_services", staticmethod(lambda n: calls.append(("start", tuple(n)))))
    monkeypatch.setattr(W, "suspend_hogs", staticmethod(lambda h, g: [111, 222]))
    monkeypatch.setattr(W, "resume_pids", staticmethod(lambda p: calls.append(("resume", tuple(p)))))
    monkeypatch.setattr(W, "purge_standby", staticmethod(lambda: "OK, +500 MB available"))
    monkeypatch.setattr(W, "set_timer", staticmethod(lambda on: calls.append(("timer", on))))
    monkeypatch.setattr(W, "overlay_warnings", staticmethod(lambda: ["Game Bar ON"]))
    e, msgs = make_engine()
    e.apply()
    assert e.active
    st = json.load(open(ab.STATE_FILE))
    assert st["power"] == "old-guid" and st["suspended"] == [111, 222] and st["services"] == ["wuauserv", "WSearch"]
    assert any("Standby" in m for m in msgs) and any("Game Bar" in m for m in msgs)
    e.restore()
    assert ("resume", (111, 222)) in calls
    assert ("start", ("wuauserv", "WSearch")) in calls
    assert ("restore_power", "old-guid") in calls
    assert ("timer", False) in calls
    assert not os.path.exists(ab.STATE_FILE) and not e.active


def test_engine_respects_disabled_options(monkeypatch):
    W = ab.WinTweaks
    for f in ["set_best_power_plan", "stop_services", "suspend_hogs", "purge_standby", "set_timer"]:
        monkeypatch.setattr(W, f, staticmethod(lambda *a: pytest.fail(f"{f} should not run")))
    monkeypatch.setattr(W, "overlay_warnings", staticmethod(lambda: []))
    e, _ = make_engine({k: False for k in ["power", "services", "suspend", "standby", "timer", "gamebar_warn"]})
    e.apply(); e.restore()


def test_crash_recovery_restores_previous_session(monkeypatch):
    json.dump({"suspended": [5, 6], "power": "abc", "services": ["BITS"], "timer": True}, open(ab.STATE_FILE, "w"))
    got = []
    monkeypatch.setattr(ab.WinTweaks, "resume_pids", staticmethod(lambda p: got.append(("resume", p))))
    monkeypatch.setattr(ab.WinTweaks, "set_power_plan", staticmethod(lambda g: got.append(("power", g))))
    monkeypatch.setattr(ab.WinTweaks, "start_services", staticmethod(lambda s: got.append(("svc", s))))
    monkeypatch.setattr(ab.WinTweaks, "set_timer", staticmethod(lambda on: got.append(("timer", on))))
    msgs = []
    ab.BoostEngine.crash_recover(msgs.append)
    assert ("resume", [5, 6]) in got and ("power", "abc") in got and ("svc", ["BITS"]) in got
    assert not os.path.exists(ab.STATE_FILE)
    assert any("previous session" in m for m in msgs)


def test_crash_recovery_real_suspended_process():
    """End-to-end: suspend a real process, 'crash', recover -> it runs again."""
    p, exe = spawn_sleeper(name="abcrash")
    try:
        time.sleep(0.5)
        pids = ab.WinTweaks.suspend_hogs([os.path.basename(exe)], set())
        json.dump({"suspended": pids}, open(ab.STATE_FILE, "w"))
        ab.BoostEngine.crash_recover(lambda m: None)
        time.sleep(0.2)
        assert psutil.Process(p.pid).status() != psutil.STATUS_STOPPED
    finally:
        cleanup(p, exe)


def test_power_plan_parsing(monkeypatch):
    monkeypatch.setattr(ab, "run", lambda c: "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *")
    assert ab.WinTweaks.get_power_plan() == "381b4222-f694-41f0-9685-ff5bb260df2e"


def test_best_power_plan_prefers_ultimate(monkeypatch):
    out = ("Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *\n"
           "Power Scheme GUID: 11111111-2222-3333-4444-555555555555  (Ultimate Performance)")
    cmds = []
    monkeypatch.setattr(ab, "run", lambda c: (cmds.append(c), out)[1])
    assert ab.WinTweaks.set_best_power_plan() == "11111111-2222-3333-4444-555555555555"
    assert "powercfg /setactive 11111111-2222-3333-4444-555555555555" in cmds


def test_best_power_plan_falls_back_to_high_perf(monkeypatch):
    monkeypatch.setattr(ab, "run", lambda c: "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *")
    assert ab.WinTweaks.set_best_power_plan() == ab.HIGH_PERF


def test_standby_purge_requires_admin(monkeypatch):
    monkeypatch.setattr(ab, "is_admin", lambda: False)
    assert "Administrator" in ab.WinTweaks.purge_standby()


# ------------------------------------------------------------ network
def test_tcp_ping_local_server():
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(20)
    port = srv.getsockname()[1]
    threading.Thread(target=lambda: [srv.accept()[0].close() for _ in range(5)], daemon=True).start()
    avg, jit, loss = ab.tcp_ping("127.0.0.1", port, count=5)
    srv.close()
    assert 0 <= avg < 200 and jit >= 0 and loss == 0


def test_tcp_ping_failures():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    assert ab.tcp_ping("127.0.0.1", port, count=2) is None
    assert ab.tcp_ping("does-not-exist.invalid") is None


def test_top_network_users_returns_list():
    assert isinstance(ab.top_network_users(), list)
