import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'auth.dart';
import 'models.dart';

/// Talks to the SatyaCheck backend. The only part of the app that makes network calls.
///
/// Two paths, because the backend offers two and they serve different moments:
///
///   * **`/api/ws/screen/{id}`** — a WebSocket. Chunks go up as the call proceeds and a
///     rescored verdict comes back every few seconds. This is what drives the live overlay,
///     and it is the only way the user learns something *during* the call, which is the
///     only time the warning can still change what they do.
///
///   * **`POST /api/screen`** — one multipart WAV, one verdict. Used as the fallback when
///     the socket cannot be established, and for screening a recording after the fact.
///
/// Everything here degrades rather than throws. A backend that is down, slow or on another
/// subnet must leave the call untouched — a screening app that interferes with answering
/// the phone is worse than no screening app.
class ApiClient {
  ApiClient({String? baseUrl, AuthSession? auth})
      : _baseUrl = baseUrl ?? defaultBaseUrl,
        auth = auth ?? AuthSession();

  /// Who is signed in. Every request carries its token; a 401 signs out.
  final AuthSession auth;

  /// Where the backend lives, from the phone's point of view.
  ///
  /// Defaults to `localhost:8000` because the intended transport is a **USB tunnel**:
  ///
  ///     adb reverse tcp:8000 tcp:8000
  ///
  /// That makes the phone's own `localhost:8000` resolve to the laptop's, over the USB
  /// cable. It is the most reliable option and usually the only one that works at a venue:
  /// it needs no Wi-Fi, survives the laptop being on Ethernet, and is unaffected by the
  /// Windows firewall — none of which is true of a LAN address.
  ///
  /// For Wi-Fi instead, pass the laptop's LAN IP (never `localhost` — on a phone that
  /// means the phone):
  ///
  ///     flutter run --dart-define=SATYACHECK_BACKEND=http://192.168.1.42:8000
  ///
  /// On the Android emulator the host's loopback is `10.0.2.2`.
  static const defaultBaseUrl = String.fromEnvironment(
    'SATYACHECK_BACKEND',
    defaultValue: 'http://localhost:8000',
  );

  /// Token for the live call feed, when the backend sets `LIVE_FEED_TOKEN`.
  ///
  ///     flutter run --dart-define=SATYACHECK_LIVE_TOKEN=...
  ///
  /// It can also be typed in the Calls tab; that copy lives in memory only.
  static const defaultLiveToken = String.fromEnvironment('SATYACHECK_LIVE_TOKEN');

  final String _baseUrl;

  String get baseUrl => _baseUrl;

  /// `http://` becomes `ws://` and `https://` becomes `wss://`, so a Cloudflare tunnel works as-is.
  String get _wsBase => _baseUrl.replaceFirst(RegExp('^http'), 'ws');
  String? peopleError;
  String? screeningError;

  static const signedOutMessage = 'Your sign-in has expired. Sign in again to continue.';

  /// Adds the signed-in account's token. Without sign-in the backend's dev mode applies.
  Future<void> _authorize(HttpClientRequest request) async {
    final token = await auth.accessToken();
    if (token != null) request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
  }

  /// A 401 means the token is no longer accepted: forget it so the app asks to sign in.
  bool _expired(int status) {
    if (status != 401) return false;
    auth.signOut();
    return true;
  }

  /// Sockets sign in with their first message, never the URL (URLs end up in logs).
  Future<void> _authorizeSocket(WebSocket socket) async {
    final token = await auth.accessToken();
    if (token != null) socket.add(jsonEncode({'type': 'auth', 'token': token}));
  }

  /// Is the backend reachable? Short timeout: this is called before a call is answered.
  Future<bool> ping() async {
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 3);
    try {
      final request = await client.getUrl(Uri.parse('$_baseUrl/api/health'));
      final response =
          await request.close().timeout(const Duration(seconds: 3));
      await response.drain<void>();
      return response.statusCode == 200;
    } catch (_) {
      return false;
    } finally {
      client.close(force: true);
    }
  }

  /// Screen one complete WAV and return the verdict.
  ///
  /// `wav` must carry a real RIFF header — the backend normalises with ffmpeg, and ffmpeg
  /// cannot infer sample rate or bit depth from bare PCM. `AudioChunk.toWav()` writes one.
  Future<ScreeningResult?> screenWav(
    Uint8List wav, {
    String filename = 'call.wav',
    String? claimedNumber,
    String? claimedIdentity,
    Duration timeout = const Duration(seconds: 60),
  }) async {
    screeningError = null;
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);
    try {
      final boundary = '----satyacheck${DateTime.now().microsecondsSinceEpoch}';
      final request = await client.postUrl(Uri.parse('$_baseUrl/api/screen'));
      await _authorize(request);
      request.headers.set(HttpHeaders.contentTypeHeader,
          'multipart/form-data; boundary=$boundary');

      final head = StringBuffer()
        ..write('--$boundary\r\n')
        ..write('Content-Disposition: form-data; name="channel_type"\r\n\r\n')
        ..write('upload\r\n');
      if (claimedNumber != null && claimedNumber.isNotEmpty) {
        head
          ..write('--$boundary\r\n')
          ..write(
              'Content-Disposition: form-data; name="claimed_number"\r\n\r\n')
          ..write('$claimedNumber\r\n');
      }
      // "Who's calling?": the person the caller says they are. Checked, never trusted.
      if (claimedIdentity != null && claimedIdentity.isNotEmpty) {
        head
          ..write('--$boundary\r\n')
          ..write('Content-Disposition: form-data; name="claimed_identity"\r\n\r\n')
          ..write('$claimedIdentity\r\n');
      }
      head
        ..write('--$boundary\r\n')
        ..write(
            'Content-Disposition: form-data; name="file"; filename="$filename"\r\n')
        ..write('Content-Type: application/octet-stream\r\n\r\n');

      request.add(utf8.encode(head.toString()));
      request.add(wav);
      request.add(utf8.encode('\r\n--$boundary--\r\n'));

      final response = await request.close().timeout(timeout);
      final body =
          await response.transform(utf8.decoder).join().timeout(timeout);
      if (_expired(response.statusCode)) {
        screeningError = signedOutMessage;
        return null;
      }
      if (response.statusCode != 200) {
        final decoded = jsonDecode(body);
        screeningError = decoded is Map && decoded['detail'] is String
            ? decoded['detail'] as String
            : 'The service could not check this recording. Please try again.';
        debugPrint('SatyaCheck screening: HTTP ${response.statusCode}');
        return null;
      }
      final payload = jsonDecode(body) as Map<String, dynamic>;
      final fusion = payload['fusion'];
      if (payload['session_id'] is! String ||
          (payload['session_id'] as String).isEmpty ||
          payload['quality'] is! Map ||
          payload['speaker'] is! Map ||
          fusion is! Map ||
          fusion['trust_score'] is! num ||
          !(fusion['trust_score'] as num).isFinite ||
          fusion['reason_codes'] is! List ||
          fusion['recommended_actions'] is! List) {
        debugPrint('SatyaCheck screening: incomplete result payload');
        screeningError =
            'The service returned an incomplete result. No verdict is available. Please try again.';
        return null;
      }
      return ScreeningResult.fromJson(payload);
    } catch (error) {
      debugPrint('SatyaCheck screening unavailable: $error');
      screeningError =
          'The screening service did not return a complete result. Check your connection and try again.';
      return null;
    } finally {
      client.close(force: true);
    }
  }

  /// Enrol a voice from a recorded WAV.
  ///
  /// Returns the person's name on success, or an error message the UI can show. The
  /// backend's rejections are the useful part here — "Need at least 15.0s of speech.
  /// Got 9.2s." tells the user exactly what to do differently, so it is passed through
  /// rather than flattened into "enrollment failed".
  Future<EnrollOutcome> enroll({
    required String wavPath,
    required String name,
    required String relation,
    required bool consent,
    List<String> aliases = const [],
    List<String> phoneNumbers = const [],
  }) async {
    final file = File(wavPath);
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);
    try {
      if (!await file.exists()) {
        debugPrint('SatyaCheck enrollment: recording no longer available');
        return const EnrollOutcome.failure('The recording was not saved.');
      }
      final bytes = await file.readAsBytes();
      final boundary = '----satyacheck${DateTime.now().microsecondsSinceEpoch}';
      final request = await client.postUrl(Uri.parse('$_baseUrl/api/enroll'));
      await _authorize(request);
      request.headers.set(HttpHeaders.contentTypeHeader,
          'multipart/form-data; boundary=$boundary');

      String field(String key, String value) =>
          '--$boundary\r\nContent-Disposition: form-data; name="$key"\r\n\r\n$value\r\n';

      // The backend records when consent was given; a voiceprint is biometric data.
      request.add(utf8.encode(field('name', name) +
          field('relation', relation) +
          field('consent', consent ? 'true' : 'false') +
          [for (final a in aliases) if (a.trim().isNotEmpty) field('aliases', a.trim())].join() +
          [for (final n in phoneNumbers) if (n.trim().isNotEmpty) field('phone_numbers', n.trim())].join()));
      request.add(utf8.encode(
        '--$boundary\r\n'
        'Content-Disposition: form-data; name="file"; filename="enrollment.wav"\r\n'
        'Content-Type: audio/wav\r\n\r\n',
      ));
      request.add(bytes);
      request.add(utf8.encode('\r\n--$boundary--\r\n'));

      final response =
          await request.close().timeout(const Duration(seconds: 120));
      final body = await response
          .transform(utf8.decoder)
          .join()
          .timeout(const Duration(seconds: 120));

      if (_expired(response.statusCode)) return const EnrollOutcome.failure(signedOutMessage);
      if (response.statusCode == 201) {
        final json = jsonDecode(body) as Map<String, dynamic>;
        if (json['person_id'] is! String ||
            (json['person_id'] as String).isEmpty ||
            json['voiceprints'] is! List ||
            (json['voiceprints'] as List).isEmpty) {
          debugPrint('SatyaCheck enrollment: 201 without a saved voiceprint');
          return const EnrollOutcome.failure(
              'The service did not confirm a saved voiceprint. Please record again and retry.');
        }
        return EnrollOutcome.success(
          personId: json['person_id'] as String? ?? '',
          name: json['name'] as String? ?? name,
        );
      }

      // FastAPI puts the human-readable reason in `detail`.
      try {
        final detail = (jsonDecode(body) as Map<String, dynamic>)['detail'];
        return EnrollOutcome.failure(
            detail is String ? detail : detail.toString());
      } catch (_) {
        return EnrollOutcome.failure('Server said ${response.statusCode}.');
      }
    } catch (exc) {
      return EnrollOutcome.failure('Could not reach the server ($exc).');
    } finally {
      client.close(force: true);
    }
  }

  /// Who is enrolled right now.
  Future<List<EnrolledPerson>> persons() async {
    peopleError = null;
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
    try {
      final request = await client.getUrl(Uri.parse('$_baseUrl/api/persons'));
      await _authorize(request);
      final response =
          await request.close().timeout(const Duration(seconds: 10));
      final body = await response.transform(utf8.decoder).join();
      if (_expired(response.statusCode)) {
        peopleError = signedOutMessage;
        return const [];
      }
      if (response.statusCode != 200) {
        peopleError = 'Known voices could not be loaded. Please try again.';
        debugPrint('SatyaCheck persons: HTTP ${response.statusCode}');
        return const [];
      }
      final decoded = jsonDecode(body);
      final list =
          decoded is List ? decoded : (decoded['persons'] as List? ?? const []);
      return list
          .whereType<Map>()
          .map((e) => EnrolledPerson(
                personId: e['person_id'] as String? ?? '',
                name: e['name'] as String? ?? '',
                relation: e['relation'] as String? ?? '',
                aliases: [for (final a in (e['aliases'] as List? ?? const [])) if (a is String) a],
                phoneNumbers: [for (final n in (e['phone_numbers'] as List? ?? const [])) if (n is String) n],
              ))
          .toList();
    } catch (error) {
      debugPrint('SatyaCheck persons unavailable: $error');
      peopleError =
          'Known voices could not be loaded. Check the service connection.';
      return const [];
    } finally {
      client.close(force: true);
    }
  }

  /// The stored final verdict of a finished call, for its full report. Null when unavailable.
  Future<ScreeningResult?> screening(String sessionId) async {
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
    try {
      final request = await client.getUrl(Uri.parse('$_baseUrl/api/screen/${Uri.encodeComponent(sessionId)}'));
      await _authorize(request);
      final response = await request.close().timeout(const Duration(seconds: 15));
      final body = await response.transform(utf8.decoder).join();
      _expired(response.statusCode);
      if (response.statusCode != 200) {
        debugPrint('SatyaCheck screening $sessionId: HTTP ${response.statusCode}');
        return null;
      }
      final json = jsonDecode(body);
      if (json is! Map || json['fusion'] is! Map || json['quality'] is! Map) return null;
      return ScreeningResult.fromJson(json.cast<String, dynamic>());
    } catch (error) {
      debugPrint('SatyaCheck screening $sessionId unavailable: $error');
      return null;
    } finally {
      client.close(force: true);
    }
  }

  /// Watch the live verdict feed (`/api/ws/live`). Throws when the socket cannot be opened.
  Future<LiveFeedSocket> openLiveFeed({String token = ''}) async {
    final query = token.isEmpty ? '' : '?token=${Uri.encodeQueryComponent(token)}';
    final socket = await WebSocket.connect('$_wsBase/api/ws/live$query').timeout(const Duration(seconds: 8));
    await _authorizeSocket(socket);
    return LiveFeedSocket._(socket);
  }

  /// Open a streaming screening session. Returns null if the socket cannot be opened.
  Future<ScreeningSocket?> openStream(String sessionId) async {
    try {
      final url = '$_wsBase/api/ws/screen/$sessionId';
      final socket =
          await WebSocket.connect(url).timeout(const Duration(seconds: 8));
      await _authorizeSocket(socket);
      return ScreeningSocket._(socket, sessionId);
    } catch (_) {
      return null;
    }
  }

  // --- people and app-to-app calls (webrtc/BACKEND_API.md) ----------------------------

  /// Why the last people or call request failed, in words for the person holding the phone.
  String? rtcError;

  /// Your username, or null before you have chosen one. Throws nothing; on a failure
  /// [rtcError] is set and the result is [ProfileLookup.failed].
  Future<ProfileLookup> myProfile() async {
    final reply = await _rtc('GET', '/api/profile', allow: const {404});
    if (reply == null) return const ProfileLookup.failed();
    if (reply.status == 404) return const ProfileLookup.none();
    return ProfileLookup.found(RtcPerson.fromJson(reply.map));
  }

  /// Choose or change your username. Null on failure, with [rtcError] set.
  Future<RtcPerson?> saveProfile(String username, String displayName) async {
    final reply = await _rtc('PUT', '/api/profile', body: {'username': username, 'display_name': displayName},
        statusText: const {409: 'That username is taken. Choose another.'});
    return reply == null ? null : RtcPerson.fromJson(reply.map);
  }

  /// Usernames starting with [query], with your relation to each. Null on failure.
  Future<List<RtcPerson>?> searchPeople(String query) async {
    final reply = await _rtc('GET', '/api/users/search?q=${Uri.encodeQueryComponent(query.trim())}',
        statusText: const {429: 'Too many searches. Wait a minute, then try again.'});
    if (reply == null) return null;
    return [for (final p in reply.list) if (p is Map) RtcPerson.fromJson(p.cast<String, dynamic>())];
  }

  /// Connected people, requests to you, and your requests. Null on failure.
  Future<RtcConnections?> connections() async {
    final reply = await _rtc('GET', '/api/connections');
    return reply == null ? null : RtcConnections.fromJson(reply.map);
  }

  /// Ask to connect. If they already asked you, this connects you. Null on failure.
  Future<RtcPerson?> requestConnection(String userId) async {
    final reply = await _rtc('POST', '/api/connections', body: {'user_id': userId}, expect: 201, statusText: const {
      409: 'Choose your username first.',
      429: 'Too many connect requests. Try again later.',
    });
    return reply == null ? null : RtcPerson.fromJson(reply.map);
  }

  Future<RtcPerson?> acceptConnection(String userId) async {
    final reply = await _rtc('POST', '/api/connections/${Uri.encodeComponent(userId)}/accept',
        statusText: const {404: 'That request is no longer there.'});
    return reply == null ? null : RtcPerson.fromJson(reply.map);
  }

  /// Decline their request, cancel yours, or disconnect.
  Future<bool> removeConnection(String userId) async =>
      await _rtc('DELETE', '/api/connections/${Uri.encodeComponent(userId)}', expect: 204) != null;

  /// Ring a connection. Null on failure, with [rtcError] set.
  Future<RtcCallTicket?> placeCall(String calleeId) async {
    final reply = await _rtc('POST', '/api/webrtc/calls', body: {'callee_id': calleeId}, expect: 201, statusText: const {
      403: 'You can call only people you are connected with.',
      503: 'The screening service is at capacity. Try again in a minute.',
    });
    return reply == null ? null : RtcCallTicket.fromJson(reply.map);
  }

  /// Calls ringing for you right now. Null when the service cannot be asked, and
  /// [IncomingCalls.unavailable] when this service has no app calls.
  Future<IncomingCalls?> incomingCalls() async {
    final reply = await _rtc('GET', '/api/webrtc/incoming', quiet: true, allow: const {404});
    if (reply == null) return null;
    if (reply.status == 404) return const IncomingCalls.unavailable();
    return IncomingCalls.fromJson(reply.map);
  }

  /// Answer a ringing call. Null on failure, with [rtcError] set.
  Future<RtcCallTicket?> acceptCall(String callId) async {
    final reply = await _rtc('POST', '/api/webrtc/calls/${Uri.encodeComponent(callId)}/accept',
        statusText: const {404: 'This call is no longer ringing.'});
    return reply == null ? null : RtcCallTicket.fromJson(reply.map);
  }

  /// A fresh room ticket for a call this phone is already in, after its connection dropped
  /// for good (room tokens are short-lived). Null when the call is over or unreachable.
  Future<RtcCallTicket?> rejoinCall(String callId) async {
    final reply = await _rtc('POST', '/api/webrtc/calls/${Uri.encodeComponent(callId)}/rejoin', quiet: true);
    return reply == null ? null : RtcCallTicket.fromJson(reply.map);
  }

  Future<void> declineCall(String callId) async {
    await _rtc('POST', '/api/webrtc/calls/${Uri.encodeComponent(callId)}/decline', expect: 204, quiet: true);
  }

  /// The call's state, for either party. Null when it cannot be read right now.
  Future<RtcCallState?> rtcCallState(String callId) async {
    final reply = await _rtc('GET', '/api/webrtc/calls/${Uri.encodeComponent(callId)}', quiet: true);
    return reply == null ? null : RtcCallState.fromJson(reply.map);
  }

  /// Cancel or hang up, for both people. Best effort: hanging up locally never waits on this.
  Future<void> endRtcCall(String callId) async {
    await _rtc('DELETE', '/api/webrtc/calls/${Uri.encodeComponent(callId)}', expect: 204, quiet: true);
  }

  /// One request. Null on failure (with [rtcError] set unless [quiet]); otherwise the
  /// status, which is [expect] or one of [allow], and the decoded body.
  Future<_Reply?> _rtc(String method, String path,
      {Object? body, int expect = 200, Set<int> allow = const {}, Map<int, String> statusText = const {}, bool quiet = false}) async {
    if (!quiet) rtcError = null;
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 8);
    try {
      final request = await client.openUrl(method, Uri.parse('$_baseUrl$path'));
      await _authorize(request);
      if (body != null) {
        request.headers.contentType = ContentType.json;
        request.add(utf8.encode(jsonEncode(body)));
      }
      final response = await request.close().timeout(const Duration(seconds: 15));
      final text = await response.transform(utf8.decoder).join().timeout(const Duration(seconds: 15));
      final status = response.statusCode;
      if (status == expect || allow.contains(status)) {
        return _Reply(status, text.isEmpty || status == 204 ? null : jsonDecode(text));
      }
      debugPrint('SatyaCheck people/call $method $path: HTTP $status');
      if (!quiet) {
        rtcError = _expired(status)
            ? signedOutMessage
            : statusText[status] ??
                (status == 404 && (path.startsWith('/api/webrtc') || path.startsWith('/api/profile'))
                    ? 'App calls are not switched on for this service.'
                    : _detail(text) ?? 'Something went wrong (HTTP $status). Please try again.');
      }
      return null;
    } catch (error) {
      debugPrint('SatyaCheck people/call $method $path unavailable: $error');
      if (!quiet) rtcError = 'The service could not be reached. Check your connection and try again.';
      return null;
    } finally {
      client.close(force: true);
    }
  }

  static String? _detail(String body) {
    try {
      final decoded = jsonDecode(body);
      return decoded is Map && decoded['detail'] is String ? decoded['detail'] as String : null;
    } catch (_) {
      return null;
    }
  }
}

class _Reply {
  const _Reply(this.status, this.json);
  final int status;
  final Object? json;
  Map<String, dynamic> get map => json is Map ? (json as Map).cast<String, dynamic>() : const {};
  List<Object?> get list => json is List ? json as List<Object?> : const [];
}

/// Another SatyaCheck user, as search and connections show them. Never an email address.
class RtcPerson {
  const RtcPerson({required this.userId, required this.username, required this.displayName, this.relation = 'none'});

  final String userId, username, displayName;

  /// none | outgoing | incoming | connected, from your side.
  final String relation;

  bool get connected => relation == 'connected';

  factory RtcPerson.fromJson(Map<String, dynamic> json) => RtcPerson(
        userId: json['user_id'] as String? ?? '',
        username: json['username'] as String? ?? '',
        displayName: json['display_name'] as String? ?? '',
        relation: json['relation'] as String? ?? 'none',
      );

  RtcPerson withRelation(String relation) => RtcPerson(userId: userId, username: username, displayName: displayName, relation: relation);

  /// What to call them on screen.
  String get name => displayName.isNotEmpty ? displayName : username.isNotEmpty ? '@$username' : 'Unknown';
}

/// `GET /api/profile`: found, not chosen yet, or could not be asked.
class ProfileLookup {
  const ProfileLookup.found(RtcPerson this.profile) : failed = false;
  const ProfileLookup.none()
      : profile = null,
        failed = false;
  const ProfileLookup.failed()
      : profile = null,
        failed = true;
  final RtcPerson? profile;
  final bool failed;
}

class RtcConnections {
  const RtcConnections({this.connected = const [], this.incoming = const [], this.outgoing = const []});
  final List<RtcPerson> connected, incoming, outgoing;

  factory RtcConnections.fromJson(Map<String, dynamic> json) {
    List<RtcPerson> people(String key) => [
          for (final p in (json[key] as List? ?? const []))
            if (p is Map) RtcPerson.fromJson(p.cast<String, dynamic>())
        ];
    return RtcConnections(connected: people('connected'), incoming: people('incoming'), outgoing: people('outgoing'));
  }
}

/// A call ringing for you.
class IncomingCall {
  const IncomingCall({required this.callId, required this.caller, required this.ringsForS});
  final String callId;
  final RtcPerson caller;
  final int ringsForS;

  factory IncomingCall.fromJson(Map<String, dynamic> json) => IncomingCall(
        callId: json['call_id'] as String? ?? '',
        caller: RtcPerson.fromJson((json['caller'] as Map? ?? const {}).cast<String, dynamic>()).withRelation('connected'),
        ringsForS: (json['rings_for_s'] as num?)?.toInt() ?? 0,
      );
}

class IncomingCalls {
  const IncomingCalls(this.calls) : available = true;
  const IncomingCalls.unavailable()
      : calls = const [],
        available = false;
  final List<IncomingCall> calls;

  /// False when this service does not offer app calls at all.
  final bool available;

  factory IncomingCalls.fromJson(Map<String, dynamic> json) => IncomingCalls([
        for (final c in (json['calls'] as List? ?? const []))
          if (c is Map) IncomingCall.fromJson(c.cast<String, dynamic>())
      ]);
}

/// What the backend hands a phone to enter a call: the room, its token, who the screening
/// agent is, and who is on the other end.
class RtcCallTicket {
  const RtcCallTicket({required this.callId, required this.livekitUrl, required this.token, required this.agentIdentity, this.other, this.ringTimeoutS});

  final String callId, livekitUrl, token, agentIdentity;
  final RtcPerson? other;

  /// Set for the caller: how long the call rings before it counts as missed.
  final int? ringTimeoutS;

  factory RtcCallTicket.fromJson(Map<String, dynamic> json) => RtcCallTicket(
        callId: json['call_id'] as String? ?? '',
        livekitUrl: json['livekit_url'] as String? ?? '',
        token: json['token'] as String? ?? '',
        agentIdentity: json['agent_identity'] as String? ?? '',
        other: json['other'] is Map ? RtcPerson.fromJson((json['other'] as Map).cast<String, dynamic>()) : null,
        ringTimeoutS: (json['ring_timeout_s'] as num?)?.toInt(),
      );

  bool get valid => callId.isNotEmpty && livekitUrl.isNotEmpty && token.isNotEmpty && agentIdentity.isNotEmpty;
}

/// `GET /api/webrtc/calls/{call_id}`.
class RtcCallState {
  const RtcCallState({required this.status, this.endedReason, required this.screening});

  /// ringing | active | ended
  final String status;

  /// declined | missed | cancelled | hung_up, once ended.
  final String? endedReason;
  final bool screening;

  bool get ended => status == 'ended';
  bool get answered => status == 'active';

  factory RtcCallState.fromJson(Map<String, dynamic> json) => RtcCallState(
        status: json['status'] as String? ?? (json['ended'] == true ? 'ended' : 'ringing'),
        endedReason: json['ended_reason'] as String?,
        screening: json['screening'] == true,
      );
}

/// A live screening session. One per call.
class ScreeningSocket {
  ScreeningSocket._(this._socket, this.sessionId) {
    _socket.listen(
      _onMessage,
      onDone: () => _updates.isClosed ? null : _updates.close(),
      onError: (_) => _updates.isClosed ? null : _updates.close(),
      cancelOnError: true,
    );
  }

  final WebSocket _socket;
  final String sessionId;
  final _updates = StreamController<ScreeningResult>.broadcast();

  int _chunkIndex = 0;
  bool _closed = false;

  /// A rescored verdict per chunk the backend accepts. Trust only ever decreases within a
  /// session — the backend enforces that, so a scam that reveals itself late cannot be
  /// undone by a benign closing sentence.
  Stream<ScreeningResult> get updates => _updates.stream;

  void _onMessage(dynamic raw) {
    try {
      final msg = jsonDecode(raw as String) as Map<String, dynamic>;
      if (msg['type'] != 'screening_update') return;
      final response = (msg['response'] as Map?)?.cast<String, dynamic>();
      if (response == null) return;
      if (!_updates.isClosed) _updates.add(ScreeningResult.fromJson(response));
    } catch (_) {
      // A malformed frame must not tear down a call in progress.
    }
  }

  /// Send one window of audio. `wav` should be a complete RIFF file.
  void send(Uint8List wav, {bool isFinal = false}) {
    if (_closed) return;
    try {
      _socket.add(jsonEncode({
        'type': 'audio_chunk',
        'session_id': sessionId,
        'chunk_index': _chunkIndex++,
        'audio_base64': base64Encode(wav),
        'is_final': isFinal,
      }));
    } catch (_) {
      // Dropping a chunk is survivable; the next one re-scores the whole session.
    }
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    try {
      await _socket.close();
    } catch (_) {}
    if (!_updates.isClosed) await _updates.close();
  }
}

/// The live verdict feed. Receive-only: one socket carries every call.
class LiveFeedSocket {
  LiveFeedSocket._(this._socket) {
    _socket.listen(
      (raw) {
        try {
          final verdict = LiveVerdict.fromJson(jsonDecode(raw as String));
          if (verdict != null && !_verdicts.isClosed) _verdicts.add(verdict);
        } catch (_) {
          // A malformed frame is ignored; the next verdict carries the whole state again.
        }
      },
      onDone: _finish,
      onError: (_) => _finish(),
      cancelOnError: true,
    );
  }

  final WebSocket _socket;
  final _verdicts = StreamController<LiveVerdict>.broadcast();
  final _closed = Completer<int?>();

  Stream<LiveVerdict> get verdicts => _verdicts.stream;

  /// Completes with the close code when the feed ends. 1008 means a missing or wrong token.
  Future<int?> get closed => _closed.future;

  void _finish() {
    if (!_closed.isCompleted) _closed.complete(_socket.closeCode);
    if (!_verdicts.isClosed) _verdicts.close();
  }

  Future<void> close() async {
    try {
      await _socket.close();
    } catch (_) {}
    _finish();
  }
}
