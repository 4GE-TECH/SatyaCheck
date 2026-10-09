import 'dart:math' as math;
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'theme.dart';

/// Min/max peaks of a 16-bit PCM WAV, normalised to the loudest sample. Returns null for any
/// other format; the stage then stays ambient rather than drawing something it did not read.
Float32List? wavPeaks(Uint8List bytes, {int buckets = 120}) {
  try {
    if (bytes.length < 44 || String.fromCharCodes(bytes.sublist(0, 4)) != 'RIFF') return null;
    final view = ByteData.sublistView(bytes);
    var offset = 12;
    int? dataStart, dataLength, channels, bits;
    while (offset + 8 <= bytes.length) {
      final id = String.fromCharCodes(bytes.sublist(offset, offset + 4));
      final size = view.getUint32(offset + 4, Endian.little);
      if (id == 'fmt ') {
        channels = view.getUint16(offset + 10, Endian.little);
        bits = view.getUint16(offset + 22, Endian.little);
      } else if (id == 'data') {
        dataStart = offset + 8;
        dataLength = math.min(size, bytes.length - dataStart);
        break;
      }
      offset += 8 + size + (size.isOdd ? 1 : 0);
    }
    if (dataStart == null || bits != 16 || channels == null || channels < 1) return null;
    final frames = dataLength! ~/ (2 * channels);
    if (frames < buckets) return null;
    final per = frames ~/ buckets;
    final out = Float32List(buckets * 2);
    var loudest = 1e-6;
    for (var b = 0; b < buckets; b++) {
      var lo = 0.0, hi = 0.0;
      for (var i = b * per; i < (b + 1) * per; i += 4) {
        final s = view.getInt16(dataStart + i * 2 * channels, Endian.little) / 32768.0;
        if (s < lo) lo = s;
        if (s > hi) hi = s;
      }
      out[b * 2] = lo;
      out[b * 2 + 1] = hi;
      loudest = math.max(loudest, math.max(-lo, hi));
    }
    for (var i = 0; i < out.length; i++) {
      out[i] /= loudest;
    }
    return out;
  } catch (_) {
    return null;
  }
}

/// A slow, decorative field of voice ribbons behind a screen. Paused under reduced motion.
class AmbientField extends StatefulWidget {
  const AmbientField({super.key, this.level = 0, this.height = 420});
  final double level;
  final double height;
  @override
  State<AmbientField> createState() => _AmbientFieldState();
}

class _AmbientFieldState extends State<AmbientField> with SingleTickerProviderStateMixin {
  late final AnimationController _t = AnimationController(vsync: this, duration: const Duration(seconds: 40));
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (context.calmMotion) {
      _t.stop();
      _t.value = 0.3;
    } else if (!_t.isAnimating) {
      _t.repeat();
    }
  }

  @override
  void dispose() {
    _t.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: RepaintBoundary(
          child: SizedBox(
            height: widget.height,
            width: double.infinity,
            child: CustomPaint(painter: _RibbonPainter(_t, context.palette, widget.level)),
          ),
        ),
      );
}

class _RibbonPainter extends CustomPainter {
  _RibbonPainter(this.t, this.p, this.level) : super(repaint: t);
  final Animation<double> t;
  final Palette p;
  final double level;

  @override
  void paint(Canvas canvas, Size size) {
    final time = t.value * 40;
    final shader = LinearGradient(colors: [p.voice1, p.voice2, p.voice3]).createShader(Offset.zero & size);
    for (var line = 0; line < 5; line++) {
      final depth = line / 4;
      final path = Path();
      final centre = size.height * (0.42 + line * 0.035);
      for (var x = 0.0; x <= size.width; x += 6) {
        final u = x / size.width;
        final envelope = math.pow(math.sin(math.pi * u), 1.3).toDouble();
        final amp = size.height * (0.12 + level * 0.25) * envelope;
        final y = centre +
            math.sin(u * (5.5 + line * 1.1) + time * (0.18 + line * 0.03) + line * 1.7) * amp * 0.7 +
            math.sin(u * 13 - time * 0.25 + line) * amp * 0.2;
        x == 0 ? path.moveTo(x, y) : path.lineTo(x, y);
      }
      final paint = Paint()
        ..shader = shader
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2 + (1 - depth) * 1.4
        ..color = Colors.white.withValues(alpha: (p.dark ? 0.55 : 0.35) * (1 - depth * 0.7));
      if (line == 0 && p.dark) {
        canvas.drawPath(path, Paint()
          ..shader = shader
          ..style = PaintingStyle.stroke
          ..strokeWidth = 6
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8)
          ..color = Colors.white.withValues(alpha: 0.35));
      }
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(_RibbonPainter old) => old.level != level || old.p != p;
}

/// The capture stage: ambient lines that swell with the microphone, the real waveform once a
/// WAV is chosen, and a reading sweep while a check runs.
class VoiceStage extends StatefulWidget {
  const VoiceStage({super.key, this.level = 0, this.peaks, this.scanning = false, this.height = 220});
  final double level;
  final Float32List? peaks;
  final bool scanning;
  final double height;
  @override
  State<VoiceStage> createState() => _VoiceStageState();
}

class _VoiceStageState extends State<VoiceStage> with TickerProviderStateMixin {
  late final AnimationController _t = AnimationController(vsync: this, duration: const Duration(seconds: 30));
  late final AnimationController _morph = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (context.calmMotion) {
      _t.value = 0.2;
    } else if (!_t.isAnimating) {
      _t.repeat();
    }
    _syncMorph();
  }

  @override
  void didUpdateWidget(VoiceStage old) {
    super.didUpdateWidget(old);
    if ((old.peaks == null) != (widget.peaks == null)) _syncMorph();
  }

  void _syncMorph() {
    final target = widget.peaks == null ? 0.0 : 1.0;
    if (context.calmMotion) {
      _morph.value = target;
    } else {
      _morph.animateTo(target, curve: Curves.easeOutExpo);
    }
  }

  @override
  void dispose() {
    _t.dispose();
    _morph.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: SizedBox(
          height: widget.height,
          width: double.infinity,
          child: CustomPaint(
            painter: _StagePainter(Listenable.merge([_t, _morph]), _t, _morph, context.palette, widget.level, widget.peaks, widget.scanning),
          ),
        ),
      );
}

class _StagePainter extends CustomPainter {
  _StagePainter(Listenable repaint, this.t, this.morph, this.p, this.level, this.peaks, this.scanning) : super(repaint: repaint);
  final Animation<double> t, morph;
  final Palette p;
  final double level;
  final Float32List? peaks;
  final bool scanning;

  @override
  void paint(Canvas canvas, Size size) {
    final time = t.value * 30;
    final m = morph.value;
    final shader = LinearGradient(colors: [p.voice1, p.voice2, p.voice3]).createShader(Offset.zero & size);
    final mid = size.height * (0.4 + 0.1 * m);

    if (m < 0.99) {
      for (var line = 0; line < 7; line++) {
        final depth = line / 6;
        final path = Path();
        for (var x = 0.0; x <= size.width; x += 4) {
          final u = x / size.width;
          final envelope = math.pow(math.sin(math.pi * u), 1.6).toDouble();
          final amp = (size.height * 0.16 + level * size.height * 0.34) * envelope * (0.45 + depth * 0.55);
          final y = mid +
              math.sin(u * (7 + line * 1.3) + time * (0.9 + line * 0.17) + line) * amp * 0.6 +
              math.sin(u * (17 - line) - time * 1.4 + line) * amp * 0.25 * (0.4 + level);
          x == 0 ? path.moveTo(x, y) : path.lineTo(x, y);
        }
        canvas.drawPath(
            path,
            Paint()
              ..shader = shader
              ..style = PaintingStyle.stroke
              ..strokeWidth = 1 + (1 - depth) * 1.4
              ..color = Colors.white.withValues(alpha: (1 - m) * (0.16 + (1 - depth) * 0.6)));
      }
    }

    final data = peaks;
    if (data != null && m > 0.01) {
      final buckets = data.length ~/ 2;
      final bar = size.width / buckets;
      final scanX = scanning ? (time * 0.32 % 1) * size.width : -1.0;
      for (var b = 0; b < buckets; b++) {
        final distance = (b / buckets - 0.5).abs() * 2;
        final reveal = ((m - distance * 0.6) / 0.4).clamp(0.0, 1.0);
        final top = math.max(0.02, data[b * 2 + 1]) * size.height * 0.4 * reveal;
        final bottom = math.max(0.02, -data[b * 2]) * size.height * 0.4 * reveal;
        final x = b * bar;
        final lit = scanX >= 0 && (x - scanX).abs() < 30;
        canvas.drawRRect(
          RRect.fromRectAndRadius(Rect.fromLTWH(x + bar * 0.2, mid - top, bar * 0.6, top + bottom), const Radius.circular(2)),
          Paint()
            ..shader = shader
            ..color = Colors.white.withValues(alpha: m * (lit ? 1 : scanning ? 0.45 : 0.9)),
        );
      }
      if (scanX >= 0) {
        canvas.drawRect(
          Rect.fromLTWH(scanX - 50, 0, 52, size.height),
          Paint()..shader = LinearGradient(colors: [p.voice3.withValues(alpha: 0), p.voice3.withValues(alpha: 0.55)]).createShader(Rect.fromLTWH(scanX - 50, 0, 52, size.height)),
        );
      }
    }
  }

  @override
  bool shouldRepaint(_StagePainter old) => old.level != level || old.peaks != peaks || old.scanning != scanning || old.p != p;
}

/// A small live waveform set inside a headline, like an inline image in type.
class InlineWave extends StatefulWidget {
  const InlineWave({super.key, this.height = 30});
  final double height;
  @override
  State<InlineWave> createState() => _InlineWaveState();
}

class _InlineWaveState extends State<InlineWave> with SingleTickerProviderStateMixin {
  late final AnimationController _t = AnimationController(vsync: this, duration: const Duration(seconds: 6));
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (context.calmMotion) {
      _t.value = 0.3;
    } else if (!_t.isAnimating) {
      _t.repeat();
    }
  }

  @override
  void dispose() {
    _t.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return ExcludeSemantics(
      child: Container(
        width: widget.height * 2.4,
        height: widget.height,
        padding: EdgeInsets.symmetric(horizontal: widget.height * 0.22),
        decoration: BoxDecoration(
          color: Color.alphaBlend(p.voice1.withValues(alpha: 0.22), p.panel),
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: p.voice3.withValues(alpha: 0.45)),
        ),
        child: AnimatedBuilder(
          animation: _t,
          builder: (_, __) {
            final time = _t.value * 6 * 2.1;
            return Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: List.generate(14, (i) {
                final envelope = math.sin(math.pi * (i + 0.5) / 14);
                final v = (0.2 + envelope * (0.35 + 0.4 * math.sin(time + i * 0.55).abs())).clamp(0.12, 1.0);
                return Container(
                  width: 2.6,
                  height: widget.height * 0.62 * v,
                  decoration: BoxDecoration(borderRadius: BorderRadius.circular(2), gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [p.voice3, p.voice1])),
                );
              }),
            );
          },
        ),
      ),
    );
  }
}

/// Fusion: three branch rows whose wires, thick as their weights, meet at the trust score.
class FusionWires extends StatefulWidget {
  const FusionWires({super.key, required this.weights, required this.tones, required this.abstains, required this.rowHeight});
  final List<double> weights;
  final List<Color> tones;
  final List<bool> abstains;
  final double rowHeight;
  @override
  State<FusionWires> createState() => _FusionWiresState();
}

class _FusionWiresState extends State<FusionWires> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1300));
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (context.calmMotion) {
      _c.value = 1;
    } else if (_c.value == 0) {
      Future.delayed(const Duration(milliseconds: 350), () { if (mounted) _c.forward(); });
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => CustomPaint(
        size: Size(56, widget.rowHeight * widget.weights.length),
        painter: _WirePainter(CurvedAnimation(parent: _c, curve: Curves.easeInOutCubic), widget),
      );
}

class _WirePainter extends CustomPainter {
  _WirePainter(this.a, this.w) : super(repaint: a);
  final Animation<double> a;
  final FusionWires w;
  @override
  void paint(Canvas canvas, Size size) {
    final mid = size.height / 2;
    canvas.save();
    canvas.clipRect(Rect.fromLTWH(0, 0, size.width * a.value, size.height));
    for (var i = 0; i < w.weights.length; i++) {
      final y = w.rowHeight * i + w.rowHeight / 2;
      final path = Path()
        ..moveTo(0, y)
        ..cubicTo(size.width * 0.55, y, size.width * 0.45, mid, size.width, mid);
      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round
        ..strokeWidth = 1.5 + w.weights[i] * 16
        ..color = w.tones[i].withValues(alpha: 0.7);
      if (w.abstains[i]) {
        for (final metric in path.computeMetrics()) {
          for (var d = 0.0; d < metric.length; d += 9) {
            canvas.drawPath(metric.extractPath(d, d + 2.5), paint..strokeWidth = 2.5);
          }
        }
      } else {
        canvas.drawPath(path, paint);
      }
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_WirePainter old) => true;
}

/// Synthetic-speech score per segment, against the per-segment threshold.
class SyntheticStrip extends StatelessWidget {
  const SyntheticStrip({super.key, required this.segments, required this.threshold});
  final List<({double start, double end, double score, bool synthetic})> segments;
  final double threshold;
  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Container(
      height: 104,
      decoration: BoxDecoration(color: p.raise, borderRadius: BorderRadius.circular(20), border: Border.all(color: p.line)),
      clipBehavior: Clip.antiAlias,
      child: CustomPaint(painter: _StripPainter(segments, threshold, p), size: Size.infinite),
    );
  }
}

class _StripPainter extends CustomPainter {
  _StripPainter(this.segments, this.threshold, this.p);
  final List<({double start, double end, double score, bool synthetic})> segments;
  final double threshold;
  final Palette p;
  @override
  void paint(Canvas canvas, Size size) {
    if (segments.isEmpty) return;
    final sorted = [...segments]..sort((a, b) => a.start.compareTo(b.start));
    final total = sorted.map((s) => s.end).reduce(math.max);
    if (total <= 0) return;
    for (var i = 0; i < sorted.length; i++) {
      final s = sorted[i];
      final end = i + 1 < sorted.length ? math.min(sorted[i + 1].start, s.end) : s.end;
      final left = s.start / total * size.width;
      final width = math.max(0.0, (end - s.start) / total * size.width - 3);
      final height = math.max(6.0, s.score.clamp(0, 1) * (size.height - 12));
      final rect = RRect.fromRectAndCorners(Rect.fromLTWH(left + 2, size.height - height, width, height), topLeft: const Radius.circular(6), topRight: const Radius.circular(6));
      canvas.drawRRect(rect, Paint()
        ..shader = s.synthetic
            ? LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [p.danger, p.danger.withValues(alpha: 0.5)]).createShader(rect.outerRect)
            : null
        ..color = s.synthetic ? p.danger : p.edge(p.neutral));
    }
    final y = size.height - threshold * (size.height - 12);
    final dash = Paint()
      ..color = p.danger.withValues(alpha: 0.8)
      ..strokeWidth = 1.2;
    for (var x = 0.0; x < size.width; x += 8) {
      canvas.drawLine(Offset(x, y), Offset(x + 4, y), dash);
    }
  }

  @override
  bool shouldRepaint(_StripPainter old) => old.segments != segments || old.p != p;
}
