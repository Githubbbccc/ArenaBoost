// REAL-DEVICE test: runs on an actual Android phone/emulator. Nothing is mocked:
// real package manager, real RAM, real battery, real DND, real rotation lock, real app launch.
// Run:  flutter test integration_test   (with a phone/emulator connected)
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:arenaboost/main.dart' as app;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  const native = app.native;

  // CI grants DND + "modify system settings" via adb in the background; wait for it
  // so the SUCCESS paths are tested for real (falls back to graceful checks otherwise).
  setUpAll(() async {
    for (int i = 0; i < 30; i++) {
      final dnd = await native.invokeMethod<bool>('hasDndAccess');
      final ws = await native.invokeMethod<bool>('canWriteSettings');
      if (dnd == true && ws == true) break;
      await Future.delayed(const Duration(seconds: 1));
    }
  });

  group('Real Android native functions', () {
    testWidgets('list installed apps (with icons)', (t) async {
      final apps = await native.invokeListMethod<Map>('getApps');
      debugPrint('REAL: ${apps!.length} launchable apps: ${apps.take(8).map((a) => a['name']).join(', ')}');
      expect(apps, isNotEmpty);
      expect(apps.first.keys, containsAll(['pkg', 'name', 'isGame', 'icon']));
      expect(apps.any((a) => a['icon'] != null), isTrue);
      expect(apps.any((a) => a['pkg'] == 'com.arena.arenaboost'), isFalse, reason: 'must not list itself');
    });

    testWidgets('real memory info', (t) async {
      final m = (await native.invokeMapMethod('memInfo'))!;
      debugPrint('REAL: RAM total=${m['total'] ~/ 1048576} MB avail=${m['avail'] ~/ 1048576} MB');
      expect(m['total'], greaterThan(256 * 1048576));
      expect(m['avail'], inInclusiveRange(1, m['total']));
    });

    testWidgets('real device / battery / thermal / network info', (t) async {
      final d = (await native.invokeMapMethod('deviceInfo'))!;
      debugPrint('REAL: $d');
      expect(d['model'], isNotEmpty);
      expect(d['cores'], greaterThan(0));
      expect(d['battery'], inInclusiveRange(0, 100));
      expect(d['batteryTemp'], inInclusiveRange(0, 80));
      expect(d['refresh'], greaterThan(0));
      expect(['Wi-Fi', 'Mobile data', 'Ethernet', 'Other', 'Offline'], contains(d['network']));
      expect(d['storageTotal'], greaterThan(d['storageFree']));
    });

    testWidgets('real background clean', (t) async {
      final r = (await native.invokeMapMethod('boost', {'keep': <String>[]}))!;
      debugPrint('REAL: boost killed=${r['killed']} freed=${r['freed'] ~/ 1048576} MB');
      expect(r['killed'], greaterThanOrEqualTo(0));
      expect(r['freed'], greaterThanOrEqualTo(0));
    });

    testWidgets('real Do Not Disturb on/off (or graceful without permission)', (t) async {
      final granted = await native.invokeMethod<bool>('hasDndAccess');
      final on = await native.invokeMethod<bool>('setDnd', {'on': true});
      final off = await native.invokeMethod<bool>('setDnd', {'on': false});
      debugPrint('REAL: DND permission=$granted on=$on off=$off');
      expect(on, granted);
      expect(off, granted);
    });

    testWidgets('real rotation lock (or graceful without permission)', (t) async {
      final can = await native.invokeMethod<bool>('canWriteSettings');
      final l = await native.invokeMethod<bool>('lockRotation', {'mode': 'landscape'});
      final p = await native.invokeMethod<bool>('lockRotation', {'mode': 'portrait'});
      final off = await native.invokeMethod<bool>('lockRotation', {'mode': 'off'});
      debugPrint('REAL: write-settings=$can landscape=$l portrait=$p restore=$off');
      expect([l, p, off], everyElement(can));
    });

    testWidgets('real game bar overlay (or graceful without permission)', (t) async {
      final granted = await native.invokeMethod<bool>('canDrawOverlays');
      final on = await native.invokeMethod<bool>('setGameBar', {'on': true, 'title': 'Test Game'});
      final upd = await native.invokeMethod<bool>('gameBarUpdate',
          {'text': '⚡ Test Game · CPU 10% · RAM 20% · 30°C · 00:01'});
      final off = await native.invokeMethod<bool>('setGameBar', {'on': false});
      debugPrint('REAL: overlay granted=$granted on=$on update=$upd off=$off');
      expect(on, granted);
      expect(upd, on == true);
      expect(off, isA<bool>(), reason: 'off never errors, with or without permission');
    });

    testWidgets('Game Mode API query does not crash', (t) async {
      final g = await native.invokeMethod<String>('gameMode', {'pkg': 'com.arena.arenaboost'});
      debugPrint('REAL: game mode = $g');
      expect(g, isNotEmpty);
    });

    testWidgets('launch unknown package returns false, not crash', (t) async {
      expect(await native.invokeMethod<bool>('launch', {'pkg': 'does.not.exist.app'}), isFalse);
    });
  });

  group('Real UI on device', () {
    testWidgets('app starts, loads real apps & stats, every tab renders', (t) async {
      await app.main();
      await t.pump(const Duration(seconds: 3));
      await t.pump(const Duration(seconds: 3));
      expect(find.text('Created by Ghost'), findsOneWidget);
      expect(find.text('BOOST'), findsOneWidget);
      expect(find.textContaining('RAM '), findsOneWidget);
      for (final tab in ['Games', 'Network', 'Monitor', 'Settings', 'Boost']) {
        await t.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text(tab)));
        await t.pump(const Duration(milliseconds: 600));
        expect(t.takeException(), isNull, reason: 'tab $tab threw');
      }
      // real clean via the orb -> user must SEE a result
      await t.tap(find.byKey(const Key('boostOrb')));
      await t.pump(const Duration(seconds: 2));
      expect(find.textContaining('Boost done!'), findsOneWidget);
    });

    testWidgets('real ping from device', (t) async {
      final ms = await app.measureTcpPing('dns.google');
      debugPrint('REAL: ping dns.google = $ms ms');
      expect(ms == null || ms > 0, isTrue);
      if (Platform.isAndroid) expect(ms, isNotNull, reason: 'emulator should have internet');
    });

    testWidgets('real Boost & Launch of another app (Settings)', (t) async {
      final ok = await native.invokeMethod<bool>('launch', {'pkg': 'com.android.settings'});
      expect(ok, isTrue);
      await t.pump(const Duration(seconds: 2));
    });
  });
}
