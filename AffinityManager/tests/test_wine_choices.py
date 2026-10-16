"""Every Wine version the installer offers can actually be chosen.

The installer asks "Choose Wine Version" in three places, each with its own
list of labels and its own label -> version mapping. A Wine question is never
shown as those buttons, though: _show_question_dialog_safe swaps it for a
radio-button dialog with labels of its own, and whatever label that dialog
returns is what the mapping sees.

The two drifted apart once. 11.18 was added to the three lists and the 11.16
label renamed, but not in the radio dialog -- so the manager offered 11.16
only, and choosing it returned the old label, which no mapping recognised:
"Wine setup cancelled". This reads the installer's source and checks the
pieces against each other.
"""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import aol  # noqa: E402

try:
    inst = aol.module()
    TREE = ast.parse(Path(inst.__file__).read_text())
except aol.NotAvailable:
    inst, TREE = None, None

pytestmark = pytest.mark.skipif(TREE is None, reason="installer not available")


def _method(name):
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"installer has no {name}()")


def _radio_labels():
    """Labels the radio-button dialog can hand back."""
    labels = set()
    for node in ast.walk(_method("_show_wine_version_dialog_safe")):
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Attribute) and t.attr == "question_dialog_response"
                        for t in node.targets)
                and isinstance(node.value, ast.Constant)):
            labels.add(node.value.value)
    labels.discard("Cancel")
    return labels


def _wine_questions():
    """(options, mapped labels) for each "Choose Wine Version" question."""
    found = []
    for func in ast.walk(TREE):
        if not isinstance(func, ast.FunctionDef):
            continue
        for call in ast.walk(func):
            if not (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "show_question_dialog"
                    and call.args and isinstance(call.args[0], ast.Constant)
                    and "Wine Version" in str(call.args[0].value)):
                continue
            options = {e.value for e in call.args[2].elts if isinstance(e, ast.Constant)}
            mapped = {
                cmp.comparators[0].value
                for cmp in ast.walk(func)
                if isinstance(cmp, ast.Compare)
                and isinstance(cmp.left, ast.Name) and cmp.left.id == "wine_version"
                and isinstance(cmp.comparators[0], ast.Constant)
                and str(cmp.comparators[0].value).startswith("Wine ")
            }
            found.append((func.name, options, mapped))
    return found


def test_there_are_wine_questions_to_check():
    assert len(_wine_questions()) >= 3
    assert len(_radio_labels()) >= 2


def test_the_radio_dialog_offers_exactly_what_each_question_offers():
    radio = _radio_labels()
    for name, options, _ in _wine_questions():
        assert radio == options, (
            f"{name}(): the radio dialog offers {sorted(radio - options)} that the "
            f"question does not, and lacks {sorted(options - radio)}")


def test_every_offered_label_is_mapped_to_a_version():
    for name, options, mapped in _wine_questions():
        assert options <= mapped, f"{name}(): no mapping for {sorted(options - mapped)}"


def test_the_patched_builds_come_first_and_11_19_is_the_default():
    source = ast.get_source_segment(Path(inst.__file__).read_text(),
                                    _method("_show_wine_version_dialog_safe"))
    first_radio = source.index("QRadioButton(")
    assert source[first_radio:].startswith('QRadioButton("Wine 11.19')
    checked = [line for line in source.splitlines() if ".setChecked(True)" in line]
    assert checked == [line for line in checked if "wine_1119_radio" in line] and checked
