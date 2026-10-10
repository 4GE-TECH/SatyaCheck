import 'package:flutter/material.dart';

import 'auth.dart';
import 'theme.dart';

/// Shows [child] only to a signed-in account (when sign-in is on), and the sign-in
/// screen otherwise. A 401 from the backend signs out, which brings this screen back.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key, required this.auth, required this.child});
  final AuthSession auth;
  final Widget child;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: auth,
        builder: (context, _) => auth.ready ? child : SignInScreen(auth: auth),
      );
}

/// Email, then the 6-digit code from it. No password to remember.
class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key, required this.auth});
  final AuthSession auth;
  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _email = TextEditingController(), _code = TextEditingController();
  bool _codeSent = false, _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _email.text.trim();
    if (_busy || email.isEmpty || (_codeSent && _code.text.trim().length != 6)) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final problem = _codeSent
        ? await widget.auth.verifyCode(email, _code.text.trim())
        : await widget.auth.sendCode(email);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = problem;
      if (problem == null && !_codeSent) _codeSent = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: ListView(shrinkWrap: true, padding: const EdgeInsets.fromLTRB(20, 24, 20, 36), children: [
              Semantics(header: true, child: Text('Sign in to SatyaCheck', style: theme.textTheme.displayMedium)),
              const SizedBox(height: 12),
              Text('We will email you a 6-digit code. Your known voices and reports stay with your account.',
                  style: theme.textTheme.bodyLarge),
              const SizedBox(height: 24),
              Panel(
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  TextField(
                    controller: _email,
                    enabled: !_busy && !_codeSent,
                    keyboardType: TextInputType.emailAddress,
                    autofillHints: const [AutofillHints.email],
                    decoration: const InputDecoration(labelText: 'Email address'),
                    onSubmitted: (_) => _submit(),
                  ),
                  if (_codeSent) ...[
                    const SizedBox(height: 14),
                    TextField(
                      controller: _code,
                      enabled: !_busy,
                      autofocus: true,
                      keyboardType: TextInputType.number,
                      maxLength: 6,
                      autofillHints: const [AutofillHints.oneTimeCode],
                      decoration: InputDecoration(labelText: 'Code sent to ${_email.text.trim()}', counterText: ''),
                      onSubmitted: (_) => _submit(),
                    ),
                  ],
                ]),
              ),
              if (_error != null) Padding(padding: const EdgeInsets.only(top: 14), child: InfoMessage(_error!, error: true)),
              const SizedBox(height: 18),
              PillButton(
                label: _codeSent ? 'Sign in' : 'Email me a code',
                trailing: Icons.arrow_forward_rounded,
                large: true,
                expand: true,
                busy: _busy,
                onPressed: _busy ? null : _submit,
              ),
              if (_codeSent) ...[
                const SizedBox(height: 10),
                PillButton(
                  label: 'Use a different address',
                  kind: PillKind.ghost,
                  expand: true,
                  onPressed: _busy
                      ? null
                      : () => setState(() {
                            _codeSent = false;
                            _code.clear();
                            _error = null;
                          }),
                ),
              ],
              const SizedBox(height: 14),
              Text('You stay signed in until you close the app.', style: theme.textTheme.bodySmall, textAlign: TextAlign.center),
            ]),
          ),
        ),
      ),
    );
  }
}
