import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:satyacheck/main.dart';
import 'package:satyacheck/api_client.dart';
import 'package:satyacheck/models.dart';
import 'package:satyacheck/result_screen.dart';
import 'package:satyacheck/theme.dart';

Map<String, dynamic> fixture(
        {String mode = 'identity_check',
        String verdict = 'match',
        bool passed = true}) =>
    {
      'session_id': 'test',
      'quality': {'passed': passed},
      'speaker': {'verdict': verdict},
      'fusion': {
        'mode': mode,
        'band': 'verified',
        'trust_score': 90,
        'reason_codes': [],
        'recommended_actions': []
      },
    };

class OfflineApi extends ApiClient {
  @override
  Future<bool> ping() async => false;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('unknown identity and authority mode stay neutral', () {
    expect(ScreeningResult.fromJson(fixture(mode: 'authority_check')).band,
        TrustBand.unverified);
    expect(ScreeningResult.fromJson(fixture(verdict: 'unknown')).signal,
        Signal.grey);
    expect(ScreeningResult.fromJson(fixture()).band, TrustBand.verified);
    expect(ScreeningResult.fromJson(fixture(passed: false)).band,
        TrustBand.insufficient);
  });
  testWidgets('insufficient result hides numeric score and supports large text',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(
        theme: satyaTheme(Brightness.light),
        home: MediaQuery(
          data: const MediaQueryData(textScaler: TextScaler.linear(1.6)),
          child: ResultScreen(
              result: ScreeningResult.fromJson(fixture(passed: false))),
        )));
    for (var i = 0; i < 25; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.text('90/100'), findsNothing);
    expect(find.text('No score given.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('offline home remains usable and navigation works',
      (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
            const MethodChannel('com.satyacheck/native'),
            (call) async => call.method == 'getPermissionStatus'
                ? <String, dynamic>{}
                : null);
    await tester.pumpWidget(SatyaCheckApp(api: OfflineApi()));
    // The ambient field animates indefinitely by design, so pump fixed frames rather than settle.
    for (var i = 0; i < 25; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.text('Choose audio'), findsOneWidget);
    await tester.tap(find.text('Recent').last);
    for (var i = 0; i < 25; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.text('Choose audio'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
