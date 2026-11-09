"""Independent line/branch gates prevent an aggregate score hiding missed branches."""

CORE = ("domain.py", "provider.py", "services.py", "images.py")


def coverage_rates(summary: dict) -> tuple[float, float]:
    statements = summary["num_statements"]
    branches = summary["num_branches"]
    lines = 100 * summary["covered_lines"] / statements if statements else 100.0
    paths = 100 * summary["covered_branches"] / branches if branches else 100.0
    return lines, paths


def check_coverage(report: dict, threshold: float = 96.0) -> dict[str, tuple[float, float]]:
    scopes = {"total": report["totals"]}
    for core in CORE:
        matches = [
            value["summary"] for name, value in report["files"].items() if name.endswith("/" + core)
        ]
        if len(matches) != 1:
            raise ValueError(f"Missing or ambiguous coverage for {core}")
        scopes[core] = matches[0]
    rates = {name: coverage_rates(summary) for name, summary in scopes.items()}
    for name, (lines, branches) in rates.items():
        if min(lines, branches) < threshold:
            raise ValueError(
                f"{name}: lines {lines:.2f}%, branches {branches:.2f}%; required {threshold}% each"
            )
    return rates
