import 'dart:async';

import 'package:flutter/material.dart';

import 'call_session.dart';
import 'live_calls.dart';
import 'models.dart';
import 'palette.dart';

/// Calls the backend is screening, as they happen: the app's copy of the dashboard's
/// Live calls page (web/src/pages/LivePage.tsx), fed by the same /api/ws/live.
///
/// Follows whichever call updated last, unless one is picked from the list. Rendering
/// rules from docs/LIVE_FEED.md: colour comes from `overlay_state`; `insufficient` is
/// "listening", not a judgement; a verdict is a level with evidence, never an accusation;
/// a voice check that did not run is "not measured", never "genuine".
class LiveScreen extends StatefulWidget {
  const LiveScreen({super.key, required this.session});

  final CallSession session;

  @override
  State<LiveScreen> createState() => _LiveScreenState();
}

class _LiveScreenState extends State<LiveScreen> {
  StreamSubscription<CallSessionState>? _states;
  Timer? _clock;
  late LiveFeedState _feed = widget.session.liveFeedState;

  /// A call the viewer picked. Null means follow whichever call updated last.
  String? _pinned;

  @override
  void initState() {
    super.initState();
    _states = widget.session.states.listen((s) => setState(() => _feed = s.liveFeed));
    // Call durations tick while a call is live.
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (widget.session.liveCalls.value.any((c) => !c.ended)) setState(() {});
    });
  }

  @override
  void dispose() {
    _states?.cancel();
    _clock?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Live calls')),
      body: ValueListenableBuilder<List<LiveCall>>(
        valueListenable: widget.session.liveCalls,
        builder: (context, calls, _) {
          final pinned = calls.where((c) => c.sessionId == _pinned).firstOrNull;
          LiveCall? latest;
          for (final call in calls) {
            if (latest == null || call.lastSeen.isAfter(latest.lastSeen)) latest = call;
          }
          final focused = pinned ?? latest;

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _FeedStatus(state: _feed),
              const SizedBox(height: 16),
              if (focused == null)
                _Waiting(feed: _feed)
              else
                _LiveCallView(call: focused),
              if (calls.isNotEmpty) ...[
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: Text('Calls on this feed',
                          style: Theme.of(context).textTheme.titleMedium),
                    ),
                    if (pinned != null)
                      TextButton(
                        onPressed: () => setState(() => _pinned = null),
                        child: const Text('Follow the latest'),
                      ),
                  ],
                ),
                for (final call in calls)
                  _CallTile(
                    call: call,
                    focused: call.sessionId == focused?.sessionId,
                    onTap: () => setState(() => _pinned = call.sessionId),
                  ),
              ],
            ],
          );
        },
      ),
    );
  }
}

// --- wording ------------------------------------------------------------------

const _headlines = {
  TrustBand.insufficient: (
    'Listening…',
    'Not enough clear speech yet to judge this call.',
  ),
  TrustBand.unverified: (
    'Unverified caller',
    'Not an enrolled voice, which is normal for a stranger. Nothing worrying so far.',
  ),
  TrustBand.verified: (
    'Verified caller',
    'The voice matches an enrolled family member.',
  ),
  TrustBand.caution: (
    'Check before you act',
    'Something on this call needs verifying before anyone sends money or shares a code.',
  ),
  TrustBand.suspicious: (
    'Signs of a scam call',
    'Several warning signs. Do not send money or share any code.',
  ),
  TrustBand.highRisk: (
    'Likely scam — do not send money',
    'Strong signs of fraud on this call.',
  ),
};

const _bandLabels = {
  TrustBand.insufficient: 'Listening',
  TrustBand.unverified: 'Unverified',
  TrustBand.verified: 'Verified',
  TrustBand.caution: 'Caution',
  TrustBand.suspicious: 'Suspicious',
  TrustBand.highRisk: 'High risk',
};

const _identity = {
  'match': 'Matches an enrolled voice',
  'mismatch': 'Does not match the enrolled voice',
  'unknown': 'Not an enrolled voice',
};

String _duration(Duration d) {
  final s = d.inSeconds < 0 ? 0 : d.inSeconds;
  return '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';
}

/// The colour for text on a verdict: grey reads as plain white, not as a warning.
Color _ink(Signal signal) => signal == Signal.grey ? Colors.white : signalColors[signal]!;

// --- pieces -------------------------------------------------------------------

class _FeedStatus extends StatelessWidget {
  const _FeedStatus({required this.state});

  final LiveFeedState state;

  @override
  Widget build(BuildContext context) {
    final (icon, colour, text, note) = switch (state) {
      LiveFeedState.connected => (Icons.sensors, Colors.lightBlueAccent, 'Live feed connected', null),
      LiveFeedState.connecting => (
          Icons.sync,
          signalColors[Signal.amber]!,
          'Connecting to the live feed…',
          'Retrying. If this lasts, check the server address and live-feed token on the home screen.',
        ),
      LiveFeedState.off => (
          Icons.sensors_off,
          signalColors[Signal.grey]!,
          'Live feed off',
          'Add the live-feed token under Screening server on the home screen.',
        ),
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 18, color: colour),
            const SizedBox(width: 8),
            Text(text, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          ],
        ),
        if (note != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(note, style: const TextStyle(fontSize: 13, color: Colors.white70)),
          ),
      ],
    );
  }
}

class _Waiting extends StatelessWidget {
  const _Waiting({required this.feed});

  final LiveFeedState feed;

  @override
  Widget build(BuildContext context) {
    // Only promise a call while the feed can deliver one.
    if (feed != LiveFeedState.connected) return const SizedBox.shrink();
    return const Card(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: 20, vertical: 32),
        child: Column(
          children: [
            Icon(Icons.phone_callback, size: 44, color: Colors.white54),
            SizedBox(height: 12),
            Text('Waiting for a call',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
            SizedBox(height: 8),
            Text(
              'Verdicts appear here a few seconds after a call starts. Earlier verdicts are '
              'not replayed, so keep the app open before the call begins.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 15, color: Colors.white70),
            ),
          ],
        ),
      ),
    );
  }
}

class _LiveCallView extends StatelessWidget {
  const _LiveCallView({required this.call});

  final LiveCall call;

  @override
  Widget build(BuildContext context) {
    final v = call.latest;
    final r = v.result;
    final colour = signalColors[v.signal]!;
    final (title, detail) = _headlines[r.band]!;
    final ended = call.ended;
    final duration = (ended ? call.lastSeen : DateTime.now()).difference(call.firstSeen);
    final intent = (r.scriptRisk.clamp(0.0, 1.0) * 100).round();
    final warning = r.vernacularWarning?.trim() ?? '';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ── The verdict ─────────────────────────────────────────────────
        Card(
          color: colour.withValues(alpha: 0.18),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
            side: BorderSide(color: colour, width: 2),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.call, size: 16, color: Colors.white70),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        v.callerNumber ?? 'Unknown number',
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontFamily: 'monospace', fontWeight: FontWeight.bold, fontSize: 15),
                      ),
                    ),
                    _Pill(ended: ended),
                    const SizedBox(width: 8),
                    Text(_duration(duration),
                        style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
                  ],
                ),
                const SizedBox(height: 12),
                if (v.escalated && !ended)
                  Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: signalColors[Signal.red],
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Text('Warning level raised',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                  ),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(title,
                              style: TextStyle(
                                  fontSize: 28,
                                  height: 1.15,
                                  fontWeight: FontWeight.w800,
                                  color: _ink(v.signal))),
                          const SizedBox(height: 6),
                          Text(detail, style: const TextStyle(fontSize: 15, color: Colors.white70)),
                          if (v.threat != null) ...[
                            const SizedBox(height: 6),
                            Text(
                              'Resembles ${v.threat}${v.threatSector == null ? '' : ' · ${v.threatSector}'}',
                              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        const Text('Trust score',
                            style: TextStyle(fontSize: 11, color: Colors.white60)),
                        Text(
                          v.listening ? '—' : '${r.trustScore.round()}',
                          style: TextStyle(
                              fontSize: 52,
                              height: 1.0,
                              fontWeight: FontWeight.w800,
                              fontFamily: 'monospace',
                              color: _ink(v.signal)),
                        ),
                        const Text('out of 100',
                            style: TextStyle(fontSize: 11, color: Colors.white60)),
                      ],
                    ),
                  ],
                ),
                if (warning.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(warning,
                      style: TextStyle(
                          fontSize: 18, fontWeight: FontWeight.bold, color: _ink(v.signal))),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),

        // ── The three signals ───────────────────────────────────────────
        _SignalTile(
          icon: Icons.person_outline,
          label: 'Who is speaking',
          value: _identity[r.speakerVerdict] ?? r.speakerVerdict,
          detail: r.mode == 'identity_check'
              ? 'Checking a known contact'
              : 'Unknown caller: judged on what is asked',
        ),
        _SignalTile(
          icon: Icons.graphic_eq,
          label: 'Voice',
          value: switch (v.authenticity) {
            'synthetic' => 'Signs of a cloned voice',
            'bonafide' => 'No signs of a cloned voice',
            _ => 'Not measured',
          },
          warn: v.authenticity == 'synthetic',
          detail: v.authenticity == 'unavailable'
              ? 'The voice check did not run on this call.'
              : 'From the sound of the voice itself.',
        ),
        _SignalTile(
          icon: Icons.shield_outlined,
          label: 'What is being asked',
          value: 'Scam-language risk $intent%',
          bar: intent / 100,
        ),
        const SizedBox(height: 12),

        // ── Timeline and transcript ─────────────────────────────────────
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Every 2 seconds of the call, oldest first',
                    style: TextStyle(fontSize: 12, color: Colors.white60)),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 4,
                  runSpacing: 4,
                  children: [
                    for (final w in call.windows)
                      Tooltip(
                        message: 'Window ${w.windowIndex} · ${_bandLabels[w.result.band]} · '
                            'trust ${w.result.trustScore.round()}${w.isFinal ? ' · final' : ''}',
                        child: Container(
                          width: 10,
                          height: 22,
                          decoration: BoxDecoration(
                            color: signalColors[w.signal],
                            borderRadius: BorderRadius.circular(2),
                            border: w.isFinal ? Border.all(color: Colors.white, width: 2) : null,
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    const Expanded(
                      child: Text('What was said',
                          style: TextStyle(fontSize: 12, color: Colors.white60)),
                    ),
                    if (r.detectedLanguage != 'unknown')
                      Text(r.detectedLanguage,
                          style: const TextStyle(
                              fontSize: 12, color: Colors.white60, fontFamily: 'monospace')),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  r.transcript.isNotEmpty
                      ? '“${r.transcript}”'
                      : ended
                          ? 'No speech was understood on this call.'
                          : 'The transcript appears after about 10 seconds of speech.',
                  style: TextStyle(
                    fontSize: 16,
                    fontStyle: r.transcript.isNotEmpty ? FontStyle.italic : FontStyle.normal,
                    color: r.transcript.isNotEmpty ? Colors.white : Colors.white60,
                  ),
                ),
              ],
            ),
          ),
        ),

        // ── What to do, and why ─────────────────────────────────────────
        if (r.recommendedActions.isNotEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('What to tell the person on the call',
                      style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  for (var i = 0; i < r.recommendedActions.length; i++)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Text('${i + 1}. ${r.recommendedActions[i]}',
                          style: const TextStyle(fontSize: 15, color: Colors.white70)),
                    ),
                ],
              ),
            ),
          ),
        if (r.reasonCodes.isNotEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Why', style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  for (final rc in r.reasonCodes) _Reason(code: rc),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.ended});

  final bool ended;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: Colors.black26,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.white24),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (!ended) ...[
              Icon(Icons.circle, size: 8, color: signalColors[Signal.red]),
              const SizedBox(width: 4),
            ],
            Text(ended ? 'Call ended' : 'In progress',
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          ],
        ),
      );
}

class _SignalTile extends StatelessWidget {
  const _SignalTile({
    required this.icon,
    required this.label,
    required this.value,
    this.detail,
    this.warn = false,
    this.bar,
  });

  final IconData icon;
  final String label;
  final String value;
  final String? detail;
  final bool warn;

  /// 0–1, drawn as a bar under the value.
  final double? bar;

  @override
  Widget build(BuildContext context) {
    final fill = bar;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 16, color: Colors.white60),
                const SizedBox(width: 6),
                Text(label, style: const TextStyle(fontSize: 12, color: Colors.white60)),
              ],
            ),
            const SizedBox(height: 4),
            Text(value,
                style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.bold,
                    color: warn ? signalColors[Signal.red] : Colors.white)),
            if (detail != null)
              Text(detail!, style: const TextStyle(fontSize: 13, color: Colors.white70)),
            if (fill != null) ...[
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: fill,
                  minHeight: 6,
                  backgroundColor: Colors.white12,
                  color: fill >= 0.6
                      ? signalColors[Signal.red]
                      : fill >= 0.3
                          ? signalColors[Signal.amber]
                          : signalColors[Signal.grey],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Reason extends StatelessWidget {
  const _Reason({required this.code});

  final ReasonCode code;

  @override
  Widget build(BuildContext context) {
    final severity = code.severity ?? 'info';
    final (background, foreground) = switch (severity) {
      'critical' => (signalColors[Signal.red]!, Colors.white),
      'high' => (signalColors[Signal.red]!.withValues(alpha: 0.25), Colors.white),
      'medium' => (signalColors[Signal.amber]!.withValues(alpha: 0.3), Colors.white),
      _ => (Colors.white12, Colors.white70),
    };
    final measured = code.value;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(4)),
                child: Text(severity,
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: foreground)),
              ),
              if (measured != null && measured.isNotEmpty)
                Text(
                  '$measured${code.threshold == null ? '' : ' (threshold ${code.threshold})'}',
                  style: const TextStyle(
                      fontSize: 11, color: Colors.white54, fontFamily: 'monospace'),
                ),
            ],
          ),
          const SizedBox(height: 4),
          Text(code.explanation, style: const TextStyle(fontSize: 14)),
        ],
      ),
    );
  }
}

class _CallTile extends StatelessWidget {
  const _CallTile({required this.call, required this.focused, required this.onTap});

  final LiveCall call;
  final bool focused;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final v = call.latest;
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: focused ? Colors.white : Colors.white12),
      ),
      child: ListTile(
        onTap: onTap,
        leading: CircleAvatar(radius: 7, backgroundColor: signalColors[v.signal]),
        title: Text(v.callerNumber ?? call.sessionId,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.w600)),
        subtitle: Text(
            '${_bandLabels[v.result.band]} · ${call.ended ? 'ended' : 'live'}'
            '${v.listening ? '' : ' · trust ${v.result.trustScore.round()}'}'),
        trailing: Text(TimeOfDay.fromDateTime(call.firstSeen).format(context),
            style: const TextStyle(fontSize: 12, color: Colors.white54)),
      ),
    );
  }
}
