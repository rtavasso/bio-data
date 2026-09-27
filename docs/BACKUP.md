# Backup and restore

```sh
uv run daw backup /absolute/path/outside-workspace/backup-2026-09-27
uv run daw restore-check /absolute/path/outside-workspace/backup-2026-09-27
```

The destination must not exist. Backup serializes against writers, uses SQLite's online backup API, then copies/verifies every cataloged immutable blob. `backup.json` records the catalog hash and each blob's hash/size. A live database is never copied with `cp`.

`restore-check` copies the backup into an independent temporary workspace, runs SQLite integrity/foreign-key checks, reconciles the manifest, verifies every blob, and opens the restored inventory. It exits nonzero on failure.

For continued work, copy the **entire verified backup** to a new local directory, run `daw init NEW_DIRECTORY`, and select it with `-w` or `DAW_WORKSPACE`. Initialization preserves existing state. `daw report RUN_ID` regenerates reports from immutable artifacts.

After an interruption, `daw recover` marks unfinished attempts interrupted, registers verified orphan blobs, and lists staging files. It never marks a partial download successful. `daw gc --dry-run` previews old unregistered orphan blobs; `--execute` requires an unchanged preview. Accepted evidence is retained.
