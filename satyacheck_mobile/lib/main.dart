import 'dart:async';

import 'package:flutter/material.dart';

import 'api_client.dart';
import 'call_session.dart';
import 'enroll_screen.dart';
import 'models.dart';
import 'native_bridge.dart';

void main() {
  runApp(const SatyaCheckApp());
}

class SatyaCheckApp extends StatelessWidget {
  const SatyaCheckApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SatyaCheck',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorSchemeSeed: const Color(0xFF1F2937),
      ),
      home: const HomePage(),
    );
  }
}

/// Colours for the four verdicts. Kept in one place so the overlay, the notification and
/// this screen cannot drift apart.
const _signalColors = {
  Signal.green: Color(0xFF16A34A),
  Signal.amber: Color(0xFFD97706),
  Signal.red: Color(0xFFDC2626),
  Signal.grey: Color(0xFF6B7280),
};

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver {
  final _bridge = NativeBridge.instance;
  final _api = ApiClient();
  late final CallSession _session = CallSession(api: _api);

  StreamSubscription<CallSessionState>? _states;

  Permissions _permissions = Permissions.none;
  CallSessionState _state = const CallSessionState(phase: CallPhase.idle);
  bool? _backendUp;
  List<EnrolledPerson> _enrolled = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _session.start();
    _states = _session.states.listen((s) => setState(() => _state = s));
    _refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _states?.cancel();
    _session.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // The overlay permission is granted on a Settings screen, so the only way to notice it
    // was granted is to re-check when the user comes back.
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _refresh() async {
    final permissions = await _bridge.permissions();
    final up = await _api.ping();
    final people = up ? await _api.persons() : const <EnrolledPerson>[];
    if (!mounted) return;
    setState(() {
      _permissions = permissions;
      _backendUp = up;
      _enrolled = people;
    });
  }

  Future<void> _openEnroll() async {
    final name = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => EnrollScreen(api: _api)),
    );
    await _refresh();
    if (name != null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Enrolled $name')),
      );
    }
  }

  bool _screening = false;

  bool get _ready => _permissions.allGranted && (_backendUp ?? false);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('SatyaCheck'),
        actions: [IconButton(onPressed: _refresh, icon: const Icon(Icons.refresh))],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _VerdictCard(state: _state, ready: _ready),
          const SizedBox(height: 20),
          if (!_permissions.allGranted) _setup(context),
          if (_permissions.allGranted && _backendUp == false) _backendOffline(),
          if (_state.result != null) ...[
            const SizedBox(height: 8),
            _Evidence(result: _state.result!),
          ],
          if (_permissions.allGranted) ...[
            const SizedBox(height: 20),
            _enrolledVoices(context),
            const SizedBox(height: 20),
            _demo(context),
            const SizedBox(height: 20),
            _captureTest(context),
          ],
          const SizedBox(height: 24),
          _history(context),
        ],
      ),
    );
  }

  // --- setup -----------------------------------------------------------------

  Widget _setup(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Finish setup', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              const Text(
                'SatyaCheck cannot screen calls until all three are allowed.',
                style: TextStyle(fontSize: 13, color: Colors.white70),
              ),
              const SizedBox(height: 12),
              _PermissionRow(
                label: 'Microphone',
                detail: 'Listens to the call to check the voice',
                granted: _permissions.microphone,
              ),
              _PermissionRow(
                label: 'Phone state',
                detail: 'Knows when a call starts and ends',
                granted: _permissions.phoneState,
              ),
              _PermissionRow(
                label: 'Display over other apps',
                detail: 'Shows the result while you are still on the call',
                granted: _permissions.overlay,
              ),
              const SizedBox(height: 12),
              if (!_permissions.microphone || !_permissions.phoneState)
                FilledButton(
                  onPressed: () async {
                    await _bridge.requestPermissions();
                    await _refresh();
                  },
                  child: const Text('Allow microphone and phone access'),
                ),
              if (!_permissions.overlay)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: OutlinedButton(
                    // Opens a Settings screen rather than a dialog; the app is backgrounded
                    // and didChangeAppLifecycleState re-checks on return.
                    onPressed: () => _bridge.requestOverlayPermission(),
                    child: const Text('Allow display over other apps'),
                  ),
                ),
            ],
          ),
        ),
      );

  Widget _backendOffline() => Card(
        color: const Color(0xFF3F2D1A),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Cannot reach the screening server',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 6),
              Text(
                'Tried ${_api.baseUrl}. Check the phone and the server are on the same '
                'Wi-Fi, and that the server is running.',
                style: const TextStyle(fontSize: 13, color: Colors.white70),
              ),
              const SizedBox(height: 10),
              OutlinedButton(onPressed: _refresh, child: const Text('Try again')),
            ],
          ),
        ),
      );

  // --- enrolled voices -------------------------------------------------------

  /// Who the app can recognise.
  ///
  /// Worth showing prominently: until somebody is enrolled, *every* caller is grey, and
  /// that looks like the app not working rather than the app behaving correctly.
  Widget _enrolledVoices(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Known voices',
                      style: Theme.of(context).textTheme.titleMedium),
                  TextButton.icon(
                    onPressed: _openEnroll,
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Add'),
                  ),
                ],
              ),
              if (_enrolled.isEmpty)
                const Text(
                  'Nobody enrolled yet. Until a voice is added, every caller shows as '
                  'unverified — which is correct, but nothing can be confirmed as genuine.',
                  style: TextStyle(fontSize: 12, color: Colors.white60),
                )
              else
                for (final person in _enrolled)
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: const CircleAvatar(
                      radius: 14,
                      backgroundColor: Color(0xFF16A34A),
                      child: Icon(Icons.person, size: 16, color: Colors.white),
                    ),
                    title: Text(person.name),
                    subtitle: Text(person.relation,
                        style: const TextStyle(fontSize: 12)),
                  ),
            ],
          ),
        ),
      );

  // --- capture test ----------------------------------------------------------

  /// Runs the whole pipeline without waiting for someone to ring the phone.
  ///
  /// Same service, same speakerphone forcing, same 9-second windows, same backend — only
  /// the telephony trigger is missing. That makes it the way to verify capture works on a
  /// given handset, and the fallback if a live call misbehaves during a demo.
  /// The walkthrough a judge sees: three callers, one tap each.
  ///
  /// Ordered genuine -> clone -> stranger on purpose. A green light alone proves nothing;
  /// what proves something is the same voice coming back red once it has been cloned, and
  /// the number underneath saying why.
  Widget _demo(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Demo callers', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              const Text(
                'Each one is screened by the real backend — same models, same scoring, '
                'same evidence as a live call.',
                style: TextStyle(fontSize: 12, color: Colors.white70),
              ),
              const SizedBox(height: 14),
              _demoButton(
                context,
                label: 'Friend calling',
                subtitle: 'Enrolled voice, ordinary conversation',
                asset: 'assets/demo/genuine.wav',
                colour: const Color(0xFF16A34A),
                icon: Icons.verified_user,
              ),
              const SizedBox(height: 10),
              _demoButton(
                context,
                label: 'Friend calling — cloned',
                subtitle: 'Same voice, AI clone, asks for ₹40,000',
                asset: 'assets/demo/clone.wav',
                colour: const Color(0xFFDC2626),
                icon: Icons.record_voice_over,
              ),
              const SizedBox(height: 10),
              _demoButton(
                context,
                label: 'Unknown number',
                subtitle: 'Stranger running a delivery scam',
                asset: 'assets/demo/stranger.wav',
                colour: const Color(0xFFD97706),
                icon: Icons.phone_callback,
              ),
            ],
          ),
        ),
      );

  Widget _demoButton(
    BuildContext context, {
    required String label,
    required String subtitle,
    required String asset,
    required Color colour,
    required IconData icon,
  }) =>
      InkWell(
        onTap: _screening ? null : () => _runDemo(asset, label),
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: colour.withValues(alpha: 0.55), width: 1.5),
          ),
          child: Row(
            children: [
              Icon(icon, color: colour, size: 26),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label,
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 2),
                    Text(subtitle,
                        style: const TextStyle(
                            fontSize: 12, color: Colors.white60)),
                  ],
                ),
              ),
              if (_screening)
                const SizedBox(
                  height: 18,
                  width: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                const Icon(Icons.play_arrow, color: Colors.white38),
            ],
          ),
        ),
      );

  Future<void> _runDemo(String asset, String label) async {
    setState(() => _screening = true);
    try {
      await _session.screenBundledClip(asset, label);
    } finally {
      if (mounted) setState(() => _screening = false);
    }
  }

  Widget _captureTest(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Test without a call',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              const Text(
                'Starts listening now. Speakerphone will turn on. Play a scam clip or '
                'speak for 15 seconds, then stop.',
                style: TextStyle(fontSize: 12, color: Colors.white70),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: FilledButton.tonal(
                      onPressed: () => _session.startManualCapture(),
                      child: const Text('Start listening'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => _session.stopManualCapture(),
                      child: const Text('Stop'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      );

  // --- history ---------------------------------------------------------------

  Widget _history(BuildContext context) {
    final calls = _session.history;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Recent calls', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (calls.isEmpty)
          const Text('No calls screened yet.',
              style: TextStyle(fontSize: 13, color: Colors.white54)),
        for (final call in calls)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: CircleAvatar(
              radius: 6,
              backgroundColor: _signalColors[call.signal],
            ),
            title: Text(call.number ?? 'Unknown number'),
            subtitle: Text(
              call.result == null
                  ? (call.error ?? 'Not scored')
                  : '${call.result!.band.name} · trust ${call.result!.trustScore.round()}',
              style: const TextStyle(fontSize: 12),
            ),
            trailing: Text(
              TimeOfDay.fromDateTime(call.startedAt).format(context),
              style: const TextStyle(fontSize: 12, color: Colors.white54),
            ),
          ),
      ],
    );
  }
}

/// The big status card — what the user reads from across the room.
class _VerdictCard extends StatelessWidget {
  const _VerdictCard({required this.state, required this.ready});

  final CallSessionState state;
  final bool ready;

  @override
  Widget build(BuildContext context) {
    final result = state.result;
    final colour = _signalColors[state.signal]!;

    String headline;
    String detail;

    switch (state.phase) {
      case CallPhase.idle:
        headline = ready ? 'Watching for calls' : 'Not ready';
        detail = ready
            ? 'The next call will be screened automatically.'
            : 'Finish setup below to start screening.';
        break;
      case CallPhase.ringing:
        headline = 'Incoming call';
        detail = state.number ?? 'Screening starts when you answer.';
        break;
      case CallPhase.screening:
        headline = result == null ? 'Checking…' : _headlineFor(result);
        detail = result == null
            ? (state.detail ?? 'Listening. ${state.chunksSent} clip(s) sent.')
            : _detailFor(result);
        break;
      case CallPhase.done:
        headline = result == null ? 'Call ended' : _headlineFor(result);
        detail = result == null ? 'Nothing was scored.' : _detailFor(result);
        break;
      case CallPhase.failed:
        headline = 'Could not screen';
        detail = state.detail ?? 'The call was not checked.';
        break;
    }

    return Card(
      color: state.phase == CallPhase.idle ? null : colour.withValues(alpha: 0.22),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colour, width: 2),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(headline,
                // Large type: CLAUDE.md asks for something readable from three metres.
                style: Theme.of(context)
                    .textTheme
                    .headlineSmall
                    ?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Text(detail, style: Theme.of(context).textTheme.bodyMedium),
            if (result != null && result.transcript.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('“${result.transcript}”',
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 13, fontStyle: FontStyle.italic, color: Colors.white70)),
            ],
          ],
        ),
      ),
    );
  }

  String _headlineFor(ScreeningResult r) {
    switch (r.signal) {
      case Signal.green:
        return r.matchedPersonName == null
            ? 'Verified caller'
            : 'Verified: ${r.matchedPersonName}';
      case Signal.amber:
        return 'Check before you act';
      case Signal.red:
        return 'Likely scam';
      case Signal.grey:
        // Never "suspicious". A stranger calling is the normal case, and most of them are
        // legitimate — a real bank, a delivery driver, a doctor.
        return 'Unverified caller';
    }
  }

  String _detailFor(ScreeningResult r) {
    final warning = r.vernacularWarning;
    if (warning != null && warning.trim().isNotEmpty) return warning;
    if (r.recommendedActions.isNotEmpty) return r.recommendedActions.first;
    return r.signal == Signal.grey
        ? 'Nobody enrolled matched this voice. That is normal for a stranger.'
        : 'Trust ${r.trustScore.round()} out of 100.';
  }
}

/// The reason codes behind the score — the "why", with citations.
class _Evidence extends StatelessWidget {
  const _Evidence({required this.result});

  final ScreeningResult result;

  @override
  Widget build(BuildContext context) {
    final evidence = result.evidence;
    if (evidence.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Why', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        for (final code in evidence)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 4, right: 10),
                  child: Icon(_iconFor(code.signal), size: 16, color: Colors.white54),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(code.explanation, style: const TextStyle(fontSize: 13)),
                      if (code.citationTitle != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                            'Source: ${code.citationTitle}',
                            style: const TextStyle(fontSize: 11, color: Colors.white38),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  IconData _iconFor(String signal) {
    switch (signal) {
      case 'identity':
        return Icons.person_outline;
      case 'authenticity':
        return Icons.graphic_eq;
      case 'intent':
        return Icons.chat_bubble_outline;
      default:
        return Icons.info_outline;
    }
  }
}

class _PermissionRow extends StatelessWidget {
  const _PermissionRow({
    required this.label,
    required this.detail,
    required this.granted,
  });

  final String label;
  final String detail;
  final bool granted;

  @override
  Widget build(BuildContext context) => ListTile(
        dense: true,
        contentPadding: EdgeInsets.zero,
        leading: Icon(
          granted ? Icons.check_circle : Icons.radio_button_unchecked,
          color: granted ? const Color(0xFF16A34A) : Colors.white38,
        ),
        title: Text(label),
        subtitle: Text(detail, style: const TextStyle(fontSize: 12)),
      );
}
