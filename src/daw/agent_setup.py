"""Stage ordinary research tools and instructions for an isolated stock agent."""
import shutil
import subprocess
import sys
from pathlib import Path

from daw.util import DawError, file_hash


def copy_research_tools(trial, repository=None, skill_names=(), previous=None):
    repo = Path(repository) if repository else Path(__file__).resolve().parents[2]
    if not (repo / "src/daw/bio_cli.py").is_file() or not (repo / "AGENTS.md").is_file():
        raise DawError("development_checkout_required", "agent tool staging requires the bio-data source checkout")
    copied = {}
    files = [repo / p for p in ("AGENTS.md", "README.md", "pyproject.toml", "uv.lock")]
    for directory in ("src/daw", "contracts", "examples"):
        files += [p for p in (repo / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    files += [repo / "docs" / name for name in ("WORKFLOW.md", "V2.md", "V3.md", "SKILLS.md", "COMMUNITY.md")]
    for name in skill_names:
        files += [p for p in (repo / ".agents/skills" / name).rglob("*") if p.is_file()]
    for source in files:
        if not source.exists():
            continue
        if source.is_symlink():
            raise ValueError(f"project snapshot refuses symlink: {source}")
        destination = trial / source.relative_to(repo)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            raise ValueError(f"project destination refuses symlink: {destination}")
        if previous and destination.is_file() and file_hash(source) != file_hash(destination):
            backup = Path(previous) / destination.relative_to(trial)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(destination, backup)
        shutil.copyfile(source, destination)
        copied[str(destination.relative_to(trial))] = file_hash(destination)
    subprocess.run(["git", "init", "--quiet", str(trial)], check=True, capture_output=True)
    bin_dir = trial / "bin"
    bin_dir.mkdir(exist_ok=True)
    wrappers = {"bio": "from daw.bio_cli import main\nmain()\n",
                "python": f"import os, sys\nos.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n"}
    for name, body in wrappers.items():
        path = bin_dir / name
        path.write_text(f"#!{sys.executable}\nimport os, ssl, certifi\nos.environ.setdefault('SSL_CERT_FILE', certifi.where())\n"
                       f"ssl.create_default_context(cafile=os.environ['SSL_CERT_FILE'])\n{body}")
        path.chmod(0o755)
        copied[str(path.relative_to(trial))] = file_hash(path)
    return copied
