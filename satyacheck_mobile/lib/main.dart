import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

void main() {
  runApp(const SatyaCheckApp());
}

class SatyaCheckApp extends StatelessWidget {
  const SatyaCheckApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SatyaCheck',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        useMaterial3: true,
      ),
      home: const M0ScaffoldScreen(),
    );
  }
}

class M0ScaffoldScreen extends StatefulWidget {
  const M0ScaffoldScreen({Key? key}) : super(key: key);

  @override
  State<M0ScaffoldScreen> createState() => _M0ScaffoldScreenState();
}

class _M0ScaffoldScreenState extends State<M0ScaffoldScreen> {
  static const platform = MethodChannel('com.satyacheck/native');

  String _response = 'Waiting for Kotlin...';
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _testMethodChannel();
  }

  Future<void> _testMethodChannel() async {
    setState(() => _isLoading = true);

    try {
      final String result = await platform.invokeMethod<String>('getPlatformVersion') ?? 'null response';
      setState(() {
        _response = 'Kotlin says: $result';
        _isLoading = false;
      });
    } on PlatformException catch (e) {
      setState(() {
        _response = 'Error from Kotlin: ${e.message}';
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('SatyaCheck M0 - MethodChannel Test'),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (_isLoading)
              const CircularProgressIndicator()
            else
              Text(
                _response,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            const SizedBox(height: 32),
            ElevatedButton(
              onPressed: _testMethodChannel,
              child: const Text('Call Kotlin Again'),
            ),
          ],
        ),
      ),
    );
  }
}
