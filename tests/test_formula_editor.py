"""公式编辑控件的解析、预览与插入行为。"""

from PySide6.QtWidgets import QLabel, QPushButton

from ai_physics_tracker.domain.expression import parse_expression
from ai_physics_tracker.gui.formula_editor import FormulaEditor


def _editor(qtbot) -> FormulaEditor:
    editor = FormulaEditor()
    qtbot.addWidget(editor)
    editor.show()
    return editor


def test_initial_preview_uses_domain_expression_and_target_is_read_only(qtbot) -> None:
    editor = _editor(qtbot)

    assert isinstance(editor.quantityLabel, QLabel)
    assert editor.quantityLabel.text() == "y(t)"
    assert editor.expression() == parse_expression(editor.text())
    assert editor.previewLabel.pixmap() is not None
    assert not editor.previewLabel.pixmap().isNull()

    editor.setQuantityLabel("theta(t)")
    assert editor.quantityLabel.text() == "theta(t)"


def test_set_text_emits_raw_formula_and_updates_preview(qtbot) -> None:
    editor = _editor(qtbot)

    with qtbot.waitSignal(editor.formulaChanged, timeout=1000) as signal:
        editor.setText("A*cos(omega*t)")

    assert signal.args == ["A*cos(omega*t)"]
    assert editor.text() == "A*cos(omega*t)"
    assert editor.expression() is not None


def test_negative_power_and_fraction_render_distinct_previews(qtbot) -> None:
    editor = _editor(qtbot)

    editor.setText("-t^2")
    power = editor.expression()
    power_size = editor.previewLabel.pixmap().size()
    assert power is not None
    assert power.latex == parse_expression("-t^2").latex

    editor.setText("1/(t+1)")
    fraction = editor.expression()
    fraction_size = editor.previewLabel.pixmap().size()
    assert fraction is not None
    assert fraction.latex == parse_expression("1/(t+1)").latex
    assert power.latex != fraction.latex
    assert power_size != fraction_size


def test_mathtext_math_mode_renders_supported_expression_grammar(qtbot, monkeypatch) -> None:
    editor = _editor(qtbot)
    real_parse = editor._mathTextParser.parse
    parsed_sources: list[str] = []

    def record_mathtext_source(source: str, *args, **kwargs):
        parsed_sources.append(source)
        return real_parse(source, *args, **kwargs)

    monkeypatch.setattr(editor._mathTextParser, "parse", record_mathtext_source)
    formulas = (
        "alpha_beta*t + 1e-300",
        "1e-300*t + 1e300",
        "sin(" * 24 + "t" + ")" * 24,
    )

    for formula in formulas:
        editor.setText(formula)
        expression = editor.expression()

        assert expression is not None
        assert parsed_sources[-1] == f"${expression.latex}$"
        assert editor.previewLabel.pixmap() is not None
        assert not editor.previewLabel.pixmap().isNull()
        assert editor.errorLabel.text() == ""


def test_mathtext_render_failure_clears_preview_and_reports_error(qtbot, monkeypatch) -> None:
    editor = _editor(qtbot)

    def fail_render(*args, **kwargs):
        raise ValueError("unsupported MathText command")

    monkeypatch.setattr(editor._mathTextParser, "parse", fail_render)

    editor.setText("a*t + c")

    assert editor.expression() == parse_expression("a*t + c")
    assert editor.previewLabel.pixmap().isNull()
    assert "MathText preview failed" in editor.errorLabel.text()
    assert "unsupported MathText command" in editor.errorLabel.text()


def test_invalid_formula_clears_preview_and_reports_original_position(qtbot) -> None:
    editor = _editor(qtbot)

    editor.setText("t^2 + @")

    assert editor.expression() is None
    assert editor.previewLabel.pixmap().isNull()
    assert "character 7" in editor.errorLabel.text()
    assert "source index 6, zero-based" in editor.errorLabel.text()


def test_insertion_and_examples_remain_editable(qtbot) -> None:
    editor = _editor(qtbot)
    editor.setText("")
    editor.formulaEdit.setFocus()

    for object_name in (
        "insert_sin", "insert_cos", "insert_exp", "insert_log", "insert_sqrt",
        "insert_abs", "insert_pi", "insert_power", "insert_paren", "insert_multiply",
    ):
        assert editor.findChild(QPushButton, object_name) is not None

    for name in ("sin", "cos", "exp", "log", "sqrt", "abs"):
        editor.setText("")
        button = editor.findChild(QPushButton, f"insert_{name}")
        assert button is not None
        button.click()
        assert editor.text() == f"{name}()"
        editor.formulaEdit.insert("pi")
        assert editor.text() == f"{name}(pi)"
        assert editor.expression() is not None

    editor.setText("")
    editor.findChild(QPushButton, "insert_paren").click()
    editor.formulaEdit.insert("pi")
    assert editor.text() == "(pi)"
    assert editor.expression() is not None

    editor.setText("")
    editor.findChild(QPushButton, "insert_pi").click()
    assert editor.text() == "pi"
    assert editor.expression() is not None

    for button_name, suffix in (("insert_power", "^2"), ("insert_multiply", "*2")):
        editor.setText("t")
        editor.findChild(QPushButton, button_name).click()
        editor.formulaEdit.insert("2")
        assert editor.text() == "t" + suffix
        assert editor.expression() is not None

    examples = {
        "example_linear": "a*t + b",
        "example_quadratic": "a*t^2 + b*t + c",
        "example_damped_cosine": "A*exp(-gamma*t)*cos(omega*t + phi) + y0",
    }
    for object_name, formula in examples.items():
        button = editor.findChild(QPushButton, object_name)
        assert button is not None
        button.click()
        assert editor.text() == formula
        assert editor.expression() is not None
        editor.formulaEdit.insert(" + 1")
        assert editor.text() == formula + " + 1"
        assert editor.expression() is not None
