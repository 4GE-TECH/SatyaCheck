import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'api_client.dart';
import 'calls_screen.dart';
import 'models.dart';
import 'native_bridge.dart';
import 'enroll_screen.dart';
import 'result_screen.dart';
import 'sign_in_screen.dart';
import 'theme.dart';
import 'voice_capture.dart';
import 'widgets.dart';

void main() => runApp(const SatyaCheckApp());

class SatyaCheckApp extends StatefulWidget {
  const SatyaCheckApp({super.key, this.api});
  final ApiClient? api;
  @override
  State<SatyaCheckApp> createState() => _SatyaCheckAppState();
}

class _SatyaCheckAppState extends State<SatyaCheckApp> {
  ThemeMode _mode = ThemeMode.system;
  late final ApiClient _api = widget.api ?? ApiClient();
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'SatyaCheck',
        debugShowCheckedModeBanner: false,
        theme: satyaTheme(Brightness.light),
        darkTheme: satyaTheme(Brightness.dark),
        themeMode: _mode,
        home: AuthGate(
          auth: _api.auth,
          child: HomePage(api: _api, themeMode: _mode, onTheme: (mode) => setState(() => _mode = mode)),
        ),
      );
}

const _examples = [
  ('assets/demo/genuine.wav', 'Familiar voice', 'An enrolled family member speaking normally'),
  ('assets/demo/clone.wav', 'Synthetic voice', 'A cloned voice making an urgent request'),
  ('assets/demo/stranger.wav', 'Unknown caller', 'Someone who is not enrolled'),
];

const _tabs = [
  (Icons.graphic_eq_rounded, 'Check'),
  (Icons.phone_in_talk_outlined, 'Calls'),
  (Icons.people_alt_outlined, 'Voices'),
  (Icons.history_rounded, 'Recent'),
  (Icons.tune_rounded, 'Setup'),
];

class HomePage extends StatefulWidget {
  const HomePage({super.key, this.api, required this.themeMode, required this.onTheme});
  final ApiClient? api;
  final ThemeMode themeMode;
  final ValueChanged<ThemeMode> onTheme;
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver {
  late final ApiClient _api = widget.api ?? ApiClient();

  /// Created the first time the Calls tab opens, then kept running so calls are not missed
  /// while another tab is showing. The feed is live only: nothing is replayed later.
  LiveFeedController? _feed;
  final _bridge = NativeBridge.instance;
  final List<CallRecord> _history = [];
  int _destination = 0, _refreshId = 0;
  bool? _connected;
  bool _refreshing = false, _busy = false;
  Permissions _permissions = Permissions.none;
  List<EnrolledPerson> _people = [];
  String? _peopleError, _error, _selectedPath;

  /// "Who's calling?" for the selected recording: a claim the voice is checked against.
  String? _claimedId;
  String _selectedLabel = 'Selected recording';
  Float32List? _peaks;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _bridge.listen();
    unawaited(_refresh());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _feed?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_refresh());
  }

  Future<void> _refresh() async {
    final id = ++_refreshId;
    if (mounted) setState(() => _refreshing = true);
    try {
      final values = await Future.wait<Object>([_bridge.permissions(), _api.ping()]);
      final permissions = values[0] as Permissions, connected = values[1] as bool;
      final people = connected ? await _api.persons() : <EnrolledPerson>[];
      if (!mounted || id != _refreshId) return;
      setState(() {
        _permissions = permissions;
        _connected = connected;
        _refreshing = false;
        _peopleError = connected ? _api.peopleError : 'Connect to the service to load known voices.';
        if (_peopleError == null) _people = people;
      });
    } catch (error) {
      debugPrint('SatyaCheck setup refresh: $error');
      if (mounted && id == _refreshId) {
        setState(() {
          _refreshing = false;
          _connected = false;
          _peopleError = 'Connection and permission status are unavailable. Please retry.';
        });
      }
    }
  }

  Future<void> _enroll() async {
    final name = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => EnrollScreen(api: _api)));
    if (!mounted) return;
    if (name != null) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$name’s voice is enrolled')));
    await _refresh();
  }

  Future<void> _select(String path, String label) async {
    setState(() {
      _selectedPath = path;
      _selectedLabel = label;
      _claimedId = null;
      _error = null;
      _peaks = null;
    });
    try {
      final peaks = wavPeaks(await File(path).readAsBytes());
      if (mounted && _selectedPath == path) setState(() => _peaks = peaks);
    } catch (error) {
      debugPrint('SatyaCheck waveform preview: $error');
    }
  }

  Future<void> _pick() async {
    try {
      final path = await _bridge.pickAudio();
      if (mounted && path != null) await _select(path, 'Uploaded recording');
    } catch (error) {
      debugPrint('SatyaCheck audio picker: $error');
      if (mounted) {
        setState(() => _error = error is PlatformException ? error.message ?? 'Could not open the recording.' : 'Could not select audio. Please try again.');
      }
    }
  }

  Future<void> _record() async {
    final path = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const CaptureScreen()));
    if (mounted && path != null) await _select(path, 'Microphone recording');
  }

  Future<void> _check({String? asset, String? label}) async {
    if (_busy || (asset == null && _selectedPath == null)) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final record = CallRecord(startedAt: DateTime.now(), number: label ?? _selectedLabel);
    try {
      Uint8List bytes;
      if (asset != null) {
        final data = await rootBundle.load(asset);
        bytes = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
        if (mounted) setState(() => _peaks = wavPeaks(bytes));
      } else {
        final file = File(_selectedPath!);
        final size = await file.length();
        if (size == 0 || size > 50 * 1024 * 1024) throw const FormatException('Choose a non-empty recording smaller than 50 MB.');
        bytes = await file.readAsBytes();
      }
      final claim = asset == null && _people.any((person) => person.personId == _claimedId) ? _claimedId : null;
      final result = await _api.screenWav(bytes, filename: asset == null ? 'recording.audio' : 'example.wav', claimedIdentity: claim);
      if (!mounted) return;
      if (result == null) {
        record.error = _api.screeningError ?? 'No result was returned. Please try again.';
        setState(() {
          _error = record.error;
          _history.insert(0, record);
        });
      } else {
        record.result = result;
        setState(() {
          _history.insert(0, record);
          _selectedPath = null;
          _peaks = null;
        });
        if (_history.length > 30) _history.removeLast();
        unawaited(Navigator.push(context, MaterialPageRoute(builder: (_) => ResultScreen(result: result, label: record.number ?? 'Screening result'))));
      }
    } catch (error) {
      debugPrint('SatyaCheck audio check: $error');
      if (mounted) setState(() => _error = error is FormatException ? error.message : 'Could not read this recording. Choose it again or record a new sample.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _navigate(int destination) {
    if (destination == 1 && _feed == null) {
      _feed = LiveFeedController(_api);
      unawaited(_feed!.connect());
    }
    setState(() => _destination = destination);
  }

  @override
  Widget build(BuildContext context) {
    final content = switch (_destination) {
      1 => CallsView(feed: _feed!, api: _api, padding: _pagePadding),
      2 => _voices(),
      3 => _recent(),
      4 => _setup(),
      _ => _home(),
    };
    return PopScope(
      canPop: _destination == 0,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _navigate(0);
      },
      child: Scaffold(
        body: Stack(children: [
          // A whisper behind the header: decorative, never competing with text.
          const Positioned(top: 0, left: 0, right: 0, child: Opacity(opacity: 0.32, child: AmbientField(height: 460))),
          SafeArea(
            bottom: false,
            child: Column(children: [
              _TopBar(connected: _connected, refreshing: _refreshing, onRefresh: _refresh),
              Expanded(
                child: Align(
                  alignment: Alignment.topCenter,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 720),
                    child: AnimatedSwitcher(
                      duration: context.calmMotion ? Duration.zero : const Duration(milliseconds: 420),
                      switchInCurve: Curves.easeOutExpo,
                      transitionBuilder: (child, animation) => FadeTransition(
                        opacity: animation,
                        child: SlideTransition(position: Tween(begin: const Offset(0, 0.025), end: Offset.zero).animate(animation), child: child),
                      ),
                      child: KeyedSubtree(key: ValueKey(_destination), child: content),
                    ),
                  ),
                ),
              ),
            ]),
          ),
        ]),
        bottomNavigationBar: _GlassTabs(index: _destination, onSelect: _navigate),
      ),
    );
  }

  EdgeInsets get _pagePadding => const EdgeInsets.fromLTRB(20, 8, 20, 40);

  Widget _heading(String title, String detail) {
    final theme = Theme.of(context);
    return Reveal(
      child: Padding(
        padding: const EdgeInsets.only(top: 18, bottom: 26),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Semantics(header: true, child: Text(title, style: theme.textTheme.displayMedium)),
          const SizedBox(height: 12),
          Text(detail, style: theme.textTheme.bodyLarge),
        ]),
      ),
    );
  }

  Widget _home() {
    final p = context.palette, theme = Theme.of(context);
    final headline = theme.textTheme.displayLarge!;
    return ListView(key: const PageStorageKey('check'), padding: _pagePadding, children: [
      Reveal(
        child: Padding(
          padding: const EdgeInsets.only(top: 22),
          child: Semantics(
            header: true,
            label: 'Is this voice really who it says it is?',
            child: ExcludeSemantics(
              child: Text.rich(TextSpan(style: headline, children: [
                const TextSpan(text: 'Is this voice '),
                WidgetSpan(alignment: PlaceholderAlignment.middle, child: Padding(padding: const EdgeInsets.symmetric(horizontal: 2), child: InlineWave(height: headline.fontSize! * 0.66))),
                const TextSpan(text: ' really who it says it is?'),
              ])),
            ),
          ),
        ),
      ),
      const SizedBox(height: 16),
      Reveal(
        delay: const Duration(milliseconds: 120),
        child: Text('Choose a call recording or voice note. SatyaCheck checks who is speaking, whether the voice is synthetic and what is being asked.', style: theme.textTheme.bodyLarge),
      ),
      const SizedBox(height: 20),
      if (_connected == false) ...[
        _OfflineStrip(onReconnect: _refreshing ? null : _refresh),
        const SizedBox(height: 14),
      ],
      Reveal(delay: const Duration(milliseconds: 200), child: _composer()),
      if (_error != null) Padding(padding: const EdgeInsets.only(top: 16), child: InfoMessage(_error!, error: true)),
      const SizedBox(height: 48),
      Text('Three questions, answered together', style: theme.textTheme.headlineMedium),
      const SizedBox(height: 8),
      Text('Each is checked on its own, then combined into one trust score with the evidence behind it.', style: theme.textTheme.bodyMedium),
      const SizedBox(height: 18),
      const _QuestionPager(),
      const SizedBox(height: 48),
      Text('A real emergency asks you to check. A scam asks you not to.', style: theme.textTheme.headlineLarge?.copyWith(height: 1.12)),
      const SizedBox(height: 10),
      Text('SatyaCheck listens for both, and never calls anyone a fraud.', style: theme.textTheme.bodyLarge),
      const SizedBox(height: 48),
      Text('Try a bundled example', style: theme.textTheme.headlineSmall),
      const SizedBox(height: 6),
      Text('Real recordings, checked by your configured service.', style: theme.textTheme.bodySmall),
      const SizedBox(height: 14),
      for (final example in _examples)
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: _ExampleTile(title: example.$2, story: example.$3, enabled: !_busy, onTap: () => _check(asset: example.$1, label: 'Example · ${example.$2}')),
        ),
      const SizedBox(height: 16),
      InfoMessage('On a live call? Calls routed through Exotel are screened on the server: open Calls to watch them. Otherwise use a separate device near the speaker, because Android gives other apps silence during a cellular call on this handset.', tone: p.voice1),
    ]);
  }

  Widget _composer() {
    final p = context.palette, theme = Theme.of(context);
    final ready = _selectedPath != null;
    return Bezel(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Container(
            decoration: BoxDecoration(color: p.raise, borderRadius: BorderRadius.circular(22), border: Border.all(color: p.line)),
            clipBehavior: Clip.antiAlias,
            child: Stack(children: [
              VoiceStage(peaks: _peaks, scanning: _busy, height: 210),
              Positioned.fill(
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 300),
                      child: _busy
                          ? Semantics(
                              key: const ValueKey('busy'),
                              liveRegion: true,
                              child: Column(mainAxisSize: MainAxisSize.min, children: [
                                Text('Listening to the recording…', style: theme.textTheme.titleMedium),
                                const SizedBox(height: 6),
                                Text('Identity, authenticity and intent run together.', style: theme.textTheme.bodySmall),
                              ]),
                            )
                          : ready
                              ? _FileChip(key: const ValueKey('file'), label: _selectedLabel, onRemove: () => setState(() { _selectedPath = null; _peaks = null; }))
                              : Text(key: const ValueKey('idle'), 'Choose a recording, or record nearby', style: theme.textTheme.titleMedium),
                    ),
                  ),
                ),
              ),
            ]),
          ),
          const SizedBox(height: 14),
          Row(children: [
            Expanded(child: _SourceTile(label: 'Choose audio', icon: Icons.upload_rounded, onTap: _busy ? null : _pick)),
            const SizedBox(width: 10),
            Expanded(child: _SourceTile(label: 'Record nearby', icon: Icons.mic_none_rounded, onTap: _busy ? null : _record)),
          ]),
          if (_selectedPath != null && _people.isNotEmpty) ...[
            const SizedBox(height: 14),
            _CallerPicker(people: _people, value: _claimedId, enabled: !_busy, onChanged: (id) => setState(() => _claimedId = id)),
          ],
          const SizedBox(height: 10),
          PillButton(
            label: _busy ? 'Checking…' : 'Check this recording',
            trailing: Icons.arrow_forward_rounded,
            large: true,
            expand: true,
            busy: _busy,
            onPressed: ready ? _check : null,
          ),
          const SizedBox(height: 12),
          Text('Only check audio you have permission to use. It is sent to your configured service for analysis.', style: theme.textTheme.bodySmall, textAlign: TextAlign.center),
        ]),
      ),
    );
  }

  Widget _voices() {
    final p = context.palette, theme = Theme.of(context);
    return ListView(key: const PageStorageKey('voices'), padding: _pagePadding, children: [
      _heading('Known voices', 'Enroll the people who might call. Anyone not enrolled stays unverified, which is normal and not a warning.'),
      PillButton(label: 'Add a known voice', icon: Icons.person_add_alt_1_rounded, trailing: Icons.arrow_forward_rounded, expand: true, onPressed: _busy ? null : _enroll),
      const SizedBox(height: 22),
      if (_refreshing)
        const LinearProgressIndicator()
      else if (_peopleError != null)
        InfoMessage(_peopleError!, error: true, action: TextButton(onPressed: _refresh, child: const Text('Try again')))
      else if (_people.isEmpty)
        Panel(
          child: Column(children: [
            Icon(Icons.people_alt_outlined, size: 38, color: p.voice3),
            const SizedBox(height: 14),
            Text('No one enrolled yet', style: theme.textTheme.titleLarge),
            const SizedBox(height: 8),
            Text('Start with the people most likely to call: children, parents, a spouse.', textAlign: TextAlign.center, style: theme.textTheme.bodyMedium),
          ]),
        )
      else
        for (var i = 0; i < _people.length; i++)
          Reveal(
            delay: Duration(milliseconds: 60 * i),
            child: Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Panel(
                padding: const EdgeInsets.all(14),
                child: Row(children: [
                  Container(
                    width: 50,
                    height: 50,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(borderRadius: BorderRadius.circular(17), gradient: LinearGradient(colors: [p.voice1, p.voice2])),
                    child: Text(_people[i].name.isEmpty ? '?' : _people[i].name.characters.first.toUpperCase(), style: const TextStyle(fontFamily: sans, fontSize: 19, fontWeight: FontWeight.w700, color: Colors.white)),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(_people[i].name, style: theme.textTheme.titleMedium),
                      Text(_people[i].relation, style: theme.textTheme.bodyMedium),
                    ]),
                  ),
                  Icon(Icons.verified_user_outlined, color: p.muted),
                ]),
              ),
            ),
          ),
      const SizedBox(height: 18),
      const InfoMessage('A voice match is one piece of evidence, not proof. Confirm unexpected requests with a call back on a number you trust.'),
    ]);
  }

  Widget _recent() {
    final p = context.palette, theme = Theme.of(context);
    return ListView(key: const PageStorageKey('recent'), padding: _pagePadding, children: [
      _heading('Recent checks', 'From this app session. Open one to see its evidence or copy a summary.'),
      if (_history.isEmpty)
        Panel(
          child: Column(children: [
            Icon(Icons.history_rounded, size: 38, color: p.voice3),
            const SizedBox(height: 14),
            Text('Nothing checked yet', style: theme.textTheme.titleLarge),
            const SizedBox(height: 8),
            Text('Completed checks appear here with their evidence.', textAlign: TextAlign.center, style: theme.textTheme.bodyMedium),
            const SizedBox(height: 14),
            PillButton(label: 'Check audio', kind: PillKind.secondary, trailing: Icons.arrow_forward_rounded, onPressed: () => _navigate(0)),
          ]),
        )
      else
        for (var i = 0; i < _history.length; i++)
          Reveal(
            delay: Duration(milliseconds: 60 * i),
            child: Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Material(
                color: p.panel,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24), side: BorderSide(color: p.line)),
                clipBehavior: Clip.antiAlias,
                child: InkWell(
                  onTap: _history[i].result == null
                      ? null
                      : () => Navigator.push(context, MaterialPageRoute(builder: (_) => ResultScreen(result: _history[i].result!, label: _history[i].number ?? 'Screening result'))),
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Row(children: [
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(_history[i].number ?? 'Audio recording', style: theme.textTheme.titleMedium),
                          const SizedBox(height: 4),
                          Text(TimeOfDay.fromDateTime(_history[i].startedAt).format(context), style: theme.textTheme.bodySmall),
                          const SizedBox(height: 10),
                          if (_history[i].result != null) VerdictBadge(_history[i].result!.band) else Text(_history[i].error ?? 'Not checked', style: theme.textTheme.bodyMedium?.copyWith(color: p.danger)),
                        ]),
                      ),
                      if (_history[i].result != null && _history[i].result!.band != TrustBand.insufficient)
                        Text('${_history[i].result!.trustScore.round()}', style: TextStyle(fontFamily: sans, fontSize: 34, fontWeight: FontWeight.w300, color: bandColor(context, _history[i].result!.band))),
                      if (_history[i].result != null) Icon(Icons.chevron_right_rounded, color: p.muted),
                    ]),
                  ),
                ),
              ),
            ),
          ),
    ]);
  }

  Widget _setup() {
    final p = context.palette, theme = Theme.of(context);
    Widget group(String title, List<Widget> children) => Padding(
          padding: const EdgeInsets.only(bottom: 14),
          child: Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: theme.textTheme.titleLarge), const SizedBox(height: 12), ...children])),
        );
    return ListView(key: const PageStorageKey('setup'), padding: _pagePadding, children: [
      _heading('Setup', 'Connection, appearance and what happens to your audio.'),
      group('Screening service', [
        Row(children: [
          Container(width: 10, height: 10, decoration: BoxDecoration(shape: BoxShape.circle, color: _connected == true ? p.safe : _connected == false ? p.caution : p.neutral)),
          const SizedBox(width: 12),
          Expanded(child: Text(_refreshing ? 'Checking connection…' : _connected == true ? 'Service connected' : 'Service unavailable', style: theme.textTheme.titleMedium)),
          IconButton(tooltip: 'Refresh connection', onPressed: _refreshing ? null : _refresh, icon: const Icon(Icons.refresh_rounded)),
        ]),
        const SizedBox(height: 6),
        Text('Analysis needs a connection to your configured service. No result is available when it cannot be reached.', style: theme.textTheme.bodyMedium),
        const SizedBox(height: 10),
        SelectableText(_api.baseUrl, style: TextStyle(fontFamily: mono, fontSize: 13.5, color: p.muted)),
      ]),
      if (_api.auth.enabled)
        group('Account', [
          Text('Signed in as ${_api.auth.email ?? 'your account'}', style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          Text('Known voices and reports belong to this account. Nobody else signed in to the service can see them.', style: theme.textTheme.bodyMedium),
          const SizedBox(height: 12),
          PillButton(label: 'Sign out', kind: PillKind.secondary, icon: Icons.logout_rounded, onPressed: _api.auth.signOut),
        ]),
      group('Appearance', [
        SegmentedButton<ThemeMode>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: ThemeMode.system, label: Text('Device')),
            ButtonSegment(value: ThemeMode.light, label: Text('Light')),
            ButtonSegment(value: ThemeMode.dark, label: Text('Dark')),
          ],
          selected: {widget.themeMode},
          onSelectionChanged: (value) => widget.onTheme(value.first),
        ),
      ]),
      group('Microphone', [
        Text(_permissions.microphone ? 'Allowed. Used only when you start a recording.' : 'Needed only for recording a voice. Choosing saved audio does not need it.', style: theme.textTheme.bodyMedium),
        const SizedBox(height: 8),
        Text('Phone and overlay permissions do not enable same-device cellular call recording.', style: theme.textTheme.bodySmall),
      ]),
      group('Your audio and evidence', [
        Text('Recordings are sent to your configured screening service. Ask its operator about access, retention and deletion. Recent checks are held in memory for this app session.', style: theme.textTheme.bodyMedium),
        const SizedBox(height: 10),
        Text('Unverified is neutral. Insufficient audio has no score. Even a familiar voice is a reason to verify an unexpected request.', style: theme.textTheme.bodySmall),
      ]),
    ]);
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.connected, required this.refreshing, required this.onRefresh});
  final bool? connected;
  final bool refreshing;
  final VoidCallback onRefresh;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final label = refreshing ? 'Connecting' : connected == true ? 'Online' : connected == false ? 'Offline' : 'Connecting';
    final color = connected == true ? p.safe : connected == false ? p.caution : p.neutral;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 10, 14, 4),
      child: Row(children: [
        Container(
          width: 34,
          height: 34,
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(borderRadius: BorderRadius.circular(11), boxShadow: [BoxShadow(color: p.voice1.withValues(alpha: 0.5), blurRadius: 16, spreadRadius: -6, offset: const Offset(0, 6))]),
          child: Image.asset('assets/brand/satyacheck-logo.jpg', fit: BoxFit.cover),
        ),
        const SizedBox(width: 10),
        Text('SatyaCheck', style: TextStyle(fontFamily: sans, fontSize: 18, fontWeight: FontWeight.w700, letterSpacing: -0.6, color: p.text)),
        const Spacer(),
        Semantics(
          button: true,
          label: 'Service ${label.toLowerCase()}. Refresh connection',
          child: InkWell(
            borderRadius: BorderRadius.circular(999),
            onTap: refreshing ? null : onRefresh,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(color: p.panel.withValues(alpha: 0.7), borderRadius: BorderRadius.circular(999), border: Border.all(color: p.line2)),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle, boxShadow: [BoxShadow(color: color.withValues(alpha: 0.35), spreadRadius: 3)])),
                const SizedBox(width: 8),
                ExcludeSemantics(child: Text(label, style: TextStyle(fontFamily: sans, fontSize: 13.5, fontWeight: FontWeight.w600, color: p.text2))),
              ]),
            ),
          ),
        ),
      ]),
    );
  }
}

/// The standard Material 3 navigation bar, themed into the listening room.
class _GlassTabs extends StatelessWidget {
  const _GlassTabs({required this.index, required this.onSelect});
  final int index;
  final ValueChanged<int> onSelect;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return NavigationBarTheme(
      data: NavigationBarThemeData(
        backgroundColor: p.panel.withValues(alpha: p.dark ? 0.94 : 0.97),
        surfaceTintColor: Colors.transparent,
        indicatorColor: p.soft(p.accent),
        indicatorShape: const StadiumBorder(),
        height: 72,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
              size: 24,
              color: states.contains(WidgetState.selected) ? (p.dark ? const Color(0xFFA7AFFF) : p.accent) : p.muted,
            )),
        labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
              fontFamily: sans,
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
              color: states.contains(WidgetState.selected) ? p.text : p.muted,
            )),
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(border: Border(top: BorderSide(color: p.line))),
        child: NavigationBar(
          selectedIndex: index,
          onDestinationSelected: onSelect,
          animationDuration: context.calmMotion ? Duration.zero : const Duration(milliseconds: 420),
          destinations: [for (final t in _tabs) NavigationDestination(icon: Icon(t.$1), label: t.$2)],
        ),
      ),
    );
  }
}

/// "Who's calling?" — pick the person the caller said they were. The voice is checked
/// against theirs. A claim narrows the check; it is never proof either way.
class _CallerPicker extends StatelessWidget {
  const _CallerPicker({required this.people, required this.value, required this.enabled, required this.onChanged});
  final List<EnrolledPerson> people;
  final String? value;
  final bool enabled;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      DropdownButtonFormField<String?>(
        initialValue: value,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Who’s calling? (optional)'),
        items: [
          const DropdownMenuItem<String?>(value: null, child: Text('Not sure, or someone new')),
          for (final person in people)
            DropdownMenuItem<String?>(
              value: person.personId,
              child: Text(person.relation.isEmpty ? person.name : '${person.name} (${person.relation})', overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: enabled ? onChanged : null,
      ),
      const SizedBox(height: 6),
      Text('If the caller said who they are, pick them. Their voice is checked against that person’s. It is a check, not proof.',
          style: theme.textTheme.bodySmall),
    ]);
  }
}

class _FileChip extends StatelessWidget {
  const _FileChip({super.key, required this.label, required this.onRemove});
  final String label;
  final VoidCallback onRemove;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 6, 6, 6),
      decoration: BoxDecoration(color: p.panel.withValues(alpha: 0.86), borderRadius: BorderRadius.circular(999), border: Border.all(color: p.line2)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.audio_file_outlined, color: p.voice3, size: 20),
        const SizedBox(width: 10),
        Flexible(child: Text('$label ready', overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontSize: 15))),
        const SizedBox(width: 6),
        IconButton(tooltip: 'Remove recording', onPressed: onRemove, icon: const Icon(Icons.close_rounded, size: 18)),
      ]),
    );
  }
}

class _ExampleTile extends StatelessWidget {
  const _ExampleTile({required this.title, required this.story, required this.enabled, required this.onTap});
  final String title, story;
  final bool enabled;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    return Material(
      color: p.panel,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22), side: BorderSide(color: p.line)),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: enabled ? onTap : null,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            Container(width: 44, height: 44, decoration: BoxDecoration(color: p.soft(p.voice1), borderRadius: BorderRadius.circular(15)), child: Icon(Icons.play_arrow_rounded, color: p.voice3)),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: theme.textTheme.titleMedium),
                Text(story, style: theme.textTheme.bodySmall),
              ]),
            ),
            Icon(Icons.arrow_forward_rounded, color: p.muted),
          ]),
        ),
      ),
    );
  }
}

/// The three questions as a swipeable pager, each with its own rule.
class _QuestionPager extends StatefulWidget {
  const _QuestionPager();
  @override
  State<_QuestionPager> createState() => _QuestionPagerState();
}

class _QuestionPagerState extends State<_QuestionPager> {
  final _controller = PageController(viewportFraction: 0.88);
  int _page = 0;
  static const _items = [
    (Icons.fingerprint_rounded, 'Who is speaking?', 'The voice is compared with people you enrolled. A stranger is unverified, not guilty: banks and couriers are strangers too.'),
    (Icons.graphic_eq_rounded, 'Is the voice synthetic?', 'Every moment is scored, so a cloned voice switched in mid-call still shows. Synthetic speech only counts when the request is alarming.'),
    (Icons.forum_outlined, 'What is being asked?', 'Secrecy, urgency and payment demands raise risk. Invitations to verify lower it.'),
  ];

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    return Column(children: [
      SizedBox(
        height: 236,
        child: PageView.builder(
          controller: _controller,
          padEnds: false,
          itemCount: _items.length,
          onPageChanged: (i) => setState(() => _page = i),
          itemBuilder: (context, i) => AnimatedScale(
            scale: i == _page ? 1 : 0.95,
            duration: const Duration(milliseconds: 400),
            curve: Curves.easeOutCubic,
            child: Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Container(
                padding: const EdgeInsets.all(22),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(28),
                  border: Border.all(color: i == _page ? p.line2 : p.line),
                  gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color.alphaBlend(p.voice1.withValues(alpha: i == _page ? 0.16 : 0.06), p.panel), p.panel]),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(_items[i].$1, size: 30, color: p.voice3),
                  const SizedBox(height: 16),
                  Text(_items[i].$2, style: theme.textTheme.headlineSmall),
                  const SizedBox(height: 10),
                  Text(_items[i].$3, style: theme.textTheme.bodyMedium),
                ]),
              ),
            ),
          ),
        ),
      ),
      const SizedBox(height: 14),
      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        for (var i = 0; i < _items.length; i++)
          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            margin: const EdgeInsets.symmetric(horizontal: 4),
            width: i == _page ? 22 : 7,
            height: 7,
            decoration: BoxDecoration(color: i == _page ? p.voice3 : p.line2, borderRadius: BorderRadius.circular(9)),
          ),
      ]),
    ]);
  }
}

/// A one-line offline notice, so the composer's actions stay in the first screen.
class _OfflineStrip extends StatelessWidget {
  const _OfflineStrip({required this.onReconnect});
  final VoidCallback? onReconnect;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 4, 4, 4),
        decoration: BoxDecoration(color: p.soft(p.caution), borderRadius: BorderRadius.circular(999), border: Border.all(color: p.edge(p.caution))),
        child: Row(children: [
          Icon(Icons.cloud_off_rounded, size: 18, color: p.caution),
          const SizedBox(width: 10),
          Expanded(child: Text('Service offline', style: TextStyle(fontFamily: sans, fontSize: 14.5, fontWeight: FontWeight.w500, color: p.text))),
          TextButton(onPressed: onReconnect, child: const Text('Reconnect')),
        ]),
      ),
    );
  }
}

/// An audio source: icon over a full label, so both fit side by side on a phone.
class _SourceTile extends StatelessWidget {
  const _SourceTile({required this.label, required this.icon, required this.onTap});
  final String label;
  final IconData icon;
  final VoidCallback? onTap;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Material(
      color: p.panel2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22), side: BorderSide(color: p.line2)),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 24, color: onTap == null ? p.muted : (p.dark ? const Color(0xFFA7AFFF) : p.accent)),
            const SizedBox(height: 6),
            Text(label, textAlign: TextAlign.center, style: TextStyle(fontFamily: sans, fontSize: 15, fontWeight: FontWeight.w600, color: onTap == null ? p.muted : p.text)),
          ]),
        ),
      ),
    );
  }
}
