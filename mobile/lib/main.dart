// ArenaBoost Mobile v2 - Safe Game Launcher & Booster (Android + iOS)
// Created by Ghost - Copyright (c) 2026 Ghost - MIT License
//
// Android: real boost (background clean, DND, rotation lock, thermal, RAM) via MethodChannel.
// iOS: Apple blocks boosting -> launcher + ping test + checklist.
import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

const appName = 'ArenaBoost', appVersion = '2.2.0', author = 'Ghost';

// ---------------------------------------------------------------- design tokens
const bg = Color(0xFF0B0D14), surface = Color(0xFF161A26), surface2 = Color(0xFF1E2333);
const acc = Color(0xFF8B5CF6), acc2 = Color(0xFF22D3EE);
const good = Color(0xFF34D399), warn = Color(0xFFFBBF24), bad = Color(0xFFF87171), muted = Color(0xFF8A90A6);
const gradient = LinearGradient(colors: [acc, acc2], begin: Alignment.topLeft, end: Alignment.bottomRight);

const native = MethodChannel('arenaboost/native');

/// Overridable in tests.
bool Function() isAndroidPlatform = () => Platform.isAndroid;

// ---------------------------------------------------------------- orientation
/// Launcher screen orientation. Default = portrait (vertical).
const appOrientations = {
  'portrait': [DeviceOrientation.portraitUp],
  'landscape': [DeviceOrientation.landscapeLeft, DeviceOrientation.landscapeRight],
  'auto': <DeviceOrientation>[],
};

Future<void> applyAppOrientation(String mode) =>
    SystemChrome.setPreferredOrientations(appOrientations[mode] ?? appOrientations['portrait']!);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final sp = await SharedPreferences.getInstance();
  await applyAppOrientation(sp.getString('appOrientation') ?? 'portrait');
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent, systemNavigationBarColor: bg));
  runApp(const ArenaBoostApp());
}

class ArenaBoostApp extends StatelessWidget {
  const ArenaBoostApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: appName,
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: bg,
          colorScheme: const ColorScheme.dark(primary: acc, secondary: acc2, surface: surface),
          cardTheme: CardThemeData(
              color: surface, elevation: 0, margin: const EdgeInsets.symmetric(vertical: 6),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20),
                  side: const BorderSide(color: Color(0xFF232A3D)))),
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
  'UAE / Dubai': 'dynamodb.me-central-1.amazonaws.com',
  'Mumbai': 'dynamodb.ap-south-1.amazonaws.com',
  'Singapore': 'dynamodb.ap-southeast-1.amazonaws.com',
  'Frankfurt (EU)': 'dynamodb.eu-central-1.amazonaws.com',
  'Virginia (US)': 'dynamodb.us-east-1.amazonaws.com',
};

String mb(num b) => '${(b / 1048576).toStringAsFixed(0)} MB';
String gb(num b) => '${(b / 1073741824).toStringAsFixed(1)} GB';

// ================================================================ HOME SHELL
class Home extends StatefulWidget {
  const Home({super.key});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> with WidgetsBindingObserver, SingleTickerProviderStateMixin {
  int tab = 0;
  List<GameApp> apps = [];
  Set<String> myGames = {};
  bool loading = true, showAll = false, boosting = false, boostedSession = false;
  bool gameBarActive = false;
  String activeGame = '';
  DateTime? boostStarted;
  String query = '', appOrientation = 'portrait', gameRotation = 'off', gameBar = 'on';
  Map mem = {}, dev = {};
  final logs = <String>[];
  Timer? timer;
  late final AnimationController pulse =
      AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
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
    pulse.dispose();
    super.dispose();
  }

  /// Auto-restore when the user comes back from the game.
  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    if (s == AppLifecycleState.resumed && boostedSession) {
      boostedSession = false;
      if (isAndroid) {
        // Fire-and-forget, but never let a channel error go unhandled here.
        if (gameBarActive) {
          gameBarActive = false;
          native.invokeMethod('setGameBar', {'on': false}).catchError((e) => log('⚠ Game bar hide: $e'));
        }
        native.invokeMethod('setDnd', {'on': false}).catchError((e) => log('⚠ DND restore: $e'));
        if (gameRotation != 'off') {
          native.invokeMethod('lockRotation', {'mode': 'off'}).catchError((e) => log('⚠ Rotation restore: $e'));
        }
      }
      log('✅ Welcome back - notifications & rotation restored');
      _refreshStats();
    }
  }

  void log(String m) {
    if (!mounted) return;
    final t = TimeOfDay.now();
    setState(() => logs.insert(0, '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}  $m'));
  }

  Future<void> _init() async {
    final sp = await SharedPreferences.getInstance();
    myGames = (sp.getStringList('myGames') ?? []).toSet();
    appOrientation = sp.getString('appOrientation') ?? 'portrait';
    gameRotation = sp.getString('gameRotation') ?? 'off';
    gameBar = sp.getString('gameBar') ?? 'on';
    await _loadApps();
    await _refreshStats();
    timer = Timer.periodic(const Duration(seconds: 3), (_) => _refreshStats());
  }

  Future<void> _loadApps() async {
    setState(() => loading = true);
    final out = <GameApp>[];
    if (isAndroid) {
      try {
        final list = await native.invokeListMethod<Map>('getApps') ?? [];
        for (final m in list) {
          out.add(GameApp(m['pkg'], m['name'], m['icon'] as Uint8List?,
              m['isGame'] == true || myGames.contains(m['pkg'])));
        }
      } catch (e) {
        log('❌ Could not read apps: $e');
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
    if (!mounted) return;
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
      if (gameBarActive) _pushGameBar();
    } catch (_) {}
  }

  /// Live stats for the floating game bar (runs on the 3 s timer while active).
  void _pushGameBar() {
    final total = (mem['total'] ?? 0) as num, avail = (mem['avail'] ?? 0) as num;
    final ram = total > 0 ? (1 - avail / total) * 100 : 0.0;
    final cpu = (dev['cpuUsage'] ?? 0) as num;
    final temp = (dev['batteryTemp'] ?? 0) as num;
    final el = boostStarted != null ? DateTime.now().difference(boostStarted!) : Duration.zero;
    final mm = el.inMinutes.toString().padLeft(2, '0');
    final ss = (el.inSeconds % 60).toString().padLeft(2, '0');
    native.invokeMethod('gameBarUpdate',
        {'text': '⚡ $activeGame · CPU ${cpu.toStringAsFixed(0)}% · RAM ${ram.toStringAsFixed(0)}% · ${temp.toStringAsFixed(0)}°C · $mm:$ss'})
        .catchError((_) {});
  }

  Future<void> _toggleGame(GameApp a) async {
    setState(() => a.isGame = !a.isGame);
    a.isGame ? myGames.add(a.id) : myGames.remove(a.id);
    (await SharedPreferences.getInstance()).setStringList('myGames', myGames.toList());
  }

  Future<void> setAppOrientation(String m) async {
    setState(() => appOrientation = m);
    (await SharedPreferences.getInstance()).setString('appOrientation', m);
    await applyAppOrientation(m);
    log('📱 Launcher orientation: $m');
  }

  Future<void> setGameBarPref(String m) async {
    setState(() => gameBar = m);
    (await SharedPreferences.getInstance()).setString('gameBar', m);
    log(m == 'on' ? '📺 Game bar: shown while gaming' : '📺 Game bar: off');
  }

  Future<void> setGameRotation(String m) async {
    if (m != 'off' && isAndroid && await native.invokeMethod<bool>('canWriteSettings') != true) {
      log('🔓 Allow "Modify system settings" for ArenaBoost, then choose again');
      await native.invokeMethod('requestWriteSettings');
      return;
    }
    setState(() => gameRotation = m);
    (await SharedPreferences.getInstance()).setString('gameRotation', m);
  }

  // ---------------- quick boost (no launch)
  Future<Map?> quickClean() async {
    if (!isAndroid) return null;
    try {
      final r = await native.invokeMapMethod('boost', {'keep': <String>[]});
      final msg = 'Cleaned ${r?['killed']} apps, freed ~${mb(r?['freed'] ?? 0)}';
      log('🧹 $msg');
      _toast('⚡ Boost done! $msg');
      _refreshStats();
      return r;
    } catch (e) {
      log('❌ Clean failed: $e');
      _toast('Clean failed');
      return null;
    }
  }

  /// Visible confirmation (the activity log may be below the fold on small phones).
  void _toast(String m) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
          content: Text(m), behavior: SnackBarBehavior.floating, backgroundColor: surface2,
          duration: const Duration(seconds: 3)));
  }

  // ---------------- BOOST & LAUNCH
  Future<void> boostAndLaunch(GameApp g) async {
    if (!isAndroid) {
      try {
        await launchUrl(Uri.parse('${g.id}://'), mode: LaunchMode.externalApplication);
      } catch (e) {
        log('❌ Could not open ${g.name} ($e) - is it still installed?');
      }
      return;
    }
    setState(() => boosting = true);
    try {
      log('🚀 Boosting for ${g.name}…');
      await _refreshStats();
      if ((dev['batteryTemp'] ?? 0) > 42) {
        log('🌡 Phone is hot (${dev['batteryTemp']}°C) - performance will throttle. Remove case / cool down.');
      }
      if (dev['powerSave'] == true) log('🔋 Battery Saver is ON - it limits CPU/GPU. Turn it off for gaming.');
      if (dev['network'] == 'Mobile data') log('📶 On mobile data - 4G ping varies; Wi-Fi 5GHz is usually more stable.');
      final r = await native.invokeMapMethod('boost', {'keep': [g.id]});
      log('🧹 Cleared background of ${r?['killed']} apps, freed ~${mb(r?['freed'] ?? 0)}');
      final dnd = await native.invokeMethod<bool>('setDnd', {'on': true});
      log(dnd == true ? '🔕 Do Not Disturb ON (starred contacts can still call)' : '🔔 DND skipped - allow it in Settings');
      if (gameRotation != 'off') {
        final ok = await native.invokeMethod<bool>('lockRotation', {'mode': gameRotation});
        log(ok == true ? '🔒 Screen rotation locked: $gameRotation' : '🔓 Rotation lock needs permission (Settings)');
      }
      if (gameBar == 'on') {
        if (await native.invokeMethod<bool>('canDrawOverlays') != true) {
          log('📺 Game bar needs "Display over other apps" permission - opened Settings');
          await native.invokeMethod('requestDrawOverlays');
        } else if (await native.invokeMethod<bool>('setGameBar', {'on': true, 'title': g.name}) == true) {
          gameBarActive = true;
          activeGame = g.name;
          boostStarted = DateTime.now();
          log('📺 Game bar on - tap it to come back & restore');
        }
      }
      await Future.delayed(const Duration(milliseconds: 400));
      boostedSession = true;
      final launched = await native.invokeMethod<bool>('launch', {'pkg': g.id});
      log(launched == true ? '🎮 Launched ${g.name}. Settings restore when you come back.' : '❌ Could not open ${g.name}');
    } catch (e) {
      log('❌ Boost error: $e');
    } finally {
      if (mounted) setState(() => boosting = false);
    }
  }

  // ================================================================ UI
  @override
  Widget build(BuildContext context) {
    final pages = [
      _homePage(),
      _gamesPage(),
      const NetworkPage(),
      _monitorPage(),
      _settingsPage(),
    ];
    return Scaffold(
      body: SafeArea(
        child: Stack(children: [
          AnimatedSwitcher(duration: const Duration(milliseconds: 220), child: KeyedSubtree(key: ValueKey(tab), child: pages[tab])),
          if (boosting)
            Container(
              color: Colors.black87,
              child: const Center(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  SizedBox(width: 120, height: 120, child: CircularProgressIndicator(strokeWidth: 6, color: acc2)),
                  SizedBox(height: 22),
                  Text('Boosting…', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
                  Text('Cleaning background • DND • Rotation', style: TextStyle(color: muted)),
                ]),
              ),
            ),
        ]),
      ),
      bottomNavigationBar: NavigationBar(
        backgroundColor: surface,
        indicatorColor: acc.withValues(alpha: .25),
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.bolt_outlined), selectedIcon: Icon(Icons.bolt), label: 'Boost'),
          NavigationDestination(icon: Icon(Icons.sports_esports_outlined), selectedIcon: Icon(Icons.sports_esports), label: 'Games'),
          NavigationDestination(icon: Icon(Icons.wifi), label: 'Network'),
          NavigationDestination(icon: Icon(Icons.speed), label: 'Monitor'),
          NavigationDestination(icon: Icon(Icons.tune), label: 'Settings'),
        ],
      ),
    );
  }

  // ---------------- HOME / BOOST
  Widget _homePage() {
    final total = (mem['total'] ?? 0) as num, avail = (mem['avail'] ?? 0) as num;
    final used = total > 0 ? 1 - avail / total : 0.0;
    final games = apps.where((a) => a.isGame).toList();
    return ListView(padding: const EdgeInsets.fromLTRB(18, 12, 18, 18), children: [
      Row(children: [
        Expanded(
          child: Align(
            alignment: Alignment.centerLeft,
            child: FittedBox(
              child: ShaderMask(
                shaderCallback: (r) => gradient.createShader(r),
                child: const Text('⚡ $appName', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: Colors.white)),
              ),
            ),
          ),
        ),
        IconButton(tooltip: 'Refresh', onPressed: _loadApps, icon: const Icon(Icons.refresh, color: muted)),
      ]),
      const Text('Created by $author', style: TextStyle(color: muted, fontSize: 12)),
      const SizedBox(height: 18),
      if (!isAndroid)
        _note('iPhone note: Apple does not allow any app to close other apps, free RAM or change performance. '
            'On iOS, ArenaBoost is a launcher + ping test + checklist.'),
      Center(
        child: GestureDetector(
          key: const Key('boostOrb'),
          onTap: isAndroid ? quickClean : () => setState(() => tab = 2),
          child: AnimatedBuilder(
            animation: pulse,
            builder: (_, __) => CustomPaint(
              painter: _OrbPainter(used.toDouble(), pulse.value),
              child: SizedBox(
                width: 230, height: 230,
                child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  const Icon(Icons.bolt, size: 44, color: Colors.white),
                  Text(isAndroid ? 'BOOST' : 'PING TEST',
                      style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900, letterSpacing: 2)),
                  if (isAndroid)
                    Text('RAM ${(used * 100).toStringAsFixed(0)}% used', style: const TextStyle(color: Colors.white70)),
                ]),
              ),
            ),
          ),
        ),
      ),
      const SizedBox(height: 18),
      if (isAndroid)
        Row(children: [
          _chip(Icons.thermostat, '${((dev['batteryTemp'] ?? 0) as num).toStringAsFixed(0)}°C',
              ((dev['batteryTemp'] ?? 0) as num) > 42 ? bad : good),
          _chip(Icons.battery_std, '${dev['battery'] ?? '-'}%', dev['powerSave'] == true ? warn : good),
          _chip(dev['network'] == 'Wi-Fi' ? Icons.wifi : Icons.signal_cellular_alt, '${dev['network'] ?? '-'}', acc2),
        ]),
      const SizedBox(height: 18),
      Row(children: [
        const Expanded(
            child: Text('Quick launch', overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800))),
        TextButton(onPressed: () => setState(() => tab = 1), child: const Text('All games ›')),
      ]),
      SizedBox(
        height: 118,
        child: loading
            ? const Center(child: CircularProgressIndicator())
            : games.isEmpty
                ? _note(isAndroid ? 'No games yet — open Games and tap ☆ to add.' : 'No supported games found.')
                : ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: games.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 12),
                    itemBuilder: (_, i) => _gameTile(games[i], compact: true),
                  ),
      ),
      const SizedBox(height: 10),
      _logCard(),
    ]);
  }

  Widget _chip(IconData i, String t, Color c) => Expanded(
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 4),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(color: surface, borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFF232A3D))),
          child: Column(children: [
            Icon(i, color: c, size: 20),
            const SizedBox(height: 4),
            Text(t, style: const TextStyle(fontWeight: FontWeight.w700), overflow: TextOverflow.ellipsis),
          ]),
        ),
      );

  Widget _gameTile(GameApp a, {bool compact = false}) => InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () => boostAndLaunch(a),
        onLongPress: isAndroid ? () => _toggleGame(a) : null,
        child: Container(
          width: compact ? 92 : null,
          decoration: BoxDecoration(color: surface, borderRadius: BorderRadius.circular(20),
              border: Border.all(color: const Color(0xFF232A3D))),
          child: Stack(children: [
            Padding(
              padding: const EdgeInsets.all(10),
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                Container(
                  decoration: BoxDecoration(borderRadius: BorderRadius.circular(16),
                      boxShadow: [BoxShadow(color: acc.withValues(alpha: .35), blurRadius: 14)]),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(16),
                    child: a.icon != null
                        ? Image.memory(a.icon!, width: compact ? 48 : 58, height: compact ? 48 : 58)
                        : Container(width: compact ? 48 : 58, height: compact ? 48 : 58,
                            decoration: const BoxDecoration(gradient: gradient),
                            child: const Icon(Icons.sports_esports, color: Colors.white)),
                  ),
                ),
                const SizedBox(height: 8),
                Text(a.name, maxLines: compact ? 1 : 2, textAlign: TextAlign.center, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                if (!compact) ...[
                  const SizedBox(height: 4),
                  const Text('🚀 Boost', style: TextStyle(fontSize: 11, color: acc2, fontWeight: FontWeight.w800)),
                ],
              ]),
            ),
            if (isAndroid && !compact)
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
      );

  // ---------------- GAMES
  Widget _gamesPage() {
    if (loading) return const Center(child: CircularProgressIndicator());
    var list = showAll ? apps : apps.where((a) => a.isGame).toList();
    if (query.isNotEmpty) list = list.where((a) => a.name.toLowerCase().contains(query.toLowerCase())).toList();
    return ListView(padding: const EdgeInsets.fromLTRB(18, 12, 18, 18), children: [
      _title('Games', 'Tap to Boost & Launch · ☆ to add or remove'),
      TextField(
        key: const Key('search'),
        onChanged: (v) => setState(() => query = v),
        decoration: InputDecoration(
          hintText: 'Search',
          prefixIcon: const Icon(Icons.search, color: muted),
          filled: true, fillColor: surface,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
        ),
      ),
      const SizedBox(height: 8),
      Row(children: [
        Expanded(
          child: Text(showAll ? 'All apps (tap ☆ to mark as game)' : 'My games (${list.length})',
              overflow: TextOverflow.ellipsis, style: const TextStyle(color: muted)),
        ),
        if (isAndroid)
          TextButton(onPressed: () => setState(() => showAll = !showAll), child: Text(showAll ? 'Games only' : 'Show all apps')),
      ]),
      if (list.isEmpty)
        _note(isAndroid ? 'No games detected. Tap "Show all apps" and star your games.' : 'No supported games found on this iPhone.'),
      GridView.extent(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        maxCrossAxisExtent: 130,
        childAspectRatio: 0.72,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        children: list.map((a) => _gameTile(a)).toList(),
      ),
      const SizedBox(height: 12),
      _logCard(),
    ]);
  }

  // ---------------- MONITOR
  Widget _monitorPage() {
    if (!isAndroid) {
      return ListView(padding: const EdgeInsets.all(18), children: [
        _title('Monitor', null),
        _note('iOS does not expose RAM, CPU or temperature to apps. Check: Settings › Battery › Battery Health, '
            'and Settings › General › iPhone Storage (keep 10%+ free).'),
      ]);
    }
    final total = (mem['total'] ?? 1) as num, avail = (mem['avail'] ?? 0) as num;
    final used = 1 - avail / total;
    final temp = (dev['batteryTemp'] ?? 0) as num;
    final sFree = (dev['storageFree'] ?? 0) as num, sTot = (dev['storageTotal'] ?? 1) as num;
    return ListView(padding: const EdgeInsets.fromLTRB(18, 12, 18, 18), children: [
      _title('Monitor', '${dev['model'] ?? ''} · ${dev['android'] ?? ''}'),
      _stat('RAM', '${(used * 100).toStringAsFixed(0)}%', '${gb(total - avail)} / ${gb(total)} used', used.toDouble(),
          used > .85 ? bad : used > .7 ? warn : good, Icons.memory),
      _stat('Temperature', '${temp.toStringAsFixed(1)}°C', dev['thermal'] ?? '', (temp / 50).clamp(0, 1).toDouble(),
          temp > 42 ? bad : temp > 38 ? warn : good, Icons.thermostat),
      _stat('Battery', '${dev['battery'] ?? '-'}%',
          '${dev['charging'] == true ? '⚡ Charging (adds heat while gaming)' : 'On battery'}${dev['powerSave'] == true ? ' • Battery Saver ON ⚠' : ''}',
          ((dev['battery'] ?? 0) as num) / 100, dev['powerSave'] == true ? warn : good, Icons.battery_std),
      _stat('Storage free', gb(sFree), sFree / sTot < .1 ? 'Under 10% free - causes lag!' : 'OK', 1 - sFree / sTot,
          sFree / sTot < .1 ? bad : good, Icons.sd_storage),
      Card(child: ListTile(
        leading: const Icon(Icons.developer_board, color: acc2),
        title: Text('Chip: ${dev['cpu'] ?? ''} · ${dev['cores'] ?? ''} cores'),
        subtitle: Text('Screen ${dev['refresh'] ?? ''} Hz · ${dev['network'] ?? ''}', style: const TextStyle(color: muted)),
      )),
      const SizedBox(height: 8),
      _gradientButton(Icons.cleaning_services, 'Clean background apps now', quickClean),
    ]);
  }

  // ---------------- SETTINGS
  Widget _settingsPage() => ListView(padding: const EdgeInsets.fromLTRB(18, 12, 18, 18), children: [
        _title('Settings', null),
        _section('SCREEN ORIENTATION'),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('ArenaBoost screen', style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              SegmentedButton<String>(
                key: const Key('appOrientation'),
                segments: const [
                  ButtonSegment(value: 'portrait', label: Text('Vertical'), icon: Icon(Icons.stay_current_portrait)),
                  ButtonSegment(value: 'landscape', label: Text('Horizontal'), icon: Icon(Icons.stay_current_landscape)),
                  ButtonSegment(value: 'auto', label: Text('Auto'), icon: Icon(Icons.screen_rotation)),
                ],
                selected: {appOrientation},
                onSelectionChanged: (s) => setAppOrientation(s.first),
              ),
              if (isAndroid) ...[
                const SizedBox(height: 16),
                const Text('Lock rotation while gaming', style: TextStyle(fontWeight: FontWeight.w700)),
                const Text('Stops the screen flipping by accident mid-match. Restored when you return.',
                    style: TextStyle(color: muted, fontSize: 12)),
                const SizedBox(height: 8),
                SegmentedButton<String>(
                  key: const Key('gameRotation'),
                  segments: const [
                    ButtonSegment(value: 'off', label: Text('Game decides')),
                    ButtonSegment(value: 'portrait', label: Text('Vertical')),
                    ButtonSegment(value: 'landscape', label: Text('Horizontal')),
                  ],
                  selected: {gameRotation},
                  onSelectionChanged: (s) => setGameRotation(s.first),
                ),
                const SizedBox(height: 6),
                const Text('Note: games that force their own orientation (e.g. PUBG = horizontal) always win.',
                    style: TextStyle(color: muted, fontSize: 11)),
              ],
            ]),
          ),
        ),
        if (isAndroid) ...[
          Card(
            child: SwitchListTile(
              title: const Text('Show game bar during gaming'),
              subtitle: const Text('Floating bar over your game: CPU · RAM · temp · time.\nTap it to come back - everything restores.',
                  style: TextStyle(color: muted, fontSize: 12)),
              value: gameBar == 'on',
              onChanged: (v) => setGameBarPref(v ? 'on' : 'off'),
            ),
          ),
          _section('PERMISSIONS & SYSTEM'),
          _tool(Icons.do_not_disturb_on, 'Allow Do Not Disturb control', 'Blocks notifications during matches',
              () => native.invokeMethod('requestDndAccess')),
          _tool(Icons.smart_display, 'Allow game bar overlay', '"Display over other apps" permission',
              () => native.invokeMethod('requestDrawOverlays')),
          _tool(Icons.screen_lock_rotation, 'Allow rotation lock', '"Modify system settings" permission',
              () => native.invokeMethod('requestWriteSettings')),
          _tool(Icons.battery_charging_full, 'Battery optimization', 'Set your games to "Unrestricted"',
              () => native.invokeMethod('openBatteryOpt')),
          _tool(Icons.developer_mode, 'Developer options', 'Animation scales to 0.5x for a snappier phone',
              () => native.invokeMethod('openDevOptions')),
        ],
        _section('PRO CHECKLIST'),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              ...(isAndroid ? androidTips : iosTips).map((t) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Icon(Icons.check_circle, color: good, size: 16),
                      const SizedBox(width: 8),
                      Expanded(child: Text(t, style: const TextStyle(color: muted))),
                    ]),
                  )),
            ]),
          ),
        ),
        _section('ABOUT'),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              ShaderMask(
                shaderCallback: (r) => gradient.createShader(r),
                child: const Text('⚡ $appName', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: Colors.white)),
              ),
              const Text('Version $appVersion', style: TextStyle(color: muted)),
              const SizedBox(height: 8),
              const Text('Created by $author', style: TextStyle(color: acc, fontWeight: FontWeight.w800, fontSize: 16)),
              const Text('© 2026 $author · MIT License', style: TextStyle(color: muted)),
              const SizedBox(height: 8),
              const Text('🛡 Anti-cheat safe: never modifies game files or memory — no ban risk.',
                  style: TextStyle(color: muted, fontSize: 12)),
              const SizedBox(height: 6),
              const Text('🔒 Secure: no telemetry, no data ever leaves your phone, no cleartext traffic, '
                  'app data excluded from cloud backups, each permission granted by you.',
                  style: TextStyle(color: muted, fontSize: 12)),
            ]),
          ),
        ),
      ]);

  // ---------------- shared widgets
  Widget _title(String t, String? sub) => Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(t, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
          if (sub != null) Text(sub, style: const TextStyle(color: muted)),
        ]),
      );

  Widget _section(String t) => Padding(
      padding: const EdgeInsets.fromLTRB(4, 16, 4, 6),
      child: Text(t, style: const TextStyle(color: muted, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1.2)));

  Widget _stat(String t, String v, String sub, double pct, Color c, IconData icon) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Icon(icon, color: c, size: 20),
              const SizedBox(width: 8),
              Expanded(child: Text(t, overflow: TextOverflow.ellipsis, style: const TextStyle(color: muted))),
              Text(v, style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: c)),
            ]),
            const SizedBox(height: 10),
            LinearProgressIndicator(value: pct.clamp(0, 1), color: c, backgroundColor: surface2, minHeight: 8,
                borderRadius: BorderRadius.circular(6)),
            const SizedBox(height: 6),
            Text(sub, style: const TextStyle(color: muted, fontSize: 12)),
          ]),
        ),
      );

  Widget _gradientButton(IconData i, String t, VoidCallback f) => InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: f,
        child: Ink(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(gradient: gradient, borderRadius: BorderRadius.circular(18)),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(i, color: Colors.white),
            const SizedBox(width: 10),
            Flexible(child: Text(t, overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w800, color: Colors.white))),
          ]),
        ),
      );

  Widget _tool(IconData i, String t, String s, VoidCallback f) => Card(
      child: ListTile(leading: Icon(i, color: acc2), title: Text(t), subtitle: Text(s, style: const TextStyle(color: muted)),
          trailing: const Icon(Icons.chevron_right), onTap: f));

  Widget _note(String t) => Card(
      color: surface2,
      child: Padding(padding: const EdgeInsets.all(14), child: Text(t, style: const TextStyle(color: muted, fontSize: 13))));

  Widget _logCard() => Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('ACTIVITY', style: TextStyle(fontWeight: FontWeight.w800, color: muted, fontSize: 11, letterSpacing: 1.2)),
            const SizedBox(height: 6),
            if (logs.isEmpty)
              const Text('Tap a game to boost & launch. Long-press / ☆ to add or remove games.',
                  style: TextStyle(color: muted, fontSize: 12)),
            ...logs.take(12).map((l) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 1),
                  child: Text(l, style: const TextStyle(color: Color(0xFFB7BDD1), fontSize: 12)),
                )),
          ]),
        ),
      );
}

class _OrbPainter extends CustomPainter {
  final double used, pulse;
  _OrbPainter(this.used, this.pulse);
  @override
  void paint(Canvas c, Size s) {
    final ctr = s.center(Offset.zero), r = s.width / 2;
    c.drawCircle(ctr, r - 4 + pulse * 4,
        Paint()..color = acc.withValues(alpha: .18 + pulse * .12)..maskFilter = const MaskFilter.blur(BlurStyle.normal, 22));
    c.drawCircle(ctr, r - 26, Paint()..shader = gradient.createShader(Rect.fromCircle(center: ctr, radius: r - 26)));
    final ring = Paint()..style = PaintingStyle.stroke..strokeWidth = 10..strokeCap = StrokeCap.round;
    c.drawCircle(ctr, r - 10, ring..color = surface2);
    final col = used > .85 ? bad : used > .7 ? warn : good;
    c.drawArc(Rect.fromCircle(center: ctr, radius: r - 10), -math.pi / 2, 2 * math.pi * used.clamp(0, 1), false,
        ring..color = col);
  }

  @override
  bool shouldRepaint(covariant _OrbPainter o) => o.used != used || o.pulse != pulse;
}

const androidTips = [
  'Turn OFF Battery Saver while gaming - it caps CPU/GPU.',
  'Use your phone\'s built-in Game Mode / Game Space / Game Turbo - it has system powers no app has.',
  'Don\'t game while fast-charging - heat = throttling = FPS drops.',
  'Remove thick case during long sessions; avoid direct sun.',
  'Keep 10-15% storage free; clear game cache from inside the game only.',
  'Wi-Fi 5 GHz, sit near router; ask family to pause YouTube/downloads.',
  'Pick the closest server (Middle East / Asia for Pakistan).',
  'Stable 60 FPS beats unstable 90 - pick what your phone can hold.',
  'Restart phone once a day before long gaming sessions.',
];

const iosTips = [
  'Turn OFF Low Power Mode (Settings › Battery) - it caps performance.',
  'Enable Focus › Gaming / Do Not Disturb to block notifications.',
  'Use Control Center rotation lock to stop accidental flips.',
  'Turn off Background App Refresh for apps you don\'t need.',
  'Keep 10-15% storage free (Settings › General › iPhone Storage).',
  'Don\'t game while charging - heat causes throttling.',
  'Wi-Fi 5 GHz near the router; pick closest server region.',
  'Check Battery Health - below ~80% the iPhone may throttle performance.',
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

  Future<void> testAll() async {
    setState(() { running = true; results.clear(); });
    for (final e in pingTargets.entries) {
      try { await InternetAddress.lookup(e.value); } catch (_) {}
      final samples = <double?>[];
      for (int i = 0; i < 5; i++) {
        samples.add(await measureTcpPing(e.value));
        await Future.delayed(const Duration(milliseconds: 150));
      }
      if (!mounted) return;
      setState(() => results[e.key] = pingStats(samples));
    }
    if (mounted) setState(() => running = false);
  }

  void toggleLive(String region) {
    liveTimer?.cancel();
    if (liveHost == region) { setState(() => liveHost = null); return; }
    setState(() { liveHost = region; live = []; });
    liveTimer = Timer.periodic(const Duration(seconds: 1), (_) async {
      final p = await measureTcpPing(pingTargets[region]!);
      if (mounted) setState(() { live.add(p ?? 999); if (live.length > 40) live.removeAt(0); });
    });
  }

  Color q(double ms) => ms < 60 ? good : ms < 100 ? warn : bad;

  @override
  Widget build(BuildContext context) {
    final best = results.entries.where((e) => e.value != null).fold<MapEntry<String, List<double>?>?>(
        null, (a, e) => a == null || e.value![0] < a.value![0] ? e : a);
    return ListView(padding: const EdgeInsets.fromLTRB(18, 12, 18, 18), children: [
      const Text('Network', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
      const Text('Ping, jitter & packet loss to game regions', style: TextStyle(color: muted)),
      const SizedBox(height: 14),
      InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: running ? null : testAll,
        child: Ink(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(gradient: gradient, borderRadius: BorderRadius.circular(18)),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            running
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.network_ping, color: Colors.white),
            const SizedBox(width: 10),
            Flexible(
              child: Text(running ? 'Testing…' : 'Test ping to game regions', overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800, color: Colors.white)),
            ),
          ]),
        ),
      ),
      if (best != null)
        Card(
          color: good.withValues(alpha: .12),
          child: ListTile(
            leading: const Icon(Icons.emoji_events, color: good),
            title: Text('Best region: ${best.key}'),
            subtitle: Text('${best.value![0].toStringAsFixed(0)} ms — choose this server in your game',
                style: const TextStyle(color: muted)),
          ),
        ),
      const SizedBox(height: 6),
      ...results.entries.map((e) {
        final r = e.value;
        return Card(
          child: ListTile(
            title: Text(e.key),
            subtitle: Text(r == null ? 'Unreachable' : 'Jitter ${r[1].toStringAsFixed(1)} ms • Loss ${r[2].toStringAsFixed(0)}%',
                style: const TextStyle(color: muted)),
            trailing: Text(r == null ? '—' : '${r[0].toStringAsFixed(0)} ms',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: r == null ? bad : q(r[0]))),
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
        color: surface2,
        child: Padding(
          padding: EdgeInsets.all(14),
          child: Text(
              'Honest note: no app can shorten the distance to the game server. What really lowers ping: '
              '5 GHz Wi-Fi close to the router, pausing downloads/streams on other devices, choosing the nearest '
              'server (UAE/Mumbai for Pakistan), and trying a different network if your ISP route is bad.',
              style: TextStyle(color: muted, fontSize: 13)),
        ),
      ),
    ]);
  }
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
    c.drawPath(p, Paint()..shader = gradient.createShader(Offset.zero & s)..strokeWidth = 2.5..style = PaintingStyle.stroke);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
