"""M1.9 source adapters: PRIDE, GTEx, CZ cellxgene, Europe PMC full text, supplementary tables.

Offline: every response is a recorded shape served by httpx.MockTransport. Live checks
(`DAW_LIVE=1`) hit the real services and need actual receipts.
"""
import io
import json

import httpx
import pytest

from daw.adapters import Sources, identify, jats_paragraphs
from daw.models import Discovery
from daw.search import search
from daw.transport import Transport
from daw.util import DawError, read_json


def sources(ws, handler):
    return Sources(ws, Transport(ws, http_transport=httpx.MockTransport(handler), sleep=lambda _: None))


def pride_file(i, category="RESULT", checksum=""):
    return {"projectAccessions": ["PXD000001"], "accession": f"{i:064x}", "checksum": checksum,
            "fileCategory": {"@type": "CvParam", "value": category},
            "publicFileLocations": [{"name": "FTP Protocol", "value": f"ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2012/03/PXD000001/f{i}.mztab"},
                                    {"name": "Aspera Protocol", "value": f"prd_ascp@fasp.ebi.ac.uk:pride/f{i}.mztab"}],
            "fileSizeBytes": 100 + i, "fileName": f"f{i}.mztab", "publicationDate": "2012-03-07T00:00:00.000+00:00"}


def test_identify_new_providers():
    assert identify("PXD000001") == ("pride", "PXD000001")
    assert identify("gtex:gtex_v10/Nerve_Tibial") == ("gtex", "gtex_v10/Nerve_Tibial")
    assert identify("cellxgene:af893e86-8e9f-41f1-a474-ef05359b1fb7")[0] == "cellxgene"


def test_pride_project_files_paginate_with_receipts_and_checksums(ws):
    files = [pride_file(i, "RAW" if i == 0 else "RESULT", "a" * 40 if i == 1 else "") for i in range(150)]

    def handler(request):
        path = request.url.path
        if path.endswith("/files/count"):
            return httpx.Response(200, content=b"150", headers={"content-type": "application/json"})
        if path.endswith("/files"):
            page = int(request.url.params["page"])
            return httpx.Response(200, json=files[page * 100:(page + 1) * 100])
        return httpx.Response(200, json={"accession": "PXD000001", "title": "TMT spikes", "unknown": {"kept": True}})
    result = sources(ws, handler).add("PXD000001")
    assert result["outcome"] == "inventoried" and result["enumeration_complete"]
    assert len(result["assets"]) == 150 and result["metadata"]["reported_file_count"] == 150
    bodies = [ws.asset(a)["body"] for a in result["assets"]]
    raw = next(b for b in bodies if b["name"] == "f0.mztab")
    assert raw["raw"] and raw["url"].startswith("https://ftp.pride.ebi.ac.uk/")
    assert next(b for b in bodies if b["name"] == "f1.mztab")["checksum"] == "sha1:" + "a" * 40
    assert next(b for b in bodies if b["name"] == "f2.mztab")["checksum"] is None
    # Each asset points at the page snapshot that listed it; raw project JSON survives untouched.
    assert len({ws.asset(a)["snapshot_id"] for a in result["assets"]}) == 2
    snapshot = ws.one("SELECT blob FROM snapshot WHERE id=?", (result["snapshots"][0],))
    assert read_json(ws.blob_path(snapshot["blob"]))["unknown"] == {"kept": True}


def test_pride_count_mismatch_is_a_warning_not_completion(ws):
    def handler(request):
        if request.url.path.endswith("/files/count"):
            return httpx.Response(200, json=3)
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[pride_file(1)])
        return httpx.Response(200, json={"accession": "PXD000002"})
    result = sources(ws, handler).add("PXD000002")
    assert not result["enumeration_complete"] and "PRIDE reported 3 files; listed 1" in result["warnings"]


def test_pride_discovery_short_page_terminates(ws):
    result = sources(ws, lambda r: httpx.Response(200, json=[{"accession": "PXD070596", "title": "yeast"}])).discover(
        Discovery(provider="pride", query="schwann", page_size=5))
    assert result["exhausted"] and len(result["resources"]) == 1


def gtex_handler(samples, datasets=("gtex_v8", "gtex_v10")):
    def handler(request):
        path = request.url.path
        if path.endswith("/metadata/dataset"):
            return httpx.Response(200, json=[{"datasetId": d, "genomeBuild": "GRCh38/hg38"} for d in datasets])
        if path.endswith("/tissueSiteDetail"):
            return httpx.Response(200, json={"data": [{"tissueSiteDetailId": "Nerve_Tibial", "tissueSite": "Nerve"},
                                                      {"tissueSiteDetailId": "Whole_Blood", "tissueSite": "Blood"}],
                                             "paging_info": {"numberOfPages": 1, "page": 0, "totalNumberOfItems": 2}})
        page = int(request.url.params["page"])
        chunk = samples[page * 250:(page + 1) * 250]
        return httpx.Response(200, json={"data": chunk, "paging_info": {
            "numberOfPages": (len(samples) + 249) // 250, "page": page, "maxItemsPerPage": 250, "totalNumberOfItems": len(samples)}})
    return handler


def test_gtex_samples_become_a_literal_metadata_table(ws):
    samples = [{"sampleId": f"GTEX-{i}", "subjectId": f"GTEX-S{i // 2}", "rin": None if i == 0 else 7.1,
                "pathologyNotesCategories": {}, "tissueSiteDetailId": "Nerve_Tibial"} for i in range(260)]
    result = sources(ws, gtex_handler(samples)).add("gtex:gtex_v10/Nerve_Tibial")
    assert result["outcome"] == "inventoried" and result["metadata"]["samples"] == 260
    tissues = ws.rows("SELECT native_id FROM resource WHERE kind='tissue_site' ORDER BY native_id")
    assert [t["native_id"] for t in tissues] == ["gtex_v10/Nerve_Tibial", "gtex_v10/Whole_Blood"]
    asset = ws.asset(result["assets"][0])
    assert asset["access"] == "available_full" and len(asset["body"]["metadata"]["source_snapshots"]) == 2
    lines = ws.blob_path(asset["blob"]).read_text().splitlines()
    assert lines[0].split("\t")[0] == "sampleId" and len(lines) == 261
    header = lines[0].split("\t")
    first = dict(zip(header, lines[1].split("\t"), strict=True))
    assert first["rin"] == "NA" and first["pathologyNotesCategories"] == "{}"
    assert asset["body"]["metadata"]["sample_rows_are_not_donors"]


def test_gtex_never_assumes_a_dataset(ws):
    blocked = sources(ws, gtex_handler([])).add("gtex:gtex_v99")
    assert blocked["outcome"] == "blocked" and "not listed" in blocked["reason"]
    with pytest.raises(DawError, match="unsupported_reference"):
        sources(ws, gtex_handler([])).resolve_gtex("gtex v10", None)


def test_gtex_discovery_scope_is_explicit(ws):
    result = sources(ws, gtex_handler([])).discover(Discovery(provider="gtex", query="gtex_v10 nerve"))
    hit = ws.one("SELECT native_id FROM resource WHERE id=?", (result["resources"][0],))
    assert result["exhausted"] and hit["native_id"] == "gtex_v10/Nerve_Tibial"
    assert any("tissue-site listing" in w for w in result["warnings"])


COLLECTION = "af893e86-8e9f-41f1-a474-ef05359b1fb7"


def cellxgene_handler(request):
    if request.url.path.endswith("/collections"):
        return httpx.Response(200, json=[{"collection_id": COLLECTION, "name": "Human retina atlas", "datasets": [{"title": "Fovea"}]},
                                         {"collection_id": "00000000-0000-0000-0000-000000000000", "name": "Mouse lung", "datasets": []}])
    return httpx.Response(200, json={"collection_id": COLLECTION, "collection_version_id": "c1", "name": "Human retina atlas",
        "datasets": [{"dataset_id": "d1", "dataset_version_id": "v1", "title": "Fovea", "schema_version": "5.2.0",
                      "assets": [{"filetype": "H5AD", "filesize": 1433774383, "url": "https://datasets.cellxgene.cziscience.com/v1.h5ad"},
                                 {"filetype": "RDS", "filesize": 10, "url": "https://datasets.cellxgene.cziscience.com/v1.rds"}]}]})


def test_cellxgene_collection_assets_keep_versions_and_never_load_r(ws):
    result = sources(ws, cellxgene_handler).add("cellxgene:" + COLLECTION)
    bodies = {ws.asset(a)["body"]["name"]: ws.asset(a)["body"] for a in result["assets"]}
    assert set(bodies) == {"v1.h5ad", "v1.rds"} and bodies["v1.h5ad"]["version"] == "v1"
    assert bodies["v1.rds"]["metadata"]["serialization"].startswith("R serialization; never")
    assert "not asserted" in bodies["v1.h5ad"]["metadata"]["count_semantics"]
    assert ws.one("SELECT id FROM resource WHERE kind='dataset' AND provider='cellxgene' AND native_id='d1'")


def test_cellxgene_discovery_is_literal_over_one_listing_snapshot(ws):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return cellxgene_handler(request)
    result = sources(ws, handler).discover(Discovery(provider="cellxgene", query="retina", page_size=1, max_pages=3))
    assert len(result["resources"]) == 1 and result["exhausted"] and len(calls) == 1
    body = json.loads(ws.one("SELECT body FROM resource WHERE id=?", (result["resources"][0],))["body"])
    assert body["id"] == COLLECTION and body["source_pointer"] == "/0"


JATS = b"""<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta>
<title-group><article-title>Schwann cell <italic>Pmp22</italic> dosage</article-title></title-group>
<abstract><p>Myelin  protein dosage matters.</p></abstract>
<abstract abstract-type="summary"><title>Author Summary</title><p>Plain summary.</p></abstract>
</article-meta></front>
<body><p>Lead paragraph.</p>
<sec><title>Introduction</title><p>Intro one with CO<sub>2</sub>.</p><p>Intro two.</p></sec>
<sec><title>Results</title><p>Result one.</p><sec><title>Knockdown</title><p>Nested <bold>knockdown</bold> counts.</p></sec>
<p>Result two.</p><supplementary-material><caption><p>Table S1 counts.</p></caption>
<media xlink:href="table_s1.xlsx"/></supplementary-material></sec></body>
<back><ack><p>Thanks.</p></ack></back></article>"""


def test_jats_paragraph_locators_are_stable_and_hashed():
    from defusedxml import ElementTree as ET
    paragraphs = {p["locator"]: p for p in jats_paragraphs(ET.fromstring(JATS))}
    assert list(paragraphs) == ["abstract[1]/p[1]", "abstract[2]/p[1]", "p[1]", "sec[1]/p[1]", "sec[1]/p[2]",
                                "sec[2]/p[1]", "sec[2]/sec[1]/p[1]", "sec[2]/p[2]",
                                "sec[2]/supplementary-material[1]/caption[1]/p[1]", "back/ack[1]/p[1]"]
    assert paragraphs["sec[1]/p[1]"]["text"] == "Intro one with CO2." and paragraphs["sec[1]/p[1]"]["section"] == "Introduction"
    assert paragraphs["abstract[1]/p[1]"]["text"] == "Myelin protein dosage matters."
    assert paragraphs["abstract[2]/p[1]"]["section"] == "Author Summary"
    assert paragraphs["sec[2]/sec[1]/p[1]"]["section"] == "Knockdown"
    import hashlib
    assert paragraphs["p[1]"]["sha256"] == hashlib.sha256(b"Lead paragraph.").hexdigest()


def test_fulltext_is_immutable_object_plus_paragraph_search(ws):
    result = sources(ws, lambda r: httpx.Response(200, content=JATS)).fulltext("pmc123")
    assert result["outcome"] == "available_full" and result["paragraphs"] == 10
    asset = ws.asset(result["asset_revision"])
    assert asset["blob"] == result["source_blob"] and asset["body"]["native_id"] == "PMC123:jats"
    record = read_json(ws.blob_path(result["paragraphs_blob"]))
    assert record["parser"] == "jats-paragraphs-v1" and record["source_blob"] == result["source_blob"]
    hits = search(ws, "knockdown counts", format="jats-paragraph")
    assert hits["items"][0]["record_id"] == "sec[2]/sec[1]/p[1]" and hits["items"][0]["body_blob"] == result["paragraphs_blob"]
    assert search(ws, "Pmp22", format="jats")["total"] == 1
    # Re-fetching identical bytes reuses the revision; nothing is duplicated.
    again = sources(ws, lambda r: httpx.Response(200, content=JATS)).fulltext("PMC123")
    assert again["asset_revision"] == result["asset_revision"]
    assert search(ws, "knockdown counts", format="jats-paragraph")["total"] == 1


def test_fulltext_absent_is_recorded_as_not_found(ws):
    result = sources(ws, lambda r: httpx.Response(404, content=b"<error/>")).fulltext("PMC9")
    assert result["outcome"] == "not_found" and result["snapshots"]
    assert ws.one("SELECT state FROM run WHERE id=?", (result["run"],))["state"] == "failed"


def workbook_bytes():
    import openpyxl
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["gene", "count", "double"])
    sheet.append(["Pmp22", 10, "=B2*2"])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def cloud_listing(keys):
    contents = "".join(f"<Contents><Key>{k}</Key><Size>{s}</Size></Contents>" for k, s in keys)
    return (f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>false</IsTruncated>'
            f"{contents}</ListBucketResult>").encode()


def test_supplementary_tables_fetched_inspected_and_receipted(ws):
    xlsx, csv_bytes = workbook_bytes(), b"gene,count\nPmp22,10\n"
    objects = {"PMC5.1/PMC5.1.xml": b"<article/>", "PMC5.1/s1.xlsx": xlsx, "PMC5.1/s2.csv": csv_bytes,
               "PMC5.1/s3.tif": b"II*\x00", "PMC5.1/s4.tsv": b"a\tb\n"}

    def handler(request):
        if request.url.path == "/" and "delimiter" in request.url.params:
            return httpx.Response(200, content=b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                                  b"<IsTruncated>false</IsTruncated><CommonPrefixes><Prefix>PMC5.1/</Prefix></CommonPrefixes></ListBucketResult>")
        if request.url.path == "/":
            return httpx.Response(200, content=cloud_listing((k, len(v)) for k, v in objects.items()))
        return httpx.Response(200, content=objects[request.url.path.lstrip("/")])
    result = sources(ws, handler).supplementary("PMC5", max_files=2, isolated=False)
    assert result["route"] == "pmc_cloud"
    tables = {t["name"]: t for t in result["tables"]}
    assert set(tables) == {"s1.xlsx", "s2.csv"}
    sheet = tables["s1.xlsx"]["sheets"][0]
    assert sheet["formulas"] == 1 and tables["s1.xlsx"]["formula_policy"].startswith("not evaluated")
    inspection = read_json(ws.blob_path(tables["s1.xlsx"]["inspection_blob"]))
    formula = inspection["sheets"][0]["formulas"][0]
    assert formula["formula"] == "=B2*2" and formula["cache_resolved"] is False
    assert tables["s2.csv"]["rows_scanned"] == 2
    reasons = {s["name"]: s["reason"] for s in result["skipped"] if "name" in s}
    assert reasons == {"s3.tif": "no_safe_table_reader", "s4.tsv": "file_budget"}
    assert all(f["outcome"] == "available_full" and f["snapshot"] for f in result["fetched"])
    assert read_json(ws.blob_path(result["receipt_blob"]))["tables"] == result["tables"]
    assert ws.one("SELECT state FROM run WHERE id=?", (result["run"],))["state"] == "succeeded"


def test_supplementary_zip_fallback_extracts_only_tables_within_budget(ws):
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("counts.tsv", "gene\tcount\nPmp22\t10\n")
        z.writestr("macro.xlsm", workbook_bytes())
        z.writestr("figure.pdf", b"%PDF-1.4")
        z.writestr("run.py", "print('never executed')\n")

    def handler(request):
        if "pmc-oa-opendata" in request.url.host:
            return httpx.Response(200, content=b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                                  b"<IsTruncated>false</IsTruncated></ListBucketResult>")
        assert request.url.path.endswith("/PMC7/supplementaryFiles")
        return httpx.Response(200, content=buffer.getvalue())
    result = sources(ws, handler).supplementary("PMC7", isolated=False)
    assert result["route"] == "europepmc_zip"
    assert {t["name"] for t in result["tables"]} == {"counts.tsv", "macro.xlsm"}
    assert {s["member"] for s in result["skipped"] if "member" in s} == {"figure.pdf", "run.py"}
    over = sources(ws, handler).supplementary("PMC7", max_asset_bytes=10, isolated=False)
    assert over["fetched"][0]["outcome"] == "over_budget" and over["tables"] == []


@pytest.mark.live
def test_live_new_adapters_receipts(ws):
    source = Sources(ws)
    try:
        pride = source.add("PXD000001")
        assert pride["outcome"] == "inventoried" and pride["assets"]
        text = source.fulltext("PMC3257301")
        assert text["outcome"] == "available_full" and text["paragraphs"] > 20
        cellxgene = source.discover(Discovery(provider="cellxgene", query="retina", page_size=5))
        assert cellxgene["resources"]
        gtex = source.discover(Discovery(provider="gtex", query="gtex_v8 nerve"))
        assert gtex["resources"]
    finally:
        source.http.close()
