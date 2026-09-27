# Backup and restore

```sh
uv run bio backup /absolute/path/outside-workspace/backup-2026-09-27
uv run bio restore-check /absolute/path/outside-workspace/backup-2026-09-27
```

The destination must not exist. Backup serializes against catalog writers, uses SQLite's online backup API, then copies/verifies every cataloged immutable blob and every question working file, including unsynced notebooks, scripts, outputs, and event journals. `backup.json` records the catalog hash and each file's hash/size. Stop external editors/scripts while taking a backup: they do not obey the catalog lock. A live database is never copied with `cp`.

`restore-check` copies the backup into an independent temporary workspace, runs SQLite integrity/foreign-key checks, reconciles the manifest, verifies every blob and question working file, and opens the restored inventory. It exits nonzero on failure. Older backups without question files remain supported.

For continued work, copy the **entire verified backup** to a new local directory, run `bio init NEW_DIRECTORY`, and select it with `-w` or `BIO_WORKSPACE`. Initialization preserves existing state and migrates old catalogs additively. Keep a pre-migration backup if you need rollback to older software. `daw report RUN_ID` can still regenerate historical v1 reports.

After an interruption, `bio recover` marks unfinished attempts interrupted, registers verified orphan blobs, lists staging files, requeues interrupted indexing tasks, and rebuilds question journals from committed events. It never marks a partial download successful. `daw gc --dry-run` previews old unregistered orphan blobs; `--execute` requires an unchanged preview. Preserved evidence and registered artifacts are retained.
