"""Download one URL to a file with a receipt; never executes or parses the payload.

Example:
  ./bin/python .agents/skills/bio-research/scripts/fetch_receipt.py URL \
      --output workspace/questions/Q/inputs/sources/paper.xml

The receipt (OUTPUT.receipt.json) records request, final URL, status, bytes and
sha256, or the failure. Certificate validation stays enabled. A 200 status does
not establish a usable scientific source; inspect the bytes before reuse.
"""
import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def fetch(url, output, *, receipt=None, max_bytes=0, timeout=120, user_agent="bio-data fetch_receipt"):
    output = Path(output)
    receipt = Path(receipt) if receipt else output.with_name(output.name + ".receipt.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    value = {"version": 1, "url": url, "started": datetime.now(UTC).isoformat(), "status": None,
             "final_url": None, "bytes": 0, "sha256": None, "output": str(output), "error": None,
             "note": "bytes saved verbatim; nothing was executed or rendered"}
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=timeout) as response, output.open("wb") as sink:
            value["status"] = response.status
            value["final_url"] = response.geturl()
            value["content_type"] = response.headers.get("Content-Type")
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                value["bytes"] += len(chunk)
                if max_bytes and value["bytes"] > max_bytes:
                    raise ValueError(f"payload exceeds --max-bytes {max_bytes}")
                digest.update(chunk)
                sink.write(chunk)
        value["sha256"] = digest.hexdigest()
    except urllib.error.HTTPError as error:
        value["status"] = error.code
        value["error"] = f"HTTP {error.code}: {error.reason}"
        value["error_body_prefix"] = error.read(512).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as error:
        value["error"] = f"{type(error).__name__}: {error}"
    if value["error"] and output.exists() and value["sha256"] is None:
        # A partial payload is kept but labelled; do not let it look complete.
        value["partial_bytes_kept"] = output.stat().st_size
    value["finished"] = datetime.now(UTC).isoformat()
    receipt.write_text(json.dumps(value, indent=2, allow_nan=False))
    return value, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, default=None, help="default: OUTPUT.receipt.json")
    parser.add_argument("--max-bytes", type=int, default=0, help="0 = unlimited")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    value, receipt = fetch(args.url, args.output, receipt=args.receipt, max_bytes=args.max_bytes, timeout=args.timeout)
    print(json.dumps({"event": "fetched" if not value["error"] else "fetch_failed", "receipt": str(receipt),
                      "status": value["status"], "bytes": value["bytes"], "sha256": value["sha256"], "error": value["error"]}))
    return 0 if not value["error"] else 1


if __name__ == "__main__":
    sys.exit(main())
