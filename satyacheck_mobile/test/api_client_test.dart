import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:satyacheck/api_client.dart';

void main() {
  test('HTTP 200 with missing evidence is an error, never a completed check',
      () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      await request.drain<void>();
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({'session_id': 'partial'}));
      await request.response.close();
    });
    try {
      final api = ApiClient(baseUrl: 'http://127.0.0.1:${server.port}');
      final result = await api.screenWav(Uint8List.fromList([0, 1]));
      expect(result, isNull);
      expect(api.screeningError, contains('incomplete result'));
    } finally {
      await server.close(force: true);
    }
  });
}
