"""Workspaces and tenancy (M7.4): several commons served from one process.

A commons is one board plus one library. A multi-tenant host runs one commons per
organisation, each mounted at `/c/<tenant>/` as its own application: its own root
(board, library, agent checkouts, runs), accounts and `secrets/session.key`,
`sandbox.toml`, `commons.toml` rate limits and login limits. Nothing is shared
between tenants except the process and the built web app: every request is
answered by the tenant application whose settings name exactly one root, session
cookies are signed per root and scoped to the tenant's path, and module caches are
keyed by root. Federation between tenants is never a shared database; a tenant
reads another's work only as an exported snapshot imported read-only.

`tenants.toml`:

    [host]
    static_dir = "/app/web/dist"        # optional; default COLLOQUY_WEB_DIST or web/dist

    [tenants.lab-a]
    root = "/commons/lab-a"             # an initialized commons (bio community init); relative to this file
    title = "Lab A"                     # optional, shown on the host index
    login = { attempts = 10, window_seconds = 300 }   # optional override of the commons' [login]
    read = "private"                    # optional override of the commons' [access] read (spec v2 V9)

Tenants are always served in accounts mode (people log in with tokens). Each tenant enforces its own read policy
(`daw.commons.access`); the host's aggregate health and index never disclose a non-public tenant's board sequence
or title.
"""
import html
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from daw.util import DawError

NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
TENANT_KEYS = {"root", "title", "login", "read"}
HOST_KEYS = {"static_dir"}


@dataclass(frozen=True)
class Tenant:
    name: str
    root: Path
    title: str = ""
    login: dict = field(default_factory=dict)
    read: str | None = None

    @property
    def base(self):
        return f"/c/{self.name}/"


@dataclass(frozen=True)
class HostConfig:
    tenants: tuple
    static_dir: Path | None = None


def load(path):
    """Parse and validate tenants.toml: known keys only, distinct non-nested initialized roots."""
    path = Path(path).expanduser().resolve()
    try:
        raw = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise DawError("invalid_tenants_config", str(e)) from e
    unknown = set(raw) - {"host", "tenants"}
    host = raw.get("host", {})
    if unknown or not isinstance(host, dict) or set(host) - HOST_KEYS:
        raise DawError("invalid_tenants_config", "top-level tables are [host] (static_dir) and [tenants.<name>]")
    entries = raw.get("tenants")
    if not isinstance(entries, dict) or not entries:
        raise DawError("invalid_tenants_config", "declare at least one [tenants.<name>] table")
    tenants = []
    for name, entry in entries.items():
        if not NAME.fullmatch(name):
            raise DawError("invalid_tenant_name", f"{name!r}: lowercase letters, digits and inner '-' (max 63)")
        if not isinstance(entry, dict) or set(entry) - TENANT_KEYS or not isinstance(entry.get("root"), str):
            raise DawError("invalid_tenants_config", f"tenant {name}: root (required), title, login and read only")
        if not isinstance(entry.get("login", {}), dict) or not isinstance(entry.get("title", ""), str):
            raise DawError("invalid_tenants_config", f"tenant {name}: login is a table and title a string")
        root = (path.parent / Path(entry["root"]).expanduser()).resolve()
        if not (root / "board.sqlite").is_file():
            raise DawError("community_not_initialized", f"tenant {name}: {root} (create it with bio community init)")
        read = entry.get("read")
        if read is not None:
            from daw.commons.access import policy
            policy(root, read)  # validated here: public | members | private
        tenants.append(Tenant(name, root, entry.get("title", ""), dict(entry.get("login", {})), read))
    for i, one in enumerate(tenants):
        for other in tenants[i + 1:]:
            if one.root.is_relative_to(other.root) or other.root.is_relative_to(one.root):
                raise DawError("tenant_roots_overlap", f"{one.name} and {other.name} must not share or nest roots")
    static = host.get("static_dir")
    return HostConfig(tuple(tenants), (path.parent / static).resolve() if static else None)


def tenant_policy(tenant):
    """The tenant's read policy: its tenants.toml override, else its commons.toml [access] read."""
    from daw.commons.access import policy
    return policy(tenant.root, tenant.read)


def index_page(config):
    def label(tenant):
        read = tenant_policy(tenant)
        # A members-only or private tenant is listed by its configured name only, with its policy.
        shown = html.escape(tenant.title if read == "public" and tenant.title else tenant.name)
        return shown if read == "public" else f"{shown} <em>({html.escape(read)})</em>"
    items = "".join(f'<li><a href="{html.escape(t.base)}">{label(t)}</a> '
                    f'<code>{html.escape(t.name)}</code></li>' for t in config.tenants)
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            "content=\"width=device-width, initial-scale=1\"><title>Colloquy commons</title><style>"
            "body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
            "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}a{color:#9cf}}</style></head><body>"
            f"<h1>Colloquy commons</h1><p>Each commons is a separate board and library.</p><ul>{items}</ul>"
            "</body></html>")


def create_host_app(config, *, forwarded_allow_ips=None, graph_store=False):
    """The host application: one mounted commons application per tenant plus an index and aggregate health.
    `forwarded_allow_ips` names trusted reverse proxies for every tenant (daw.commons.app); `graph_store` builds
    each tenant's graph store at its first request (spec v3 B11)."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

    from daw.commons.app import create_app
    from daw.commons.archive import Archive

    host = FastAPI(title="Colloquy host", description="One commons per organisation (M7.4).", version="1",
                   docs_url=None, redoc_url=None, openapi_url=None)
    host.state.config = config
    by_name = {t.name: t for t in config.tenants}

    @host.get("/api/health")
    def health():
        tenants = []
        for tenant in config.tenants:
            try:
                with Archive(tenant.root) as view:
                    read = tenant_policy(tenant)
                    entry = {"name": tenant.name, "base": tenant.base, "ok": True, "read_policy": read}
                    if read == "public":  # a non-public tenant's sequence is board information
                        entry["sequence"] = view.sequence()
                    tenants.append(entry)
            except Exception as error:  # report, never raise: one broken tenant must not hide the others
                tenants.append({"name": tenant.name, "base": tenant.base, "ok": False,
                                "error": getattr(error, "reason", type(error).__name__)})
        ok = all(t["ok"] for t in tenants)
        return JSONResponse({"ok": ok, "mode": "host", "tenants": tenants}, status_code=200 if ok else 503)

    @host.get("/", include_in_schema=False)
    def index():
        return HTMLResponse(index_page(config))

    @host.get("/c/{name}", include_in_schema=False)
    def tenant_root(name: str):
        if name not in by_name:
            return JSONResponse({"error": "unknown_tenant", "detail": name}, status_code=404)
        return RedirectResponse(by_name[name].base)

    for tenant in config.tenants:
        host.mount(tenant.base.rstrip("/"), create_app(tenant.root, mode="accounts", static_dir=config.static_dir,
                                                       base=tenant.base, login=tenant.login, read_policy=tenant.read,
                                                       graph_store=graph_store))
    from daw.commons.app import trusted_proxies
    if trusted_proxies(forwarded_allow_ips):
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
        host.add_middleware(ProxyHeadersMiddleware, trusted_hosts=list(trusted_proxies(forwarded_allow_ips)))
    return host
