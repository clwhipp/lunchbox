from copy import deepcopy

import pytest

from schoolmenu.quality import CORE, check_coverage, coverage_rates


def report():
    summary = {
        "num_statements": 100,
        "covered_lines": 96,
        "num_branches": 100,
        "covered_branches": 96,
    }
    return {
        "totals": summary,
        "files": {f"schoolmenu/{core}": {"summary": deepcopy(summary)} for core in CORE},
    }


def test_independent_coverage_gates():
    assert check_coverage(report())["total"] == (96, 96)
    for field in ["covered_lines", "covered_branches"]:
        data = report()
        data["totals"][field] = 95
        with pytest.raises(ValueError, match="required"):
            check_coverage(data)
        data = report()
        data["files"]["schoolmenu/domain.py"]["summary"][field] = 0
        with pytest.raises(ValueError, match="domain.py"):
            check_coverage(data)
    data = report()
    data["files"] = {}
    with pytest.raises(ValueError, match="Missing"):
        check_coverage(data)
    assert coverage_rates({"num_statements": 0, "num_branches": 0}) == (100, 100)
