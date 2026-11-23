# Run audit trail

Every run with a resolvable, writable output folder leaves four files:
- run_record.json: settings, installed engine version, SHA-256 fingerprints of file inputs,
  kernel identities, named cases and stresses, completion state and timings.
- main.log: start, finish and emitted engine messages.
- error.log: empty on success; the failure type and message on failure.
- run_status.json: the current status and stage, replaced atomically.

Hashes describe source bytes, including configuration files, table indexes, case tables,
stress presets and correlations when used. In-memory configurations are recorded as settings.
Run records use sorted JSON keys. Only timestamps and timings vary for identical inputs.
These metadata files are excluded from saved reporting-table comparisons.
Resolved root, output and diagnostics paths include API/CLI overrides.
The optional Python progress callback receives a dictionary with status and stage.
The audit covers invalid settings as well as input/projection errors. CLI --output is
honoured even when settings fail validation. An explicit output override also permits
a failed record for unreadable or malformed configurations; unreadable files have a
null fingerprint and an explicit error. Without a resolvable output path, or when the
output is unwritable, the original configuration error is reported.
Output folders should be unique per run; files in an existing folder are replaced.
