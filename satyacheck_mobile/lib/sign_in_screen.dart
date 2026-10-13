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

/// Email and password: sign in, or create an account. No email is sent: Supabase's
/// built-in mailer cannot carry a sign-in code without custom SMTP, so testers use a
/// password instead ("Confirm email" must be off in Supabase for new accounts).
class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key, required this.auth});
  final AuthSession auth;
  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _email = TextEditingController(), _password = TextEditingController(), _again = TextEditingController();
  bool _creating = false, _busy = false, _hidden = true;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _again.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _email.text.trim(), password = _password.text;
    if (_busy) return;
    if (email.isEmpty || password.isEmpty) {
      setState(() => _error = 'Enter your email and password.');
      return;
    }
    if (_creating && password.length < 6) {
      setState(() => _error = 'Choose a password of at least 6 characters.');
      return;
    }
    if (_creating && password != _again.text) {
      setState(() => _error = 'The two passwords are different.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final problem = _creating
        ? await widget.auth.signUp(email, password)
        : await widget.auth.signInWithPassword(email, password);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = problem;
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
            child: AutofillGroup(
              child: ListView(shrinkWrap: true, padding: const EdgeInsets.fromLTRB(20, 24, 20, 36), children: [
                Semantics(
                  header: true,
                  child: Text(_creating ? 'Create your account' : 'Sign in to SatyaCheck', style: theme.textTheme.displayMedium),
                ),
                const SizedBox(height: 12),
                Text('Your known voices, contacts and calls stay with your account.', style: theme.textTheme.bodyLarge),
                const SizedBox(height: 24),
                Panel(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    TextField(
                      controller: _email,
                      enabled: !_busy,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      autofillHints: const [AutofillHints.email],
                      decoration: const InputDecoration(labelText: 'Email address'),
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _password,
                      enabled: !_busy,
                      obscureText: _hidden,
                      autocorrect: false,
                      enableSuggestions: false,
                      autofillHints: [_creating ? AutofillHints.newPassword : AutofillHints.password],
                      decoration: InputDecoration(
                        labelText: 'Password',
                        suffixIcon: IconButton(
                          tooltip: _hidden ? 'Show password' : 'Hide password',
                          icon: Icon(_hidden ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                          onPressed: () => setState(() => _hidden = !_hidden),
                        ),
                      ),
                      onSubmitted: _creating ? null : (_) => _submit(),
                    ),
                    if (_creating) ...[
                      const SizedBox(height: 14),
                      TextField(
                        controller: _again,
                        enabled: !_busy,
                        obscureText: _hidden,
                        autocorrect: false,
                        enableSuggestions: false,
                        decoration: const InputDecoration(labelText: 'Password again'),
                        onSubmitted: (_) => _submit(),
                      ),
                    ],
                  ]),
                ),
                if (_error != null) Padding(padding: const EdgeInsets.only(top: 14), child: InfoMessage(_error!, error: true)),
                const SizedBox(height: 18),
                PillButton(
                  label: _creating ? 'Create account' : 'Sign in',
                  trailing: Icons.arrow_forward_rounded,
                  large: true,
                  expand: true,
                  busy: _busy,
                  onPressed: _busy ? null : _submit,
                ),
                const SizedBox(height: 10),
                PillButton(
                  label: _creating ? 'I already have an account' : 'Create an account',
                  kind: PillKind.ghost,
                  expand: true,
                  onPressed: _busy
                      ? null
                      : () => setState(() {
                            _creating = !_creating;
                            _again.clear();
                            _error = null;
                          }),
                ),
                const SizedBox(height: 14),
                Text('You stay signed in until you close the app.', style: theme.textTheme.bodySmall, textAlign: TextAlign.center),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
