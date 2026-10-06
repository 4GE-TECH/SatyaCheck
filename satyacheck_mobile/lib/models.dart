/// Dart mirrors of the parts of `contracts.py` the app actually reads.
///
/// Deliberately partial. `ScreeningResponse` has thirty-odd nested fields and the phone
/// needs a handful of them; parsing the rest would mean tracking a contract we do not use.
/// Every field here is `?`-tolerant, because a backend that adds or renames something must
/// degrade to "no verdict yet" rather than crash a call in progress.
library;

/// `contracts.TrustBand` — the four bands the UI can show.
enum TrustBand {
  /// Green. An enrolled person, verified.
  verified,

  /// Amber. Moderate risk, or an enrolled caller making an unusual request.
  caution,

  /// Orange. Elevated spoof or scam markers.
  suspicious,

  /// Red. Confirmed clone or severe scam intent.
  highRisk,

  /// Grey. Authority-check mode — nobody was verified, so green is not available.
  unverified,

  /// Grey. Below 1.5s of speech or 5 dB SNR; refusing to score is deliberate.
  insufficient;

  static TrustBand parse(String? wire) {
    switch (wire) {
      case 'verified':
        return TrustBand.verified;
      case 'caution':
        return TrustBand.caution;
      case 'suspicious':
        return TrustBand.suspicious;
      case 'high_risk':
        return TrustBand.highRisk;
      case 'unverified':
        return TrustBand.unverified;
      default:
        return TrustBand.insufficient;
    }
  }

  /// The traffic-light bucket this band belongs to.
  ///
  /// `unverified` and `insufficient` map to grey rather than green. This is the rule
  /// CLAUDE.md is most emphatic about: green means "we verified this person", and in
  /// authority-check mode we verified nobody. Showing green there would be a lie the user
  /// acts on.
  Signal get signal {
    switch (this) {
      case TrustBand.verified:
        return Signal.green;
      case TrustBand.caution:
        return Signal.amber;
      case TrustBand.suspicious:
      case TrustBand.highRisk:
        return Signal.red;
      case TrustBand.unverified:
      case TrustBand.insufficient:
        return Signal.grey;
    }
  }
}

enum Signal { green, amber, red, grey }

/// The `overlay_update` frame the WebSocket sends after each `screening_update`.
///
/// Not a `contracts.py` mirror — `server/ws_router.py` builds it, pre-flattened so the
/// overlay can be drawn without walking a whole `ScreeningResponse`. Only the two fields
/// the overlay renders are read.
class OverlayUpdate {
  const OverlayUpdate({required this.signal, this.evidence});

  /// `state` on the wire. Anything unrecognised is grey, never green.
  final Signal signal;

  /// The strongest incriminating phrase, or null when nothing stood out.
  final String? evidence;

  factory OverlayUpdate.fromJson(Map<String, dynamic> json) {
    final evidence = (json['evidence'] as String?)?.trim();
    return OverlayUpdate(
      signal: Signal.values.asNameMap()[json['state']] ?? Signal.grey,
      evidence: evidence == null || evidence.isEmpty ? null : evidence,
    );
  }
}

/// One line of evidence behind the score.
class ReasonCode {
  const ReasonCode({
    required this.code,
    required this.signal,
    required this.explanation,
    this.value,
    this.threshold,
    this.citationTitle,
    this.citationUrl,
    this.severity,
  });

  final String code;

  /// identity · authenticity · intent · quality
  final String signal;
  final String explanation;
  final String? value;

  /// The bar `value` was measured against, e.g. "> 40%".
  final String? threshold;
  final String? citationTitle;
  final String? citationUrl;
  final String? severity;

  factory ReasonCode.fromJson(Map<String, dynamic> json) => ReasonCode(
        code: json['code'] as String? ?? '',
        signal: json['signal'] as String? ?? '',
        explanation: json['explanation'] as String? ?? '',
        value: json['value'] as String?,
        threshold: json['threshold'] as String?,
        citationTitle: json['citation_title'] as String?,
        citationUrl: json['citation_url'] as String?,
        severity: json['severity'] as String?,
      );
}

/// What the app shows after screening a call.
class ScreeningResult {
  const ScreeningResult({
    required this.sessionId,
    required this.band,
    required this.trustScore,
    required this.mode,
    this.transcript = '',
    this.detectedLanguage = 'unknown',
    this.speakerVerdict = 'unknown',
    this.matchedPersonName,
    this.scriptRisk = 0.0,
    this.reasonCodes = const [],
    this.recommendedActions = const [],
    this.vernacularWarning,
    this.processingMs = 0,
  });

  final String sessionId;
  final TrustBand band;

  /// 0–100. Higher is safer — it is a *trust* score, not a risk score.
  final double trustScore;

  /// `identity_check` when someone enrolled is close; `authority_check` otherwise.
  final String mode;

  final String transcript;
  final String detectedLanguage;
  final String speakerVerdict;
  final String? matchedPersonName;
  final double scriptRisk;
  final List<ReasonCode> reasonCodes;
  final List<String> recommendedActions;

  /// Warning copy in the caller's own language, chosen by the backend for this band.
  final String? vernacularWarning;

  final int processingMs;

  Signal get signal => band.signal;

  /// Evidence worth putting in front of a frightened person, most severe first.
  List<ReasonCode> get evidence {
    const order = {'critical': 0, 'high': 1, 'medium': 2, 'info': 3, 'low': 4};
    final sorted = [...reasonCodes];
    sorted.sort((a, b) =>
        (order[a.severity] ?? 9).compareTo(order[b.severity] ?? 9));
    return sorted;
  }

  factory ScreeningResult.fromJson(Map<String, dynamic> json) {
    final fusion = (json['fusion'] as Map?)?.cast<String, dynamic>() ?? {};
    final transcript = (json['transcript'] as Map?)?.cast<String, dynamic>() ?? {};
    final speaker = (json['speaker'] as Map?)?.cast<String, dynamic>() ?? {};
    final script = (json['script'] as Map?)?.cast<String, dynamic>() ?? {};

    return ScreeningResult(
      sessionId: json['session_id'] as String? ?? '',
      band: TrustBand.parse(fusion['band'] as String?),
      trustScore: (fusion['trust_score'] as num?)?.toDouble() ?? 50.0,
      mode: fusion['mode'] as String? ?? 'authority_check',
      transcript: transcript['text'] as String? ?? '',
      detectedLanguage: transcript['detected_language'] as String? ?? 'unknown',
      speakerVerdict: speaker['verdict'] as String? ?? 'unknown',
      matchedPersonName: speaker['matched_person_name'] as String?,
      scriptRisk: (script['risk'] as num?)?.toDouble() ?? 0.0,
      reasonCodes: ((fusion['reason_codes'] as List?) ?? const [])
          .whereType<Map>()
          .map((e) => ReasonCode.fromJson(e.cast<String, dynamic>()))
          .toList(),
      recommendedActions: ((fusion['recommended_actions'] as List?) ?? const [])
          .map((e) => e.toString())
          .toList(),
      vernacularWarning: fusion['vernacular_warning'] as String?,
      processingMs: (json['processing_time_ms'] as num?)?.toInt() ?? 0,
    );
  }
}

/// One `verdict` from the backend's live feed, `/api/ws/live` (docs/LIVE_FEED.md, schema 1).
///
/// How the phone learns about its own Exotel calls. Exotel streams the call's audio
/// straight to the backend; the phone in the call cannot record it, because Android gives
/// the dialer the microphone (CLAUDE.md). The backend scores the call and publishes a
/// verdict about every 2 seconds of audio, plus one final one.
class LiveVerdict {
  const LiveVerdict({
    required this.sessionId,
    required this.isFinal,
    required this.signal,
    required this.result,
    this.windowIndex = 0,
    this.windowTrustScore,
    this.windowBand,
    this.escalated = false,
    this.authenticity = 'unavailable',
    this.callerNumber,
    this.threat,
    this.threatSector,
  });

  /// One call. Every call on the backend shares the feed, so verdicts are grouped by this.
  final String sessionId;

  /// True exactly once per call, on its last verdict.
  final bool isFinal;

  /// `overlay_state`: the colour to show, as the backend decided it.
  final Signal signal;

  /// The same verdict in the shape the rest of the app renders.
  final ScreeningResult result;

  /// 0, 1, 2… per call, one per ~2 s of audio. The final verdict may repeat the last one.
  final int windowIndex;

  /// This window's own score and band, before the session floor and latch. They move up
  /// and down, where the session's only ever fall: what a live gauge follows
  /// (docs/LIVE_FEED.md). Null from backends that do not send them.
  final double? windowTrustScore;
  final TrustBand? windowBand;

  /// The window's own view, falling back to the session's as the backend itself does.
  double get liveScore => windowTrustScore ?? result.trustScore;
  TrustBand get liveBand => windowBand ?? result.band;

  /// True when this verdict raised the call's warning level.
  final bool escalated;

  /// `synthetic` · `bonafide` · `unavailable`. Unavailable means the voice check did not
  /// run: "not measured", never "genuine".
  final String authenticity;

  /// The caller's number as Exotel reported it. Display only; never part of the score.
  final String? callerNumber;

  /// The scam it resembles, e.g. "KYC update fraud". Only on warning bands.
  final String? threat;

  /// The sector of that scam, e.g. "banking".
  final String? threatSector;

  /// `insufficient`: too little speech so far. "Listening", not a judgement.
  bool get listening => result.band == TrustBand.insufficient;

  /// Null for anything that is not a well-formed verdict.
  static LiveVerdict? tryParse(Map<String, dynamic> json) {
    if (json['type'] != 'verdict') return null;
    final sessionId = json['session_id'];
    if (sessionId is! String || sessionId.isEmpty) return null;
    final signals = (json['signals'] as Map?)?.cast<String, dynamic>() ?? {};
    final threat = (json['threat_label'] as Map?)?.cast<String, dynamic>();
    final caller = (json['caller_context'] as Map?)?.cast<String, dynamic>();
    return LiveVerdict(
      sessionId: sessionId,
      isFinal: json['is_final'] == true,
      signal: Signal.values.asNameMap()[json['overlay_state']] ?? Signal.grey,
      windowIndex: (json['window_index'] as num?)?.toInt() ?? 0,
      windowTrustScore: (json['window_trust_score'] as num?)?.toDouble(),
      windowBand: json['window_band'] is String
          ? TrustBand.parse(json['window_band'] as String)
          : null,
      escalated: json['escalated'] == true,
      authenticity: signals['authenticity'] as String? ?? 'unavailable',
      callerNumber: caller?['claimed_number'] as String?,
      threat: threat?['threat'] as String?,
      threatSector: threat?['sector'] as String?,
      result: ScreeningResult(
        sessionId: sessionId,
        band: TrustBand.parse(json['band'] as String?),
        trustScore: (json['trust_score'] as num?)?.toDouble() ?? 50.0,
        mode: json['mode'] as String? ?? 'authority_check',
        transcript: json['transcript'] as String? ?? '',
        detectedLanguage: json['language'] as String? ?? 'unknown',
        speakerVerdict: signals['identity'] as String? ?? 'unknown',
        scriptRisk: (signals['intent_risk'] as num?)?.toDouble() ?? 0.0,
        reasonCodes: ((json['reason_codes'] as List?) ?? const [])
            .whereType<Map>()
            .map((e) => ReasonCode.fromJson(e.cast<String, dynamic>()))
            .toList(),
        recommendedActions: ((json['recommended_actions'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
        vernacularWarning: json['vernacular_warning'] as String?,
      ),
    );
  }
}

/// Someone with a stored voiceprint.
class EnrolledPerson {
  const EnrolledPerson({
    required this.personId,
    required this.name,
    required this.relation,
  });

  final String personId;
  final String name;
  final String relation;
}

/// The result of trying to enrol a voice.
///
/// Carries the backend's own message on failure rather than a generic one. "Need at least
/// 15.0s of speech. Got 9.2s." tells the user what to do differently; "enrollment failed"
/// does not.
class EnrollOutcome {
  const EnrollOutcome.success({required this.personId, required this.name})
      : error = null;

  const EnrollOutcome.failure(this.error)
      : personId = null,
        name = null;

  final String? personId;
  final String? name;
  final String? error;

  bool get ok => error == null;
}

/// A screened call, as the history list shows it.
class CallRecord {
  CallRecord({
    required this.startedAt,
    this.number,
    this.result,
    this.error,
  });

  final DateTime startedAt;
  final String? number;
  ScreeningResult? result;
  String? error;

  Signal get signal => result?.signal ?? Signal.grey;
}
