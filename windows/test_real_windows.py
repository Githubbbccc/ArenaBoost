"""REAL end-to-end tests on a real Windows PC (run as Administrator).
Nothing here is mocked: real power plans, real services, real RAM purge,
real GUI window, real Boost & Launch of a real process.
GitHub Actions windows-latest runs these with admin rights on every push."""
import os, shutil, subprocess, sys, time, json
import psutil, pytest

sys.argv = ["arenaboost.py"]
import arenaboost as ab

pytestmark = pytest.mark.skipif(os.name != "nt", reason="real Windows only")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(ab, "CFG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(ab, "STATE_FILE", str(tmp_path / "state.json"))


def fake_exe(folder, name):
    """Copy python.exe (+ its DLLs) so we get a real process with our own exe name."""
    src = os.path.dirname(sys.executable)
    os.makedirs(folder, exist_ok=True)
    for f in os.listdir(src):
        if f.lower().endswith(".dll"):
            shutil.copy(os.path.join(src, f), folder)
    exe = os.path.join(folder, name + ".exe")
    shutil.copy(sys.executable, exe)
    return exe


def test_running_as_admin():
    assert ab.is_admin(), "CI must run elevated so admin features are really tested"


def test_real_power_plan_switch_and_restore():
    old = ab.WinTweaks.get_power_plan()
    new = ab.WinTweaks.set_best_power_plan()
    assert ab.WinTweaks.get_power_plan().lower() == new.lower() != old.lower()
    ab.WinTweaks.set_power_plan(old)
    assert ab.WinTweaks.get_power_plan() == old


def test_real_service_pause_and_restart():
    name = next((s for s in ["Spooler", "WSearch", "BITS", "wuauserv"]
                 if _svc_status(s) == "running"), None)
    if not name:
        pytest.skip("no stoppable service running on this machine")
    stopped = ab.WinTweaks.stop_services([name])
    assert stopped == [name]
    _wait(lambda: _svc_status(name) == "stopped")
    ab.WinTweaks.start_services(stopped)
    _wait(lambda: _svc_status(name) == "running")


def test_real_standby_purge():
    r = ab.WinTweaks.purge_standby()
    assert r.startswith("OK"), r


def test_real_data_files_are_owner_only():
    """App runs elevated: config/state must not grant access to BUILTIN\\Users / Everyone."""
    ab.save_cfg(ab.load_cfg())
    out = subprocess.run(f'icacls "{ab.CFG_FILE}"', capture_output=True, text=True).stdout
    assert "BUILTIN\\Users" not in out and "Everyone" not in out, out


def test_real_ping_regions_reachable():
    """Print real ping to every game region from this machine."""
    ok = 0
    for region, host in ab.PING_TARGETS.items():
        r = ab.tcp_ping(host, count=3)
        print(f"REAL ping {region:15s} {host}: {'unreachable' if not r else f'{r[0]:.0f} ms'}")
        ok += bool(r)
    assert ok >= len(ab.PING_TARGETS) // 2


def test_real_double_suspend_is_fully_resumed(tmp_path):
    """Real Windows suspend counting: after a long game session the hog must run again."""
    hog = fake_exe(str(tmp_path / "h"), "abhog2")
    p = subprocess.Popen([hog, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(1)
        first = ab.WinTweaks.suspend_hogs(["abhog2.exe"], set())
        for _ in range(5):  # simulate the 5-second re-check loop
            ab.WinTweaks.suspend_hogs(["abhog2.exe"], set(), already=first)
        ab.WinTweaks.resume_pids(first)
        time.sleep(0.5)
        assert psutil.Process(p.pid).status() != psutil.STATUS_STOPPED
    finally:
        p.kill()


def test_real_timer_resolution():
    assert ab.WinTweaks.set_timer(True) is True
    assert ab.WinTweaks.set_timer(False) is True


def test_selftest_command_passes():
    out = subprocess.run([sys.executable, ab.__file__, "--selftest"], capture_output=True, text=True, timeout=120)
    print(out.stdout, out.stderr)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "[PASS] Standby RAM purge" in out.stdout
    assert "[PASS] Power plan switch + restore" in out.stdout


def test_gui_opens_and_every_page_works():
    app = ab.App()
    try:
        for key, _, _ in ab.App.PAGES:
            app.show(key)
            app.update()
            assert app.pages[key].winfo_ismapped()
        app.update_monitor()
        app.update()
        # floating game bar: show, live text, hide
        app.gamebar.show()
        app.update()
        assert app.gamebar.winfo_ismapped()
        app.gamebar.update_text(ab.gamebar_text("SelfTest", 10, 20, 30, 65))
        app.update()
        app.gamebar.hide()
        app.update()
        assert not app.gamebar.winfo_ismapped()
        app.check_overlays()
        app.find_hogs()
        app.search.set("zzz")
        app.search.set("")
        app.save_opts()
        app.hogtext.insert("end", "\ncsrss.exe\nmytesthog.exe")
        app.save_hogs()
        assert "mytesthog.exe" in app.cfg["hogs"] and "csrss.exe" not in app.cfg["hogs"]
        done = []
        app.ping_all({"Local": "127.0.0.1"}, done=lambda: done.append(1))
        t = time.time()
        while not done and time.time() - t < 20:
            app.update(); time.sleep(0.1)
        assert done
    finally:
        app.destroy()


def test_real_boost_and_launch_end_to_end(tmp_path):
    """Full user flow: Boost & Launch a 'game', check tweaks are live while it runs,
    and that EVERYTHING is restored after it closes."""
    hog = fake_exe(str(tmp_path / "hog"), "abhog")
    hog_p = subprocess.Popen([hog, "-c", "import time; time.sleep(120)"])
    game_exe = fake_exe(str(tmp_path / "MyGame"), "mygame")
    launcher = str(tmp_path / "launch.bat")
    open(launcher, "w").write(f'@"{game_exe}" -c "import time; time.sleep(12)"\n')
    old_plan = ab.WinTweaks.get_power_plan()
    app = ab.App()
    try:
        app.cfg["hogs"] = ["abhog.exe"]
        app.cfg["opt"].update(services=False, standby=True, timer=True, power=True, suspend=True, priority=True)
        game = {"name": "MyGame", "source": "Manual", "launch": f'"{launcher}"',
                "folder": str(tmp_path / "MyGame"), "process": "mygame.exe"}
        import threading
        res = {}
        th = threading.Thread(target=lambda: res.setdefault("r", app._boost_launch_worker(game, 60, 1)))
        th.start()
        # while game runs: boosted
        _wait(lambda: ab.find_game_procs(game), 30)
        time.sleep(2)
        assert app.engine.active
        assert ab.WinTweaks.get_power_plan() != old_plan, "power plan not switched"
        assert psutil.Process(hog_p.pid).status() == psutil.STATUS_STOPPED, "hog not suspended"
        _wait(lambda: all(p.nice() == psutil.ABOVE_NORMAL_PRIORITY_CLASS for p in ab.find_game_procs(game)), 20)
        # floating game bar is visible over the running game
        app.update_monitor()
        app.update()
        assert app.gamebar.winfo_ismapped(), "game bar should be visible while the game runs"
        th.join(60)
        # after game closed: everything restored
        assert res.get("r") == "ok"
        assert not app.engine.active
        app.update_monitor()
        app.update()
        assert not app.gamebar.winfo_ismapped(), "game bar should hide after restore"
        assert ab.WinTweaks.get_power_plan() == old_plan, "power plan not restored"
        assert psutil.Process(hog_p.pid).status() != psutil.STATUS_STOPPED, "hog not resumed"
        assert not os.path.exists(ab.STATE_FILE)
    finally:
        app.destroy()
        try:
            psutil.Process(hog_p.pid).resume()
        except Exception:
            pass
        hog_p.kill()
        ab.WinTweaks.set_power_plan(old_plan)


def _svc_status(name):
    try:
        return psutil.win_service_get(name).status()
    except Exception:
        return None


def _wait(cond, timeout=30):
    t = time.time()
    while time.time() - t < timeout:
        if cond():
            return True
        time.sleep(0.5)
    raise AssertionError("condition not met in time")
