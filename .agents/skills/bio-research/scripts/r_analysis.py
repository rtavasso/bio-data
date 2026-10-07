"""Run one saved R analysis (DESeq2, edgeR, limma, apeglm) in the pinned R image with a run_analysis.py receipt.

  ./bin/python .agents/skills/bio-research/scripts/r_analysis.py --receipt outputs/de-execution-r001.json \\
      --input inputs/counts.tsv --output outputs/de.tsv -- scripts/de.R inputs/counts.tsv outputs/de.tsv

The script must be saved under the question's scripts/. It runs as `Rscript --vanilla SCRIPT.R ARGS` in
`docker run --rm --network none` from the pinned image (containers/r-deseq2, default IMAGE below): the question
folder is mounted read-only at its own path, each declared output's directory writable, each declared input
outside the question folder read-only; the working directory is the caller's, so relative paths resolve
as they do on the host. `--native` uses a local Rscript instead (no container). The receipt has
the same fields as run_analysis.py (producer, code sha256, inputs sha256 and unchanged flag, outputs sha256 and
written flags, exit code, complete) plus the runtime (image id and digest, or the native Rscript), and the same
`analysis_executed` JSON line is printed with the stdout tail (stderr tail on failure).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_analysis import sha, tail  # noqa: E402  (the sibling helper: one hashing and tail implementation)

IMAGE = os.environ.get("BIO_R_IMAGE", "colloquy-r-deseq2:bioc3.23")


def question_root(script):
    """The folder holding the script's scripts/ directory (the question folder)."""
    parts = script.parts
    index = len(parts) - 1 - parts[::-1].index("scripts")
    return Path(*parts[:index])


def r_command(command):
    """`SCRIPT.R ARGS` or `Rscript SCRIPT.R ARGS` -> (script path, args)."""
    if command and command[0] == "--":
        command = command[1:]
    if command and Path(command[0]).name == "Rscript":
        command = command[1:]
    if not command or Path(command[0]).suffix.lower() != ".r":
        raise ValueError("give a saved R script (scripts/NAME.R) and its arguments, without shell syntax")
    script = Path(command[0]).resolve()
    if "scripts" not in script.parts or not script.is_file():
        raise ValueError("producer must be a saved local analysis under scripts/")
    return script, list(command[1:])


def image_identity(docker, image):
    """{"image", "image_id", "repo_digests"} from `docker image inspect`; raises when the image is absent."""
    result = subprocess.run([docker, "image", "inspect", "--format", "{{json .Id}} {{json .RepoDigests}}", image],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError(f"R image {image} is not available locally (build containers/r-deseq2): "
                         f"{result.stderr.strip()[-300:]}")
    image_id, digests = result.stdout.strip().split(" ", 1)
    return {"image": image, "image_id": json.loads(image_id), "repo_digests": json.loads(digests) or []}


def container_argv(docker, image, script, args, *, root, inputs, outputs, cwd):
    mounts = [("-v", f"{root}:{root}:ro")]
    for directory in sorted({str(p.parent) for p in outputs}):
        mounts.append(("-v", f"{directory}:{directory}:rw"))
    for path in inputs:
        if not path.is_relative_to(root):
            mounts.append(("-v", f"{path}:{path}:ro"))
    user = [f"--user={os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []
    return [docker, "run", "--rm", "--network", "none", *user, "-e", "HOME=/tmp",
            *[part for mount in mounts for part in mount], "-w", str(cwd),
            image, "Rscript", "--vanilla", str(script), *args]


def native_runtime(rscript):
    version = subprocess.run([rscript, "--version"], capture_output=True, text=True, check=False)
    return {"kind": "native", "rscript": rscript, "version": (version.stdout + version.stderr).strip()[:200]}


def run(receipt, outputs, command, inputs=(), *, tail_lines=20, native=False, docker="docker", image=IMAGE):
    script, args = r_command(list(command))
    root = question_root(script)
    outputs = [p.resolve() for p in outputs]
    if not outputs or len(set(outputs)) != len(outputs) or script in outputs:
        raise ValueError("declare distinct output files, separate from the producer")
    if any(not p.is_relative_to(root) for p in outputs):
        raise ValueError(f"outputs must be inside the question folder {root}")
    receipt = receipt.resolve()
    if receipt in outputs:
        raise ValueError("receipt cannot be an analysis output")
    inputs = [p.resolve() for p in inputs]
    if any(not p.is_file() or p in outputs or p == receipt for p in inputs):
        raise ValueError("declare existing input files, separate from the outputs and the receipt")
    cwd = Path.cwd().resolve()
    if native:
        rscript = shutil.which("Rscript")
        if not rscript:
            raise ValueError("--native needs Rscript on PATH")
        runtime = native_runtime(rscript)
        argv = [rscript, "--vanilla", str(script), *args]
    else:
        runtime = {"kind": "docker", **image_identity(docker, image)}
        # Run the inspected image by id, so the receipt names exactly what ran.
        argv = container_argv(docker, runtime["image_id"], script, args, root=root, inputs=inputs, outputs=outputs,
                              cwd=cwd)
        runtime["container_argv"] = argv
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive paths preserve failed invocations and prevent stale receipt reuse.
    with receipt.open("x") as saved:
        before = {str(p): (p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None
                  for p in outputs}
        code = sha(script)
        value = {"version": 1, "argv": ["Rscript", "--vanilla", str(script), *args], "cwd": str(cwd),
                 "producer": str(script), "code_sha256": code, "started": datetime.now(UTC).isoformat(),
                 "inputs": [{"path": str(p), "sha256": sha(p)} for p in inputs], "exit_code": None, "outputs": [],
                 "runtime": runtime}
        try:
            with receipt.with_suffix(receipt.suffix + ".stdout").open("xb") as out, \
                    receipt.with_suffix(receipt.suffix + ".stderr").open("xb") as err:
                value["exit_code"] = subprocess.run(argv, stdout=out, stderr=err, check=False).returncode
            value["code_unchanged"] = sha(script) == code
            value["inputs_unchanged"] = all(p.is_file() and sha(p) == i["sha256"] for p, i in zip(inputs, value["inputs"]))
            for path in outputs:
                exists = path.is_file()
                stat = path.stat() if exists else None
                value["outputs"].append({"path": str(path), "sha256": sha(path) if exists else None,
                    "written": bool(exists and before[str(path)] != (stat.st_ino, stat.st_mtime_ns, stat.st_size))})
        except OSError as error:
            value["error"] = str(error)
        value["finished"] = datetime.now(UTC).isoformat()
        value["complete"] = (value["exit_code"] == 0 and value.get("code_unchanged", False)
                             and value.get("inputs_unchanged", False)
                             and len(value["outputs"]) == len(outputs) and all(o["written"] for o in value["outputs"]))
        json.dump(value, saved, indent=2, allow_nan=False)
    event = {"event": "analysis_executed", "receipt": str(receipt), "sha256": sha(receipt),
             "exit_code": value["exit_code"], "complete": value["complete"],
             "outputs_written": sum(1 for o in value["outputs"] if o["written"]), "outputs_declared": len(outputs),
             "stdout_tail": tail(receipt.with_suffix(receipt.suffix + ".stdout"), tail_lines)}
    if value["exit_code"] != 0 or value.get("error"):
        event["stderr_tail"] = tail(receipt.with_suffix(receipt.suffix + ".stderr"), tail_lines)
        if value.get("error"):
            event["error"] = value["error"]
    elif not value["complete"]:
        event["incomplete_reason"] = ("producer changed during the run" if not value.get("code_unchanged")
                                      else "an input changed during the run" if not value.get("inputs_unchanged")
                                      else "a declared output was not written")
    print(json.dumps(event, allow_nan=False), flush=True)
    return 0 if value["complete"] else (value["exit_code"] or 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, action="append", required=True)
    parser.add_argument("--input", type=Path, action="append", default=[], help="input file the code reads (repeatable)")
    parser.add_argument("--tail", type=int, default=20, help="stdout lines to print (0 = none); stderr tail on failure")
    parser.add_argument("--native", action="store_true", help="use a local Rscript instead of the pinned image")
    parser.add_argument("--image", default=IMAGE, help=f"R image (default {IMAGE}; env BIO_R_IMAGE)")
    parser.add_argument("--docker", default=os.environ.get("BIO_R_DOCKER", "docker"), help="container engine")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        status = run(args.receipt, args.output, args.command, args.input, tail_lines=args.tail, native=args.native,
                     docker=args.docker, image=args.image)
    except ValueError as error:
        parser.error(str(error))
    raise SystemExit(status)
