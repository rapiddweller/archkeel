import { existsSync, readFileSync, realpathSync, statSync } from "node:fs";
import nodePath, { isAbsolute, relative, resolve } from "node:path";
import ts = require("typescript");
import { digest, type Request } from "./protocol.js";

export function withinRoot(scope: string, path: string, platform = nodePath): boolean {
  const rel = platform.relative(platform.resolve(scope), platform.resolve(path)).replaceAll("\\", "/");
  return !platform.isAbsolute(rel) && rel !== ".." && !rel.startsWith("../");
}

export function loadProject(request: Request) {
  const root = realpathSync(request.snapshot.root);
  const inputs = new Map<string, { path: string; digest: string; role: "selected" | "resolution" }>();
  const problems = new Set<string>();
  function pathOf(path: string): string | undefined {
    const rel = relative(root, resolve(path)).replaceAll("\\", "/");
    if (rel === ".." || rel.startsWith("../") || isAbsolute(rel)) return undefined;
    return rel;
  }
  function safe(path: string): boolean {
    if (pathOf(path) === undefined) return false;
    try {
      if (pathOf(realpathSync(path)) === undefined) { problems.add("Resolver symlink outside snapshot"); return false; }
      return true;
    } catch { return false; }
  }
  function readFile(path: string): string | undefined {
    if (pathOf(path) === undefined) {
      if (existsSync(path)) problems.add("Resolver input outside snapshot");
      return undefined;
    }
    if (!safe(path)) return undefined;
    try {
      const content = readFileSync(path);
      const rel = pathOf(path);
      if (rel !== undefined) inputs.set(rel, { path: rel, digest: digest(content), role: inputs.get(rel)?.role ?? "resolution" });
      return content.toString("utf8");
    } catch { problems.add(`Unreadable resolver input: ${pathOf(path)}`); return undefined; }
  }
  const host: ts.ParseConfigHost & ts.ModuleResolutionHost = {
    useCaseSensitiveFileNames: true, readFile,
    fileExists: path => {
      if (pathOf(path) === undefined && existsSync(path)) problems.add("Resolver input outside snapshot");
      return safe(path) && existsSync(path) && statSync(path).isFile();
    },
    directoryExists: path => safe(path) && statSync(path).isDirectory(),
    readDirectory: (path, extensions, excludes, includes, depth) => safe(path) ? ts.sys.readDirectory(path, extensions, excludes, includes, depth).filter(safe) : [],
    realpath: path => safe(path) ? realpathSync(path) : path,
  };
  const configPath = resolve(root, request.resolver.tsconfig);
  const config = ts.readConfigFile(configPath, readFile);
  const parsed = ts.parseJsonConfigFileContent(config.config ?? {}, host, resolve(configPath, ".."), undefined, configPath);
  for (const error of [...(config.error ? [config.error] : []), ...parsed.errors]) problems.add(ts.flattenDiagnosticMessageText(error.messageText, " "));
  const diagnosticHost: ts.CompilerHost = {
    ...ts.createCompilerHost(parsed.options), ...host, useCaseSensitiveFileNames: () => true,
    readDirectory: (...args) => [...host.readDirectory(...args)],
    getDirectories: path => safe(path) ? ts.sys.getDirectories(path).filter(safe) : [],
    getSourceFile: (path, languageVersion) => {
      const content = readFile(path);
      return content === undefined ? undefined : ts.createSourceFile(path, content, languageVersion, true);
    },
  };
  for (const diagnostic of ts.createProgram([], parsed.options, diagnosticHost).getOptionsDiagnostics()) {
    problems.add(`Compiler option ${diagnostic.code}: ${ts.flattenDiagnosticMessageText(diagnostic.messageText, " ")}`);
  }
  if (parsed.projectReferences?.length) problems.add("Project references require separately observed projects");
  const roots = request.scope.roots.map(path => resolve(root, path));
  function installed(path: string): boolean {
    return pathOf(host.realpath?.(path) ?? path)?.split("/").includes("node_modules") ?? false;
  }
  function selected(path: string): boolean {
    return !installed(path) && roots.some(scope => withinRoot(scope, path));
  }
  for (const scope of roots) {
    if (!safe(scope)) problems.add("Missing or unsafe source root");
    else if (installed(scope)) problems.add("Installed dependency cannot be a selected source root");
  }
  const files = [...new Set([
    ...parsed.fileNames.map(path => resolve(path)),
    ...roots.filter(path => host.fileExists(path)),
  ])].filter(selected).sort();
  if (!files.length) problems.add("No selected source files");
  return { root, host, options: parsed.options, inputs, problems, pathOf, selected, files, readFile };
}
