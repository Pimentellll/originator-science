"""No hidden-truth access: static scan of belief and policy sources."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "mirage"
FILES = sorted((SRC / "belief").glob("*.py")) + [
    p for name in ("base", "random", "fixed", "greedy_eig") if (p := SRC / "policies" / f"{name}.py").exists()
]
FORBIDDEN_NAMES = {
    "_ground_truth", "_simulator_truth", "_privileged_state", "hidden_truth", "true_failure",
    "privileged", "evaluator", "ground_truth",
}
ALLOWED_IMPORT_ROOTS = {
    "__future__", "abc", "copy", "dataclasses", "typing", "math", "functools", "itertools",
    "collections", "time", "numpy", "pydantic", "mirage",
}
ALLOWED_MIRAGE = ("mirage.core", "mirage.belief", "mirage.policies")
# The single place allowed to touch the environment package: the adapter that
# delegates to the environment's PUBLIC predictive model (no truth, no env object).
ADAPTER_EXCEPTIONS = {"binder.py": {"mirage.environments.binder.predictive"}}


def _tree(path):
    return ast.parse(path.read_text(), filename=str(path))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_private_names(path):
    for node in ast.walk(_tree(path)):
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.append(node.name)
        for n in names:
            assert n.lower() not in FORBIDDEN_NAMES and "truth" not in n.lower(), f"{path.name}: {n}"


def test_greedy_eig_is_scanned():
    assert "greedy_eig.py" in {p.name for p in FILES}


def test_only_the_adapter_may_import_the_environment_package():
    offenders = [p.name for p in FILES for n in ast.walk(_tree(p))
                 if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("mirage.environments")]
    assert set(offenders) <= set(ADAPTER_EXCEPTIONS)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_imports_restricted_to_public_surface(path):
    for node in ast.walk(_tree(path)):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            mods = [node.module or ""]
        for m in mods:
            assert m.split(".")[0] in ALLOWED_IMPORT_ROOTS, f"{path.name} imports {m}"
            if m.startswith("mirage") and m not in ADAPTER_EXCEPTIONS.get(path.name, ()):
                assert m.startswith(ALLOWED_MIRAGE), f"{path.name} imports {m}"


def test_policy_signature_has_no_environment_argument():
    import inspect
    from mirage.policies import ScientificPolicy
    assert list(inspect.signature(ScientificPolicy.choose_action).parameters) == [
        "self", "state", "belief", "available_actions"]
