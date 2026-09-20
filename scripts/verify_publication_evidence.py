"""Read-only checks for frozen publication evidence; no scientific solver or Qt."""
from __future__ import annotations

import argparse
from contextlib import closing
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sqlite3
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    """Raise a stable validation error rather than relying on Python assertions."""
    if not condition:
        raise ValueError(message)


def strict_json(data: str) -> object:
    """Reject non-standard NaN/Infinity and duplicate keys in configuration."""
    def bad_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON literal: {value}")

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(data, parse_constant=bad_constant, object_pairs_hook=unique_pairs)


def check_trajectory(rows: list[dict], meta: dict, fits: list[dict]) -> None:
    """Check release, source time, masks and archived residual arithmetic."""
    vid = meta['video_id']
    require(len(rows) == meta['frame_count'] - meta['release_frame'], f'{vid}: row count')
    for index, row in enumerate(rows):
        require(row['video_id'] == vid, f'{vid}: mixed video')
        frame = int(row['frame_index_0based'])
        require(frame == meta['release_frame'] + index, f'{vid}: effective release/frame mismatch')
        require(math.isclose(float(row['time_s']), index / meta['fps'], abs_tol=1e-9, rel_tol=0), f'{vid}: relative time mismatch')
        require(row['geometry_valid'] in ('True', 'False'), f'{vid}: invalid mask')
        likelihood = float(row['marker_likelihood'])
        require(math.isfinite(likelihood) and 0 <= likelihood <= 1, f'{vid}: likelihood')
    for fit in fits:
        require(int(fit['release_frame_used_0based']) == meta['release_frame'], f'{vid}: fit release')
        model = fit['model']
        residuals = []
        for row in rows:
            observed = float(row['theta_observed_deg'])
            predicted = float(row['theta_predicted_deg__' + model])
            residual = float(row['residual_deg__' + model])
            require(math.isclose(predicted - observed, residual, abs_tol=1e-10, rel_tol=0), f'{vid}: residual sign/units')
            if row['geometry_valid'] == 'True':
                residuals.append(residual)
        require(len(residuals) == int(fit['frame_count_geometry_valid']), f'{vid}: valid count')
        rmse = math.sqrt(sum(x*x for x in residuals) / len(residuals))
        require(math.isclose(rmse, float(fit['rmse_deg']), abs_tol=1e-8, rel_tol=0), f'{vid}: RMSE mismatch')


def check_fields(rows: list[dict], item: dict) -> None:
    """Check frozen field schema and explicit unit metadata before consuming rows."""
    require(item['columns'] == list(item['fields']), 'Field schema order mismatch')
    for name, field in item['fields'].items():
        require(bool(field['unit']) and bool(field['provenance']) and bool(field['comparison']), 'Incomplete field metadata')
        if '_deg' in name:
            require(field['unit'] == 'deg', f'{name}: degree unit metadata mismatch')
        if name in ('time_s', 'duration_post_release_s'):
            require(field['unit'] == 's', f'{name}: time unit metadata mismatch')
        if name in ('theta0_rad',):
            require(field['unit'] == 'rad', f'{name}: radian unit metadata mismatch')
    for row in rows:
        require(list(row) == item['columns'], 'Golden column schema mismatch')
        for name, field in item['fields'].items():
            value = row[name]
            if value in ('', None):
                require(field['nullable'], f'{name}: unexpected missing value')
                continue
            kind = field['type']
            if kind in ('number', 'integer'):
                number = float(value)
                require(math.isfinite(number), f'{name}: nonfinite value')
                require(kind != 'integer' or number.is_integer(), f'{name}: noninteger value')
            elif kind == 'boolean_token':
                require(value in ('True', 'False'), f'{name}: invalid boolean token')
            elif kind == 'object':
                require(isinstance(value, dict) and set(value) == set(field['properties']), f'{name}: nested schema mismatch')
                require(all(math.isfinite(float(v)) for v in value.values()), f'{name}: nonfinite coordinate')
            elif kind == 'array':
                require(isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value), f'{name}: invalid frame endpoints')
            else:
                require(kind == 'string' and isinstance(value, str), f'{name}: invalid string')


def check_extrema(rows: list[dict], trajectory: list[dict]) -> None:
    """Validate archived selected extrema identity and source joins, not re-detect peaks."""
    require(len(rows) == 213, 'P011 extrema count')
    lookup = {int(row['frame_index_0based']): row for row in trajectory}
    previous = -1
    for ordinal, row in enumerate(rows):
        frame = int(row['frame_index_0based'])
        require(int(row['extremum_index_0based']) == ordinal and frame > previous, 'Extrema order/identity')
        previous = frame
        require(frame in lookup, 'Extremum frame outside source')
        source = lookup[frame]
        for key in ('time_s', 'theta_observed_deg', 'omega_savgol9_rad_s'):
            require(math.isclose(float(row[key]), float(source[key]), abs_tol=1e-10, rel_tol=0), 'Extremum source join mismatch')
        value = float(source['theta_observed_deg'])
        before = float(lookup[frame-1]['theta_observed_deg'])
        after = float(lookup[frame+1]['theta_observed_deg'])
        kind = 'maximum' if value > before and value > after else 'minimum' if value < before and value < after else 'neither'
        require(row['extremum_type'] == kind, 'Extremum type mismatch')


def check_profiles(directory: Path, source_ids: set[str]) -> None:
    """Validate provenance references and prevent ambiguous inheritance."""
    profiles = [strict_json(path.read_text(encoding='utf-8')) for path in sorted(directory.glob('*.json'))]
    require(len(profiles) == 3, 'Expected three versioned profile documents')
    require({p['id'] for p in profiles} == {'legacy-publication-v1', 'student-default-v1', 'diagnostics-v1'}, 'Profile IDs')
    allowed = source_ids | {'policy-student-v1'}
    def walk(value: object) -> None:
        if isinstance(value, dict):
            if 'origin' in value:
                require(value['origin'] in {'historical_source', 'new_student_policy'}, 'Unknown provenance origin')
                require(bool(value.get('sources')), 'Missing section provenance')
                require(set(value['sources']) <= allowed, 'Unknown provenance source')
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    for profile in profiles:
        walk(profile)
    student = next(p for p in profiles if p['id'] == 'student-default-v1')
    legacy = next(p for p in profiles if p['id'] == 'legacy-publication-v1')
    require(student['base_profile'] == legacy['id'], 'Unknown inherited profile')
    require(set(student['inherit_sections']) <= legacy.keys(), 'Unknown inherited section')
    require(student['ic']['requires_rest_confirmation'] is True, 'Student rest IC must be explicit')
    require(student['conventions']['timestamp_zero_allowed'] is True, 'Zero timestamp must be allowed')
    require(student['weighting']['manual_requires_ai_likelihood'] is False, 'Adopted manual points must not depend on AI likelihood')
    require(legacy['qc']['requires_tracked_pivot_finite'] is False, 'Legacy mask silently changed')
    require(student['qc']['requires_all_four_finite_coordinates'] is True, 'Student four-point QC missing')


def verify(root: Path = ROOT, external_roots: dict[str, Path] | None = None) -> dict[str, int]:
    """Verify frozen package; optionally hash external sources without modifying them."""
    evidence = root / 'publication/evidence'
    manifest = strict_json((evidence / 'source-map.json').read_text(encoding='utf-8'))
    for item in manifest['profile_files']:
        data = (root / item['path']).read_bytes()
        require(hashlib.sha256(data).hexdigest() == item['sha256'], f"Profile SHA mismatch: {item['path']}")
    sources = {item['id']: item for item in manifest['sources']}
    require(len(sources) == len(manifest['sources']), 'Duplicate source IDs')
    check_profiles(root / 'publication/profiles', set(sources))
    loaded = {}
    for item in manifest['local_files']:
        path = evidence / item['path']
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == item['sha256'], f"SHA mismatch: {item['id']}")
        source_ids = item['source'] if isinstance(item['source'], list) else [item['source']]
        require(set(source_ids) <= sources.keys(), 'Unknown golden source')
        if path.suffix == '.gz':
            data = gzip.decompress(data)
        if len(source_ids) == 1:
            source = sources[source_ids[0]]
            expected_source_hash = source.get('sha256', source.get('selected_content_sha256'))
            # Trajectory source is already gzip; diagnostic copies use deterministic gzip.
            original_bytes = path.read_bytes() if item['kind'] == 'trajectory' else data
            require(hashlib.sha256(original_bytes).hexdigest() == expected_source_hash, f"Golden/source identity mismatch: {item['id']}")
        if '.csv' in path.name:
            rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
        else:
            rows = strict_json(data.decode('utf-8'))
        require(len(rows) == item['rows'], f"Count mismatch: {item['id']}")
        check_fields(rows, item)
        loaded[item['id']] = rows
    fits = loaded['fit48']
    require(len({(r['video_id'], r['model']) for r in fits}) == 48, 'Duplicate fit key')
    require(all(r['fit_status'] == 'success' and r['release_offset_frames'] == '0' for r in fits), 'Not formal effective-release fits')
    inputs = {r['video_id']: r for r in loaded['inputs24']}
    require(len(inputs) == 24 and {r['video_id'] for r in fits} == inputs.keys(), 'Video sets mismatch')
    for vid, meta in inputs.items():
        require(meta['initial_frames'] == [meta['release_frame']-5, meta['release_frame']-1], f'{vid}: IC frames')
        for row in [r for r in fits if r['video_id'] == vid]:
            require(row['calibration_sha256'].lower() == sources[meta['source']]['sha256'], f'{vid}: calibration identity')
            require(math.isclose(float(row['theta0_deg_signed']), math.degrees(meta['theta0_rad']), abs_tol=1e-10), f'{vid}: IC units')
    for vid in ('P011', 'P014'):
        check_trajectory(loaded['trajectory-'+vid], inputs[vid], [r for r in fits if r['video_id'] == vid])
        require(sources['trajectory-'+vid]['role'] == 'formal_effective_release_trajectory', 'Old trajectory source forbidden')
    check_extrema(loaded['P011-information-extrema'], loaded['trajectory-P011'])
    for row in loaded['db-m1_tail_frequency_periods']:
        period = row['end_crossing_time_s'] - row['start_crossing_time_s']
        require(math.isclose(period, row['period_s'], abs_tol=1e-10), 'Tail period time mismatch')
        require(math.isclose((2*math.pi/period)**2, row['omega2_tail_period_s_inv2'], rel_tol=1e-12), 'Tail period units')
    for row in loaded['fig04_complete_raw_parameter_sets']:
        scale = 1 + float(row['alpha_a'])
        for raw, lump in [('alpha1_s_inv', 'alpha1_star_s_inv'), ('alpha2_rad_inv', 'alpha2_star_rad_inv'), ('omega0_sq_s_inv2', 'omega_obs_sq_s_inv2')]:
            require(math.isclose(float(row[raw])/scale, float(row[lump]), abs_tol=1e-12, rel_tol=1e-12), 'Raw/starred parameter mismatch')
    curve = loaded['db-report_identifiability_objective_curve']
    fitted_q = next(float(r['omega2_s_inv2']) for r in fits if r['video_id'] == 'P011' and r['model'] == 'M1_linear_quadratic')
    reference = next(r['robust_objective'] for r in curve if math.isclose(r['omega2_observed_s_inv2'], fitted_q, rel_tol=0, abs_tol=1e-12))
    for row in curve:
        require(math.isclose(row['robust_objective']/reference, row['objective_over_fitted'], rel_tol=1e-12), 'Objective normalization mismatch')
    checked_external = 0
    for item in sources.values():
        if item.get('root') not in (external_roots or {}):
            continue
        path = external_roots[item['root']] / item['path']
        if 'table' in item:
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro')) as connection:
                connection.row_factory = sqlite3.Row
                # Table names come from the checked-in manifest, restricted before quoting.
                table = item['table']
                require(table.replace('_', '').isalnum(), 'Invalid table name')
                rows = [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
            if item['selection'] == "video_id='P011'":
                rows = [row for row in rows if row['video_id'] == 'P011']
            else:
                require(item['selection'] == 'all rows', 'Unknown table selection')
            columns = list(rows[0])
            rows.sort(key=lambda row: tuple(str(row[col]) for col in columns))
            data = (json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
            expected = item['selected_content_sha256']
        elif 'zip_member' in item:
            with zipfile.ZipFile(path) as archive:
                data = archive.read(item['zip_member'])
            expected = item['sha256']
        else:
            data = path.read_bytes()
            expected = item['sha256']
        require(hashlib.sha256(data).hexdigest() == expected, f"External source mismatch: {item['id']}")
        if item['id'] == 'fig03_p011_measured_phase_and_speed':
            archived = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
            expected_times = [float(row['time_s']) for row in archived if row['is_detected_extremum'] == 'True']
            require(expected_times == [float(row['time_s']) for row in loaded['P011-information-extrema']], 'Archived extrema selection mismatch')
        checked_external += 1
    return {'local_files': len(loaded), 'formal_fit_rows': len(fits), 'offline_trajectory_cases': 2, 'external_sources': checked_external}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prov-root', type=Path)
    parser.add_argument('--ejp-root', type=Path)
    args = parser.parse_args()
    roots = {key: path for key, path in [('PROV', args.prov_root), ('EJP', args.ejp_root)] if path is not None}
    print(json.dumps(verify(external_roots=roots), ensure_ascii=False))


if __name__ == '__main__':
    main()
