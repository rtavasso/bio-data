import os

import pytest

from daw.catalog import Workspace
from daw.curation import accept, add_assertion, register_reference
from daw.demo import sourced_settings
from daw.models import AssertionInput, Curation, Evidence


def pytest_collection_modifyitems(items):
    for item in items:
        if "live" in item.keywords and os.environ.get("DAW_LIVE") != "1":
            item.add_marker(pytest.mark.skip(reason="set DAW_LIVE=1 to enable live source integration"))


@pytest.fixture
def ws(tmp_path):
    workspace = Workspace.create(tmp_path / "workspace")
    workspace.budgets = workspace.budgets.model_copy(update={"reserve_bytes": 0, "reserve_fraction": 0.0})
    # Reopened and copied fixtures need the same test-only disk settings as workers.
    (workspace.root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0.0\n")
    yield workspace
    workspace.close()


@pytest.fixture
def curated(ws):
    def make(imported, kind="table", settings=None, selector=None, sample_map=None, reference=None):
        settings = settings or {"feature_column": 1, "columns": {"effect": 2}, "namespace": "literal", "selection": "complete_tested"}
        source = {**settings, "synthetic": True}
        if sample_map:
            source["sample_map"] = sample_map
        if reference:
            source["reference"] = reference
        blob = ws.put_json(source)
        assertions = sourced_settings(ws, imported["asset_revision"], settings, evidence_blob=blob)
        if sample_map:
            assertions["sample_map"] = add_assertion(ws, AssertionInput(subject=ws.asset(imported["asset_revision"])["resource_id"],
                field="sample_map", raw_value=sample_map, value=sample_map, evidence=Evidence(blob=blob, locator="/sample_map")))
        if reference:
            assertions["reference"] = add_assertion(ws, AssertionInput(subject=ws.asset(imported["asset_revision"])["resource_id"],
                field="reference", raw_value=reference, value=reference, evidence=Evidence(blob=blob, locator="/reference")))
        proposal = Curation(asset_revision=imported["asset_revision"], kind=kind, settings=settings,
                            selector=selector or {}, sample_map=sample_map or {}, reference=reference, assertions=assertions)
        result = accept(ws, proposal)
        return proposal, result
    return make


@pytest.fixture
def reference(ws):
    annotation = ws.put_bytes(b"synthetic annotation chr1 1000\n")
    evidence = ws.put_json({"assembly": "synthetic1", "chromosomes": {"chr1": 1000}})
    return register_reference(ws, {"assembly": "synthetic1", "species": "synthetic", "chromosomes": {"chr1": 1000},
        "annotation": {"source": "synthetic fixture", "release": "1", "blob": annotation},
        "namespaces": ["synthetic"], "aliases": {"1": "chr1"},
        "evidence": [{"blob": evidence, "locator": "/chromosomes"}]})["reference"]


@pytest.fixture(scope="session")
def demo_template(tmp_path_factory):
    """One synthetic demo commons per test session (built through ordinary board functions)."""
    from daw.commons.demo import build_demo
    root = tmp_path_factory.mktemp("demo") / "commons"
    return root, build_demo(root)


@pytest.fixture
def demo(demo_template, tmp_path):
    """A private writable copy of the demo commons and the identities of its records."""
    import shutil
    root, context = demo_template
    copy = tmp_path / "commons"
    shutil.copytree(root, copy, symlinks=True)
    return copy, {**context, "harness": str(copy / "demo-harness" / "hermes")}


@pytest.fixture
def demo_only(tmp_path):
    """Factory for a demo commons with only the named extensions ("module:function"), for tests whose
    expectations depend on exact record counts that other areas' demo extensions would change."""
    from daw.commons.demo import build_demo

    def make(*extensions):
        root = tmp_path / ("commons-" + str(len(list(tmp_path.glob("commons-*")))))
        context = build_demo(root, extensions=list(extensions))
        return root, {**context, "harness": str(root / "demo-harness" / "hermes")}
    return make
