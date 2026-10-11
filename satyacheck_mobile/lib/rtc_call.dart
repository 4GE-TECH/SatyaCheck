import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:livekit_client/livekit_client.dart';

import 'api_client.dart';
import 'models.dart';

/// App-to-app calls over WebRTC (webrtc/README.md).
///
/// Android gives other apps silence during a phone call, so for live testing the app *is*
/// the phone: two signed-in, connected people ring each other through a LiveKit room, and a
/// screening agent in that room hears each voice. Each person is sent the verdict about the voice
/// they hear, never about their own.
///
/// Every client rule in webrtc/BACKEND_API.md is applied here, not in the UI:
///   1. a verdict counts only on topic `satyacheck.verdict` from the `agent_identity`
///      the API returned ([VerdictGate]);
///   2. the highest `rev` wins ([VerdictGate]);
///   3. a reconnect keeps the banner as it was until the agent resends;
///   4. `screening_available: false` and the agent leaving are both shown;
///   5. the agent is never counted as a person in the call;
///   6. unresolved alerts stay visible ([RtcVerdict.openAlerts]);
///   7. unscreened time is reported ([RtcVerdict.partlyUnchecked]).

const verdictTopic = 'satyacheck.verdict';

/// One alert about the voice being heard. Withdrawn only by `resolved: true`.
class RtcAlert {
  const RtcAlert({required this.alertId, required this.band, required this.atS, required this.resolved, this.evidence});
  final String alertId;
  final TrustBand band;
  final double atS;
  final bool resolved;
  final String? evidence;

  factory RtcAlert.fromJson(Map<String, dynamic> json) => RtcAlert(
        alertId: json['alert_id'] as String? ?? '',
        band: TrustBand.parse(json['band'] as String?),
        atS: (json['at_s'] as num?)?.toDouble() ?? 0,
        resolved: json['resolved'] == true,
        evidence: json['evidence'] as String?,
      );
}

/// A reason code behind the score.
class RtcReason {
  const RtcReason(this.code, this.explanation);
  final String code, explanation;
}

/// The verdict message (webrtc/BACKEND_API.md, "The verdict message"), schema version 1.
class RtcVerdict {
  const RtcVerdict({
    required this.rev,
    required this.band,
    required this.trustScore,
    required this.screeningAvailable,
    this.reason,
    this.mode,
    this.reasons = const [],
    this.alerts = const [],
    this.screenedS = 0,
    this.unscreenedS = 0,
    this.degraded = false,
    this.transcriptTail = '',
    this.isFinal = false,
  });

  final int rev;
  final TrustBand band;

  /// Null when [band] is `insufficient`: no number is shown then.
  final double? trustScore;
  final bool screeningAvailable;
  final String? reason, mode;
  final List<RtcReason> reasons;
  final List<RtcAlert> alerts;
  final double screenedS, unscreenedS;
  final bool degraded;
  final String transcriptTail;
  final bool isFinal;

  /// Every alert not withdrawn. They never silently disappear (rule 6).
  List<RtcAlert> get openAlerts => [for (final a in alerts) if (!a.resolved) a];

  /// Part of the call could not be checked (rule 7).
  bool get partlyUnchecked => unscreenedS > 0 || degraded;

  /// Null for anything that is not a well-formed schema-1 verdict.
  static RtcVerdict? tryParse(List<int> data) {
    try {
      final json = jsonDecode(utf8.decode(data));
      if (json is! Map<String, dynamic> || json['type'] != verdictTopic || json['rev'] is! num) return null;
      final band = TrustBand.parse(json['display_band'] as String?);
      final coverage = json['coverage'] is Map ? (json['coverage'] as Map).cast<String, dynamic>() : const <String, dynamic>{};
      return RtcVerdict(
        rev: (json['rev'] as num).toInt(),
        band: band,
        trustScore: band == TrustBand.insufficient ? null : (json['trust_score'] as num?)?.toDouble(),
        screeningAvailable: json['screening_available'] != false,
        reason: json['reason'] as String?,
        mode: json['mode'] as String?,
        reasons: [
          for (final r in (json['reasons'] as List? ?? const []))
            if (r is Map) RtcReason(r['code'] as String? ?? '', r['explanation'] as String? ?? ''),
        ],
        alerts: [for (final a in (json['alerts'] as List? ?? const [])) if (a is Map) RtcAlert.fromJson(a.cast<String, dynamic>())],
        screenedS: (coverage['screened_s'] as num?)?.toDouble() ?? 0,
        unscreenedS: (coverage['unscreened_s'] as num?)?.toDouble() ?? 0,
        degraded: coverage['degraded'] == true,
        transcriptTail: json['transcript_tail'] as String? ?? '',
        isFinal: json['is_final'] == true,
      );
    } catch (error) {
      debugPrint('SatyaCheck call: unreadable verdict ignored ($error)');
      return null;
    }
  }
}

/// Rules 1 and 2: which data messages may change what the listener is shown.
class VerdictGate {
  VerdictGate(this.agentIdentity);

  /// The only sender whose verdicts count, as returned by the call API.
  final String agentIdentity;
  RtcVerdict? current;

  /// True when the message replaced [current].
  bool offer({required String? topic, required String? sender, required List<int> data}) {
    if (topic != verdictTopic || sender == null || sender != agentIdentity) {
      if (topic == verdictTopic) debugPrint('SatyaCheck call: verdict from "$sender" refused; only $agentIdentity may send one');
      return false;
    }
    final verdict = RtcVerdict.tryParse(data);
    if (verdict == null) return false;
    // Reliable messages can arrive after a newer heartbeat: an older rev never wins.
    if (current != null && verdict.rev < current!.rev) return false;
    current = verdict;
    return true;
  }
}

enum RtcPhase {
  /// No call yet.
  idle,

  /// Asking the service for the call, or entering the room.
  connecting,

  /// Calling out: in the room, their phone is ringing.
  ringing,

  /// Both people are in the call.
  inCall,

  /// The call is over. The last verdict stays readable.
  ended,
}

/// How a call ended, in words. Never blames anyone; a missed call is just missed.
String endedText(String? reason, String name, {required bool caller}) => switch (reason) {
      'declined' => caller ? '$name declined the call.' : 'You declined the call.',
      'missed' => caller ? '$name didn’t answer.' : 'You missed the call.',
      'cancelled' => caller ? 'You cancelled the call.' : '$name hung up before you answered.',
      _ => '$name ended the call.',
    };

/// One call, from ringing (or answering) to hanging up.
class RtcCallController extends ChangeNotifier {
  RtcCallController(this._api);

  final ApiClient _api;

  RtcPhase phase = RtcPhase.idle;
  RtcCallTicket? ticket;
  VerdictGate? _gate;

  /// Who is on the other end.
  RtcPerson? other;

  /// This phone placed the call.
  bool isCaller = false;

  /// Why a request failed, or why the call ended when it was not this phone hanging up.
  String? error, endedReason;

  /// The other person was in the call and is not right now: probably reconnecting.
  bool otherAway = false;

  /// This phone's connection is being restored. The banner stays as it was (rule 3).
  bool reconnecting = false;

  /// The screening agent left the room, or never arrived (rule 4).
  bool screeningLost = false;

  bool muted = false, speaker = false;

  Room? _room;
  EventsListener<RoomEvent>? _events;
  Timer? _poll, _agentGrace;
  bool _agentSeen = false, _otherSeen = false, _closing = false, _disposed = false;

  RtcVerdict? get verdict => _gate?.current;
  bool get busy => phase == RtcPhase.connecting;
  bool get live => phase == RtcPhase.connecting || phase == RtcPhase.ringing || phase == RtcPhase.inCall;
  String get otherName => other?.name ?? 'The other person';

  /// Ring a connection, and wait in the room for them to answer.
  Future<void> call(RtcPerson person) async {
    other = person;
    isCaller = true;
    await _enter(() => _api.placeCall(person.userId));
  }

  /// Answer a call that is ringing for you.
  Future<void> answer(IncomingCall incoming) async {
    other = incoming.caller;
    isCaller = false;
    await _enter(() => _api.acceptCall(incoming.callId));
  }

  Future<void> _enter(Future<RtcCallTicket?> Function() request) async {
    if (live) return;
    _reset();
    phase = RtcPhase.connecting;
    notifyListeners();

    final got = await request();
    if (_disposed) {
      // The screen closed while the call was being set up: do not leave it open on the server.
      if (got != null && got.valid) unawaited(_api.endRtcCall(got.callId));
      return;
    }
    if (got == null || !got.valid) {
      if (got != null) debugPrint('SatyaCheck call: incomplete call ticket');
      _fail(_api.rtcError ?? 'The call could not be set up. Please try again.');
      return;
    }
    ticket = got;
    other = got.other ?? other;
    _gate = VerdictGate(got.agentIdentity);

    final room = Room(roomOptions: const RoomOptions(adaptiveStream: false, dynacast: false));
    _room = room;
    _events = room.createListener()
      ..on<DataReceivedEvent>(_onData)
      ..on<ParticipantConnectedEvent>((e) => _onArrived(e.participant.identity))
      ..on<ParticipantDisconnectedEvent>((e) => _onLeft(e.participant.identity))
      ..on<RoomReconnectingEvent>((_) => _set(() => reconnecting = true))
      ..on<RoomReconnectedEvent>((_) => _set(() => reconnecting = false))
      ..on<RoomDisconnectedEvent>((e) {
        if (!_closing) _finish('The connection to the call was lost (${e.reason?.name ?? 'unknown reason'}).', endOnServer: false);
      });

    try {
      await room.connect(got.livekitUrl, got.token);
    } catch (e) {
      debugPrint('SatyaCheck call: could not enter the room at ${got.livekitUrl}: $e');
      unawaited(_api.endRtcCall(got.callId));
      _fail('Could not connect to the call server at ${got.livekitUrl}. Check that this phone can reach it.');
      return;
    }
    if (_disposed) {
      await _close(endOnServer: true);
      return;
    }
    try {
      await room.localParticipant?.setMicrophoneEnabled(true);
      await AudioManager.instance.setSpeakerOutputPreferred(speaker);
    } catch (e) {
      debugPrint('SatyaCheck call: microphone unavailable: $e');
      await _close(endOnServer: true);
      _fail('SatyaCheck needs the microphone for calls. Allow it in Settings, then try again.');
      return;
    }

    for (final identity in room.remoteParticipants.keys) {
      _onArrived(identity, notify: false);
    }
    // The person answering is joining a room the caller is already in.
    phase = _otherSeen || !isCaller ? RtcPhase.inCall : RtcPhase.ringing;
    // The agent starts with the call; give it a moment to enter the room before saying
    // screening is unavailable.
    _agentGrace = Timer(const Duration(seconds: 20), () {
      if (!_agentSeen && phase == RtcPhase.inCall) {
        debugPrint('SatyaCheck call: the screening agent did not join within 20 s');
        _set(() => screeningLost = true);
      }
    });
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _checkState());
    notifyListeners();
  }

  void _onData(DataReceivedEvent e) {
    final gate = _gate;
    if (gate == null) return;
    if (gate.offer(topic: e.topic, sender: e.participant?.identity, data: e.data)) notifyListeners();
  }

  void _onArrived(String identity, {bool notify = true}) {
    if (identity == ticket?.agentIdentity) {
      // Rule 5: the agent is screening, not a person in the call.
      _agentSeen = true;
      screeningLost = false;
    } else {
      _otherSeen = true;
      otherAway = false;
      if (phase == RtcPhase.ringing) phase = RtcPhase.inCall;
    }
    if (notify) notifyListeners();
  }

  void _onLeft(String identity) {
    if (identity == ticket?.agentIdentity) {
      // While it still rings, the agent leaving is the call being declined or missed;
      // the state poll says which.
      if (phase == RtcPhase.inCall) {
        debugPrint('SatyaCheck call: the screening agent left the room');
        _set(() => screeningLost = true);
      }
    } else {
      // Often a network change on their side; the call API says whether it really ended.
      _set(() => otherAway = true);
    }
    unawaited(_checkState());
  }

  Future<void> _checkState() async {
    final id = ticket?.callId;
    if (id == null || _closing) return;
    final state = await _api.rtcCallState(id);
    if (state == null || _closing || ticket?.callId != id) return;
    if (state.ended) {
      _finish(endedText(state.endedReason, otherName, caller: isCaller), endOnServer: false);
    } else if (state.answered && phase == RtcPhase.ringing && _otherSeen) {
      _set(() => phase = RtcPhase.inCall);
    }
  }

  Future<void> toggleMute() async {
    final local = _room?.localParticipant;
    if (local == null) return;
    try {
      await local.setMicrophoneEnabled(muted);
      _set(() => muted = !muted);
    } catch (e) {
      debugPrint('SatyaCheck call: could not ${muted ? 'unmute' : 'mute'}: $e');
    }
  }

  Future<void> toggleSpeaker() async {
    try {
      await AudioManager.instance.setSpeakerOutputPreferred(!speaker);
      _set(() => speaker = !speaker);
    } catch (e) {
      debugPrint('SatyaCheck call: could not switch the speaker: $e');
    }
  }

  /// Cancel a ringing call, or hang up, for both people.
  Future<void> hangUp() async {
    if (!live) return;
    final wasRinging = phase == RtcPhase.ringing;
    await _close(endOnServer: true);
    endedReason = wasRinging ? 'You cancelled the call.' : null;
    phase = RtcPhase.ended;
    if (!_disposed) notifyListeners();
  }

  void _finish(String reason, {required bool endOnServer}) {
    if (_closing || phase == RtcPhase.ended) return;
    endedReason = reason;
    unawaited(_close(endOnServer: endOnServer).then((_) {
      phase = RtcPhase.ended;
      if (!_disposed) notifyListeners();
    }));
  }

  void _fail(String message) {
    if (_disposed) return;
    error = message;
    phase = RtcPhase.ended;
    notifyListeners();
  }

  Future<void> _close({required bool endOnServer}) async {
    _closing = true;
    _poll?.cancel();
    _agentGrace?.cancel();
    final id = ticket?.callId;
    if (endOnServer && id != null) {
      // Best effort and bounded: hanging up never waits on the network.
      unawaited(_api.endRtcCall(id).timeout(const Duration(seconds: 5), onTimeout: () {}));
    }
    final room = _room, events = _events;
    _room = null;
    _events = null;
    await events?.dispose();
    try {
      await room?.disconnect();
    } catch (e) {
      debugPrint('SatyaCheck call: disconnect failed: $e');
    }
    await room?.dispose();
  }

  void _reset() {
    ticket = null;
    _gate = null;
    error = endedReason = null;
    otherAway = reconnecting = screeningLost = muted = false;
    _agentSeen = _otherSeen = _closing = false;
  }

  void _set(void Function() change) {
    if (_disposed) return;
    change();
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    if (live) unawaited(_close(endOnServer: true));
    super.dispose();
  }
}

/// Asks the service every two seconds, while the app is open, whether a call is ringing
/// for you. The app shows the incoming-call screen for each new one.
class IncomingCallWatcher {
  IncomingCallWatcher(this._api, {required this.onRing, this.interval = const Duration(seconds: 2)});

  final ApiClient _api;

  /// A call started ringing. Called once per call.
  final void Function(IncomingCall call) onRing;
  final Duration interval;

  /// Calls ringing right now, as of the last answer.
  List<IncomingCall> ringing = const [];

  /// This service offers app calls (false after a 404; asked again every minute).
  bool available = true;

  final _seen = <String>{};
  final _listeners = <VoidCallback>[];
  Timer? _timer;
  bool _asking = false;
  DateTime _nextProbe = DateTime.fromMillisecondsSinceEpoch(0);

  void addListener(VoidCallback listener) => _listeners.add(listener);
  void removeListener(VoidCallback listener) => _listeners.remove(listener);

  /// Is this call still ringing? False once it was answered elsewhere, cancelled or missed.
  bool stillRinging(String callId) => ringing.any((c) => c.callId == callId);

  void start() {
    _timer ??= Timer.periodic(interval, (_) => check());
    unawaited(check());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> check() async {
    if (_asking || (!available && DateTime.now().isBefore(_nextProbe))) return;
    _asking = true;
    try {
      final result = await _api.incomingCalls();
      if (result == null) return;   // offline for a moment: keep the last picture
      available = result.available;
      if (!available) _nextProbe = DateTime.now().add(const Duration(minutes: 1));
      ringing = result.calls;
      for (final call in result.calls) {
        if (_seen.add(call.callId)) onRing(call);
      }
      for (final listener in List.of(_listeners)) {
        listener();
      }
    } finally {
      _asking = false;
    }
  }
}
