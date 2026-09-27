"""Small read-only provider adapters; raw payloads and pagination survive normalization."""
import csv
import io
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit

from defusedxml import ElementTree as ET

from daw.models import Asset, Discovery, Page
from daw.transport import Transport
from daw.util import DawError, canonical, digest, now, read_json, safe_url

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/"
PMC = "https://pmc-oa-opendata.s3.amazonaws.com/"
ENA = "https://www.ebi.ac.uk/ena/portal/api/"
VERSION = "1"


class Sources:
    def __init__(self, ws, transport=None):
        self.ws = ws
        self.http = transport or Transport(ws)
        self.snapshots = []
        self.warnings = []

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
        if provider not in {"url", "geo", "pmc", "europepmc", "zenodo", "figshare", "ena", "biostudies", "encode", "chipatlas"}:
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
                assets = [self.ws.register_asset(bundle, provider, asset, source or sid)
                          for asset, source in records]
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


    @staticmethod
    def chipatlas_threshold(code):
        if code not in {"05", "10", "20"}:
            raise DawError("unsupported_chipatlas_threshold")
        return {"code": code, "max_q": 10.0 ** -int(code), "qvalue_scale": "minus_log10_Q",
                "minimum_qvalue": int(code), "higher_code_is_stricter": True,
                "validation_required": "confirm score schema and threshold nesting on exact files"}

    def discover(self, request: Discovery):
        run, _ = self.ws.start_run("discover", {"request": request.model_dump(), "adapter_version": VERSION})
        scope = self.ws.resource("scope", request.provider, run, request.model_dump())
        pages, ids, seen, cursor = [], [], set(), "*" if request.provider == "europepmc" else "1"
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
            if not complete and not warnings:
                warnings.append("page_budget_exhausted")
            if len(set(t for t in totals if t is not None)) > 1:
                warnings.append("reported_total_changed_during_enumeration")
            output = {"run": run, "scope": scope, "request": request.model_dump(), "pages": pages,
                      "resources": ids, "exhausted": complete, "warnings": warnings,
                      "retrieved_utc": now(), "adapter_version": VERSION}
            self.ws.finish_run(run, output)
            return output
        except DawError as e:
            output = {"run": run, "scope": scope, "request": request.model_dump(), "pages": pages,
                      "resources": ids, "exhausted": False, "warnings": warnings + [str(e)]}
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


def identify(reference, provider=None):
    if provider:
        return provider, reference
    if reference.startswith("zenodo:"):
        return "zenodo", reference.removeprefix("zenodo:")
    if reference.startswith("figshare:"):
        return "figshare", reference.removeprefix("figshare:")
    if reference.startswith("chipatlas:"):
        return "chipatlas", reference.removeprefix("chipatlas:")
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
