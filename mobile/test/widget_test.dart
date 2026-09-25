import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:arenaboost/main.dart';

/// Fake Android native layer: records every call so we can verify the boost flow.
final calls = <String>[];
Map<String, dynamic> fakeDev({double temp = 35, bool powerSave = false, String net = 'Wi-Fi'}) => {
      'model': 'Test Phone', 'android': 'Android 14 (API 34)', 'cpu': 'qcom', 'cores': 8,
      'batteryTemp': temp, 'battery': 80, 'charging': false, 'thermal': 'Normal',
      'powerSave': powerSave, 'network': net, 'refresh': 120,
      'storageFree': 20 * 1073741824, 'storageTotal': 128 * 1073741824,
    };
var dev = fakeDev();
bool dndGranted = true;

void installFakeNative() {
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(native, (c) async {
    calls.add(c.method);
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
        expect((c.arguments as Map)['keep'], isA<List>());
        return {'killed': 12, 'freed': 450 * 1048576};
      case 'setDnd':
        return dndGranted;
      case 'launch':
        return true;
    }
    return true;
  });
}

Future<void> pumpApp(WidgetTester t) async {
  await t.binding.setSurfaceSize(const Size(420, 2400));
  await t.pumpWidget(const ArenaBoostApp());
  await t.pump();
  await t.pump(const Duration(milliseconds: 100));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    calls.clear();
    dev = fakeDev();
    dndGranted = true;
    SharedPreferences.setMockInitialValues({});
    isAndroidPlatform = () => true;
    installFakeNative();
  });

  group('Games tab (Android)', () {
    testWidgets('detects games and hides non-games', (t) async {
      await pumpApp(t);
      expect(find.text('PUBG MOBILE'), findsOneWidget);
      expect(find.text('Free Fire'), findsOneWidget);
      expect(find.text('WhatsApp'), findsNothing);
      expect(find.text('My games (2)'), findsOneWidget);
      expect(calls, containsAll(['getApps', 'memInfo', 'deviceInfo']));
    });

    testWidgets('"Show all apps" + star adds a game and saves it', (t) async {
      await pumpApp(t);
      await t.tap(find.text('Show all apps'));
      await t.pump();
      expect(find.text('WhatsApp'), findsOneWidget);
      await t.tap(find.byIcon(Icons.star_border).first);
      await t.pump();
      await t.tap(find.text('Games only'));
      await t.pump();
      expect(find.text('WhatsApp'), findsOneWidget);
      final sp = await SharedPreferences.getInstance();
      expect(sp.getStringList('myGames'), contains('com.whatsapp'));
    });

    testWidgets('Boost & Launch runs full flow in correct order', (t) async {
      await pumpApp(t);
      calls.clear();
      await t.tap(find.text('PUBG MOBILE'));
      await t.pump();
      await t.pump(const Duration(seconds: 1));
      expect(calls, containsAllInOrder(['deviceInfo', 'boost', 'setDnd', 'launch']));
      expect(find.textContaining('Cleared background of 12 apps'), findsOneWidget);
      expect(find.textContaining('freed ~450 MB'), findsOneWidget);
      expect(find.textContaining('Do Not Disturb ON'), findsOneWidget);
      expect(find.textContaining('Launched PUBG MOBILE'), findsOneWidget);
    });

    testWidgets('Warnings: hot phone, battery saver, mobile data', (t) async {
      dev = fakeDev(temp: 45, powerSave: true, net: 'Mobile data');
      await pumpApp(t);
      await t.tap(find.text('Free Fire'));
      await t.pump();
      await t.pump(const Duration(seconds: 1));
      expect(find.textContaining('Phone is hot'), findsOneWidget);
      expect(find.textContaining('Battery Saver is ON'), findsOneWidget);
      expect(find.textContaining('mobile data'), findsOneWidget);
    });

    testWidgets('DND without permission is skipped gracefully', (t) async {
      dndGranted = false;
      await pumpApp(t);
      await t.tap(find.text('Free Fire'));
      await t.pump();
      await t.pump(const Duration(seconds: 1));
      expect(find.textContaining('DND skipped'), findsOneWidget);
      expect(calls, contains('launch'));
    });

    testWidgets('Returning from game restores DND', (t) async {
      await pumpApp(t);
      await t.tap(find.text('PUBG MOBILE'));
      await t.pump();
      await t.pump(const Duration(seconds: 1));
      calls.clear();
      t.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      t.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await t.pump();
      expect(calls, contains('setDnd'));
      expect(find.textContaining('Do Not Disturb restored'), findsOneWidget);
    });
  });

  group('Monitor tab', () {
    testWidgets('shows RAM, temp, battery, storage and cleans', (t) async {
      await pumpApp(t);
      await t.tap(find.text('Monitor'));
      await t.pump();
      expect(find.text('63%'), findsOneWidget); // 5/8 GB used
      expect(find.text('35.0°C'), findsOneWidget);
      expect(find.text('80%'), findsOneWidget);
      expect(find.text('20.0 GB'), findsOneWidget);
      expect(find.textContaining('120 Hz'), findsOneWidget);
      calls.clear();
      await t.tap(find.text('Clean background apps now'));
      await t.pump();
      expect(calls, contains('boost'));
      expect(find.text('Freed ~450 MB'), findsOneWidget);
    });
  });

  group('Tools tab', () {
    testWidgets('buttons open correct system screens', (t) async {
      await pumpApp(t);
      await t.tap(find.text('Tools'));
      await t.pump();
      for (final entry in {
        'Allow Do Not Disturb control': 'requestDndAccess',
        'Battery optimization': 'openBatteryOpt',
        'Developer options': 'openDevOptions',
      }.entries) {
        calls.clear();
        await t.tap(find.text(entry.key));
        await t.pump();
        expect(calls, [entry.value]);
      }
      expect(find.textContaining('Turn OFF Battery Saver'), findsOneWidget);
    });
  });

  group('iOS mode', () {
    testWidgets('shows iOS note, no native boost calls, iOS tips', (t) async {
      isAndroidPlatform = () => false;
      await pumpApp(t);
      for (int i = 0; i < 12; i++) {
        await t.pump(const Duration(seconds: 2)); // let each game-scheme check time out
      }
      expect(find.textContaining('iPhone note'), findsOneWidget);
      expect(calls.where((c) => c == 'boost' || c == 'getApps'), isEmpty);
      await t.tap(find.text('Monitor'));
      await t.pump();
      expect(find.textContaining('iOS does not expose'), findsOneWidget);
      await t.tap(find.text('Tools'));
      await t.pump();
      expect(find.textContaining('Low Power Mode'), findsOneWidget);
      expect(find.text('Battery optimization'), findsNothing);
    });
  });

  group('Network', () {
    test('pingStats: average, jitter, loss', () {
      final r = pingStats([10, 20, null, 30, null])!;
      expect(r[0], 20);
      expect(r[1], 10);
      expect(r[2], 40);
      expect(pingStats([null, null]), isNull);
      expect(pingStats([50])!, [50, 0, 0]);
    });

    test('measureTcpPing: real local TCP server & closed port', () async {
      final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((s) => s.destroy());
      final ms = await measureTcpPing('127.0.0.1', port: server.port);
      expect(ms, isNotNull);
      expect(ms!, lessThan(500));
      final closedPort = server.port;
      await server.close();
      expect(await measureTcpPing('127.0.0.1', port: closedPort), isNull);
      expect(await measureTcpPing('does-not-exist.invalid'), isNull);
    });

    testWidgets('Network tab renders test button & honest note', (t) async {
      await pumpApp(t);
      await t.tap(find.text('Network'));
      await t.pump();
      expect(find.text('Test ping to game regions'), findsOneWidget);
      expect(find.textContaining('Honest note'), findsOneWidget);
    });
  });
}
