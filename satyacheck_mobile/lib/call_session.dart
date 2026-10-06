import 'dart:async';
import 'dart:io';
import 'dart:math' show min;
import 'dart:typed_data';

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
  CallPhase _phase = CallPhase.idle;
  String? _detail;

  // --- live feed (Exotel calls) ---
  //
  // During a phone call this phone cannot record the call: Android gives the dialer the
  // microphone (CLAUDE.md, "Call audio cannot be captured on the phone that is in the
  // call"). With Exotel, the call's audio goes straight to the backend instead, and the
  // backend publishes its verdicts on /api/ws/live. That feed is what screens a call here.
  LiveFeed? _live;
  StreamSubscription<LiveVerdict>? _liveVerdicts;
  StreamSubscription<bool>? _liveConnection;
  bool _inCall = false;
  String? _liveSessionId;
  LiveVerdict? _liveApplied;
  LiveVerdict? _lastLive;
  DateTime? _lastLiveAt;
  Completer<void>? _finalVerdict;
  bool _keepAlive = false;

  /// Every change worth redrawing for.
  Stream<CallSessionState> get states => _state.stream;

  LiveFeedState get liveFeedState => _live == null
      ? LiveFeedState.off
      : (_live!.connected ? LiveFeedState.connected : LiveFeedState.connecting);

  /// Follow the backend's live feed for calls on this phone. A null or empty token turns
  /// it off, which brings back the old behaviour: try the microphone during a call.
  Future<void> setLiveFeedToken(String? token) async {
    await _liveVerdicts?.cancel();
    await _liveConnection?.cancel();
    await _live?.stop();
    _live = null;
    if (token != null && token.isNotEmpty) {
      final live = LiveFeed(_api, token);
      _live = live;
      _liveVerdicts = live.verdicts.listen(_onLiveVerdict);
      _liveConnection = live.connection.listen((_) => _emit(_phase, detail: _detail));
      live.start();
    }
    // With the feed on, a call must not start the microphone service at all: it cannot
    // hear the call, and when it gives up it takes the receiver's call state with it, so
    // the hang-up never reaches here (see CallStateReceiver.setCallCapture).
    try {
      await _bridge.setCallCapture(_live == null);
    } catch (exc) {
      print('SC/Session: could not set call capture (${exc.runtimeType}): $exc');
    }
    // And during a call this app is in the background, where Android blocks its network;
    // a silent foreground service keeps the feed connected (LiveFeedService). Only on a
    // change: stopping it straight after a start would race its startForeground.
    final keepAlive = _live != null;
    if (keepAlive != _keepAlive) {
      _keepAlive = keepAlive;
      try {
        await _bridge.setKeepAlive(keepAlive);
      } catch (exc) {
        print('SC/Session: could not ${keepAlive ? 'start' : 'stop'} the keep-alive service: $exc');
      }
    }
    _emit(_phase, detail: _detail);
  }

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
    await _liveVerdicts?.cancel();
    await _liveConnection?.cancel();
    await _live?.stop();
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
  /// Not a mock. The clip goes up the same WebSocket live capture uses, in the same
  /// 3-second chunks at the same real-time pace, and is normalised by ffmpeg, embedded by
  /// ECAPA, transcribed by Whisper, retrieved against the corpus and fused exactly as live
  /// audio is; the verdict, the reason codes, the citations and the overlay's colour and
  /// quote all come back from the server. The single thing this skips is the microphone —
  /// and on a real call Android hands third-party apps digital silence anyway, so there is
  /// no version of this walkthrough where the phone's own mic hears the caller.
  ///
  /// If the socket cannot be opened, the whole clip goes to `POST /api/screen` instead —
  /// one verdict at the end rather than a running one, but still a verdict.
  Future<void> screenBundledClip(String assetPath, String label) async {
    _current = CallRecord(startedAt: DateTime.now(), number: label);
    _latest = null;
    _overlay = null;
    _chunksSent = 0;
    _emit(CallPhase.ringing);
    await _bridge.updateOverlay('Checking this call…');

    // A view of exactly the asset's bytes: `bytes.buffer` may be larger than the asset,
    // and the RIFF walk in [_pcm16Mono] reads from offset zero.
    final bytes = await rootBundle.load(assetPath);
    final wav = Uint8List.sublistView(bytes);

    // Open before playback starts, so the handshake over the tunnel does not hold up the
    // first chunk.
    final id = 'demo-${DateTime.now().millisecondsSinceEpoch}';
    final socket = await _api.openStream(id);
    if (socket == null) {
      print('SC/Session: demo socket $id FAILED to open; screening the clip in one POST');
    }

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

    if (socket != null) {
      socket.updates.listen(_onVerdict);
      socket.overlays.listen(_onOverlay);
      if (await _streamClip(socket, wav, startedAt)) {
        // The backend closes the socket once it has scored the final chunk. Wait for
        // that rather than guessing how long scoring takes over a tunnel.
        await socket.done.timeout(const Duration(seconds: 30), onTimeout: () {
          print('SC/Session: demo socket $id still open 30s after the final chunk');
        });
      }
      await socket.close();
    }

    if (_latest == null) {
      // No socket, or it returned nothing: screen the whole clip in one request.
      final result = await _api.screenWav(wav, filename: '$label.wav');

      // Hold the verdict until the caller has stopped speaking. Scoring takes about three
      // seconds and the clips run five to seventeen, so without this the card flips to
      // "likely scam" while the cloned voice is still mid-sentence — which reads as though
      // the app decided before it had heard anything.
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
    }

    await _finish();
  }

  /// Send a clip up [socket] the way live capture would: 3-second WAV chunks, each one
  /// sent once that much of the clip has played, the last marked final.
  ///
  /// Returns false, having sent nothing, if the clip is not 16-bit mono PCM.
  Future<bool> _streamClip(
      ScreeningSocket socket, Uint8List wav, DateTime startedAt) async {
    final clip = _pcm16Mono(wav);
    if (clip == null) {
      print('SC/Session: demo clip is not 16-bit mono PCM WAV; cannot stream it');
      return false;
    }

    final bytesPerSecond = clip.sampleRate * 2;
    final bytesPerChunk = bytesPerSecond * _chunkSeconds;
    final total = clip.pcm16.length;

    for (var start = 0, index = 0; start < total; start += bytesPerChunk, index++) {
      final end = min(start + bytesPerChunk, total);

      // Real-time pacing: a chunk goes up once its last sample has been heard, which is
      // when live capture would have it.
      final due = startedAt.add(Duration(milliseconds: end * 1000 ~/ bytesPerSecond));
      final wait = due.difference(DateTime.now());
      if (wait > Duration.zero) await Future<void>.delayed(wait);

      final chunk = AudioChunk(
        sessionId: socket.sessionId,
        index: index,
        sampleRate: clip.sampleRate,
        durationMs: (end - start) * 1000 ~/ bytesPerSecond,
        pcm16: Uint8List.sublistView(clip.pcm16, start, end),
      );
      final last = end == total;
      socket.send(chunk.toWav(), isFinal: last);
      _chunksSent++;
      print('SC/Session: demo chunk $index sent (${chunk.durationMs}ms'
          '${last ? ', final' : ''}, total $_chunksSent)');
      _emit(CallPhase.screening);
    }
    return true;
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
        _inCall = true;
        _liveSessionId = null;
        _liveApplied = null;
        _emit(CallPhase.ringing);
        // Grey, not green. Nothing has been screened yet, and green would be a claim.
        _bridge.updateOverlay('Checking this call…');
        // Exotel starts streaming when it answers the caller, before it rings this phone,
        // so the backend may already be scoring this call.
        final recent = _lastLive;
        final at = _lastLiveAt;
        if (_live != null &&
            recent != null &&
            !recent.isFinal &&
            at != null &&
            DateTime.now().difference(at) < const Duration(seconds: 60)) {
          _applyLive(recent);
        }
        break;

      case CallState.answered:
        _current ??= CallRecord(startedAt: DateTime.now());
        _inCall = true;
        if (_live != null) {
          // The live feed screens this call, so the receiver started no local capture
          // (setCallCapture) and there is no audio to open a /api/ws/screen session for.
          // Stopping the capture service from here instead raced its startForeground and
          // crashed the app (ForegroundServiceDidNotStartInTimeException).
          if (_latest == null) {
            _emit(CallPhase.screening, detail: 'Waiting for the backend’s verdict on this call');
            _bridge.updateOverlay('Checking this call…');
          }
          break;
        }
        _emit(CallPhase.screening);
        _bridge.updateOverlay('Checking this call…');
        // Native capture has already started by this point — the receiver starts the
        // service directly rather than waiting for a round trip through Dart.
        unawaited(_openSocket());
        break;

      case CallState.ended:
        unawaited(_endCall());
        break;

      case CallState.error:
        if (_inCall && _live != null) {
          // Expected: the dialer holds the microphone during a call. Not a failure to
          // screen — the live feed does that — so log it rather than show it.
          print('SC/Session: local capture unavailable during the call (${event.detail}); '
              'the live feed screens it');
          break;
        }
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

  void _onLiveVerdict(LiveVerdict verdict) {
    _lastLive = verdict;
    _lastLiveAt = DateTime.now();
    // Calls on other phones belong on the dashboard; this phone shows its own call only.
    if (!_inCall) return;
    final following = _liveSessionId;
    if (following != null && verdict.sessionId != following) {
      // The feed carries every call. One call at a time — the demo — means a newer call
      // is this one; a finished call that is not the one being followed is not.
      if (verdict.isFinal) return;
      print('SC/Live: now following ${verdict.sessionId} (was $following)');
    }
    _applyLive(verdict);
  }

  void _applyLive(LiveVerdict verdict) {
    // The screen is usually off during a call, so this line is how to tell afterwards
    // what the phone showed.
    print('SC/Live: ${verdict.sessionId} -> ${verdict.listening ? 'listening' : verdict.signal.name}'
        '${verdict.isFinal ? ' (final)' : ''}');
    final wasRed = _liveApplied?.signal == Signal.red;
    _liveSessionId = verdict.sessionId;
    _liveApplied = verdict;
    _latest = verdict.result;
    _current?.result = verdict.result;
    _emit(CallPhase.screening);
    _bridge.updateOverlay(_liveOverlayText(verdict), signal: _signalName(verdict.signal));

    // As for the app's own sessions: interrupt a live call only for red, and only once.
    if (verdict.signal == Signal.red && !wasRed) {
      _bridge.showVerdictNotification(
        signal: 'red',
        title: 'Likely scam call',
        body: _notificationBody(verdict.result),
      );
    }
    if (verdict.isFinal && !(_finalVerdict?.isCompleted ?? true)) _finalVerdict!.complete();
  }

  String _liveOverlayText(LiveVerdict verdict) {
    // docs/LIVE_FEED.md: `insufficient` is "listening", never a colour judgement.
    if (verdict.listening) return 'Listening…';
    final line = _stateLine(verdict.signal, null);
    final threat = verdict.threat;
    final warning = verdict.signal == Signal.amber || verdict.signal == Signal.red;
    return threat != null && warning ? '$line\nResembles $threat' : line;
  }

  /// The phone hung up. When the live feed is screening the call, wait briefly for the
  /// backend's final verdict, which lands when Exotel's stream ends and can trail the
  /// phone's own hang-up by a moment. It is the one to keep.
  Future<void> _endCall() async {
    final session = _liveSessionId;
    if (session != null && !(_liveApplied?.isFinal ?? false)) {
      final waiter = Completer<void>();
      _finalVerdict = waiter;
      await waiter.future.timeout(const Duration(seconds: 4), onTimeout: () {});
      _finalVerdict = null;
      if (!(_liveApplied?.isFinal ?? false)) {
        // Missed on the feed, which nothing replays. The backend stores every call's
        // final verdict, so ask for it rather than keep a mid-call one.
        final stored = await _api.storedVerdict(session);
        if (stored != null) {
          print('SC/Live: $session final verdict fetched from the backend');
          _liveApplied = LiveVerdict(
            sessionId: session,
            isFinal: true,
            signal: stored.signal,
            result: stored,
            threat: _liveApplied?.threat,
          );
          _latest = stored;
          _current?.result = stored;
        } else {
          print('SC/Live: no final verdict for $session; keeping the last one');
        }
      }
    }
    _inCall = false;
    final live = _liveApplied;
    await _finish();
    if (live != null) {
      // _finish draws from the app's own overlay state; a live verdict has its own text.
      _bridge.updateOverlay(_liveOverlayText(live), signal: _signalName(live.signal));
    }
    _liveSessionId = null;
    _liveApplied = null;
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
    _phase = phase;
    _detail = detail;
    if (_state.isClosed) return;
    _state.add(CallSessionState(
      phase: phase,
      result: _latest,
      chunksSent: _chunksSent,
      number: _current?.number,
      detail: detail,
      liveFeed: liveFeedState,
    ));
  }
}

/// Whether the backend's live feed is screening this phone's calls.
enum LiveFeedState { off, connecting, connected }

/// Seconds of audio per chunk. Matches `windowSeconds` in `CallAudioService.kt`; the
/// backend keeps its own trailing context window, so chunks carry no overlap.
const _chunkSeconds = 3;

/// The sample rate and PCM of a 16-bit mono WAV, or null for anything else.
///
/// Walks the RIFF chunks rather than assuming a 44-byte header: editors often write LIST
/// or fact chunks ahead of `data`.
({int sampleRate, Uint8List pcm16})? _pcm16Mono(Uint8List wav) {
  if (wav.length < 12) return null;
  final bytes = ByteData.sublistView(wav);
  String tag(int at) => String.fromCharCodes(wav, at, at + 4);
  if (tag(0) != 'RIFF' || tag(8) != 'WAVE') return null;

  int? sampleRate;
  var offset = 12;
  while (offset + 8 <= wav.length) {
    final id = tag(offset);
    final size = bytes.getUint32(offset + 4, Endian.little);
    final body = offset + 8;
    if (id == 'fmt ' && size >= 16 && body + 16 <= wav.length) {
      final format = bytes.getUint16(body, Endian.little);
      final channels = bytes.getUint16(body + 2, Endian.little);
      final bits = bytes.getUint16(body + 14, Endian.little);
      if (format != 1 || channels != 1 || bits != 16) return null;
      sampleRate = bytes.getUint32(body + 4, Endian.little);
    } else if (id == 'data') {
      if (sampleRate == null || sampleRate <= 0) return null;
      var end = min(body + size, wav.length);
      end -= (end - body) % 2; // whole samples only
      return (sampleRate: sampleRate, pcm16: Uint8List.sublistView(wav, body, end));
    }
    offset = body + size + size % 2; // chunks are word-aligned
  }
  return null;
}

enum CallPhase { idle, ringing, screening, done, failed }

class CallSessionState {
  const CallSessionState({
    required this.phase,
    this.result,
    this.chunksSent = 0,
    this.number,
    this.detail,
    this.liveFeed = LiveFeedState.off,
  });

  final CallPhase phase;
  final ScreeningResult? result;
  final int chunksSent;
  final String? number;
  final String? detail;
  final LiveFeedState liveFeed;

  Signal get signal => result?.signal ?? Signal.grey;
}
