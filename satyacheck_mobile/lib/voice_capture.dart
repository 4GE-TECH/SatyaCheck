import 'dart:async';
import 'package:flutter/material.dart';
import 'native_bridge.dart';
import 'theme.dart';
import 'widgets.dart';

/// Captures real microphone audio. Elapsed time never substitutes for amplitude.
class VoiceCapture extends StatefulWidget {
  const VoiceCapture(
      {super.key,
      required this.onReady,
      required this.onActive,
      this.minSeconds = 2,
      this.disabled = false});
  final ValueChanged<String?> onReady;
  final ValueChanged<bool> onActive;
  final double minSeconds;
  final bool disabled;
  @override
  State<VoiceCapture> createState() => _VoiceCaptureState();
}

class _VoiceCaptureState extends State<VoiceCapture>
    with WidgetsBindingObserver {
  final _bridge = NativeBridge.instance;
  StreamSubscription<RecordLevel>? _subscription;
  bool _recording = false,
      _starting = false,
      _stopping = false,
      _playing = false;
  double _level = 0, _seconds = 0, _peak = 0;
  String? _path, _error;
  Timer? _playbackTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _bridge.listen();
    _subscription = _bridge.recordLevels.listen((event) {
      if (!mounted || !_recording) return;
      setState(() {
        _level = event.level;
        _seconds = event.seconds;
        if (_level > _peak) _peak = _level;
      });
      if (_seconds >= 120 && !_stopping) unawaited(_stop());
    }, onError: (Object error) {
      if (!mounted) return;
      setState(() {
        _recording = false;
        _starting = false;
        _path = null;
        _error = 'The microphone stopped. Please try recording again.';
      });
      widget.onReady(null);
      widget.onActive(false);
      debugPrint('SatyaCheck recorder: $error');
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused && _recording) unawaited(_stop());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _subscription?.cancel();
    _playbackTimer?.cancel();
    if (_recording) unawaited(_bridge.stopRecording().catchError((_) => null));
    unawaited(_bridge.stopClip().catchError((_) {}));
    super.dispose();
  }

  Future<void> _start() async {
    if (_starting || _recording || widget.disabled) return;
    setState(() {
      _starting = true;
      _error = null;
      _path = null;
      _seconds = 0;
      _level = 0;
      _peak = 0;
    });
    widget.onReady(null);
    widget.onActive(true);
    try {
      await _bridge.stopClip();
      final permissions = await _bridge.permissions();
      if (!permissions.microphone) {
        await _bridge.requestMicrophonePermission();
        if (mounted)
          setState(() => _error =
              'Allow microphone access, then tap Start recording. You can also choose a saved audio file.');
        return;
      }
      final path = await _bridge.startRecording();
      if (!mounted) {
        await _bridge.stopRecording();
        return;
      }
      if (path == null) {
        setState(() => _error =
            'Could not open the microphone. Check that another app is not using it.');
        return;
      }
      setState(() {
        _recording = true;
        _playing = false;
      });
    } catch (error) {
      debugPrint('SatyaCheck recorder start: $error');
      if (mounted)
        setState(() => _error =
            'Microphone access is unavailable. Check permissions and try again.');
    } finally {
      if (mounted) {
        setState(() => _starting = false);
        widget.onActive(_recording);
      }
    }
  }

  Future<void> _stop() async {
    if (!_recording || _stopping) return;
    _stopping = true;
    String? path;
    try {
      path = await _bridge.stopRecording();
    } catch (error) {
      debugPrint('SatyaCheck recorder stop: $error');
    }
    if (!mounted) return;
    setState(() {
      _recording = false;
      _stopping = false;
      _level = 0;
      if (_peak < 0.01) {
        _error =
            'No audible speech was captured. Move closer, or use a device that is not on a call.';
        _path = null;
      } else if (_seconds < widget.minSeconds) {
        _error =
            'Record at least ${widget.minSeconds.round()} seconds. The service will also check usable speech.';
        _path = null;
      } else if (path == null) {
        _error = 'The recording could not be saved. Please try again.';
        _path = null;
      } else {
        _path = path;
        _error = null;
      }
    });
    widget.onReady(_path);
    widget.onActive(false);
  }

  Future<void> _preview() async {
    try {
      if (_playing) {
        await _bridge.stopClip();
        _playbackTimer?.cancel();
        if (mounted) setState(() => _playing = false);
        return;
      }
      if (_path == null) return;
      final duration = await _bridge.playClip(_path!);
      if (!mounted) return;
      if (duration <= 0) {
        setState(() =>
            _error = 'Could not play this recording. Try recording again.');
        return;
      }
      setState(() => _playing = true);
      _playbackTimer?.cancel();
      _playbackTimer = Timer(Duration(milliseconds: duration), () {
        if (mounted) setState(() => _playing = false);
      });
    } catch (error) {
      debugPrint('SatyaCheck preview: $error');
      if (mounted) setState(() => _error = 'Audio playback is unavailable.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final status = _recording
        ? 'Listening'
        : _path == null
            ? 'Ready when you are'
            : 'Recording ready';
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Container(
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          color: p.raise,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: _recording ? p.edge(p.danger) : p.line),
        ),
        child: Stack(children: [
          VoiceStage(level: _level.clamp(0, 1).toDouble(), height: 190),
          Positioned.fill(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  if (_recording) Container(width: 10, height: 10, margin: const EdgeInsets.only(right: 10), decoration: BoxDecoration(color: p.danger, shape: BoxShape.circle)),
                  Text('${_seconds.round()}s', style: TextStyle(fontFamily: sans, fontSize: 40, fontWeight: FontWeight.w300, letterSpacing: -2, color: p.text)),
                ]),
                Text(status, style: theme.textTheme.bodyMedium),
              ]),
            ),
          ),
        ]),
      ),
      const SizedBox(height: 10),
      Semantics(
        label: 'Microphone sound level',
        value: '${(_level * 100).round()} percent',
        child: ClipRRect(
          borderRadius: BorderRadius.circular(9),
          child: LinearProgressIndicator(value: _level.clamp(0, 1).toDouble(), minHeight: 6),
        ),
      ),
      const SizedBox(height: 8),
      Text(
        _recording && _seconds > 2 && _peak < 0.01 ? 'Very quiet. Move closer and speak normally.' : 'A real sound level, not just a running timer.',
        style: theme.textTheme.bodySmall?.copyWith(color: _recording && _seconds > 2 && _peak < 0.01 ? p.caution : null),
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: 16),
      if (_recording)
        PillButton(label: 'Stop recording', icon: Icons.stop_rounded, kind: PillKind.danger, expand: true, onPressed: _stopping ? null : _stop)
      else
        PillButton(
          label: _starting ? 'Opening microphone…' : _path == null ? 'Start recording' : 'Record again',
          icon: Icons.mic_rounded,
          kind: _path == null ? PillKind.primary : PillKind.secondary,
          expand: true,
          busy: _starting,
          onPressed: widget.disabled ? null : _start,
        ),
      if (_path != null && !_recording)
        Padding(
          padding: const EdgeInsets.only(top: 10),
          child: PillButton(
            label: _playing ? 'Stop preview' : 'Listen to recording',
            icon: _playing ? Icons.stop_rounded : Icons.play_arrow_rounded,
            kind: PillKind.ghost,
            expand: true,
            onPressed: widget.disabled ? null : _preview,
          ),
        ),
      if (_error != null) Padding(padding: const EdgeInsets.only(top: 16), child: InfoMessage(_error!, error: true)),
    ]);
  }
}

class CaptureScreen extends StatefulWidget {
  const CaptureScreen({super.key});
  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends State<CaptureScreen> {
  String? _path;
  bool _active = false;
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Record nearby')),
      body: SafeArea(
        child: ListView(padding: const EdgeInsets.fromLTRB(20, 4, 20, 32), children: [
          Reveal(child: Text('Let’s hear the conversation.', style: theme.textTheme.displayMedium)),
          const SizedBox(height: 12),
          Text('Use this phone near a separate device on speaker. Android cannot record a cellular call happening on this phone.', style: theme.textTheme.bodyLarge),
          const SizedBox(height: 24),
          Reveal(
            delay: const Duration(milliseconds: 120),
            child: VoiceCapture(onReady: (path) => setState(() => _path = path), onActive: (active) => setState(() => _active = active)),
          ),
          const SizedBox(height: 18),
          PillButton(
            label: 'Use this recording',
            trailing: Icons.arrow_forward_rounded,
            large: true,
            expand: true,
            onPressed: _path != null && !_active ? () => Navigator.pop(context, _path) : null,
          ),
          const SizedBox(height: 14),
          Text('Record only with permission. Audio is sent to your configured screening service when you start the check.', style: theme.textTheme.bodySmall, textAlign: TextAlign.center),
        ]),
      ),
    );
  }
}
