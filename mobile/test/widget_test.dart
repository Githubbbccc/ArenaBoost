import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:arenaboost/main.dart';

/// Fake Android native layer: records every call so we can verify each flow.
final calls = <MethodCall>[];
List<String> get names => calls.map((c) => c.method).toList();
final orientations = <List>[];
Map<String, dynamic> fakeDev({double temp = 35, bool powerSave = false, String net = 'Wi-Fi'}) => {
      'model': 'Test Phone', 'android': 'Android 14 (API 34)', 'cpu': 'qcom', 'cores': 8,
      'batteryTemp': temp, 'battery': 80, 'charging': false, 'thermal': 'Normal',
      'powerSave': powerSave, 'network': net, 'refresh': 120,
      'storageFree': 20 * 1073741824, 'storageTotal': 128 * 1073741824,
    };
var dev = fakeDev();
bool dndGranted = true, canWrite = true;

void installFakes() {
  final m = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  m.setMockMethodCallHandler(native, (c) async {
    calls.add(c);
    switch (c.method) {
      case 'getApps':
        return [
          {'pkg': 'com.tencent.ig', 'name': 'PUBG MOBILE', 'isGame': true, 'icon': null},
          {'pkg': 'com.dts.freefireth', 'name': 'Free Fire', 'isGame': true, 'icon': null},
          {'pkg': 'com.whatsapp', 'name': 'WhatsApp', 'isGame': false, 'icon': null},
        ];
      case 'memInfo':
        return {'total': 8 * 1073741824, 'avail': 3 * 1073741824, 'low': false, 'threshold': 0};
      case 'deviceInfo':
        return dev;
      case 'boost':
        return {'killed': 12, 'freed': 450 * 1048576};
      case 'setDnd':
        return dndGranted;
      case 'canWriteSettings':
        return canWrite;
      case 'lockRotation':
        return canWrite;
      case 'launch':
        return true;
    }
    return true;
  });
  m.setMockMethodCallHandler(SystemChannels.platform, (c) async {
    if (c.method == 'SystemChrome.setPreferredOrientations') orientations.add(c.arguments as List);
    return null;
  });
}

Future<void> pumpApp(WidgetTester t) async {
  await t.binding.setSurfaceSize(const Size(420, 2600));
  await t.pumpWidget(const ArenaBoostApp());
  await t.pump();
  await t.pump(const Duration(milliseconds: 100));
}

Future<void> goTab(WidgetTester t, String label) async {
  await t.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text(label)));
  await t.pump();
  await t.pump(const Duration(milliseconds: 300));
}

Future<void> boostGame(WidgetTester t, String name) async {
  await goTab(t, 'Games');
  await t.tap(find.text(name));
  await t.pump();
  await t.pump(const Duration(seconds: 1));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    calls.clear();
    orientations.clear();
    dev = fakeDev();
    dndGranted = true;
    canWrite = true;
    SharedPreferences.setMockInitialValues({});
    isAndroidPlatform = () => true;
    installFakes();
  });

  group('Branding & license', () {
    testWidgets('Created by Ghost shown on home and About', (t) async {
      await pumpApp(t);
      expect(find.text('Created by Ghost'), findsOneWidget);
      await goTab(t, 'Settings');
      expect(find.text('Created by Ghost'), findsOneWidget);
      expect(find.textContaining('MIT License'), findsOneWidget);
      expect(find.textContaining('© 2026 Ghost'), findsOneWidget);
    });
  });

  group('Home / Boost', () {
    testWidgets('home shows orb, RAM, stats chips and quick-launch games', (t) async {
      await pumpApp(t);
      expect(find.text('BOOST'), findsOneWidget);
      expect(find.text('RAM 63% used'), findsOneWidget);
      expect(find.text('35°C'), findsOneWidget);
      expect(find.text('Wi-Fi'), findsOneWidget);
      expect(find.text('PUBG MOBILE'), findsOneWidget);
      expect(find.text('WhatsApp'), findsNothing);
    });

    testWidgets('tapping the orb cleans background apps', (t) async {
      await pumpApp(t);
      calls.clear();
      await t.tap(find.byKey(const Key('boostOrb')));
      await t.pump();
      expect(names, contains('boost'));
      expect(find.textContaining('Cleaned 12 apps'), findsNWidgets(2)); // log + visible toast
      expect(find.textContaining('Boost done!'), findsOneWidget);
    });

    testWidgets('quick-launch tile boosts and launches', (t) async {
      await pumpApp(t);
      calls.clear();
      await t.tap(find.text('Free Fire'));
      await t.pump();
      await t.pump(const Duration(seconds: 1));
      expect(names, containsAllInOrder(['boost', 'setDnd', 'launch']));
    });
  });

  group('Games tab', () {
    testWidgets('detects games and hides non-games', (t) async {
      await pumpApp(t);
      await goTab(t, 'Games');
      expect(find.text('My games (2)'), findsOneWidget);
      expect(find.text('WhatsApp'), findsNothing);
    });

    testWidgets('search filters games', (t) async {
      await pumpApp(t);
      await goTab(t, 'Games');
      await t.enterText(find.byKey(const Key('search')), 'free');
      await t.pump();
      expect(find.text('Free Fire'), findsOneWidget);
      expect(find.text('PUBG MOBILE'), findsNothing);
    });

    testWidgets('"Show all apps" + star adds a game and saves it', (t) async {
      await pumpApp(t);
      await goTab(t, 'Games');
      await t.tap(find.text('Show all apps'));
      await t.pump();
      await t.tap(find.byIcon(Icons.star_border).first);
      await t.pump();
      await t.tap(find.text('Games only'));
      await t.pump();
      expect(find.text('WhatsApp'), findsOneWidget);
      expect((await SharedPreferences.getInstance()).getStringList('myGames'), contains('com.whatsapp'));
    });

    testWidgets('Boost & Launch: full flow in correct order', (t) async {
      await pumpApp(t);
      calls.clear();
      await boostGame(t, 'PUBG MOBILE');
      expect(names, containsAllInOrder(['deviceInfo', 'boost', 'setDnd', 'launch']));
      expect(calls.firstWhere((c) => c.method == 'boost').arguments['keep'], ['com.tencent.ig']);
      expect(calls.firstWhere((c) => c.method == 'launch').arguments['pkg'], 'com.tencent.ig');
      expect(names, isNot(contains('lockRotation')), reason: 'default = game decides');
      expect(find.textContaining('freed ~450 MB'), findsOneWidget);
      expect(find.textContaining('Launched PUBG MOBILE'), findsOneWidget);
    });

    testWidgets('warnings: hot phone, battery saver, mobile data', (t) async {
      dev = fakeDev(temp: 45, powerSave: true, net: 'Mobile data');
      await pumpApp(t);
      await boostGame(t, 'Free Fire');
      expect(find.textContaining('Phone is hot'), findsOneWidget);
      expect(find.textContaining('Battery Saver is ON'), findsOneWidget);
      expect(find.textContaining('On mobile data'), findsOneWidget);
    });

    testWidgets('DND without permission is skipped gracefully', (t) async {
      dndGranted = false;
      await pumpApp(t);
      await boostGame(t, 'Free Fire');
      expect(find.textContaining('DND skipped'), findsOneWidget);
      expect(names, contains('launch'));
    });

    testWidgets('native error does not freeze the app', (t) async {
      await pumpApp(t);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(native, (c) async {
        if (c.method == 'boost') throw PlatformException(code: 'ERR', message: 'boom');
        return fakeDev();
      });
      await boostGame(t, 'Free Fire');
      expect(find.textContaining('Boost error'), findsOneWidget);
      expect(find.text('Boosting…'), findsNothing);
    });
  });

  group('Orientation', () {
    testWidgets('launcher defaults to vertical and can switch', (t) async {
      await pumpApp(t);
      await goTab(t, 'Settings');
      await t.tap(find.text('Horizontal').first);
      await t.pump();
      expect(orientations.last, ['DeviceOrientation.landscapeLeft', 'DeviceOrientation.landscapeRight']);
      await t.tap(find.text('Vertical').first);
      await t.pump();
      expect(orientations.last, ['DeviceOrientation.portraitUp']);
      expect((await SharedPreferences.getInstance()).getString('appOrientation'), 'portrait');
    });

    testWidgets('lock rotation while gaming: locks on launch, restores on return', (t) async {
      await pumpApp(t);
      await goTab(t, 'Settings');
      await t.tap(find.descendant(of: find.byKey(const Key('gameRotation')), matching: find.text('Horizontal')));
      await t.pump();
      calls.clear();
      await boostGame(t, 'PUBG MOBILE');
      final lock = calls.firstWhere((c) => c.method == 'lockRotation');
      expect(lock.arguments['mode'], 'landscape');
      expect(names.indexOf('lockRotation'), lessThan(names.indexOf('launch')));
      calls.clear();
      // real Android sequence: user goes to the game and comes back
      for (final st in [AppLifecycleState.inactive, AppLifecycleState.hidden, AppLifecycleState.paused,
          AppLifecycleState.hidden, AppLifecycleState.inactive, AppLifecycleState.resumed]) {
        t.binding.handleAppLifecycleStateChanged(st);
      }
      await t.pump();
      expect(calls.where((c) => c.method == 'lockRotation').single.arguments['mode'], 'off');
      expect(names, contains('setDnd'));
      expect(find.textContaining('rotation restored'), findsOneWidget);
    });

    testWidgets('without permission it opens the permission screen', (t) async {
      canWrite = false;
      await pumpApp(t);
      await goTab(t, 'Settings');
      await t.tap(find.descendant(of: find.byKey(const Key('gameRotation')), matching: find.text('Vertical')));
      await t.pump();
      expect(names, contains('requestWriteSettings'));
      expect((await SharedPreferences.getInstance()).getString('gameRotation'), isNull);
    });
  });

  group('Monitor tab', () {
    testWidgets('shows RAM, temp, battery, storage and cleans', (t) async {
      await pumpApp(t);
      await goTab(t, 'Monitor');
      expect(find.text('63%'), findsOneWidget);
      expect(find.text('35.0°C'), findsOneWidget);
      expect(find.text('80%'), findsOneWidget);
      expect(find.text('20.0 GB'), findsOneWidget);
      expect(find.textContaining('120 Hz'), findsOneWidget);
      calls.clear();
      await t.tap(find.text('Clean background apps now'));
      await t.pump();
      expect(names, contains('boost'));
      expect(find.textContaining('Boost done! Cleaned 12 apps, freed ~450 MB'), findsOneWidget);
    });
  });

  group('Settings tools', () {
    testWidgets('buttons open correct system screens', (t) async {
      await pumpApp(t);
      await goTab(t, 'Settings');
      for (final e in {
        'Allow Do Not Disturb control': 'requestDndAccess',
        'Allow rotation lock': 'requestWriteSettings',
        'Battery optimization': 'openBatteryOpt',
        'Developer options': 'openDevOptions',
      }.entries) {
        calls.clear();
        await t.ensureVisible(find.text(e.key));
        await t.tap(find.text(e.key));
        await t.pump();
        expect(names, [e.value]);
      }
    });
  });

  group('iOS mode', () {
    testWidgets('iOS note, no native calls, iOS tips, no Android tools', (t) async {
      isAndroidPlatform = () => false;
      await pumpApp(t);
      for (int i = 0; i < 12; i++) {
        await t.pump(const Duration(seconds: 2));
      }
      expect(find.textContaining('iPhone note'), findsOneWidget);
      expect(find.text('PING TEST'), findsOneWidget);
      expect(names, isEmpty);
      await goTab(t, 'Monitor');
      expect(find.textContaining('iOS does not expose'), findsOneWidget);
      await goTab(t, 'Settings');
      expect(find.textContaining('Low Power Mode'), findsOneWidget);
      expect(find.text('Battery optimization'), findsNothing);
      expect(find.byKey(const Key('gameRotation')), findsNothing);
      expect(find.byKey(const Key('appOrientation')), findsOneWidget);
    });
  });

  group('Network', () {
    test('pingStats: average, jitter, loss', () {
      final r = pingStats([10, 20, null, 30, null])!;
      expect(r, [20, 10, 40]);
      expect(pingStats([null, null]), isNull);
      expect(pingStats([50])!, [50, 0, 0]);
    });

    test('measureTcpPing: real local TCP server & closed port', () async {
      final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((s) => s.destroy());
      final ms = await measureTcpPing('127.0.0.1', port: server.port);
      expect(ms, isNotNull);
      expect(ms!, lessThan(500));
      final closed = server.port;
      await server.close();
      expect(await measureTcpPing('127.0.0.1', port: closed), isNull);
      expect(await measureTcpPing('does-not-exist.invalid'), isNull);
    });

    testWidgets('Network tab renders', (t) async {
      await pumpApp(t);
      await goTab(t, 'Network');
      expect(find.text('Test ping to game regions'), findsOneWidget);
      expect(find.textContaining('Honest note'), findsOneWidget);
    });
  });
}
