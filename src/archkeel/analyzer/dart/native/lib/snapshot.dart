import 'dart:convert';
import 'dart:io';

import 'package:analyzer/dart/analysis/features.dart';
import 'package:analyzer/dart/analysis/utilities.dart';
import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/error/error.dart';
import 'package:path/path.dart' as p;
import 'package:pub_semver/pub_semver.dart';
import 'package:yaml/yaml.dart';

String? dartModuleName(String path) {
  final segments = path.split('/');
  final names = [
    for (var index = 0; index < segments.length; index++)
      (index == segments.length - 1
              ? segments[index].replaceFirst(RegExp(r'\.dart$'), '')
              : segments[index])
          .replaceAll(RegExp(r'[.-]'), '_'),
  ];
  if (names.any(
    (name) => !RegExp(r'^[A-Za-z_][A-Za-z0-9_]*$').hasMatch(name),
  )) {
    return null;
  }
  return names.join('.');
}

class DartSource {
  DartSource(this.path, this.rel, this.module, this.text, this.bytes);
  final String path;
  final String rel;
  final String module;
  final String text;
  final List<int> bytes;
  List<String> get lines => const LineSplitter().convert(text);
}

class DartProblem {
  DartProblem(this.file, this.offset, this.kind, this.message);
  final String file;
  final int offset;
  final String kind;
  final String message;
}

class PreparedDartSnapshot {
  PreparedDartSnapshot({
    required this.root,
    required this.roots,
    required this.packageName,
    required this.pubspecBytes,
    required this.sources,
    required this.stagedRoot,
    required this.invalidSources,
    required this.problems,
  });
  final String root;
  final List<String> roots;
  final String packageName;
  final List<int> pubspecBytes;
  final List<DartSource> sources;
  final String stagedRoot;
  final Map<String, String> invalidSources;
  final List<DartProblem> problems;
}

class DartSnapshot {
  DartSnapshot(this.request);
  final Map<String, dynamic> request;
  final Map<String, String> invalidSources = {};
  final List<DartProblem> problems = [];
  final Map<String, Set<String>> dependencies = {};

  Future<PreparedDartSnapshot> prepare(Directory temp) async {
    _validateRequest();
    final snapshot = request['snapshot'] as Map<String, dynamic>;
    final scope = request['scope'] as Map<String, dynamic>;
    final root = p.normalize(p.absolute(snapshot['root'] as String));
    final roots = (scope['roots'] as List).cast<String>();
    final namespace = scope['namespace'] as String;
    final pubspec = File(p.join(root, 'pubspec.yaml'));
    if (FileSystemEntity.typeSync(pubspec.path, followLinks: false) !=
        FileSystemEntityType.file) {
      throw const FormatException(
        'snapshot must include a regular pubspec.yaml file',
      );
    }
    final snapshotReal = Directory(root).resolveSymbolicLinksSync();
    final pubspecReal = pubspec.resolveSymbolicLinksSync();
    if (!p.isWithin(snapshotReal, pubspecReal)) {
      throw const FormatException('pubspec.yaml escapes the snapshot');
    }
    final pubspecBytes = pubspec.readAsBytesSync();
    final package = _packageName(pubspecBytes);
    final sources = _read(root, roots, namespace);
    _validateUris(sources, roots, package);
    _propagateInvalidDependencies(sources);
    final safeSources = sources
        .where((source) => !invalidSources.containsKey(source.rel))
        .toList();
    final stagedRoot = await _stage(temp, safeSources, pubspecBytes, package);
    return PreparedDartSnapshot(
      root: root,
      roots: roots,
      packageName: package,
      pubspecBytes: pubspecBytes,
      sources: sources,
      stagedRoot: stagedRoot,
      invalidSources: invalidSources,
      problems: problems,
    );
  }

  void _validateRequest() {
    final scope = request['scope'];
    final resolver = request['resolver'];
    final roots = scope is Map<String, dynamic> ? scope['roots'] : null;
    final namespace = scope is Map<String, dynamic> ? scope['namespace'] : null;
    if (request['protocol_version'] != '2.0.0' ||
        scope is! Map<String, dynamic> ||
        resolver is! Map<String, dynamic> ||
        resolver['language'] != 'dart' ||
        roots is! List ||
        roots.isEmpty ||
        roots.any((root) => root is! String || !_validRoot(root)) ||
        roots.toSet().length != roots.length ||
        namespace is! String ||
        !RegExp(
          r'^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$',
        ).hasMatch(namespace)) {
      throw const FormatException(
        'Dart collector requires a valid protocol 2.0.0 request',
      );
    }
    final selectedRoots = roots.cast<String>();
    for (var left = 0; left < selectedRoots.length; left++) {
      for (var right = left + 1; right < selectedRoots.length; right++) {
        if (p.posix.isWithin(selectedRoots[left], selectedRoots[right]) ||
            p.posix.isWithin(selectedRoots[right], selectedRoots[left])) {
          throw const FormatException('Dart scope roots must not overlap');
        }
      }
    }
  }

  bool _validRoot(String root) =>
      root.isNotEmpty &&
      !root.contains('\\') &&
      !p.posix.isAbsolute(root) &&
      p.posix.normalize(root) == root &&
      !root.split('/').contains('..');

  List<DartSource> _read(String root, List<String> roots, String namespace) {
    final result = <DartSource>[];
    final snapshotReal = Directory(root).resolveSymbolicLinksSync();
    for (final selected in roots) {
      final directoryPath = p.normalize(p.join(root, selected));
      if (directoryPath != root && !p.isWithin(root, directoryPath)) {
        throw const FormatException('Dart scope escapes the snapshot');
      }
      final directory = Directory(directoryPath);
      if (FileSystemEntity.typeSync(directoryPath, followLinks: false) !=
          FileSystemEntityType.directory) {
        _addProblem(
          selected,
          0,
          'SelectedRootError',
          'selected source root is missing or is not a directory',
        );
        continue;
      }
      final directoryReal = directory.resolveSymbolicLinksSync();
      if (directoryReal != snapshotReal &&
          !p.isWithin(snapshotReal, directoryReal)) {
        _addProblem(
          selected,
          0,
          'SelectedRootError',
          'selected source root escapes the snapshot',
        );
        continue;
      }
      final firstSource = result.length;
      for (final entity in directory.listSync(
        recursive: true,
        followLinks: false,
      )) {
        if (entity is Link) {
          final targetType = FileSystemEntity.typeSync(entity.path);
          if (!entity.path.endsWith('.dart') &&
              targetType != FileSystemEntityType.directory) {
            continue;
          }
          final rel = p
              .relative(entity.path, from: root)
              .replaceAll(p.separator, '/');
          _addProblem(
            rel,
            0,
            'DartSourceLink',
            'source symlinks are not followed',
          );
          continue;
        }
        if (entity is! File || !entity.path.endsWith('.dart')) continue;
        if (FileSystemEntity.typeSync(entity.path, followLinks: false) !=
            FileSystemEntityType.file) {
          _addProblem(
            p.relative(entity.path, from: root),
            0,
            'DartSourceError',
            'source is not a regular file',
          );
          continue;
        }
        final rel = p
            .relative(entity.path, from: root)
            .replaceAll(p.separator, '/');
        final belowRoot = p
            .relative(entity.path, from: directoryPath)
            .replaceAll(p.separator, '/');
        final modulePath = dartModuleName(belowRoot);
        if (modulePath == null) {
          _addProblem(
            rel,
            0,
            'DartModuleError',
            'source path cannot form a module identity',
          );
          continue;
        }
        final bytes = entity.readAsBytesSync();
        result.add(
          DartSource(
            entity.path,
            rel,
            namespace + '.' + modulePath,
            utf8.decode(bytes),
            bytes,
          ),
        );
      }
      if (result.length == firstSource) {
        _addProblem(
          selected,
          0,
          'EmptySourceRoot',
          'selected source root contains no Dart files',
        );
      }
    }
    result.sort((a, b) => a.rel.compareTo(b.rel));
    final pathsByModule = <String, List<DartSource>>{};
    for (final source in result) {
      pathsByModule.putIfAbsent(source.module, () => []).add(source);
    }
    for (final entry in pathsByModule.entries) {
      if (entry.value.length < 2) continue;
      final paths = entry.value.map((source) => source.rel).join(', ');
      for (final source in entry.value) {
        invalidSources[source.rel] = 'Dart module identity collision';
        _addProblem(
          source.rel,
          0,
          'DartModuleCollision',
          'selected paths ' + paths + ' map to the same module ' + entry.key,
        );
      }
    }
    return result;
  }

  String _packageName(List<int> pubspecBytes) {
    final yaml = loadYaml(utf8.decode(pubspecBytes));
    if (yaml is! YamlMap ||
        yaml['name'] is! String ||
        !RegExp(r'^[a-z][a-z0-9_]*$').hasMatch(yaml['name'] as String)) {
      throw const FormatException(
        'pubspec.yaml must declare a valid package name',
      );
    }
    return yaml['name'] as String;
  }

  Future<String> _stage(
    Directory temp,
    List<DartSource> sources,
    List<int> pubspecBytes,
    String packageName,
  ) async {
    final root = Directory(p.join(temp.path, 'snapshot'))..createSync();
    for (final source in sources) {
      final target = File(p.join(root.path, source.rel));
      target.parent.createSync(recursive: true);
      target.writeAsBytesSync(source.bytes);
    }
    File(p.join(root.path, 'pubspec.yaml')).writeAsBytesSync(pubspecBytes);
    File(p.join(root.path, 'analysis_options.yaml')).writeAsStringSync('');
    final pubspecData = loadYaml(utf8.decode(pubspecBytes)) as YamlMap;
    final environment = pubspecData['environment'] as YamlMap?;
    final sdk = environment?['sdk'];
    final runningVersion = Version.parse(Platform.version.split(' ').first);
    var constraint = VersionConstraint.any;
    if (sdk != null) {
      try {
        if (sdk is! String)
          throw const FormatException('SDK range must be a string');
        constraint = VersionConstraint.parse(sdk);
      } on FormatException {
        for (final source in sources) {
          _invalid(
            source,
            0,
            'SdkConstraintError',
            'pubspec SDK constraint is malformed',
          );
        }
      }
    }
    if (!constraint.allows(runningVersion)) {
      for (final source in sources) {
        _invalid(
          source,
          0,
          'SdkConstraintError',
          'pubspec SDK constraint does not include the running Dart SDK',
        );
      }
    }
    Version? minimum;
    if (sdk == null || constraint.isAny) {
      minimum = runningVersion;
    } else if (constraint is VersionRange) {
      minimum = constraint.min;
    }
    if (minimum == null) {
      for (final source in sources) {
        _invalid(
          source,
          0,
          'SdkConstraintError',
          'pubspec SDK constraint has no unambiguous source language lower bound',
        );
      }
    }
    final languageMinimum = minimum ?? runningVersion;
    final packageLanguageVersion = Version(
      languageMinimum.major,
      languageMinimum.minor,
      0,
    );
    final minimumSupported = Feature.non_nullable.releaseVersion;
    // Analyzer misses old package defaults; null safety is this Dart 3 collector's source floor.
    if (minimum != null &&
        (minimumSupported == null ||
            packageLanguageVersion < minimumSupported)) {
      for (final source in sources) {
        _invalid(
          source,
          0,
          'SdkConstraintError',
          minimumSupported == null
              ? 'Analyzer does not declare its minimum supported language version'
              : 'pubspec SDK constraint selects a language version below Analyzer support',
        );
      }
    }
    final tool = Directory(p.join(root.path, '.dart_tool'))..createSync();
    File(p.join(tool.path, 'package_config.json')).writeAsStringSync(
      jsonEncode({
        'configVersion': 2,
        'packages': [
          {
            'name': packageName,
            'rootUri': '../',
            'packageUri': 'lib/',
            'languageVersion':
                languageMinimum.major.toString() +
                '.' +
                languageMinimum.minor.toString(),
          },
        ],
      }),
    );
    return root.path;
  }

  void _validateUris(
    List<DartSource> sources,
    List<String> roots,
    String packageName,
  ) {
    final sourcePaths = sources.map((source) => source.rel).toSet();
    final sourcesByPath = {for (final source in sources) source.rel: source};
    final partOwners = <String, Set<String>>{};
    for (final source in sources) {
      final parsed = parseString(
        content: source.text,
        path: source.path,
        throwIfDiagnostics: false,
      );
      final syntaxError = parsed.errors
          .where(
            (error) =>
                error.diagnosticCode.type == DiagnosticType.SYNTACTIC_ERROR,
          )
          .firstOrNull;
      if (syntaxError != null) {
        _invalid(
          source,
          syntaxError.offset,
          'SyntaxError',
          'syntax errors prevent complete declaration facts',
        );
      }
      for (final directive in parsed.unit.directives) {
        final uris = <String?>[];
        if (directive is ImportDirective) {
          uris.add(directive.uri.stringValue);
          uris.addAll(
            directive.configurations.map(
              (configuration) => configuration.uri.stringValue,
            ),
          );
        } else if (directive is ExportDirective) {
          uris.add(directive.uri.stringValue);
          uris.addAll(
            directive.configurations.map(
              (configuration) => configuration.uri.stringValue,
            ),
          );
        } else if (directive is PartDirective) {
          uris.add(directive.uri.stringValue);
          final uri = directive.uri.stringValue;
          if (uri != null) {
            final target = _partTarget(source, uri, packageName);
            if (target != null && sourcePaths.contains(target)) {
              partOwners.putIfAbsent(target, () => {}).add(source.rel);
            }
          }
        } else if (directive is PartOfDirective) {
          if (directive.uri != null) uris.add(directive.uri!.stringValue);
        } else {
          continue;
        }
        for (final uri in uris) {
          if (uri == null) {
            _invalid(
              source,
              directive.offset,
              'DirectiveError',
              'directive URI is not a string literal',
            );
            continue;
          }
          final parsedUri = Uri.tryParse(uri);
          if (parsedUri == null ||
              (parsedUri.hasScheme &&
                  !uri.startsWith('dart:') &&
                  !uri.startsWith('package:'))) {
            _invalid(
              source,
              directive.offset,
              'DirectiveError',
              'unsupported source URI ' + uri,
            );
          } else if (uri.startsWith('package:')) {
            final rest = uri.substring(8);
            final slash = rest.indexOf('/');
            final name = slash < 0 ? rest : rest.substring(0, slash);
            if (name == packageName && slash >= 0) {
              _checkPath(
                source,
                p.posix.join('lib', rest.substring(slash + 1)),
                roots,
                sourcePaths,
                directive.offset,
              );
            } else if (directive is PartOfDirective) {
              _invalid(
                source,
                directive.offset,
                'PartError',
                'part-of URI must name a selected library in this package',
              );
            }
          } else if (!uri.startsWith('dart:')) {
            _checkPath(
              source,
              p.posix.normalize(p.posix.join(p.posix.dirname(source.rel), uri)),
              roots,
              sourcePaths,
              directive.offset,
            );
          }
        }
      }
    }
    for (final entry in partOwners.entries) {
      if (entry.value.length < 2) continue;
      final owners = entry.value.toList()..sort();
      final message =
          'part ' +
          entry.key +
          ' is declared by multiple libraries: ' +
          owners.join(', ');
      for (final owner in owners) {
        final source = sourcesByPath[owner]!;
        _invalid(source, 0, 'PartOwnershipConflict', message);
      }
      final part = sourcesByPath[entry.key]!;
      _invalid(part, 0, 'PartOwnershipConflict', message);
    }
  }

  String? _partTarget(DartSource source, String uri, String packageName) {
    if (uri.startsWith('package:')) {
      final rest = uri.substring(8);
      final slash = rest.indexOf('/');
      final name = slash < 0 ? rest : rest.substring(0, slash);
      return name == packageName && slash >= 0
          ? p.posix.normalize(p.posix.join('lib', rest.substring(slash + 1)))
          : null;
    }
    final parsed = Uri.tryParse(uri);
    if (parsed == null || parsed.hasScheme) return null;
    return p.posix.normalize(p.posix.join(p.posix.dirname(source.rel), uri));
  }

  void _checkPath(
    DartSource source,
    String target,
    List<String> roots,
    Set<String> sourcePaths,
    int offset,
  ) {
    if (target == '..' ||
        target.startsWith('../') ||
        !roots.any(
          (root) => target == root || p.posix.isWithin(root, target),
        )) {
      _invalid(
        source,
        offset,
        'DirectiveError',
        'source URI escapes the selected roots',
      );
    } else if (!sourcePaths.contains(target)) {
      _invalid(
        source,
        offset,
        'DirectiveError',
        'source URI does not name a selected Dart input',
      );
    } else {
      dependencies.putIfAbsent(source.rel, () => {}).add(target);
    }
  }

  void _propagateInvalidDependencies(List<DartSource> sources) {
    var changed = true;
    while (changed) {
      changed = false;
      for (final source in sources) {
        if (invalidSources.containsKey(source.rel)) continue;
        final invalidTarget = (dependencies[source.rel] ?? const <String>{})
            .where(invalidSources.containsKey)
            .firstOrNull;
        if (invalidTarget == null) continue;
        _invalid(
          source,
          0,
          'IncompleteDependency',
          'source depends on an incomplete selected Dart input',
        );
        changed = true;
      }
    }
  }

  void _invalid(DartSource source, int offset, String kind, String message) {
    invalidSources[source.rel] = message;
    _addProblem(source.rel, offset, kind, message);
  }

  void _addProblem(String file, int offset, String kind, String message) {
    if (problems.any(
      (problem) =>
          problem.file == file &&
          problem.kind == kind &&
          problem.message == message,
    ))
      return;
    problems.add(DartProblem(file, offset, kind, message));
  }
}
