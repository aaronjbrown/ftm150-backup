"""The engine is the bytes-only domain model: from outside engine/ it imports only units."""
import ast
import pathlib

ENGINE = pathlib.Path(__file__).resolve().parent.parent / "ftm150" / "engine"


def _imports(path: pathlib.Path) -> list[str]:
    """Absolute and parent-relative imports of a module (same-package ones skipped)."""
    out = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level != 1:
            out.append("." * node.level + (node.module or ""))
    return out


def test_engine_imports_only_units_and_stdlib():
    allowed_parent = {"..units"}
    stdlib_only = {"collections", "dataclasses", "enum", "typing"}
    for path in sorted(ENGINE.glob("*.py")):
        for name in _imports(path):
            if name.startswith("."):
                assert name in allowed_parent, f"{path.name} imports {name}"
            else:
                assert name.split(".")[0] in stdlib_only, f"{path.name} imports {name}"
