import 'dart:convert';
import 'dart:io';

import 'package:analyzer/dart/analysis/analysis_context_collection.dart';
import 'package:analyzer/dart/analysis/results.dart';
import 'package:analyzer/dart/analysis/utilities.dart';
import 'package:analyzer/dart/ast/ast.dart';
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
        'calls': [],
        'references': [],
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
          _walk(libraryUnit, unit.unit);
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
        for (final uriNode in [
          namespaceDirective.uri,
          ...namespaceDirective.configurations.map(
            (configuration) => configuration.uri,
          ),
        ]) {
          final uri = uriNode.stringValue;
          if (uri == null) continue;
          final target = _importTarget(source, uri, package, sources);
          final module = moduleForSource[source.rel] ?? source.module;
          final combinators = switch (directive) {
            ImportDirective value => value.combinators,
            ExportDirective value => value.combinators,
            _ => const <Combinator>[],
          };
          final shown = combinators
              .whereType<ShowCombinator>()
              .expand(
                (combinator) => combinator.shownNames.map((name) => name.name),
              )
              .toList();
          final hidden = combinators
              .whereType<HideCombinator>()
              .expand(
                (combinator) => combinator.hiddenNames.map((name) => name.name),
              )
              .toSet();
          final symbols = shown.isEmpty
              ? <String?>[null]
              : shown
                    .where((name) => !hidden.contains(name))
                    .cast<String?>()
                    .toList();
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
                  'symbols_known': shown.isNotEmpty,
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
        _classBody(source, declaration.body, owner);
      } else if (declaration is EnumDeclaration) {
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
        _members(source, declaration.body.members, owner);
      } else if (declaration is MixinDeclaration) {
        final owner = _classifier(
          source,
          declaration,
          declaration.name.lexeme,
          'mixin',
        );
        _members(source, declaration.body.members, owner);
      } else if (declaration is FunctionDeclaration) {
        _function(
          source,
          declaration,
          declaration.name.lexeme,
          null,
          declaration.functionExpression.parameters,
          declaration.returnType?.toSource(),
        );
      } else if (declaration is GenericTypeAlias) {
        _simple(
          source,
          declaration,
          declaration.name.lexeme,
          'alias',
          declaration.type.toSource(),
        );
      } else if (declaration is FunctionTypeAlias) {
        _simple(
          source,
          declaration,
          declaration.name.lexeme,
          'alias',
          declaration.returnType?.toSource(),
        );
      } else if (declaration is TopLevelVariableDeclaration) {
        for (final variable in declaration.variables.variables) {
          _variable(
            source,
            variable,
            null,
            declaration.variables.type?.toSource(),
            declaration.variables.isConst,
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
    symbols.add(
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
    symbols.add(
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

  void _variable(
    DartSource source,
    VariableDeclaration node,
    String? parent,
    String? type,
    bool isConst,
  ) {
    final name = node.name.lexeme;
    _simple(
      source,
      node,
      name,
      isConst ? 'constant' : 'attribute',
      type,
      constant: isConst ? node.initializer?.toSource() : null,
      parent: parent,
    );
  }

  void _simple(
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
    symbols.add(
      _record(
        id,
        'source',
        kind,
        qualified + ' declaration',
        [qualified],
        [_cite(source, node)],
        {
          ..._meta(source, node, name, kind, parent, null),
          'annotation': annotation,
          'constant': constant,
        },
      ),
    );
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

  void _gap(String rel, int offset, String kind, String message) {
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
    final cited = source == null ? <String>[] : [_cite(source, null, true)];
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
    for (final item in symbols) {
      final data = item['data'] as Map<String, Object?>;
      final name = data['qualified_name'] as String;
      counts.update(name, (count) => count + 1, ifAbsent: () => 1);
    }
    for (final item in symbols) {
      final data = item['data'] as Map<String, Object?>;
      final name = data['qualified_name'] as String;
      if (counts[name] == 1) continue;
      final evidenceId = (item['evidence_ids'] as List).first as String;
      final file = evidence[evidenceId]!['file'] as String;
      _gap(file, 0, 'DuplicateDeclaration', 'duplicate declaration ' + name);
      data['source_binding_unique'] = false;
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
