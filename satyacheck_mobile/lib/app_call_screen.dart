import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api_client.dart';
import 'models.dart';
import 'rtc_call.dart';
import 'theme.dart';

/// A call with another SatyaCheck user, each voice screened live for the person hearing it
/// (webrtc/README.md). Opened to ring a connection ([callee]) or to answer ([incoming]).
class AppCallScreen extends StatefulWidget {
  const AppCallScreen({super.key, required this.api, this.callee, this.incoming})
      : assert((callee == null) != (incoming == null), 'ring someone, or answer a call');
  final ApiClient api;
  final RtcPerson? callee;
  final IncomingCall? incoming;
  @override
  State<AppCallScreen> createState() => _AppCallScreenState();
}

class _AppCallScreenState extends State<AppCallScreen> {
  late final RtcCallController _call = RtcCallController(widget.api);

  @override
  void initState() {
    super.initState();
    final incoming = widget.incoming;
    unawaited(incoming != null ? _call.answer(incoming) : _call.call(widget.callee!));
  }

  @override
  void dispose() {
    _call.dispose();
    super.dispose();
  }

  Future<bool> _confirmLeave() async {
    if (!_call.live) return true;
    final leave = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Hang up?'),
        content: const Text('Leaving this screen ends the call for both of you.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Stay')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Hang up')),
        ],
      ),
    );
    if (leave == true) await _call.hangUp();
    return leave == true;
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _call,
      builder: (context, _) {
        return PopScope(
          canPop: !_call.live,
          onPopInvokedWithResult: (didPop, _) async {
            if (didPop) return;
            if (await _confirmLeave() && context.mounted) Navigator.pop(context);
          },
          child: Scaffold(
            appBar: AppBar(title: Text(_call.otherName)),
            body: SafeArea(
              child: Align(
                alignment: Alignment.topCenter,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 720),
                  child: switch (_call.phase) {
                    RtcPhase.idle || RtcPhase.connecting || RtcPhase.ringing => _ringing(context),
                    RtcPhase.inCall => _inCall(context),
                    RtcPhase.ended => _ended(context),
                  },
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  EdgeInsets get _padding => const EdgeInsets.fromLTRB(20, 8, 20, 40);

  // --- calling, or connecting after answering ---------------------------------------------

  Widget _ringing(BuildContext context) {
    final theme = Theme.of(context);
    final calling = _call.isCaller && _call.phase == RtcPhase.ringing;
    return ListView(padding: _padding, children: [
      const SizedBox(height: 40),
      Center(child: _Avatar(person: _call.other, size: 104)),
      const SizedBox(height: 20),
      Text(_call.otherName, textAlign: TextAlign.center, style: theme.textTheme.headlineMedium),
      if (_call.other?.username.isNotEmpty ?? false)
        Text('@${_call.other!.username}', textAlign: TextAlign.center, style: theme.textTheme.bodyMedium),
      const SizedBox(height: 18),
      Semantics(
        liveRegion: true,
        child: Text(calling ? 'Ringing…' : 'Connecting…', textAlign: TextAlign.center, style: theme.textTheme.titleMedium),
      ),
      const SizedBox(height: 8),
      Text('Nothing is checked until you are both in the call.', textAlign: TextAlign.center, style: theme.textTheme.bodySmall),
      const SizedBox(height: 48),
      Center(
        child: SizedBox(
          width: 96,
          child: _RoundControl(icon: Icons.call_end_rounded, label: calling ? 'Cancel' : 'Hang up', danger: true, onTap: _call.hangUp),
        ),
      ),
    ]);
  }

  // --- in the call -------------------------------------------------------------------------

  Widget _inCall(BuildContext context) {
    final theme = Theme.of(context);
    final verdict = _call.verdict;
    return ListView(padding: _padding, children: [
      const SizedBox(height: 10),
      Row(children: [
        _Avatar(person: _call.other, size: 44),
        const SizedBox(width: 12),
        Expanded(child: Text('The voice of ${_call.otherName}', style: theme.textTheme.titleMedium)),
      ]),
      const SizedBox(height: 12),
      VerdictBanner(verdict: verdict),
      ..._notices(context),
      if (verdict != null && verdict.openAlerts.isNotEmpty) ...[
        const SizedBox(height: 22),
        Text('What was found', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 10),
        for (final alert in verdict.openAlerts) Padding(padding: const EdgeInsets.only(bottom: 10), child: _AlertTile(alert: alert)),
      ],
      if (verdict != null && verdict.reasons.isNotEmpty && verdict.band != TrustBand.insufficient) ...[
        const SizedBox(height: 18),
        Text('Why', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        for (final reason in verdict.reasons)
          Padding(padding: const EdgeInsets.only(bottom: 6), child: Text('•  ${calm(reason.explanation)}', style: theme.textTheme.bodyMedium)),
      ],
      if (verdict != null && verdict.transcriptTail.isNotEmpty) ...[
        const SizedBox(height: 18),
        Text('Heard', style: theme.textTheme.titleMedium),
        const SizedBox(height: 6),
        Text('“${verdict.transcriptTail}”', maxLines: 5, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodyMedium?.copyWith(fontStyle: FontStyle.italic)),
      ],
      const SizedBox(height: 28),
      _controls(),
    ]);
  }

  /// Conditions the listener has to know about, in order of how much they change the picture.
  List<Widget> _notices(BuildContext context) {
    final p = context.palette;
    final verdict = _call.verdict;
    final notices = <Widget>[
      if (_call.screeningLost)
        const InfoMessage('Screening unavailable. The call continues, but nothing is being checked. If you are asked for money or codes, call them back on a number you already have.',
            error: true),
      if (verdict != null && !verdict.screeningAvailable)
        InfoMessage('Screening paused${verdict.reason == null ? '' : ': ${verdict.reason}'}. The last result stays shown.', tone: p.caution),
      if (verdict != null && verdict.partlyUnchecked) InfoMessage('Part of this call couldn’t be checked.', tone: p.caution),
      if (_call.reconnecting) InfoMessage('Reconnecting… The last result stays shown.', tone: p.neutral),
      if (_call.otherAway) InfoMessage('${_call.otherName}’s connection dropped. Waiting for them to come back…', tone: p.neutral),
      // The connection is up but nothing is flowing (rtc_call.dart, MediaHealth). Said only
      // while it lasts; each clears itself as soon as audio or results arrive.
      if (!_call.reconnecting && !_call.otherAway) ...[
        if (_call.media.notHeardByServer)
          InfoMessage('The call hasn’t heard your voice yet. If you are talking, check the microphone permission or try a better connection.',
              tone: p.caution),
        if (_call.media.notHearingThem)
          InfoMessage('No audio is arriving from ${_call.otherName}. The connection on one side may be blocking it.', tone: p.caution),
        if (_call.media.noVerdicts && !_call.screeningLost)
          InfoMessage('Results aren’t reaching this phone, so the check above can’t update.', tone: p.caution),
      ],
    ];
    return [for (final n in notices) Padding(padding: const EdgeInsets.only(top: 14), child: n)];
  }

  Widget _controls() {
    return Row(children: [
      Expanded(
        child: _RoundControl(
          icon: _call.muted ? Icons.mic_off_rounded : Icons.mic_none_rounded,
          label: _call.muted ? 'Unmute' : 'Mute',
          active: _call.muted,
          onTap: _call.toggleMute,
        ),
      ),
      Expanded(
        child: _RoundControl(
          icon: _call.speaker ? Icons.volume_up_rounded : Icons.hearing_rounded,
          label: _call.speaker ? 'Speaker' : 'Earpiece',
          active: _call.speaker,
          onTap: _call.toggleSpeaker,
        ),
      ),
      Expanded(child: _RoundControl(icon: Icons.call_end_rounded, label: 'Hang up', danger: true, onTap: _call.hangUp)),
    ]);
  }

  // --- after the call ------------------------------------------------------------------------

  Widget _ended(BuildContext context) {
    final theme = Theme.of(context);
    final verdict = _call.verdict;
    return ListView(padding: _padding, children: [
      const SizedBox(height: 14),
      Semantics(header: true, child: Text(_call.error != null ? 'Call not connected' : 'Call ended', style: theme.textTheme.displaySmall)),
      if (_call.error != null) ...[
        const SizedBox(height: 14),
        InfoMessage(_call.error!, error: true),
      ] else if (_call.endedReason != null) ...[
        const SizedBox(height: 10),
        Text(_call.endedReason!, style: theme.textTheme.bodyLarge),
      ],
      const SizedBox(height: 22),
      if (verdict != null) ...[
        Text('Last result for ${_call.otherName}’s voice', style: theme.textTheme.titleMedium),
        const SizedBox(height: 10),
        VerdictBanner(verdict: verdict),
        for (final alert in verdict.openAlerts) Padding(padding: const EdgeInsets.only(top: 10), child: _AlertTile(alert: alert)),
        const SizedBox(height: 10),
        Text('The full result is under Reports on the web dashboard.', style: theme.textTheme.bodySmall),
        const SizedBox(height: 24),
      ],
      PillButton(label: 'Done', expand: true, onPressed: () => Navigator.maybePop(context)),
    ]);
  }
}

/// The full-screen ring for a call from one of your connections.
class IncomingCallScreen extends StatefulWidget {
  const IncomingCallScreen({super.key, required this.api, required this.call, required this.watcher});
  final ApiClient api;
  final IncomingCall call;
  final IncomingCallWatcher watcher;
  @override
  State<IncomingCallScreen> createState() => _IncomingCallScreenState();
}

class _IncomingCallScreenState extends State<IncomingCallScreen> {
  Timer? _buzz;
  bool _answered = false;

  @override
  void initState() {
    super.initState();
    widget.watcher.addListener(_onWatch);
    unawaited(HapticFeedback.heavyImpact());
    _buzz = Timer.periodic(const Duration(milliseconds: 1500), (_) => unawaited(HapticFeedback.heavyImpact()));
  }

  @override
  void dispose() {
    _buzz?.cancel();
    widget.watcher.removeListener(_onWatch);
    super.dispose();
  }

  /// Cancelled by the caller, or rang out: close quietly and say so.
  void _onWatch() {
    if (_answered || !mounted || widget.watcher.stillRinging(widget.call.callId)) return;
    _buzz?.cancel();
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(SnackBar(content: Text('Missed call from ${widget.call.caller.name}')));
    Navigator.maybePop(context);
  }

  void _accept() {
    _answered = true;
    _buzz?.cancel();
    Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => AppCallScreen(api: widget.api, incoming: widget.call)));
  }

  Future<void> _decline() async {
    _answered = true;
    _buzz?.cancel();
    unawaited(widget.api.declineCall(widget.call.callId));
    if (mounted) Navigator.maybePop(context);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final caller = widget.call.caller;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) unawaited(_decline());
      },
      child: Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 48, 24, 40),
            child: Column(children: [
              Text('Incoming SatyaCheck call', style: theme.textTheme.titleMedium),
              const Spacer(),
              _Avatar(person: caller, size: 120),
              const SizedBox(height: 22),
              Semantics(
                liveRegion: true,
                child: Text(caller.name, textAlign: TextAlign.center, style: theme.textTheme.displaySmall),
              ),
              if (caller.username.isNotEmpty) Text('@${caller.username}', style: theme.textTheme.bodyLarge),
              const SizedBox(height: 14),
              Text('Their voice will be checked while you talk.', textAlign: TextAlign.center, style: theme.textTheme.bodyMedium),
              const Spacer(),
              Row(children: [
                Expanded(child: _RoundControl(icon: Icons.call_end_rounded, label: 'Decline', danger: true, onTap: _decline)),
                Expanded(child: _RoundControl(icon: Icons.call_rounded, label: 'Accept', accept: true, onTap: _accept)),
              ]),
            ]),
          ),
        ),
      ),
    );
  }
}

/// Band copy for a call (webrtc/BACKEND_API.md, "display_band"). Never "scammer" or "fraud";
/// unverified is neutral, not an accusation.
String _bandCopy(TrustBand band) => switch (band) {
      TrustBand.insufficient => 'Listening…',
      TrustBand.unverified => 'Not a saved voice',
      TrustBand.verified => 'Matches a saved voice',
      TrustBand.caution => 'Take a moment to verify',
      TrustBand.suspicious => 'Be careful',
      TrustBand.highRisk => 'Stop. Call them back on a number you trust.',
    };

class VerdictBanner extends StatelessWidget {
  const VerdictBanner({super.key, required this.verdict});
  final RtcVerdict? verdict;

  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final band = verdict?.band ?? TrustBand.insufficient;
    final tone = bandColor(context, band);
    final score = verdict?.trustScore;
    return Semantics(
      liveRegion: true,
      child: AnimatedContainer(
        duration: context.calmMotion ? Duration.zero : const Duration(milliseconds: 300),
        padding: const EdgeInsets.all(22),
        decoration: BoxDecoration(color: p.soft(tone), borderRadius: BorderRadius.circular(26), border: Border.all(color: p.edge(tone), width: 1.5)),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // Large type: readable from across the room.
              Text(_bandCopy(band), style: theme.textTheme.headlineMedium?.copyWith(color: p.text)),
              const SizedBox(height: 8),
              Text(band == TrustBand.insufficient ? 'Not enough speech yet to judge.' : bandSummary(band), style: theme.textTheme.bodyMedium),
            ]),
          ),
          // No number while there is nothing to score.
          if (score != null && band != TrustBand.insufficient) ...[
            const SizedBox(width: 14),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text('${score.round()}', style: TextStyle(fontFamily: sans, fontSize: 44, height: 1, fontWeight: FontWeight.w300, color: tone)),
              Text('trust / 100', style: theme.textTheme.bodySmall),
            ]),
          ],
        ]),
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.person, required this.size});
  final RtcPerson? person;
  final double size;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final name = person?.name.replaceFirst('@', '') ?? '?';
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(shape: BoxShape.circle, gradient: LinearGradient(colors: [p.voice1, p.voice2])),
      child: Text(name.isEmpty ? '?' : name.characters.first.toUpperCase(),
          style: TextStyle(fontFamily: sans, fontSize: size * 0.4, fontWeight: FontWeight.w600, color: Colors.white)),
    );
  }
}

class _AlertTile extends StatelessWidget {
  const _AlertTile({required this.alert});
  final RtcAlert alert;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final tone = bandColor(context, alert.band);
    final at = alert.atS.round();
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: p.panel, borderRadius: BorderRadius.circular(20), border: Border.all(color: p.edge(tone))),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(Icons.flag_rounded, color: tone),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(alert.evidence == null ? bandLabel(alert.band) : calm(alert.evidence!), style: theme.textTheme.bodyLarge),
            const SizedBox(height: 4),
            Text('${bandLabel(alert.band)} · at ${at ~/ 60}:${(at % 60).toString().padLeft(2, '0')}', style: theme.textTheme.bodySmall),
          ]),
        ),
      ]),
    );
  }
}

class _RoundControl extends StatelessWidget {
  const _RoundControl({required this.icon, required this.label, required this.onTap, this.active = false, this.danger = false, this.accept = false});
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool active, danger, accept;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final fill = danger ? p.danger : accept ? p.safe : active ? p.text : p.panel2;
    final ink = danger || accept ? Colors.white : active ? (p.dark ? p.bg : Colors.white) : p.text;
    return Semantics(
      button: true,
      label: label,
      child: Column(children: [
        Material(
          color: fill,
          shape: CircleBorder(side: BorderSide(color: danger || accept ? fill : p.line2)),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox(width: 68, height: 68, child: Icon(icon, size: 28, color: ink)),
          ),
        ),
        const SizedBox(height: 8),
        ExcludeSemantics(child: Text(label, style: theme.textTheme.bodySmall)),
      ]),
    );
  }
}
