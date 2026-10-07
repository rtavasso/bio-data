"""Small read-only provider adapters; raw payloads and pagination survive normalization."""
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit

from defusedxml import ElementTree as ET

from daw.models import Asset, Discovery, Page
from daw.search import index_document
from daw.transport import Transport
from daw.util import DawError, canonical, digest, now, read_json, safe_url

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/"
PMC = "https://pmc-oa-opendata.s3.amazonaws.com/"
ENA = "https://www.ebi.ac.uk/ena/portal/api/"
PRIDE = "https://www.ebi.ac.uk/pride/ws/archive/v3/"
GTEX = "https://gtexportal.org/api/v2/"
CELLXGENE = "https://api.cellxgene.cziscience.com/curation/v1/"
VERSION = "1"
# Paragraph locator scheme for Europe PMC JATS full text; a change is a new parser version.
JATS_PARSER = "jats-paragraphs-v1"
TABLE_SUFFIXES = ("csv", "tsv", "txt", "xlsx", "xlsm")
MAX_LISTING_PAGES = 100


class Sources:
    def __init__(self, ws, transport=None):
        self.ws = ws
        self.http = transport or Transport(ws)
        self.snapshots = []
        self.warnings = []
        self._listings = {}

    def payload(self, url, kind="json", limit=16 * 2**20):
        receipt = self.http.fetch(url, expected=kind, limit=limit)
        self.snapshots.append(receipt["snapshot"])
        if receipt["outcome"] != "available_full":
            raise DawError(receipt["outcome"], f"source snapshot {receipt['snapshot']}: {receipt.get('reason')}")
        raw = self.ws.blob_path(receipt["blob"]).read_bytes()
        try:
            parsed = json.loads(raw) if kind == "json" else ET.fromstring(raw) if kind == "xml" else raw.decode("utf-8-sig")
        except (ValueError, ET.ParseError) as e:
            raise DawError("malformed_metadata", receipt["snapshot"]) from e
        return parsed, receipt["snapshot"], receipt["blob"]

    def resolve_geo(self, native, bundle):
        from daw.geo import resolve_geo
        return resolve_geo(self, native, bundle)

    def add(self, reference, provider=None):
        provider, native = identify(reference, provider)
        if provider not in {"url", "geo", "pmc", "europepmc", "zenodo", "figshare", "ena", "biostudies", "encode", "chipatlas",
                            "pride", "gtex", "cellxgene"}:
            raise DawError("unsupported_provider", provider)
        bundle = self.ws.resource("bundle", provider, native, {"reference": safe_url(reference) if "://" in reference else reference})
        run, _ = self.ws.start_run("resolve", {"provider": provider, "reference": native, "adapter_version": VERSION})
        assets, metadata = [], {}
        before = len(self.snapshots)
        try:
            if provider == "url":
                sid = self.ws.snapshot(safe_url(native), "listed", {"source": "explicit_user_reference"}, resource=bundle)
                assets = [self.ws.register_asset(bundle, provider, Asset(native_id=safe_url(native), url=native,
                           name=Path(urlsplit(native).path).name or "download"), sid)]
                self.snapshots.append(sid)
            else:
                method = getattr(self, "resolve_" + provider)
                records, sid, metadata = method(native, bundle)
                # A record is (asset, snapshot) or, for a derived metadata table, (asset, snapshot, blob).
                assets = [self.ws.register_asset(bundle, provider, record[0], record[1] or sid, *record[2:])
                          for record in records]
            result = {"bundle": bundle, "provider": provider, "reference": native, "assets": assets,
                      "snapshots": self.snapshots[before:], "metadata": metadata, "warnings": self.warnings,
                      "adapter_version": VERSION, "retrieved_utc": now(), "enumeration_complete": not self.warnings,
                      "outcome": "inventoried", "run": run}
            self.ws.finish_run(run, result)
        except (DawError, KeyError, TypeError, ValueError) as e:
            reason = str(e)
            # Keep the unresolved route as an explicit candidate, even with no file list.
            sid = self.snapshots[-1] if len(self.snapshots) > before else self.ws.snapshot(
                native, "unsupported_route", {"reason": reason}, resource=bundle)
            asset = Asset(native_id=native + ":unresolved_inventory", name="Unresolved source inventory",
                          access=e.reason if isinstance(e, DawError) and e.reason in {
                              "restricted", "not_found", "transient_failure", "over_budget", "removed_upstream"
                          } else "unsupported_route", metadata={"reason": reason, "route": native})
            assets.append(self.ws.register_asset(bundle, provider, asset, sid))
            result = {"bundle": bundle, "provider": provider, "reference": native, "assets": assets,
                      "snapshots": self.snapshots[before:], "outcome": "blocked", "reason": reason,
                      "enumeration_complete": False, "adapter_version": VERSION, "retrieved_utc": now(), "run": run}
            self.ws.finish_run(run, result, error=reason)
        return result

    def resolve_zenodo(self, native, bundle):
        if native.isdigit():
            url = f"https://zenodo.org/api/records/{native}"
        elif native.startswith("10."):
            data, _, _ = self.payload("https://zenodo.org/api/records?" + urlencode({"q": f'doi:"{native}" OR conceptdoi:"{native}"', "size": 10}))
            hits = data["hits"]["hits"]
            exact = [x for x in hits if x.get("doi") == native or x.get("conceptdoi") == native]
            if len(exact) != 1:
                raise DawError("ambiguous_record_version", "select an explicit record ID")
            url = exact[0]["links"]["self"]
        else:
            raise DawError("unsupported_reference")
        record, sid, _ = self.payload(url)
        version = str(record["id"])
        license_value = record.get("metadata", {}).get("license", "unknown")
        license_value = license_value.get("id", "unknown") if isinstance(license_value, dict) else str(license_value)
        assets = []
        for f in record.get("files", []):
            assets.append((Asset(native_id=f"{version}:{f.get('id', f['key'])}", name=f["key"], version=version,
                                 url=f["links"].get("self") or f["links"].get("download"), size=f.get("size"),
                                 checksum=f.get("checksum"), license=license_value,
                                 metadata={"conceptrecid": record.get("conceptrecid"), "record": version}), sid))
        return assets, sid, {"record": version, "schema_keys": sorted(record), "license": license_value}

    def resolve_figshare(self, native, bundle):
        match = re.fullmatch(r"(\d+)(?:/versions/(\d+))?", native)
        if not match:
            raise DawError("unsupported_reference", "use public article ID and optional /versions/N; DOI suffixes are not guessed")
        article, version = match.groups()
        root = f"https://api.figshare.com/v2/articles/{article}"
        current, sid, _ = self.payload(root + (f"/versions/{version}" if version else ""))
        observed_version = str(current["version"])
        if version is None:
            current, sid, _ = self.payload(root + f"/versions/{observed_version}")
        license_value = current.get("license", {}).get("name", "unknown")
        assets = []
        for f in current.get("files", []):
            md5 = f.get("computed_md5") or f.get("supplied_md5")
            assets.append((Asset(native_id=f"{article}:v{observed_version}:{f['id']}", name=f["name"],
                                 url=f.get("download_url"), size=f.get("size"), version=observed_version,
                                 checksum=f"md5:{md5}" if md5 else None, license=license_value,
                                 metadata={"is_link_only": f.get("is_link_only", False),
                                           "computed_md5": f.get("computed_md5"), "supplied_md5": f.get("supplied_md5")}), sid))
        return assets, sid, {"article": article, "version": observed_version, "schema_keys": sorted(current)}

    def resolve_europepmc(self, native, bundle):
        query = f"EXT_ID:{native}" if native.isdigit() else f'DOI:"{native}"' if native.startswith("10.") else f"PMCID:{native}"
        data, sid, _ = self.payload(EPMC + "search?" + urlencode({"query": query, "format": "json", "resultType": "core", "pageSize": 10}))
        results = data.get("resultList", {}).get("result", [])
        assets = []
        for index, item in enumerate(results):
            article = self.ws.resource("article", "europepmc", item.get("id", native), item)
            self.ws.link(bundle, article, "describes", sid, f"/resultList/result/{index}")
            pmcid = item.get("pmcid")
            if pmcid:
                # The XML is a file candidate; enumerating cloud media is a separate bounded route.
                assets.append((Asset(native_id=f"{pmcid}:jats", name=f"{pmcid}.xml", url=EPMC + pmcid + "/fullTextXML",
                                     metadata={"article": article}), sid))
                try:
                    extra, _, _ = self.resolve_pmc(pmcid, bundle)
                    assets.extend(extra)
                except DawError as e:
                    self.warnings.append(f"PMC Cloud route: {e}")
                    assets.append((Asset(native_id=f"{pmcid}:cloud_inventory", name="Unresolved PMC Cloud inventory",
                                         access="unsupported_route", metadata={"reason": str(e)}), self.snapshots[-1]))
        if not results:
            self.warnings.append("no article resolved in this exact query scope")
        return assets, sid, {"articles": len(results), "query": query, "schema_keys": sorted(data)}

    def resolve_pmc(self, native, bundle):
        if not re.fullmatch(r"PMC\d+(?:\.\d+)?", native):
            raise DawError("unsupported_reference", "expected PMCID or explicit article version")
        exact_version = "." in native
        params = {"list-type": "2", "prefix": native + ("/" if exact_version else "."), "delimiter": "/"}
        root, sid, _ = self.payload(PMC + "?" + urlencode(params), "xml")
        ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
        if root.findtext("s:IsTruncated", namespaces=ns) == "true":
            self.warnings.append("article-version prefix listing truncated")
        prefixes = [native + "/"] if exact_version else [x.text for x in root.findall("s:CommonPrefixes/s:Prefix", ns)]
        assets, versions = [], []
        for prefix in prefixes:
            listing, listing_sid, _ = self.payload(PMC + "?" + urlencode({"list-type": "2", "prefix": prefix}), "xml")
            if listing.findtext("s:IsTruncated", namespaces=ns) == "true":
                self.warnings.append(f"object listing truncated: {prefix}")
            contents = listing.findall("s:Contents", ns)
            metadata_keys = [node.findtext("s:Key", namespaces=ns) for node in contents
                             if (node.findtext("s:Key", namespaces=ns) or "").endswith(".json")]
            metadata = {}
            metadata_sid = listing_sid
            if len(metadata_keys) == 1:
                metadata, metadata_sid, _ = self.payload(PMC + quote(metadata_keys[0], safe="/"))
            versions.append({"prefix": prefix, "is_manuscript": metadata.get("is_manuscript"),
                             "is_retracted": metadata.get("is_retracted"), "metadata_snapshot": metadata_sid})
            returned = {}
            for field in ("xml_url", "pdf_url", "text_url", "media_urls"):
                urls = metadata.get(field, [])
                for url in urls if isinstance(urls, list) else [urls]:
                    if isinstance(url, str):
                        returned[urlsplit(url).path.lstrip("/")] = url
            for node in contents:
                key = node.findtext("s:Key", namespaces=ns)
                url = returned.get(key, PMC + quote(key, safe="/"))
                native_locator = url
                parsed = urlsplit(url)
                if parsed.scheme == "s3" and parsed.netloc == "pmc-oa-opendata":
                    url = PMC + parsed.path.lstrip("/") + ("?" + parsed.query if parsed.query else "")
                md5 = parse_qs(urlsplit(url).query).get("md5", [None])[0]
                assets.append((Asset(native_id=key, name=Path(key).name, url=url, version=prefix.rstrip("/"),
                                     size=int(node.findtext("s:Size", namespaces=ns)), checksum=f"md5:{md5}" if md5 else None,
                                     license=str(metadata.get("license_code", "unknown")),
                                     metadata={"article_version": prefix, "is_manuscript": metadata.get("is_manuscript"),
                                               "is_retracted": metadata.get("is_retracted"),
                                               "provider_locator": native_locator,
                                               "version_is_immutable": False}), metadata_sid))
        if not prefixes:
            self.warnings.append("no eligible PMC Cloud version returned; redistribution scope may differ")
        return assets, sid, {"versions": versions, "selected_policy": "inventory every returned version; do not equate latest with published"}

    def resolve_ena(self, native, bundle):
        fields = ["study_accession", "sample_accession", "experiment_accession", "run_accession",
                  "library_layout", "fastq_ftp", "fastq_md5", "fastq_bytes"]
        handshake, _, _ = self.payload(ENA + "returnFields?result=read_run&format=json")
        available = {f.get("columnId") for f in handshake}
        if not set(fields) <= available:
            raise DawError("schema_changed", f"missing ENA fields: {sorted(set(fields) - available)}")
        rows, sid, _ = self.payload(ENA + "filereport?" + urlencode({"accession": native, "result": "read_run",
                                                                     "format": "json", "fields": ",".join(fields)}))
        assets = []
        for i, row in enumerate(rows):
            exp = self.ws.resource("experiment", "insdc", row["experiment_accession"])
            sample = self.ws.resource("sample", "ena", row["sample_accession"])
            run = self.ws.resource("sequencing_run", "ena", row["run_accession"])
            self.ws.link(bundle, exp, "contains_experiment", sid, f"/{i}")
            self.ws.link(run, exp, "run_of", sid, f"/{i}/experiment_accession")
            self.ws.link(exp, sample, "assays", sid, f"/{i}/sample_accession")
            urls, sizes, checksums = [str(row.get(k, "")).split(";") for k in ("fastq_ftp", "fastq_bytes", "fastq_md5")]
            if len({len(urls), len(sizes), len(checksums)}) != 1:
                self.warnings.append(f"unequal ENA arrays at /{i}; no guessed file pairing")
                assets.append((Asset(native_id=row["run_accession"] + ":unpaired_files", name="Unresolved ENA file arrays",
                                     access="unsupported_route", metadata={"row": row}), sid))
                continue
            for url, size, md5 in zip(urls, sizes, checksums, strict=True):
                if not url:
                    continue
                url = "https://" + url if "://" not in url else url.replace("ftp://", "https://", 1)
                assets.append((Asset(native_id=row["run_accession"] + ":" + urlsplit(url).path, name=Path(urlsplit(url).path).name,
                                     url=url, size=int(size) if size else None, checksum="md5:" + md5 if md5 else None,
                                     raw=True, metadata={"experiment": exp, "run": run, "sample": sample,
                                                         "representation": "archive-derived FASTQ", "library_layout": row["library_layout"]}), sid))
        return assets, sid, {"rows": len(rows), "handshake_fields": fields, "raw_processing": "disabled"}

    def resolve_biostudies(self, native, bundle):
        base = f"https://www.ebi.ac.uk/biostudies/api/v1/studies/{quote(native, safe='')}"
        data, sid, _ = self.payload(base)
        info, _, _ = self.payload(base + "/info")
        locations = info.get("ftpLink") or info.get("httpLink") or info.get("filesPath")
        if isinstance(locations, str) and locations.startswith("ftp://"):
            locations = locations.replace("ftp://", "https://", 1)
        assets = []
        def walk(node, pointer=""):
            if isinstance(node, list):
                for i, child in enumerate(node):
                    walk(child, pointer + f"/{i}")
            elif isinstance(node, dict):
                files = node.get("files", [])
                def visit_files(value, locator):
                    if isinstance(value, list):
                        for i, child in enumerate(value):
                            visit_files(child, f"{locator}/{i}")
                    elif isinstance(value, dict):
                        name = value.get("path") or value.get("name")
                        if name:
                            url = value.get("url")
                            if not url and locations and str(locations).startswith("https://"):
                                url = urljoin(locations.rstrip("/") + "/", quote(name, safe="/"))
                            assets.append((Asset(native_id=native + ":" + name, name=name, url=url,
                                                 size=int(value["size"]) if value.get("size") else None,
                                                 selector={"metadata_pointer": locator}, metadata={"file": value}), sid))
                visit_files(files, pointer + "/files")
                for k, child in node.items():
                    if k != "files":
                        walk(child, pointer + "/" + k)
        walk(data)
        if not locations:
            self.warnings.append("file location metadata unresolved; file candidates retained")
        return assets, sid, {"schema_keys": sorted(data), "location_metadata": info}

    def resolve_encode(self, native, bundle):
        data, sid, _ = self.payload(f"https://www.encodeproject.org/{quote(native, safe='')}/?format=json")
        assets = []
        files = data.get("files", [data] if "File" in data.get("@type", []) else [])
        for f in files:
            fsid = sid
            if isinstance(f, str):
                f, fsid, _ = self.payload(urljoin("https://www.encodeproject.org", f) + "?format=json")
            href = f.get("href")
            status = f.get("status", "unknown")
            assets.append((Asset(native_id=f["accession"], name=Path(href).name if href else f["accession"],
                                 url=urljoin("https://www.encodeproject.org", href) if href else None,
                                 size=f.get("file_size"), checksum="md5:" + f["md5sum"] if f.get("md5sum") else None,
                                 raw=f.get("file_format") in {"fastq", "bam", "cram"},
                                 metadata={k: f.get(k) for k in ("assembly", "output_type", "status", "derived_from",
                                            "biological_replicates", "technical_replicates", "replicate", "audit", "no_file_available")}), fsid))
            if status not in {"released"}:
                self.warnings.append(f"{f['accession']}: non-released file retained but ineligible by default")
        # Preserve returned library/biosample lineage; resolve linked records in a bounded one-hop handshake.
        for i, rep in enumerate(data.get("replicates", [])):
            if isinstance(rep, str):
                rep, rsid, _ = self.payload(urljoin("https://www.encodeproject.org", rep) + "?format=json")
            else:
                rsid = sid
            entity = self.ws.resource("library", "encode", rep.get("uuid", f"{native}:rep:{i}"), rep)
            self.ws.link(bundle, entity, "contains_library", rsid, f"/replicates/{i}")
        return assets, sid, {"schema_keys": sorted(data), "experiment": data.get("accession"), "audit": data.get("audit")}

    def resolve_chipatlas(self, native, bundle):
        genomes, _, _ = self.payload("https://chip-atlas.org/data/list_of_genome.json")
        data, sid, _ = self.payload("https://chip-atlas.org/data/exp_metadata.json?" + urlencode({"expid": native}))
        assets = []
        # Only acquire links actually returned by the service; do not manufacture track paths.
        def walk(value, pointer=""):
            if isinstance(value, dict):
                for key, child in value.items():
                    walk(child, pointer + "/" + key)
            elif isinstance(value, list):
                for i, child in enumerate(value):
                    walk(child, pointer + f"/{i}")
            elif isinstance(value, str) and value.startswith(("https://", "http://")) and re.search(r"\.(bigWig|bw|bed|bed\.gz)(?:\?|$)", value, re.I):
                assets.append((Asset(native_id=native + ":" + pointer, name=Path(urlsplit(value).path).name, url=value,
                                     license="CC-BY-4.0", metadata={"experiment": native, "source_pointer": pointer,
                                     "threshold_semantics": "unresolved_documentation_conflict"}), sid))
        walk(data)
        if not assets and isinstance(data, list) and data:
            documentation, docs_sid, docs_blob = self.payload("https://github.com/inutano/chip-atlas/wiki", "html")
            if "/eachData/bw/" in documentation and "/eachData/bed" in documentation:
                experiment = self.ws.resource("experiment", "insdc", native)
                self.ws.link(bundle, experiment, "contains_experiment", sid, "/expid")
                for index, record in enumerate(data):
                    genome = record.get("genome")
                    if genome not in genomes or record.get("expid") != native or record.get("agClass") == "Bisulfite-Seq":
                        self.warnings.append("unsupported ChIP-Atlas record class/genome; no generic methylation track guessing")
                        continue
                    common = {"experiment": experiment, "genome": genome, "source_pointer": f"/{index}",
                              "source_metadata": record, "download_rule_snapshot": docs_sid, "download_rule_blob": docs_blob}
                    assets.append((Asset(native_id=f"{native}:{genome}:bw", name=native + ".bw",
                        url=f"https://chip-atlas.dbcls.jp/data/{genome}/eachData/bw/{native}.bw",
                        license="CC-BY-4.0", metadata={**common, "representation": "RPM coverage"}), sid))
                    for code in ("05", "10", "20"):
                        assets.append((Asset(native_id=f"{native}:{genome}:bed:{code}", name=f"{native}.{code}.bed",
                            url=f"https://chip-atlas.dbcls.jp/data/{genome}/eachData/bed{code}/{native}.{code}.bed",
                            license="CC-BY-4.0", metadata={**common, "threshold_code": code,
                            "threshold_semantics": "requires_file_level_verification"}), sid))
        if not assets:
            self.warnings.append("experiment metadata returned no native track links; explicit source-backed track locator required")
            assets.append((Asset(native_id=native + ":tracks", name="Unresolved ChIP-Atlas track locations",
                                 metadata={"experiment": native}, access="unsupported_route"), sid))
        return assets, sid, {"supported_genomes": genomes, "source_metadata": data,
                             "threshold_issue": "05/10/20 use -log10(Q); agent guide contradicts processing wiki; blocked until file fixture"}
    def listing(self, url, limit=64 * 2**20):
        """One snapshot per listing URL per invocation, so paging a client-side match costs one request."""
        if url not in self._listings:
            data, sid, _ = self.payload(url, limit=limit)
            self._listings[url] = (data, sid)
        return self._listings[url]

    def resolve_pride(self, native, bundle):
        if not re.fullmatch(r"PXD\d{6,}", native):
            raise DawError("unsupported_reference", "expected a PRIDE project accession (PXD…)")
        project, sid, _ = self.payload(PRIDE + f"projects/{native}")
        count, _, _ = self.payload(PRIDE + f"projects/{native}/files/count")
        if isinstance(count, bool) or not isinstance(count, int):
            self.warnings.append("PRIDE file count unavailable; listing completeness unknown")
            count = None
        assets, seen, page = [], set(), 0
        while page < MAX_LISTING_PAGES:
            rows, page_sid, _ = self.payload(PRIDE + f"projects/{native}/files?" + urlencode({"pageSize": 100, "page": page}))
            if not isinstance(rows, list):
                raise DawError("schema_changed", "PRIDE file listing is not a list")
            for i, f in enumerate(rows):
                if f["accession"] in seen:
                    self.warnings.append(f"duplicate PRIDE file record across pages: {f['accession']}")
                    continue
                seen.add(f["accession"])
                locations = {x.get("name"): x.get("value") for x in f.get("publicFileLocations") or [] if isinstance(x, dict)}
                ftp = locations.get("FTP Protocol") or ""
                checksum = str(f.get("checksum") or "").lower()
                algorithm = {32: "md5", 40: "sha1", 64: "sha256"}.get(len(checksum)) if re.fullmatch(r"[0-9a-f]+", checksum) else None
                category = (f.get("fileCategory") or {}).get("value")
                assets.append((Asset(native_id=f"{native}:{f['accession']}", name=f["fileName"],
                                     url=ftp.replace("ftp://", "https://", 1) if ftp.startswith("ftp://") else None,
                                     size=f.get("fileSizeBytes"), checksum=f"{algorithm}:{checksum}" if algorithm else None,
                                     raw=category == "RAW", selector={"metadata_pointer": f"page={page}/{i}"},
                                     metadata={"project": native, "file_accession": f["accession"], "category": category,
                                               "locations": locations, "provider_checksum": checksum or None,
                                               "publication_date": f.get("publicationDate"), "updated_date": f.get("updatedDate")}),
                               page_sid))
            page += 1
            if len(rows) < 100 or (count is not None and len(seen) >= count):
                break
        else:
            self.warnings.append("PRIDE file listing page budget exhausted")
        if count is not None and len(seen) != count:
            self.warnings.append(f"PRIDE reported {count} files; listed {len(seen)}")
        return assets, sid, {"title": project.get("title"), "reported_file_count": count, "listed_files": len(seen),
                             "schema_keys": sorted(project)}

    def resolve_gtex(self, native, bundle):
        dataset, _, tissue = native.partition("/")
        if not re.fullmatch(r"\w+", dataset) or (tissue and not re.fullmatch(r"\w+", tissue)):
            raise DawError("unsupported_reference", "use gtex:<datasetId>[/<tissueSiteDetailId>]; no dataset is assumed")
        datasets, sid, _ = self.payload(GTEX + "metadata/dataset")
        info = [d for d in datasets if isinstance(d, dict) and d.get("datasetId") == dataset]
        if len(info) != 1:
            raise DawError("not_found", f"datasetId {dataset} is not listed by GTEx metadata/dataset")
        tissues, tissue_sid, _ = self.payload(GTEX + "dataset/tissueSiteDetail?" + urlencode({"datasetId": dataset, "itemsPerPage": 250}))
        if (tissues.get("paging_info") or {}).get("numberOfPages", 1) > 1:
            self.warnings.append("tissue listing has more than one page; only the first was read")
        known = set()
        for i, t in enumerate(tissues.get("data", [])):
            known.add(t.get("tissueSiteDetailId"))
            rid = self.ws.resource("tissue_site", "gtex", f"{dataset}/{t.get('tissueSiteDetailId')}", t)
            self.ws.link(bundle, rid, "describes_tissue", tissue_sid, f"/data/{i}")
        if tissue and tissue not in known:
            raise DawError("not_found", f"tissueSiteDetailId {tissue} is not listed for {dataset}")
        rows, pages, snapshots, total, page = [], 1, [], None, 0
        while page < pages:
            if page >= MAX_LISTING_PAGES:
                self.warnings.append(f"sample listing truncated at {MAX_LISTING_PAGES} pages")
                break
            params = {"datasetId": dataset, "itemsPerPage": 250, "page": page} | ({"tissueSiteDetailId": tissue} if tissue else {})
            data, page_sid, _ = self.payload(GTEX + "dataset/sample?" + urlencode(params))
            snapshots.append(page_sid)
            paging = data.get("paging_info") or {}
            pages, total = paging.get("numberOfPages", 0), paging.get("totalNumberOfItems")
            rows.extend(data.get("data", []))
            page += 1
        if total is not None and len(rows) != total:
            self.warnings.append(f"GTEx reported {total} samples; read {len(rows)}")
        # Derived metadata table: the API pages remain the authority (snapshots); values are literal.
        columns = sorted({key for row in rows for key in row}, key=lambda k: (k != "sampleId", k))
        out = io.StringIO()
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        literal_na = False
        for row in rows:
            values = []
            for key in columns:
                value = row.get(key)
                literal_na |= value == "NA"
                values.append("NA" if value is None else canonical(value).decode() if isinstance(value, (dict, list)) else str(value))
            writer.writerow(values)
        if literal_na:
            self.warnings.append("a source value is the literal string NA, which is also the null token")
        name = f"{dataset}{'-' + tissue if tissue else ''}-samples.tsv"
        blob = self.ws.put_bytes(out.getvalue().encode(), "derived")
        asset = Asset(native_id=f"{native}:samples.tsv", name=name, version=dataset, access="available_full",
                      metadata={"conversion": "GTEx API v2 dataset/sample pages to TSV; columns are the union of returned keys",
                                "null_token": "NA", "nested_values": "canonical JSON", "source_snapshots": snapshots,
                                "rows": len(rows), "reported_total": total, "dataset": info[0], "tissue": tissue or None,
                                "sample_rows_are_not_donors": True})
        return [(asset, snapshots[0] if snapshots else sid, blob)], sid, {
            "dataset": info[0], "tissues": len(known), "samples": len(rows), "reported_samples": total,
            "data_files": "the portal API lists metadata only; data files need an explicit source-backed locator"}

    def resolve_cellxgene(self, native, bundle):
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", native):
            raise DawError("unsupported_reference", "use cellxgene:<collection UUID>")
        data, sid, _ = self.payload(CELLXGENE + f"collections/{native}")
        assets = []
        for i, ds in enumerate(data.get("datasets", [])):
            rid = self.ws.resource("dataset", "cellxgene", ds["dataset_id"], {k: ds.get(k) for k in (
                "dataset_id", "dataset_version_id", "title", "schema_version", "cell_count", "is_primary_data",
                "organism", "assay", "tissue", "disease", "suspension_type", "tombstone")})
            self.ws.link(bundle, rid, "contains_dataset", sid, f"/datasets/{i}")
            if ds.get("tombstone"):
                self.warnings.append(f"dataset {ds['dataset_id']} is tombstoned upstream; retained")
            for j, item in enumerate(ds.get("assets") or []):
                url, filetype = item.get("url"), item.get("filetype")
                assets.append((Asset(
                    native_id=f"{ds['dataset_version_id']}:{filetype}", version=ds.get("dataset_version_id"),
                    name=Path(urlsplit(url).path).name if url else f"{ds['dataset_id']}.{str(filetype).lower()}",
                    url=url, size=item.get("filesize"), selector={"metadata_pointer": f"/datasets/{i}/assets/{j}"},
                    metadata={"collection_id": native, "collection_version_id": data.get("collection_version_id"),
                              "dataset": rid, "dataset_id": ds["dataset_id"], "dataset_version_id": ds.get("dataset_version_id"),
                              "filetype": filetype, "schema_version": ds.get("schema_version"), "title": ds.get("title"),
                              "is_primary_data": ds.get("is_primary_data"),
                              "count_semantics": "not asserted by the listing; inspect X and raw layers",
                              **({"serialization": "R serialization; never deserialized"} if filetype == "RDS" else {})}), sid))
        if data.get("revising_in") or data.get("revision_of"):
            self.warnings.append("collection has a revision relationship; versions are not merged")
        return assets, sid, {"collection_version_id": data.get("collection_version_id"), "name": data.get("name"),
                             "doi": data.get("doi"), "revision_of": data.get("revision_of"), "published_at": data.get("published_at"),
                             "datasets": len(data.get("datasets", [])), "schema_keys": sorted(data)}

    def fulltext_routes(self, pmcid):
        """The full-text route ladder. Europe PMC's fullTextXML answered 18 cohort calls with HTTP 500 and the
        agents then wrote 13 fetchers of their own; the NCBI routes serve the same open-access article."""
        number = pmcid[3:]
        return [("europepmc", EPMC + pmcid + "/fullTextXML"),
                ("ncbi_efetch", f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={number}&retmode=xml"),
                ("ncbi_bioc", f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/{pmcid}/unicode")]

    def fulltext(self, reference):
        """Full text of one open-access article as immutable XML, a paragraph object with stable locators and
        search documents. Routes are tried in order (`fulltext_routes`) until one serves a parsable article;
        a stub body (an error page, a BioC "No result can be found" notice, an article set without an article)
        is recorded as that route's outcome and never kept as the source."""
        pmcid = reference.upper()
        if not re.fullmatch(r"PMC\d+", pmcid):
            raise DawError("unsupported_reference", "a PMCID is needed for full text")
        bundle = self.ws.resource("bundle", "europepmc", pmcid, {"reference": pmcid})
        run, _ = self.ws.start_run("fulltext", {"pmcid": pmcid, "adapter_version": VERSION, "parser": JATS_PARSER})
        before = len(self.snapshots)
        routes, output = [], None
        for route, url in self.fulltext_routes(pmcid):
            try:
                root, sid, blob = self.payload(url, "xml")
                article, paragraphs = article_paragraphs(root)
                if not paragraphs:
                    raise DawError("no_full_text", f"{route} served no article paragraphs (snapshot {sid})")
                node = next((e for e in article.iter() if local_tag(e) == "article-title"), None)
                title = " ".join("".join(node.itertext()).split()) if node is not None else pmcid
                provider = "europepmc" if route == "europepmc" else "ncbi"
                aid = self.ws.register_asset(bundle, provider, Asset(
                    native_id=f"{pmcid}:jats", name=f"{pmcid}.xml", url=url, access="available_full",
                    metadata={"article": pmcid, "parser": JATS_PARSER, "route": route}), sid, blob)
                record = {"kind": "jats_paragraphs", "parser": JATS_PARSER, "pmcid": pmcid, "title": title, "route": route,
                          "asset_revision": aid, "source_blob": blob, "source_snapshot": sid, "paragraphs": paragraphs,
                          "locators": "element path with 1-based same-tag sibling indexes; body paragraphs are relative to "
                                      "<body>, others start at abstract/back/floats-group; BioC routes use passage[N]"}
                obj = self.ws.put_json(record)
                abstract = " ".join(p["text"] for p in paragraphs if p["locator"].startswith("abstract"))
                # Keyed by asset revision: a changed upstream representation leaves older documents historical.
                index_document(self.ws, key=f"fulltext:{aid}", family="data", subject=aid, record_id=obj, title=title,
                               summary=(abstract or " ".join(p["text"] for p in paragraphs[:3]))[:2000], body_blob=obj,
                               detail="\n".join(f"[{p['locator']}] {p['text']}" for p in paragraphs),
                               provider=provider, format="jats", level=2)
                for p in paragraphs:
                    index_document(self.ws, key=f"fulltext:{aid}#{p['locator']}", family="data", subject=aid,
                                   record_id=p["locator"], title=f"{title} — {p['section'] or p['locator']}",
                                   summary=p["text"][:2000], body_blob=obj, detail=p["text"], provider=provider,
                                   format="jats-paragraph", level=2)
                routes.append({"route": route, "outcome": "available_full"})
                output = {"pmcid": pmcid, "outcome": "available_full", "route": route, "routes": routes, "asset_revision": aid,
                          "source_blob": blob, "snapshot": sid, "paragraphs_blob": obj, "paragraphs": len(paragraphs),
                          "title": title, "parser": JATS_PARSER, "run": run, "warnings": [],
                          "next": "bio data search TEXT --paragraphs returns paragraph locators in record_id"}
                self.ws.finish_run(run, output)
                break
            except DawError as e:
                routes.append({"route": route, "outcome": e.reason, "reason": str(e)})
        if output is None:
            last = routes[-1] if routes else {"outcome": "unsupported_route", "reason": "no route"}
            output = {"pmcid": pmcid, "outcome": last["outcome"], "reason": last["reason"], "routes": routes,
                      "snapshots": self.snapshots[before:], "run": run,
                      "note": "every route failed; not_found/no_full_text mean these services served no full text for "
                              "this ID, not that the article lacks it. Record the gap with bio work gap and cite this run."}
            self.ws.finish_run(run, output, error=last["reason"])
        return output

    def supplementary(self, reference, *, max_files=10, max_bytes=256 * 2**20, max_asset_bytes=64 * 2**20, isolated=True):
        """List supplementary files, fetch tables within budgets, inspect them with the safe readers, keep a receipt.

        Listing uses the PMC Cloud inventory; when it has no candidate files the Europe PMC
        supplementaryFiles ZIP is the route. Formulas and macros are never evaluated; formats
        without a safe reader are listed and skipped, not fetched.
        """
        from daw.inspectors import extract_members, inspect_asset
        pmcid = reference.upper()
        if not re.fullmatch(r"PMC\d+(?:\.\d+)?", pmcid) or not 1 <= max_files <= 200 or max_bytes < 1 or max_asset_bytes < 1:
            raise DawError("unsupported_reference", "a PMCID and positive budgets are required")
        base = pmcid.split(".")[0]
        budgets = {"max_files": max_files, "max_bytes": max_bytes, "max_asset_bytes": max_asset_bytes}
        run, _ = self.ws.start_run("supplementary", {"pmcid": pmcid, "budgets": budgets, "adapter_version": VERSION})
        original = self.ws.budgets
        self.ws.budgets = original.model_copy(update={
            "asset_bytes": min(original.asset_bytes or max_asset_bytes, max_asset_bytes),
            "bundle_bytes": min(original.bundle_bytes or max_bytes, max_bytes)})
        candidates, fetched, tables, skipped, route = [], [], [], [], "pmc_cloud"
        try:
            listing = self.add(pmcid, "pmc")
            for aid in listing["assets"]:
                body = self.ws.asset(aid)["body"]
                if body["metadata"].get("article_version") and not body["name"].upper().startswith(base + "."):
                    candidates.append(aid)
            if not candidates:
                route = "europepmc_zip"
                bundle = self.ws.resource("bundle", "europepmc", base, {"reference": base})
                url = EPMC + base + "/supplementaryFiles"
                sid = self.ws.snapshot(url, "listed", {"source": "Europe PMC supplementaryFiles route (one ZIP per article)",
                                                       "pmc_cloud_outcome": listing["outcome"]}, resource=bundle)
                candidates = [self.ws.register_asset(bundle, "europepmc", Asset(
                    native_id=f"{base}:supplementaryFiles", name=f"{base}_SupplementaryFiles.zip", url=url,
                    metadata={"article": base, "route": "europepmc_zip"}), sid)]
            selected = []
            for aid in candidates:
                name = self.ws.asset(aid)["body"]["name"]
                suffix = name.lower().rsplit(".", 1)[-1]
                if suffix not in TABLE_SUFFIXES and suffix != "zip":
                    skipped.append({"asset_revision": aid, "name": name, "reason": "no_safe_table_reader"})
                elif len(selected) >= max_files:
                    skipped.append({"asset_revision": aid, "name": name, "reason": "file_budget"})
                else:
                    selected.append(aid)
            for aid in selected:
                result = self.http.acquire(aid)
                fetched.append({k: result.get(k) for k in ("asset_revision", "previous_revision", "outcome", "snapshot",
                                                          "blob", "bytes", "reason", "reused")})
                if result["outcome"] != "available_full":
                    continue
                current = result["asset_revision"]
                inspection = inspect_asset(self.ws, current, isolated)
                if inspection.get("kind") == "archive":
                    members = [self.ws.asset(c)["body"]["name"] for c in inspection.get("listed_child_assets", [])]
                    wanted = [m for m in members if m.lower().rsplit(".", 1)[-1] in TABLE_SUFFIXES]
                    skipped.extend({"member": m, "parent": current, "reason": "no_safe_table_reader"}
                                   for m in members if m not in wanted)
                    room = max(0, max_files - len(tables))
                    skipped.extend({"member": m, "parent": current, "reason": "file_budget"} for m in wanted[room:])
                    try:
                        children = extract_members(self.ws, current, wanted[:room]) if wanted[:room] else []
                    except DawError as e:
                        skipped.append({"parent": current, "reason": e.reason, "detail": e.detail})
                        children = []
                    for child in children:
                        tables.append(table_summary(child["member"], inspect_asset(self.ws, child["asset_revision"], isolated)))
                else:
                    tables.append(table_summary(self.ws.asset(current)["body"]["name"], inspection))
            receipt = {"pmcid": pmcid, "route": route, "listing_run": listing.get("run"), "budgets": budgets,
                       "candidates": candidates, "fetched": fetched, "tables": tables, "skipped": skipped,
                       "requests": self.http.requests, "transferred_bytes": self.http.transferred,
                       "policy": "tables read with the safe readers; formulas and macros are not evaluated; "
                                 "downloaded code is never executed", "adapter_version": VERSION, "retrieved_utc": now()}
            receipt_blob = self.ws.put_json(receipt)
            output = {**receipt, "receipt_blob": receipt_blob, "run": run}
            self.ws.finish_run(run, output)
            return output
        except DawError as e:
            output = {"pmcid": pmcid, "route": route, "outcome": e.reason, "reason": str(e), "fetched": fetched,
                      "tables": tables, "run": run}
            self.ws.finish_run(run, output, error=str(e))
            return output
        finally:
            self.ws.budgets = original


    @staticmethod
    def chipatlas_threshold(code):
        if code not in {"05", "10", "20"}:
            raise DawError("unsupported_chipatlas_threshold")
        return {"code": code, "max_q": 10.0 ** -int(code), "qvalue_scale": "minus_log10_Q",
                "minimum_qvalue": int(code), "higher_code_is_stricter": True,
                "validation_required": "confirm score schema and threshold nesting on exact files"}

    def discover(self, request: Discovery, *, cursor=None, prior_resources=()):
        run, _ = self.ws.start_run("discover", {"request": request.model_dump(), "adapter_version": VERSION,
            "start_cursor": cursor, "prior_resources": list(prior_resources)})
        scope = self.ws.resource("scope", request.provider, run, request.model_dump())
        pages, ids, seen = [], list(prior_resources), set()
        cursor = cursor or ("*" if request.provider == "europepmc" else "1")
        totals, complete, warnings = [], False, []
        try:
            for _ in range(request.max_pages):
                if cursor in seen:
                    warnings.append("repeated_cursor")
                    break
                seen.add(cursor)
                page = self.page(request, cursor)
                pages.append(page.model_dump())
                totals.append(page.reported_total)
                for item in page.items:
                    native = str(item.get("id") or item.get("accession") or item.get("srx") or digest(item))
                    rid = self.ws.resource("discovery_hit", request.provider, native, item)
                    self.ws.link(scope, rid, "discovered", page.source_snapshot_id, native)
                    if rid not in ids:
                        ids.append(rid)
                warnings.extend(page.warnings)
                if page.exhausted:
                    complete = True
                    break
                if not page.next_cursor:
                    # Some Europe PMC final pages omit nextCursorMark entirely.
                    # Accept that terminator only when unique recovered records
                    # account for the reported scope, never from a short page alone.
                    if page.reported_total is not None and len(ids) == page.reported_total and len(set(totals)) == 1:
                        complete = True
                        break
                    warnings.append("missing_continuation_without_exhaustion")
                    break
                cursor = page.next_cursor
                if cursor in seen:
                    warnings.append("repeated_cursor")
                    cursor = None
                    break
            if not complete and not warnings:
                warnings.append("page_budget_exhausted")
            if len(set(t for t in totals if t is not None)) > 1:
                warnings.append("reported_total_changed_during_enumeration")
            output = {"run": run, "scope": scope, "request": request.model_dump(), "pages": pages,
                      "resources": ids, "exhausted": complete, "warnings": warnings,
                      "retrieved_utc": now(), "adapter_version": VERSION,
                      "next_cursor": None if complete or not pages or not pages[-1].get("next_cursor") else cursor}
            self.ws.finish_run(run, output)
            return output
        except DawError as e:
            output = {"run": run, "scope": scope, "request": request.model_dump(), "pages": pages,
                      "resources": ids, "exhausted": False, "warnings": warnings + [str(e)], "next_cursor": cursor}
            self.ws.finish_run(run, output, str(e))
            return output

    def page(self, request, cursor):
        if request.provider == "europepmc":
            data, sid, _ = self.payload(EPMC + "search?" + urlencode({"query": request.query, "format": "json",
                "resultType": "core", "cursorMark": cursor, "pageSize": request.page_size}))
            items = data.get("resultList", {}).get("result", [])
            nxt = data.get("nextCursorMark")
            # The API omits the continuation for a one-page complete result.
            exhausted = not items or (not nxt and data.get("hitCount") == len(items))
            return Page(items=items, next_cursor=nxt, exhausted=exhausted,
                        reported_total=data.get("hitCount"), source_snapshot_id=sid)
        if request.provider == "zenodo":
            url = cursor if cursor.startswith("https://") else "https://zenodo.org/api/records?" + urlencode({
                "q": request.query, "size": request.page_size, "page": cursor})
            data, sid, _ = self.payload(url)
            nxt = data.get("links", {}).get("next")
            total = data["hits"].get("total")
            return Page(items=data["hits"]["hits"], next_cursor=nxt, exhausted=not nxt,
                        reported_total=total.get("value") if isinstance(total, dict) else total, source_snapshot_id=sid)
        if request.provider == "encode":
            url = "https://www.encodeproject.org/search/?" + urlencode({"searchTerm": request.query, "type": "Experiment",
                "format": "json", "limit": request.page_size, "from": (int(cursor) - 1) * request.page_size})
            data, sid, _ = self.payload(url)
            total = data.get("total")
            exhausted = not data.get("@graph") or (total is not None and int(cursor) * request.page_size >= total)
            return Page(items=data.get("@graph", []), next_cursor=None if exhausted else str(int(cursor) + 1),
                        exhausted=exhausted, reported_total=total, source_snapshot_id=sid)
        if request.provider == "chipatlas":
            cache = self.ws.one("SELECT blob,id FROM snapshot WHERE locator=? AND outcome='available_full' ORDER BY retrieved DESC LIMIT 1",
                                ("https://chip-atlas.org/data/ExperimentList.json",))
            if cache:
                data, sid = read_json(self.ws.blob_path(cache["blob"])), cache["id"]
            else:
                data, sid, _ = self.payload("https://chip-atlas.org/data/ExperimentList.json", limit=self.ws.budgets.asset_bytes)
            rows = data if isinstance(data, list) else data.get("data", [])
            matches = [x for x in rows if request.query.casefold() in canonical(x).decode().casefold()]
            start = (int(cursor) - 1) * request.page_size
            selected = matches[start:start + request.page_size]
            selected = [x if isinstance(x, dict) else {"id": str(x[0]), "fields": x} for x in selected]
            end = start + request.page_size >= len(matches)
            return Page(items=selected, next_cursor=None if end else str(int(cursor) + 1), exhausted=end,
                        reported_total=len(matches), source_snapshot_id=sid,
                        warnings=["search scope is the saved experiment-list snapshot"])
        if request.provider == "pride":
            items, sid, _ = self.payload(PRIDE + "search/projects?" + urlencode({
                "keyword": request.query, "pageSize": request.page_size, "page": int(cursor) - 1}))
            if not isinstance(items, list):
                raise DawError("schema_changed", "PRIDE search did not return a list")
            # The total is only a response header; a short page is the terminator.
            exhausted = len(items) < request.page_size
            return Page(items=items, next_cursor=None if exhausted else str(int(cursor) + 1), exhausted=exhausted,
                        reported_total=None, source_snapshot_id=sid)
        if request.provider in {"cellxgene", "gtex"}:
            if request.provider == "cellxgene":
                data, sid = self.listing(CELLXGENE + "collections")
                rows = [{"id": x.get("collection_id"), "name": x.get("name"), "doi": x.get("doi"),
                         "collection_version_id": x.get("collection_version_id"), "published_at": x.get("published_at"),
                         "revised_at": x.get("revised_at"), "datasets": len(x.get("datasets") or []),
                         "dataset_titles": [d.get("title") for d in (x.get("datasets") or [])][:50], "source_pointer": f"/{i}"}
                        for i, x in enumerate(data) if request.query.casefold() in canonical(x).decode().casefold()]
                scope = "search scope is the full public collection listing; literal case-insensitive match"
            else:
                dataset, _, text = request.query.strip().partition(" ")
                data, sid = self.listing(GTEX + "dataset/tissueSiteDetail?" + urlencode({"datasetId": dataset, "itemsPerPage": 250}))
                if not isinstance(data, dict) or not data.get("data"):
                    raise DawError("unsupported_reference", "start a GTEx query with an explicit datasetId, e.g. 'gtex_v10 nerve'")
                rows = [{"id": f"{dataset}/{t.get('tissueSiteDetailId')}", "record": t, "source_pointer": f"/data/{i}"}
                        for i, t in enumerate(data["data"]) if text.strip().casefold() in canonical(t).decode().casefold()]
                scope = f"search scope is the {dataset} tissue-site listing; literal case-insensitive match"
            start = (int(cursor) - 1) * request.page_size
            end = start + request.page_size >= len(rows)
            return Page(items=rows[start:start + request.page_size], next_cursor=None if end else str(int(cursor) + 1),
                        exhausted=end, reported_total=len(rows), source_snapshot_id=sid, warnings=[scope])
        raise DawError("unsupported_provider")

    def jats_links(self, aid):
        asset = self.ws.asset(aid)
        root = ET.fromstring(self.ws.blob_path(asset["blob"]).read_bytes())
        bundle = self.ws.bundle_for(asset)
        base = asset["body"].get("url") or ""
        assets, links = [], []
        for index, element in enumerate(root.iter()):
            tag = element.tag.rsplit("}", 1)[-1]
            href = element.attrib.get("{http://www.w3.org/1999/xlink}href")
            locator = f"element[{index}]/{tag}"
            if href:
                url = urljoin(base, href)
                link = self.ws.resource("reference", "jats", url, {"label": " ".join(element.itertext())[:500]})
                self.ws.link(bundle, link, "references", asset["snapshot_id"], locator)
                links.append({"url": safe_url(url), "locator": locator, "tag": tag})
                if tag in {"supplementary-material", "media"}:
                    # Relative media in EPMC XML has no reliable media base. Cloud uses a true object base.
                    resolved = bool(urlsplit(href).scheme) or base.startswith(PMC)
                    a = Asset(native_id=f"{aid}:{locator}", name=Path(urlsplit(href).path).name,
                              url=url if resolved else None, selector={"jats_element": locator, "parent_blob": asset["blob"]},
                              metadata={"original_href": href, "relative_base_resolved": resolved})
                    assets.append(self.ws.register_asset(bundle, "jats", a, asset["snapshot_id"]))
            if tag == "table":
                lines = []
                for row in element.iter("tr"):
                    lines.append([" ".join(c.itertext()).strip() for c in row if c.tag in {"th", "td"}])
                if lines:
                    out = io.StringIO()
                    csv.writer(out, delimiter="\t", lineterminator="\n").writerows(lines)
                    sha = self.ws.put_bytes(out.getvalue().encode(), "derived")
                    a = Asset(native_id=f"{aid}:{locator}", name=f"inline-table-{index}.tsv", access="available_full",
                              selector={"parent_blob": asset["blob"], "jats_element": locator},
                              metadata={"conversion": "XML text content to TSV; spans require explicit curation"})
                    assets.append(self.ws.register_asset(bundle, "jats", a, asset["snapshot_id"], sha, previous=aid))
        return {"assets": assets, "links": links}


def local_tag(element):
    return element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""


def jats_paragraphs(root):
    """Every <p> of a JATS article with a stable locator, its section title, text and text SHA-256.

    A locator is the element path with 1-based indexes among same-tag siblings
    (`sec[2]/p[3]`). Body paragraphs are relative to <body>; abstract, back matter and
    floats keep their container (`abstract[1]/p[1]`, `back/ack[1]/p[1]`). Nested
    paragraphs belong to their outer <p>. Text is whitespace-normalised, otherwise literal.
    """
    found = []

    def walk(element, path, section):
        counts = {}
        for child in element:
            tag = local_tag(child)
            if not tag:
                continue
            counts[tag] = counts.get(tag, 0) + 1
            step = f"{path}/{tag}[{counts[tag]}]" if path else f"{tag}[{counts[tag]}]"
            if tag == "p":
                text = " ".join("".join(child.itertext()).split())
                if text:
                    found.append({"locator": step, "section": section,
                                  "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text})
                continue
            walk(child, step, heading(child) or section if tag in {"sec", "app", "ack", "boxed-text"} else section)

    def heading(element):
        title = next((c for c in element if local_tag(c) == "title"), None)
        return " ".join("".join(title.itertext()).split()) if title is not None else ""

    meta = next((e for e in root.iter() if local_tag(e) == "article-meta"), None)
    if meta is not None:
        for count, abstract in enumerate((c for c in meta if local_tag(c) == "abstract"), 1):
            walk(abstract, f"abstract[{count}]", heading(abstract) or "Abstract")
    for container in ("body", "back", "floats-group"):
        node = next((c for c in root if local_tag(c) == container), None)
        if node is not None:
            walk(node, "" if container == "body" else container, "")
    return found


def article_paragraphs(root):
    """(article element, paragraphs) for a JATS <article>, an efetch <pmc-articleset>, or a BioC <collection>.
    Anything else (an HTML error page parsed as XML, a notice element) yields no paragraphs."""
    tag = local_tag(root)
    if tag == "article":
        return root, jats_paragraphs(root)
    if tag == "pmc-articleset":
        article = next((c for c in root if local_tag(c) == "article"), None)
        return (article, jats_paragraphs(article)) if article is not None else (root, [])
    if tag == "collection":
        return root, bioc_paragraphs(root)
    return root, []


def bioc_paragraphs(root):
    """BioC passages as paragraphs: locator passage[N], section from the section_type/type infons."""
    found = []
    for n, passage in enumerate((e for e in root.iter() if local_tag(e) == "passage"), 1):
        infons = {i.get("key"): "".join(i.itertext()).strip() for i in passage if local_tag(i) == "infon"}
        if infons.get("type", "").lower() in {"title", "front", "ref"}:
            continue
        node = next((c for c in passage if local_tag(c) == "text"), None)
        text = " ".join("".join(node.itertext()).split()) if node is not None else ""
        if text:
            found.append({"locator": f"passage[{n}]", "section": infons.get("section_type") or infons.get("type") or "",
                          "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text})
    return found


def table_summary(name, inspection):
    """Compact extraction receipt for one inspected supplementary table; the inspection blob is the full record."""
    summary = {"name": name, "asset_revision": inspection.get("asset_revision"), "inspection": inspection.get("inspection"),
               "inspection_blob": inspection.get("manifest_blob"), "status": inspection.get("status"),
               "kind": inspection.get("kind"), "reason": inspection.get("reason")}
    if inspection.get("kind") == "workbook":
        summary["sheets"] = [{"name": s["name"], "rows": s["rows"], "columns": s["columns"], "formulas": len(s["formulas"]),
                              "complete": s["complete"]} for s in inspection.get("sheets", [])]
        summary["formula_policy"] = inspection.get("formula_policy")
    elif inspection.get("kind") == "delimited":
        summary.update(rows_scanned=inspection.get("rows_scanned"), column_counts=inspection.get("column_counts"),
                       complete=inspection.get("complete"))
    return summary

def identify(reference, provider=None):
    if provider:
        return provider, reference
    if reference.startswith("zenodo:"):
        return "zenodo", reference.removeprefix("zenodo:")
    if reference.startswith("figshare:"):
        return "figshare", reference.removeprefix("figshare:")
    if reference.startswith("chipatlas:"):
        return "chipatlas", reference.removeprefix("chipatlas:")
    for prefix in ("cellxgene", "gtex", "pride"):
        if reference.startswith(prefix + ":"):
            return prefix, reference.removeprefix(prefix + ":")
    if re.fullmatch(r"PXD\d{6,}", reference):
        return "pride", reference
    if re.fullmatch(r"GSE\d+", reference):
        return "geo", reference
    if re.fullmatch(r"PMC\d+(?:\.\d+)?", reference):
        return "pmc", reference
    if re.fullmatch(r"(?:[SED]R[APRSX]\d+|PRJ[EDN][AB]\d+)", reference):
        return "ena", reference
    if reference.startswith("ENC"):
        return "encode", reference
    if reference.startswith(("E-MTAB-", "S-BSST")):
        return "biostudies", reference
    if reference.startswith("10.") or reference.isdigit():
        return "europepmc", reference
    if reference.startswith(("https://", "http://")):
        parts = urlsplit(reference)
        if parts.hostname == "zenodo.org" and re.fullmatch(r"/records?/\d+/?", parts.path):
            return "zenodo", parts.path.rstrip("/").rsplit("/", 1)[-1]
        return "url", reference
    raise DawError("unsupported_reference", reference)
