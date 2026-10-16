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
            lines.append(f'Error reduction vs constant mean: {metrics.improvement_percent:.1f}%')
            lines.append(f'A constant line gives {metrics.baseline_rmse:.5g} {unit} error; this formula gives {metrics.rmse:.5g} {unit}.')
            if round(metrics.improvement_percent, 1) == 0:
                lines.append('At this displayed precision, the formula explains no more of the variation than a constant line. Try a different time-dependent formula or interval.')
    except ValueError as error:
        lines.append(f'Error comparison unavailable: {error}')
    expression = parse_expression(metadata['spec']['expression'])
    if not expression.uses_time:
        lines.append('Constant level only: no time variation is modeled.')
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
        else:
            lines.append(f"{conversion['name']} = {conversion['value']:.6g} (user result formula)")
    return '\n'.join(lines)
