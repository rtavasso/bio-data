"""Native-reference IGV Desktop packages, copied separately from immutable data."""
import shutil
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

from daw.models import Curation
from daw.operators import checked_region
from daw.query import plan_query
from daw.util import DawError, file_hash, read_json, write_json


def export_igv(ws, request, destination):
    if request.operator not in {"signal.interval_summary", "interval.overlap"}:
        raise DawError("igv_requires_native_interval_or_signal_query")
    destination = Path(destination).resolve()
    if destination.exists():
        raise DawError("export_destination_exists")
    if destination.is_relative_to(ws.root / "blobs"):
        raise DawError("export_cannot_modify_blob_store")
    plan = plan_query(ws, request)
    tracks = []
    for candidate in plan["candidates"]:
        if candidate["decision"]["status"] not in {"ready", "ready_with_limits"}:
            continue
        curation = Curation.model_validate(read_json(ws.blob_path(candidate["curation"])))
        chrom, start, end, reference = checked_region(ws, curation, request.region)
        asset = ws.asset(candidate["asset_revision"])
        suffix = Path(asset["body"]["name"]).suffix.lower()
        if suffix not in {".bw", ".bigwig", ".bed", ".narrowpeak", ".broadpeak"}:
            raise DawError("unsupported_igv_track_suffix")
        if file_hash(ws.blob_path(asset["blob"])) != asset["blob"]:
            raise DawError("integrity_failed")
        tracks.append({"asset_revision": asset["id"], "blob": asset["blob"], "curation": candidate["curation"],
                       "name": asset["body"]["name"], "path": asset["id"] + suffix,
                       "units": curation.settings.get("units"), "limitations": curation.limitations})
    if not tracks:
        raise DawError("no_eligible_igv_tracks")
    session = Element("Session", genome=reference["assembly"], locus=f"{chrom}:{start + 1}-{end}", version="3")
    resources = SubElement(session, "Resources")
    ws.check_disk(sum(ws.blob_path(t["blob"]).stat().st_size for t in tracks))
    destination.mkdir(parents=True)
    for track in tracks:
        shutil.copyfile(ws.blob_path(track["blob"]), destination / track["path"])
        SubElement(resources, "Resource", path=track["path"], name=track["name"])
    ElementTree(session).write(destination / "session.xml", encoding="utf-8", xml_declaration=True)
    manifest = {"reference": request.region.reference, "assembly": reference["assembly"],
                "internal_region": request.region.model_dump(), "igv_locus": session.attrib["locus"],
                "tracks": tracks, "plan": plan, "source_bytes_copied": True,
                "validation": "XML and source hashes verified; IGV Desktop GUI not exercised",
                "documentation": "https://igv.org/doc/desktop/UserGuide/sessions/"}
    write_json(destination / "manifest.json", manifest)
    return {"session": str(destination / "session.xml"), "manifest": str(destination / "manifest.json"), "tracks": len(tracks)}
