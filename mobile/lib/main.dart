// ArenaBoost Mobile - Safe Game Launcher & Booster (Android + iOS)
// Android: real boost (background kill, DND, thermal, RAM) via MethodChannel.
// iOS: Apple blocks boosting -> launcher + ping test + checklist.
import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

const bg = Color(0xFF0F1117), card = Color(0xFF1A1D27), acc = Color(0xFF7C5CFF);
const good = Color(0xFF3DDC97), warn = Color(0xFFFFB84D), bad = Color(0xFFFF5C7A), muted = Color(0xFF8A8FA3);
const native = MethodChannel('arenaboost/native');

/// Overridable in tests.
bool Function() isAndroidPlatform = () => Platform.isAndroid;

void main() => runApp(const ArenaBoostApp());

class ArenaBoostApp extends StatelessWidget {
  const ArenaBoostApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'ArenaBoost',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: bg,
          colorScheme: const ColorScheme.dark(primary: acc, surface: card),
          cardTheme: CardThemeData(color: card, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
          useMaterial3: true,
        ),
        home: const Home(),
      );
}

// ================================================================ MODELS
class GameApp {
  final String id, name; // id = package (Android) or url scheme (iOS)
  final Uint8List? icon;
  bool isGame;
  GameApp(this.id, this.name, this.icon, this.isGame);
}

const iosGames = {
  'PUBG Mobile': 'pubgmobile', 'Free Fire': 'freefire', 'Call of Duty Mobile': 'codm',
  'Mobile Legends': 'mobilelegends', 'Roblox': 'roblox', 'Minecraft': 'minecraft',
  'Clash of Clans': 'clashofclans', 'Clash Royale': 'clashroyale', 'Brawl Stars': 'brawlstars',
};

const pingTargets = {
  'Bahrain (ME)': 'dynamodb.me-south-1.amazonaws.com',
  'UAE / Dubai': 'dynamodb.me-central-1.amazonaws.com',
  'Mumbai': 'dynamodb.ap-south-1.amazonaws.com',
  'Singapore': 'dynamodb.ap-southeast-1.amazonaws.com',
  'Frankfurt (EU)': 'dynamodb.eu-central-1.amazonaws.com',
  'Virginia (US)': 'dynamodb.us-east-1.amazonaws.com',
};

String mb(num b) => '${(b / 1048576).toStringAsFixed(0)} MB';
String gb(num b) => '${(b / 1073741824).toStringAsFixed(1)} GB';

// ================================================================ HOME
class Home extends StatefulWidget {
  const Home({super.key});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> with WidgetsBindingObserver {
  int tab = 0;
  List<GameApp> apps = [];
  Set<String> myGames = {};
  bool loading = true, showAll = false, boosting = false, boostedSession = false;
  Map mem = {}, dev = {};
  final logs = <String>[];
  Timer? timer;
  bool get isAndroid => isAndroidPlatform();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _init();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    timer?.cancel();
    super.dispose();
  }

  // Auto-restore when the user comes back from the game
  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    if (s == AppLifecycleState.resumed && boostedSession) {
      boostedSession = false;
      if (isAndroid) native.invokeMethod('setDnd', {'on': false});
      log('✅ Welcome back - Do Not Disturb restored');
      _refreshStats();
    }
  }

  void log(String m) => setState(() => logs.insert(0, '${TimeOfDay.now().format(context)}  $m'));

  Future<void> _init() async {
    final sp = await SharedPreferences.getInstance();
    myGames = (sp.getStringList('myGames') ?? []).toSet();
    await _loadApps();
    await _refreshStats();
    timer = Timer.periodic(const Duration(seconds: 3), (_) => _refreshStats());
  }

  Future<void> _loadApps() async {
    setState(() => loading = true);
    final out = <GameApp>[];
    if (isAndroid) {
      final list = await native.invokeListMethod<Map>('getApps') ?? [];
      for (final m in list) {
        out.add(GameApp(m['pkg'], m['name'], m['icon'] as Uint8List?, m['isGame'] == true || myGames.contains(m['pkg'])));
      }
    } else {
      for (final e in iosGames.entries) {
        bool ok = false;
        try {
          ok = await canLaunchUrl(Uri.parse('${e.value}://')).timeout(const Duration(seconds: 2));
        } catch (_) {}
        if (ok) out.add(GameApp(e.value, e.key, null, true));
      }
    }
    setState(() {
      apps = out;
      loading = false;
    });
  }

  Future<void> _refreshStats() async {
    if (!isAndroid || !mounted) return;
    try {
      final m = await native.invokeMapMethod('memInfo');
      final d = await native.invokeMapMethod('deviceInfo');
      if (mounted) setState(() { mem = m ?? {}; dev = d ?? {}; });
    } catch (_) {}
  }

  Future<void> _toggleGame(GameApp a) async {
    setState(() => a.isGame = !a.isGame);
    a.isGame ? myGames.add(a.id) : myGames.remove(a.id);
    (await SharedPreferences.getInstance()).setStringList('myGames', myGames.toList());
  }

  // ---------------- BOOST & LAUNCH
  Future<void> boostAndLaunch(GameApp g) async {
    if (!isAndroid) {
      await launchUrl(Uri.parse('${g.id}://'), mode: LaunchMode.externalApplication);
      return;
    }
    setState(() => boosting = true);
    log('🚀 Boosting for ${g.name}…');
    // 1. Thermal / battery checks
    await _refreshStats();
    if ((dev['batteryTemp'] ?? 0) > 42) log('🌡 Phone is hot (${dev['batteryTemp']}°C) - performance will throttle. Remove case / cool down.');
    if (dev['powerSave'] == true) log('🔋 Battery Saver is ON - it limits CPU/GPU. Turn it off for gaming.');
    if (dev['network'] == 'Mobile data') log('📶 On mobile data - 4G ping varies; Wi-Fi 5GHz is usually more stable.');
    // 2. Kill background apps (all except game)
    final r = await native.invokeMapMethod('boost', {'keep': [g.id]});
    log('🧹 Cleared background of ${r?['killed']} apps, freed ~${mb(r?['freed'] ?? 0)}');
    // 3. DND
    final dnd = await native.invokeMethod<bool>('setDnd', {'on': true});
    log(dnd == true ? '🔕 Do Not Disturb ON (calls from starred contacts still allowed)' : '🔔 DND skipped - grant access in Tools tab');
    await Future.delayed(const Duration(milliseconds: 400));
    setState(() => boosting = false);
    boostedSession = true;
    await native.invokeMethod('launch', {'pkg': g.id});
    log('🎮 Launched ${g.name}. Settings restore when you come back.');
  }

  // ================================================================ UI
  @override
  Widget build(BuildContext context) {
    final pages = [_gamesPage(), _monitorPage(), const NetworkPage(), _toolsPage()];
    return Scaffold(
      appBar: AppBar(
        backgroundColor: bg,
        title: const Text('⚡ ArenaBoost', style: TextStyle(fontWeight: FontWeight.bold)),
        actions: [IconButton(onPressed: _loadApps, icon: const Icon(Icons.refresh))],
      ),
      body: Stack(children: [
        pages[tab],
        if (boosting)
          Container(
            color: Colors.black54,
            child: const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              CircularProgressIndicator(color: acc), SizedBox(height: 16),
              Text('Boosting…', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            ])),
          ),
      ]),
      bottomNavigationBar: NavigationBar(
        backgroundColor: card,
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.sports_esports), label: 'Games'),
          NavigationDestination(icon: Icon(Icons.speed), label: 'Monitor'),
          NavigationDestination(icon: Icon(Icons.wifi), label: 'Network'),
          NavigationDestination(icon: Icon(Icons.tune), label: 'Tools'),
        ],
      ),
    );
  }

  Widget _gamesPage() {
    if (loading) return const Center(child: CircularProgressIndicator());
    final list = showAll ? apps : apps.where((a) => a.isGame).toList();
    return ListView(padding: const EdgeInsets.all(12), children: [
      if (!isAndroid)
        _note('iPhone note: Apple does not allow any app to close other apps, free RAM or change performance. '
            'ArenaBoost on iOS = launcher + ping test + checklist (Tools tab).'),
      Row(children: [
        Expanded(
          child: Text(showAll ? 'All apps (tap ☆ to mark as game)' : 'My games (${list.length})',
              overflow: TextOverflow.ellipsis, style: const TextStyle(color: muted)),
        ),
        if (isAndroid) TextButton(onPressed: () => setState(() => showAll = !showAll), child: Text(showAll ? 'Games only' : 'Show all apps')),
      ]),
      if (list.isEmpty) _note(isAndroid ? 'No games detected. Tap "Show all apps" and star your games.' : 'No supported games found on this iPhone.'),
      GridView.count(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        crossAxisCount: 3,
        childAspectRatio: 0.78,
        mainAxisSpacing: 10,
        crossAxisSpacing: 10,
        children: list.map((a) => InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () => boostAndLaunch(a),
              onLongPress: isAndroid ? () => _toggleGame(a) : null,
              child: Card(
                child: Stack(children: [
                  Padding(
                    padding: const EdgeInsets.all(10),
                    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(14),
                        child: a.icon != null
                            ? Image.memory(a.icon!, width: 56, height: 56)
                            : Container(width: 56, height: 56, color: acc, child: const Icon(Icons.sports_esports)),
                      ),
                      const SizedBox(height: 8),
                      Text(a.name, maxLines: 2, textAlign: TextAlign.center, overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 12)),
                      const SizedBox(height: 4),
                      const Text('🚀 Boost', style: TextStyle(fontSize: 11, color: acc, fontWeight: FontWeight.bold)),
                    ]),
                  ),
                  if (isAndroid)
                    Positioned(
                      right: 0, top: 0,
                      child: IconButton(
                        iconSize: 18,
                        icon: Icon(a.isGame ? Icons.star : Icons.star_border, color: a.isGame ? warn : muted),
                        onPressed: () => _toggleGame(a),
                      ),
                    ),
                ]),
              ),
            )).toList(),
      ),
      const SizedBox(height: 12),
      _logCard(),
    ]);
  }

  Widget _monitorPage() {
    if (!isAndroid) {
      return ListView(padding: const EdgeInsets.all(12), children: [
        _note('iOS does not expose RAM, CPU or temperature to apps. Check: Settings › Battery › Battery Health, '
            'and Settings › General › iPhone Storage (keep 10%+ free).'),
      ]);
    }
    final total = (mem['total'] ?? 1) as num, avail = (mem['avail'] ?? 0) as num;
    final used = 1 - avail / total;
    final temp = (dev['batteryTemp'] ?? 0) as num;
    final sFree = (dev['storageFree'] ?? 0) as num, sTot = (dev['storageTotal'] ?? 1) as num;
    return ListView(padding: const EdgeInsets.all(12), children: [
      _stat('RAM', '${(used * 100).toStringAsFixed(0)}%', '${gb(total - avail)} / ${gb(total)} used', used,
          used > .85 ? bad : used > .7 ? warn : good),
      _stat('Temperature', '${temp.toStringAsFixed(1)}°C', dev['thermal'] ?? '', (temp / 50).clamp(0, 1).toDouble(),
          temp > 42 ? bad : temp > 38 ? warn : good),
      _stat('Battery', '${dev['battery'] ?? '-'}%',
          '${dev['charging'] == true ? '⚡ Charging (adds heat while gaming)' : 'On battery'}${dev['powerSave'] == true ? ' • Battery Saver ON ⚠' : ''}',
          ((dev['battery'] ?? 0) as num) / 100, dev['powerSave'] == true ? warn : good),
      _stat('Storage free', gb(sFree), sFree / sTot < .1 ? 'Under 10% free - causes lag!' : 'OK', 1 - sFree / sTot,
          sFree / sTot < .1 ? bad : good),
      Card(child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${dev['model'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.bold)),
          Text('${dev['android'] ?? ''}', style: const TextStyle(color: muted)),
          Text('Chip: ${dev['cpu'] ?? ''} • ${dev['cores'] ?? ''} cores • Screen ${dev['refresh'] ?? ''} Hz • ${dev['network'] ?? ''}',
              style: const TextStyle(color: muted)),
        ]),
      )),
      const SizedBox(height: 8),
      FilledButton.icon(
        style: FilledButton.styleFrom(backgroundColor: acc, padding: const EdgeInsets.all(16)),
        onPressed: () async {
          final r = await native.invokeMapMethod('boost', {'keep': <String>[]});
          log('🧹 Cleaned ${r?['killed']} apps, freed ~${mb(r?['freed'] ?? 0)}');
          _refreshStats();
          if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Freed ~${mb(r?['freed'] ?? 0)}')));
        },
        icon: const Icon(Icons.cleaning_services),
        label: const Text('Clean background apps now'),
      ),
    ]);
  }

  Widget _toolsPage() => ListView(padding: const EdgeInsets.all(12), children: [
        if (isAndroid) ...[
          _tool(Icons.do_not_disturb_on, 'Allow Do Not Disturb control', 'Needed to block notifications during matches',
              () => native.invokeMethod('requestDndAccess')),
          _tool(Icons.battery_charging_full, 'Battery optimization', 'Set games to "Unrestricted"',
              () => native.invokeMethod('openBatteryOpt')),
          _tool(Icons.developer_mode, 'Developer options',
              'Set Window/Transition/Animator scale to 0.5x or off for snappier UI', () => native.invokeMethod('openDevOptions')),
        ],
        const SizedBox(height: 8),
        Card(child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('✅ Pro gaming checklist', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 8),
            ...(isAndroid ? androidTips : iosTips).map((t) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Text('• $t', style: const TextStyle(color: muted)),
                )),
          ]),
        )),
        _note('🛡 Safe: ArenaBoost never modifies game files or memory - no ban risk with PUBG, Free Fire, CODM anti-cheat.'),
      ]);

  // ---------- widgets
  Widget _stat(String t, String v, String sub, double pct, Color c) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Text(t, style: const TextStyle(color: muted)),
              const Spacer(),
              Text(v, style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: c)),
            ]),
            const SizedBox(height: 8),
            LinearProgressIndicator(value: pct.clamp(0, 1), color: c, backgroundColor: const Color(0xFF232736), minHeight: 6,
                borderRadius: BorderRadius.circular(4)),
            const SizedBox(height: 6),
            Text(sub, style: const TextStyle(color: muted, fontSize: 12)),
          ]),
        ),
      );

  Widget _tool(IconData i, String t, String s, VoidCallback f) =>
      Card(child: ListTile(leading: Icon(i, color: acc), title: Text(t), subtitle: Text(s, style: const TextStyle(color: muted)),
          trailing: const Icon(Icons.chevron_right), onTap: f));

  Widget _note(String t) => Card(
      color: const Color(0xFF232736),
      child: Padding(padding: const EdgeInsets.all(14), child: Text(t, style: const TextStyle(color: muted, fontSize: 13))));

  Widget _logCard() => Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Activity', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            if (logs.isEmpty) const Text('Tap a game to boost & launch. Long-press / ☆ to add or remove games.', style: TextStyle(color: muted, fontSize: 12)),
            ...logs.take(12).map((l) => Text(l, style: const TextStyle(color: muted, fontSize: 12, fontFamily: 'monospace'))),
          ]),
        ),
      );
}

const androidTips = [
  'Turn OFF Battery Saver while gaming - it caps CPU/GPU.',
  'Use your phone\'s built-in Game Mode / Game Space / Game Turbo (Samsung Game Booster, Xiaomi Game Turbo, Oppo Game Space) - it has system powers no app has.',
  'Don\'t game while fast-charging - heat = throttling = FPS drops.',
  'Remove thick case during long sessions; avoid direct sun.',
  'Keep 10-15% storage free; clear game cache from inside the game only.',
  'Wi-Fi 5 GHz, sit near router; ask family to pause YouTube/downloads.',
  'Pick the closest server (Middle East / Asia for Pakistan).',
  'Set in-game FPS to what your phone can hold steady - stable 60 beats unstable 90.',
  'Restart phone once a day before long gaming sessions.',
];

const iosTips = [
  'Turn OFF Low Power Mode (Settings › Battery) - it caps performance.',
  'Enable Focus › Gaming / Do Not Disturb to block notifications.',
  'Settings › Accessibility › Motion › Reduce Motion ON for snappier UI.',
  'Turn off Background App Refresh for apps you don\'t need.',
  'Keep 10-15% storage free (Settings › General › iPhone Storage).',
  'Don\'t game while charging - heat causes throttling.',
  'Wi-Fi 5 GHz near the router; pick closest server region.',
  'Check Battery Health - below ~80% the iPhone may throttle performance.',
  'Restart iPhone before long sessions.',
];

// ================================================================ NETWORK (both platforms)
class NetworkPage extends StatefulWidget {
  const NetworkPage({super.key});
  @override
  State<NetworkPage> createState() => _NetworkPageState();
}

class _NetworkPageState extends State<NetworkPage> {
  final results = <String, List<double>?>{};
  bool running = false;
  List<double> live = [];
  Timer? liveTimer;
  String? liveHost;

  @override
  void dispose() {
    liveTimer?.cancel();
    super.dispose();
  }

  Future<double?> tcpPing(String host) => measureTcpPing(host);


  Future<void> testAll() async {
    setState(() { running = true; results.clear(); });
    for (final e in pingTargets.entries) {
      try { await InternetAddress.lookup(e.value); } catch (_) {} // warm DNS
      final samples = <double?>[];
      for (int i = 0; i < 5; i++) {
        samples.add(await tcpPing(e.value));
        await Future.delayed(const Duration(milliseconds: 150));
      }
      if (!mounted) return;
      setState(() => results[e.key] = pingStats(samples));
    }
    setState(() => running = false);
  }

  void toggleLive(String region) {
    liveTimer?.cancel();
    if (liveHost == region) { setState(() => liveHost = null); return; }
    setState(() { liveHost = region; live = []; });
    liveTimer = Timer.periodic(const Duration(seconds: 1), (_) async {
      final p = await tcpPing(pingTargets[region]!);
      if (mounted) setState(() { live.add(p ?? 999); if (live.length > 40) live.removeAt(0); });
    });
  }

  Color q(double ms) => ms < 60 ? good : ms < 100 ? warn : bad;

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(12), children: [
        FilledButton.icon(
          style: FilledButton.styleFrom(backgroundColor: acc, padding: const EdgeInsets.all(16)),
          onPressed: running ? null : testAll,
          icon: const Icon(Icons.network_ping),
          label: Text(running ? 'Testing…' : 'Test ping to game regions'),
        ),
        const SizedBox(height: 8),
        ...results.entries.map((e) {
          final r = e.value;
          return Card(
            child: ListTile(
              title: Text(e.key),
              subtitle: Text(r == null ? 'Unreachable' : 'Jitter ${r[1].toStringAsFixed(1)} ms • Loss ${r[2].toStringAsFixed(0)}%',
                  style: const TextStyle(color: muted)),
              trailing: Text(r == null ? '—' : '${r[0].toStringAsFixed(0)} ms',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: r == null ? bad : q(r[0]))),
              onTap: () => toggleLive(e.key),
            ),
          );
        }),
        if (results.isNotEmpty) const Text('  Tap a region for a live ping graph', style: TextStyle(color: muted, fontSize: 12)),
        if (liveHost != null)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Live: $liveHost  ${live.isEmpty ? '' : '${live.last.toStringAsFixed(0)} ms'}',
                    style: const TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 10),
                SizedBox(height: 90, child: CustomPaint(painter: _Graph(live), size: Size.infinite)),
                const Text('Spikes = Wi-Fi interference or someone downloading on your network.',
                    style: TextStyle(color: muted, fontSize: 12)),
              ]),
            ),
          ),
        const Card(
          color: Color(0xFF232736),
          child: Padding(
            padding: EdgeInsets.all(14),
            child: Text(
                'Honest note: no app can shorten the distance to the game server. What really lowers ping: '
                '5 GHz Wi-Fi close to the router, pausing downloads/streams on other devices, choosing the nearest '
                'server (Bahrain/UAE/Mumbai for Pakistan), and trying a different network if your ISP route is bad.',
                style: TextStyle(color: muted, fontSize: 13)),
          ),
        ),
      ]);
}

/// TCP connect time in ms to host:443 (works without root/admin on Android & iOS).
Future<double?> measureTcpPing(String host, {int port = 443}) async {
  try {
    final sw = Stopwatch()..start();
    final s = await Socket.connect(host, port, timeout: const Duration(seconds: 2));
    sw.stop();
    s.destroy();
    return sw.elapsedMicroseconds / 1000;
  } catch (_) {
    return null;
  }
}

/// [avg, jitter, loss%] from samples (null = failed attempt).
List<double>? pingStats(List<double?> samples) {
  final t = samples.whereType<double>().toList();
  if (t.isEmpty) return null;
  final avg = t.reduce((a, b) => a + b) / t.length;
  final jit = t.length > 1
      ? List.generate(t.length - 1, (i) => (t[i + 1] - t[i]).abs()).reduce((a, b) => a + b) / (t.length - 1)
      : 0.0;
  return [avg, jit, (samples.length - t.length) / samples.length * 100];
}

class _Graph extends CustomPainter {
  final List<double> d;
  _Graph(this.d);
  @override
  void paint(Canvas c, Size s) {
    if (d.length < 2) return;
    final mx = d.reduce((a, b) => a > b ? a : b).clamp(50, 400).toDouble();
    final p = Path();
    for (int i = 0; i < d.length; i++) {
      final x = s.width * i / 39, y = s.height - (d[i].clamp(0, mx) / mx) * s.height;
      i == 0 ? p.moveTo(x, y) : p.lineTo(x, y);
    }
    c.drawPath(p, Paint()..color = acc..strokeWidth = 2.5..style = PaintingStyle.stroke);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
