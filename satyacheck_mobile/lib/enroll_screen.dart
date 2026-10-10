import 'package:flutter/material.dart';
import 'api_client.dart';
import 'theme.dart';
import 'voice_capture.dart';

class EnrollScreen extends StatefulWidget {
  const EnrollScreen({super.key, required this.api});
  final ApiClient api;
  @override
  State<EnrollScreen> createState() => _EnrollScreenState();
}

class _EnrollScreenState extends State<EnrollScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController(),
      _relation = TextEditingController(text: 'Family'),
      _aliases = TextEditingController(),
      _numbers = TextEditingController();
  bool _recording = false, _saving = false, _consent = false, _hindi = false;
  String? _path, _error;
  @override
  void dispose() {
    _name.dispose();
    _relation.dispose();
    _aliases.dispose();
    _numbers.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_saving ||
        _recording ||
        _path == null ||
        !_consent ||
        !_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final result = await widget.api.enroll(
        wavPath: _path!,
        name: _name.text.trim(),
        relation: _relation.text.trim(),
        consent: _consent,
        aliases: splitList(_aliases.text),
        phoneNumbers: splitList(_numbers.text));
    if (!mounted) return;
    setState(() => _saving = false);
    if (result.ok) {
      Navigator.pop(context, result.name);
    } else {
      setState(() => _error = result.error ??
          'The service could not confirm enrollment. Please try again.');
    }
  }

  Widget _step(int n, String title, List<Widget> children) {
    final p = context.palette, theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Container(
              width: 28,
              height: 28,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: p.soft(p.accent), shape: BoxShape.circle),
              child: Text('$n', style: TextStyle(fontFamily: mono, fontSize: 13, fontWeight: FontWeight.w600, color: p.dark ? const Color(0xFFA7AFFF) : p.accent)),
            ),
            const SizedBox(width: 12),
            Text(title, style: theme.textTheme.titleLarge),
          ]),
          const SizedBox(height: 16),
          ...children,
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette, theme = Theme.of(context);
    final locked = _recording || _saving;
    return Scaffold(
      appBar: AppBar(title: const Text('Add a known voice')),
      body: SafeArea(
        child: Form(
          key: _form,
          child: ListView(padding: const EdgeInsets.fromLTRB(20, 4, 20, 36), children: [
            Reveal(child: Text('Recognition starts here.', style: theme.textTheme.displayMedium)),
            const SizedBox(height: 12),
            Text('About 30 seconds of natural speech lets future recordings be compared with this person’s voice.', style: theme.textTheme.bodyLarge),
            const SizedBox(height: 24),
            Reveal(
              delay: const Duration(milliseconds: 80),
              child: _step(1, 'Who is it?', [
                TextFormField(
                  controller: _name,
                  enabled: !locked,
                  textCapitalization: TextCapitalization.words,
                  maxLength: 100,
                  decoration: const InputDecoration(labelText: 'Name', counterText: ''),
                  validator: (value) => value == null || value.trim().isEmpty ? 'Enter the person’s name.' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _relation,
                  enabled: !locked,
                  maxLength: 60,
                  decoration: const InputDecoration(labelText: 'Relationship', hintText: 'Son, mother, friend…', counterText: ''),
                  validator: (value) => value == null || value.trim().isEmpty ? 'Enter your relationship.' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _aliases,
                  enabled: !locked,
                  maxLength: 200,
                  decoration: const InputDecoration(
                      labelText: 'What callers call them (optional)', hintText: 'Papa, Raju bhaiya', counterText: '',
                      helperText: 'Separate with commas. Helps match “It’s Papa” to this person.', helperMaxLines: 3),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _numbers,
                  enabled: !locked,
                  maxLength: 120,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(
                      labelText: 'Numbers they call from (optional)', hintText: '+91…', counterText: '',
                      helperText: 'A matching number is a hint, never proof. Numbers can be faked.', helperMaxLines: 3),
                ),
              ]),
            ),
            Reveal(
              delay: const Duration(milliseconds: 160),
              child: _step(2, 'Their voice', [
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(color: p.panel2, borderRadius: BorderRadius.circular(20), border: Border.all(color: p.line)),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Expanded(child: Text('Read aloud, or just talk', style: theme.textTheme.labelMedium)),
                      SegmentedButton<bool>(
                        showSelectedIcon: false,
                        segments: const [ButtonSegment(value: false, label: Text('English')), ButtonSegment(value: true, label: Text('हिन्दी'))],
                        selected: {_hindi},
                        onSelectionChanged: locked ? null : (value) => setState(() => _hindi = value.first),
                      ),
                    ]),
                    const SizedBox(height: 14),
                    Text(
                      _hindi ? hindiScript : englishScript,
                      style: theme.textTheme.bodyLarge?.copyWith(color: p.text, height: 1.7),
                    ),
                  ]),
                ),
                const SizedBox(height: 16),
                VoiceCapture(
                  disabled: _saving,
                  minSeconds: 15,
                  onReady: (path) => setState(() => _path = path),
                  onActive: (active) => setState(() => _recording = active),
                ),
                const SizedBox(height: 10),
                Text('Aim for 30 seconds in a quiet room. At least 15 seconds of speech is required.', style: theme.textTheme.bodySmall),
              ]),
            ),
            Reveal(
              delay: const Duration(milliseconds: 240),
              child: _step(3, 'Consent', [
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  controlAffinity: ListTileControlAffinity.leading,
                  title: Text('This person has agreed to enroll their voice for comparison. A voiceprint is biometric data: the service records when consent was given, and removing the person deletes it.', style: theme.textTheme.bodyLarge?.copyWith(color: p.text)),
                  value: _consent,
                  onChanged: locked ? null : (value) => setState(() => _consent = value ?? false),
                ),
              ]),
            ),
            if (_error != null) Padding(padding: const EdgeInsets.only(bottom: 14), child: InfoMessage(_error!, error: true)),
            PillButton(
              label: _saving ? 'Enrolling voice…' : 'Enroll voice',
              trailing: Icons.arrow_forward_rounded,
              large: true,
              expand: true,
              busy: _saving,
              onPressed: _path != null && !_recording && !_saving && _consent ? _submit : null,
            ),
            const SizedBox(height: 14),
            Text('Enrollment counts only once the service confirms a saved voiceprint.', style: theme.textTheme.bodySmall, textAlign: TextAlign.center),
          ]),
        ),
      ),
    );
  }
}

const englishScript = 'Hello, I’m recording my voice so my family can recognise me. I usually call in the evening to ask how everyone’s day went. If someone ever asks for money in my name, call me back on my saved number first.';
const hindiScript = 'नमस्ते, मैं अपनी आवाज़ इसलिए रिकॉर्ड कर रहा हूँ ताकि मेरा परिवार मुझे पहचान सके। अगर कभी कोई मेरे नाम पर पैसे माँगे, तो पहले मेरे सेव किए हुए नंबर पर मुझे वापस फ़ोन करें।';

/// "Papa, Raju" → ["Papa", "Raju"].
List<String> splitList(String text) =>
    [for (final part in text.split(RegExp(r'[,;\n]'))) if (part.trim().isNotEmpty) part.trim()];
