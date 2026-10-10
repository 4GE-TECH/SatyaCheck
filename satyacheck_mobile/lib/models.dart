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

/// `contracts.ThreatLabel`: which kind of fraud the call resembles. A pattern, never a verdict.
class ThreatLabel {
  const ThreatLabel({required this.sector, required this.threat, required this.family});

  final String sector;
  final String threat;
  final String family;

  /// `banking`, `law_enforcement_impersonation` become readable words.
  String get sectorText => sector.replaceAll('_', ' ');

  static ThreatLabel? fromJson(Object? json) {
    if (json is! Map) return null;
    final threat = json['threat'];
    if (threat is! String || threat.isEmpty) return null;
    return ThreatLabel(
      sector: json['sector'] as String? ?? '',
      threat: threat,
      family: json['family'] as String? ?? '',
    );
  }
}

/// The caller ID as received (`contracts.CallerMetadata`). Explanation only: never scored.
String? callerIdFrom(Object? json) {
  if (json is! Map) return null;
  final number = json['claimed_number'], name = json['claimed_name'];
  if (number is String && number.isNotEmpty) return number;
  if (name is String && name.isNotEmpty) return name;
  return null;
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
    this.threatLabel,
    this.callerId,
    this.channel,
    this.raw = const {},
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

  /// The kind of fraud the call resembles, on warning bands with a cited playbook.
  final ThreatLabel? threatLabel;

  /// Caller ID as received from the phone network. Never part of the score.
  final String? callerId;

  /// `telephony` for calls screened through Exotel, `upload` for files, and so on.
  final String? channel;

  final Map<String, dynamic> raw;

  Signal get signal => band.signal;

  /// Evidence worth putting in front of a frightened person, most severe first.
  List<ReasonCode> get evidence {
    const order = {'critical': 0, 'high': 1, 'medium': 2, 'info': 3, 'low': 4};
    final sorted = [...reasonCodes];
    sorted.sort(
        (a, b) => (order[a.severity] ?? 9).compareTo(order[b.severity] ?? 9));
    return sorted;
  }

  factory ScreeningResult.fromJson(Map<String, dynamic> json) {
    final fusion = (json['fusion'] as Map?)?.cast<String, dynamic>() ?? {};
    final transcript =
        (json['transcript'] as Map?)?.cast<String, dynamic>() ?? {};
    final speaker = (json['speaker'] as Map?)?.cast<String, dynamic>() ?? {};
    final script = (json['script'] as Map?)?.cast<String, dynamic>() ?? {};
    final quality = (json['quality'] as Map?)?.cast<String, dynamic>() ?? {};
    var safeBand = TrustBand.parse(fusion['band'] as String?);
    if (quality['passed'] != true) {
      safeBand = TrustBand.insufficient;
    } else if (safeBand == TrustBand.verified &&
        (fusion['mode'] != 'identity_check' || speaker['verdict'] != 'match')) {
      safeBand = TrustBand.unverified;
    }

    return ScreeningResult(
      sessionId: json['session_id'] as String? ?? '',
      band: safeBand,
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
      threatLabel: ThreatLabel.fromJson(fusion['threat_label']),
      callerId: callerIdFrom(json['caller_context']),
      channel: (json['caller_context'] as Map?)?['channel_type'] as String?,
      raw: json,
    );
  }
}

/// Someone with a stored voiceprint.
class EnrolledPerson {
  const EnrolledPerson({
    required this.personId,
    required this.name,
    required this.relation,
    this.aliases = const [],
    this.phoneNumbers = const [],
  });

  final String personId;
  final String name;
  final String relation;

  /// What callers call them ("Papa"), and numbers they call from. Hints, never proof.
  final List<String> aliases;
  final List<String> phoneNumbers;
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

/// One message from the live verdict feed, `/api/ws/live` (docs/LIVE_FEED.md, schema 1).
///
/// Exotel calls stream from Exotel straight to the backend; the phone only watches verdicts.
class LiveVerdict {
  const LiveVerdict({
    required this.sessionId,
    required this.windowIndex,
    required this.isFinal,
    required this.escalated,
    required this.band,
    required this.overlay,
    required this.trustScore,
    required this.mode,
    required this.identity,
    required this.authenticity,
    required this.intentRisk,
    this.windowTrustScore,
    this.reasonCodes = const [],
    this.transcript = '',
    this.language = 'unknown',
    this.callerId,
    this.threatLabel,
    this.recommendedActions = const [],
    this.vernacularWarning,
  });

  final String sessionId;
  final int windowIndex;
  final bool isFinal;

  /// This verdict raised the call's warning level.
  final bool escalated;
  final TrustBand band;

  /// The colour the backend says to show, used as-is rather than re-derived from the band.
  final Signal overlay;

  /// The session score: never rises during a call.
  final double trustScore;

  /// This window's own score before the session floor; moves up and down.
  final double? windowTrustScore;
  final String mode;
  final String identity;
  final String authenticity;
  final double intentRisk;
  final List<ReasonCode> reasonCodes;
  final String transcript;
  final String language;
  final String? callerId;
  final ThreatLabel? threatLabel;
  final List<String> recommendedActions;
  final String? vernacularWarning;

  static const _overlay = {'green': Signal.green, 'amber': Signal.amber, 'red': Signal.red};

  /// Null for anything that is not a well-formed verdict, so a stray frame is ignored.
  static LiveVerdict? fromJson(Object? decoded) {
    if (decoded is! Map || decoded['type'] != 'verdict') return null;
    final session = decoded['session_id'], trust = decoded['trust_score'];
    if (session is! String || session.isEmpty || trust is! num) return null;
    final signals = (decoded['signals'] as Map?) ?? const {};
    var overlay = _overlay[decoded['overlay_state']] ?? Signal.grey;
    // Green means "we verified this person". Never show it for a stranger check.
    if (overlay == Signal.green && decoded['mode'] != 'identity_check') overlay = Signal.grey;
    return LiveVerdict(
      sessionId: session,
      windowIndex: (decoded['window_index'] as num?)?.toInt() ?? 0,
      isFinal: decoded['is_final'] == true,
      escalated: decoded['escalated'] == true,
      band: TrustBand.parse(decoded['band'] as String?),
      overlay: overlay,
      trustScore: trust.toDouble(),
      windowTrustScore: (decoded['window_trust_score'] as num?)?.toDouble(),
      mode: decoded['mode'] as String? ?? 'authority_check',
      identity: signals['identity'] as String? ?? 'unknown',
      authenticity: signals['authenticity'] as String? ?? 'unavailable',
      intentRisk: (signals['intent_risk'] as num?)?.toDouble() ?? 0,
      reasonCodes: ((decoded['reason_codes'] as List?) ?? const [])
          .whereType<Map>()
          .map((e) => ReasonCode.fromJson(e.cast<String, dynamic>()))
          .toList(),
      transcript: decoded['transcript'] as String? ?? '',
      language: decoded['language'] as String? ?? 'unknown',
      callerId: callerIdFrom(decoded['caller_context']),
      threatLabel: ThreatLabel.fromJson(decoded['threat_label']),
      recommendedActions: ((decoded['recommended_actions'] as List?) ?? const []).map((e) => e.toString()).toList(),
      vernacularWarning: decoded['vernacular_warning'] as String?,
    );
  }

  /// Evidence worth showing, most severe first, with info lines left out.
  List<ReasonCode> get evidence {
    const order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3};
    final sorted = reasonCodes.where((r) => r.severity != 'info').toList();
    sorted.sort((a, b) => (order[a.severity] ?? 9).compareTo(order[b.severity] ?? 9));
    return sorted;
  }
}

/// One phone call on the live feed, built up from its verdicts.
class LiveCall {
  LiveCall(this.latest)
      : startedAt = DateTime.now(),
        updatedAt = DateTime.now(),
        escalations = latest.escalated ? 1 : 0;

  LiveVerdict latest;
  final DateTime startedAt;
  DateTime updatedAt;
  int escalations;
  bool get ended => latest.isFinal;

  void add(LiveVerdict verdict) {
    // A late non-final verdict after the final one must not reopen the call.
    if (!latest.isFinal || verdict.isFinal) latest = verdict;
    updatedAt = DateTime.now();
    if (verdict.escalated) escalations++;
  }
}
