import 'package:flutter/foundation.dart';

import 'models.dart';

/// One call seen on the backend's live feed: every verdict it has had so far.
class LiveCall {
  const LiveCall({
    required this.sessionId,
    required this.firstSeen,
    required this.lastSeen,
    required this.latest,
    required this.windows,
  });

  final String sessionId;

  /// When this phone saw the call's first and latest verdicts.
  final DateTime firstSeen;
  final DateTime lastSeen;

  final LiveVerdict latest;

  /// One verdict per scoring window, oldest first. The final verdict replaces a repeated
  /// window index rather than adding one.
  final List<LiveVerdict> windows;

  bool get ended => latest.isFinal;
}

/// The calls on the live feed, newest first — what the app's live view draws, as the
/// dashboard's Live calls page does (web/src/hooks/useLiveFeed.ts).
///
/// Memory only. The feed replays nothing, so this holds what arrived while the app ran.
class LiveCalls extends ValueNotifier<List<LiveCall>> {
  LiveCalls() : super(const []);

  /// Calls kept. Older ones drop off; the backend keeps their reports.
  static const _maxCalls = 20;

  void add(LiveVerdict verdict) {
    final now = DateTime.now();
    final calls = value;
    final i = calls.indexWhere((c) => c.sessionId == verdict.sessionId);
    if (i == -1) {
      value = [
        LiveCall(
          sessionId: verdict.sessionId,
          firstSeen: now,
          lastSeen: now,
          latest: verdict,
          windows: [verdict],
        ),
        ...calls,
      ].take(_maxCalls).toList();
      return;
    }
    final old = calls[i];
    final last = old.windows.isEmpty ? null : old.windows.last;
    final windows = last != null && last.windowIndex == verdict.windowIndex
        ? [...old.windows.sublist(0, old.windows.length - 1), verdict]
        : [...old.windows, verdict];
    final updated = LiveCall(
      sessionId: old.sessionId,
      firstSeen: old.firstSeen,
      lastSeen: now,
      latest: verdict,
      windows: windows,
    );
    value = [for (var j = 0; j < calls.length; j++) j == i ? updated : calls[j]];
  }
}
