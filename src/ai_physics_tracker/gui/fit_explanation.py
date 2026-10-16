"""GUI层：把同样本拟合指标与可选换算解释为图旁英文反馈。"""
from ai_physics_tracker.domain.expression import parse_expression
from ai_physics_tracker.domain.fit_interpretation import interpret_fit


def explain_fit(metadata: dict, unit: str) -> str:
    """只解释记录中实际保存的模型与样本，不推断实验物理正确性。"""
    summary = metadata['summary']
    measured = [row['value'] for row in metadata['samples']]
    predicted = summary['prediction']
    lines = []
    try:
        metrics = interpret_fit(measured, predicted)
        lines.append(f'Typical deviation (RMSE): {metrics.rmse:.5g} {unit}')
        if metrics.improvement_percent is None:
            lines.append('Improvement vs constant mean: unavailable — '+metrics.reason)
        else:
            lines.append(f'Error reduction vs constant mean: {metrics.improvement_percent:.3g}%')
    except ValueError as error:
        lines.append(f'Error comparison unavailable: {error}')
    expression = parse_expression(metadata['spec']['expression'])
    if not expression.uses_time:
        lines.append('Constant level only: no time variation is modeled. Try a time-dependent example to explain changes.')
    conversions = summary.get('result_formulas', [])
    for conversion in conversions:
        if conversion.get('error'):
            try:
                parsed = parse_expression(conversion['formula'])
                missing = set(parsed.parameter_names)-dict(summary['parameter_values']).keys()
            except ValueError:
                missing = set()
            detail = 'Missing fitted parameter(s): '+', '.join(sorted(missing)) if missing else conversion['error']
            lines.append(f"Fit completed; {conversion['name']} was not calculated. {detail}.")
            lines.append('Next: edit / clear the optional result formula, or Measure repeat intervals.')
        else:
            lines.append(f"{conversion['name']} = {conversion['value']:.6g} (user result formula)")
    lines.append('Convergence does not validate the physical model. Residuals are not measurement uncertainty.')
    return '\n'.join(lines)
