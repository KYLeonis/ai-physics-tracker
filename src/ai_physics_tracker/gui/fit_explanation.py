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
    '95% local confidence interval = estimate ± t(0.975, n − p) × SE. '
    'The interval additionally assumes approximately normal residuals; for nonlinear models it is a local approximation. '
    'These are individual parameter intervals, not a joint region, prediction band or proof of the physical model. '
    'Scale calibration, pivot / reference and timing systematics are not quantified. '
    'Only Measured position / angle sources support SE and intervals. '
    'User result formulas show values only; their uncertainty is not propagated.'
)

RECURRENCE_ERROR_NOTE = (
    'Sample std describes scatter between successive intervals, not the error of the mean '
    'or a parameter SE. Adjacent intervals can share event errors and be correlated. '
    'Timing, reference and other systematics are not quantified.'
)

PARAMETER_RESULT_HELP = (
    'Parameter: a named constant in your formula. Use this row to read its fitted value and precision. '
    'Its physical meaning and units depend on your formula, not its name.',
    'Estimate: the value chosen by least squares to fit the selected source samples. '
    'Use it in your formula or compare it with a reference value. A good fit does not establish physical correctness.',
    'Conditional standard error (SE): the local uncertainty scale of an estimated parameter, in that parameter\'s units. '
    'Use it to assess how tightly these samples constrain the parameter. It assumes independent, zero-mean, '
    'equal-variance residuals and holds the formula, source and fixed parameters given. '
    'It excludes calibration, timing and other systematic uncertainty. Fixed means the parameter was not estimated; '
    'Not recorded means this historical result has no saved statistic.',
    '95% confidence interval (local): [lower, upper] = estimate ± t(0.975, n − p) × SE; '
    'n is the number of fitted samples and p is the number of free parameters. '
    'Use the width to assess parameter precision and compare the range with a reference value. '
    'Under the assumptions, 95% of intervals from repeated datasets would cover the true parameter. '
    'Residuals must be approximately normal; nonlinear fits use a local approximation. '
    'This is an individual parameter interval, not a prediction range or complete experimental uncertainty. '
    'Fixed has no estimated interval; Not recorded is never filled in retrospectively.',
)

FIXED_PARAMETER_HELP = (
    'To hold a known parameter value: open Parameter bounds / fixed values, enter the value in Initial, '
    'check Fixed in that row, then click Fit. Uncheck Fixed to estimate it again. '
    'While viewing a recorded result, click Use recorded setup first. '
    'Fixed holds Initial, not the previous fitted Estimate. Its SE and interval show Fixed because it is not estimated; '
    'uncertainty in the supplied fixed value is not propagated.'
)

FIT_METRIC_HELP = (
    'Residual = measured source value − model prediction. Inspect the Residuals plot for patterns the formula misses.\n\n'
    'RMSE (root mean square error) summarizes residual scatter in the source units; it is not parameter SE. '
    'Compare RMSE only for the same samples and source.\n\n'
    'Error reduction vs constant mean compares RMSE with a horizontal line at the mean of those same samples. '
    'It describes improvement over that baseline, not the probability that the physical model is correct.\n\n'
    'User result formulas substitute parameter values only; uncertainty is not propagated.\n\n'
    + RECURRENCE_ERROR_NOTE
)


def parameter_error_rows(metadata: dict) -> tuple[tuple[str, str, str, str], ...]:
    """只读已记录SE；旧 / 损坏 / 未来统计不回填且不展示伪数值。"""
    from ai_physics_tracker.application.signal_analysis_job import recorded_parameter_errors
    from ai_physics_tracker.domain.function_fit import FitParameter
    parameters = tuple(FitParameter(**row) for row in metadata['spec']['parameters'])
    summary = metadata['summary']
    values = dict(summary['parameter_values'])
    if 'parameter_uncertainty' not in summary:
        descriptions = intervals = ['Not recorded'] * len(parameters)
    else:
        try:
            entries = recorded_parameter_errors(metadata)
            descriptions = [f'{entry.standard_error:.6g}' if entry.status == 'estimated'
                            else 'Fixed' if entry.status == 'fixed' else entry.reason for entry in entries]
            intervals = [_interval_text(entry.confidence_interval) if entry.confidence_interval is not None
                         else 'Fixed' if entry.status == 'fixed' else entry.interval_reason for entry in entries]
        except (KeyError, TypeError, ValueError) as error:
            descriptions = intervals = [str(error)] * len(parameters)
    return tuple((parameter.name, f'{values[parameter.name]:.6g}', text, interval)
                 for parameter, text, interval in zip(parameters, descriptions, intervals))


def _interval_text(bounds: tuple[float, float]) -> str:
    lower, upper = (f'{value:.8g}' for value in bounds)
    if lower == upper and bounds[0] < bounds[1]:
        lower, upper = (f'{value:.17g}' for value in bounds)
    return f'[{lower}, {upper}]'
