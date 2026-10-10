import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:satyacheck/api_client.dart';
import 'package:satyacheck/auth.dart';

// No testWidgets in this file: declaring one installs flutter_test's HTTP override, and
// every real HttpClient request then answers 400. The sign-in screen is tested in
// frontend_test.dart.

/// A stand-in for Supabase Auth: records requests, answers from [routes].
class FakeSupabase {
  FakeSupabase._(this._server);
  final HttpServer _server;
  final requests = <(String, Map<String, dynamic>, String?)>[];
  final routes = <String, (int, Map<String, dynamic>)>{};

  static Future<FakeSupabase> start() async {
    final fake = FakeSupabase._(await HttpServer.bind(InternetAddress.loopbackIPv4, 0));
    fake._server.listen((request) async {
      final body = await utf8.decoder.bind(request).join();
      final path = request.uri.path + (request.uri.query.isEmpty ? '' : '?${request.uri.query}');
      fake.requests.add((path, body.isEmpty ? {} : jsonDecode(body) as Map<String, dynamic>, request.headers.value('apikey')));
      final (status, reply) = fake.routes[path] ?? (404, <String, dynamic>{});
      request.response.statusCode = status;
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode(reply));
      await request.response.close();
    });
    return fake;
  }

  String get url => 'http://127.0.0.1:${_server.port}';
  Future<void> close() => _server.close(force: true);
}

Map<String, dynamic> session(String access, {int expiresIn = 3600}) =>
    {'access_token': access, 'refresh_token': 'r-$access', 'expires_in': expiresIn};

void main() {
  test('sign-in is off without a project, and then never blocks the app', () async {
    final auth = AuthSession(url: '', anonKey: '');
    expect(auth.enabled, isFalse);
    expect(auth.ready, isTrue);
    expect(await auth.accessToken(), isNull);
  });

  test('a code is emailed, then verified into a session that refreshes before it expires', () async {
    final supabase = await FakeSupabase.start();
    var now = DateTime(2026, 10, 10, 12);
    try {
      final auth = AuthSession(url: supabase.url, anonKey: 'anon', clock: () => now);
      supabase.routes['/auth/v1/otp'] = (200, {});
      supabase.routes['/auth/v1/verify'] = (200, session('t1'));
      supabase.routes['/auth/v1/token?grant_type=refresh_token'] = (200, session('t2'));

      expect(auth.ready, isFalse);
      expect(await auth.sendCode('asha@example.com'), isNull);
      expect(await auth.verifyCode('asha@example.com', '123456'), isNull);
      expect(auth.ready, isTrue);
      expect(auth.email, 'asha@example.com');
      expect(supabase.requests[1].$2, {'type': 'email', 'email': 'asha@example.com', 'token': '123456'});
      expect(supabase.requests.every((r) => r.$3 == 'anon'), isTrue);

      expect(await auth.accessToken(), 't1');
      now = now.add(const Duration(minutes: 59, seconds: 30));   // inside the last minute
      expect(await auth.accessToken(), 't2');
      expect(supabase.requests.last.$2, {'refresh_token': 'r-t1'});
    } finally {
      await supabase.close();
    }
  });

  test('a wrong code is refused, and a failed refresh signs out', () async {
    final supabase = await FakeSupabase.start();
    var now = DateTime(2026, 10, 10, 12);
    try {
      final auth = AuthSession(url: supabase.url, anonKey: 'anon', clock: () => now);
      supabase.routes['/auth/v1/verify'] = (403, {'msg': 'expired'});
      expect(await auth.verifyCode('a@example.com', '000000'), contains('did not work'));
      expect(auth.ready, isFalse);

      supabase.routes['/auth/v1/verify'] = (200, session('t1', expiresIn: 60));
      await auth.verifyCode('a@example.com', '123456');
      supabase.routes['/auth/v1/token?grant_type=refresh_token'] = (400, {});
      now = now.add(const Duration(seconds: 30));
      expect(await auth.accessToken(), isNull);
      expect(auth.ready, isFalse);
    } finally {
      await supabase.close();
    }
  });

  test('requests carry the token and the claimed caller; a 401 signs out', () async {
    final supabase = await FakeSupabase.start();
    final backend = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final seen = <(String?, String)>[];
    var status = 200;
    backend.listen((request) async {
      final body = await utf8.decoder.bind(request).join();
      seen.add((request.headers.value(HttpHeaders.authorizationHeader), body));
      request.response.statusCode = status;
      request.response.headers.contentType = ContentType.json;
      request.response.write(status == 200 ? '[{"person_id":"p1","name":"Asha","relation":"Mother","aliases":["Mummy"],"phone_numbers":["+919800000001"]}]' : '{}');
      await request.response.close();
    });
    try {
      final auth = AuthSession(url: supabase.url, anonKey: 'anon');
      supabase.routes['/auth/v1/verify'] = (200, session('t1'));
      await auth.verifyCode('a@example.com', '123456');
      final api = ApiClient(baseUrl: 'http://127.0.0.1:${backend.port}', auth: auth);

      final people = await api.persons();
      expect(seen.last.$1, 'Bearer t1');
      expect(people.single.aliases, ['Mummy']);
      expect(people.single.phoneNumbers, ['+919800000001']);

      status = 422;
      await api.screenWav(Uint8List.fromList([0, 1]), claimedIdentity: 'p1');
      expect(seen.last.$2, contains('name="claimed_identity"\r\n\r\np1\r\n'));

      status = 401;
      expect(await api.persons(), isEmpty);
      expect(api.peopleError, ApiClient.signedOutMessage);
      expect(auth.ready, isFalse);
    } finally {
      await supabase.close();
      await backend.close(force: true);
    }
  });

  test('sockets sign in with their first message, not the URL', () async {
    final supabase = await FakeSupabase.start();
    final backend = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final first = <String>[];
    final paths = <String>[];
    backend.listen((request) async {
      paths.add(request.uri.toString());
      final socket = await WebSocketTransformer.upgrade(request);
      socket.listen((message) {
        first.add(message as String);
        socket.close();
      });
    });
    try {
      final auth = AuthSession(url: supabase.url, anonKey: 'anon');
      supabase.routes['/auth/v1/verify'] = (200, session('t1'));
      await auth.verifyCode('a@example.com', '123456');
      final api = ApiClient(baseUrl: 'http://127.0.0.1:${backend.port}', auth: auth);
      final feed = await api.openLiveFeed();
      await feed.closed.timeout(const Duration(seconds: 5));
      expect(jsonDecode(first.single), {'type': 'auth', 'token': 't1'});
      expect(paths.single, isNot(contains('t1')));
    } finally {
      await supabase.close();
      await backend.close(force: true);
    }
  });

}
