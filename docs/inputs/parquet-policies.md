# Parquet policy books

Use the same policy columns as CSV and declare the storage format explicitly:

    {"Inputs": {"Replace": {"policies_term": {
      "Source": "parquet", "Path": "/books/term.parquet"
    }}}}

The same location contract works for all five products, case policy overrides and
opening/closing books. Arrow decodes policy files in bounded batches; single-product
preparation uses Batch_Size. Source fingerprints use streaming SHA-256. Validation and preparation run on every batch before projection.
Identifier checks also reject duplicates across batch boundaries.

Single-product preparation spills to temporary, memory-mapped Arrow files. Its valuation lowers one
1024-policy logical block at a time through the existing compiled kernel, preserving
the original summation order. Per-policy slices spill to disk, and CSV writers stream
them in source order. Temporary files are released after the run; allow disk space for
the prepared book and policy slices. On Linux, set `TMPDIR` to an existing writable directory outside synced folders.
Diagnostic exports are for small books and intentionally retain diagnostic grids.

The perf group measures single-product Term valuation, not mixed-product dispatch.
It creates seeded 100k and 1M Term books outside the repository, then
measures fresh run-only child processes. The 1M peak limit is 2 GiB; growth from 100k
to 1M is limited to 256 MiB. Run only on idle mains power:
uv run pytest -m perf -s
PowerShell (idle mains power only):

```powershell
uv run pytest -m perf -s
```

On Windows, set TEMP and TMP to an unsynced folder before starting Python;
see [Windows](../WINDOWS.md). Use a native path such as C:/books/term.parquet
in JSON, or escape backslashes as C:\\books\\term.parquet.
The CSV speed guard retains its existing baseline.
