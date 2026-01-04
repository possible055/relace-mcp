import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "benchmark"))

from evaluation.metrics import compute_f_score, compute_joint_f_score


class TestComputeFScore:
    def test_perfect_scores(self) -> None:
        result = compute_f_score(1.0, 1.0, beta=1.0)
        assert result == pytest.approx(1.0)

    def test_zero_precision(self) -> None:
        assert compute_f_score(0.0, 1.0, beta=1.0) == 0.0

    def test_zero_recall(self) -> None:
        assert compute_f_score(1.0, 0.0, beta=1.0) == 0.0

    def test_f1_balanced(self) -> None:
        # F1 with equal precision and recall should equal them
        result = compute_f_score(0.8, 0.8, beta=1.0)
        assert result == pytest.approx(0.8)

    def test_f1_unbalanced(self) -> None:
        # F1 = 2 * P * R / (P + R) = 2 * 0.8 * 0.6 / 1.4 ≈ 0.6857
        result = compute_f_score(0.8, 0.6, beta=1.0)
        expected = 2 * 0.8 * 0.6 / (0.8 + 0.6)
        assert result == pytest.approx(expected)

    def test_beta_half_emphasizes_precision(self) -> None:
        # β=0.5: precision weighted more heavily
        # Fβ = (1 + β²) * P * R / (β² * P + R)
        # F0.5 = 1.25 * 0.9 * 0.5 / (0.25 * 0.9 + 0.5)
        result = compute_f_score(0.9, 0.5, beta=0.5)
        expected = 1.25 * 0.9 * 0.5 / (0.25 * 0.9 + 0.5)
        assert result == pytest.approx(expected)
        # With β=0.5, high precision + low recall should score well
        assert result > 0.6

    def test_beta_two_emphasizes_recall(self) -> None:
        # β=2: recall weighted more heavily
        result_high_recall = compute_f_score(0.5, 0.9, beta=2.0)
        result_high_prec = compute_f_score(0.9, 0.5, beta=2.0)
        # High recall should score better with β=2
        assert result_high_recall > result_high_prec


class TestComputeJointFScore:
    def test_empty_returned(self) -> None:
        result = compute_joint_f_score({}, {"a.py": [(1, 10)]})
        assert result["file_precision"] == 0.0
        assert result["file_recall"] == 0.0
        assert result["joint_f"] == 0.0

    def test_perfect_match(self) -> None:
        files = {"a.py": [[1, 10]]}
        gt = {"a.py": [(1, 10)]}
        result = compute_joint_f_score(files, gt, beta=1.0)
        assert result["file_precision"] == pytest.approx(1.0)
        assert result["file_recall"] == pytest.approx(1.0)
        assert result["file_f"] == pytest.approx(1.0)
        assert result["line_precision"] == pytest.approx(1.0)
        assert result["line_recall"] == pytest.approx(1.0)
        assert result["line_f"] == pytest.approx(1.0)
        assert result["joint_f"] == pytest.approx(1.0)

    def test_partial_file_match(self) -> None:
        files = {"a.py": [[1, 10]], "b.py": [[1, 5]]}
        gt = {"a.py": [(1, 10)]}
        result = compute_joint_f_score(files, gt, beta=1.0)
        # File precision = 1/2 = 0.5, recall = 1/1 = 1.0
        assert result["file_precision"] == pytest.approx(0.5)
        assert result["file_recall"] == pytest.approx(1.0)

    def test_beta_affects_f_scores(self) -> None:
        files = {"a.py": [[1, 10]]}
        gt = {"a.py": [(1, 5)], "b.py": [(1, 10)]}
        result_beta_half = compute_joint_f_score(files, gt, beta=0.5)
        result_beta_two = compute_joint_f_score(files, gt, beta=2.0)
        # With higher file precision than recall, β=0.5 should give higher score
        assert result_beta_half["file_f"] > result_beta_two["file_f"]

    def test_file_weight(self) -> None:
        files = {"a.py": [[1, 10]]}
        gt = {"a.py": [(1, 10)]}
        result_file_heavy = compute_joint_f_score(files, gt, file_weight=0.9)
        result_line_heavy = compute_joint_f_score(files, gt, file_weight=0.1)
        # Perfect match, both should be 1.0
        assert result_file_heavy["joint_f"] == pytest.approx(1.0)
        assert result_line_heavy["joint_f"] == pytest.approx(1.0)

    def test_returns_all_keys(self) -> None:
        result = compute_joint_f_score({}, {})
        expected_keys = {
            "file_precision",
            "file_recall",
            "file_f",
            "line_precision",
            "line_recall",
            "line_f",
            "joint_f",
        }
        assert set(result.keys()) == expected_keys
