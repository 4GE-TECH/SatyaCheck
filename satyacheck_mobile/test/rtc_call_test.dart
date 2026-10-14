import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:satyacheck/api_client.dart';
import 'package:satyacheck/people_screen.dart';
import 'package:satyacheck/auth.dart';
import 'package:satyacheck/models.dart';
import 'package:satyacheck/rtc_call.dart';
import 'package:satyacheck/theme.dart';

const agent = 'satyacheck-agent-e7919c122f171720';

/// A packet as server/live_presenter.py `compact()` builds it.
List<int> packet({int rev = 1, String band = 'suspicious', double? score = 41.0, bool available = true,
    List<Map<String, dynamic>> alerts = const [], Map<String, dynamic>? coverage, String type = 'satyacheck.verdict'}) {
  return utf8.encode(jsonEncode({
    'type': type,
    'schema_version': 1,
    'rev': rev,
    'session_id': 'rtc_e7919c122f171720_caller',
    'screening_available': available,
    'reason': available ? null : 'the screening service is restarting',
    'display_band': band,
    'trust_score': score,
    'mode': 'authority_check',
    'reasons': [
      {'code': 'RC_RISK_MARKERS_PRESENT', 'explanation': 'Asks for money to be sent immediately.'}
    ],
    'alerts': alerts,
    'coverage': coverage ?? {'screened_s': 48.0, 'unscreened_s': 0.0, 'degraded': false},
    'transcript_tail': 'Papa ko mat batana',
    'transcript_rev': 5,
    'is_final': false,
  }));
}

void main() {
  group('rejoining a call after the connection drops', rejoinTests);
  group('VerdictGate', () {
    test('accepts a verdict from the agent on the verdict topic', () {
      final gate = VerdictGate(agent);
      expect(gate.offer(topic: verdictTopic, sender: agent, data: packet()), isTrue);
      expect(gate.current!.band, TrustBand.suspicious);
      expect(gate.current!.trustScore, 41.0);
      expect(gate.current!.reasons.single.code, 'RC_RISK_MARKERS_PRESENT');
    });

    test('refuses a verdict from anyone but the agent (rule 1)', () {
      final gate = VerdictGate(agent);
      expect(gate.offer(topic: verdictTopic, sender: 'the-other-phone', data: packet(band: 'verified')), isFalse);
      expect(gate.offer(topic: verdictTopic, sender: null, data: packet(band: 'verified')), isFalse);
      expect(gate.current, isNull);
    });

    test('ignores other topics and malformed payloads', () {
      final gate = VerdictGate(agent);
      expect(gate.offer(topic: 'chat', sender: agent, data: packet()), isFalse);
      expect(gate.offer(topic: verdictTopic, sender: agent, data: utf8.encode('not json')), isFalse);
      expect(gate.offer(topic: verdictTopic, sender: agent, data: packet(type: 'something.else')), isFalse);
      expect(gate.current, isNull);
    });

    test('keeps the highest rev (rule 2)', () {
      final gate = VerdictGate(agent);
      gate.offer(topic: verdictTopic, sender: agent, data: packet(rev: 7, band: 'high_risk'));
      expect(gate.offer(topic: verdictTopic, sender: agent, data: packet(rev: 5, band: 'unverified')), isFalse);
      expect(gate.current!.band, TrustBand.highRisk);
      expect(gate.offer(topic: verdictTopic, sender: agent, data: packet(rev: 8, band: 'high_risk')), isTrue);
      expect(gate.current!.rev, 8);
    });
  });

  group('RtcVerdict', () {
    test('insufficient carries no score, even if one is sent', () {
      final v = RtcVerdict.tryParse(packet(band: 'insufficient', score: 50))!;
      expect(v.band, TrustBand.insufficient);
      expect(v.trustScore, isNull);
    });

    test('keeps unresolved alerts and drops resolved ones from the open list (rule 6)', () {
      final v = RtcVerdict.tryParse(packet(alerts: [
        {'alert_id': 'a1', 'band': 'high_risk', 'at_s': 22.5, 'resolved': false, 'evidence': 'Asks you not to tell anyone.'},
        {'alert_id': 'a2', 'band': 'caution', 'at_s': 30.0, 'resolved': true, 'evidence': null},
      ]))!;
      expect(v.alerts, hasLength(2));
      expect(v.openAlerts.single.alertId, 'a1');
      expect(v.openAlerts.single.band, TrustBand.highRisk);
    });

    test('reports unscreened time and degraded coverage (rule 7)', () {
      expect(RtcVerdict.tryParse(packet())!.partlyUnchecked, isFalse);
      expect(RtcVerdict.tryParse(packet(coverage: {'screened_s': 10.0, 'unscreened_s': 4.0, 'degraded': false}))!.partlyUnchecked, isTrue);
      expect(RtcVerdict.tryParse(packet(coverage: {'screened_s': 10.0, 'unscreened_s': 0.0, 'degraded': true}))!.partlyUnchecked, isTrue);
    });

    test('reads screening paused (rule 4)', () {
      final v = RtcVerdict.tryParse(packet(available: false))!;
      expect(v.screeningAvailable, isFalse);
      expect(v.reason, isNotNull);
    });

    test('a packet before any assessment parses as listening', () {
      final data = utf8.encode(jsonEncode({
        'type': 'satyacheck.verdict', 'schema_version': 1, 'rev': 0, 'session_id': 's', 'screening_available': true,
        'reason': null, 'alerts': [], 'display_band': 'insufficient', 'trust_score': null, 'mode': null, 'reasons': [],
        'coverage': null, 'transcript_tail': '', 'transcript_rev': -1, 'is_final': false,
      }));
      final v = RtcVerdict.tryParse(data)!;
      expect(v.band, TrustBand.insufficient);
      expect(v.partlyUnchecked, isFalse);
    });
  });

  test('RtcCallTicket reads place and accept responses, with who is on the other end', () {
    final placed = RtcCallTicket.fromJson({
      'call_id': 'e7919c122f171720', 'livekit_url': 'ws://192.168.1.20:7880', 'token': 'jwt', 'agent_identity': agent,
      'other': {'user_id': 'bob', 'username': 'bob', 'display_name': 'Bob'}, 'ring_timeout_s': 45,
    });
    expect(placed.valid, isTrue);
    expect(placed.other!.name, 'Bob');
    expect(placed.ringTimeoutS, 45);
    expect(RtcCallTicket.fromJson({'call_id': 'x'}).valid, isFalse);
  });

  test('people, connections and call state parse from the API', () {
    final c = RtcConnections.fromJson({
      'connected': [{'user_id': 'b', 'username': 'bob', 'display_name': 'Bob', 'relation': 'connected'}],
      'incoming': [{'user_id': 'c', 'username': 'carol', 'display_name': '', 'relation': 'incoming'}],
      'outgoing': [],
    });
    expect(c.connected.single.connected, isTrue);
    expect(c.incoming.single.name, '@carol');
    final state = RtcCallState.fromJson({'status': 'ended', 'ended_reason': 'declined', 'screening': false});
    expect((state.ended, state.answered, state.endedReason), (true, false, 'declined'));
    final ringing = IncomingCalls.fromJson({'calls': [{'call_id': 'k1', 'caller': {'user_id': 'a', 'username': 'alice', 'display_name': 'Alice'}, 'rings_for_s': 40}]});
    expect(ringing.calls.single.caller.name, 'Alice');
    expect(ringing.calls.single.caller.connected, isTrue);
  });

  test('how a call ended is said plainly, from each side', () {
    expect(endedText('declined', 'Bob', caller: true), 'Bob declined the call.');
    expect(endedText('missed', 'Bob', caller: true), 'Bob didn’t answer.');
    expect(endedText('missed', 'Alice', caller: false), 'You missed the call.');
    expect(endedText('cancelled', 'Alice', caller: false), 'Alice hung up before you answered.');
    expect(endedText('hung_up', 'Bob', caller: true), 'Bob ended the call.');
    // Ended by the service, not by a person: never says someone hung up.
    expect(endedText('dropped', 'Bob', caller: true), 'The call dropped: one phone lost its connection.');
    expect(endedText('timed_out', 'Bob', caller: false), 'The call reached its time limit and was ended.');
  });

  group('IncomingCallWatcher', () {
    test('rings once per call and notices when it stops ringing', () async {
      final api = _ScriptedApi([
        IncomingCalls([_incoming('k1')]),
        IncomingCalls([_incoming('k1')]),
        const IncomingCalls([]),
      ]);
      final rung = <String>[];
      final watcher = IncomingCallWatcher(api, onRing: (c) => rung.add(c.callId));
      await watcher.check();
      await watcher.check();
      expect(rung, ['k1']);
      expect(watcher.stillRinging('k1'), isTrue);
      await watcher.check();
      expect(watcher.stillRinging('k1'), isFalse);
    });

    test('keeps the last picture while offline, and backs off when calls are not offered', () async {
      final api = _ScriptedApi([IncomingCalls([_incoming('k1')]), null, const IncomingCalls.unavailable(), IncomingCalls([_incoming('k2')])]);
      final watcher = IncomingCallWatcher(api, onRing: (_) {});
      await watcher.check();
      await watcher.check();
      expect(watcher.stillRinging('k1'), isTrue);
      await watcher.check();
      expect(watcher.available, isFalse);
      await watcher.check();                       // within the back-off: not asked
      expect(api.asked, 3);
    });
  });

  testWidgets('without sign-in, People explains why calls are unavailable', (tester) async {
    final api = ApiClient(baseUrl: 'http://127.0.0.1:9', auth: AuthSession(url: '', anonKey: ''));
    await tester.pumpWidget(MaterialApp(theme: satyaTheme(Brightness.light), home: PeopleScreen(api: api)));
    await tester.pump();
    expect(find.textContaining('App calls need sign-in'), findsOneWidget);
  });

  group('MediaHealth', () {
    final t0 = DateTime(2026, 10, 14, 12);
    DateTime at(int s) => t0.add(Duration(seconds: s));

    test('nothing is flagged before the call starts, or while each wait is still running', () {
      final m = MediaHealth();
      expect(m.evaluate(at(60), agentPresent: true, muted: false), isEmpty);
      m
        ..onInCall(at(0))
        ..onOtherJoined(at(0));
      expect(m.evaluate(at(9), agentPresent: true, muted: false), isEmpty);
      expect(m.anyProblem, isFalse);
    });

    test('a call that carries nothing says so: the failing call from the field', () {
      final m = MediaHealth()
        ..onInCall(at(0))
        ..onOtherJoined(at(0));
      expect(m.evaluate(at(10), agentPresent: true, muted: false), ['notHearingThem']);
      expect(m.evaluate(at(15), agentPresent: true, muted: false), ['notHeardByServer', 'noVerdicts']);
      expect((m.notHeardByServer, m.notHearingThem, m.noVerdicts), (true, true, true));
    });

    test('each flag clears as soon as its evidence arrives', () {
      final m = MediaHealth()
        ..onInCall(at(0))
        ..onOtherJoined(at(0));
      m.evaluate(at(20), agentPresent: true, muted: false);
      m
        ..onLocalSpeaking()
        ..onRemoteAudio()
        ..onVerdict();
      expect(m.evaluate(at(21), agentPresent: true, muted: false).toSet(), {'notHeardByServer', 'notHearingThem', 'noVerdicts'});
      expect(m.anyProblem, isFalse);
    });

    test('a healthy call is never flagged', () {
      final m = MediaHealth()
        ..onInCall(at(0))
        ..onOtherJoined(at(1))
        ..onRemoteAudio()
        ..onVerdict()
        ..onLocalSpeaking();
      expect(m.evaluate(at(120), agentPresent: true, muted: false), isEmpty);
    });

    test('muted is not "not heard", and unmuting restarts the wait', () {
      final m = MediaHealth()..onInCall(at(0));
      m.evaluate(at(40), agentPresent: false, muted: true);
      expect(m.notHeardByServer, isFalse);
      m.onUnmuted(at(40));
      m.evaluate(at(50), agentPresent: false, muted: false);
      expect(m.notHeardByServer, isFalse);
      m.evaluate(at(55), agentPresent: false, muted: false);
      expect(m.notHeardByServer, isTrue);
    });

    test('missing verdicts count only while the agent is in the call, and a failed subscription shows at once', () {
      final m = MediaHealth()..onInCall(at(0));
      m.evaluate(at(30), agentPresent: false, muted: false);
      expect(m.noVerdicts, isFalse);
      m.onSubscriptionFailed();
      m.evaluate(at(31), agentPresent: false, muted: false);
      expect(m.notHearingThem, isTrue);
    });

    test('reset forgets everything, as after re-entering the call', () {
      final m = MediaHealth()
        ..onInCall(at(0))
        ..onOtherJoined(at(0));
      m.evaluate(at(30), agentPresent: true, muted: false);
      m.reset();
      expect(m.anyProblem, isFalse);
      expect(m.inCallAt, isNull);
    });
  });
}

IncomingCall _incoming(String id) =>
    IncomingCall(callId: id, caller: const RtcPerson(userId: 'a', username: 'alice', displayName: 'Alice', relation: 'connected'), ringsForS: 40);

class _ScriptedApi extends ApiClient {
  _ScriptedApi(this.replies) : super(baseUrl: 'http://127.0.0.1:9', auth: AuthSession(url: '', anonKey: ''));
  final List<IncomingCalls?> replies;
  int asked = 0;

  @override
  Future<IncomingCalls?> incomingCalls() async => replies[asked++];
}

/// Answers rejoin and state requests from scripts, for [obtainRejoinTicket].
class _RejoinApi extends ApiClient {
  _RejoinApi({required this.tickets, this.ended = false})
      : super(baseUrl: 'http://127.0.0.1:9', auth: AuthSession(url: '', anonKey: ''));
  final List<RtcCallTicket?> tickets;
  final bool ended;
  int asked = 0;

  @override
  Future<RtcCallTicket?> rejoinCall(String callId) async => asked < tickets.length ? tickets[asked++] : null;

  @override
  Future<RtcCallState?> rtcCallState(String callId) async =>
      RtcCallState.fromJson({'status': ended ? 'ended' : 'active', 'ended_reason': ended ? 'dropped' : null, 'screening': true});
}

void rejoinTests() {
  final fresh = RtcCallTicket.fromJson({
    'call_id': 'c1', 'livekit_url': 'ws://lk', 'token': 'new-token', 'agent_identity': 'satyacheck-agent-c1'});
  final soon = DateTime.now().add(const Duration(seconds: 2));

  test('a dropped phone keeps asking until the service gives it a fresh ticket', () async {
    final api = _RejoinApi(tickets: [null, null, fresh]);
    final got = await obtainRejoinTicket(api, 'c1', until: soon, every: const Duration(milliseconds: 10));
    expect(got?.token, 'new-token');
    expect(api.asked, 3);
  });

  test('it stops at once when the call has ended, instead of retrying', () async {
    final api = _RejoinApi(tickets: [null, null, fresh], ended: true);
    expect(await obtainRejoinTicket(api, 'c1', until: soon, every: const Duration(milliseconds: 10)), isNull);
    expect(api.asked, 1);
  });

  test('it gives up at the deadline', () async {
    final api = _RejoinApi(tickets: List.filled(1000, null));
    final until = DateTime.now().add(const Duration(milliseconds: 80));
    expect(await obtainRejoinTicket(api, 'c1', until: until, every: const Duration(milliseconds: 10)), isNull);
    expect(DateTime.now().isBefore(until.add(const Duration(milliseconds: 200))), isTrue);
  });
}
