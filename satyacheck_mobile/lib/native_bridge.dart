import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/services.dart';

/// Everything that crosses the Dart↔Kotlin boundary, in one place.
///
/// `CLAUDE.md` for this folder: MethodChannel only. Dart never touches an Android API and
/// Kotlin never makes an HTTP call — audio comes up here, and the Dart side is what talks to
/// the backend.
class NativeBridge {
  NativeBridge._();
  static final NativeBridge instance = NativeBridge._();

  static const MethodChannel _channel = MethodChannel('com.satyacheck/native');

  final _callEvents = StreamController<CallEvent>.broadcast();
  final _audioChunks = StreamController<AudioChunk>.broadcast();
  final _levels = StreamController<RecordLevel>.broadcast();

  /// RINGING / ANSWERED / ENDED, as they happen.
  Stream<CallEvent> get callEvents => _callEvents.stream;

  /// One event per captured audio window during a call.
  Stream<AudioChunk> get audioChunks => _audioChunks.stream;

  /// Live microphone level while enrollment is recording.
  Stream<RecordLevel> get recordLevels => _levels.stream;

  bool _listening = false;

  /// Begin receiving native callbacks. Safe to call more than once.
  void listen() {
    if (_listening) return;
    _listening = true;
    _channel.setMethodCallHandler(_onNativeCall);
  }

  Future<dynamic> _onNativeCall(MethodCall call) async {
    switch (call.method) {
      case 'onCallRinging':
        _callEvents.add(CallEvent(
          CallState.ringing,
          number: (call.arguments as Map?)?['number'] as String?,
        ));
        break;
      case 'onCallAnswered':
        _callEvents.add(const CallEvent(CallState.answered));
        break;
      case 'onCallEnded':
        _callEvents.add(const CallEvent(CallState.ended));
        break;
      case 'onAudioChunk':
        try {
          final chunk = AudioChunk.fromMap(
            Map<String, dynamic>.from(call.arguments as Map),
          );
          print('SC/Bridge: chunk ${chunk.index} arrived '
              '(${chunk.pcm16.length} bytes, listeners=${_audioChunks.hasListener})');
          _audioChunks.add(chunk);
        } catch (e, st) {
          // A decode failure here used to vanish: the MethodChannel handler swallowed it
          // and the window simply never reached the session.
          print('SC/Bridge: chunk decode FAILED: $e / $st');
        }
        break;
      case 'onCaptureError':
        _callEvents.add(CallEvent(
          CallState.error,
          detail: (call.arguments as Map?)?['reason'] as String?,
        ));
        break;
      case 'onRecordLevel':
        final args = Map<String, dynamic>.from(call.arguments as Map);
        _levels.add(RecordLevel(
          level: (args['level'] as num?)?.toDouble() ?? 0,
          seconds: (args['seconds'] as num?)?.toDouble() ?? 0,
        ));
        break;
      case 'onRecorderError':
        _levels.addError((call.arguments as Map?)?['reason'] ?? 'recording failed');
        break;
      case 'onPermissionsChanged':
        _callEvents.add(const CallEvent(CallState.permissionsChanged));
        break;
    }
    return null;
  }

  Future<String> platformVersion() async =>
      await _channel.invokeMethod<String>('getPlatformVersion') ?? 'unknown';

  Future<Permissions> permissions() async {
    final map = await _channel.invokeMethod<Map<dynamic, dynamic>>('getPermissionStatus');
    return Permissions.fromMap(Map<String, dynamic>.from(map ?? const {}));
  }

  /// Microphone, phone state and notifications, via the standard dialog.
  Future<void> requestPermissions() =>
      _channel.invokeMethod<void>('requestPermissions');

  /// The overlay is granted on a Settings screen, not by a dialog. Returns true if the
  /// user was sent there, false if it was already granted.
  Future<bool> requestOverlayPermission() async =>
      await _channel.invokeMethod<bool>('requestOverlayPermission') ?? false;

  Future<bool> isScreeningActive() async =>
      await _channel.invokeMethod<bool>('isScreeningActive') ?? false;

  /// Start capture without waiting for a real call — how M3 is tested on a desk.
  Future<void> startCapture() => _channel.invokeMethod<void>('startCapture');

  Future<void> stopCapture() => _channel.invokeMethod<void>('stopCapture');

  /// Update the in-call banner. `signal` is green / amber / red / grey.
  /// Play a WAV out loud through the speaker.
  ///
  /// Returns the clip's length in milliseconds, or 0 if playback could not start — the
  /// caller needs it to keep a verdict from appearing while the voice is still talking.
  Future<int> playClip(String path) async =>
      await _channel.invokeMethod<int>('playClip', {'path': path}) ?? 0;

  Future<void> stopClip() => _channel.invokeMethod<void>('stopClip');

  Future<void> updateOverlay(String text, {String signal = 'grey'}) =>
      _channel.invokeMethod<void>('updateOverlay', {'text': text, 'signal': signal});

  Future<void> hideOverlay() => _channel.invokeMethod<void>('hideOverlay');

  /// Post the verdict as a notification, so it outlives the call.
  ///
  /// Grey posts nothing — "we could not tell" is not worth interrupting for, and an app
  /// that notifies on every call gets muted before the one that matters.
  Future<void> showVerdictNotification({
    required String signal,
    required String title,
    required String body,
  }) =>
      _channel.invokeMethod<void>('showVerdictNotification', {
        'signal': signal,
        'title': title,
        'body': body,
      });

  Future<void> clearVerdictNotification() =>
      _channel.invokeMethod<void>('clearVerdictNotification');

  /// Start recording an enrollment sample. Returns the file path, or null on failure.
  Future<String?> startRecording() =>
      _channel.invokeMethod<String>('startRecording');

  /// Stop recording. Returns the finished WAV path, or null if nothing usable was captured.
  Future<String?> stopRecording() =>
      _channel.invokeMethod<String>('stopRecording');

  Future<bool> isRecording() async =>
      await _channel.invokeMethod<bool>('isRecording') ?? false;
}

/// A live microphone reading while enrollment is recording.
class RecordLevel {
  const RecordLevel({required this.level, required this.seconds});

  /// Peak amplitude, 0..1.
  final double level;

  /// Seconds recorded so far.
  final double seconds;
}

enum CallState { ringing, answered, ended, error, permissionsChanged }

class CallEvent {
  const CallEvent(this.state, {this.number, this.detail});
  final CallState state;
  final String? number;
  final String? detail;
}

/// One captured window of call audio.
class AudioChunk {
  const AudioChunk({
    required this.sessionId,
    required this.index,
    required this.sampleRate,
    required this.durationMs,
    required this.pcm16,
  });

  final String sessionId;
  final int index;
  final int sampleRate;
  final int durationMs;

  /// Raw little-endian PCM16. Not a WAV — [toWav] adds the header.
  final Uint8List pcm16;

  factory AudioChunk.fromMap(Map<String, dynamic> map) => AudioChunk(
        sessionId: map['sessionId'] as String? ?? '',
        index: map['index'] as int? ?? 0,
        sampleRate: map['sampleRate'] as int? ?? 16000,
        durationMs: (map['durationMs'] as num?)?.toInt() ?? 0,
        pcm16: base64Decode(map['pcm16Base64'] as String? ?? ''),
      );

  /// Wrap the PCM in a 44-byte WAV header.
  ///
  /// The backend's `/api/screen` takes a multipart *file* and normalises it with ffmpeg,
  /// so it needs a container it can identify. Raw PCM is rejected — ffmpeg cannot guess
  /// the sample rate or bit depth from bytes alone.
  Uint8List toWav() {
    const headerSize = 44;
    final dataSize = pcm16.length;
    final bytes = BytesBuilder();

    void ascii(String s) => bytes.add(utf8.encode(s));
    void u32(int v) => bytes.add(Uint8List(4)..buffer.asByteData().setUint32(0, v, Endian.little));
    void u16(int v) => bytes.add(Uint8List(2)..buffer.asByteData().setUint16(0, v, Endian.little));

    ascii('RIFF');
    u32(headerSize - 8 + dataSize); // everything after this field
    ascii('WAVE');
    ascii('fmt ');
    u32(16); // PCM fmt chunk size
    u16(1); // format 1 = PCM
    u16(1); // mono
    u32(sampleRate);
    u32(sampleRate * 2); // byte rate: rate * channels * bytesPerSample
    u16(2); // block align
    u16(16); // bits per sample
    ascii('data');
    u32(dataSize);
    bytes.add(pcm16);

    return bytes.toBytes();
  }
}

class Permissions {
  const Permissions({
    required this.microphone,
    required this.phoneState,
    required this.overlay,
  });

  final bool microphone;
  final bool phoneState;
  final bool overlay;

  /// Screening cannot run without all three.
  bool get allGranted => microphone && phoneState && overlay;

  factory Permissions.fromMap(Map<String, dynamic> map) => Permissions(
        microphone: map['microphone'] as bool? ?? false,
        phoneState: map['phoneState'] as bool? ?? false,
        overlay: map['overlay'] as bool? ?? false,
      );

  static const none = Permissions(microphone: false, phoneState: false, overlay: false);
}
