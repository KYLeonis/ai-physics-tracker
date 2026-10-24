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
    lines.append('RMSE measures residual scatter, not parameter SE or full measurement uncertainty.')
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
            lines.append(f"{conversion['name']} = {conversion['value']:.6g} (user result formula; value only, uncertainty not propagated)")
    return '\n'.join(lines)


PARAMETER_ERROR_METHOD = (
    'Conditional SE: local Jacobian SVD with residual variance SSE / (n − p), '
    'restored to each original parameter scale. Assumes zero-mean, independent, '
    'equal-variance residuals and a locally linear model, conditional on this formula, '
    'fixed parameters and source samples. Unsmoothed data do not guarantee independence. '
    'This is not a confidence interval or proof of the physical model. '
    'Scale calibration, pivot / reference and timing systematics are not quantified. '
    'User result formulas show values only; their uncertainty is not propagated.'
)

RECURRENCE_ERROR_NOTE = (
    'Sample std describes scatter between successive intervals, not the error of the mean '
    'or a parameter SE. Adjacent intervals can share event errors and be correlated. '
    'Timing, reference and other systematics are not quantified.'
)


def parameter_error_rows(metadata: dict) -> tuple[tuple[str, str, str], ...]:
    """只读已记录SE；旧 / 损坏 / 未来统计不回填且不展示伪数值。"""
    from ai_physics_tracker.application.signal_analysis_job import signal_source
    from ai_physics_tracker.domain.function_fit import FitParameter
    from ai_physics_tracker.domain.fit_uncertainty import read_parameter_uncertainty
    parameters = tuple(FitParameter(**row) for row in metadata['spec']['parameters'])
    summary = metadata['summary']
    values = dict(summary['parameter_values'])
    raw = summary.get('parameter_uncertainty')
    if 'parameter_uncertainty' not in summary:
        descriptions = ['Not recorded'] * len(parameters)
    else:
        try:
            snapshot = metadata.get('source_snapshot')
            if isinstance(snapshot, dict):
                kind = snapshot['kind']
            else:
                selection = metadata['selection']
                if type(selection['smoothed']) is not bool:
                    raise ValueError('Unreadable recorded source processing')
                kind, _ = signal_source(metadata['quantity'], selection['smoothed'])
            entries = read_parameter_uncertainty(
                raw, parameters, len(metadata['samples']) if 'samples' in metadata else metadata['sample_count'], kind)
            descriptions = [f'{entry.standard_error:.6g}' if entry.status == 'estimated'
                            else 'Fixed' if entry.status == 'fixed' else entry.reason for entry in entries]
        except (KeyError, TypeError, ValueError) as error:
            descriptions = [str(error)] * len(parameters)
    return tuple((parameter.name, f'{values[parameter.name]:.6g}', text)
                 for parameter, text in zip(parameters, descriptions))
