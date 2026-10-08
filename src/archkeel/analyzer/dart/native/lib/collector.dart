import 'dart:convert';
import 'dart:collection';
import 'dart:io';

import 'package:analyzer/dart/analysis/analysis_context_collection.dart';
import 'package:analyzer/dart/analysis/results.dart';
import 'package:analyzer/dart/analysis/utilities.dart';
import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/visitor.dart';
import 'package:analyzer/dart/element/element.dart';
import 'package:analyzer/error/error.dart';
import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;
import 'package:archkeel_dart_analyzer/snapshot.dart';

const sectionNames = [
  'imports',
  'unknowns',
  'symbols',
  'calls',
  'references',
  'bindings',
];

final _languageVersionDiagnosticCodes = {
  for (final name in [
    'illegal_language_version_override',
    'inconsistent_language_version_override',
    'invalid_language_version_override_at_sign',
    'invalid_language_version_override_equals',
    'invalid_language_version_override_greater',
    'invalid_language_version_override_location',
    'invalid_language_version_override_lower_case',
    'invalid_language_version_override_number',
    'invalid_language_version_override_prefix',
    'invalid_language_version_override_trailing_characters',
    'invalid_language_version_override_two_slashes',
  ])
    errorCodeByUniqueName(name)!,
};

String _hash(List<int> value) => sha256.convert(value).toString();
String _id(String prefix, List<Object?> values) =>
    prefix + '-' + _hash(utf8.encode(values.join('\u001f'))).substring(0, 16);

Map<String, Object?> _record(
  String id,
  String area,
  String kind,
  String title,
  List<String> subjects,
  List<String> evidence,
  Map<String, Object?> data, {
  String cls = 'FACT',
}) => {
  'id': id,
  'evidence_class': cls,
  'area': area,
  'kind': kind,
  'title': title,
  'subjects': subjects.toSet().toList()..sort(),
  'evidence_ids': evidence.toSet().toList()..sort(),
  'rule_ids': <String>[],
  'fact_ids': <String>[],
  'provenance': <String>[],
  'data': data,
};

class DartCollector {
  DartCollector(this.request);
  final Map<String, dynamic> request;
  final Map<String, Map<String, Object?>> evidence = {};
  final List<Map<String, Object?>> unknowns = [];
  final List<Map<String, Object?>> symbols = [];
  final List<Map<String, Object?>> calls = [];
  final List<Map<String, Object?>> references = [];
  final Map<Element, String> definitions = HashMap.identity();
  final Map<String, Map<String, Object?>> symbolByQualified = {};
  final Map<String, Map<String, Object?>> symbolById = {};
  final Map<String, String> modules = {};
  final Map<String, String> packages = {};
  final Map<String, DartSource> sourceByRel = {};
  final Map<String, String> moduleForSource = {};
  final Set<String> seenLibraries = {};
  final Set<String> parsedSources = {};
  final List<Map<String, Object?>> imports = [];
  final List<Map<String, Object?>> targets = [];

  Future<Map<String, Object?>> collect() async {
    final snapshot = request['snapshot'] as Map<String, dynamic>;
    final tmp = await Directory.systemTemp.createTemp('archkeel-dart-');
    try {
      final prepared = await DartSnapshot(request).prepare(tmp);
      final sources = prepared.sources;
      for (final source in sources) {
        modules[source.rel] = source.module;
        packages[source.module] = source.module.substring(
          0,
          source.module.lastIndexOf('.'),
        );
        sourceByRel[source.rel] = source;
      }
      for (final problem in prepared.problems) {
        _gap(problem.file, problem.offset, problem.kind, problem.message);
      }
      await _analyze(prepared.stagedRoot, sources, prepared.invalidSources);
      _emitImports(sources, prepared.packageName, prepared.invalidSources);
      _emitDuplicateGaps();
      _finalizeInventories();
      final inputs = [
        ...sources.map(
          (source) => {
            'path': source.rel,
            'digest': _hash(source.bytes),
            'role': 'selected',
          },
        ),
        {
          'path': 'pubspec.yaml',
          'digest': _hash(prepared.pubspecBytes),
          'role': 'resolution',
        },
      ]..sort((a, b) => (a['path'] as String).compareTo(b['path'] as String));
      final fileFacts = _files(sources);
      final sections = <String, List<Map<String, Object?>>>{
        'imports': imports,
        'unknowns': unknowns,
        'symbols': symbols,
        'calls': calls,
        'references': references,
        'bindings': [],
      };
      final facts = <String, Object?>{
        'profile': 'archkeel-dart-analyzer',
        'adapter': {
          'name': 'archkeel-dart-analyzer',
          'version': '1.0.0',
          'code_digest': await _collectorDigest(),
        },
        'runtime': {
          'name': 'dart',
          'version': Platform.version.split(' ').first,
          'required': '>=3.9,<4',
          'requirement_state': 'declared',
        },
        'source': {
          'git_head': snapshot['git_head'],
          'dirty': snapshot['dirty'],
          'source_digest': _hash(utf8.encode(inputs.map(jsonEncode).join())),
          'scope': prepared.roots.map((root) => root + '/**/*.dart').toList(),
        },
        'capabilities': {
          'sections': sectionNames,
          'resolution_features': ['inner-uml-v1'],
          'constructs': [],
        },
        'inputs': inputs,
        'files': fileFacts,
        'imports': targets,
        'uncertain_reexports': [],
        'type_shapes': [],
        'state': {'classes': [], 'functions': []},
        'sections': sectionNames
            .map((name) => {'name': name, 'records': sections[name]})
            .toList(),
        'coverage': {
          'selected_files': sources.map((source) => source.rel).toList(),
          'files_read': sources.length,
          'files_parsed': parsedSources.length,
          'full_scope': unknowns.isEmpty && sources.isNotEmpty,
          'gaps': unknowns,
        },
        'evidence': evidence.values.toList()
          ..sort((a, b) => (a['id'] as String).compareTo(b['id'] as String)),
        'candidate_evidence': [],
      };
      return {'protocol_version': '2.0.0', 'facts': facts};
    } finally {
      await tmp.delete(recursive: true);
    }
  }

  Future<void> _analyze(
    String root,
    List<DartSource> sources,
    Map<String, String> invalidSources,
  ) async {
    final libraries = <(DartSource, List<(DartSource, ResolvedUnitResult)>)>[];
    final contexts = AnalysisContextCollection(
      includedPaths: [root],
      sdkPath: p.dirname(p.dirname(Platform.resolvedExecutable)),
    );
    try {
      for (final source in sources) {
        if (invalidSources.containsKey(source.rel)) continue;
        final path = p.join(root, source.rel);
        final result = await contexts
            .contextFor(path)
            .currentSession
            .getResolvedLibraryContaining(path);
        if (result is! ResolvedLibraryResult) {
          _gap(
            source.rel,
            1,
            'LibraryError',
            'library did not resolve completely',
          );
          continue;
        }
        final languageVersionErrors = result.units
            .expand((unit) => unit.diagnostics)
            .where(
              (diagnostic) => _languageVersionDiagnosticCodes.contains(
                diagnostic.diagnosticCode,
              ),
            )
            .toList();
        if (languageVersionErrors.isNotEmpty) {
          _gap(
            source.rel,
            1,
            'LanguageVersionError',
            'unsupported or inconsistent language version override: ' +
                languageVersionErrors
                    .map(
                      (diagnostic) =>
                          diagnostic.diagnosticCode.lowerCaseName +
                          '@' +
                          diagnostic.offset.toString(),
                    )
                    .toSet()
                    .join(', '),
          );
          continue;
        }
        final syntaxErrors = result.units
            .expand((unit) => unit.diagnostics)
            .where(
              (diagnostic) =>
                  diagnostic.diagnosticCode.type ==
                  DiagnosticType.SYNTACTIC_ERROR,
            )
            .toList();
        if (syntaxErrors.isNotEmpty) {
          _gap(
            source.rel,
            1,
            'SyntaxError',
            'syntax errors prevent complete declaration facts: ' +
                syntaxErrors
                    .map(
                      (diagnostic) =>
                          diagnostic.diagnosticCode.lowerCaseName +
                          '@' +
                          diagnostic.offset.toString(),
                    )
                    .toSet()
                    .join(', '),
          );
          continue;
        }
        final mainPath = p
            .relative(result.units.first.path, from: root)
            .replaceAll(p.separator, '/');
        if (!seenLibraries.add(mainPath)) continue;
        final main = sources.where((s) => s.rel == mainPath).firstOrNull;
        if (main == null) {
          _gap(
            source.rel,
            1,
            'LibraryError',
            'library source is outside selected roots',
          );
          continue;
        }
        final units = <(DartSource, ResolvedUnitResult)>[];
        for (final unit in result.units) {
          final rel = p
              .relative(unit.path, from: root)
              .replaceAll(p.separator, '/');
          moduleForSource[rel] = main.module;
          if (sourceByRel.containsKey(rel)) parsedSources.add(rel);
        }
        for (final unit in result.units) {
          final rel = p
              .relative(unit.path, from: root)
              .replaceAll(p.separator, '/');
          final sourceUnit = sourceByRel[rel];
          if (sourceUnit == null) {
            _gap(
              mainPath,
              1,
              'PartError',
              'library contains an unselected part',
            );
            continue;
          }
          final libraryUnit = DartSource(
            sourceUnit.path,
            rel,
            main.module,
            sourceUnit.text,
            sourceUnit.bytes,
          );
          units.add((libraryUnit, unit));
        }
        libraries.add((main, units));
      }
      // Index every selected declaration before resolving any source site.
      for (final library in libraries) {
        for (final entry in library.$2) {
          _walk(entry.$1, entry.$2.unit);
        }
      }
      for (final library in libraries) {
        for (final entry in library.$2) {
          _emitBases(entry.$1, entry.$2);
          _emitSites(entry.$1, entry.$2);
        }
      }
    } finally {
      await contexts.dispose();
    }
  }

  void _emitImports(
    List<DartSource> sources,
    String package,
    Map<String, String> invalidSources,
  ) {
    for (final source in sources) {
      if (invalidSources.containsKey(source.rel)) continue;
      final unit = parseString(
        content: source.text,
        path: source.path,
        throwIfDiagnostics: false,
      ).unit;
      for (final directive in unit.directives) {
        final namespaceDirective = switch (directive) {
          ImportDirective value => value,
          ExportDirective value => value,
          _ => null,
        };
        if (namespaceDirective == null) continue;
        final seenUris = <String>{};
        for (final uriNode in [
          namespaceDirective.uri,
          ...namespaceDirective.configurations.map(
            (configuration) => configuration.uri,
          ),
        ]) {
          final uri = uriNode.stringValue;
          if (uri == null || !seenUris.add(uri)) continue;
          final target = _importTarget(source, uri, package, sources);
          final module = moduleForSource[source.rel] ?? source.module;
          final combinators = switch (directive) {
            ImportDirective value => value.combinators,
            ExportDirective value => value.combinators,
            _ => const <Combinator>[],
          };
          Set<String>? shown;
          final hidden = <String>{};
          for (final combinator in combinators) {
            if (combinator is ShowCombinator) {
              final names = combinator.shownNames
                  .map((name) => name.name)
                  .toSet();
              if (shown == null) {
                shown = names;
              } else {
                shown.retainAll(names);
              }
            } else if (combinator is HideCombinator) {
              final names = combinator.hiddenNames
                  .map((name) => name.name)
                  .toSet();
              if (shown == null) {
                hidden.addAll(names);
              } else {
                shown.removeAll(names);
              }
            }
          }
          final selected =
              shown?.where((name) => !hidden.contains(name)).toList()?..sort();
          final symbols = selected == null || selected.isEmpty
              ? <String?>[null]
              : selected.cast<String?>();
          final symbolsKnown = selected != null && selected.isNotEmpty;
          for (final symbol in symbols) {
            final id = _id('DARTIMP', [
              source.rel,
              directive.offset,
              uri,
              symbol,
            ]);
            final evidenceId = _cite(source, directive);
            imports.add(
              _record(
                id,
                'dependencies',
                'import',
                module + ' imports ' + uri,
                [module, target.$1],
                [evidenceId],
                {
                  'source_module': module,
                  'source_package': packages[module] ?? module,
                  'target_module': target.$1,
                  'target_package': target.$2,
                  'symbol': symbol,
                  'binding':
                      symbol ??
                      (directive is ImportDirective
                          ? directive.prefix?.name
                          : null),
                  'symbols_known': symbolsKnown,
                  'relative_level': 0,
                  'under_type_checking': false,
                  'ordinary_module': true,
                  'module_level_import': true,
                  'reexport': directive is ExportDirective,
                  'reexport_chain': symbol == null
                      ? <String>[]
                      : [target.$1 + '.' + symbol],
                  'origin_definition': symbol == null
                      ? null
                      : target.$1 + '.' + symbol,
                  'symbol_visibility': symbol == null
                      ? null
                      : symbol.startsWith('_')
                      ? 'private'
                      : 'public_name',
                },
              ),
            );
            targets.add(
              target.$4 != null
                  ? {
                      'kind': 'local',
                      'import_id': id,
                      'module': target.$1,
                      'file': target.$4,
                      'runtime_file': null,
                      'declaration_file': null,
                    }
                  : uri.startsWith('dart:')
                  ? {'kind': 'builtin', 'import_id': id, 'name': target.$1}
                  : uri.startsWith('package:') &&
                        uri.substring(8).split('/').first != package
                  ? {
                      'kind': 'external',
                      'import_id': id,
                      'package': uri.substring(8).split('/').first,
                    }
                  : {
                      'kind': 'unresolved',
                      'import_id': id,
                      'specifier': uri,
                      'reason': 'target is not selected',
                    },
            );
          }
        }
      }
    }
    imports.sort((a, b) => (a['id'] as String).compareTo(b['id'] as String));
    targets.sort(
      (a, b) => (a['import_id'] as String).compareTo(b['import_id'] as String),
    );
  }

  (String, String?, String?, String?) _importTarget(
    DartSource source,
    String uri,
    String package,
    List<DartSource> sources,
  ) {
    if (uri.startsWith('dart:')) {
      final module =
          'dart.' + uri.substring(5).replaceAll('/', '.').replaceAll('-', '_');
      return (module, 'dart', null, null);
    }
    String rel;
    if (uri.startsWith('package:')) {
      final rest = uri.substring(8);
      final slash = rest.indexOf('/');
      final name = slash < 0 ? rest : rest.substring(0, slash);
      if (name != package) {
        final module = dartModuleName(
          rest.replaceFirst(RegExp(r'\.dart$'), ''),
        );
        return (module ?? uri, name, null, null);
      }
      rel = p.posix.join('lib', slash < 0 ? '' : rest.substring(slash + 1));
    } else {
      rel = p.posix.normalize(p.posix.join(p.posix.dirname(source.rel), uri));
    }
    final found = sources.where((s) => s.rel == rel).toList();
    if (found.length != 1) return (uri, null, uri, null);
    return (
      found.single.module,
      packages[found.single.module],
      null,
      found.single.rel,
    );
  }

  void _walk(DartSource source, CompilationUnit unit) {
    for (final declaration in unit.declarations) {
      if (declaration is ClassDeclaration) {
        final classKind = declaration.interfaceKeyword == null
            ? 'class'
            : 'protocol';
        final owner = _classifier(
          source,
          declaration,
          declaration.namePart.typeName.lexeme,
          classKind,
        );
        _indexElement(
          declaration.declaredFragment?.element,
          owner['qualified'] as String,
        );
        _classBody(source, declaration.body, owner);
        _indexClassMembers(
          source,
          declaration.body is BlockClassBody
              ? (declaration.body as BlockClassBody).members
              : const <ClassMember>[],
          owner,
        );
      } else if (declaration is EnumDeclaration) {
        for (final constant in declaration.body.constants) {
          _indexElement(
            constant.declaredFragment?.element,
            '${source.module}.${declaration.namePart.typeName.lexeme}.${constant.name.lexeme}',
          );
        }
        final enumAttributes = declaration.body.constants.map((constant) {
          final name = constant.name.lexeme;
          return {
            'name': name,
            'annotation': null,
            'visibility': {
              'kind': 'public',
              'basis': 'language',
              'spelling': name,
            },
            'definition_id': _id('DARTATTR', [
              source.rel,
              constant.offset,
              source.module + '.' + declaration.namePart.typeName.lexeme,
              name,
            ]),
            'evidence_ids': [_cite(source, constant)],
            'static': true,
          };
        }).toList();
        final owner = _classifier(
          source,
          declaration,
          declaration.namePart.typeName.lexeme,
          'enum',
          enumAttributes: enumAttributes,
          enumMembers: declaration.body.constants
              .map((constant) => constant.name.lexeme)
              .toList(),
        );
        _indexElement(
          declaration.declaredFragment?.element,
          owner['qualified'] as String,
        );
        _members(source, declaration.body.members, owner);
        _indexClassMembers(
          source,
          declaration.body is BlockClassBody
              ? (declaration.body as BlockClassBody).members
              : const <ClassMember>[],
          owner,
        );
      } else if (declaration is MixinDeclaration) {
        _gap(
          source.rel,
          declaration.offset,
          'UnsupportedDeclaration',
          'mixin declarations have no shared UML entity kind',
        );
      } else if (declaration is ExtensionDeclaration ||
          declaration is ExtensionTypeDeclaration) {
        _gap(
          source.rel,
          declaration.offset,
          'UnsupportedDeclaration',
          'extension declarations have no shared UML entity kind',
        );
      } else if (declaration is FunctionDeclaration) {
        final id = _function(
          source,
          declaration,
          declaration.name.lexeme,
          null,
          declaration.functionExpression.parameters,
          declaration.returnType?.toSource(),
        );
        _indexElement(
          declaration.declaredFragment?.element,
          symbolsByIdName(id),
        );
      } else if (declaration is GenericTypeAlias) {
        final id = _simple(
          source,
          declaration,
          declaration.name.lexeme,
          'alias',
          declaration.type.toSource(),
        );
        _indexElement(
          declaration.declaredFragment?.element,
          symbolsByIdName(id),
        );
      } else if (declaration is FunctionTypeAlias) {
        final id = _simple(
          source,
          declaration,
          declaration.name.lexeme,
          'alias',
          declaration.returnType?.toSource(),
        );
        _indexElement(
          declaration.declaredFragment?.element,
          symbolsByIdName(id),
        );
      } else if (declaration is TopLevelVariableDeclaration) {
        for (final variable in declaration.variables.variables) {
          final id = _variable(
            source,
            variable,
            null,
            declaration.variables.type?.toSource(),
            declaration.variables.isConst,
          );
          _indexVariable(
            variable.declaredFragment?.element,
            symbolsByIdName(id),
          );
        }
      } else {
        _gap(
          source.rel,
          declaration.offset,
          'UnsupportedDeclaration',
          'declaration kind is not represented',
        );
      }
    }
  }

  void _classBody(
    DartSource source,
    ClassBody body,
    Map<String, Object?> owner,
  ) {
    switch (body) {
      case BlockClassBody(:final members):
        _members(source, members, owner);
      case EmptyClassBody():
        _members(source, const <ClassMember>[], owner);
    }
  }

  void _addSymbol(Map<String, Object?> record) {
    symbols.add(record);
    final data = record['data'] as Map<String, Object?>;
    final name = data['qualified_name'] as String;
    symbolByQualified[name] = record;
    symbolById[record['id'] as String] = record;
  }

  String symbolsByIdName(String id) =>
      (symbolById[id]!['data'] as Map<String, Object?>)['qualified_name']
          as String;

  void _indexElement(Element? element, String qualified) {
    if (element != null) definitions[element.baseElement] = qualified;
  }

  String? _definitionOf(Element? element) =>
      element == null ? null : definitions[element.baseElement];

  void _indexVariable(VariableElement? element, String qualified) {
    if (element == null) return;
    _indexElement(element, qualified);
    if (element is PropertyInducingElement) {
      _indexElement(element.getter, qualified);
      _indexElement(element.setter, qualified);
    }
  }

  void _indexClassMembers(
    DartSource source,
    List<ClassMember> members,
    Map<String, Object?> owner,
  ) {
    for (final member in members) {
      final ownerName = owner['qualified'] as String;
      if (member is FieldDeclaration) {
        for (final variable in member.fields.variables) {
          _indexVariable(
            variable.declaredFragment?.element,
            '$ownerName.${variable.name.lexeme}',
          );
        }
      } else if (member is MethodDeclaration) {
        final record = symbols.firstWhere(
          (item) =>
              item['data'] is Map<String, Object?> &&
              (item['data'] as Map<String, Object?>)['source_file'] ==
                  source.rel &&
              (item['data'] as Map<String, Object?>)['qualified_name'] ==
                  '$ownerName.${member.name.lexeme}',
        );
        _indexElement(
          member.declaredFragment?.element,
          symbolsByIdName(record['id'] as String),
        );
      } else if (member is ConstructorDeclaration) {
        final suffix = member.name?.lexeme;
        final constructorName = suffix == null
            ? owner['name'] as String
            : '${owner['name']}.$suffix';
        final element = member.declaredFragment?.element;
        _indexElement(element, '$ownerName.$constructorName');
      }
    }
  }

  void _emitBases(DartSource source, ResolvedUnitResult resolved) {
    for (final declaration in resolved.unit.declarations) {
      if (declaration is! ClassDeclaration && declaration is! EnumDeclaration)
        continue;
      final name = switch (declaration) {
        ClassDeclaration value => value.namePart.typeName.lexeme,
        EnumDeclaration value => value.namePart.typeName.lexeme,
        _ => '',
      };
      final record = symbolByQualified['${source.module}.$name'];
      if (record == null) continue;
      final bases = <Map<String, Object?>>[];
      if (declaration is ClassDeclaration &&
          declaration.extendsClause != null) {
        bases.add(
          _baseFact(source, declaration.extendsClause!.superclass, 'inherits'),
        );
      }
      if (declaration is ClassDeclaration) {
        for (final type
            in declaration.withClause?.mixinTypes ?? const <NamedType>[]) {
          bases.add(_baseFact(source, type, 'inherits'));
        }
        for (final type
            in declaration.implementsClause?.interfaces ??
                const <NamedType>[]) {
          bases.add(_baseFact(source, type, 'realizes'));
        }
      } else if (declaration is EnumDeclaration) {
        for (final type
            in declaration.implementsClause?.interfaces ??
                const <NamedType>[]) {
          bases.add(_baseFact(source, type, 'realizes'));
        }
      }
      (record['data'] as Map<String, Object?>)['base_declarations'] = bases;
    }
  }

  Map<String, Object?> _baseFact(
    DartSource source,
    NamedType type,
    String kind,
  ) {
    final target = _definitionOf(type.type?.element);
    final targetRecord = target == null ? null : symbolByQualified[target];
    final isResolved = targetRecord?['kind'] == 'class';
    return {
      'id': _id('DARTBASE', [source.rel, type.offset, kind]),
      'relationship_kind': kind,
      'status': isResolved ? 'resolved' : 'unresolved',
      'targets': isResolved ? [target] : <String>[],
      'candidate_count': isResolved ? 1 : 0,
      'candidates_truncated': false,
      'expression': type.toSource(),
      'reason': isResolved
          ? 'Analyzer resolved local declared type'
          : 'base type is external or unresolved',
      'evidence_ids': [_cite(source, type)],
    };
  }

  void _emitSites(DartSource source, ResolvedUnitResult resolved) {
    resolved.unit.accept(_DartSiteVisitor(this, source, resolved));
  }

  Map<String, Object?> _site(
    DartSource source,
    AstNode node,
    String scope,
    String scopeId,
    String expression,
    Element? target, {
    required bool call,
    String? use,
    List<Map<String, Object?>> resultBindings = const [],
    Map<String, Object?>? construction,
  }) {
    final targetName = _definitionOf(target);
    final targetRecord = targetName == null
        ? null
        : symbolByQualified[targetName];
    final isAllowedCallTarget =
        !call ||
        construction != null && targetRecord?['kind'] == 'class' ||
        targetRecord?['kind'] == 'method' ||
        targetRecord?['kind'] == 'function';
    final isResolved = targetName != null && isAllowedCallTarget;
    final id = _id(call ? 'DARTCALL' : 'DARTREF', [
      source.rel,
      node.offset,
      scopeId,
      expression,
    ]);
    final data = <String, Object?>{
      'source_scope': scope,
      'source_definition_id': scopeId,
      'source_module': moduleForSource[source.rel] ?? source.module,
      'source_file': source.rel,
      'expression': expression,
      'status': isResolved ? 'resolved' : 'unresolved',
      'targets': isResolved ? [targetName] : <String>[],
      'candidate_count': isResolved ? 1 : 0,
      'candidates_truncated': false,
      'reason': isResolved
          ? 'Analyzer resolved the source element'
          : 'target is external, dynamic, or unresolved',
      if (!call) 'use': use ?? 'read',
      if (resultBindings.isNotEmpty) 'result_bindings': resultBindings,
      if (construction != null) 'construction': construction,
    };
    final record = _record(
      id,
      'source',
      call ? 'call' : 'reference',
      expression,
      [scope],
      [_cite(source, node)],
      data,
    );
    (call ? calls : references).add(record);
    return record;
  }

  Map<String, Object?> _localBinding(
    DartSource source,
    VariableDeclaration node,
    String scope,
    String scopeId,
  ) {
    final name = node.name.lexeme;
    final qualified = '$scope.$name';
    final id = _id('DARTBIND', [source.rel, node.offset, scopeId, name]);
    final initializer =
        node.initializer is InstanceCreationExpression ||
            node.initializer is MethodInvocation ||
            node.initializer is FunctionExpressionInvocation
        ? null
        : node.initializer?.toSource();
    final annotation = switch (node.parent) {
      VariableDeclarationList(:final type) => type?.toSource(),
      _ => null,
    };
    final data = <String, Object?>{
      ..._meta(source, node, name, 'binding', scope, scopeId),
      'symbol_category': 'dynamic_binding',
      'annotation': annotation,
      'initializer': initializer,
      'definition_contexts': <Object?>[],
    };
    final record = _record(
      id,
      'source',
      'binding',
      '$qualified declaration',
      [qualified],
      [_cite(source, node)],
      data,
    );
    _addSymbol(record);
    final element = node.declaredFragment?.element;
    _indexElement(element, qualified);
    return {
      'id': id,
      'name': name,
      'qualified_name': qualified,
      'initializer': initializer,
      'annotation': annotation,
      'element': element,
      'evidence_ids': [_cite(source, node)],
    };
  }

  Map<String, Object?> _meta(
    DartSource source,
    AstNode node,
    String name,
    String kind,
    String? parent,
    String? parentId,
  ) => {
    'qualified_name': parent == null
        ? source.module + '.' + name
        : parent + '.' + name,
    'module': source.module,
    'source_file': source.rel,
    'package': packages[source.module],
    'name': name,
    'parent': parent,
    'lexical_parent_id': parentId,
    'visibility_detail': {
      'kind': name.startsWith('_') ? 'private' : 'public',
      'basis': 'language',
      'spelling': name,
    },
    'symbol_category': kind == 'class' ? 'class' : kind,
    'source_binding_unique': true,
    'source_member_binding_static': true,
    'class_header_static': true,
    'decorators': <String>[],
    'signature_complete': true,
    'overload_signature': false,
  };

  Map<String, Object?> _classifier(
    DartSource source,
    AstNode node,
    String name,
    String classKind, {
    List<String>? enumMembers,
    List<Map<String, Object?>>? enumAttributes,
  }) {
    final qualified = source.module + '.' + name;
    final id = _id('DARTDEF', [source.rel, node.offset, qualified, 'class']);
    final attributes = enumAttributes ?? <Map<String, Object?>>[];
    _addSymbol(
      _record(
        id,
        'source',
        'class',
        qualified + ' declaration',
        [qualified],
        [_cite(source, node)],
        {
          ..._meta(source, node, name, 'class', null, null),
          'class_kind': classKind,
          'enum_members': enumMembers ?? <String>[],
          'attribute_declarations': attributes,
          'member_inventories': [
            {
              'schema_version': '1.0.0',
              'kind': 'attribute',
              'status': 'complete',
              'definition_ids': attributes
                  .map((attribute) => attribute['definition_id'] as String)
                  .toList(),
              'reason': null,
            },
            {
              'schema_version': '1.0.0',
              'kind': 'method',
              'status': 'complete',
              'definition_ids': <String>[],
              'reason': null,
            },
          ],
        },
      ),
    );
    return {
      'id': id,
      'name': name,
      'qualified': qualified,
      'attributes': attributes,
    };
  }

  void _members(
    DartSource source,
    List<ClassMember> members,
    Map<String, Object?> owner,
  ) {
    final attrs =
        (owner['attributes'] as List<Map<String, Object?>>?)?.toList() ??
        <Map<String, Object?>>[];
    final fieldTypes = <String, String>{};
    for (final member in members.whereType<FieldDeclaration>()) {
      final type = member.fields.type?.toSource();
      if (type == null) continue;
      for (final variable in member.fields.variables) {
        fieldTypes[variable.name.lexeme] = type;
      }
    }
    final methods = <String>[];
    for (final member in members) {
      if (member is FieldDeclaration) {
        for (final variable in member.fields.variables) {
          final name = variable.name.lexeme;
          final id = _id('DARTATTR', [
            source.rel,
            variable.offset,
            owner['qualified'],
            name,
          ]);
          attrs.add({
            'name': name,
            'annotation': member.fields.type?.toSource(),
            'visibility': {
              'kind': name.startsWith('_') ? 'private' : 'public',
              'basis': 'language',
              'spelling': name,
            },
            'definition_id': id,
            'evidence_ids': [_cite(source, variable)],
            'static': member.isStatic,
            'constant': member.fields.isConst
                ? variable.initializer?.toSource()
                : null,
          });
        }
      } else if (member is MethodDeclaration) {
        final name = member.name.lexeme;
        methods.add(
          _function(
            source,
            member,
            name,
            owner,
            member.parameters,
            member.returnType?.toSource(),
            member.isStatic,
          ),
        );
      } else if (member is ConstructorDeclaration) {
        final suffix = member.name?.lexeme;
        final name = suffix == null
            ? owner['name'] as String
            : (owner['name'] as String) + '.' + suffix;
        methods.add(
          _function(
            source,
            member,
            name,
            owner,
            member.parameters,
            null,
            true,
            member.factoryKeyword == null ? 'constructor' : 'factory',
            fieldTypes,
          ),
        );
      } else {
        _gap(
          source.rel,
          member.offset,
          'UnsupportedMember',
          'class member kind is not represented',
        );
      }
    }
    final record = symbols.firstWhere((r) => r['id'] == owner['id']);
    final data = record['data'] as Map<String, Object?>;
    data['attribute_declarations'] = attrs;
    final inventories = (data['member_inventories'] as List)
        .cast<Map<String, Object?>>();
    inventories[0]['definition_ids'] = attrs
        .map((a) => a['definition_id'])
        .toList();
    inventories[1]['definition_ids'] = methods;
  }

  String _function(
    DartSource source,
    AstNode node,
    String name,
    Map<String, Object?>? parent,
    FormalParameterList? list,
    String? returns, [
    bool isStatic = false,
    String? methodKind,
    Map<String, String>? fieldTypes,
  ]) {
    final qualifiedParent = parent?['qualified'] as String?;
    final parentId = parent?['id'] as String?;
    final qualified = qualifiedParent == null
        ? source.module + '.' + name
        : qualifiedParent + '.' + name;
    final id = _id('DARTDEF', [
      source.rel,
      node.offset,
      qualified,
      parent == null ? 'function' : 'method',
    ]);
    final params = _params(source, list, fieldTypes ?? const {});
    _addSymbol(
      _record(
        id,
        'source',
        parent == null ? 'function' : 'method',
        qualified + ' declaration',
        [qualified],
        [_cite(source, node)],
        {
          ..._meta(
            source,
            node,
            name,
            parent == null ? 'function' : 'method',
            qualifiedParent,
            parentId,
          ),
          'annotation': null,
          'returns':
              (methodKind == 'constructor' || methodKind == 'factory') &&
                  parent != null
              ? parent['name']
              : returns,
          'parameters': params.values,
          'method_kind': methodKind ?? (isStatic ? 'static' : 'instance'),
          'signature_complete': params.complete,
        },
      ),
    );
    return id;
  }

  ({List<Map<String, Object?>> values, bool complete}) _params(
    DartSource source,
    FormalParameterList? list,
    Map<String, String> fieldTypes,
  ) {
    if (list == null) return (values: <Map<String, Object?>>[], complete: true);
    final result = <Map<String, Object?>>[];
    var complete = true;
    for (final item in list.parameters) {
      var actual = item;
      String? defaultValue;
      var kind = item.isNamed ? 'keyword_only' : 'positional';
      if (item is DefaultFormalParameter) {
        actual = item.parameter;
        defaultValue = item.defaultValue?.toSource();
        if (item.isOptional && defaultValue == null) defaultValue = 'null';
      }
      final name = switch (actual) {
        SimpleFormalParameter() => actual.name?.lexeme,
        FieldFormalParameter() => actual.name.lexeme,
        SuperFormalParameter() => actual.name.lexeme,
        FunctionTypedFormalParameter() => actual.name.lexeme,
        _ => null,
      };
      if (name == null) {
        complete = false;
        _gap(
          source.rel,
          item.offset,
          'UnsupportedParameter',
          'parameter form is not represented in the shared signature',
        );
        continue;
      }
      final type = switch (actual) {
        SimpleFormalParameter() => actual.type?.toSource(),
        FieldFormalParameter() =>
          actual.type?.toSource() ?? fieldTypes[actual.name.lexeme],
        SuperFormalParameter() => actual.type?.toSource(),
        FunctionTypedFormalParameter() =>
          '${actual.returnType?.toSource() ?? 'dynamic'} Function'
              '${actual.typeParameters?.toSource() ?? ''}'
              '${actual.parameters.toSource()}'
              '${actual.question == null ? '' : '?'}',
        _ => null,
      };
      final supported = switch (actual) {
        SimpleFormalParameter() || FunctionTypedFormalParameter() => true,
        FieldFormalParameter() || SuperFormalParameter() => type != null,
        _ => false,
      };
      if (!supported) {
        complete = false;
        _gap(
          source.rel,
          item.offset,
          'UnsupportedParameter',
          'parameter type is not represented in the shared signature',
        );
      }
      result.add({
        'name': name,
        'annotation': type,
        'kind': kind,
        'default': defaultValue,
        'default_known': true,
      });
    }
    return (values: result, complete: complete);
  }

  String _variable(
    DartSource source,
    VariableDeclaration node,
    String? parent,
    String? type,
    bool isConst,
  ) {
    final name = node.name.lexeme;
    return _simple(
      source,
      node,
      name,
      isConst ? 'constant' : 'attribute',
      type,
      constant: isConst ? node.initializer?.toSource() : null,
      parent: parent,
    );
  }

  String _simple(
    DartSource source,
    AstNode node,
    String name,
    String kind,
    String? annotation, {
    String? constant,
    String? parent,
  }) {
    final qualified = parent == null
        ? source.module + '.' + name
        : parent + '.' + name;
    final id = _id('DARTDEF', [source.rel, node.offset, qualified, kind]);
    _addSymbol(
      _record(
        id,
        'source',
        kind,
        qualified + ' declaration',
        [qualified],
        [_cite(source, node)],
        {
          ..._meta(source, node, name, kind, parent, null),
          if (kind == 'alias') 'symbol_category': 'type_alias',
          'annotation': annotation,
          'constant': constant,
        },
      ),
    );
    return id;
  }

  String _cite(DartSource source, AstNode? node, [bool file = false]) {
    final offset = file ? 0 : node!.offset;
    final end = file ? 0 : node!.end;
    final before = source.text.substring(
      0,
      offset.clamp(0, source.text.length),
    );
    final line = file
        ? (source.lines.isEmpty ? 0 : 1)
        : '\n'.allMatches(before).length + 1;
    final column = file ? 0 : before.length - before.lastIndexOf('\n') - 1;
    final endLine = file
        ? line
        : line +
              '\n'
                  .allMatches(
                    source.text.substring(
                      offset,
                      end.clamp(offset, source.text.length),
                    ),
                  )
                  .length;
    final id = _id('EVD', [source.rel, line, endLine, column]);
    evidence[id] = {
      'id': id,
      'file': source.rel,
      'line': line,
      'end_line': endLine,
      'column': column,
      'excerpt': file
          ? (source.lines.isEmpty ? '' : source.lines.first.trimRight())
          : node!.toSource(),
    };
    return id;
  }

  void _gap(
    String rel,
    int offset,
    String kind,
    String message, {
    List<String>? evidenceIds,
  }) {
    final source = _source(rel);
    final line = source == null
        ? 1
        : '\n'
                  .allMatches(
                    source.text.substring(
                      0,
                      offset.clamp(0, source.text.length),
                    ),
                  )
                  .length +
              1;
    final id = _id('COVERAGE', [rel, line, kind, message]);
    if (unknowns.any((item) => item['id'] == id)) return;
    final cited =
        evidenceIds ??
        (source == null ? <String>[] : [_cite(source, null, true)]);
    unknowns.add(
      _record(
        id,
        'analysis_coverage',
        kind,
        rel + ':' + line.toString() + ' could not be analyzed: ' + message,
        [rel + ':' + line.toString()],
        cited,
        {'file': rel, 'line': line, 'message': message},
        cls: 'UNKNOWN',
      ),
    );
  }

  DartSource? _source(String rel) {
    return sourceByRel[rel];
  }

  Future<String> _collectorDigest() async {
    final root = Directory.fromUri(Platform.script).parent.parent;
    final sourceFiles = <File>[];
    await for (final entity in root.list(recursive: true)) {
      if (entity is File && entity.path.endsWith('.dart'))
        sourceFiles.add(entity);
    }
    final bytes = <int>[];
    sourceFiles.sort((a, b) => a.path.compareTo(b.path));
    for (final file in sourceFiles) {
      bytes
        ..addAll(utf8.encode(p.relative(file.path, from: root.path)))
        ..addAll(await file.readAsBytes());
    }
    for (final name in ['pubspec.yaml', 'pubspec.lock']) {
      final file = File(p.join(root.path, name));
      if (file.existsSync()) {
        bytes
          ..addAll(utf8.encode(name))
          ..addAll(await file.readAsBytes());
      }
    }
    return _hash(bytes);
  }

  void _finalizeInventories() {
    if (unknowns.isEmpty) return;
    for (final item in symbols) {
      final data = item['data'] as Map<String, Object?>;
      final inventories = data['member_inventories'];
      if (inventories is List) {
        for (final receipt in inventories.cast<Map<String, Object?>>()) {
          receipt['status'] = 'partial';
          receipt['reason'] =
              'source contains unsupported or incomplete declarations';
        }
      }
    }
  }

  void _emitDuplicateGaps() {
    final counts = <String, int>{};
    final evidenceByName = <String, Set<String>>{};
    void add(String name, List<String> evidenceIds) {
      counts.update(name, (count) => count + 1, ifAbsent: () => 1);
      (evidenceByName[name] ??= <String>{}).addAll(evidenceIds);
    }

    for (final item in symbols) {
      final data = item['data'] as Map<String, Object?>;
      final name = data['qualified_name'] as String;
      add(name, (item['evidence_ids'] as List).cast<String>());
      final attributes = data['attribute_declarations'];
      if (attributes is! List) continue;
      for (final attribute in attributes.cast<Map<String, Object?>>()) {
        add(
          '$name.${attribute['name']}',
          (attribute['evidence_ids'] as List).cast<String>(),
        );
      }
    }

    for (final entry in counts.entries.where((entry) => entry.value > 1)) {
      final evidenceIds = evidenceByName[entry.key]!.toList()..sort();
      final file = evidence[evidenceIds.first]!['file'] as String;
      _gap(
        file,
        0,
        'DuplicateDeclaration',
        'duplicate declaration ' + entry.key,
        evidenceIds: evidenceIds,
      );
    }

    for (final item in symbols) {
      final data = item['data'] as Map<String, Object?>;
      final name = data['qualified_name'] as String;
      if (counts[name] != 1) data['source_binding_unique'] = false;

      final attributes = data['attribute_declarations'];
      if (attributes is! List) continue;
      final uniqueAttributes = attributes
          .cast<Map<String, Object?>>()
          .where(
            (attribute) =>
                counts[name] == 1 && counts['$name.${attribute['name']}'] == 1,
          )
          .toList();
      if (uniqueAttributes.length == attributes.length) continue;
      data['attribute_declarations'] = uniqueAttributes;
      final inventories = (data['member_inventories'] as List)
          .cast<Map<String, Object?>>();
      inventories[0]['definition_ids'] = uniqueAttributes
          .map((attribute) => attribute['definition_id'])
          .toList();
    }
  }

  List<Map<String, Object?>> _files(List<DartSource> sources) {
    final logicalSources = sources.where(
      (s) =>
          parsedSources.contains(s.rel) &&
          (moduleForSource[s.rel] ?? s.module) == s.module,
    );
    return logicalSources.map((s) {
      final evidenceId = _cite(s, null, true);
      return {
        'id': _id('FILE', [s.module]),
        'rel_path': s.rel,
        'module': s.module,
        'package': packages[s.module],
        'all_exports': <String>[],
        'all_literal': false,
        'compatibility_logic_free': false,
        'stable_bindings': <String>[],
        'blank': s.text.trim().isEmpty,
        'evidence_id': evidenceId,
      };
    }).toList();
  }
}

class _DartSiteVisitor extends RecursiveAstVisitor<void> {
  _DartSiteVisitor(this.collector, this.source, this.resolved);

  final DartCollector collector;
  final DartSource source;
  final ResolvedUnitResult resolved;
  String? scope;
  String? scopeId;
  Map<String, Object?>? binding;
  final Map<AstNode, Map<String, Object?>> resultBindings = HashMap.identity();

  void _withDefinition(AstNode node, Element? element, void Function() visit) {
    final next = collector._definitionOf(element);
    final record = next == null ? null : collector.symbolByQualified[next];
    final oldScope = scope;
    final oldId = scopeId;
    if (next != null && record != null) {
      scope = next;
      scopeId = record['id'] as String;
    }
    visit();
    scope = oldScope;
    scopeId = oldId;
  }

  (String, String)? get _sourceContext {
    final local = binding;
    if (local != null)
      return (local['qualified_name'] as String, local['id'] as String);
    return _functionContext;
  }

  (String, String)? get _functionContext {
    if (scope != null && scopeId != null) return (scope!, scopeId!);
    return null;
  }

  @override
  void visitFunctionDeclaration(FunctionDeclaration node) {
    _withDefinition(
      node,
      node.declaredFragment?.element,
      () => super.visitFunctionDeclaration(node),
    );
  }

  @override
  void visitMethodDeclaration(MethodDeclaration node) {
    _withDefinition(
      node,
      node.declaredFragment?.element,
      () => super.visitMethodDeclaration(node),
    );
  }

  @override
  void visitConstructorDeclaration(ConstructorDeclaration node) {
    _withDefinition(
      node,
      node.declaredFragment?.element,
      () => super.visitConstructorDeclaration(node),
    );
  }

  @override
  void visitVariableDeclaration(VariableDeclaration node) {
    final isLocal =
        node.parent is VariableDeclarationList &&
        ((node.parent as AstNode).parent is VariableDeclarationStatement ||
            (node.parent as AstNode).parent is ForPartsWithDeclarations);
    final currentScope = scope;
    final currentScopeId = scopeId;
    if (!isLocal || currentScope == null || currentScopeId == null) {
      super.visitVariableDeclaration(node);
      return;
    }
    final local = collector._localBinding(
      source,
      node,
      currentScope,
      currentScopeId,
    );
    final initializer = node.initializer;
    if (initializer != null &&
        (initializer is InstanceCreationExpression ||
            initializer is MethodInvocation ||
            initializer is FunctionExpressionInvocation)) {
      resultBindings[initializer] = local;
    }
    final oldBinding = binding;
    binding = local;
    super.visitVariableDeclaration(node);
    binding = oldBinding;
  }

  List<Map<String, Object?>> _bindingPayload(AstNode node) {
    final local = resultBindings[node];
    if (local == null) return const [];
    return [
      {
        'id': local['id'],
        'name': local['name'],
        'target_kind': 'name',
        'annotation': local['annotation'],
        'initializer': node.toSource(),
        'evidence_ids': local['evidence_ids'],
        'definition_contexts': <Object?>[],
      },
    ];
  }

  @override
  void visitMethodInvocation(MethodInvocation node) {
    final context = _functionContext;
    if (context != null) {
      collector._site(
        source,
        node,
        context.$1,
        context.$2,
        node.toSource(),
        node.methodName.element,
        call: true,
        resultBindings: _bindingPayload(node),
      );
    }
    super.visitMethodInvocation(node);
  }

  @override
  void visitFunctionExpressionInvocation(FunctionExpressionInvocation node) {
    final context = _functionContext;
    if (context != null) {
      collector._site(
        source,
        node,
        context.$1,
        context.$2,
        node.toSource(),
        node.function is SimpleIdentifier
            ? (node.function as SimpleIdentifier).element
            : null,
        call: true,
        resultBindings: _bindingPayload(node),
      );
    }
    super.visitFunctionExpressionInvocation(node);
  }

  @override
  void visitInstanceCreationExpression(InstanceCreationExpression node) {
    final context = _functionContext;
    if (context != null) {
      final classElement = node.constructorName.type.type?.element;
      final className = collector._definitionOf(classElement);
      final local =
          className != null &&
          collector.symbolByQualified.containsKey(className);
      final constructor = node.constructorName.element;
      final generative =
          local && constructor != null && constructor.isGenerative;
      final construction = <String, Object?>{
        'status': !local || constructor == null
            ? 'unresolved'
            : generative
            ? 'resolved'
            : 'partially_resolved',
        'targets': local && constructor != null ? [className] : <String>[],
        'candidates_truncated': false,
        'reason': !local
            ? 'constructor target is external, dynamic, or unresolved'
            : constructor == null
            ? 'Analyzer did not resolve a local constructor'
            : generative
            ? 'Analyzer resolved a local generative constructor'
            : 'factory construction does not prove a local instance target',
      };
      collector._site(
        source,
        node,
        context.$1,
        context.$2,
        node.toSource(),
        constructor == null ? null : classElement,
        call: true,
        resultBindings: _bindingPayload(node),
        construction: construction,
      );
    }
    super.visitInstanceCreationExpression(node);
  }

  @override
  void visitPropertyAccess(PropertyAccess node) {
    final context = _sourceContext;
    if (context != null) {
      collector._site(
        source,
        node,
        context.$1,
        context.$2,
        node.toSource(),
        node.propertyName.element,
        call: false,
      );
    }
    super.visitPropertyAccess(node);
  }

  @override
  void visitPrefixedIdentifier(PrefixedIdentifier node) {
    final context = _sourceContext;
    if (context != null) {
      final prefix = node.prefix.element;
      if (collector._definitionOf(prefix) != null) {
        collector._site(
          source,
          node.prefix,
          context.$1,
          context.$2,
          node.prefix.name,
          prefix,
          call: false,
        );
      }
      collector._site(
        source,
        node,
        context.$1,
        context.$2,
        node.toSource(),
        node.element,
        call: false,
      );
    }
    super.visitPrefixedIdentifier(node);
  }

  @override
  void visitNamedType(NamedType node) {
    final parent = node.parent;
    final isBase =
        parent is ExtendsClause ||
        parent is WithClause ||
        parent is ImplementsClause;
    final context = _sourceContext;
    if (!isBase && context != null) {
      collector._site(
        source,
        node,
        context.$1,
        context.$2,
        node.toSource(),
        node.element,
        call: false,
      );
    }
    super.visitNamedType(node);
  }

  @override
  void visitSimpleIdentifier(SimpleIdentifier node) {
    final parent = node.parent;
    if (parent is MethodInvocation && identical(parent.methodName, node) ||
        parent is NamedType ||
        parent is Declaration ||
        parent is VariableDeclaration && identical(parent.name, node) ||
        parent is PropertyAccess && identical(parent.propertyName, node) ||
        parent is PrefixedIdentifier) {
      super.visitSimpleIdentifier(node);
      return;
    }
    final context = _sourceContext;
    if (context != null && collector._definitionOf(node.element) != null) {
      collector._site(
        source,
        node,
        context.$1,
        context.$2,
        node.name,
        node.element,
        call: false,
      );
    }
    super.visitSimpleIdentifier(node);
  }
}
