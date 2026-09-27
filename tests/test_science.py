import json

import pyarrow.parquet as pq
import pytest
from hypothesis import given, strategies as st

from daw.curation import capability
from daw.models import Query, Region
from daw.operators import contact_extract, interval_overlap, matrix_values, signal_summary
from daw.query import query
from daw.util import DawError


def test_half_open_boundaries_and_native_reference(ws, tmp_path, curated, reference):
    pytest.importorskip("bioframe")
    path = tmp_path / "peaks.bed"
    path.write_text("chr1\t10\t20\nchr1\t20\t30\n")
    imported = ws.local_asset(path)
    proposal, _ = curated(imported, "interval", {"native_coordinates": "0-based-half-open", "interval_schema": "bed3"}, reference=reference)
    request = Query(question_id="boundary", operator="interval.overlap", region=Region(chrom="chr1", start=19, end=20, reference=reference))
    result, state, _ = interval_overlap(ws, ws.asset(imported["asset_revision"]), proposal, request)
    assert state == "evaluated_detected" and len(result) == 1 and result[0]["start"] == 10
    request.region = Region(chrom="chr1", start=30, end=31, reference=reference)
    result, state, reason = interval_overlap(ws, ws.asset(imported["asset_revision"]), proposal, request)
    assert not result and state == "evaluated_not_detected" and "not_molecular_occupancy" in reason
    request.region = Region(chrom="chr1", start=10, end=15, reference="different-build")
    with pytest.raises(DawError, match="incompatible_reference"):
        interval_overlap(ws, ws.asset(imported["asset_revision"]), proposal, request)


@given(st.integers(min_value=1, max_value=10**8), st.integers(min_value=1, max_value=10000))
def test_one_based_coordinate_roundtrip(start, length):
    native_end = start + length - 1
    internal = (start - 1, native_end)
    assert internal[1] - internal[0] == length
    assert (internal[0] + 1, internal[1]) == (start, native_end)


def test_signal_exact_mean_coverage_missing_bases(ws, tmp_path, curated, reference):
    bigwig = pytest.importorskip("pyBigWig")
    path = tmp_path / "track.bw"
    with bigwig.open(str(path), "w") as bw:
        bw.addHeader([("chr1", 1000)])
        bw.addEntries(["chr1", "chr1"], [10, 20], ends=[15, 25], values=[2.0, 4.0])
    imported = ws.local_asset(path)
    proposal, _ = curated(imported, "signal", {"units": "RPM", "signal_missingness": "covered_bases_only"}, reference=reference)
    request = Query(question_id="signal", operator="signal.interval_summary", region=Region(chrom="chr1", start=10, end=30, reference=reference))
    rows, state, _ = signal_summary(ws, ws.asset(imported["asset_revision"]), proposal, request)
    assert rows[0]["value"] == 3.0 and rows[0]["covered_bases"] == 10
    assert rows[0]["coverage_fraction"] == 0.5 and rows[0]["requested_bases"] == 20
    assert state == "evaluated_detected"
    request.region = Region(chrom="chr1", start=30, end=40, reference=reference)
    rows, state, _ = signal_summary(ws, ws.asset(imported["asset_revision"]), proposal, request)
    assert rows[0]["value"] is None and state == "not_measurable"


def make_matrix(path):
    ad = pytest.importorskip("anndata")
    import numpy as np
    import pandas as pd
    from scipy import sparse
    matrix = ad.AnnData(sparse.csr_matrix(np.array([[0, 2], [3, 4], [1, 1]], dtype=float)),
                       obs=pd.DataFrame(index=["c1", "c2", "c3"]),
                       var=pd.DataFrame({"gene_symbol": ["DUP", "DUP"]}, index=["PMP22", "SOX10"]))
    matrix.raw = matrix.copy()
    matrix.write_h5ad(path)


def matrix_settings():
    return {"layer": "X", "namespace": "literal", "units": "UMI", "transform": "none", "matrix_semantics": "molecule_counts",
            "count_generating_assay": "synthetic UMI assay", "grouping": ["study", "donor", "sample"],
            "feature_presence": {"dataset1": ["PMP22", "SOX10"]}}


def sample_map():
    return {c: {"study": "study1", "donor": "donor1" if c != "c3" else "donor2", "sample": "s1" if c != "c3" else "s2",
                "dataset": "dataset1"} for c in ("c1", "c2", "c3")}


def test_matrix_zero_absent_feature_and_donor_grouping(ws, tmp_path, curated):
    path = tmp_path / "matrix.h5ad"
    make_matrix(path)
    imported = ws.local_asset(path)
    proposal, _ = curated(imported, "matrix", matrix_settings(), sample_map=sample_map())
    request = Query(question_id="matrix", operator="expression.feature_values", feature="PMP22")
    rows, state, _ = matrix_values(ws, ws.asset(imported["asset_revision"]), proposal, request)
    assert [r["value"] for r in rows] == [0.0, 3.0, 1.0] and state == "evaluated_detected"
    request.feature = "ABSENT"
    assert matrix_values(ws, ws.asset(imported["asset_revision"]), proposal, request)[1] == "not_measurable"
    request.feature, request.operator = "PMP22", "expression.pseudobulk_counts"
    rows, state, _ = matrix_values(ws, ws.asset(imported["asset_revision"]), proposal, request)
    assert [r["value"] for r in rows] == [3, 1] and [r["cell_count"] for r in rows] == [2, 1]
    assert len(rows) == 2  # three cells never become three independent donors


def test_raw_name_does_not_grant_counts_missing_presence_blocks_zero(ws, tmp_path, curated):
    path = tmp_path / "matrix.h5ad"
    make_matrix(path)
    imported = ws.local_asset(path)
    settings = matrix_settings()
    settings.update(layer="raw.X", units="log values", matrix_semantics="normalized", transform="log1p")
    settings.pop("feature_presence")
    proposal, _ = curated(imported, "matrix", settings, sample_map=sample_map())
    assert capability(proposal, "expression.pseudobulk_counts")["status"] == "blocked"
    assert capability(proposal, "promoter.tss_summary")["status"] == "not_supported"
    rows, state, _ = matrix_values(ws, ws.asset(imported["asset_revision"]), proposal,
        Query(question_id="presence", operator="expression.feature_values", feature="PMP22"))
    assert state == "unresolved" and all(r["value"] is None for r in rows)


def test_matrix_axis_map_mismatch(ws, tmp_path, curated):
    path = tmp_path / "matrix.h5ad"
    make_matrix(path)
    imported = ws.local_asset(path)
    mapping = sample_map()
    mapping["wrong_barcode"] = mapping.pop("c1")
    proposal, _ = curated(imported, "matrix", matrix_settings(), sample_map=mapping)
    with pytest.raises(DawError, match="cell_mapping_mismatch"):
        matrix_values(ws, ws.asset(imported["asset_revision"]), proposal,
                      Query(question_id="ordering", operator="expression.feature_values", feature="PMP22"))


def test_stable_feature_ids_preserve_duplicate_symbols(ws, tmp_path, curated):
    path = tmp_path / "matrix.h5ad"
    make_matrix(path)
    import anndata
    ad = anndata.read_h5ad(path)
    ad.var["stable_id"] = ["ENSG0001", "ENSG0002"]
    ad.var_names = ["DUP", "DUP"]
    ad.write_h5ad(path)
    imported = ws.local_asset(path)
    settings = {**matrix_settings(), "feature_id_column": "stable_id", "gene_symbol_column": "index",
                "feature_presence": {"dataset1": ["ENSG0001", "ENSG0002"]}}
    proposal, _ = curated(imported, "matrix", settings, sample_map=sample_map())
    request = Query(question_id="stable identity", operator="expression.feature_values", feature="ENSG0002")
    rows, state, _ = matrix_values(ws, ws.asset(imported["asset_revision"]), proposal, request)
    assert [r["value"] for r in rows] == [2.0, 4.0, 1.0]
    assert {r["gene_symbol"] for r in rows} == {"DUP"} and state == "evaluated_detected"
    request.feature = "DUP"
    assert matrix_values(ws, ws.asset(imported["asset_revision"]), proposal, request)[1] == "not_measurable"


def test_contact_resolution_balance_and_symmetric_counts(ws, tmp_path, curated, reference):
    cooler = pytest.importorskip("cooler")
    import pandas as pd
    path = tmp_path / "contact.cool"
    bins = pd.DataFrame({"chrom": ["chr1"] * 10, "start": list(range(0, 1000, 100)), "end": list(range(100, 1100, 100))})
    pixels = pd.DataFrame({"bin1_id": [0, 0, 1], "bin2_id": [0, 1, 1], "count": [1, 3, 2]})
    cooler.create_cooler(str(path), bins, pixels)
    imported = ws.local_asset(path)
    proposal, _ = curated(imported, "contact", {"resolution": 100, "balance": False}, reference=reference)
    request = Query(question_id="contacts", operator="contact.region_extract", region=Region(chrom="chr1", start=0, end=200, reference=reference))
    rows, state, _ = contact_extract(ws, ws.asset(imported["asset_revision"]), proposal, request)
    values = [r["value"] for r in rows if "value" in r]
    assert sum(values) == 6 and len(values) == 3 and state == "evaluated_detected"
    request.parameters["required_resolution"] = 50
    with pytest.raises(DawError, match="insufficient_contact_resolution"):
        contact_extract(ws, ws.asset(imported["asset_revision"]), proposal, request)
    request.parameters.clear()
    proposal.settings["balance"] = True
    with pytest.raises(DawError, match="missing_balancing_weights"):
        contact_extract(ws, ws.asset(imported["asset_revision"]), proposal, request)


def test_matrix_operator_worker_no_catalog_write(ws, tmp_path, curated):
    path = tmp_path / "matrix.h5ad"
    make_matrix(path)
    curated(ws.local_asset(path), "matrix", matrix_settings(), sample_map=sample_map())
    result = query(ws, Query(question_id="worker", operator="expression.feature_values", feature="PMP22"))
    assert result["measurements"] == 3
    rows = pq.read_table(ws.blob_path(result["artifacts"]["measurements.parquet"])).to_pylist()
    assert json.loads(rows[0]["details_json"])["value_state"] == "measured"


def test_matrix_market_paired_axes_and_release_mismatch(ws, tmp_path, curated):
    pytest.importorskip("scipy")
    path = tmp_path / "matrix.mtx"
    path.write_text("%%MatrixMarket matrix coordinate integer general\n2 3 5\n1 2 3\n1 3 1\n2 1 2\n2 2 4\n2 3 1\n")
    imported = ws.local_asset(path)
    settings = {**matrix_settings(), "orientation": "features_by_cells",
        "feature_ids": ws.put_json(["PMP22", "SOX10"]), "cell_ids": ws.put_json(["c1", "c2", "c3"]),
        "bundle_identity": {"matrix": "release1", "features": "release1", "cells": "release1"}}
    proposal, _ = curated(imported, "matrix", settings, sample_map=sample_map())
    request = Query(question_id="paired axes", operator="expression.feature_values", feature="PMP22")
    rows, state, _ = matrix_values(ws, ws.asset(imported["asset_revision"]), proposal, request)
    assert [r["value"] for r in rows] == [0, 3, 1] and state == "evaluated_detected"
    proposal.settings["bundle_identity"]["cells"] = "release2"
    with pytest.raises(DawError, match="matrix_bundle_release_mismatch"):
        matrix_values(ws, ws.asset(imported["asset_revision"]), proposal, request)
