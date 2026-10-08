import 'dart:convert';
import 'dart:io';

import 'package:archkeel_dart_analyzer/collector.dart';

Future<void> main() async {
  final decoded = jsonDecode(await stdin.transform(utf8.decoder).join());
  if (decoded is! Map<String, dynamic>) {
    throw const FormatException('request must be a JSON object');
  }
  stdout.write(jsonEncode(await DartCollector(decoded).collect()));
}
