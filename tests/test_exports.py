from xml.etree.ElementTree import parse

from daw.exports import export_igv
from daw.models import Query, Region


def test_igv_reference_coordinates_and_copied_bytes(ws, tmp_path, curated, reference):
    source = tmp_path / "peaks.bed"
    source.write_text("chr1\t10\t20\n")
    imported = ws.local_asset(source)
    curated(imported, "interval", {"interval_schema": "bed3", "native_coordinates": "0-based-half-open"}, reference=reference)
    request = Query(question_id="native", operator="interval.overlap", region=Region(chrom="chr1", start=10, end=20, reference=reference))
    destination = tmp_path / "export"
    result = export_igv(ws, request, destination)
    root = parse(result["session"]).getroot()
    assert root.attrib["locus"] == "chr1:11-20"
    track = destination / root.find("Resources/Resource").attrib["path"]
    assert track.read_bytes() == source.read_bytes()
    track.write_text("edited copy")
    assert ws.blob_path(imported["blob"]).read_bytes() == source.read_bytes()
