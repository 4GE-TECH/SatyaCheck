import 'dart:async';
import 'package:flutter/material.dart';
import 'models.dart';

/// SatyaCheck's listening-room palette. Voice colours come from the logo and belong to audio;
/// tone colours belong to verdicts. Mirrors the web dashboard's tokens.
@immutable
class Palette extends ThemeExtension<Palette> {
  const Palette({
    required this.bg,
    required this.raise,
    required this.panel,
    required this.panel2,
    required this.panel3,
    required this.line,
    required this.line2,
    required this.text,
    required this.text2,
    required this.muted,
    required this.accent,
    required this.voice1,
    required this.voice2,
    required this.voice3,
    required this.safe,
    required this.caution,
    required this.danger,
    required this.neutral,
    required this.dark,
  });

  final Color bg, raise, panel, panel2, panel3, line, line2, text, text2, muted, accent;
  final Color voice1, voice2, voice3, safe, caution, danger, neutral;
  final bool dark;

  static const night = Palette(
    bg: Color(0xFF050611),
    raise: Color(0xFF0A0C21),
    panel: Color(0xFF0D102B),
    panel2: Color(0xFF13173A),
    panel3: Color(0xFF1A1F4A),
    line: Color(0x219CA4FF),
    line2: Color(0x3D9CA4FF),
    text: Color(0xFFEEF0FF),
    text2: Color(0xFFBCC1E8),
    muted: Color(0xFF8D93C2),
    accent: Color(0xFF5F6BFF),
    voice1: Color(0xFF3C56FF),
    voice2: Color(0xFF7A5CFF),
    voice3: Color(0xFF39C6FF),
    safe: Color(0xFF43E0A4),
    caution: Color(0xFFFFC24F),
    danger: Color(0xFFFF5F6F),
    neutral: Color(0xFFA3AAD6),
    dark: true,
  );

  static const day = Palette(
    bg: Color(0xFFF2F3F9),
    raise: Color(0xFFE9EBF6),
    panel: Color(0xFFFFFFFF),
    panel2: Color(0xFFF5F6FC),
    panel3: Color(0xFFECEEF9),
    line: Color(0x1A1E246E),
    line2: Color(0x331E246E),
    text: Color(0xFF0A0C2A),
    text2: Color(0xFF353A68),
    muted: Color(0xFF5B6190),
    accent: Color(0xFF3A43F2),
    voice1: Color(0xFF2F45F5),
    voice2: Color(0xFF6A45F2),
    voice3: Color(0xFF0F9EE0),
    safe: Color(0xFF0B8458),
    caution: Color(0xFFA05F00),
    danger: Color(0xFFD0283A),
    neutral: Color(0xFF535A87),
    dark: false,
  );

  Color soft(Color tone) => tone.withValues(alpha: dark ? 0.14 : 0.09);
  Color edge(Color tone) => tone.withValues(alpha: dark ? 0.38 : 0.3);

  @override
  Palette copyWith() => this;

  @override
  Palette lerp(ThemeExtension<Palette>? other, double t) => t < 0.5 || other is! Palette ? this : other;
}

extension PaletteOf on BuildContext {
  Palette get palette => Theme.of(this).extension<Palette>()!;
  bool get calmMotion => MediaQuery.maybeDisableAnimationsOf(this) ?? false;
}

const sans = 'Geist';
const mono = 'GeistMono';

ThemeData satyaTheme(Brightness brightness) {
  final p = brightness == Brightness.dark ? Palette.night : Palette.day;
  final scheme = ColorScheme.fromSeed(
    seedColor: p.accent,
    brightness: brightness,
    primary: p.accent,
    onPrimary: Colors.white,
    surface: p.panel,
    onSurface: p.text,
    onSurfaceVariant: p.muted,
    outline: p.line2,
    outlineVariant: p.line,
    error: p.danger,
  );
  final base = ThemeData(useMaterial3: true, colorScheme: scheme, brightness: brightness, fontFamily: sans);
  TextStyle t(double size, FontWeight weight, {double tracking = 0, double height = 1.4, Color? color}) =>
      TextStyle(fontFamily: sans, fontSize: size, fontWeight: weight, letterSpacing: tracking, height: height, color: color ?? p.text);
  return base.copyWith(
    scaffoldBackgroundColor: p.bg,
    extensions: [p],
    splashFactory: InkSparkle.splashFactory,
    textTheme: TextTheme(
      displayLarge: t(46, FontWeight.w600, tracking: -2.4, height: 1.02),
      displayMedium: t(38, FontWeight.w600, tracking: -1.9, height: 1.04),
      headlineLarge: t(32, FontWeight.w600, tracking: -1.4, height: 1.08),
      headlineMedium: t(26, FontWeight.w600, tracking: -1.0, height: 1.12),
      headlineSmall: t(22, FontWeight.w600, tracking: -0.7, height: 1.18),
      titleLarge: t(19, FontWeight.w600, tracking: -0.4, height: 1.25),
      titleMedium: t(16.5, FontWeight.w600, tracking: -0.2),
      bodyLarge: t(17, FontWeight.w400, height: 1.55, color: p.text2),
      bodyMedium: t(15.5, FontWeight.w400, height: 1.5, color: p.text2),
      bodySmall: t(14, FontWeight.w400, height: 1.45, color: p.muted),
      labelLarge: t(15, FontWeight.w600),
      labelMedium: t(14, FontWeight.w600, color: p.muted),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: p.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: t(18, FontWeight.w600, tracking: -0.4),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: p.panel2,
      labelStyle: t(15, FontWeight.w500, color: p.muted),
      floatingLabelStyle: t(14, FontWeight.w600, color: p.accent),
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(18), borderSide: BorderSide(color: p.line2)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(18), borderSide: BorderSide(color: p.line2)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(18), borderSide: BorderSide(color: p.accent, width: 1.6)),
      errorBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(18), borderSide: BorderSide(color: p.danger)),
    ),
    checkboxTheme: CheckboxThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      side: BorderSide(color: p.line2, width: 1.5),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: p.panel3,
      contentTextStyle: t(15, FontWeight.w500),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    ),
    dividerTheme: DividerThemeData(color: p.line, thickness: 1, space: 1),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: p.voice3, linearTrackColor: p.panel3),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: _RisePageTransitions(),
      TargetPlatform.iOS: _RisePageTransitions(),
      TargetPlatform.windows: _RisePageTransitions(),
      TargetPlatform.linux: _RisePageTransitions(),
      TargetPlatform.macOS: _RisePageTransitions(),
    }),
  );
}

/// Pages rise into place with a short settle; nothing slides from the side like a document.
class _RisePageTransitions extends PageTransitionsBuilder {
  const _RisePageTransitions();
  @override
  Widget buildTransitions<T>(PageRoute<T> route, BuildContext context, Animation<double> animation,
      Animation<double> secondaryAnimation, Widget child) {
    if (context.calmMotion) return FadeTransition(opacity: animation, child: child);
    final curve = CurvedAnimation(parent: animation, curve: Curves.easeOutExpo, reverseCurve: Curves.easeInCubic);
    return FadeTransition(
      opacity: Tween(begin: 0.0, end: 1.0).animate(CurvedAnimation(parent: animation, curve: const Interval(0, 0.6))),
      child: SlideTransition(
        position: Tween(begin: const Offset(0, 0.06), end: Offset.zero).animate(curve),
        child: ScaleTransition(scale: Tween(begin: 0.985, end: 1.0).animate(curve), child: child),
      ),
    );
  }
}

// ── Verdict vocabulary ──────────────────────────────────────────────────────────────

String bandLabel(TrustBand band) => switch (band) {
      TrustBand.verified => 'Voice verified',
      TrustBand.caution => 'Caution',
      TrustBand.suspicious => 'Suspicious',
      TrustBand.highRisk => 'High risk',
      TrustBand.unverified => 'Unverified',
      TrustBand.insufficient => 'Not enough audio',
    };

String bandHeadline(TrustBand band) => switch (band) {
      TrustBand.verified => 'This is a voice you know.',
      TrustBand.caution => 'Take a moment to verify.',
      TrustBand.suspicious => 'Check before you act.',
      TrustBand.highRisk => 'Pause. Verify independently.',
      TrustBand.unverified => 'We don’t know this voice.',
      TrustBand.insufficient => 'Not enough speech to judge.',
    };

String bandSummary(TrustBand band) => switch (band) {
      TrustBand.verified => 'The voice matches someone you enrolled. Still verify anything unexpected, like a payment request.',
      TrustBand.caution => 'Something here deserves a closer look. Confirm the request through a number you already trust.',
      TrustBand.suspicious => 'The analysis found concerning signals. Call the person back on a number you trust before doing anything.',
      TrustBand.highRisk => 'Several signals raise concern. Do not send money or share codes until you have verified the caller.',
      TrustBand.unverified => 'No enrolled person matched. That is normal for banks, couriers and doctors, and is not a sign of fraud on its own.',
      TrustBand.insufficient => 'There was too little clear speech for a reliable check, so no score is given. Try a longer, clearer recording.',
    };

Color bandColor(BuildContext context, TrustBand band) {
  final p = context.palette;
  return switch (band.signal) {
    Signal.green => p.safe,
    Signal.amber => p.caution,
    Signal.red => p.danger,
    Signal.grey => p.neutral,
  };
}

/// Some reply templates shout ("DO NOT transfer money"). Shown calmly; acronyms keep their capitals.
String calm(String text) {
  final softened = text.replaceAllMapped(
      RegExp(r"\b(DO|NOT|NEVER|DON'T|DONT|STOP|PLEASE|IMMEDIATELY|ANY|NO)\b"), (m) => m[0]!.toLowerCase());
  return softened.isEmpty ? softened : softened[0].toUpperCase() + softened.substring(1);
}

// ── Building blocks ────────────────────────────────────────────────────────────────

/// A plate seated in a tray: the double bezel, used only for hero surfaces.
class Bezel extends StatelessWidget {
  const Bezel({super.key, required this.child, this.radius = 30, this.tint});
  final Widget child;
  final double radius;
  final Color? tint;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
        color: p.text.withValues(alpha: 0.035),
        borderRadius: BorderRadius.circular(radius + 6),
        border: Border.all(color: p.text.withValues(alpha: 0.08)),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: p.dark ? 0.45 : 0.12), blurRadius: 60, offset: const Offset(0, 28), spreadRadius: -24)],
      ),
      child: Container(
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          color: p.panel,
          gradient: tint == null ? null : LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color.alphaBlend(tint!.withValues(alpha: p.dark ? 0.16 : 0.08), p.panel), p.panel], stops: const [0, 0.7]),
          borderRadius: BorderRadius.circular(radius),
          border: Border.all(color: p.line),
        ),
        child: child,
      ),
    );
  }
}

/// A flat panel for secondary content.
class Panel extends StatelessWidget {
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(22), this.color});
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? color;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Container(
      padding: padding,
      decoration: BoxDecoration(color: color ?? p.panel, borderRadius: BorderRadius.circular(26), border: Border.all(color: p.line)),
      child: child,
    );
  }
}

/// Kept for screens that still say Surface.
typedef Surface = Panel;

enum PillKind { primary, secondary, danger, ghost }

/// A pill button. A trailing icon sits in its own circle inside the pill and nudges when pressed.
class PillButton extends StatefulWidget {
  const PillButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.kind = PillKind.primary,
    this.icon,
    this.trailing,
    this.busy = false,
    this.large = false,
    this.expand = false,
  });
  final String label;
  final VoidCallback? onPressed;
  final PillKind kind;
  final IconData? icon, trailing;
  final bool busy, large, expand;
  @override
  State<PillButton> createState() => _PillButtonState();
}

class _PillButtonState extends State<PillButton> {
  bool _down = false;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final enabled = widget.onPressed != null && !widget.busy;
    final (bg, fg, border) = switch (widget.kind) {
      PillKind.primary => (enabled ? p.accent : p.panel3, enabled ? Colors.white : p.muted, Colors.transparent),
      PillKind.secondary => (p.panel2, p.text, p.line2),
      PillKind.danger => (p.soft(p.danger), p.danger, p.edge(p.danger)),
      PillKind.ghost => (Colors.transparent, p.text2, Colors.transparent),
    };
    final height = widget.large ? 58.0 : 50.0;
    final content = Row(
      mainAxisSize: widget.expand ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (widget.busy)
          Padding(padding: const EdgeInsets.only(right: 10), child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: fg)))
        else if (widget.icon != null)
          Padding(padding: const EdgeInsets.only(right: 9), child: Icon(widget.icon, size: 19, color: fg)),
        Flexible(child: Text(widget.label, overflow: TextOverflow.ellipsis, style: TextStyle(fontFamily: sans, fontSize: widget.large ? 17 : 15.5, fontWeight: FontWeight.w600, color: fg, letterSpacing: -0.2))),
        if (widget.trailing != null && !widget.busy)
          AnimatedSlide(
            offset: _down ? const Offset(0.08, -0.04) : Offset.zero,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            child: Container(
              margin: const EdgeInsets.only(left: 12),
              width: height - 14,
              height: height - 14,
              decoration: BoxDecoration(shape: BoxShape.circle, color: widget.kind == PillKind.primary && enabled ? Colors.white.withValues(alpha: 0.18) : p.panel3),
              child: Icon(widget.trailing, size: 18, color: fg),
            ),
          ),
      ],
    );
    return Semantics(
      button: true,
      enabled: enabled,
      child: GestureDetector(
        onTapDown: enabled ? (_) => setState(() => _down = true) : null,
        onTapCancel: () => setState(() => _down = false),
        onTapUp: (_) => setState(() => _down = false),
        child: AnimatedScale(
          scale: _down ? 0.97 : 1,
          duration: const Duration(milliseconds: 160),
          curve: Curves.easeOutCubic,
          child: Material(
            color: bg,
            shape: StadiumBorder(side: BorderSide(color: border)),
            clipBehavior: Clip.antiAlias,
            elevation: 0,
            child: InkWell(
              onTap: enabled ? widget.onPressed : null,
              child: Container(
                height: height,
                padding: EdgeInsets.only(left: widget.large ? 26 : 20, right: widget.trailing != null && !widget.busy ? 7 : (widget.large ? 26 : 20)),
                child: content,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class ToneChip extends StatelessWidget {
  const ToneChip(this.label, this.tone, {super.key, this.large = false});
  final String label;
  final Color tone;
  final bool large;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: large ? 14 : 11, vertical: large ? 8 : 5),
      decoration: BoxDecoration(color: p.soft(tone), borderRadius: BorderRadius.circular(999), border: Border.all(color: p.edge(tone))),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 8, height: 8, decoration: BoxDecoration(color: tone, shape: BoxShape.circle, boxShadow: [BoxShadow(color: tone.withValues(alpha: 0.35), blurRadius: 0, spreadRadius: 3)])),
        const SizedBox(width: 8),
        Flexible(child: Text(label, softWrap: true, style: TextStyle(fontFamily: sans, fontSize: large ? 15 : 13.5, fontWeight: FontWeight.w600, color: tone))),
      ]),
    );
  }
}

class VerdictBadge extends StatelessWidget {
  const VerdictBadge(this.band, {super.key, this.large = false});
  final TrustBand band;
  final bool large;
  @override
  Widget build(BuildContext context) => ToneChip(bandLabel(band), bandColor(context, band), large: large);
}

enum FlagMark { high, low, ok, none, heldBack }

class FlagBadge extends StatelessWidget {
  const FlagBadge(this.mark, {super.key});
  final FlagMark mark;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final (text, label, fg, bg, border) = switch (mark) {
      FlagMark.high => ('Concern', 'Raised concern', Colors.white, p.danger, Colors.transparent),
      FlagMark.low => ('Below minimum', 'Below the minimum', p.caution, p.soft(p.caution), p.edge(p.caution)),
      FlagMark.ok => ('Expected', 'As expected', p.safe, Colors.transparent, p.edge(p.safe)),
      FlagMark.none => ('Not assessed', 'Not assessed', p.muted, Colors.transparent, p.line2),
      FlagMark.heldBack => ('Not trusted', 'Match not trusted', p.muted, Colors.transparent, p.line2),
    };
    return Semantics(
      label: label,
      excludeSemantics: true,
      child: Container(
        constraints: const BoxConstraints(minWidth: 40),
        height: 28,
        alignment: Alignment.center,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999), border: Border.all(color: border)),
        child: Text(text, style: TextStyle(fontFamily: sans, fontSize: 13, fontWeight: FontWeight.w600, color: fg)),
      ),
    );
  }
}

class InfoMessage extends StatelessWidget {
  const InfoMessage(this.message, {super.key, this.error = false, this.action, this.tone});
  final String message;
  final bool error;
  final Widget? action;
  final Color? tone;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final color = tone ?? (error ? p.danger : p.neutral);
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: p.soft(color), borderRadius: BorderRadius.circular(20), border: Border.all(color: p.edge(color))),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(error ? Icons.error_rounded : Icons.info_rounded, size: 20, color: color),
            const SizedBox(width: 12),
            Expanded(child: Text(message, style: TextStyle(fontFamily: sans, fontSize: 15, height: 1.45, color: p.text))),
          ]),
          if (action != null) Padding(padding: const EdgeInsets.only(top: 8, left: 26), child: action!),
        ]),
      ),
    );
  }
}

/// Staggered entrance: content rises a few pixels and fades in once. Under reduced motion it is
/// simply there.
class Reveal extends StatefulWidget {
  const Reveal({super.key, required this.child, this.delay = Duration.zero, this.offset = 18});
  final Widget child;
  final Duration delay;
  final double offset;
  @override
  State<Reveal> createState() => _RevealState();
}

class _RevealState extends State<Reveal> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 760));
  Timer? _timer;
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (context.calmMotion) {
      _c.value = 1;
    } else if (!_c.isAnimating && _c.value == 0) {
      _timer = Timer(widget.delay, () { if (mounted) _c.forward(); });
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final curve = CurvedAnimation(parent: _c, curve: Curves.easeOutExpo);
    return AnimatedBuilder(
      animation: curve,
      builder: (_, child) => Opacity(
        opacity: (0.2 + curve.value * 0.8).clamp(0, 1),
        child: Transform.translate(offset: Offset(0, (1 - curve.value) * widget.offset), child: child),
      ),
      child: widget.child,
    );
  }
}
