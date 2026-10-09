import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'models.dart';
import 'native_bridge.dart';
import 'theme.dart';
import 'widgets.dart';

/// Per-segment synthetic threshold. Mirrors config.CM_SYNTHETIC_THRESHOLD.
const synthThreshold = 0.4;

Map<String, dynamic> _map(Object? value) => value is Map ? value.cast<String, dynamic>() : const {};
List<Map<String, dynamic>> _list(Object? value) => value is List ? value.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList() : const [];
double? _num(Object? value) => value is num && value.isFinite ? value.toDouble() : null;
String _pct(double? v) => v == null ? '—' : '${(v.clamp(0, 1) * 100).round()}%';
String _sec(double? v) => v == null ? '—' : '${v.toStringAsFixed(1)} s';

class _Signal {
  const _Signal(this.icon, this.name, this.finding, this.detail, this.risk, this.weight, this.flag, this.abstains);
  final IconData icon;
  final String name, finding, detail;
  final double risk, weight;
  final FlagMark flag;
  final bool abstains;
}

class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.result, this.label = 'Screening result', this.sample = false});
  final ScreeningResult result;
  final String label;
  final bool sample;

  Map<String, dynamic> get _fusion => _map(result.raw['fusion']);
  Map<String, dynamic> get _spoof => _map(result.raw['spoof']);
  Map<String, dynamic> get _script => _map(result.raw['script']);
  Map<String, dynamic> get _quality => _map(result.raw['quality']);
  bool get _insufficient => result.band == TrustBand.insufficient;

  /// A voiceprint match is trusted only when the voice is not flagged as synthetic or replayed.
  bool get _trustedMatch => result.speakerVerdict == 'match' && _spoof['is_synthetic'] != true && _map(result.raw['speaker'])['is_replay'] != true;

  List<_Signal> _signals(Palette p) {
    final weights = _map(_fusion['weights_used']);
    final authority = result.mode == 'authority_check';
    final timeline = _list(_spoof['timeline']);
    final concerns = _list(_script['incriminating_markers']).length;
    final reassurances = _list(_script['exculpatory_markers']).length;
    final raw = _num(_fusion['authenticity_risk']) ?? 0;
    final effective = _num(_fusion['authenticity_risk_effective']) ?? raw;
    return [
      _Signal(
        Icons.fingerprint_rounded,
        'Identity',
        result.speakerVerdict == 'match'
            ? '${_trustedMatch ? 'Matches' : 'Sounds like'} ${result.matchedPersonName ?? 'an enrolled voice'}'
            : result.speakerVerdict == 'mismatch' ? 'Differs from the claimed person' : 'No enrolled voice matched',
        authority
            ? 'Steps back in this check'
            : result.speakerVerdict == 'match' && !_trustedMatch
                ? 'Weight ${_pct(_num(weights['asv_weight']))} of the score. A synthetic voice can imitate someone you know.'
                : 'Weight ${_pct(_num(weights['asv_weight']))} of the score',
        _num(_fusion['identity_risk']) ?? 0.5,
        _num(weights['asv_weight']) ?? 0,
        result.speakerVerdict == 'mismatch' ? FlagMark.high : result.speakerVerdict == 'match' ? (_trustedMatch ? FlagMark.ok : FlagMark.heldBack) : FlagMark.none,
        authority,
      ),
      _Signal(
        Icons.graphic_eq_rounded,
        'Authenticity',
        timeline.isEmpty
            ? 'No segment evidence returned'
            : _spoof['is_synthetic'] == true ? 'Synthetic for ${_sec(_num(_spoof['max_synth_run_s']))} straight' : 'No sustained synthetic speech',
        (raw - effective).abs() > 0.005
            ? 'Counted at ${_pct(effective)} of ${_pct(raw)}: the request is not alarming'
            : 'Weight ${_pct(_num(weights['cm_weight']))} of the score',
        effective,
        _num(weights['cm_weight']) ?? 0,
        timeline.isEmpty ? FlagMark.none : _spoof['is_synthetic'] == true ? FlagMark.high : FlagMark.ok,
        false,
      ),
      _Signal(
        Icons.forum_outlined,
        'Intent',
        (_script['intent_summary'] as String?) ?? (concerns > 0 ? '$concerns concerning ${concerns == 1 ? 'phrase' : 'phrases'}' : 'Nothing concerning was asked'),
        'Weight ${_pct(_num(weights['text_weight']))} of the score',
        _num(_fusion['intent_risk']) ?? result.scriptRisk,
        _num(weights['text_weight']) ?? 0,
        concerns > 0 ? FlagMark.high : reassurances > 0 ? FlagMark.ok : FlagMark.none,
        false,
      ),
    ];
  }

  String _summary() => [
        if (sample) 'SAMPLE — DEMONSTRATION ONLY',
        'SatyaCheck screening report',
        'Session: ${result.sessionId}',
        'Result: ${bandLabel(result.band)}',
        'Trust score: ${_insufficient ? 'not given (insufficient speech)' : '${result.trustScore.round()}/100, not a probability'}',
        if (result.matchedPersonName != null) 'Matched voice: ${result.matchedPersonName}',
        '',
        'Evidence',
        ...result.evidence.map((e) => '- ${e.explanation}${e.citationUrl == null ? '' : '\n  ${e.citationTitle ?? 'Source'}: ${e.citationUrl}'}'),
        '',
        'Transcript (automatic; may contain errors)',
        result.transcript.isEmpty ? 'Not available' : result.transcript,
        '',
        'Recommended actions',
        ...result.recommendedActions.map((a) => '- ${calm(a)}'),
        '',
        'This is a screening summary, not an official complaint or a determination of fraud.',
      ].join('\n');

  Future<void> _copy(BuildContext context) async {
    try {
      await Clipboard.setData(ClipboardData(text: _summary()));
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Summary copied')));
    } catch (_) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not copy the summary. Please try again.')));
    }
  }

  Future<void> _source(BuildContext context, String url) async {
    try {
      final uri = Uri.tryParse(url);
      if (uri == null || !['http', 'https'].contains(uri.scheme)) return;
      final opened = await NativeBridge.instance.openExternal(url);
      if (!opened && context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open this source.')));
    } catch (_) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open this source.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final tone = bandColor(context, result.band);
    final actions = _insufficient
        ? ['Record more clear speech in a quiet place, then check again.']
        : result.recommendedActions.isEmpty
            ? ['Verify unexpected requests through a phone number you already trust.']
            : result.recommendedActions.map(calm).toList();
    final question = _map(_fusion['challenge_question'])['question_text'] as String?;
    var step = 0;
    Duration next() => Duration(milliseconds: 90 * step++);

    return Scaffold(
      appBar: AppBar(
        title: Text(label, overflow: TextOverflow.ellipsis),
        actions: [IconButton(tooltip: 'Copy summary', onPressed: () => _copy(context), icon: const Icon(Icons.copy_rounded))],
      ),
      body: Stack(children: [
        const Positioned(top: -40, left: 0, right: 0, child: Opacity(opacity: 0.6, child: AmbientField(height: 360))),
        SafeArea(
          child: ListView(padding: const EdgeInsets.fromLTRB(18, 6, 18, 36), children: [
            if (sample) ...[
              const InfoMessage('Labelled sample. This demonstrates a result type and does not describe your audio.'),
              const SizedBox(height: 14),
            ],
            Reveal(
              delay: next(),
              child: Bezel(
                tint: tone,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 26, 24, 26),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    VerdictBadge(result.band, large: true),
                    const SizedBox(height: 18),
                    Semantics(header: true, child: Text(bandHeadline(result.band), style: theme.textTheme.displayMedium)),
                    const SizedBox(height: 14),
                    Text(_insufficient ? (_quality['reason'] as String?) ?? bandSummary(result.band) : bandSummary(result.band), style: theme.textTheme.bodyLarge),
                    if (result.band == TrustBand.verified && result.matchedPersonName != null) ...[
                      const SizedBox(height: 10),
                      Text('Matched voice: ${result.matchedPersonName}', style: theme.textTheme.titleMedium),
                    ],
                    Padding(padding: const EdgeInsets.symmetric(vertical: 22), child: Divider(color: p.line)),
                    if (_insufficient)
                      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('—', style: TextStyle(fontFamily: sans, fontSize: 64, height: 0.9, color: p.neutral)),
                        const SizedBox(height: 10),
                        Text('No score given.', style: theme.textTheme.titleLarge),
                        const SizedBox(height: 4),
                        Text('A number on too little speech would be a guess, so SatyaCheck refuses to give one.', style: theme.textTheme.bodyMedium),
                      ])
                    else
                      _TrustScale(score: result.trustScore, tone: tone, verifiable: result.mode != 'authority_check' && _trustedMatch),
                  ]),
                ),
              ),
            ),
            const SizedBox(height: 14),
            Reveal(
              delay: next(),
              child: Container(
                padding: const EdgeInsets.fromLTRB(22, 22, 22, 22),
                decoration: BoxDecoration(color: p.soft(tone), borderRadius: BorderRadius.circular(28), border: Border.all(color: p.edge(tone))),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  for (var i = 0; i < actions.length; i++)
                    Padding(
                      padding: EdgeInsets.only(bottom: i == actions.length - 1 ? 0 : 10),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        SizedBox(width: 28, child: Text('${i + 1}.', style: TextStyle(fontFamily: mono, fontSize: i == 0 ? 20 : 16, fontWeight: FontWeight.w600, color: tone, height: 1.3))),
                        Expanded(child: Text(actions[i], style: i == 0 ? theme.textTheme.headlineSmall : theme.textTheme.bodyLarge?.copyWith(color: p.text2))),
                      ]),
                    ),
                  if (question != null && question.isNotEmpty) ...[
                    Padding(padding: const EdgeInsets.symmetric(vertical: 18), child: Divider(color: p.edge(tone))),
                    Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon(Icons.help_outline_rounded, color: tone, size: 22),
                      const SizedBox(width: 10),
                      Expanded(child: Text(question, style: theme.textTheme.titleMedium)),
                    ]),
                    const SizedBox(height: 6),
                    Padding(padding: const EdgeInsets.only(left: 32), child: Text('A question only they would know. Pair it with a call back on a saved number.', style: theme.textTheme.bodySmall)),
                  ],
                  if (result.vernacularWarning?.isNotEmpty == true) ...[
                    Padding(padding: const EdgeInsets.symmetric(vertical: 18), child: Divider(color: p.edge(tone))),
                    Text(result.vernacularWarning!, style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w500, height: 1.5)),
                  ],
                ]),
              ),
            ),
            _Section(
              delay: next(),
              title: 'How the score was formed',
              note: 'Three independent checks. Each shows its risk out of 100 and its weight in this check.',
              child: _Fusion(signals: _signals(p), result: result, tone: tone),
            ),
            _Section(
              delay: next(),
              title: 'The recording, moment by moment',
              note: 'Bars are each segment’s synthetic score. The dashed line marks the ${_pct(synthThreshold)} threshold.',
              child: _Timeline(spoof: _spoof, transcript: _map(result.raw['transcript']), script: _script),
            ),
            _Section(
              delay: next(),
              title: 'What was said',
              note: 'Transcribed automatically, so it can contain mistakes.',
              child: _Transcript(text: result.transcript, script: _script),
            ),
            _Section(
              delay: next(),
              title: 'Measurements',
              note: 'Each value against its reference. Below either quality minimum, no score is given.',
              child: _Measurements(quality: _quality, spoof: _spoof),
            ),
            _Section(
              delay: next(),
              title: 'Evidence and sources',
              note: 'Each finding, what was observed, and where the rule comes from.',
              child: _Evidence(result: result, script: _script, onSource: (url) => _source(context, url)),
            ),
            const SizedBox(height: 28),
            PillButton(label: 'Copy summary', icon: Icons.copy_rounded, kind: PillKind.secondary, expand: true, onPressed: () => _copy(context)),
            const SizedBox(height: 18),
            SelectableText('Session ${result.sessionId}', style: TextStyle(fontFamily: mono, fontSize: 13, color: p.muted)),
            const SizedBox(height: 6),
            Text('This is a record of returned signals and evidence. It is not an official complaint and not a determination of fraud.', style: theme.textTheme.bodySmall),
          ]),
        ),
      ]),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.note, required this.child, this.delay = Duration.zero});
  final String title, note;
  final Widget child;
  final Duration delay;
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Reveal(
      delay: delay,
      child: Container(
        margin: const EdgeInsets.only(top: 34),
        padding: const EdgeInsets.only(top: 30),
        decoration: BoxDecoration(border: Border(top: BorderSide(color: context.palette.line))),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Semantics(header: true, child: Text(title, style: theme.textTheme.headlineSmall)),
          const SizedBox(height: 6),
          Text(note, style: theme.textTheme.bodySmall),
          const SizedBox(height: 18),
          child,
        ]),
      ),
    );
  }
}

class _TrustScale extends StatelessWidget {
  const _TrustScale({required this.score, required this.tone, required this.verifiable});
  final double score;
  final Color tone;
  final bool verifiable;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final value = score.clamp(0, 100).toDouble();
    final zones = [
      (0.0, 35.0, p.danger.withValues(alpha: 0.42), 'High risk'),
      (35.0, 60.0, p.danger.withValues(alpha: 0.22), 'Suspicious'),
      (60.0, 85.0, p.caution.withValues(alpha: 0.34), 'Caution'),
      verifiable ? (85.0, 100.0, p.safe.withValues(alpha: 0.34), 'Verified') : (85.0, 100.0, p.neutral.withValues(alpha: 0.26), 'Unverified'),
    ];
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: context.calmMotion ? value : 0, end: value),
      duration: const Duration(milliseconds: 1500),
      curve: Curves.easeOutExpo,
      builder: (context, v, _) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Semantics(
          label: 'Trust score ${value.round()} out of 100',
          excludeSemantics: true,
          child: Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
            Text('${v.round()}', style: TextStyle(fontFamily: sans, fontSize: 92, fontWeight: FontWeight.w300, height: 0.95, letterSpacing: -5, color: tone)),
            const SizedBox(width: 8),
            Text('/100 trust', style: TextStyle(fontFamily: mono, fontSize: 15, color: p.muted)),
          ]),
        ),
        const SizedBox(height: 16),
        LayoutBuilder(builder: (context, box) {
          final w = box.maxWidth;
          return SizedBox(
            height: 66,
            child: Stack(clipBehavior: Clip.none, children: [
              Positioned(
                top: 10,
                left: 0,
                right: 0,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(99),
                  child: Row(children: [for (final z in zones) Expanded(flex: (z.$2 - z.$1).round(), child: Container(height: 12, color: z.$3))]),
                ),
              ),
              Positioned(
                left: (v / 100 * w - 3).clamp(0, w - 6),
                top: 0,
                child: Container(width: 6, height: 32, decoration: BoxDecoration(color: p.text, borderRadius: BorderRadius.circular(4), border: Border.all(color: p.panel, width: 2))),
              ),
              for (final limit in [35, 60, 85])
                Positioned(left: limit / 100 * w - 10, top: 30, child: SizedBox(width: 20, child: Text('$limit', textAlign: TextAlign.center, style: TextStyle(fontFamily: mono, fontSize: 12, color: p.muted)))),
              for (final z in zones)
                Positioned(
                  left: (z.$1 + z.$2) / 200 * w - 40,
                  top: 46,
                  child: SizedBox(width: 80, child: Text(z.$4, textAlign: TextAlign.center, style: TextStyle(fontFamily: sans, fontSize: 12.5, color: p.text2))),
                ),
            ]),
          );
        }),
        const SizedBox(height: 8),
        Text('Higher means more trust. Not a probability, and never a guarantee.', style: Theme.of(context).textTheme.bodySmall),
      ]),
    );
  }
}

class _Fusion extends StatelessWidget {
  const _Fusion({required this.signals, required this.result, required this.tone});
  final List<_Signal> signals;
  final ScreeningResult result;
  final Color tone;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    Color flagTone(FlagMark f) => switch (f) { FlagMark.high => p.danger, FlagMark.ok => p.safe, FlagMark.low => p.caution, FlagMark.none || FlagMark.heldBack => p.neutral };
    const rowHeight = 92.0;
    // Wide layouts align rows to the wires, so their height is fixed; on phones rows grow to fit.
    Widget rows(bool fixed) => Column(children: [
      for (final s in signals)
        Container(
          height: fixed ? rowHeight : null,
          constraints: fixed ? null : const BoxConstraints(minHeight: rowHeight),
          padding: fixed ? null : const EdgeInsets.symmetric(vertical: 10),
          child: Row(children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: p.soft(flagTone(s.flag)), borderRadius: BorderRadius.circular(15)),
              child: Icon(s.icon, color: s.flag == FlagMark.none || s.flag == FlagMark.heldBack ? p.text2 : flagTone(s.flag), size: 22),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(s.name, style: theme.textTheme.titleMedium),
                Text(s.finding, maxLines: fixed ? 2 : null, overflow: fixed ? TextOverflow.ellipsis : null, style: theme.textTheme.bodyMedium),
                Text(s.detail, maxLines: fixed ? 1 : null, overflow: fixed ? TextOverflow.ellipsis : null, style: theme.textTheme.bodySmall),
              ]),
            ),
            const SizedBox(width: 10),
            Text('${(s.risk * 100).round()}', style: TextStyle(fontFamily: sans, fontSize: 28, fontWeight: FontWeight.w300, color: s.flag == FlagMark.high ? p.danger : p.text)),
            const SizedBox(width: 10),
            FlagBadge(s.flag),
          ]),
        ),
    ]);
    final insufficient = result.band == TrustBand.insufficient;
    final node = Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      decoration: BoxDecoration(color: p.soft(tone), borderRadius: BorderRadius.circular(22), border: Border.all(color: p.edge(tone))),
      child: Row(children: [
        Text(insufficient ? '—' : '${result.trustScore.round()}', style: TextStyle(fontFamily: sans, fontSize: 40, fontWeight: FontWeight.w300, color: tone, letterSpacing: -2)),
        if (!insufficient) Text('/100', style: TextStyle(fontFamily: mono, fontSize: 13, color: p.muted)),
        const SizedBox(width: 16),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(bandLabel(result.band), style: theme.textTheme.titleMedium),
            Text(result.mode == 'authority_check' ? 'Authority check' : 'Identity check', style: theme.textTheme.bodySmall),
          ]),
        ),
      ]),
    );
    return LayoutBuilder(builder: (context, box) {
      if (box.maxWidth >= 560) {
        return Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
          Expanded(child: rows(true)),
          FusionWires(
            weights: [for (final s in signals) s.weight],
            tones: [for (final s in signals) flagTone(s.flag)],
            abstains: [for (final s in signals) s.abstains],
            rowHeight: rowHeight,
          ),
          SizedBox(width: 190, child: node),
        ]);
      }
      return Column(children: [rows(false), const SizedBox(height: 12), node]);
    });
  }
}

class _Timeline extends StatelessWidget {
  const _Timeline({required this.spoof, required this.transcript, required this.script});
  final Map<String, dynamic> spoof, transcript, script;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final segments = _list(spoof['timeline'])
        .map((s) => (start: _num(s['start_s']) ?? 0, end: _num(s['end_s']) ?? 0, score: _num(s['score']) ?? 0, synthetic: s['is_synthetic'] == true))
        .toList();
    final speech = _list(transcript['segments']);
    final concerns = _list(script['incriminating_markers']).map((m) => (m['matched_text'] as String? ?? '').toLowerCase()).where((t) => t.isNotEmpty);
    final reassures = _list(script['exculpatory_markers']).map((m) => (m['matched_text'] as String? ?? '').toLowerCase()).where((t) => t.isNotEmpty);
    if (segments.isEmpty && speech.isEmpty) return Text('No time-aligned evidence was returned.', style: theme.textTheme.bodyMedium);
    final total = [...segments.map((s) => s.end), ...speech.map((s) => _num(s['end_s']) ?? 0)].fold<double>(0, math.max);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (segments.isNotEmpty) SyntheticStrip(segments: segments, threshold: synthThreshold),
      Padding(
        padding: const EdgeInsets.only(top: 6, bottom: 14),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text('0 s', style: TextStyle(fontFamily: mono, fontSize: 12, color: p.muted)),
          Text('${total.toStringAsFixed(1)} s', style: TextStyle(fontFamily: mono, fontSize: 12, color: p.muted)),
        ]),
      ),
      for (final s in speech)
        Builder(builder: (context) {
          final text = s['text'] as String? ?? '';
          final lower = text.toLowerCase();
          final concern = concerns.any(lower.contains);
          final reassure = !concern && reassures.any(lower.contains);
          final color = concern ? p.danger : reassure ? p.safe : p.neutral;
          return Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: concern || reassure ? p.soft(color) : p.panel2,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: concern || reassure ? p.edge(color) : p.line),
            ),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(width: 58, child: Text('${(_num(s['start_s']) ?? 0).toStringAsFixed(1)} s', style: TextStyle(fontFamily: mono, fontSize: 12.5, color: p.muted, height: 1.6))),
              Expanded(child: Text(text, style: theme.textTheme.bodyMedium?.copyWith(color: p.text))),
            ]),
          );
        }),
    ]);
  }
}

class _Transcript extends StatelessWidget {
  const _Transcript({required this.text, required this.script});
  final String text;
  final Map<String, dynamic> script;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    if (text.isEmpty) return Text('No transcript is available for this recording.', style: theme.textTheme.bodyMedium);
    final marks = [
      for (final m in _list(script['incriminating_markers'])) (m['matched_text'] as String? ?? '', p.danger, m['description'] as String? ?? 'Concerning'),
      for (final m in _list(script['exculpatory_markers'])) (m['matched_text'] as String? ?? '', p.safe, m['description'] as String? ?? 'Reassuring'),
    ].where((m) => m.$1.trim().isNotEmpty);
    final lower = text.toLowerCase();
    final found = <(int, int, Color)>[];
    for (final m in marks) {
      final start = lower.indexOf(m.$1.toLowerCase());
      if (start < 0 || found.any((f) => start < f.$2 && start + m.$1.length > f.$1)) continue;
      found.add((start, start + m.$1.length, m.$2));
    }
    found.sort((a, b) => a.$1.compareTo(b.$1));
    final spans = <TextSpan>[];
    var cursor = 0;
    for (final f in found) {
      if (f.$1 > cursor) spans.add(TextSpan(text: text.substring(cursor, f.$1)));
      spans.add(TextSpan(
        text: text.substring(f.$1, f.$2),
        style: TextStyle(backgroundColor: p.soft(f.$3), decoration: TextDecoration.underline, decorationColor: f.$3, decorationThickness: 2),
      ));
      cursor = f.$2;
    }
    if (cursor < text.length) spans.add(TextSpan(text: text.substring(cursor)));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(
        padding: const EdgeInsets.only(left: 16),
        decoration: BoxDecoration(border: Border(left: BorderSide(color: p.line2))),
        child: SelectableText.rich(TextSpan(style: TextStyle(fontFamily: sans, fontSize: 19, height: 1.75, color: p.text), children: spans)),
      ),
      const SizedBox(height: 14),
      for (final m in marks)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            ToneChip(m.$2 == p.danger ? 'Concerning' : 'Reassuring', m.$2),
            const SizedBox(width: 10),
            Expanded(child: Padding(padding: const EdgeInsets.only(top: 3), child: Text(m.$3, style: theme.textTheme.bodyMedium))),
          ]),
        ),
    ]);
  }
}

class _Measurements extends StatelessWidget {
  const _Measurements({required this.quality, required this.spoof});
  final Map<String, dynamic> quality, spoof;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final speech = _num(quality['speech_duration_s']), minSpeech = _num(quality['min_speech_threshold_s']) ?? 1.5;
    final snr = _num(quality['snr_db']), minSnr = _num(quality['min_snr_threshold_db']) ?? 5;
    final hasSegments = _list(spoof['timeline']).isNotEmpty;
    FlagMark synth(double? v) => !hasSegments || v == null ? FlagMark.none : v >= synthThreshold ? FlagMark.high : FlagMark.ok;
    final run = _num(spoof['max_synth_run_s']);
    final rows = [
      ('Usable speech', _sec(speech), 'at least ${minSpeech.toStringAsFixed(1)} s', speech == null ? FlagMark.none : speech >= minSpeech ? FlagMark.ok : FlagMark.low),
      ('Signal-to-noise', snr == null ? '—' : '${snr.toStringAsFixed(1)} dB', 'at least ${minSnr.toStringAsFixed(1)} dB', snr == null ? FlagMark.none : snr >= minSnr ? FlagMark.ok : FlagMark.low),
      ('Median synthetic score', hasSegments ? _pct(_num(spoof['median_score'])) : '—', 'below ${_pct(synthThreshold)}', synth(_num(spoof['median_score']))),
      ('Peak synthetic score', hasSegments ? _pct(_num(spoof['peak_score'])) : '—', 'below ${_pct(synthThreshold)}', synth(_num(spoof['peak_score']))),
      ('Longest synthetic run', hasSegments ? _sec(run) : '—', '0 s in natural speech', !hasSegments || run == null ? FlagMark.none : run > 0 ? FlagMark.high : FlagMark.ok),
    ];
    return Column(children: [
      for (final r in rows)
        Container(
          padding: const EdgeInsets.symmetric(vertical: 13),
          decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.line))),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(r.$1, style: theme.textTheme.titleMedium?.copyWith(fontSize: 15.5)),
                Text(r.$3, style: theme.textTheme.bodySmall),
              ]),
            ),
            Text(r.$2, style: TextStyle(fontFamily: mono, fontSize: 15, color: p.text)),
            const SizedBox(width: 14),
            FlagBadge(r.$4),
          ]),
        ),
    ]);
  }
}

class _Evidence extends StatelessWidget {
  const _Evidence({required this.result, required this.script, required this.onSource});
  final ScreeningResult result;
  final Map<String, dynamic> script;
  final ValueChanged<String> onSource;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final playbooks = _list(script['playbooks']);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (result.evidence.isEmpty)
        const InfoMessage('No evidence items were returned. Treat this result with extra caution.')
      else
        for (final e in result.evidence)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 16),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.line))),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Wrap(spacing: 10, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
                Text(e.signal.isEmpty ? 'Evidence' : e.signal[0].toUpperCase() + e.signal.substring(1), style: theme.textTheme.titleMedium),
                if (e.severity != null)
                  ToneChip(e.severity![0].toUpperCase() + e.severity!.substring(1), switch (e.severity) { 'critical' || 'high' => p.danger, 'medium' => p.caution, _ => p.neutral }),
              ]),
              const SizedBox(height: 8),
              Text(e.explanation, style: theme.textTheme.bodyMedium),
              if (e.value != null) Padding(padding: const EdgeInsets.only(top: 6), child: Text('Observed: ${e.value}', style: theme.textTheme.bodySmall?.copyWith(color: p.text2))),
              if (e.citationUrl != null && ['https', 'http'].contains(Uri.tryParse(e.citationUrl!)?.scheme))
                TextButton.icon(
                  style: TextButton.styleFrom(padding: EdgeInsets.zero, foregroundColor: p.dark ? const Color(0xFFA7AFFF) : p.accent),
                  onPressed: () => onSource(e.citationUrl!),
                  icon: const Icon(Icons.open_in_new_rounded, size: 16),
                  label: Text(e.citationTitle ?? 'Read source'),
                ),
            ]),
          ),
      if (playbooks.isNotEmpty) ...[
        const SizedBox(height: 18),
        Text('Resembles these published scam patterns', style: theme.textTheme.titleMedium),
        for (final pb in playbooks)
          InkWell(
            onTap: pb['source_url'] is String ? () => onSource(pb['source_url'] as String) : null,
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 14),
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.line))),
              child: Row(children: [
                SizedBox(width: 56, child: Text(_pct(_num(pb['similarity_score'])), style: TextStyle(fontFamily: sans, fontSize: 20, fontWeight: FontWeight.w300, color: p.text))),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(pb['title'] as String? ?? 'Advisory', style: theme.textTheme.titleMedium?.copyWith(fontSize: 15)),
                    Text(pb['source_agency'] as String? ?? '', style: theme.textTheme.bodySmall),
                  ]),
                ),
                Icon(Icons.open_in_new_rounded, size: 18, color: p.muted),
              ]),
            ),
          ),
      ],
    ]);
  }
}
