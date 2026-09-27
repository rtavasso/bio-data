"""Parser worker receives files and limits, never a writable catalog connection."""
import resource
import sys

from daw.models import Budgets
from daw.util import read_json, write_json


def main():
    job = read_json(sys.argv[1])
    budgets = Budgets.model_validate(job["budgets"])
    resource.setrlimit(resource.RLIMIT_CPU, (budgets.worker_seconds, budgets.worker_seconds + 1))
    # macOS does not reliably enforce RLIMIT_AS for scientific shared libraries.
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (budgets.worker_memory_bytes, budgets.worker_memory_bytes))
    if job.get("action") == "operator":
        from pathlib import Path
        from daw.models import Curation, Query
        from daw.operators import OPERATORS
        from daw.util import DawError, file_hash

        class Inputs:
            """Only selected immutable files, no catalog or write methods."""
            def __init__(self):
                self.budgets = budgets

            def blob_path(self, sha):
                if sha not in job["blobs"]:
                    raise DawError("unregistered_worker_input")
                path = Path(job["blobs"][sha])
                if file_hash(path) != sha:
                    raise DawError("integrity_failed")
                return path

        try:
            request = Query.model_validate(job["request"])
            rows, state, reason = OPERATORS[request.operator](Inputs(), job["asset"],
                Curation.model_validate(job["curation"]), request)
            result = {"rows": rows, "state": state, "reason": reason}
        except Exception as e:
            result = {"error": e.reason if isinstance(e, DawError) else type(e).__name__, "detail": str(e)[:1000]}
    else:
        from daw.inspectors import inspect_file
        result = inspect_file(job["path"], job["name"], budgets)
    result["worker_limits"] = {"cpu_seconds": budgets.worker_seconds,
                               "memory_hard_limit": sys.platform.startswith("linux"),
                               "memory_bytes": budgets.worker_memory_bytes,
                               "security_sandbox": False}
    write_json(sys.argv[2], result)


if __name__ == "__main__":
    main()
