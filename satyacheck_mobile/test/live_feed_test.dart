import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:satyacheck/api_client.dart';
import 'package:satyacheck/calls_screen.dart';
import 'package:satyacheck/models.dart';

Map<String, dynamic> verdict([Map<String, dynamic> over = const {}]) => {
      'type': 'verdict',
      'schema_version': 1,
      'session_id': 'MZcall01',
      'window_index': 0,
      'is_final': false,
      'escalated': false,
      'band': 'high_risk',
      'overlay_state': 'red',
      'trust_score': 12.0,
      'mode': 'authority_check',
      'signals': {'identity': 'unknown', 'authenticity': 'synthetic', 'intent_risk': 0.94},
      'reason_codes': [
        {'code': 'RC_INFO', 'signal': 'identity', 'explanation': 'Caller is not enrolled.', 'severity': 'info'},
        {'code': 'RC_SYNTH', 'signal': 'authenticity', 'explanation': 'Synthetic speech detected.', 'severity': 'critical'},
      ],
      'transcript': 'turant 50000 bhejo',
      'caller_context': {'claimed_number': '+919876543210', 'channel_type': 'telephony'},
      'threat_label': {'sector': 'law_enforcement_impersonation', 'threat': 'Digital arrest', 'family': 'digital_arrest'},
      'recommended_actions': ['DO NOT transfer money.'],
      'window_trust_score': 40.0,
      ...over,
    };

// Plain `test`s only: a `testWidgets` in this file would switch on the test binding, whose
// HttpClient answers every request with 400 and would break the real local servers below.

/// A one-route WebSocket server standing in for `/api/ws/live`.
Future<HttpServer> feedServer(void Function(WebSocket ws, HttpRequest request) onSocket) async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  server.listen((request) async {
    if (request.uri.path != '/api/ws/live') {
      request.response.statusCode = 404;
      await request.response.close();
      return;
    }
    onSocket(await WebSocketTransformer.upgrade(request), request);
  });
  return server;
}

Future<void> until(bool Function() done) async {
  for (var i = 0; i < 100 && !done(); i++) {
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
}

void main() {
  test('live verdicts parse, keep evidence in severity order, and never show green for a stranger', () {
    final v = LiveVerdict.fromJson(verdict())!;
    expect(v.callerId, '+919876543210');
    expect(v.threatLabel!.threat, 'Digital arrest');
    expect(v.threatLabel!.sectorText, 'law enforcement impersonation');
    expect(v.overlay, Signal.red);
    expect(v.evidence.map((r) => r.code), ['RC_SYNTH']);

    expect(LiveVerdict.fromJson(verdict({'overlay_state': 'green', 'band': 'verified'}))!.overlay, Signal.grey);
    expect(LiveVerdict.fromJson(verdict({'overlay_state': 'green', 'band': 'verified', 'mode': 'identity_check'}))!.overlay, Signal.green);
    expect(LiveVerdict.fromJson({'type': 'hello', 'schema_version': 1}), isNull);
    expect(LiveVerdict.fromJson(verdict({'trust_score': 'high'})), isNull);
  });

  test('a call keeps its final verdict even if a late window arrives', () {
    final call = LiveCall(LiveVerdict.fromJson(verdict({'escalated': true}))!);
    call.add(LiveVerdict.fromJson(verdict({'is_final': true, 'window_index': 5}))!);
    call.add(LiveVerdict.fromJson(verdict({'window_index': 4}))!);
    expect(call.ended, isTrue);
    expect(call.latest.windowIndex, 5);
    expect(call.escalations, 1);
  });

  test('screening results carry the threat label and caller ID', () {
    final result = ScreeningResult.fromJson({
      'session_id': 's',
      'quality': {'passed': true},
      'speaker': {'verdict': 'unknown'},
      'fusion': {
        'mode': 'authority_check',
        'band': 'high_risk',
        'trust_score': 12,
        'threat_label': {'sector': 'banking', 'threat': 'KYC update fraud', 'family': 'kyc'},
      },
      'caller_context': {'claimed_number': '+911234', 'channel_type': 'telephony'},
    });
    expect(result.threatLabel!.threat, 'KYC update fraud');
    expect(result.callerId, '+911234');
    expect(result.channel, 'telephony');
  });

  test('enrollment sends consent with the recording', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    String body = '';
    server.listen((request) async {
      body = await utf8.decoder.bind(request).join();
      request.response.statusCode = 201;
      request.response.write(jsonEncode({'person_id': 'p1', 'name': 'Asha', 'voiceprints': [{'voiceprint_id': 'v'}]}));
      await request.response.close();
    });
    final dir = await Directory.systemTemp.createTemp('sc_enroll');
    final wav = File('${dir.path}/a.wav')..writeAsBytesSync([82, 73, 70, 70]);
    try {
      final api = ApiClient(baseUrl: 'http://127.0.0.1:${server.port}');
      final outcome = await api.enroll(wavPath: wav.path, name: 'Asha', relation: 'Mother', consent: true);
      expect(outcome.ok, isTrue);
      expect(body, contains('name="consent"\r\n\r\ntrue'));
    } finally {
      await server.close(force: true);
      await dir.delete(recursive: true);
    }
  });

  test('the feed controller groups verdicts by call and asks for a token when refused', () async {
    final tokens = <String>[];
    WebSocket? open;
    final server = await feedServer((ws, request) {
      final token = request.uri.queryParameters['token'] ?? '';
      tokens.add(token);
      if (token != 'secret') {
        ws.close(1008, 'token');
        return;
      }
      open = ws;
      ws.add(jsonEncode({'type': 'hello', 'schema_version': 1}));
    });
    final feed = LiveFeedController(ApiClient(baseUrl: 'http://127.0.0.1:${server.port}'));
    try {
      unawaited(feed.connect());
      await until(() => feed.status == FeedStatus.refused);
      expect(feed.status, FeedStatus.refused);

      unawaited(feed.connect(token: 'secret'));
      await until(() => feed.status == FeedStatus.open && open != null);
      expect(feed.status, FeedStatus.open);
      expect(tokens.last, 'secret');

      open!.add(jsonEncode(verdict({'band': 'insufficient', 'overlay_state': 'grey'})));
      open!.add(jsonEncode(verdict({'window_index': 1, 'escalated': true})));
      open!.add(jsonEncode(verdict({'session_id': 'MZcall02', 'is_final': true})));
      await until(() => feed.calls.length == 2 && feed.calls.first.latest.windowIndex == 1);
      expect(feed.calls.map((c) => c.latest.sessionId), ['MZcall01', 'MZcall02']);
      expect(feed.calls.first.escalations, 1);
      expect(feed.calls.last.ended, isTrue);

      feed.clearEnded();
      expect(feed.calls.map((c) => c.latest.sessionId), ['MZcall01']);
    } finally {
      await feed.disconnect();
      feed.dispose();
      await server.close(force: true);
    }
  });

}
