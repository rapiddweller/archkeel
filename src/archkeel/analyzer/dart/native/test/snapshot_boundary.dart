import 'dart:io';

import 'package:archkeel_dart_analyzer/snapshot.dart';

Future<void> main(List<String> args) async {
  final root = Directory(args.single).absolute.path;
  final temp = await Directory.systemTemp.createTemp('archkeel-dart-boundary-');
  try {
    final request = {
      'protocol_version': '2.0.0',
      'snapshot': {'root': root},
      'scope': {
        'roots': ['lib'],
        'namespace': 'commerce',
      },
      'resolver': {'language': 'dart'},
    };
    final prepared = await DartSnapshot(request).prepare(temp);
    final invalid = {
      'lib/direct.dart',
      'lib/bridge.dart',
      'lib/transitive.dart',
      'lib/malformed.dart',
      'lib/parts/item.dart',
    };
    for (final path in invalid) {
      if (!prepared.invalidSources.containsKey(path) ||
          File('${prepared.stagedRoot}/$path').existsSync()) {
        throw StateError('unsafe source was staged: $path');
      }
    }
  } finally {
    await temp.delete(recursive: true);
  }
}
