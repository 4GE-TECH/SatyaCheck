import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;

import 'api_client.dart';
import 'models.dart';
import 'native_bridge.dart';

/// Orchestrates one screened call: native audio in, verdict out.
///
/// The whole product flow lives here:
///
///     call arrives      → overlay "Checking…"
///     user answers      → speakerphone forced, capture starts
///     audio accumulates → 3s windows stream to the backend
///     verdict returns   → overlay + notification turn green / amber / red
///     call ends         → final flush, result stored in history
///
/// Why the app tolerates a missing backend at every step: this runs while someone is on a
/// phone call. A screening app that interferes with answering the phone is worse than no
/// screening app, so every failure path here ends in "no verdict" rather than an exception.
class CallSession {
  CallSession({ApiClient? api, NativeBridge? bridge})
      : _api = api ?? ApiClient(),
        _bridge = bridge ?? NativeBridge.instance;

  final ApiClient _api;
  final NativeBridge _bridge;

  final _state = StreamController<CallSessionState>.broadcast();
  final _history = <CallRecord>[];

  StreamSubscription<CallEvent>? _calls;
  StreamSubscription<AudioChunk>? _audio;

  ScreeningSocket? _socket;
  CallRecord? _current;
  ScreeningResult? _latest;
  OverlayUpdate? _overlay;
  int _chunksSent = 0;
  bool _started = false;

  /// Every change worth redrawing for.
  Stream<CallSessionState> get states => _state.stream;

  List<CallRecord> get history => List.unmodifiable(_history);

  ScreeningResult? get latest => _latest;

  /// Begin listening for calls. Idempotent.
  void start() {
    if (_started) return;
    _started = true;
    _bridge.listen();
    _calls = _bridge.callEvents.listen(_onCallEvent);
    _audio = _bridge.audioChunks.listen(_onAudioChunk);
  }

  Future<void> dispose() async {
    await _calls?.cancel();
    await _audio?.cancel();
    await _socket?.close();
    await _state.close();
  }

  // --- manual capture --------------------------------------------------------

  /// Screen audio now, without waiting for the phone to ring.
  ///
  /// Drives the identical path a real call takes — the same foreground service, forced
  /// speakerphone, 3-second chunks and backend socket. Only the telephony trigger is
  /// absent. That makes it both the way to verify capture works on a new handset and the
  /// fallback when a live call misbehaves mid-demo.
  Future<void> startManualCapture() async {
    _current = CallRecord(startedAt: DateTime.now(), number: 'Manual test');
    _latest = null;
    _overlay = null;
    _chunksSent = 0;
    _emit(CallPhase.screening);
    await _bridge.updateOverlay('Listening…');
    await _openSocket();
    await _bridge.startCapture();
  }

  /// Screen a bundled clip as though it had arrived as a call.
  ///
  /// Not a mock. The bytes go to `POST /api/screen`, are normalised by ffmpeg, embedded by
  /// ECAPA, transcribed by Whisper, retrieved against the corpus and fused exactly as live
  /// audio is; the verdict, the reason codes and the citations all come back from the
  /// server. The single thing this skips is the microphone — and on a real call Android
  /// hands third-party apps digital silence anyway, so there is no version of this
  /// walkthrough where the phone's own mic hears the caller.
  ///
  /// It drives the same overlay and the same verdict card a live call drives, because it
  /// goes through the same [CallRecord] and [_emit] path.
  Future<void> screenBundledClip(String assetPath, String label) async {
    _current = CallRecord(startedAt: DateTime.now(), number: label);
    _latest = null;
    _chunksSent = 0;
    _emit(CallPhase.ringing);
    await _bridge.updateOverlay('Checking this call…');

    final bytes = await rootBundle.load(assetPath);
    final wav = bytes.buffer.asUint8List();

    // Play it aloud while it is scored. The audio and the verdict arrive together, which is
    // the whole point: a red card is a claim, a cloned voice asking for money over a red
    // card is evidence. An asset lives inside the APK and MediaPlayer cannot open it from
    // there, so it is spilled to cache first.
    final startedAt = DateTime.now();
    var clipMs = 0;
    try {
      final file = File('${(await Directory.systemTemp.createTemp()).path}/$label.wav');
      await file.writeAsBytes(wav);
      clipMs = await _bridge.playClip(file.path);
    } catch (_) {
      // Playback is a presentation nicety; never let it stop the screening.
    }

    _emit(CallPhase.screening);

    final result = await _api.screenWav(wav, filename: '$label.wav');

    // Hold the verdict until the caller has stopped speaking.
    //
    // Scoring takes about three seconds and the clips run five to eleven, so without this
    // the card flips to "likely scam" while the cloned voice is still mid-sentence — which
    // reads as though the app decided before it had heard anything. Waiting also matches
    // what actually happens on a call: the evidence accumulates, then the verdict lands.
    final remaining = clipMs - DateTime.now().difference(startedAt).inMilliseconds;
    if (remaining > 0) {
      await Future<void>.delayed(Duration(milliseconds: remaining));
    }

    if (result == null) {
      _current?.error = 'The backend did not return a verdict';
      _emit(CallPhase.failed, detail: 'Could not reach the screening server');
      await _bridge.updateOverlay('Could not screen this call');
      return;
    }

    _latest = result;
    _current?.result = result;
    await _finish();
  }

  Future<void> stopManualCapture() async {
    await _bridge.stopCapture();
    await _finish();
  }

  // --- call lifecycle --------------------------------------------------------

  void _onCallEvent(CallEvent event) {
    switch (event.state) {
      case CallState.ringing:
        _current = CallRecord(startedAt: DateTime.now(), number: event.number);
        _latest = null;
        _overlay = null;
        _chunksSent = 0;
        _emit(CallPhase.ringing);
        // Grey, not green. Nothing has been screened yet, and green would be a claim.
        _bridge.updateOverlay('Checking this call…');
        break;

      case CallState.answered:
        _current ??= CallRecord(startedAt: DateTime.now());
        _emit(CallPhase.screening);
        _bridge.updateOverlay('Checking this call…');
        // Native capture has already started by this point — the receiver starts the
        // service directly rather than waiting for a round trip through Dart.
        unawaited(_openSocket());
        break;

      case CallState.ended:
        unawaited(_finish());
        break;

      case CallState.error:
        _current?.error = event.detail;
        _emit(CallPhase.failed, detail: event.detail);
        _bridge.updateOverlay('Could not screen this call');
        break;

      case CallState.permissionsChanged:
        _emit(_current == null ? CallPhase.idle : CallPhase.screening);
        break;
    }
  }

  Future<void> _openSocket() async {
    final id = 'call-${DateTime.now().millisecondsSinceEpoch}';
    print('SC/Session: opening socket $id -> ${_api.baseUrl}');
    final socket = await _api.openStream(id);
    if (socket == null) {
      print('SC/Session: socket $id FAILED to open');
      // No live socket. Capture continues regardless: the whole call is screened in one
      // POST when it ends, so the user still gets a verdict — just later.
      _emit(CallPhase.screening, detail: 'offline — will score when the call ends');
      return;
    }
    _socket = socket;
    print('SC/Session: socket $id open');
    socket.updates.listen(_onVerdict);
    socket.overlays.listen(_onOverlay);
  }

  void _onAudioChunk(AudioChunk chunk) {
    final socket = _socket;
    if (socket == null) {
      // Dropping a window here used to be invisible, which made "the app captured audio
      // but the backend scored nothing" impossible to tell apart from "no audio was
      // captured". Say so.
      print('SC/Session: chunk ${chunk.index} DROPPED: no socket');
      return;
    }
    socket.send(chunk.toWav());
    _chunksSent++;
    print('SC/Session: chunk ${chunk.index} sent (${chunk.durationMs}ms, total $_chunksSent)');
    _emit(CallPhase.screening);
  }

  void _onVerdict(ScreeningResult result) {
    _latest = result;
    _current?.result = result;
    _emit(CallPhase.screening);
    // The overlay_update for this chunk follows immediately and draws the overlay with its
    // quote. Drawing here as well is only for a backend that never sends one.
    if (_overlay == null) _renderOverlay();

    // Notify mid-call only when it is red. That is the one verdict worth interrupting a
    // live conversation for, and it is the moment the warning can still change what the
    // person does. Everything else waits for the call to end.
    if (result.signal == Signal.red) {
      _bridge.showVerdictNotification(
        signal: 'red',
        title: 'Likely scam call',
        body: _notificationBody(result),
      );
    }
  }

  void _onOverlay(OverlayUpdate update) {
    _overlay = update;
    _renderOverlay();
  }

  Future<void> _finish() async {
    final socket = _socket;
    _socket = null;

    if (socket != null) {
      // Give the backend a moment to score the tail before tearing the socket down —
      // the end of a call is often where the payment demand lands.
      await Future<void>.delayed(const Duration(seconds: 2));
      await socket.close();
    }

    final record = _current;
    _current = null;

    if (record != null) {
      record.result = _latest;
      _history.insert(0, record);
    }

    final result = _latest;
    if (result != null) {
      _renderOverlay();
      // Leave the verdict on screen briefly — the user has just hung up and this is the
      // moment they decide whether to call back.
      Future<void>.delayed(const Duration(seconds: 8), _bridge.hideOverlay);

      await _bridge.showVerdictNotification(
        signal: _signalName(result.signal),
        title: _notificationTitle(result),
        body: _notificationBody(result),
      );
    } else {
      await _bridge.hideOverlay();
    }

    _emit(CallPhase.done);
  }

  // --- presentation ----------------------------------------------------------

  /// Draw the overlay: a state line, then the evidence in quotes when there is some.
  ///
  /// Colour comes from the latest `overlay_update`, or from the full verdict if none has
  /// arrived. Nothing is drawn before either, so "Checking this call…" stays up.
  void _renderOverlay() {
    final result = _latest;
    final signal = _overlay?.signal ?? result?.signal;
    if (signal == null) return;

    final line = _stateLine(signal, result?.matchedPersonName);
    final quote = _quotable(_overlay?.evidence, signal, result);
    _bridge.updateOverlay(
      quote == null ? line : '$line\n“$quote”',
      signal: _signalName(signal),
    );
  }

  /// The evidence phrase, if it should be put in quotation marks under [signal].
  ///
  /// Amber and red only: under grey or green a quoted phrase reads as an accusation the
  /// score does not make. And only words the caller actually said — when no marker fires,
  /// the backend's `evidence` falls back to the top playbook's excerpt, which is corpus
  /// text, and quoting it would put someone else's words in the caller's mouth. Marker
  /// text is an exact slice of the transcript, so the transcript is the test.
  String? _quotable(String? evidence, Signal signal, ScreeningResult? result) {
    if (evidence == null) return null;
    if (signal != Signal.amber && signal != Signal.red) return null;
    final transcript = result?.transcript.toLowerCase() ?? '';
    if (!transcript.contains(evidence.toLowerCase())) {
      print('SC/Session: evidence is not in the transcript, not quoting it: "$evidence"');
      return null;
    }
    return evidence;
  }

  String _stateLine(Signal signal, String? who) {
    switch (signal) {
      case Signal.green:
        return who == null ? 'Verified caller' : 'Verified: $who';
      case Signal.amber:
        return 'Caution — verify before acting';
      case Signal.red:
        return 'Likely scam — do not send money';
      case Signal.grey:
        // Authority check: an unknown caller is not an accusation. Most calls from a
        // stranger are legitimate, and saying otherwise trains people to ignore the app.
        return 'Unverified caller';
    }
  }

  String _signalName(Signal signal) {
    switch (signal) {
      case Signal.green:
        return 'green';
      case Signal.amber:
        return 'amber';
      case Signal.red:
        return 'red';
      case Signal.grey:
        return 'grey';
    }
  }

  String _notificationTitle(ScreeningResult result) {
    switch (result.signal) {
      case Signal.green:
        final who = result.matchedPersonName;
        return who == null ? 'Verified caller' : 'Verified: $who';
      case Signal.amber:
        return 'Check before you act';
      case Signal.red:
        return 'Likely scam call';
      case Signal.grey:
        return 'Call not verified';
    }
  }

  /// The evidence, in words someone frightened can act on.
  ///
  /// Prefers the backend's vernacular warning — it is already in the caller's language and
  /// written for this band. Falls back to the strongest reason code, which carries the
  /// citation. Never a bare score: "trust 21" tells a worried relative nothing.
  String _notificationBody(ScreeningResult result) {
    final warning = result.vernacularWarning;
    if (warning != null && warning.trim().isNotEmpty) return warning;

    final evidence = result.evidence;
    if (evidence.isNotEmpty) return evidence.first.explanation;

    if (result.recommendedActions.isNotEmpty) {
      return result.recommendedActions.first;
    }
    return 'Screened on ${result.mode == 'identity_check' ? 'voice and content' : 'content'}.';
  }

  void _emit(CallPhase phase, {String? detail}) {
    if (_state.isClosed) return;
    _state.add(CallSessionState(
      phase: phase,
      result: _latest,
      chunksSent: _chunksSent,
      number: _current?.number,
      detail: detail,
    ));
  }
}

enum CallPhase { idle, ringing, screening, done, failed }

class CallSessionState {
  const CallSessionState({
    required this.phase,
    this.result,
    this.chunksSent = 0,
    this.number,
    this.detail,
  });

  final CallPhase phase;
  final ScreeningResult? result;
  final int chunksSent;
  final String? number;
  final String? detail;

  Signal get signal => result?.signal ?? Signal.grey;
}
