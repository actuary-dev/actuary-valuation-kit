# Invented demo saved results

These are aggregates and reporting tables from seeded, invented inputs. No
policy book or seriatim output is stored. The project maintainers must approve any change to the saved results.

From the project root, regenerate only with:

    uv run python -m avk.testing.demo tests/saved/demo /tmp/avk-demo-results

The command runs all five products and valuation, cases, stress capital, IFRS
measurement and roll-forward at 10k and 100k, seed 209. CSV outputs become
lossless Zstandard Parquet files. MANIFEST.json records every column class;
all comparisons use avk.testing.parity, with no local tolerance constants.
The default suite runs 25 10k regressions; the slow group adds all 25 100k paths
and a 100k byte comparison across batch sizes 1024/8192 and threads 1/4.
The byte check covers every CSV, including seriatim, without storing seriatim.

    uv run pytest tests/regression/test_demo_suite.py tests/regression/test_demo_guards.py
    uv run pytest -m slow tests/regression/test_demo_suite.py
    NUMBA_DISABLE_JIT=1 uv run pytest -m purepython tests/regression/test_demo_guards.py
    uv run pytest -m perf tests/perf/test_demo_speed.py -s

Guard 1 includes four invalid books and two invalid formulas with exact expected
message fragments and compiler file/line context. Input-format checks also cover
missing numbers, duplicate keys, incomplete axes and overlapping stress windows.
The independent four-policy oracle uses ordinary Python scalar arithmetic for
both bases over all 372 months (2976 decrement and premium cells).
Guard 3 requires an idle reference laptop on mains power. Its initial baseline
is recorded once with AVK_RECORD_DEMO_BASELINE=1 on the perf command above.
Cold compile <=30 seconds, warm fixed overhead <=1 second, warm 100k elapsed
<=125% of the recorded baseline. Never replace a baseline to hide a failure.

PowerShell equivalents (from the project root, after the README environment setup):

```powershell
# Regeneration requires review; never replace references to hide a failure.
uv run python -m avk.testing.demo tests/saved/demo "$HOME\avk-work\avk-demo-results"
uv run pytest tests/regression/test_demo_suite.py tests/regression/test_demo_guards.py
uv run pytest -m slow tests/regression/test_demo_suite.py
$env:NUMBA_DISABLE_JIT = '1'
uv run pytest -m purepython tests/regression/test_demo_guards.py
Remove-Item Env:NUMBA_DISABLE_JIT
# Perf and baseline recording require the idle reference laptop on mains power.
uv run pytest -m perf tests/perf/test_demo_speed.py -s
$env:AVK_RECORD_DEMO_BASELINE = '1'
uv run pytest -m perf tests/perf/test_demo_speed.py -s
Remove-Item Env:AVK_RECORD_DEMO_BASELINE
```
