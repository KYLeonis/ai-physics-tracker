"""P1.4 联合推理必须作为同一四 bodypart 批次整体解析。"""

import csv
from math import nan

import pandas as pd
import pytest

from ai_physics_tracker.domain.pendulum import ROLE_ORDER
from ai_physics_tracker.infrastructure.dlc_predictions import read_joint_raw_predictions


MAPPING = tuple((role, role) for role in ROLE_ORDER)


def _batch():
    columns = pd.MultiIndex.from_tuples(
        [("scorer", role, coord) for role in ROLE_ORDER
         for coord in ("x", "y", "likelihood")]
    )
    return pd.DataFrame(
        [[value for _ in ROLE_ORDER for value in (1.0, 2.0, 0.9)],
         [value for _ in ROLE_ORDER for value in (3.0, 4.0, 0.8)]],
        index=[0, 1], columns=columns,
    )


def test_joint_parser_preserves_role_missing_and_frame_identity(tmp_path):
    batch = _batch()
    batch.loc[1, ("scorer", "pivot", "x")] = nan
    batch = batch.iloc[::-1]
    parsed = read_joint_raw_predictions(batch, MAPPING, frame_count=2,
                                        expected_scorer="scorer")
    assert parsed.complete_count == 1
    assert dict(parsed.missing_by_role)["pivot"] == 1
    assert [row.frame_index for row in dict(parsed.by_role)["tip"]] == [0, 1]
    path = tmp_path / "predictions.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["scorer", *["scorer"] * 12])
        writer.writerow(["bodyparts", *[role for role in ROLE_ORDER for _ in range(3)]])
        writer.writerow(["coords", *[coord for _ in ROLE_ORDER
                                      for coord in ("x", "y", "likelihood")]])
        for index, row in batch.iterrows():
            writer.writerow([index, *row.to_list()])
    assert read_joint_raw_predictions(path, MAPPING, frame_count=2,
                                      expected_scorer="scorer").complete_count == 1


@pytest.mark.parametrize("mutation", [
    lambda batch: batch.drop(columns=("scorer", "pivot", "x")),
    lambda batch: batch.rename(columns={"pivot": "extra"}, level=1),
    lambda batch: batch.set_axis([0, 0], axis=0),
    lambda batch: batch.rename(columns={"scorer": "other"}, level=0),
])
def test_joint_parser_rejects_invalid_batch(mutation):
    with pytest.raises(ValueError):
        read_joint_raw_predictions(mutation(_batch()), MAPPING,
                                   frame_count=2, expected_scorer="scorer")


def test_joint_parser_rejects_duplicate_column_and_infinity():
    batch = _batch()
    batch.columns = list(batch.columns[:-1]) + [batch.columns[-2]]
    with pytest.raises(ValueError, match="duplicate"):
        read_joint_raw_predictions(batch, MAPPING, frame_count=2)
    batch = _batch()
    batch.loc[1, ("scorer", "pivot", "x")] = float("inf")
    with pytest.raises(ValueError, match="finite"):
        read_joint_raw_predictions(batch, MAPPING, frame_count=2)
