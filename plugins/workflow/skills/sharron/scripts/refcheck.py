#!/usr/bin/env python3
"""Watch the security reference list for new editions and write verified updates to it.

Usage (from the skill folder; every subcommand prints one JSON object):
    sh scripts/run.sh refcheck.py check [--force]
    sh scripts/run.sh refcheck.py apply <update.json>
    sh scripts/run.sh refcheck.py apply --no-change --source ID

`check` probes the sources of security-references.toml that are due (each source's `check_every_days`;
--force ignores the interval) and records the check times in state/refcheck.json. It uses no model and
never changes the list. A detected change stays `pending` in that file, and is reported by every later
`check`, until `apply` writes the verified update or `apply --no-change` dismisses it.

`apply` takes the update that sharron writes after the verifier confirmed it:
    {"source": ID, "changes": {subset of edition, status, url, items, probe},
     "evidence_url": "https://...", "verified_by": "..."}
It validates the update, writes the list, appends a changelog entry, clears the pending change and then
runs the data sync (datasync.py), which commits and pushes only security-references.toml.

The list steers the security role, so the fetcher refuses a redirect that leaves a source's
`official_domains` or https before it reads the body, evidence must come from those domains, the sources
and `applies_to` are never changed by `apply`, and items are plain one-line names. An update is fully
validated before anything is written.
Bad input prints one line on stderr and exits 1.
"""

import sys

if sys.version_info < (3, 11):
    sys.exit(f"sharron scripts need Python 3.11 or newer (found {sys.version_info.major}.{sys.version_info.minor})")

import argparse  # noqa: E402
import functools  # noqa: E402
import hashlib  # noqa: E402
import http.client  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import tomllib  # noqa: E402
import unicodedata  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from collections.abc import Callable  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from html.parser import HTMLParser  # noqa: E402
from pathlib import Path  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

import config  # noqa: E402
import datasync  # noqa: E402

REFERENCES_FILE = "security-references.toml"
STATE_FILE = "state/refcheck.json"
LOCK_NAME = "refcheck"
COMMIT_MESSAGE = "chore(sharron): update security references [skip ci]"
SCHEMA_VERSION = 1
KINDS = ("risk-list", "weakness-list", "vulnerability-data", "attack-patterns")
STATUSES = ("final", "beta")
APPLIES_TO = ("code", "api", "ci-cd", "credentials", "action", "publish", "install", "agent")
PROBE_TYPES = ("next-edition", "page-change", "none")
UPDATE_KEYS = ("source", "changes", "evidence_url", "verified_by")
UPDATABLE = ("edition", "status", "url", "items", "probe")  # the only fields `apply` may change
SOURCE_KEYS = (
    "id", "name", "kind", "edition", "status", "url", "official_domains", "applies_to",
    "items", "check_every_days", "probe",
)
CHANGELOG_KEYS = ("date", "source", "change", "verified_by")
MAX_ITEMS = 50
MAX_ITEM_LENGTH = 200
MAX_TEXT_LENGTH = 300
MAX_URL_LENGTH = 2048
MAX_CHANGE_LENGTH = 1000
MAX_VERIFIED_BY_LENGTH = 200
FETCH_TIMEOUT = 10  # seconds
MAX_PAGE_BYTES = 4_000_000
USER_AGENT = "sharron-refcheck"
_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_YEAR_RE = re.compile(r"[0-9]{4}")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DOMAIN_RE = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}")

HEADER = """\
# Security reference list: the frameworks the security role uses, with their current editions.
# scripts/refcheck.py probes the official pages and writes verified updates here; you add or remove
# sources by hand. Update the fields of an entry in the same layout, since refcheck rewrites the file.
#
# [[sources]]            one entry per source
#   id                 unique, lowercase with hyphens
#   name               the source's name
#   kind               risk-list | weakness-list | vulnerability-data | attack-patterns
#   edition            the current edition, or "live" for data that is queried at review time
#   status             final | beta
#   url                the official page of this edition (https, on one of official_domains)
#   official_domains   the only domains refcheck reads and accepts evidence from (subdomains included)
#   applies_to         subset of: code, api, ci-cd, credentials, action, publish, install, agent
#   items              the names of the entries, plain one-line text, as the official page writes them
#   check_every_days   how often refcheck probes the source (a positive whole number)
#   probe              how a new edition is detected:
#                        { type = "next-edition", url = "...{edition}..." }  does the next edition's page exist?
#                        { type = "page-change" }                            did the text of `url` change?
#                        { type = "none" }                                   live data, nothing to probe
#
# [[changelog]]          one entry per change, appended by refcheck: date, source, change, verified_by
#
# An automatic update may change only edition, status, url, items and probe of an existing source.
"""


class FetchError(Exception):
    """A page could not be fetched (network failure, timeout)."""


class RefError(ValueError):
    """The reference list, its state or an update is invalid."""


@dataclass(frozen=True)
class Page:
    status: int
    final_url: str
    text: str


# ---------------------------------------------------------------- fetching


class _OfficialRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect hop that is not https on one of the official domains, before its body is read."""

    def __init__(self, domains: list[str]) -> None:
        self.domains = domains

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _host_is_official(newurl, self.domains):
            raise FetchError(f"{req.full_url} redirected to {newurl}, which is not https on the official_domains")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_url(url: str, official_domains: list[str] | None = None) -> Page:
    """GET url. An HTTP error returns its status as a Page; a network error raises FetchError.

    With official_domains, a redirect that leaves them or leaves https raises FetchError at the hop.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(_OfficialRedirects(official_domains)) if official_domains else urllib.request.build_opener()
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT) as response:
            body = response.read(MAX_PAGE_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            return Page(response.status, response.geturl(), body.decode(charset, errors="replace"))
    except urllib.error.HTTPError as error:
        return Page(error.code, error.geturl() or url, "")
    except urllib.error.URLError as error:
        raise FetchError(f"{url}: {error.reason}") from error
    except (OSError, http.client.HTTPException, LookupError) as error:  # timeouts, resets, a bad charset name
        raise FetchError(f"{url}: {error}") from error


_SKIPPED_TAGS = ("script", "style", "title")  # <title> too: some sites stream it in at the head or at the end of the body


class _TextExtractor(HTMLParser):
    """Collect the text outside <script>, <style> and <title>.

    An element that is never closed does not hide the rest of the document: its text is counted at the end.
    """

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skipping = 0
        self._skipped: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIPPED_TAGS:
            self._skipping += 1

    def handle_endtag(self, tag):
        if tag in _SKIPPED_TAGS and self._skipping:
            self._skipping -= 1
            if not self._skipping:
                self._skipped.clear()

    def handle_data(self, data):
        (self._skipped if self._skipping else self.parts).append(data)

    def close(self):
        super().close()
        if self._skipping:  # unclosed: count what followed the opening tag
            if self.cdata_elem and self.rawdata:  # older parsers keep the rest of an unclosed script or style here
                self._skipped.append(self.rawdata)
            self.parts.extend(self._skipped)
            self._skipping = 0
            self._skipped.clear()


def fingerprint(html_text: str) -> str:
    """The sha256 of a page's text outside script, style and title with whitespace collapsed, so markup changes do not count."""
    extractor = _TextExtractor()
    extractor.feed(html_text)
    extractor.close()
    text = " ".join(" ".join(extractor.parts).split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- the reference list


def _plain_text(value: object, what: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """A non-empty one-line string without control or line-separator characters."""
    if not isinstance(value, str) or not value.strip():
        raise RefError(f"{what} must be a non-empty string")
    if len(value) > max_length:
        raise RefError(f"{what} must be at most {max_length} characters")
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in value):
        raise RefError(f"{what} must not contain control characters or line breaks")
    return value


def _host_is_official(url: str, domains: list[str]) -> bool:
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        parsed.port  # noqa: B018  # raises ValueError on a malformed port
    except ValueError:
        return False
    if parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _check_url(url: object, domains: list[str], what: str) -> str:
    if not isinstance(url, str) or any(ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf") for ch in url):
        raise RefError(f"{what} must be a URL without spaces or control characters")
    if len(url) > MAX_URL_LENGTH:
        raise RefError(f"{what} must be at most {MAX_URL_LENGTH} characters")
    if not _host_is_official(url, domains):
        raise RefError(f"{what} {url!r} must be https on one of the official_domains ({', '.join(domains)})")
    return url


def _check_items(items: object, where: str) -> list[str]:
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise RefError(f"{where}items must be a list of at most {MAX_ITEMS} strings")
    return [_plain_text(item, f"{where}items entry", MAX_ITEM_LENGTH) for item in items]


def _check_subset(values: object, allowed: tuple[str, ...], what: str) -> None:
    if not isinstance(values, list) or not values or not all(isinstance(v, str) and v in allowed for v in values):
        raise RefError(f"{what} must be a non-empty list taken from: {', '.join(allowed)}")
    if len(set(values)) != len(values):
        raise RefError(f"{what} lists a value twice")


def _validate_source(source: object, index: int) -> None:
    if not isinstance(source, dict):
        raise RefError(f"sources[{index}] must be a table")
    name = source.get("id")
    if not isinstance(name, str) or not _ID_RE.fullmatch(name):
        raise RefError(f"sources[{index}].id must be lowercase letters, digits and single hyphens")
    where = f"source {name}: "
    unknown = sorted(set(source) - set(SOURCE_KEYS))
    missing = [key for key in SOURCE_KEYS if key not in source]
    if unknown or missing:
        raise RefError(f"{where}unknown keys {unknown}, missing keys {missing}" if unknown else f"{where}missing keys {missing}")
    _plain_text(source["name"], f"{where}name")
    _plain_text(source["edition"], f"{where}edition", 40)
    if source["kind"] not in KINDS:
        raise RefError(f"{where}kind must be one of: {', '.join(KINDS)}")
    if source["status"] not in STATUSES:
        raise RefError(f"{where}status must be one of: {', '.join(STATUSES)}")
    domains = source["official_domains"]
    if not isinstance(domains, list) or not domains or not all(isinstance(d, str) and _DOMAIN_RE.fullmatch(d) for d in domains):
        raise RefError(f"{where}official_domains must be a non-empty list of lowercase domain names")
    _check_subset(source["applies_to"], APPLIES_TO, f"{where}applies_to")
    _check_items(source["items"], where)
    days = source["check_every_days"]
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise RefError(f"{where}check_every_days must be a positive whole number")
    _check_url(source["url"], domains, f"{where}url")
    _validate_probe(source, where, domains)


def _validate_probe(source: dict, where: str, domains: list[str]) -> None:
    probe = source["probe"]
    if not isinstance(probe, dict) or probe.get("type") not in PROBE_TYPES or not set(probe) <= {"type", "url"}:
        raise RefError(f"{where}probe must be a table with type {' | '.join(PROBE_TYPES)} and, for next-edition, url")
    if probe["type"] == "next-edition":
        if not isinstance(source["edition"], str) or not _YEAR_RE.fullmatch(source["edition"]):
            raise RefError(f"{where}a next-edition probe needs a four-digit-year edition")
        url = _check_url(probe.get("url"), domains, f"{where}probe.url")
        if "{edition}" not in url:
            raise RefError(f"{where}probe.url must contain {{edition}}")
    elif "url" in probe:
        raise RefError(f"{where}only a next-edition probe has a url")


def _validate_changelog_entry(entry: object, index: int) -> None:
    if not isinstance(entry, dict) or set(entry) != set(CHANGELOG_KEYS):
        raise RefError(f"changelog[{index}] must have exactly: {', '.join(CHANGELOG_KEYS)}")
    if not isinstance(entry["date"], str) or not _DATE_RE.fullmatch(entry["date"]):
        raise RefError(f"changelog[{index}].date must be YYYY-MM-DD text")
    for key, limit in (("source", MAX_TEXT_LENGTH), ("change", MAX_CHANGE_LENGTH), ("verified_by", MAX_VERIFIED_BY_LENGTH)):
        _plain_text(entry[key], f"changelog[{index}].{key}", limit)


def validate_references(data: object) -> dict:
    """Return data when it is a valid reference list; raise RefError otherwise."""
    if not isinstance(data, dict) or set(data) - {"schema_version", "sources", "changelog"}:
        raise RefError("the list holds only schema_version, [[sources]] and [[changelog]]")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise RefError(f"schema_version must be {SCHEMA_VERSION}")
    sources = data.get("sources", [])
    changelog = data.get("changelog", [])
    if not isinstance(sources, list) or not isinstance(changelog, list):
        raise RefError("sources and changelog must be arrays of tables")
    for index, source in enumerate(sources):
        _validate_source(source, index)
    ids = [source["id"] for source in sources]
    if len(set(ids)) != len(ids):
        raise RefError("source ids must be unique")
    for index, entry in enumerate(changelog):
        _validate_changelog_entry(entry, index)
    return data


def load_references(path: Path) -> dict:
    """Read and validate security-references.toml; raise RefError on any violation."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise RefError(f"{path.name}: {error}") from error
    except UnicodeDecodeError as error:
        raise RefError(f"{path.name}: not UTF-8 text") from error
    try:
        data = validate_references(data)
    except RefError as error:
        raise RefError(f"{path.name}: {error}") from error
    data.setdefault("sources", [])
    data.setdefault("changelog", [])
    return data


def _s(value: str) -> str:
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def _string_list(values: list[str]) -> str:
    return "[" + ", ".join(_s(value) for value in values) + "]"


def _render_probe(probe: dict) -> str:
    fields = [f"type = {_s(probe['type'])}"]
    if "url" in probe:
        fields.append(f"url = {_s(probe['url'])}")
    return "{ " + ", ".join(fields) + " }"


def _render_source(source: dict) -> str:
    items = "items = [\n" + "".join(f"  {_s(item)},\n" for item in source["items"]) + "]" if source["items"] else "items = []"
    lines = [
        "[[sources]]",
        f"id = {_s(source['id'])}",
        f"name = {_s(source['name'])}",
        f"kind = {_s(source['kind'])}",
        f"edition = {_s(source['edition'])}",
        f"status = {_s(source['status'])}",
        f"url = {_s(source['url'])}",
        f"official_domains = {_string_list(source['official_domains'])}",
        f"applies_to = {_string_list(source['applies_to'])}",
        items,
        f"check_every_days = {source['check_every_days']}",
        f"probe = {_render_probe(source['probe'])}",
    ]
    return "\n".join(lines) + "\n"


def _render_entry(entry: dict) -> str:
    return "\n".join(["[[changelog]]", *(f"{key} = {_s(entry[key])}" for key in CHANGELOG_KEYS)]) + "\n"


def render_references(data: dict) -> str:
    """The canonical text of the list: the header, schema_version, the [[sources]], then the [[changelog]]."""
    blocks = [HEADER, f"schema_version = {data['schema_version']}\n"]
    blocks += [_render_source(source) for source in data.get("sources", [])]
    blocks += [_render_entry(entry) for entry in data.get("changelog", [])]
    return "\n".join(blocks)


# ---------------------------------------------------------------- state


def _state_path(skill_dir: Path) -> Path:
    return skill_dir / STATE_FILE


def load_state(skill_dir: Path) -> dict:
    """state/refcheck.json as {id: {"checked_at", "fingerprint", "pending"}}; a missing file is empty.

    A file that exists but is damaged raises RefError rather than reading as empty, which would lose the
    pending changes without a word; nothing overwrites it.
    """
    path = _state_path(skill_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as error:
        raise RefError(f"{STATE_FILE} cannot be read ({error}); fix or delete it") from error
    try:
        state = json.loads(text)
    except ValueError as error:
        raise RefError(f"{STATE_FILE} is damaged ({error}); fix or delete it") from error
    if not isinstance(state, dict) or not all(isinstance(value, dict) for value in state.values()):
        raise RefError(f"{STATE_FILE} is damaged (it must map source ids to objects); fix or delete it")
    return state


def _save_state(skill_dir: Path, state: dict) -> None:
    datasync.write_atomic(_state_path(skill_dir), json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def _parse_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def due_sources(data: dict, state: dict, now: datetime, force: bool = False) -> list[dict]:
    """The sources to probe now: probe not `none`, no pending change, and the interval over (or force)."""
    due = []
    for source in data["sources"]:
        entry = state.get(source["id"], {})
        if source["probe"]["type"] == "none" or entry.get("pending"):
            continue
        checked = _parse_time(entry.get("checked_at"))
        if force or checked is None or now - checked >= timedelta(days=source["check_every_days"]):
            due.append(source)
    return due


# ---------------------------------------------------------------- probes


def _fetch_checked(fetch: Callable[[str], Page], url: str) -> Page:
    page = fetch(url)
    if page.status in (404, 410):
        return page
    if not 200 <= page.status < 300:
        raise FetchError(f"{url} returned HTTP {page.status}")
    return page


def _probe_next_edition(source: dict, fetch: Callable[[str], Page], now: datetime) -> dict | None:
    """The newest later edition whose page exists, or None. The page must stay on an official domain and keep its year."""
    found = None
    for year in range(int(source["edition"]) + 1, now.year + 2):
        url = source["probe"]["url"].replace("{edition}", str(year))
        page = _fetch_checked(fetch, url)
        if 200 <= page.status < 300 and str(year) in page.final_url and _host_is_official(page.final_url, source["official_domains"]):
            found = {"type": "next-edition", "detected_at": now.isoformat(), "candidate": str(year), "url": url}
    return found


def _probe_page_change(source: dict, entry: dict, fetch: Callable[[str], Page], now: datetime) -> dict | None:
    """A pending change when the page text differs from the stored fingerprint; stores the first fingerprint silently."""
    page = _fetch_checked(fetch, source["url"])
    if not 200 <= page.status < 300:
        raise FetchError(f"{source['url']} returned HTTP {page.status}")
    if not _host_is_official(page.final_url, source["official_domains"]):
        raise FetchError(f"{source['url']} redirected outside the official_domains to {page.final_url}")
    entry["fingerprint"], previous = fingerprint(page.text), entry.get("fingerprint")
    if previous and previous != entry["fingerprint"]:
        return {"type": "page-change", "detected_at": now.isoformat(), "fingerprint": entry["fingerprint"]}
    return None


def check(skill_dir: Path, *, now: datetime, fetch: Callable[[str], Page] = fetch_url, force: bool = False) -> dict:
    """Probe the due sources. Returns {"checked": [ids], "changes": [pending changes], "errors": [{"source", "error"}]}.

    A source whose probe fails is left alone, so the next check retries it. A detected change stays
    pending until apply_update or dismiss resolves it.
    """
    data = load_references(skill_dir / REFERENCES_FILE)
    with datasync.file_lock(skill_dir, LOCK_NAME):
        state = load_state(skill_dir)
    snapshot = state
    checked, errors, results = [], [], {}
    for source in due_sources(data, state, now, force):  # the network work runs outside the lock
        entry = dict(state.get(source["id"], {}))
        # the default fetcher also refuses redirects off the source's domains; an injected one sets its own policy
        fetcher = functools.partial(fetch_url, official_domains=source["official_domains"]) if fetch is fetch_url else fetch
        try:
            if source["probe"]["type"] == "next-edition":
                pending = _probe_next_edition(source, fetcher, now)
            else:
                pending = _probe_page_change(source, entry, fetcher, now)
        except FetchError as error:
            errors.append({"source": source["id"], "error": str(error)})
            continue
        checked.append(source["id"])
        entry.update(checked_at=now.isoformat(), pending=pending)
        entry.setdefault("fingerprint", None)
        results[source["id"]] = entry
    with datasync.file_lock(skill_dir, LOCK_NAME):
        state = load_state(skill_dir)
        # Compare and swap per source: another run (or apply, or dismiss) may have changed an entry while this
        # run was probing it. This run's result was computed from the snapshot, so it is stored only when the
        # entry is still what the snapshot saw; otherwise the newer state wins.
        stored = {sid: entry for sid, entry in results.items() if state.get(sid) == snapshot.get(sid)}
        if stored:
            state.update(stored)
            _save_state(skill_dir, state)
    changes = [{"source": s["id"], **state[s["id"]]["pending"]} for s in data["sources"] if state.get(s["id"], {}).get("pending")]
    return {"checked": checked, "changes": changes, "errors": errors}


# ---------------------------------------------------------------- resolving a change


def _resolve_pending(state: dict, source_id: str, now: datetime) -> bool:
    """Clear the pending change of a source; its fingerprint becomes the stored one. Returns whether there was one."""
    entry = state.setdefault(source_id, {})
    pending = entry.get("pending")
    if pending and pending.get("fingerprint"):
        entry["fingerprint"] = pending["fingerprint"]
    entry.setdefault("fingerprint", None)
    entry.update(pending=None, checked_at=now.isoformat())
    return bool(pending)


def _find_source(data: dict, source_id: object) -> dict:
    for source in data["sources"]:
        if source["id"] == source_id:
            return source
    raise RefError(f"unknown source {source_id!r}; new sources are added by the user")


def dismiss(skill_dir: Path, source_id: str, *, now: datetime) -> dict:
    """Resolve a pending change without changing the list: the verifier found nothing to update."""
    with datasync.file_lock(skill_dir, LOCK_NAME):
        _find_source(load_references(skill_dir / REFERENCES_FILE), source_id)
        state = load_state(skill_dir)
        dismissed = _resolve_pending(state, source_id, now)
        _save_state(skill_dir, state)
    return {"source": source_id, "dismissed": dismissed}


def _describe(field: str, old: object, new: object) -> str:
    if field == "items":
        return f"items updated ({len(new)} items)"
    if field == "probe":
        return f"probe {json.dumps(old, ensure_ascii=False)} → {json.dumps(new, ensure_ascii=False)}"
    return f"{field} {old} → {new}"


def _validated_changes(update: object, data: dict) -> tuple[dict, dict, str]:
    """Check an update against the list and return (source, changes, verified_by)."""
    if not isinstance(update, dict) or not isinstance(update.get("changes"), dict):
        raise RefError("an update is an object with source, changes, evidence_url and verified_by")
    if set(update) - set(UPDATE_KEYS):
        raise RefError(f"an update has only these keys: {', '.join(UPDATE_KEYS)} (unknown: {', '.join(sorted(set(update) - set(UPDATE_KEYS)))})")
    source = _find_source(data, update.get("source"))
    changes = update["changes"]
    if not changes or not set(changes) <= set(UPDATABLE):
        raise RefError(f"an update may only change {', '.join(UPDATABLE)} (got {', '.join(sorted(changes)) or 'nothing'})")
    domains = source["official_domains"]
    _check_url(update.get("evidence_url"), domains, "evidence_url")
    verified_by = _plain_text(update.get("verified_by"), "verified_by", MAX_VERIFIED_BY_LENGTH)
    try:
        _validate_source({**source, **changes}, 0)
    except RefError as error:
        raise RefError(str(error).removeprefix(f"source {source['id']}: ")) from error
    return source, changes, verified_by


def apply_update(skill_dir: Path, update: dict, *, now: datetime) -> dict:
    """Write a verified update to the list, append the changelog entry, clear the pending change, then sync.

    Returns {"source", "change", "sync"}; "sync" is the data-sync result, whose reasons are not errors.
    """
    path = skill_dir / REFERENCES_FILE
    with datasync.file_lock(skill_dir, LOCK_NAME):
        data = load_references(path)
        source, changes, verified_by = _validated_changes(update, data)
        parts = [_describe(field, source[field], changes[field]) for field in UPDATABLE if field in changes and changes[field] != source[field]]
        if not parts:
            raise RefError("the update changes nothing; use apply --no-change to dismiss the pending change")
        for field in UPDATABLE:
            if field in changes:
                source[field] = changes[field]
        change = _plain_text("; ".join(parts), "the changelog text of this update", MAX_CHANGE_LENGTH)
        data["changelog"].append({"date": now.date().isoformat(), "source": source["id"], "change": change, "verified_by": verified_by})
        try:
            validate_references(data)  # the same validator as load_references, on the whole new list, before anything is written
        except RefError as error:
            raise RefError(f"the updated list would be invalid: {error}") from error
        state = load_state(skill_dir)  # a damaged state file stops the update before the list is written
        datasync.write_atomic(path, render_references(data))
        _resolve_pending(state, source["id"], now)
        _save_state(skill_dir, state)
    result = datasync.sync(skill_dir, REFERENCES_FILE, COMMIT_MESSAGE)  # after the lock, so a slow push does not hold it
    return {"source": source["id"], "change": change, "sync": result.to_json()}


# ---------------------------------------------------------------- command line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refcheck.py", description="Check the security reference list for new editions.")
    parser.add_argument(
        "--skill-dir", type=Path, default=config.DEFAULT_SKILL_DIR, help="skill folder (default: the folder above scripts/)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("check", help="probe the sources that are due")
    probe.add_argument("--force", action="store_true", help="ignore check_every_days")
    apply = sub.add_parser("apply", help="write a verified update, or dismiss a pending change")
    apply.add_argument("update", nargs="?", type=Path, help="the update JSON written by sharron")
    apply.add_argument("--no-change", action="store_true", help="dismiss the pending change of --source")
    apply.add_argument("--source", help="with --no-change: the source id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "apply" and (args.no_change, args.update is None, bool(args.source)) not in ((True, True, True), (False, False, False)):
        parser.error("use either `apply <update.json>` or `apply --no-change --source ID`")
    now = datetime.now(timezone.utc)
    try:
        if args.command == "check":
            result = check(args.skill_dir, now=now, force=args.force)
        elif args.no_change:
            result = dismiss(args.skill_dir, args.source, now=now)
        else:
            result = apply_update(args.skill_dir, json.loads(args.update.read_text(encoding="utf-8")), now=now)
    except (ValueError, OSError) as error:  # RefError and JSON errors are ValueErrors
        print(f"refcheck.py: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
