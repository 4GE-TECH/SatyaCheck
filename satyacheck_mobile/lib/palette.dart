import 'package:flutter/material.dart';

import 'models.dart';

/// Colours for the four verdicts. One place, so the home screen, the live view, the
/// overlay and the notification cannot drift apart.
const signalColors = {
  Signal.green: Color(0xFF16A34A),
  Signal.amber: Color(0xFFD97706),
  Signal.red: Color(0xFFDC2626),
  Signal.grey: Color(0xFF6B7280),
};
