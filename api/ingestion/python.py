"""Non-executing Python analysis. Only unambiguous static references become edges."""

import ast
import hashlib
from pathlib import PurePosixPath

from api.graph.limits import MAX_EDGES, MAX_NODES
from api.ingestion.sources import SourceError

PARSER_VERSION = "python-ast-3"


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

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []
            self.class_scope = []
            self.shadowed = []

        def bindings(self, root):
            bound = set()

            class Bindings(ast.NodeVisitor):
                def visit_Name(self, child):
                    if isinstance(child.ctx, (ast.Store, ast.Del)):
                        bound.add(child.id)

                def visit_FunctionDef(self, child):
                    pass

                visit_AsyncFunctionDef = visit_FunctionDef
                visit_ClassDef = visit_FunctionDef
                visit_Lambda = visit_FunctionDef

                def visit_Import(self, child):
                    bound.update(a.asname or a.name.split(".")[0] for a in child.names)

                def visit_ImportFrom(self, child):
                    bound.update(a.asname or a.name for a in child.names)

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
            return bound

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
            self.shadowed.append(self.bindings(node))
            for stmt in node.body:
                self.visit(stmt)
            self.scope.pop()
            self.shadowed.pop()

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
            prefix = package[: len(package) - node.level + 1] if node.level else []
            mod = ".".join([*prefix, *([node.module] if node.module else [])])
            for alias in node.names:
                if alias.name != "*":
                    result["imports"][alias.asname or alias.name] = f"{mod}.{alias.name}".strip(".")

        def visit_Call(self, node):
            if len(result["calls"]) >= 10000:
                raise SourceError("Python file exceeds the analysis limit of 10,000 call sites")
            parts, value = [], node.func
            while isinstance(value, ast.Attribute):
                parts.insert(0, value.attr)
                value = value.value
            if isinstance(value, ast.Name):
                parts.insert(0, value.id)
                result["calls"].append(
                    {
                        "scope": ".".join(self.scope),
                        "target": "<shadowed>"
                        if any(parts[0] in bound for bound in self.shadowed)
                        and parts[0] not in {"self", "cls"}
                        else ".".join(parts),
                        "class": self.class_scope[-1] if self.class_scope else "",
                        "line": node.lineno,
                    }
                )
            else:
                result["calls"].append(
                    {
                        "scope": ".".join(self.scope),
                        "target": "<dynamic>",
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
                imported = parsed["imports"].get(first)
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
