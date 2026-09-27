import json

from typer.testing import CliRunner

from daw.cli import app


def test_offline_cli_workflow_and_backup(tmp_path):
    runner = CliRunner()
    ws = tmp_path / "cli"
    initialized = runner.invoke(app, ["init", str(ws)])
    assert initialized.exit_code == 0
    assert json.loads(initialized.stdout)["catalog_version"] == 3
    demo = runner.invoke(app, ["-w", str(ws), "demo"])
    assert demo.exit_code == 0, demo.output
    result = json.loads(demo.stdout)
    assert result["synthetic"] and result["query"]["measurements"] == 3
    doctor = runner.invoke(app, ["-w", str(ws), "doctor"])
    assert doctor.exit_code == 0
    assert json.loads(doctor.stdout)["journal_mode"] == "delete"
    backup = tmp_path / "backup"
    assert runner.invoke(app, ["-w", str(ws), "backup", str(backup)]).exit_code == 0
    check = runner.invoke(app, ["restore-check", str(backup)])
    assert check.exit_code == 0 and json.loads(check.stdout)["ok"]
