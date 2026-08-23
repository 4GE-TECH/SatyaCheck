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

/// One line of evidence behind the score.
class ReasonCode {
  const ReasonCode({
    required this.code,
    required this.signal,
    required this.explanation,
    this.value,
    this.citationTitle,
    this.citationUrl,
    this.severity,
  });

  final String code;

  /// identity · authenticity · intent · quality
  final String signal;
  final String explanation;
  final String? value;
  final String? citationTitle;
  final String? citationUrl;
  final String? severity;

  factory ReasonCode.fromJson(Map<String, dynamic> json) => ReasonCode(
        code: json['code'] as String? ?? '',
        signal: json['signal'] as String? ?? '',
        explanation: json['explanation'] as String? ?? '',
        value: json['value'] as String?,
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
