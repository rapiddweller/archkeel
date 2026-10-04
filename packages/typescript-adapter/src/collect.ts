import { readFileSync } from "node:fs";
import { isBuiltin } from "node:module";
import { dirname, isAbsolute, resolve } from "node:path";
import ts from "typescript";
import { loadProject } from "./project.js";
import { digest, id, moduleIdentity, nodeRequirement, type Evidence, type Request, type SourceRecord, type Target } from "./protocol.js";

const sourceExtensions = /\.(?:[cm]?ts|tsx|[cm]?js|jsx)$/;
const declarationExtension = /\.d\.(?:[cm]?ts)$/;
const nodeModuleExports = new Set(["Module", "default"]);
export function collect(request: Request) {
  if (ts.version !== "5.9.3") throw Error("TypeScript compiler version must be 5.9.3");
  const manifest = readFileSync(new URL("../package.json", import.meta.url), "utf8");
  const metadata: unknown = JSON.parse(manifest);
  if (metadata === null || typeof metadata !== "object" || !("engines" in metadata)
    || metadata.engines === null || typeof metadata.engines !== "object" || !("node" in metadata.engines)) throw Error("Missing package Node engines policy");
  const required = nodeRequirement(metadata.engines.node);
  const project = loadProject(request);
  const evidence: Evidence[] = [];
  const imports: SourceRecord[] = [];
  const gaps: SourceRecord[] = [];
  const targets: Target[] = [];
  const files = [];
  const queue = new Set(project.files);
  const parsed = new Set<string>();
  let filesRead = 0;
  function record(kind: string, title: string, subjects: string[], evidenceIds: string[], data: { [key: string]: unknown }, identity: string, unknown = false): SourceRecord {
    return { id: identity, evidence_class: unknown ? "UNKNOWN" : "FACT", area: "source", kind, title, subjects, evidence_ids: evidenceIds, rule_ids: [], fact_ids: [], provenance: [], data };
  }
  function gap(reason: string, evidenceIds: string[] = [], module = ""): void {
    const identity = id("unknown", reason, ...evidenceIds, module);
    if (!gaps.some(item => item.id === identity)) gaps.push(record("collection_gap", reason, module ? [module] : [], evidenceIds, { reason, module }, identity, true));
  }
  function observe(path: string): string | undefined {
    const content = project.readFile(path);
    if (content !== undefined && project.selected(path) && sourceExtensions.test(path)) queue.add(path);
    else if (content !== undefined) gap(`Local dependency outside selected source scope: ${project.pathOf(path)}`);
    return content;
  }
  function targetFor(specifier: string, source: ts.SourceFile, importId: string, typeOnly: boolean, mode: ts.ResolutionMode, directCommonJS: boolean): Target {
    if (!typeOnly && specifier.startsWith("node:") && isBuiltin(specifier)) return { kind: "builtin", import_id: importId, name: specifier };
    const resolutionInputs = new Set<string>();
    const resolution = ts.resolveModuleName(specifier, source.fileName, project.options, {
      ...project.host, readFile: path => {
        resolutionInputs.add(resolve(path));
        return project.readFile(path);
      },
    }, undefined, undefined, mode).resolvedModule;
    function unresolved(reason: string): Target {
      gap(reason, [], moduleIdentity(request.scope.namespace, project.pathOf(source.fileName) ?? "unknown"));
      return { kind: "unresolved", import_id: importId, specifier, reason };
    }
    if (!resolution && isBuiltin(specifier)) return { kind: "builtin", import_id: importId, name: specifier };
    if (!resolution) return unresolved(`Unresolved module: ${specifier}`);
    const resolvedPath = resolve(resolution.resolvedFileName);
    const path = project.host.realpath?.(resolvedPath) ?? resolvedPath;
    if (project.options.preserveSymlinks && path !== resolvedPath) return unresolved(`preserveSymlinks lookup context is not observed: ${specifier}`);
    const rel = project.pathOf(path);
    if (rel === undefined || project.readFile(path) === undefined) return unresolved(`Unavailable local target: ${specifier}`);
    if (rel.split("/").includes("node_modules") || (!project.selected(path) && resolution.isExternalLibraryImport)) {
      if (specifier.startsWith("#")) return unresolved(`External package alias identity is not observed: ${specifier}`);
      const bare = !specifier.startsWith(".") && !isAbsolute(specifier);
      const packageName = bare
        ? (specifier.startsWith("@") ? specifier.split("/").slice(0, 2).join("/") : specifier.split("/")[0])
        : resolution.packageId?.name;
      if (!packageName) return unresolved(`Unidentified external package: ${specifier}`);
      return { kind: "external", import_id: importId, package: packageName };
    }
    const relativeSpecifier = specifier.startsWith("./") || specifier.startsWith("../");
    const lookup = resolve(dirname(source.fileName), specifier);
    const directoryPackage = relativeSpecifier && project.host.directoryExists?.(lookup)
      && resolutionInputs.has(resolve(lookup, "package.json"));
    const declaration = declarationExtension.test(path) ? rel : null;
    let runtime = declaration ? null : rel;
    const explicitRuntime = relativeSpecifier && /\.(?:cjs|mjs|js)$/.test(specifier);
    const commonJSLookup = relativeSpecifier && directCommonJS && !explicitRuntime;
    if (!typeOnly) {
      // Compiler substitution does not prove the file Node loads.
      const runtimePath = explicitRuntime ? lookup : undefined;
      if (runtimePath && project.host.fileExists(runtimePath)) {
        const realRuntime = project.host.realpath?.(runtimePath) ?? runtimePath;
        if (project.options.preserveSymlinks && realRuntime !== runtimePath) return unresolved(`preserveSymlinks lookup context is not observed: ${specifier}`);
        if (observe(realRuntime) !== undefined) runtime = project.pathOf(realRuntime) ?? null;
      } else if (declaration || (runtimePath && directCommonJS)) {
        runtime = null;
        gap(declaration ? `Runtime implementation unavailable for declaration: ${rel}` : `CommonJS runtime file is unavailable: ${specifier}`);
      }
    }
    observe(path);
    if (!typeOnly && (!relativeSpecifier || directoryPackage || commonJSLookup)) {
      runtime = null;
      gap(commonJSLookup ? `CommonJS runtime target is not proven: ${specifier}`
        : directoryPackage ? `Local directory runtime metadata is not proven: ${specifier}` : `Local alias runtime conditions are not proven: ${specifier}`, [], moduleIdentity(request.scope.namespace, project.pathOf(source.fileName) ?? "unknown"));
    }
    const file = !typeOnly && runtime ? runtime : rel;
    return { kind: "local", import_id: importId, module: moduleIdentity(request.scope.namespace, file), file, runtime_file: runtime, declaration_file: declaration };
  }
  const options: ts.CompilerOptions = { ...project.options, noLib: true, noResolve: true, types: [], allowJs: true, checkJs: false };
  const host = ts.createCompilerHost(options);
  host.readFile = project.readFile;
  host.fileExists = project.host.fileExists;
  host.getSourceFile = (fileName, languageVersion) => {
    const text = project.readFile(fileName);
    return text === undefined ? undefined : ts.createSourceFile(fileName, text, languageVersion, true);
  };
  let program = ts.createProgram([...queue], options, host);
  for (const absolute of queue) {
    const relativePath = project.pathOf(absolute);
    if (relativePath === undefined) { gap("Selected path outside snapshot"); continue; }
    const rel = relativePath;
    const content = project.readFile(absolute);
    if (content === undefined) { gap(`Unreadable selected source: ${rel}`); continue; }
    filesRead++;
    const input = project.inputs.get(rel);
    if (input) input.role = "selected";
    if (!program.getSourceFile(absolute)) program = ts.createProgram([...queue], options, host);
    const foundSource = program.getSourceFile(absolute);
    if (!foundSource) { gap(`Cannot parse selected source: ${rel}`); continue; }
    const source: ts.SourceFile = foundSource;
    parsed.add(rel);
    const module = moduleIdentity(request.scope.namespace, rel);
    const pkg = module.split(".").slice(0, -1).join(".");
    function location(node: ts.Node): string {
      const start = source.getLineAndCharacterOfPosition(node.getStart(source));
      const end = source.getLineAndCharacterOfPosition(node.getEnd());
      const identity = id("evidence", rel, node.getStart(source), node.getEnd());
      if (!evidence.some(item => item.id === identity)) evidence.push({ id: identity, file: rel, line: start.line + 1, end_line: end.line + 1, column: start.character + 1, excerpt: node.getText(source).slice(0, 400) });
      return identity;
    }
    const fileEvidence = location(source);
    files.push({ id: id("file", module), rel_path: rel, module, package: pkg, all_exports: [], all_literal: false, compatibility_logic_free: false, stable_bindings: [], blank: !content.trim(), evidence_id: fileEvidence });
    for (const diagnostic of program.getSyntacticDiagnostics(source)) gap(`Syntax error in ${rel}: ${ts.flattenDiagnosticMessageText(diagnostic.messageText, " ")}`, [fileEvidence], module);
    const implied = ts.getImpliedNodeFormatForFile(absolute, undefined, project.host, project.options);
    const commonJS = absolute.endsWith(".cjs") || absolute.endsWith(".cts") || project.options.module === ts.ModuleKind.CommonJS || (implied === ts.ModuleKind.CommonJS && (project.options.module === ts.ModuleKind.NodeNext || project.options.module === ts.ModuleKind.Node16));
    function add(node: ts.Node, expression: ts.Node | undefined, typeOnly: boolean, form: string, resolutionMode?: ts.ResolutionMode): void {
      const evidenceId = location(node);
      if (!expression || !ts.isStringLiteralLike(expression)) { gap(`Computed ${form} cannot be resolved`, [evidenceId], module); return; }
      const specifier = expression.text;
      const importId = id("import", module, node.getStart(source), form);
      const target = targetFor(specifier, source, importId, typeOnly, resolutionMode ?? program.getModeForUsageLocation(source, expression), resolutionMode === ts.ModuleKind.CommonJS);
      targets.push(target);
      const targetModule = target.kind === "local" ? target.module : target.kind === "builtin" ? target.name : target.kind === "external" ? target.package : specifier;
      imports.push(record(form, `${module} imports ${specifier}`, [module, targetModule], [evidenceId], {
        source_module: module, source_package: pkg, target_module: targetModule,
        target_package: target.kind === "local" ? target.module.split(".").slice(0, -1).join(".") : targetModule,
        symbol: null, binding: null, symbols_known: false, specifier, type_only: typeOnly,
        relative_level: 0, under_type_checking: typeOnly,
        reexport: form === "reexport", module_level_import: node.parent === source,
      }, importId));
    }
    for (const reference of [...source.referencedFiles, ...source.typeReferenceDirectives, ...source.libReferenceDirectives]) gap(`Unobserved triple-slash reference: ${reference.fileName}`, [fileEvidence], module);
    const checker = program.getTypeChecker();
    function nodeModuleImport(declaration: ts.Node): boolean {
      let parent: ts.Node | undefined = declaration;
      while (parent && !ts.isImportDeclaration(parent)) parent = parent.parent;
      return parent !== undefined && ts.isImportDeclaration(parent) && ts.isStringLiteralLike(parent.moduleSpecifier)
        && ["module", "node:module"].includes(parent.moduleSpecifier.text);
    }
    function nodeModuleReference(node: ts.Node | undefined, seen = new Set<ts.Node>()): boolean {
      if (!node || seen.has(node)) return false;
      seen.add(node);
      if (ts.isParenthesizedExpression(node) || ts.isAwaitExpression(node) || ts.isAsExpression(node)
        || ts.isTypeAssertionExpression(node) || ts.isNonNullExpression(node) || ts.isSatisfiesExpression(node)) return nodeModuleReference(node.expression, seen);
      if ((ts.isPropertyAccessExpression(node) && nodeModuleExports.has(node.name.text))
        || (ts.isElementAccessExpression(node) && ts.isStringLiteralLike(node.argumentExpression) && nodeModuleExports.has(node.argumentExpression.text))) return nodeModuleReference(node.expression, seen);
      if (ts.isCallExpression(node)) {
        const argument = node.arguments[0];
        return (node.expression.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(node.expression) && node.expression.text === "require"))
          && argument !== undefined && ts.isStringLiteralLike(argument) && ["module", "node:module"].includes(argument.text);
      }
      if (!ts.isIdentifier(node)) return false;
      const symbol = ts.isShorthandPropertyAssignment(node.parent)
        ? checker.getShorthandAssignmentValueSymbol(node.parent) : checker.getSymbolAtLocation(node);
      if (commonJS && node.text === "module" && !symbol?.declarations?.length) return true;
      return symbol?.declarations?.some(declaration => {
        if (ts.isNamespaceImport(declaration) || ts.isImportClause(declaration)) return nodeModuleImport(declaration);
        if (ts.isImportSpecifier(declaration) && nodeModuleExports.has((declaration.propertyName ?? declaration.name).text)) return nodeModuleImport(declaration);
        if (ts.isBindingElement(declaration) && ts.isObjectBindingPattern(declaration.parent) && ts.isVariableDeclaration(declaration.parent.parent)) {
          let name: ts.Node = declaration.propertyName ?? declaration.name;
          while (ts.isComputedPropertyName(name) || ts.isParenthesizedExpression(name)) name = name.expression;
          return (ts.isIdentifier(name) || ts.isStringLiteralLike(name)) && nodeModuleExports.has(name.text)
            && nodeModuleReference(declaration.parent.parent.initializer, seen);
        }
        if (ts.isVariableDeclaration(declaration)) return nodeModuleReference(declaration.initializer, seen);
        if (ts.isImportEqualsDeclaration(declaration) && ts.isExternalModuleReference(declaration.moduleReference)) {
          const expression = declaration.moduleReference.expression;
          return expression !== undefined && ts.isStringLiteralLike(expression) && ["module", "node:module"].includes(expression.text);
        }
        return false;
      }) ?? false;
    }
    function isValueUse(node: ts.Node): boolean {
      for (let parent = node.parent; parent; parent = parent.parent) if (ts.isTypeNode(parent)) return false;
      return true;
    }
    function createRequireReference(node: ts.Node): boolean {
      if (ts.isBindingElement(node) && ts.isObjectBindingPattern(node.parent) && ts.isVariableDeclaration(node.parent.parent)) {
        let name: ts.Node = node.propertyName ?? node.name;
        while (ts.isComputedPropertyName(name) || ts.isParenthesizedExpression(name)) name = name.expression;
        if (((ts.isIdentifier(name) || ts.isStringLiteralLike(name)) && name.text === "createRequire")
          || (node.propertyName && ts.isComputedPropertyName(node.propertyName) && !ts.isStringLiteralLike(name))) return nodeModuleReference(node.parent.parent.initializer);
      }
      if (ts.isIdentifier(node) && !ts.isImportSpecifier(node.parent)) {
        return checker.getSymbolAtLocation(node)?.declarations?.some(declaration =>
          ts.isImportSpecifier(declaration) && (declaration.propertyName ?? declaration.name).text === "createRequire" && nodeModuleImport(declaration)) ?? false;
      }
      if ((ts.isPropertyAccessExpression(node) && node.name.text === "createRequire")
        || (ts.isElementAccessExpression(node) && (!ts.isStringLiteralLike(node.argumentExpression) || node.argumentExpression.text === "createRequire"))) {
        return nodeModuleReference(node.expression);
      }
      return false;
    }
    const visited = new Set<ts.Node>();
    function visit(node: ts.Node): void {
      if (visited.has(node)) return;
      visited.add(node);
      if (createRequireReference(node) && isValueUse(node)) gap("Node createRequire loader is not observed", [location(node)], module);
      if (((ts.isPropertyAccessExpression(node) && node.name.text === "then")
        || (ts.isElementAccessExpression(node) && ts.isStringLiteralLike(node.argumentExpression) && node.argumentExpression.text === "then"))
        && nodeModuleReference(node.expression) && isValueUse(node)) gap("Node module callback namespace is not observed", [location(node)], module);
      if (ts.isExpression(node) && nodeModuleReference(node) && isValueUse(node)) {
        const parent = node.parent;
        if (!nodeModuleReference(parent)
          && !((ts.isPropertyAccessExpression(parent) || ts.isElementAccessExpression(parent)) && parent.expression === node)
          && !ts.isVariableDeclaration(parent) && !(ts.isBindingElement(parent) && parent.name === node) && !ts.isNamespaceImport(parent) && !ts.isImportClause(parent) && !ts.isImportSpecifier(parent) && !ts.isImportEqualsDeclaration(parent)
          && !ts.isTypeQueryNode(parent) && !ts.isQualifiedName(parent) && !ts.isExpressionStatement(parent) && !ts.isTypeOfExpression(parent)) {
          gap("Node module namespace escape is not observed", [location(node)], module);
        }
      }
      if (ts.isBindingElement(node) && ts.isObjectBindingPattern(node.parent)) {
        if (node.dotDotDotToken && ts.isVariableDeclaration(node.parent.parent)
          && nodeModuleReference(node.parent.parent.initializer) && isValueUse(node)) gap("Node module rest binding is not observed", [location(node)], module);
        let name: ts.Node = node.propertyName ?? node.name;
        while (ts.isComputedPropertyName(name) || ts.isParenthesizedExpression(name)) name = name.expression;
        if ((ts.isIdentifier(name) || ts.isStringLiteralLike(name)) && nodeModuleExports.has(name.text)
          && !ts.isIdentifier(node.name) && ts.isVariableDeclaration(node.parent.parent)
          && nodeModuleReference(node.parent.parent.initializer) && isValueUse(node)) gap("Node module complex binding is not observed", [location(node)], module);
        if (((ts.isIdentifier(name) || ts.isStringLiteralLike(name)) && name.text === "require")
          || (node.propertyName && ts.isComputedPropertyName(node.propertyName) && !ts.isStringLiteralLike(name)
            && ts.isVariableDeclaration(node.parent.parent) && nodeModuleReference(node.parent.parent.initializer))) gap("Indirect require binding is not resolved", [location(node)], module);
      }
      if ((ts.isPropertyAccessExpression(node) && node.name.text === "require")
        || (ts.isElementAccessExpression(node) && ((ts.isStringLiteralLike(node.argumentExpression) && node.argumentExpression.text === "require")
          || (!ts.isStringLiteralLike(node.argumentExpression) && ts.isIdentifier(node.expression) && node.expression.text === "module")))) {
        gap(ts.isElementAccessExpression(node) ? "Computed require member use" : "Unproven require member use", [location(node)], module);
      }
      if (ts.isImportDeclaration(node)) add(node, node.moduleSpecifier, (node.importClause?.isTypeOnly || (node.importClause?.namedBindings && ts.isNamedImports(node.importClause.namedBindings) && node.importClause.namedBindings.elements.length > 0 && !node.importClause.name && node.importClause.namedBindings.elements.every(item => item.isTypeOnly))) ?? false, "import");
      else if (ts.isExportDeclaration(node) && node.moduleSpecifier) add(node, node.moduleSpecifier, node.isTypeOnly || (node.exportClause !== undefined && ts.isNamedExports(node.exportClause) && node.exportClause.elements.length > 0 && node.exportClause.elements.every(item => item.isTypeOnly)), "reexport");
      else if (ts.isJSDocImportTag(node)) add(node, node.moduleSpecifier, true, "jsdoc_import");
      else if (ts.isImportTypeNode(node)) add(node, ts.isLiteralTypeNode(node.argument) ? node.argument.literal : node.argument, true, "import_type");
      else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) add(node, node.moduleReference.expression, node.isTypeOnly, "import_equals", ts.ModuleKind.CommonJS);
      else if (ts.isCallExpression(node)) {
        if (node.expression.kind === ts.SyntaxKind.ImportKeyword) add(node, node.arguments[0], false, "dynamic_import", ts.ModuleKind.ESNext);
        else if (ts.isIdentifier(node.expression) && node.expression.text === "require") {
          if (!commonJS || checker.getSymbolAtLocation(node.expression)?.declarations?.length) gap("Unproven or shadowed require call", [location(node)], module);
          else add(node, node.arguments[0], false, "require", ts.ModuleKind.CommonJS);
        }
      }
      if (ts.isIdentifier(node) && node.text === "require" && !(ts.isCallExpression(node.parent) && node.parent.expression === node) && !(ts.isPropertyAccessExpression(node.parent) && node.parent.name === node)) gap("Indirect require use is not resolved", [location(node)], module);
      ts.forEachChild(node, visit);
      for (const documentation of ts.getJSDocCommentsAndTags(node)) visit(documentation);
    }
    visit(source);
  }
  const scope = request.scope.roots.map(root => project.host.directoryExists?.(resolve(project.root, root)) ? `${root}/**` : root);
  for (const problem of project.problems) gap(problem);
  const inputs = [...project.inputs.values()].sort((a, b) => a.path.localeCompare(b.path, "en"));
  const artifact = [...["entry.js", "project.js", "collect.js", "protocol.js"].map(name => readFileSync(new URL(name, import.meta.url), "utf8")), manifest].join("\0");
  return { protocol_version: "1.0.0", facts: {
    profile: "archkeel-typescript-imports", adapter: { name: "@archkeel/typescript-adapter", version: "1.0.0+typescript.5.9.3", code_digest: digest(artifact) },
    runtime: { name: "node", version: process.versions.node, required },
    source: { git_head: request.snapshot.git_head, dirty: request.snapshot.dirty, source_digest: digest(JSON.stringify(inputs)), scope },
    capabilities: { sections: ["imports", "unknowns"], resolution_features: ["typescript-compiler-5.9.3", "literal-imports", "local-runtime-closure"], constructs: [] },
    inputs, files: files.sort((a, b) => a.rel_path.localeCompare(b.rel_path, "en")), imports: targets,
    sections: [{ name: "imports", records: imports }, { name: "unknowns", records: gaps }],
    coverage: { selected_files: [...queue].map(path => project.pathOf(path)).sort(), files_read: filesRead, files_parsed: parsed.size, full_scope: gaps.length === 0, gaps },
    evidence, uncertain_reexports: [], type_shapes: [], state: { classes: [], functions: [] }, candidate_evidence: [],
  } };
}
