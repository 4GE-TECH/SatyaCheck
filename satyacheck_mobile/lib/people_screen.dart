import 'dart:async';

import 'package:flutter/material.dart';

import 'api_client.dart';
import 'app_call_screen.dart';
import 'theme.dart';

/// Find other SatyaCheck users by username, connect, and call (webrtc/BACKEND_API.md).
///
/// A connect request has to be accepted before either of you can ring the other: someone
/// who merely knows your username cannot call you.
class PeopleScreen extends StatefulWidget {
  const PeopleScreen({super.key, required this.api});
  final ApiClient api;
  @override
  State<PeopleScreen> createState() => _PeopleScreenState();
}

class _PeopleScreenState extends State<PeopleScreen> {
  ApiClient get _api => widget.api;

  bool _loading = true;
  ProfileLookup? _profile;
  RtcConnections _connections = const RtcConnections();
  String? _error;

  final _query = TextEditingController();
  Timer? _debounce;
  List<RtcPerson>? _results;
  bool _searching = false;
  String? _searchError;
  final _working = <String>{};

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _query.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!_api.auth.enabled) {
      // The backend refuses calls without a verified sign-in: nothing to ask it.
      setState(() => _loading = false);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    final profile = await _api.myProfile();
    RtcConnections? connections;
    if (profile.profile != null) connections = await _api.connections();
    if (!mounted) return;
    setState(() {
      _loading = false;
      _profile = profile;
      if (profile.failed) _error = _api.rtcError;
      if (connections != null) _connections = connections;
    });
  }

  Future<void> _refreshConnections() async {
    final connections = await _api.connections();
    if (mounted && connections != null) setState(() => _connections = connections);
  }

  void _onQuery(String text) {
    _debounce?.cancel();
    if (text.trim().replaceFirst('@', '').length < 2) {
      setState(() {
        _results = null;
        _searchError = null;
      });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 400), () => unawaited(_search(text)));
  }

  Future<void> _search(String text) async {
    setState(() => _searching = true);
    final found = await _api.searchPeople(text);
    if (!mounted || _query.text != text) return;
    setState(() {
      _searching = false;
      _results = found;
      _searchError = found == null ? _api.rtcError : null;
    });
  }

  /// Run one action for a person, then refresh what changed.
  Future<void> _act(RtcPerson person, Future<Object?> Function() action) async {
    setState(() => _working.add(person.userId));
    final ok = await action();
    if (!mounted) return;
    setState(() => _working.remove(person.userId));
    if (ok == null || ok == false) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(_api.rtcError ?? 'That did not work. Please try again.')));
      return;
    }
    await _refreshConnections();
    if (_query.text.trim().length >= 2) await _search(_query.text);
  }

  void _call(RtcPerson person) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => AppCallScreen(api: _api, callee: person)));
  }

  @override
  Widget build(BuildContext context) {
    final profile = _profile?.profile;
    return Scaffold(
      appBar: AppBar(title: const Text('People')),
      body: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : !_api.auth.enabled
                    ? _message('App calls need sign-in, and this build has none. Build it with SATYACHECK_SUPABASE_URL and SATYACHECK_SUPABASE_ANON_KEY.')
                    : _profile?.failed ?? true
                        ? _message(_error ?? 'Could not load your profile.', retry: true)
                        : profile == null
                            ? _UsernameForm(api: _api, onSaved: (_) => unawaited(_load()))
                            : _directory(context, profile),
          ),
        ),
      ),
    );
  }

  Widget _message(String text, {bool retry = false}) => ListView(padding: const EdgeInsets.all(20), children: [
        InfoMessage(text, error: true, action: retry ? TextButton(onPressed: _load, child: const Text('Try again')) : null),
      ]);

  Widget _directory(BuildContext context, RtcPerson me) {
    final theme = Theme.of(context);
    final c = _connections;
    return RefreshIndicator(
      onRefresh: _refreshConnections,
      child: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 40), children: [
        Row(children: [
          Expanded(child: Text('You are @${me.username}', style: theme.textTheme.titleMedium)),
          TextButton(
            onPressed: () => showModalBottomSheet<void>(
              context: context,
              isScrollControlled: true,
              builder: (sheet) => Padding(
                padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(sheet).bottom),
                child: _UsernameForm(api: _api, current: me, onSaved: (_) {
                  Navigator.pop(sheet);
                  unawaited(_load());
                }),
              ),
            ),
            child: const Text('Change'),
          ),
        ]),
        const SizedBox(height: 10),
        TextField(
          controller: _query,
          autocorrect: false,
          enableSuggestions: false,
          textInputAction: TextInputAction.search,
          decoration: InputDecoration(
            labelText: 'Search by username',
            prefixIcon: const Icon(Icons.search_rounded),
            suffixIcon: _searching ? const Padding(padding: EdgeInsets.all(14), child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))) : null,
          ),
          onChanged: _onQuery,
          onSubmitted: (text) => unawaited(_search(text)),
        ),
        if (_searchError != null) Padding(padding: const EdgeInsets.only(top: 12), child: InfoMessage(_searchError!, error: true)),
        if (_results != null) ...[
          const SizedBox(height: 12),
          if (_results!.isEmpty)
            Text('No one with a username starting “${_query.text.trim()}”.', style: theme.textTheme.bodyMedium)
          else
            for (final person in _results!) _PersonRow(person: person, actions: _actionsFor(person)),
        ],
        if (c.incoming.isNotEmpty) ...[
          _Section('Requests', c.incoming.length),
          for (final person in c.incoming) _PersonRow(person: person, actions: _actionsFor(person)),
        ],
        _Section('Connected', c.connected.length),
        if (c.connected.isEmpty)
          Text('Search for someone’s username and send a connect request. Once they accept, either of you can call.',
              style: theme.textTheme.bodyMedium)
        else
          for (final person in c.connected) _PersonRow(person: person, actions: _actionsFor(person)),
        if (c.outgoing.isNotEmpty) ...[
          _Section('Sent', c.outgoing.length),
          for (final person in c.outgoing) _PersonRow(person: person, actions: _actionsFor(person)),
        ],
      ]),
    );
  }

  List<Widget> _actionsFor(RtcPerson person) {
    if (_working.contains(person.userId)) {
      return const [Padding(padding: EdgeInsets.all(12), child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)))];
    }
    return switch (person.relation) {
      'connected' => [
          FilledButton.icon(onPressed: () => _call(person), icon: const Icon(Icons.call_rounded), label: const Text('Call')),
        ],
      'incoming' => [
          TextButton(onPressed: () => _act(person, () => _api.removeConnection(person.userId)), child: const Text('Decline')),
          FilledButton(onPressed: () => _act(person, () => _api.acceptConnection(person.userId)), child: const Text('Accept')),
        ],
      'outgoing' => [
          OutlinedButton(onPressed: () => _act(person, () => _api.removeConnection(person.userId)), child: const Text('Cancel request')),
        ],
      _ => [
          FilledButton.tonal(onPressed: () => _act(person, () => _api.requestConnection(person.userId)), child: const Text('Connect')),
        ],
    };
  }
}

class _Section extends StatelessWidget {
  const _Section(this.title, this.count);
  final String title;
  final int count;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 26, bottom: 10),
        child: Text(count > 0 ? '$title · $count' : title, style: Theme.of(context).textTheme.headlineSmall),
      );
}

class _PersonRow extends StatelessWidget {
  const _PersonRow({required this.person, required this.actions});
  final RtcPerson person;
  final List<Widget> actions;
  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final initial = person.name.replaceFirst('@', '');
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Panel(
        padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
        child: Row(children: [
          Container(
            width: 44,
            height: 44,
            alignment: Alignment.center,
            decoration: BoxDecoration(shape: BoxShape.circle, gradient: LinearGradient(colors: [p.voice1, p.voice2])),
            child: Text(initial.isEmpty ? '?' : initial.characters.first.toUpperCase(),
                style: const TextStyle(fontFamily: sans, fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(person.name, style: theme.textTheme.titleMedium, overflow: TextOverflow.ellipsis),
              Text('@${person.username}', style: theme.textTheme.bodySmall, overflow: TextOverflow.ellipsis),
            ]),
          ),
          Wrap(spacing: 6, children: actions),
        ]),
      ),
    );
  }
}

/// Choose (or change) the username others find you by.
class _UsernameForm extends StatefulWidget {
  const _UsernameForm({required this.api, required this.onSaved, this.current});
  final ApiClient api;
  final RtcPerson? current;
  final ValueChanged<RtcPerson> onSaved;
  @override
  State<_UsernameForm> createState() => _UsernameFormState();
}

class _UsernameFormState extends State<_UsernameForm> {
  late final _username = TextEditingController(text: widget.current?.username ?? '');
  late final _display = TextEditingController(text: widget.current?.displayName ?? '');
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _username.dispose();
    _display.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    final saved = await widget.api.saveProfile(_username.text.trim(), _display.text.trim());
    if (!mounted) return;
    setState(() {
      _saving = false;
      _error = saved == null ? widget.api.rtcError : null;
    });
    if (saved != null) widget.onSaved(saved);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(shrinkWrap: true, padding: const EdgeInsets.fromLTRB(20, 20, 20, 32), children: [
      Text(widget.current == null ? 'Choose a username' : 'Change your username', style: theme.textTheme.headlineSmall),
      const SizedBox(height: 8),
      Text('People find you by it to send a connect request. Your email address is never shown.', style: theme.textTheme.bodyMedium),
      const SizedBox(height: 18),
      TextField(
        controller: _username,
        autocorrect: false,
        enableSuggestions: false,
        decoration: const InputDecoration(labelText: 'Username', prefixText: '@', helperText: '3 to 20 letters, numbers, dots or underscores'),
      ),
      const SizedBox(height: 12),
      TextField(
        controller: _display,
        textCapitalization: TextCapitalization.words,
        decoration: const InputDecoration(labelText: 'Your name (optional)', helperText: 'Shown to people you connect with'),
        onSubmitted: (_) => _saving ? null : _save(),
      ),
      if (_error != null) Padding(padding: const EdgeInsets.only(top: 14), child: InfoMessage(_error!, error: true)),
      const SizedBox(height: 18),
      PillButton(label: _saving ? 'Saving…' : 'Save', busy: _saving, expand: true, onPressed: _saving ? null : _save),
    ]);
  }
}
