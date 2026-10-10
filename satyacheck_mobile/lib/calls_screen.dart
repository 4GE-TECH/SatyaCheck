import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'api_client.dart';
import 'models.dart';
import 'result_screen.dart';
import 'theme.dart';

/// Phone calls screened through Exotel, as they happen.
///
/// Exotel streams call audio straight to the backend; this tab only watches the live verdict
/// feed (`/api/ws/live`). That is also why it works on the phone that is *in* the call:
/// nothing here needs the microphone, which Android gives to the dialer.
enum FeedStatus { idle, connecting, open, reconnecting, refused, closed }

class LiveFeedController extends ChangeNotifier {
  LiveFeedController(this._api) : _token = ApiClient.defaultLiveToken;

  final ApiClient _api;
  final Map<String, LiveCall> _calls = {};
  LiveFeedSocket? _socket;
  StreamSubscription<LiveVerdict>? _subscription;
  Timer? _retryTimer;
  String _token;
  int _retries = 0;
  bool _wanted = false, _disposed = false;

  FeedStatus status = FeedStatus.idle;

  /// Calls in progress first, then ended ones; most recently updated first within each.
  List<LiveCall> get calls {
    final list = _calls.values.toList();
    list.sort((a, b) {
      if (a.ended != b.ended) return a.ended ? 1 : -1;
      return b.updatedAt.compareTo(a.updatedAt);
    });
    return list;
  }

  /// Connect, or reconnect with a new token. The token lives in memory only.
  Future<void> connect({String? token}) async {
    if (token != null) _token = token.trim();
    _wanted = true;
    _retries = 0;
    await _open();
  }

  Future<void> disconnect() async {
    _wanted = false;
    _retryTimer?.cancel();
    await _teardown();
    _set(FeedStatus.closed);
  }

  void clearEnded() {
    _calls.removeWhere((_, call) => call.ended);
    _notify();
  }

  Future<void> _open() async {
    _retryTimer?.cancel();
    await _teardown();
    _set(_retries == 0 ? FeedStatus.connecting : FeedStatus.reconnecting);
    try {
      final socket = await _api.openLiveFeed(token: _token);
      if (_disposed || !_wanted) {
        await socket.close();
        return;
      }
      _socket = socket;
      _subscription = socket.verdicts.listen(_onVerdict);
      _set(FeedStatus.open);
      _retries = 0;
      final code = await socket.closed;
      if (_disposed || _socket != socket) return;
      _socket = null;
      if (code == 1008) {
        // A wrong or missing token never starts working by itself; ask instead of retrying.
        _set(FeedStatus.refused);
        return;
      }
      _scheduleRetry();
    } catch (error) {
      debugPrint('SatyaCheck live feed: $error');
      if (!_disposed) _scheduleRetry();
    }
  }

  void _scheduleRetry() {
    if (!_wanted || _disposed) {
      _set(FeedStatus.closed);
      return;
    }
    _retries++;
    _set(FeedStatus.reconnecting);
    final delay = Duration(milliseconds: math.min(15000, 600 * (1 << math.min(_retries, 5))));
    _retryTimer = Timer(delay, () => unawaited(_open()));
  }

  void _onVerdict(LiveVerdict verdict) {
    final call = _calls[verdict.sessionId];
    if (call == null) {
      _calls[verdict.sessionId] = LiveCall(verdict);
    } else {
      call.add(verdict);
    }
    if (_calls.length > 30) {
      final oldest = _calls.values.reduce((a, b) => a.updatedAt.isBefore(b.updatedAt) ? a : b);
      _calls.remove(oldest.latest.sessionId);
    }
    _notify();
  }

  Future<void> _teardown() async {
    await _subscription?.cancel();
    _subscription = null;
    final socket = _socket;
    _socket = null;
    await socket?.close();
  }

  void _set(FeedStatus next) {
    status = next;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _wanted = false;
    _retryTimer?.cancel();
    unawaited(_teardown());
    super.dispose();
  }
}

class CallsView extends StatefulWidget {
  const CallsView({super.key, required this.feed, required this.api, required this.padding});
  final LiveFeedController feed;
  final ApiClient api;
  final EdgeInsets padding;
  @override
  State<CallsView> createState() => _CallsViewState();
}

class _CallsViewState extends State<CallsView> {
  final _token = TextEditingController();
  Timer? _clock;

  @override
  void initState() {
    super.initState();
    // Durations on live calls tick once a second.
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && widget.feed.calls.any((c) => !c.ended)) setState(() {});
    });
  }

  @override
  void dispose() {
    _clock?.cancel();
    _token.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.feed,
      builder: (context, _) {
        final theme = Theme.of(context);
        final feed = widget.feed;
        final calls = feed.calls;
        final live = calls.where((c) => !c.ended).toList();
        final ended = calls.where((c) => c.ended).toList();
        return ListView(key: const PageStorageKey('calls'), padding: widget.padding, children: [
          Reveal(
            child: Padding(
              padding: const EdgeInsets.only(top: 18, bottom: 22),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Semantics(header: true, child: Text('Phone calls', style: theme.textTheme.displayMedium)),
                const SizedBox(height: 12),
                Text('Calls routed through Exotel are screened on the server while they happen. Each one appears here and updates about every two seconds of speech.',
                    style: theme.textTheme.bodyLarge),
              ]),
            ),
          ),
          _FeedBar(feed: feed),
          if (feed.status == FeedStatus.refused) ...[
            const SizedBox(height: 14),
            _TokenPanel(controller: _token, onConnect: () => feed.connect(token: _token.text)),
          ],
          const SizedBox(height: 24),
          _SectionTitle('On a call now', live.length),
          const SizedBox(height: 12),
          if (live.isEmpty)
            _EmptyCalls(open: feed.status == FeedStatus.open)
          else
            for (final call in live)
              Padding(padding: const EdgeInsets.only(bottom: 12), child: _CallCard(call: call, api: widget.api)),
          if (ended.isNotEmpty) ...[
            const SizedBox(height: 18),
            Row(children: [
              Expanded(child: _SectionTitle('Ended in this session', ended.length)),
              TextButton(onPressed: feed.clearEnded, child: const Text('Clear')),
            ]),
            const SizedBox(height: 12),
            for (final call in ended)
              Padding(padding: const EdgeInsets.only(bottom: 12), child: _CallCard(call: call, api: widget.api)),
          ],
        ]);
      },
    );
  }
}

class _FeedBar extends StatelessWidget {
  const _FeedBar({required this.feed});
  final LiveFeedController feed;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final (label, color) = switch (feed.status) {
      FeedStatus.open => ('Watching for calls', p.safe),
      FeedStatus.connecting => ('Connecting to the call feed…', p.caution),
      FeedStatus.reconnecting => ('Reconnecting…', p.caution),
      FeedStatus.refused => ('The feed needs a token', p.danger),
      FeedStatus.closed || FeedStatus.idle => ('Disconnected', p.neutral),
    };
    final active = feed.status == FeedStatus.open || feed.status == FeedStatus.connecting || feed.status == FeedStatus.reconnecting;
    return Semantics(
      liveRegion: true,
      child: Panel(
        padding: const EdgeInsets.fromLTRB(18, 10, 10, 10),
        child: Row(children: [
          Container(width: 10, height: 10, decoration: BoxDecoration(shape: BoxShape.circle, color: color)),
          const SizedBox(width: 12),
          Expanded(child: Text(label, style: theme.textTheme.titleMedium)),
          active
              ? TextButton(onPressed: feed.disconnect, child: const Text('Disconnect'))
              : FilledButton.tonal(onPressed: () => feed.connect(), child: const Text('Connect')),
        ]),
      ),
    );
  }
}

class _TokenPanel extends StatelessWidget {
  const _TokenPanel({required this.controller, required this.onConnect});
  final TextEditingController controller;
  final VoidCallback onConnect;
  @override
  Widget build(BuildContext context) {
    return Panel(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('The service refused the feed. It is protected by a token because verdicts carry call transcripts. Ask whoever runs the service for it.',
            style: Theme.of(context).textTheme.bodyMedium),
        const SizedBox(height: 14),
        TextField(
          controller: controller,
          obscureText: true,
          autocorrect: false,
          enableSuggestions: false,
          decoration: const InputDecoration(labelText: 'Live-feed token', helperText: 'Kept only while the app is open. Never saved.'),
          onSubmitted: (_) => onConnect(),
        ),
        const SizedBox(height: 14),
        PillButton(label: 'Connect with token', onPressed: onConnect),
      ]),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title, this.count);
  final String title;
  final int count;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Row(children: [
      Flexible(child: Text(title, style: Theme.of(context).textTheme.headlineSmall)),
      const SizedBox(width: 10),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
        decoration: BoxDecoration(color: p.panel2, borderRadius: BorderRadius.circular(999), border: Border.all(color: p.line)),
        child: Text('$count', style: TextStyle(fontFamily: mono, fontSize: 13, color: p.text2)),
      ),
    ]);
  }
}

class _EmptyCalls extends StatelessWidget {
  const _EmptyCalls({required this.open});
  final bool open;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    return Panel(
      child: Column(children: [
        Icon(Icons.phone_in_talk_outlined, size: 38, color: p.voice3),
        const SizedBox(height: 14),
        Text(open ? 'No call in progress' : 'Not watching for calls yet', style: theme.textTheme.titleLarge, textAlign: TextAlign.center),
        const SizedBox(height: 8),
        Text('Verdicts only arrive while a call is live, and earlier ones are not replayed. Keep this tab open before the call starts.',
            textAlign: TextAlign.center, style: theme.textTheme.bodyMedium),
      ]),
    );
  }
}

const _identityText = {'match': 'A voice you enrolled', 'mismatch': 'Differs from the claimed person', 'unknown': 'Not an enrolled voice'};
const _voiceText = {'synthetic': 'Signs of a synthetic voice', 'bonafide': 'No synthetic signs', 'unavailable': 'Not measured'};

class _CallCard extends StatefulWidget {
  const _CallCard({required this.call, required this.api});
  final LiveCall call;
  final ApiClient api;
  @override
  State<_CallCard> createState() => _CallCardState();
}

class _CallCardState extends State<_CallCard> {
  bool _opening = false;
  String? _error;

  Future<void> _openReport() async {
    setState(() {
      _opening = true;
      _error = null;
    });
    final call = widget.call;
    final result = await widget.api.screening(call.latest.sessionId);
    if (!mounted) return;
    setState(() => _opening = false);
    if (result == null) {
      setState(() => _error = 'The full report is not available yet. Try again in a moment.');
      return;
    }
    await Navigator.push(context, MaterialPageRoute(builder: (_) => ResultScreen(result: result, label: call.latest.callerId ?? 'Phone call')));
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final call = widget.call, v = call.latest;
    final listening = v.band == TrustBand.insufficient;
    final tone = switch (v.overlay) {
      Signal.green => p.safe,
      Signal.amber => p.caution,
      Signal.red => p.danger,
      Signal.grey => p.neutral,
    };
    final seconds = (call.ended ? call.updatedAt : DateTime.now()).difference(call.startedAt).inSeconds;
    final duration = '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
    final transcript = v.transcript.trim();
    final evidence = v.evidence.take(3).toList();

    return Semantics(
      container: true,
      label: 'Call from ${v.callerId ?? 'an unknown number'}, ${listening ? 'listening' : bandLabel(v.band)}',
      child: Container(
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          color: p.panel,
          borderRadius: BorderRadius.circular(26),
          border: Border.all(color: call.escalations > 0 && !call.ended ? p.edge(tone) : p.line),
        ),
        child: IntrinsicHeight(
          child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Container(width: 6, color: listening ? p.neutral : tone),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(v.callerId ?? 'Unknown number', style: TextStyle(fontFamily: mono, fontSize: 18, fontWeight: FontWeight.w600, color: p.text)),
                        // The displayed number is what the network passed on. It can be spoofed,
                        // so it is shown as a hint and never counts for or against the caller.
                        if (v.callerId != null) Text('Number shown on the call · can be faked', style: theme.textTheme.bodySmall),
                        const SizedBox(height: 2),
                        Text('${call.ended ? 'Ended after' : 'On call ·'} $duration · ${v.mode == 'identity_check' ? 'known-contact check' : 'stranger check'}',
                            style: theme.textTheme.bodySmall),
                      ]),
                    ),
                    const SizedBox(width: 8),
                    Flexible(child: ToneChip(listening ? 'Listening…' : bandLabel(v.band), listening ? p.neutral : tone)),
                  ]),
                  const SizedBox(height: 14),
                  if (listening)
                    Text('No score yet: not enough clear speech', style: theme.textTheme.bodyMedium)
                  else
                    Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                      Text('${v.trustScore.round()}', style: TextStyle(fontFamily: sans, fontSize: 44, height: 1, fontWeight: FontWeight.w300, color: tone)),
                      const SizedBox(width: 6),
                      Expanded(child: Padding(padding: const EdgeInsets.only(bottom: 4), child: Text('/100 trust for the call', style: theme.textTheme.bodySmall))),
                    ]),
                  if (!listening && !call.ended && v.windowTrustScore != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text('Right now: ${v.windowTrustScore!.round()}/100. The call score only goes down, so an earlier warning stays visible.',
                          style: theme.textTheme.bodySmall),
                    ),
                  const SizedBox(height: 12),
                  _signalRow(context, 'Identity', _identityText[v.identity] ?? 'Not assessed'),
                  _signalRow(context, 'Voice', _voiceText[v.authenticity] ?? 'Not measured'),
                  _signalRow(context, 'What is asked', '${(v.intentRisk.clamp(0, 1) * 100).round()}% concern'),
                  if (v.threatLabel != null) ...[
                    const SizedBox(height: 10),
                    _box(context, Text.rich(TextSpan(children: [
                      const TextSpan(text: 'Resembles '),
                      TextSpan(text: v.threatLabel!.threat, style: const TextStyle(fontWeight: FontWeight.w700)),
                      TextSpan(text: ' · ${v.threatLabel!.sectorText}', style: TextStyle(color: p.muted)),
                    ]), style: theme.textTheme.bodyMedium)),
                  ],
                  if (v.vernacularWarning != null && v.vernacularWarning!.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    _box(context, Text(v.vernacularWarning!, style: theme.textTheme.titleMedium), tint: v.overlay == Signal.amber ? p.caution : p.danger),
                  ],
                  if (!listening && v.recommendedActions.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    _box(context, Text(calm(v.recommendedActions.first), style: theme.textTheme.titleSmall)),
                  ],
                  for (final r in evidence)
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: Container(
                        padding: const EdgeInsets.only(left: 10),
                        decoration: BoxDecoration(border: Border(left: BorderSide(width: 3, color: r.severity == 'critical' || r.severity == 'high' ? p.danger : p.caution))),
                        child: Text(r.explanation, style: theme.textTheme.bodyMedium),
                      ),
                    ),
                  const SizedBox(height: 12),
                  Text('Transcript · automatic, may contain errors', style: theme.textTheme.bodySmall),
                  const SizedBox(height: 4),
                  Text(
                    transcript.isEmpty
                        ? 'Appears after roughly 10 to 15 seconds of speech. The score does not wait for it.'
                        : transcript.length > 280
                            ? '…${transcript.substring(transcript.length - 280)}'
                            : transcript,
                    style: theme.textTheme.bodyMedium?.copyWith(color: transcript.isEmpty ? p.muted : p.text),
                  ),
                  if (call.ended) ...[
                    const SizedBox(height: 14),
                    PillButton(
                      label: 'Open the full report',
                      kind: PillKind.secondary,
                      trailing: Icons.arrow_forward_rounded,
                      expand: true,
                      busy: _opening,
                      onPressed: _openReport,
                    ),
                    if (_error != null) Padding(padding: const EdgeInsets.only(top: 10), child: InfoMessage(_error!, error: true)),
                  ],
                ]),
              ),
            ),
          ]),
        ),
      ),
    );
  }

  Widget _signalRow(BuildContext context, String name, String value) {
    final p = context.palette, theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 7),
      decoration: BoxDecoration(border: Border(top: BorderSide(color: p.line))),
      child: Row(children: [
        SizedBox(width: 112, child: Text(name, style: theme.textTheme.bodySmall)),
        Expanded(child: Text(value, style: theme.textTheme.titleSmall)),
      ]),
    );
  }

  Widget _box(BuildContext context, Widget child, {Color? tint}) {
    final p = context.palette;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: tint == null ? p.panel2 : p.soft(tint),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: tint == null ? p.line : p.edge(tint)),
      ),
      child: child,
    );
  }
}
