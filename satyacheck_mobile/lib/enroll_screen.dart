import 'dart:async';

import 'package:flutter/material.dart';

import 'api_client.dart';
import 'native_bridge.dart';

/// Guided voice enrollment.
///
/// The whole screen exists to prevent one failure: a recording that is technically valid
/// and acoustically useless. Too quiet, too far from the mic, or not enough speech. The
/// backend rejects those — or worse, accepts one and builds a voiceprint that later
/// false-mismatches the real person, which reads to a user as "the app does not recognise
/// me" and is far harder to diagnose than a rejection.
///
/// So it does three things a bare record button would not: it gives the person something to
/// read (people dry up after four seconds of "just talk"), shows a live level meter, and
/// refuses to submit until there is enough audio.
class EnrollScreen extends StatefulWidget {
  const EnrollScreen({super.key, required this.api});

  final ApiClient api;

  @override
  State<EnrollScreen> createState() => _EnrollScreenState();
}

class _EnrollScreenState extends State<EnrollScreen> {
  static const _minSeconds = 15.0; // config.ENROLL_MIN_SPEECH_S
  static const _targetSeconds = 25.0;

  final _bridge = NativeBridge.instance;
  final _name = TextEditingController();
  final _relation = TextEditingController(text: 'Family');

  StreamSubscription<RecordLevel>? _levels;

  bool _recording = false;
  bool _uploading = false;
  double _level = 0;
  double _seconds = 0;
  double _peakSeen = 0;
  String? _message;
  String? _wavPath;

  /// Long enough that a natural reading pace fills the required time, and varied enough
  /// that the voiceprint is not built from one repeated phoneme set.
  static const _script =
      'Hello, my name is on this phone and I am setting up call screening. '
      'I usually call my family in the evening to ask how their day went. '
      'If someone rings claiming to be me and asks for money urgently, '
      'please put the phone down and call me back on my saved number first. '
      'I will never ask anyone to send money in a hurry, and I will never '
      'ask for a one time password or a card number over a call.';

  @override
  void initState() {
    super.initState();
    _bridge.listen();
    _levels = _bridge.recordLevels.listen(
      (l) => setState(() {
        _level = l.level;
        _seconds = l.seconds;
        if (l.level > _peakSeen) _peakSeen = l.level;
      }),
      onError: (e) => setState(() {
        _recording = false;
        _message = '$e';
      }),
    );
  }

  @override
  void dispose() {
    _levels?.cancel();
    // Do not leave the microphone open if the user backs out mid-recording.
    if (_recording) _bridge.stopRecording();
    _name.dispose();
    _relation.dispose();
    super.dispose();
  }

  Future<void> _start() async {
    setState(() {
      _message = null;
      _seconds = 0;
      _peakSeen = 0;
      _wavPath = null;
    });
    final path = await _bridge.startRecording();
    if (!mounted) return;
    if (path == null) {
      setState(() => _message = 'Could not start the microphone.');
      return;
    }
    setState(() => _recording = true);
  }

  Future<void> _stop() async {
    final path = await _bridge.stopRecording();
    if (!mounted) return;
    setState(() {
      _recording = false;
      _wavPath = path;
      _level = 0;
      if (path == null) _message = 'Nothing was recorded.';
    });
  }

  Future<void> _submit() async {
    final path = _wavPath;
    if (path == null) return;

    setState(() {
      _uploading = true;
      _message = null;
    });

    final outcome = await widget.api.enroll(
      wavPath: path,
      name: _name.text.trim(),
      relation: _relation.text.trim().isEmpty ? 'Family' : _relation.text.trim(),
    );

    if (!mounted) return;
    setState(() => _uploading = false);

    if (outcome.ok) {
      Navigator.of(context).pop(outcome.name);
    } else {
      // The backend's own words — they say what to do differently.
      setState(() => _message = outcome.error);
    }
  }

  bool get _longEnough => _seconds >= _minSeconds;
  bool get _canSubmit =>
      _wavPath != null && _longEnough && _name.text.trim().isNotEmpty && !_uploading;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Enrol a voice')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _name,
            enabled: !_recording && !_uploading,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(
              labelText: 'Name',
              hintText: 'Who is speaking?',
              border: OutlineInputBorder(),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _relation,
            enabled: !_recording && !_uploading,
            decoration: const InputDecoration(
              labelText: 'Relationship',
              hintText: 'Mother, Son, Friend…',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 20),

          Text('Read this aloud', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const Card(
            child: Padding(
              padding: EdgeInsets.all(14),
              child: Text(_script, style: TextStyle(fontSize: 15, height: 1.5)),
            ),
          ),
          const SizedBox(height: 20),

          _meter(context),
          const SizedBox(height: 16),

          if (_recording)
            FilledButton.tonal(
              onPressed: _stop,
              child: const Text('Stop recording'),
            )
          else
            FilledButton(
              onPressed: _uploading ? null : _start,
              child: Text(_wavPath == null ? 'Start recording' : 'Record again'),
            ),

          if (_wavPath != null && !_recording) ...[
            const SizedBox(height: 10),
            FilledButton(
              onPressed: _canSubmit ? _submit : null,
              child: _uploading
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Save this voice'),
            ),
            if (!_longEnough)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'Too short. Record at least 15 seconds of speech.',
                  style: TextStyle(fontSize: 12, color: Colors.orangeAccent),
                ),
              ),
            if (_name.text.trim().isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text('Enter a name first.',
                    style: TextStyle(fontSize: 12, color: Colors.orangeAccent)),
              ),
          ],

          if (_message != null) ...[
            const SizedBox(height: 16),
            Card(
              color: const Color(0xFF3F2D1A),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Text(_message!, style: const TextStyle(fontSize: 13)),
              ),
            ),
          ],

          const SizedBox(height: 20),
          const Text(
            'Speak normally, at arm’s length, somewhere quiet. Recording more than once, '
            'on different days, makes recognition noticeably more reliable.',
            style: TextStyle(fontSize: 12, color: Colors.white54),
          ),
        ],
      ),
    );
  }

  /// Duration and live level — the two things that decide whether this recording is usable.
  Widget _meter(BuildContext context) {
    final progress = (_seconds / _targetSeconds).clamp(0.0, 1.0);
    // Below roughly 5% peak the mic is not really picking the speaker up.
    final tooQuiet = _recording && _seconds > 2 && _peakSeen < 0.05;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('${_seconds.toStringAsFixed(0)}s',
                    style: Theme.of(context)
                        .textTheme
                        .headlineMedium
                        ?.copyWith(fontWeight: FontWeight.bold)),
                Text(
                  _recording
                      ? (_longEnough ? 'Enough — keep going or stop' : 'Keep talking…')
                      : (_wavPath == null ? 'Not started' : 'Recorded'),
                  style: TextStyle(
                    fontSize: 13,
                    color: _longEnough ? const Color(0xFF16A34A) : Colors.white60,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: progress,
                minHeight: 8,
                backgroundColor: Colors.white12,
                valueColor: AlwaysStoppedAnimation(
                  _longEnough ? const Color(0xFF16A34A) : const Color(0xFF6B7280),
                ),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                const Icon(Icons.mic, size: 18, color: Colors.white54),
                const SizedBox(width: 10),
                Expanded(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: _level.clamp(0.0, 1.0),
                      minHeight: 6,
                      backgroundColor: Colors.white12,
                      valueColor: AlwaysStoppedAnimation(
                        tooQuiet ? const Color(0xFFD97706) : const Color(0xFF3B82F6),
                      ),
                    ),
                  ),
                ),
              ],
            ),
            if (tooQuiet)
              const Padding(
                padding: EdgeInsets.only(top: 10),
                child: Text(
                  'Very quiet — hold the phone closer, or speak up.',
                  style: TextStyle(fontSize: 12, color: Color(0xFFD97706)),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
