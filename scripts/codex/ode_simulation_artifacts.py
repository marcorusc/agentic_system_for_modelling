"""Structural validation of preserved BioMASS reports and numerical CSV outputs.

These checks verify the recorded files; they do not run a solver or establish
scientific validity. The artifact envelope verifies paths and hashes first.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path, PurePosixPath

try:
    from scripts.codex.ode_artifacts import read_json
except ModuleNotFoundError:
    from ode_artifacts import read_json


def _number(value: object, label: str, *, csv_value: bool = False) -> float:
    allowed = isinstance(value, str) if csv_value else type(value) in (int, float)
    if not allowed:
        raise ValueError(f'{label} requires a finite number')
    try:
        number = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f'{label} requires a finite number') from error
    if not math.isfinite(number):
        raise ValueError(f'{label} requires a finite number')
    return number


def _conditions(report: dict) -> set[str]:
    conditions = report.get('conditions')
    if not isinstance(conditions, list) or not conditions:
        raise ValueError('simulation requires nonempty condition records')
    names = set()
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ValueError('simulation condition must be an object')
        name = condition.get('name')
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('simulation conditions require unique nonempty names')
        names.add(name)
        # The backend records actual solver parameters and initials. Keep these
        # optional for minimal reports, but reject malformed values when present.
        for field in ('parameters', 'initials'):
            if field not in condition:
                continue
            values = condition[field]
            if not isinstance(values, dict):
                raise ValueError(f'condition {field} must be a numerical object')
            for identifier, value in values.items():
                if not isinstance(identifier, str) or not identifier.strip():
                    raise ValueError(f'condition {field} requires named quantities')
                _number(value, f'condition {field}.{identifier}')
    return names


def _trajectory(path: Path, conditions: set[str], bounds: tuple[float, float]) -> dict[str, list[float]]:
    times = {name: [] for name in conditions}
    with path.open(encoding='utf-8', newline='') as stream:
        rows = csv.DictReader(stream, strict=True)
        header = rows.fieldnames
        if not header or len(header) != len(set(header)) or any(not name.strip() for name in header):
            raise ValueError('trajectory requires unique nonempty column names')
        if not {'condition', 'time'} <= set(header):
            raise ValueError('trajectory requires condition and time columns')
        data_columns = set(header) - {'condition', 'time'}
        if not data_columns:
            raise ValueError('trajectory requires species or observable numeric columns')
        for row in rows:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('trajectory row does not match its columns')
            condition = row['condition']
            if condition not in conditions:
                raise ValueError('trajectory contains an undeclared condition')
            time = _number(row['time'], 'trajectory time', csv_value=True)
            if not bounds[0] <= time <= bounds[1]:
                raise ValueError('trajectory time lies outside the reported time span')
            if times[condition] and time <= times[condition][-1]:
                raise ValueError('trajectory times must increase for each condition')
            times[condition].append(time)
            for column in data_columns:
                _number(row[column], f'trajectory {column}', csv_value=True)
    for values in times.values():
        if not values:
            raise ValueError('trajectory is missing a reported condition')
        if values[0] != bounds[0] or values[-1] != bounds[1]:
            raise ValueError('trajectory does not cover the reported time span')
    return times


def validate_simulations(ode: dict, project: Path, files: dict[str, Path], prefix: str) -> None:
    """Check selected-revision lineage and the shape of each numerical result."""
    paths = ode['simulation_paths']
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ValueError('simulation paths must be a string array')
    if len(paths) != len(set(paths)):
        raise ValueError('duplicate simulation claim')
    for relative in paths:
        if relative not in files or not relative.startswith(prefix) or PurePosixPath(relative).name != 'simulation.json':
            raise ValueError('simulation claim requires a listed scenario report')
        report_path = files[relative]
        request_path = report_path.parent / 'request.json'
        request_relative = request_path.relative_to(project).as_posix()
        if request_relative not in files or read_json(request_path).get('revision') != ode['revision']:
            raise ValueError('simulation request must match the selected revision')
        report = read_json(report_path)
        if report.get('numerical_valid') is not True:
            raise ValueError('simulation requires successful actual numerical conditions')
        conditions = _conditions(report)
        span = report.get('time_span')
        if not isinstance(span, list) or len(span) != 2:
            raise ValueError('simulation time span requires two finite numerical bounds')
        bounds = (_number(span[0], 'time span start'), _number(span[1], 'time span end'))
        if bounds[0] >= bounds[1]:
            raise ValueError('simulation time span must increase')
        trajectories = []
        for name in ('species.csv', 'observables.csv'):
            path = report_path.parent / name
            if path.relative_to(project).as_posix() not in files:
                raise ValueError('simulation requires species and observable CSV trajectories')
            try:
                trajectories.append(_trajectory(path, conditions, bounds))
            except csv.Error as error:
                raise ValueError(f'invalid trajectory CSV: {name}') from error
        if trajectories[0] != trajectories[1]:
            raise ValueError('species and observable trajectories must share condition time grids')
