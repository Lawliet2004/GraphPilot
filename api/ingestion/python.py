"""Non-executing Python analysis. Only unambiguous static references become edges."""

import ast
import hashlib
from pathlib import PurePosixPath

from api.graph.limits import MAX_EDGES, MAX_NODES
from api.ingestion.sources import SourceError

PARSER_VERSION = "python-ast-4"


def stable_id(repo_id: str, branch: str, kind: str, key: str) -> str:
    return hashlib.sha256(f"{repo_id}\0{branch}\0{kind}\0{key}".encode()).hexdigest()[:32]


def module_name(path: str):
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    # Common src layout imports are rooted below src/.
    if parts and parts[0] == "src":
        parts.pop(0)
    return ".".join(parts)


def parse_file(path: str, source: str) -> dict:
    result = {
        "definitions": [],
        "imports": {},
        "calls": [],
        "errors": [],
        "module": module_name(path),
    }
    if not path.endswith(".py"):
        return result
    if "\r" in source.replace("\r\n", ""):
        # CPython counts a standalone CR as a newline while the served
        # source-range protocol numbers lines by LF only. Rather than emit
        # definitions/calls pinned to line numbers the reader cannot
        # reproduce, withhold semantic results; the file stays searchable.
        result["errors"].append(
            {
                "path": path,
                "line": None,
                "message": "Unsupported standalone-CR newlines; definitions and calls were not analyzed",
            }
        )
        return result
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError, RecursionError) as exc:
        result["errors"].append(
            {
                "path": path,
                "line": getattr(exc, "lineno", None),
                "message": "Python syntax could not be parsed",
            }
        )
        return result
    for count, _ in enumerate(ast.walk(tree), 1):
        if count > 50000:
            raise SourceError("Python file exceeds the analysis limit of 50,000 AST nodes")
    package = (
        result["module"].split(".")
        if path.endswith("/__init__.py")
        else result["module"].split(".")[:-1]
    )

    class ModuleBindings(ast.NodeVisitor):
        """Binding events in the module namespace only.

        def/class declarations, plain stores/deletes and import aliases are
        recorded separately with their line numbers so a call can be matched
        to the binding in effect at its site. Function/class/lambda bodies
        bind in their own scope and are not descended into.
        """

        def __init__(self):
            self.stores = {}
            self.defs = {}
            self.imports = {}
            self.sequence = 0

        def event(self, lineno):
            """(line, source-order) identity for deterministic binding order."""
            self.sequence += 1
            return (lineno, self.sequence)

        def visit_FunctionDef(self, node):
            self.defs.setdefault(node.name, []).append(self.event(node.lineno))

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Lambda(self, node):
            pass  # Lambda bodies and defaults bind in their own scope.

        def visit_comprehension(self, node):
            # Comprehension targets bind in the comprehension's own scope;
            # only iterables and conditions see module bindings.
            self.visit(node.iter)
            for condition in node.ifs:
                self.visit(condition)

        def visit_Import(self, node):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                qualified = alias.name if alias.asname else alias.name.split(".")[0]
                self.imports.setdefault(name, []).append(
                    (*self.event(node.lineno), qualified)
                )

        def visit_ImportFrom(self, node):
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname or alias.name
                qualified = None
                if node.level <= len(package):
                    prefix = (
                        package[: len(package) - node.level + 1] if node.level else []
                    )
                    mod = ".".join([*prefix, *([node.module] if node.module else [])])
                    qualified = f"{mod}.{alias.name}".strip(".")
                # An escaping relative import still binds a name at its line;
                # its target stays unknowable (qualified=None).
                self.imports.setdefault(name, []).append(
                    (*self.event(node.lineno), qualified)
                )

        def visit_Name(self, node):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                self.stores.setdefault(node.id, []).append(
                    self.event(node.lineno)
                )

    module_bindings = ModuleBindings()
    for statement in tree.body:
        module_bindings.visit(statement)
    module_stores = module_bindings.stores  # name -> [(line, seq)]
    module_defs = module_bindings.defs  # name -> [(line, seq)]
    module_imports = module_bindings.imports  # name -> [(line, seq, qualified|None)]

    def module_binding(name, line, deferred):
        """The module-level binding in effect for ``name`` at a call on ``line``.

        Module statements execute top to bottom, so a module-level call sees
        the last binding event at or before its line. Calls inside def/class
        bodies run after the module finished loading, so they see the last
        event overall. Returns "def", "store", "import" or None.
        """
        events = (
            [(*seen, "def") for seen in module_defs.get(name, ())]
            + [(*seen, "store") for seen in module_stores.get(name, ())]
            + [(seen[0], seen[1], "import") for seen in module_imports.get(name, ())]
        )
        live = [event for event in events if deferred or event[0] <= line]
        return max(live)[2] if live else None

    def live_import_target(name, line, deferred):
        """The qualified target of the import binding in effect, if resolvable."""
        candidates = [
            seen
            for seen in module_imports.get(name, ())
            if deferred or seen[0] <= line
        ]
        return max(candidates)[2] if candidates else None

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []
            self.class_scope = []
            self.shadowed = []
            self.assigned = []

        def bindings(self, root):
            bound = set()

            class Bindings(ast.NodeVisitor):
                def __init__(self):
                    self.assigned = set()

                def visit_Name(self, child):
                    if isinstance(child.ctx, (ast.Store, ast.Del)):
                        bound.add(child.id)
                        self.assigned.add(child.id)

                def visit_FunctionDef(self, child):
                    pass

                visit_AsyncFunctionDef = visit_FunctionDef
                visit_ClassDef = visit_FunctionDef
                visit_Lambda = visit_FunctionDef

                def visit_Import(self, child):
                    names = {a.asname or a.name.split(".")[0] for a in child.names}
                    bound.update(names)
                    self.assigned.update(names)

                def visit_ImportFrom(self, child):
                    names = {a.asname or a.name for a in child.names}
                    bound.update(names)
                    self.assigned.update(names)

            visitor = Bindings()
            for statement in root.body:
                visitor.visit(statement)
            if isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = root.args
                bound.update(a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs])
                if args.vararg:
                    bound.add(args.vararg.arg)
                if args.kwarg:
                    bound.add(args.kwarg.arg)
            return bound, visitor.assigned

        def definition(self, node, kind):
            if len(result["definitions"]) >= 2000:
                raise SourceError("Python file exceeds the analysis limit of 2,000 declarations")
            parent = ".".join(self.scope)
            qual = ".".join([*self.scope, node.name])
            result["definitions"].append(
                {
                    "key": qual,
                    "name": node.name,
                    "kind": kind,
                    "parent": parent,
                    "line": min([node.lineno, *[d.lineno for d in node.decorator_list]]),
                    "end_line": node.end_lineno,
                    "doc": (ast.get_docstring(node) or "")[:1000],
                }
            )
            self.scope.append(node.name)
            bound, assigned = self.bindings(node)
            self.shadowed.append(bound)
            self.assigned.append(assigned)
            for stmt in node.body:
                self.visit(stmt)
            self.scope.pop()
            self.shadowed.pop()
            self.assigned.pop()

        def visit_ClassDef(self, node):
            self.class_scope.append(".".join([*self.scope, node.name]))
            self.definition(node, "Class")
            self.class_scope.pop()

        def visit_FunctionDef(self, node):
            self.definition(node, "TestCase" if node.name.startswith("test_") else "Function")

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Import(self, node):
            if self.scope:
                return  # Local imports are conservative unresolved references in v1.
            for alias in node.names:
                result["imports"][alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )

        def visit_ImportFrom(self, node):
            if self.scope:
                return
            if node.level > len(package):
                # importlib.util.resolve_name raises ImportError here: the
                # relative import escapes the top-level package. Guessing a
                # same-named top-level module would produce false edges.
                result["errors"].append(
                    {
                        "path": path,
                        "line": node.lineno,
                        "message": "Relative import escapes the top-level package; imported names are unresolved",
                    }
                )
                return
            prefix = package[: len(package) - node.level + 1] if node.level else []
            mod = ".".join([*prefix, *([node.module] if node.module else [])])
            for alias in node.names:
                if alias.name != "*":
                    result["imports"][alias.asname or alias.name] = f"{mod}.{alias.name}".strip(".")

        def call_target(self, parts, line):
            """Resolve the dotted call name, or abstain when the binding is unsafe."""
            first = parts[0]
            if first in {"self", "cls"}:
                # Parameters bind self/cls without shadowing; an actual
                # statement rebinding makes the later attribute call's target
                # unknowable without tracking the assigned value.
                if any(first in bound for bound in self.assigned):
                    return "<shadowed>", False, None
            elif any(first in bound for bound in self.shadowed):
                return "<shadowed>", False, None
            else:
                deferred = bool(self.scope or self.class_scope)
                binding = module_binding(first, line, deferred)
                if binding == "store":
                    # A store/delete supersedes an earlier declaration: the
                    # earlier def is stale by this call site.
                    return "<shadowed>", False, None
                if binding == "import":
                    # An import supersedes an earlier declaration. Resolve
                    # through the import event in effect at this site, never
                    # the stale local symbol or a later overwritten alias.
                    qualified = live_import_target(first, line, deferred)
                    if qualified is None:
                        # An escaping relative or otherwise unresolvable
                        # import: the binding exists but its target is
                        # unknowable.
                        return "<shadowed>", False, None
                    return ".".join(parts), True, qualified
            return ".".join(parts), False, None

        def visit_Call(self, node):
            if len(result["calls"]) >= 10000:
                raise SourceError("Python file exceeds the analysis limit of 10,000 call sites")
            parts, value = [], node.func
            while isinstance(value, ast.Attribute):
                parts.insert(0, value.attr)
                value = value.value
            if isinstance(value, ast.Name):
                parts.insert(0, value.id)
                target, prefer_import, import_target = self.call_target(
                    parts, node.lineno
                )
                result["calls"].append(
                    {
                        "scope": ".".join(self.scope),
                        "target": target,
                        "prefer_import": prefer_import,
                        "import_target": import_target,
                        "class": self.class_scope[-1] if self.class_scope else "",
                        "line": node.lineno,
                    }
                )
            else:
                result["calls"].append(
                    {
                        "scope": ".".join(self.scope),
                        "target": "<dynamic>",
                        "prefer_import": False,
                        "import_target": None,
                        "class": "",
                        "line": node.lineno,
                    }
                )
            self.generic_visit(node)

    try:
        Visitor().visit(tree)
    except RecursionError:
        raise SourceError("Python AST exceeds the safe analysis depth") from None
    # Property setters, overloads and repeated declarations must not share IDs.
    # Ambiguous bindings get separate declaration nodes and no guessed call target.
    from collections import Counter

    counts = Counter(d["key"] for d in result["definitions"])
    occurrences = Counter()
    by_binding = {}
    for definition in result["definitions"]:
        original = definition["key"]
        definition["binding"] = original
        by_binding.setdefault(original, []).append(definition)
        if counts[original] > 1:
            occurrences[original] += 1
            definition["key"] = f"{original}@{occurrences[original]}"
    for definition in result["definitions"]:
        parents = [
            d
            for d in by_binding.get(definition["parent"], [])
            if d["binding"] == definition["parent"]
            and d["line"] <= definition["line"] <= d["end_line"]
        ]
        if parents:
            definition["parent"] = max(parents, key=lambda d: d["line"])["key"]
    for call in result["calls"]:
        sources = [
            d
            for d in by_binding.get(call["scope"], [])
            if d["binding"] == call["scope"] and d["line"] <= call["line"] <= d["end_line"]
        ]
        call["source_key"] = (
            max(sources, key=lambda d: d["line"])["key"] if sources else call["scope"]
        )
    for binding, count in counts.items():
        if count > 1:
            result["errors"].append(
                {
                    "path": path,
                    "line": None,
                    "message": f"Repeated declaration {binding}: call resolution is ambiguous",
                }
            )
    return result


def build_graph(
    repo_id: str, branch: str, commit: str, name: str, files: dict
) -> tuple[list, list, dict]:
    nodes, edges, symbols, modules = [], [], {}, {}
    module_warnings = []
    rid = stable_id(repo_id, branch, "Repository", repo_id)
    bid = stable_id(repo_id, branch, "Branch", branch)

    def node(kind, key, **props):
        if len(nodes) >= MAX_NODES:
            raise SourceError("Graph exceeds the indexing capacity of 50,000 nodes")
        nid = stable_id(repo_id, branch, kind, key)
        nodes.append(
            {
                "id": nid,
                "type": kind,
                "repository_id": repo_id,
                "branch": branch,
                "commit": commit,
                "indexing_version": PARSER_VERSION,
                "original_id": key,
                "provenance": "static",
                **props,
            }
        )
        return nid

    def edge(source, target, kind, **props):
        if len(edges) >= MAX_EDGES:
            raise SourceError("Graph exceeds the indexing capacity of 200,000 relationships")
        edges.append(
            {"source": source, "target": target, "type": kind, "provenance": "static", **props}
        )

    node("Repository", repo_id, name=name)
    node("Branch", branch, name=branch)
    edge(rid, bid, "RELATED_TO")
    for path, file in sorted(files.items()):
        fid = node(
            "File",
            path,
            name=PurePosixPath(path).name,
            path=path,
            line=1,
            end_line=file["lines"],
            content_hash=file["hash"],
            language="Python" if path.endswith(".py") else "Text",
        )
        if path.endswith(".py"):
            module = file["parsed"]["module"]
            if module in modules:
                modules[module] = None
                module_warnings.append(
                    {
                        "path": path,
                        "line": None,
                        "message": f"Ambiguous Python module {module}; imported calls are unresolved",
                    }
                )
            else:
                modules[module] = (path, fid)
        edge(bid, fid, "HAS_FILE")
        for d in file["parsed"]["definitions"]:
            key = f"{path}:{d['key']}"
            nid = node(
                d["kind"],
                key,
                name=d["name"],
                qualified_name=d["key"],
                path=path,
                line=d["line"],
                end_line=d["end_line"],
                doc=d["doc"],
            )
            symbols[(path, d["key"])] = nid
        for d in file["parsed"]["definitions"]:
            parent = symbols.get((path, d["parent"]), fid)
            edge(parent, symbols[(path, d["key"])], "DEFINES")

    def find_module(target, allow_exact=True):
        parts = target.split(".")
        for length in range(len(parts) if allow_exact else len(parts) - 1, 0, -1):
            name = ".".join(parts[:length])
            if name in modules:
                return (name, modules[name]) if modules[name] is not None else None
        return None

    test_ids = {n["id"] for n in nodes if n["type"] == "TestCase"}
    unresolved, resolved = 0, 0
    for path, file in sorted(files.items()):
        parsed = file["parsed"]
        fid = stable_id(repo_id, branch, "File", path)
        for target in parsed["imports"].values():
            candidate = find_module(target)
            if candidate:
                _, (_, target_id) = candidate
                edge(fid, target_id, "IMPORTS")
        for call in parsed["calls"]:
            target, scope = call["target"], call["scope"]
            dest = None
            if target.startswith(("self.", "cls.")) and call["class"]:
                dest = symbols.get((path, f"{call['class']}.{target.split('.', 1)[1]}"))
            if not dest:
                segments = scope.split(".") if scope else []
                # Lexical resolution only. No unrelated global name fallback.
                for length in range(len(segments), -1, -1):
                    if length == 0 and call.get("prefer_import"):
                        # The live module binding is an import; the earlier
                        # same-named module declaration is stale at this site.
                        continue
                    if (
                        ".".join(segments[:length]) == call["class"]
                        and scope != call["class"]
                        and call["class"]
                    ):
                        continue
                    dest = symbols.get((path, ".".join([*segments[:length], target])))
                    if dest:
                        break
            if not dest:
                first, *rest = target.split(".")
                imported = call.get("import_target") or parsed["imports"].get(first)
                if imported:
                    full = ".".join([imported, *rest])
                    candidate = find_module(full, allow_exact=False)
                    if candidate:
                        mod, (module_path, _) = candidate
                        dest = symbols.get((module_path, full[len(mod) + 1 :]))
            if dest:
                source = symbols.get((path, call.get("source_key", scope)), fid)
                edge(source, dest, "CALLS", line=call["line"])
                if source in test_ids:
                    edge(source, dest, "TESTS", line=call["line"])
                resolved += 1
            else:
                unresolved += 1
    # Stable edge identity includes call-site line; duplicate imports collapse.
    unique = {(e["source"], e["target"], e["type"], e.get("line", 0)): e for e in edges}
    errors = [
        error for file in files.values() for error in file["parsed"]["errors"]
    ] + module_warnings
    return (
        nodes,
        list(unique.values()),
        {
            "resolved_calls": resolved,
            "unresolved_calls": unresolved,
            "parse_errors": errors,
            "files": len(files),
            "functions": sum(n["type"] in {"Function", "TestCase"} for n in nodes),
            "classes": sum(n["type"] == "Class" for n in nodes),
            "nodes": len(nodes),
            "edges": len(unique),
        },
    )
