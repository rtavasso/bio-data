"""Pinned GEOfetch + resolved PEP integration with a source-preserving failure fallback."""
import contextlib
import io
import os
import re
import signal
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from daw.models import Asset
from daw.util import DawError, file_hash, now


def soft_records(text):
    """Bounded SOFT metadata records; values are never normalized biologically."""
    records, current = [], None
    for line in text.splitlines():
        if line.startswith("^") and " = " in line:
            kind, native = line[1:].split(" = ", 1)
            current = {"kind": kind, "id": native, "fields": {}}
            records.append(current)
        elif current is not None and line.startswith("!") and " = " in line:
            key, value = line[1:].split(" = ", 1)
            current["fields"].setdefault(key, []).append(value)
    return records


def load_pep(path):
    import peppy
    import yaml

    path = Path(path).resolve()
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict):
        raise DawError("invalid_pep")
    # Generated local PEP only. Remote imports and arbitrary filesystem resolution are not part of this adapter.
    if "imports" in config or "import" in config:
        raise DawError("unsupported_pep_import", "provide a flattened local PEP")
    for field in ("sample_table", "subsample_table"):
        values = config.get(field, [])
        values = [values] if isinstance(values, str) else values
        for value in values:
            resolved = (path.parent / value).resolve()
            if path.parent not in resolved.parents or not resolved.is_file():
                raise DawError("unsafe_pep_path", field)
    with contextlib.redirect_stdout(io.StringIO()):
        project = peppy.Project(str(path))
    result = []
    for sample in project.samples:
        values = {}
        for key, value in dict(sample).items():
            if key.startswith("_"):
                continue
            if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                values[key] = value
            else:
                values[key] = str(value)
        result.append(values)
    return result


def resolve_geo(source, native, bundle):
    if not re.fullmatch(r"GSE\d+", native):
        raise DawError("unsupported_reference")
    ws = source.ws
    directory = ws.root / "staging" / ("geofetch-" + uuid.uuid4().hex)
    directory.mkdir()
    records, original_blobs, snapshots = [], {}, []
    for target in ("gse", "gsm"):
        url = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?" + urlencode({"targ": target, "acc": native, "form": "text", "view": "full"})
        text, sid, blob = source.payload(url, "txt")
        snapshots.append(sid)
        original_blobs[target] = blob
        (directory / f"{native}_{target.upper()}.soft").write_text(text)
        parsed = soft_records(text)
        if not parsed:
            raise DawError("malformed_metadata", "GEO response contained no SOFT records")
        records.extend((r, sid) for r in parsed)
    assets, relations = [], []
    for record, sid in records:
        kind = record["kind"].lower()
        rid = ws.resource("sample" if kind == "sample" else "study", "geo", record["id"], record)
        ws.link(bundle, rid, "contains_sample" if kind == "sample" else "describes", sid, "^" + record["kind"] + " = " + record["id"])
        for key, values in record["fields"].items():
            if "supplementary_file" in key:
                for value in values:
                    if value in {"NONE", "none"} or not value.startswith(("ftp://", "http://", "https://")):
                        continue
                    url = value.replace("ftp://", "https://", 1)
                    a = Asset(native_id=record["id"] + ":" + urlsplit(url).path, name=Path(urlsplit(url).path).name,
                              url=url, metadata={"source_record": rid, "level": kind, "source_field": key,
                                                 "listed_url": value}, raw=url.lower().endswith((".fastq.gz", ".bam", ".cram", ".sra")))
                    assets.append((a, sid))
            if key.endswith("relation"):
                for value in values:
                    relations.append({"subject": record["id"], "value": value, "source_snapshot": sid})
                    for accession in re.findall(r"GSE\d+|GSM\d+|[SED]R[APRSX]\d+|PRJNA\d+", value):
                        if re.fullmatch(r"[SED]RX\d+", accession):
                            other = ws.resource("experiment", "insdc", accession)
                        elif accession.startswith("GSE"):
                            other = ws.resource("study", "geo", accession)
                        elif accession.startswith("GSM"):
                            other = ws.resource("sample", "geo", accession)
                        else:
                            other = ws.resource("reference", "accession", accession)
                        ws.link(rid, other, "source_relationship", sid, f"{key}: {value}")
    tool_root = Path(__file__).resolve().parents[2] / "tools/geofetch"
    executable = tool_root / ".venv/bin/geofetch"
    command = [str(executable), "-i", native, "--processed", "--data-source", "all", "--just-metadata",
               "--disable-progressbar", "--max-soft-size", "16MB", "-n", native, "-u", str(directory)]
    receipt = {"command": command, "tool": "geofetch", "version": "0.12.11", "started": now(),
               "environment_lock": file_hash(tool_root / "uv.lock") if (tool_root / "uv.lock").exists() else None}
    pep_results = []
    if executable.exists():
        log_path = directory / "geofetch.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True,
                env={"PATH": os.environ.get("PATH", ""), "PYTHONUNBUFFERED": "1"})
            try:
                process.wait(timeout=min(90, ws.budgets.worker_seconds))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                receipt["timeout"] = True
            receipt["exit_code"] = process.returncode
        receipt["log_blob"] = ws.put_file(log_path, "metadata")
        for path in sorted(directory.rglob("*.yaml")):
            if path.stem.endswith(("_samples", "_series", "_processed")):
                try:
                    resolved = load_pep(path)
                    pep_results.append({"config_blob": ws.put_file(path, "metadata"), "name": path.name,
                                        "resolved_blob": ws.put_json(resolved), "sample_rows": len(resolved)})
                except (DawError, ImportError, ValueError) as e:
                    source.warnings.append(f"PEP resolution blocked for {path.name}: {e}")
        receipt["files"] = {str(p.relative_to(directory)): ws.put_file(p, "metadata")
                            for p in sorted(directory.rglob("*")) if p.is_file() and p.stat().st_size <= 16 * 2**20}
    else:
        receipt["outcome"] = "isolated_tool_not_installed"
    if not pep_results:
        source.warnings.append("GEOfetch/PEP resolution incomplete; inventory uses preserved SOFT references without biological normalization")
    receipt["finished"] = now()
    sid = ws.snapshot("geofetch:" + native, "structure_inspected" if pep_results else "unsupported_route",
                      receipt, ws.put_json(receipt), bundle)
    source.snapshots.append(sid)
    return assets, snapshots[0], {"soft_blobs": original_blobs, "resolved_peps": pep_results,
                                 "tool_receipt": sid, "relations": relations, "sample_file_rows_are_not_replicates": True}
