"""Deterministic synthetic demonstration; never presented as biological evidence."""
from datetime import datetime

from daw.curation import accept, add_assertion
from daw.inspectors import inspect_asset
from daw.models import AssertionInput, Curation, Evidence, Query
from daw.query import query, render_report
from daw.util import write_json


def sourced_settings(ws, asset_revision, settings, raw=None, methods=None, evidence_blob=None):
    """Register exact-source assertions for a reviewed deterministic recipe.

    Callers must provide an original evidence blob for real scientific inputs.
    Synthetic fixtures may use an explicitly marked source manifest.
    """
    from daw.curation import SEMANTIC_FIELDS
    raw = raw or settings
    if evidence_blob is None:
        raise ValueError("explicit original evidence blob required")
    subject = ws.asset(asset_revision)["resource_id"]
    assertions = {}
    for field in SEMANTIC_FIELDS & settings.keys():
        assertions[field] = add_assertion(ws, AssertionInput(subject=subject, field=field,
            raw_value=raw[field], value=settings[field], evidence=Evidence(blob=evidence_blob,
            locator="/" + field, method=(methods or {}).get(field, "source_mapping"))))
    return assertions


def build_demo(ws):
    import openpyxl
    directory = ws.root / "proposals/demo"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "synthetic-supplement.xlsx"
    if not path.exists():
        book = openpyxl.Workbook()
        book.properties.created = datetime(2020, 1, 1)
        book.properties.modified = datetime(2020, 1, 1)
        front = book.active
        front.title = "Overview"
        front.append(["SYNTHETIC DATA — not a public biological result"])
        front.append(["The auxiliary measurements are on a hidden sheet."])
        hidden = book.create_sheet("Auxiliary expression")
        hidden.sheet_state = "hidden"
        hidden.append(["A selected-only synthetic result table"])
        hidden.append([])
        hidden.append(["Feature", "log2FoldChange", "adjusted_p", "formula_uncached"])
        hidden.append(["PMP22", 1.5, 0.02, "=B4*2"])
        hidden.append(["SOX10", -0.75, 0.04, None])
        hidden.append(["NA", 0.25, 0.03, None])
        book.save(path)
        book.close()
    imported = ws.local_asset(path, "synthetic-demo")
    aid = imported["asset_revision"]
    inspection = inspect_asset(ws, aid)
    settings = {"feature_column": 1, "columns": {"log2FoldChange": 2, "adjusted_p": 3, "formula_uncached": 4},
                "namespace": "literal_source_identifier", "selection": "significant_only", "units": "log2 fold change",
                "contrast": {"numerator": "synthetic_treatment", "denominator": "synthetic_control", "effect_type": "published_log2_fold_change"}}
    source = {**settings, "synthetic": True, "selection_criterion": "fixture explicitly contains selected rows only"}
    source_path = directory / "synthetic-author-metadata.json"
    write_json(source_path, source)
    source_import = ws.local_asset(source_path, "synthetic-demo")
    assertions = sourced_settings(ws, aid, settings, evidence_blob=source_import["blob"])
    proposal = Curation(asset_revision=aid, kind="table", selector={"sheet": "Auxiliary expression", "start_row": 4, "end_row": 6},
                        settings=settings, assertions=assertions, limitations=["Synthetic demonstration; selected-only universe"])
    accepted = accept(ws, proposal)
    write_json(directory / "curation.json", proposal.model_dump())
    output = query(ws, Query(question_id="Synthetic pilot · hidden supplementary measurements", operator="contrast.published_lookup",
                            scope=[imported["bundle"]], feature="PMP22"))
    absent = query(ws, Query(question_id="Synthetic omission check · absent gene is unresolved", operator="contrast.published_lookup",
                            scope=[imported["bundle"]], feature="NOT_IN_SELECTED_TABLE"))
    return {"synthetic": True, "bundle": imported["bundle"], "inspection": inspection["inspection"],
            "curation": accepted["digest"], "query": output, "omission_check": absent,
            "report": render_report(ws, output["run"])["report"]}
