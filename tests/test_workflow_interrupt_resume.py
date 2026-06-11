import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / "app" / "core" / "browser" / "workflow.py"


def _contains_workflow_interrupt_requested(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Attribute)
            and child.attr == "workflow_interrupt_requested"
        ):
            return True
    return False


def _is_step_index_increment(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.AugAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "step_index"
        and isinstance(node.op, ast.Add)
        and isinstance(node.value, ast.Constant)
        and node.value.value == 1
    )


def test_workflow_interrupt_resume_advances_completed_step_before_continue():
    tree = ast.parse(WORKFLOW.read_text(encoding="utf-8"))
    matching_branches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and _contains_workflow_interrupt_requested(node.test)
    ]

    assert matching_branches, "workflow interrupt branch not found"

    for branch in matching_branches:
        saw_increment = False
        for statement in branch.body:
            if _is_step_index_increment(statement):
                saw_increment = True
            if isinstance(statement, ast.Continue):
                assert saw_increment
                return

    raise AssertionError("no workflow interrupt continue branch found")
