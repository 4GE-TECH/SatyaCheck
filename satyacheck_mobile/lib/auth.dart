import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

/// Sign-in with an emailed one-time code (Supabase Auth), over its plain REST API so the
/// app needs no extra package.
///
/// On when the build names a Supabase project:
///
///     flutter run --dart-define=SATYACHECK_SUPABASE_URL=https://<ref>.supabase.co \
///                 --dart-define=SATYACHECK_SUPABASE_ANON_KEY=<public anon key>
///
/// Off otherwise: the backend then runs in `AUTH_MODE=dev` and every request acts for its
/// dev account, as before sign-in existed.
///
/// The session lives in memory only, so closing the app means signing in again. Keeping
/// a refresh token on the device needs encrypted storage, which this build does not ship.
class AuthSession extends ChangeNotifier {
  AuthSession({String? url, String? anonKey, DateTime Function()? clock})
      : _url = (url ?? defaultUrl).replaceFirst(RegExp(r'/+$'), ''),
        _anonKey = anonKey ?? defaultAnonKey,
        _clock = clock ?? DateTime.now;

  static const defaultUrl = String.fromEnvironment('SATYACHECK_SUPABASE_URL');
  static const defaultAnonKey = String.fromEnvironment('SATYACHECK_SUPABASE_ANON_KEY');

  final String _url;
  final String _anonKey;
  final DateTime Function() _clock;

  String? _accessToken, _refreshToken, _email;
  DateTime? _expiresAt;
  Future<String?>? _refreshing;

  bool get enabled => _url.isNotEmpty && _anonKey.isNotEmpty;

  /// Signed in, or sign-in is off and nobody needs to.
  bool get ready => !enabled || _accessToken != null;

  String? get email => _email;

  /// Emails a 6-digit code. Returns an error message, or null when sent.
  Future<String?> sendCode(String email) async {
    final (status, _) = await _post('/auth/v1/otp', {'email': email, 'create_user': true});
    if (status == 200) return null;
    debugPrint('SatyaCheck sign-in: code request HTTP $status');
    return status == 429
        ? 'Too many codes were requested. Wait a minute, then try again.'
        : 'The code could not be sent. Check the address and try again.';
  }

  /// Checks the code. Returns an error message, or null when signed in.
  Future<String?> verifyCode(String email, String code) async {
    final (status, body) = await _post('/auth/v1/verify', {'type': 'email', 'email': email, 'token': code});
    if (status == 200 && _take(body)) {
      _email = email;
      notifyListeners();
      return null;
    }
    debugPrint('SatyaCheck sign-in: verify HTTP $status');
    return 'That code did not work. Check it, or send a new one.';
  }

  /// A current access token, refreshed a minute before it expires. Null when signed out,
  /// when sign-in is off, or when the refresh failed (which signs out).
  Future<String?> accessToken() async {
    if (!enabled || _accessToken == null) return null;
    final expires = _expiresAt;
    if (expires == null || _clock().isBefore(expires.subtract(const Duration(seconds: 60)))) return _accessToken;
    return _refreshing ??= _refresh().whenComplete(() => _refreshing = null);
  }

  Future<String?> _refresh() async {
    final token = _refreshToken;
    if (token == null) {
      signOut();
      return null;
    }
    final (status, body) = await _post('/auth/v1/token?grant_type=refresh_token', {'refresh_token': token});
    if (status == 200 && _take(body)) return _accessToken;
    debugPrint('SatyaCheck sign-in: refresh HTTP $status, signing out');
    signOut();
    return null;
  }

  /// Forgets the session. Called on sign-out and when the backend answers 401.
  void signOut() {
    final wasIn = _accessToken != null;
    _accessToken = _refreshToken = _expiresAt = null;
    if (wasIn) notifyListeners();
  }

  bool _take(Object? body) {
    if (body is! Map || body['access_token'] is! String) return false;
    _accessToken = body['access_token'] as String;
    _refreshToken = body['refresh_token'] as String? ?? _refreshToken;
    final seconds = body['expires_in'];
    _expiresAt = seconds is num ? _clock().add(Duration(seconds: seconds.toInt())) : null;
    return true;
  }

  Future<(int, Object?)> _post(String path, Map<String, Object?> payload) async {
    if (!enabled) return (0, null);
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
    try {
      final request = await client.postUrl(Uri.parse('$_url$path'));
      request.headers
        ..set('apikey', _anonKey)
        ..set(HttpHeaders.contentTypeHeader, 'application/json');
      request.add(utf8.encode(jsonEncode(payload)));
      final response = await request.close().timeout(const Duration(seconds: 15));
      final text = await response.transform(utf8.decoder).join();
      Object? body;
      try {
        body = text.isEmpty ? null : jsonDecode(text);
      } catch (_) {}
      return (response.statusCode, body);
    } catch (error) {
      debugPrint('SatyaCheck sign-in unavailable: $error');
      return (0, null);
    } finally {
      client.close(force: true);
    }
  }
}
