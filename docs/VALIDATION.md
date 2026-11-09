# Initial release verification

Verified locally on November 8, 2026 (America/Chicago).

| Check | Result |
| --- | --- |
| Python unit/integration tests | 102 passed on Python 3.14.4 |
| Same suite inside Docker | 102 passed on Python 3.13.18 |
| Python application coverage | 100% lines, 100% branches; independent 96% gates passed |
| Browser acceptance | 10 passed in installed Chrome |
| Custom JavaScript tests | 6 passed; 100% lines, branches, statements, and functions |
| Ruff checks and formatting | Passed |
| Mypy | Passed for all 16 application source files, excluding generated migrations |
| Migration drift | No changes detected |
| Production Docker deployment | Healthy on localhost port 8000, non-root UID 10001 |
| Isolated Docker persistence test | Preferences survived restart and container recreation |
| Isolated backup/restore | Consistent restored SQLite file retained both preference values |

The browser suite covers Saturday and Sunday defaults, weekday navigation, explicit week selection, detail dialogs, preference switching/clearing and reload persistence, failed-save rollback, three responsive widths, image fallbacks, and plain HTML operation without JavaScript. Weekend tests confirm November 7/8 opens November 9–13 and the “Upcoming week” shortcut returns there after navigating backward.

Coverage measures owned Python application code and the custom browser module. Generated database migrations and thin entry points are excluded from the percentage; migrations, WSGI startup, and browser bootstrapping are exercised by the integration, Docker, and browser checks. Operational smoke checks run against their own temporary volume and leave household preferences intact.

The production application uses live SchoolCafe data. Automated suites use recorded/synthetic data and prohibit accidental network requests. The newly observed JSON/base64 thumbnail format has its own captured regression fixture and bounded decoder tests. GitHub Actions is configured in `.github/workflows/ci.yml`; the results above are local execution results, not a claim that a remote CI run occurred.
