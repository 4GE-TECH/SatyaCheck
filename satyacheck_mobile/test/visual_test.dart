// Renders the main screens with real fonts at phone size so the design can be reviewed as PNGs.
// Run: flutter test test/visual_test.dart --update-goldens   (writes test/goldens/*.png)
// Fixtures below are labelled samples mirroring contracts.py's mock scenarios, not real calls.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:satyacheck/api_client.dart';
import 'package:satyacheck/main.dart';
import 'package:satyacheck/models.dart';
import 'package:satyacheck/result_screen.dart';
import 'package:satyacheck/enroll_screen.dart';
import 'package:satyacheck/theme.dart';

Map<String, dynamic> redFixture() => {
      'session_id': 'session_mock_red',
      'quality': {'passed': true, 'speech_duration_s': 12.0, 'snr_db': 18.5, 'min_speech_threshold_s': 1.5, 'min_snr_threshold_db': 5.0},
      'speaker': {'verdict': 'match', 'matched_person_name': 'Rahul (Son)'},
      'spoof': {
        'median_score': 0.86,
        'peak_score': 0.98,
        'max_synth_run_s': 6.5,
        'is_synthetic': true,
        'timeline': [
          {'start_s': 0.0, 'end_s': 3.0, 'score': 0.78, 'is_synthetic': true},
          {'start_s': 2.0, 'end_s': 5.0, 'score': 0.94, 'is_synthetic': true},
          {'start_s': 4.0, 'end_s': 7.0, 'score': 0.98, 'is_synthetic': true},
          {'start_s': 6.0, 'end_s': 9.0, 'score': 0.91, 'is_synthetic': true},
        ],
      },
      'transcript': {
        'text': 'Papa emergency ho gaya hai, police ne pakad liya hai! Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe!',
        'detected_language': 'hi',
        'segments': [
          {'start_s': 0.0, 'end_s': 4.5, 'text': 'Papa emergency ho gaya hai, police ne pakad liya hai!'},
          {'start_s': 4.5, 'end_s': 10.0, 'text': 'Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe!'},
        ],
      },
      'script': {
        'risk': 0.94,
        'intent_summary': 'High-severity emergency extortion & isolation demand',
        'incriminating_markers': [
          {'matched_text': 'Phone kisi ko mat dena', 'description': 'Caller demands isolation and forbids consulting family'},
          {'matched_text': 'turant 50000 bhejo is UPI ID pe', 'description': 'Demands an immediate irreversible UPI transfer'},
        ],
        'exculpatory_markers': [],
        'playbooks': [
          {'title': 'Digital Arrest & Fake Police Extortion Advisory', 'source_agency': 'Indian Cyber Crime Coordination Centre (I4C), MHA', 'similarity_score': 0.91, 'source_url': 'https://cybercrime.gov.in/Webform/Crime_Advisory.aspx'},
        ],
      },
      'fusion': {
        'trust_score': 12.0,
        'band': 'high_risk',
        'mode': 'identity_check',
        'weights_used': {'asv_weight': 0.4, 'cm_weight': 0.35, 'text_weight': 0.25},
        'identity_risk': 0.15,
        'authenticity_risk': 0.92,
        'authenticity_risk_effective': 0.92,
        'intent_risk': 0.94,
        'reason_codes': [
          {'code': 'RC_SYNTH', 'signal': 'authenticity', 'value': 'Peak Synth 98% (Run 6.5s)', 'explanation': 'Deepfake speech synthesis signatures detected.', 'citation_title': 'Deepfake Voice Fraud Advisory', 'citation_url': 'https://cybercrime.gov.in/Webform/Crime_Advisory.aspx', 'severity': 'critical'},
          {'code': 'RC_ISOLATION', 'signal': 'intent', 'value': 'Isolation Marker + Urgent UPI', 'explanation': 'Demands strict secrecy and urgent payment. Classical extortion playbook.', 'severity': 'critical'},
        ],
        'recommended_actions': ['DO NOT transfer money via UPI.', 'Disconnect the call immediately.', 'Call Rahul back directly on their known saved phone number.'],
        'challenge_question': {'question_text': "Ask the caller: 'What is the name of our hometown dog?'"},
        'vernacular_warning': 'सावधान! यह कॉल एक क्लोन की हुई नकली आवाज़ हो सकती है। कोई भी पैसा ट्रांसफर न करें।',
      },
      'processing_time_ms': 18,
    };

class OfflineApi extends ApiClient {
  @override
  Future<bool> ping() async => false;
}

Future<void> loadFonts() async {
  Future<void> family(String name, List<String> assets) async {
    final loader = FontLoader(name);
    for (final a in assets) {
      loader.addFont(rootBundle.load(a));
    }
    await loader.load();
  }

  await family('Geist', ['assets/fonts/Geist-Regular.ttf', 'assets/fonts/Geist-Medium.ttf', 'assets/fonts/Geist-SemiBold.ttf', 'assets/fonts/Geist-Bold.ttf']);
  await family('GeistMono', ['assets/fonts/GeistMono-Regular.ttf', 'assets/fonts/GeistMono-Medium.ttf']);
  await family('MaterialIcons', ['fonts/MaterialIcons-Regular.otf']);
}

Future<void> frame(WidgetTester tester, Widget child, String name, {double height = 844}) async {
  tester.view.physicalSize = Size(1170, height * 3);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(child);
  await tester.runAsync(() async {
    final element = tester.element(find.byType(MaterialApp).first);
    await precacheImage(const AssetImage('assets/brand/satyacheck-logo.jpg'), element);
  });
  for (var i = 0; i < 30; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
  await expectLater(find.byType(MaterialApp).first, matchesGoldenFile('goldens/$name.png'));
  await tester.pumpWidget(const SizedBox());
  await tester.pump(const Duration(seconds: 2));
}

MaterialApp app(Widget home, Brightness b) => MaterialApp(debugShowCheckedModeBanner: false, theme: satyaTheme(b), home: home);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(loadFonts);
  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('com.satyacheck/native'), (call) async => call.method == 'getPermissionStatus' ? <String, dynamic>{} : null);
  });

  for (final b in Brightness.values) {
    final tag = b == Brightness.dark ? 'dark' : 'light';
    testWidgets('home $tag', (tester) async {
      await frame(tester, MaterialApp(debugShowCheckedModeBanner: false, theme: satyaTheme(b), home: HomePage(api: OfflineApi(), themeMode: ThemeMode.system, onTheme: (_) {})), 'home-$tag');
    });
    testWidgets('result $tag', (tester) async {
      await frame(tester, app(ResultScreen(result: ScreeningResult.fromJson(redFixture()), label: 'Example · Synthetic voice'), b), 'result-$tag');
    });
  }
  testWidgets('result full dark', (tester) async {
    await frame(tester, app(ResultScreen(result: ScreeningResult.fromJson(redFixture()), label: 'Example · Synthetic voice'), Brightness.dark), 'result-full-dark', height: 3300);
  });
  testWidgets('enroll dark', (tester) async {
    await frame(tester, app(EnrollScreen(api: OfflineApi()), Brightness.dark), 'enroll-dark');
  });
}
