import json
import tomllib
from datetime import datetime, timedelta, timezone

import pytest

from sharron_support import git, load, make_clone, make_skill

refcheck = load("refcheck")
NOW = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)
MCP_URL = "https://owasp.org/www-project-mcp-top-10/"
REFS = {"schema_version": 1, "sources": [
    {"id": "owasp-top10", "name": "OWASP Top 10", "kind": "risk-list", "edition": "2025", "status": "final",
     "url": "https://owasp.org/Top10/2025/", "official_domains": ["owasp.org"], "applies_to": ["code"],
     "items": ["A01 Broken Access Control"], "check_every_days": 7,
     "probe": {"type": "next-edition", "url": "https://owasp.org/Top10/{edition}/"}},
    {"id": "owasp-mcp", "name": "OWASP MCP Top 10", "kind": "risk-list", "edition": "2025", "status": "beta",
     "url": MCP_URL, "official_domains": ["owasp.org"], "applies_to": ["install"], "items": [],
     "check_every_days": 1, "probe": {"type": "page-change"}},
    {"id": "cve", "name": "CVE", "kind": "vulnerability-data", "edition": "live", "status": "final",
     "url": "https://www.cve.org/", "official_domains": ["cve.org"], "applies_to": ["code", "install"], "items": [],
     "check_every_days": 7, "probe": {"type": "none"}}],
    "changelog": [{"date": "2026-10-27", "source": "owasp-top10", "change": "initial: 2025", "verified_by": "research during design"}]}
UPDATE = {"source": "owasp-mcp", "changes": {"status": "final", "edition": "2026"},
          "evidence_url": MCP_URL, "verified_by": "verifier (verify-evidence)"}


def refs_skill(tmp_path, state=None, skill=None):
    skill = skill or make_skill(tmp_path)
    (skill / "security-references.toml").write_text(refcheck.render_references(REFS), encoding="utf-8")
    if state:
        (skill / "state").mkdir(exist_ok=True)
        (skill / "state/refcheck.json").write_text(json.dumps(state))
    return skill


def fake_fetch(pages, fail=()):
    def fetch(url):
        if url in fail:
            raise refcheck.FetchError("timed out")
        return pages.get(url, refcheck.Page(404, url, ""))
    return fetch


def page(text, url=MCP_URL):
    return {url: refcheck.Page(200, url, text)}


def sources(result):
    return sorted({c["source"] for c in result["changes"]})


def test_render_round_trips():
    assert tomllib.loads(refcheck.render_references(REFS)) == REFS


def test_only_due_sources_are_probed(tmp_path):
    skill = refs_skill(tmp_path, state={"owasp-top10": {"checked_at": (NOW - timedelta(days=3)).isoformat()},
                                        "owasp-mcp": {"checked_at": (NOW - timedelta(days=2)).isoformat()}})
    assert refcheck.check(skill, now=NOW, fetch=fake_fetch(page("x")))["checked"] == ["owasp-mcp"]


def test_next_edition_found(tmp_path):
    new = "https://owasp.org/Top10/2026/"
    result = refcheck.check(refs_skill(tmp_path), now=NOW, fetch=fake_fetch({**page("x"), **page("Top 10 2026", new)}), force=True)
    [change] = [c for c in result["changes"] if c["source"] == "owasp-top10"]
    assert (change["type"], change["candidate"], change["url"]) == ("next-edition", "2026", new)


def test_next_edition_ignores_a_redirect_elsewhere(tmp_path):
    moved = {"https://owasp.org/Top10/2026/": refcheck.Page(200, "https://owasp.org/", "home")}
    result = refcheck.check(refs_skill(tmp_path), now=NOW, fetch=fake_fetch({**page("x"), **moved}), force=True)
    assert "owasp-top10" not in sources(result)


def test_page_change_ignores_markup_and_whitespace(tmp_path):
    skill = refs_skill(tmp_path)
    refcheck.check(skill, now=NOW, fetch=fake_fetch(page("<p>Beta  list</p>")), force=True)
    again = refcheck.check(skill, now=NOW + timedelta(days=2), fetch=fake_fetch(page("<div>Beta list</div>\n")))
    assert sources(again) == []


def test_detected_change_stays_pending_until_resolved(tmp_path):
    skill = refs_skill(tmp_path)
    refcheck.check(skill, now=NOW, fetch=fake_fetch(page("<p>v1</p>")), force=True)
    changed = fake_fetch(page("<p>v2</p>"))
    assert sources(refcheck.check(skill, now=NOW + timedelta(days=2), fetch=changed)) == ["owasp-mcp"]
    assert sources(refcheck.check(skill, now=NOW + timedelta(days=2, hours=1), fetch=changed)) == ["owasp-mcp"]
    refcheck.dismiss(skill, "owasp-mcp", now=NOW + timedelta(days=3))
    assert sources(refcheck.check(skill, now=NOW + timedelta(days=5), fetch=changed)) == []


def test_network_errors_are_reported_and_retried(tmp_path):
    skill = refs_skill(tmp_path)
    result = refcheck.check(skill, now=NOW, fetch=fake_fetch({}, fail={MCP_URL}), force=True)
    assert {"source": "owasp-mcp", "error": "timed out"} in result["errors"]
    retry = refcheck.check(skill, now=NOW + timedelta(hours=1), fetch=fake_fetch(page("ok")))
    assert "owasp-mcp" in retry["checked"]


@pytest.mark.usefixtures("isolated_git")
def test_apply_writes_the_update_and_commits_only_the_list(tmp_path):
    clone, skill = make_clone(tmp_path)
    refs_skill(tmp_path, skill=skill)
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", "refs")
    git(clone, "push", "-q")
    (clone / "notes.txt").write_text("wip\n")
    git(clone, "add", "notes.txt")
    result = refcheck.apply_update(skill, UPDATE, now=NOW)
    data = refcheck.load_references(skill / "security-references.toml")
    mcp = next(s for s in data["sources"] if s["id"] == "owasp-mcp")
    assert (mcp["status"], mcp["edition"]) == ("final", "2026")
    assert [s["id"] for s in data["sources"]] == ["owasp-top10", "owasp-mcp", "cve"]
    assert data["changelog"][-1] == {"date": "2026-10-28", "source": "owasp-mcp",
                                     "change": "edition 2025 → 2026; status beta → final",
                                     "verified_by": "verifier (verify-evidence)"}
    assert git(clone, "show", "--name-only", "--format=", "HEAD") == "plugins/workflow/skills/sharron/security-references.toml"
    assert result["sync"]["pushed"] is True


@pytest.mark.parametrize("update,message", [
    ({**UPDATE, "evidence_url": "https://evil.example/owasp"}, "official_domains"),
    ({**UPDATE, "changes": {"url": "https://owasp.org.evil.example/"}}, "official_domains"),
    ({**UPDATE, "changes": {"applies_to": ["code"]}}, "may only change"),
    ({**UPDATE, "source": "new-framework"}, "unknown source"),
    ({**UPDATE, "changes": {"items": ["ok", "line\nbreak"]}}, "items"),
])
def test_apply_rejects_unsafe_updates(tmp_path, update, message):
    skill = refs_skill(tmp_path)
    before = (skill / "security-references.toml").read_text()
    with pytest.raises(refcheck.RefError, match=message):
        refcheck.apply_update(skill, update, now=NOW)
    assert (skill / "security-references.toml").read_text() == before


def test_fingerprint_skips_scripts_styles_and_titles():
    plain = refcheck.fingerprint("<p>Hello</p>")
    assert refcheck.fingerprint("<title>Page</title><p>Hello</p>") == refcheck.fingerprint("<p>Hello</p><title>Page</title>") == plain
    assert refcheck.fingerprint("<style>p{color:red}</style><p>Hello</p><script>var t=1</script>") == plain
    assert refcheck.fingerprint("<p>Hello again</p>") != plain


def test_http_errors_are_errors_but_404_is_just_not_found(tmp_path):
    skill = refs_skill(tmp_path)
    broken = {MCP_URL: refcheck.Page(503, MCP_URL, ""), "https://owasp.org/Top10/2026/": refcheck.Page(404, "x", "")}
    result = refcheck.check(skill, now=NOW, fetch=fake_fetch(broken), force=True)
    assert [e["source"] for e in result["errors"]] == ["owasp-mcp"]
    assert "owasp-top10" in result["checked"] and result["changes"] == []


def test_a_pending_next_edition_is_reported_until_dismissed(tmp_path):
    skill = refs_skill(tmp_path)
    new = "https://owasp.org/Top10/2026/"
    fetch = fake_fetch({**page("x"), **page("Top 10 2026", new)})
    refcheck.check(skill, now=NOW, fetch=fetch, force=True)
    later = refcheck.check(skill, now=NOW + timedelta(days=30), fetch=fetch)
    assert sources(later) == ["owasp-top10"] and "owasp-top10" not in later["checked"]
    assert refcheck.dismiss(skill, "owasp-top10", now=NOW + timedelta(days=31)) == {"source": "owasp-top10", "dismissed": True}
    assert refcheck.dismiss(skill, "owasp-top10", now=NOW + timedelta(days=31))["dismissed"] is False


def test_dismiss_rejects_an_unknown_source(tmp_path):
    with pytest.raises(refcheck.RefError, match="unknown source"):
        refcheck.dismiss(refs_skill(tmp_path), "nope", now=NOW)


def test_apply_clears_the_pending_change_and_keeps_the_new_fingerprint(tmp_path):
    skill = refs_skill(tmp_path)
    refcheck.check(skill, now=NOW, fetch=fake_fetch(page("<p>v1</p>")), force=True)
    refcheck.check(skill, now=NOW + timedelta(days=2), fetch=fake_fetch(page("<p>v2</p>")))
    refcheck.apply_update(skill, UPDATE, now=NOW + timedelta(days=3))
    state = refcheck.load_state(skill)["owasp-mcp"]
    assert state["pending"] is None and state["fingerprint"] == refcheck.fingerprint("<p>v2</p>")
    assert sources(refcheck.check(skill, now=NOW + timedelta(days=5), fetch=fake_fetch(page("<p>v2</p>")))) == []


def test_apply_describes_only_the_fields_that_changed(tmp_path):
    skill = refs_skill(tmp_path)
    update = {**UPDATE, "changes": {"edition": "2025", "items": ["A01 One", "A02 Two"],
                                    "probe": {"type": "none"}, "url": "https://owasp.org/mcp-2025/"}}
    result = refcheck.apply_update(skill, update, now=NOW)
    assert result["change"] == ('url https://owasp.org/www-project-mcp-top-10/ → https://owasp.org/mcp-2025/; '
                                'items updated (2 items); probe {"type": "page-change"} → {"type": "none"}')


def test_apply_that_changes_nothing_is_rejected(tmp_path):
    skill = refs_skill(tmp_path)
    with pytest.raises(refcheck.RefError, match="changes nothing"):
        refcheck.apply_update(skill, {**UPDATE, "changes": {"status": "beta"}}, now=NOW)


@pytest.mark.parametrize("changes,message", [
    ({"url": "http://owasp.org/x"}, "official_domains"),
    ({"url": "https://owasp.org@evil.example/"}, "official_domains"),
    ({"url": "https://owasp.org/a b"}, "url"),
    ({"status": "draft"}, "status"),
    ({"items": ["x"] * 51}, "items"),
    ({"items": ["x" * 201]}, "items"),
    ({"items": "A01"}, "items"),
    ({"edition": "live", "probe": {"type": "next-edition", "url": "https://owasp.org/{edition}/"}}, "four-digit"),
    ({"edition": "bad\nline"}, "edition"),
])
def test_apply_rejects_invalid_values(tmp_path, changes, message):
    with pytest.raises(refcheck.RefError, match=message):
        refcheck.apply_update(refs_skill(tmp_path), {**UPDATE, "changes": changes}, now=NOW)


@pytest.mark.parametrize("edit,message", [
    (lambda s: s.update(kind="guide"), "kind"),
    (lambda s: s.update(applies_to=["code", "moon"]), "applies_to"),
    (lambda s: s.update(check_every_days=0), "check_every_days"),
    (lambda s: s.update(url="http://owasp.org/Top10/2025/"), "official_domains"),
    (lambda s: s.update(url="https://owasp.org.evil.example/"), "official_domains"),
    (lambda s: s["probe"].update(url="https://owasp.org/Top10/next/"), "{edition}"),
    (lambda s: s.update(edition="live"), "four-digit"),
])
def test_load_references_rejects_a_bad_source(tmp_path, edit, message):
    data = json.loads(json.dumps(REFS))
    edit(data["sources"][0])
    path = tmp_path / "refs.toml"
    path.write_text(refcheck.render_references(data), encoding="utf-8")
    with pytest.raises(refcheck.RefError, match=message):
        refcheck.load_references(path)


def test_load_references_rejects_unknown_keys(tmp_path):
    path = tmp_path / "refs.toml"
    path.write_text(refcheck.render_references(REFS).replace('id = "cve"\n', 'id = "cve"\nextra = 1\n'), encoding="utf-8")
    with pytest.raises(refcheck.RefError, match="unknown keys"):
        refcheck.load_references(path)


def test_load_references_rejects_duplicate_ids_and_bad_toml(tmp_path):
    data = json.loads(json.dumps(REFS))
    data["sources"].append(data["sources"][0])
    path = tmp_path / "refs.toml"
    path.write_text(refcheck.render_references(data), encoding="utf-8")
    with pytest.raises(refcheck.RefError, match="unique"):
        refcheck.load_references(path)
    path.write_text("schema_version = [", encoding="utf-8")
    with pytest.raises(refcheck.RefError, match="refs.toml"):
        refcheck.load_references(path)


def test_cli_check_prints_one_json_object(tmp_path, capsys, monkeypatch):
    skill = refs_skill(tmp_path)
    real_check = refcheck.check
    monkeypatch.setattr(refcheck, "check", lambda skill_dir, **kwargs: real_check(skill_dir, **kwargs, fetch=fake_fetch(page("x"))))
    assert refcheck.main(["--skill-dir", str(skill), "check", "--force"]) == 0
    assert json.loads(capsys.readouterr().out) == {"checked": ["owasp-top10", "owasp-mcp"], "changes": [], "errors": []}


def test_cli_apply_needs_exactly_one_form(tmp_path, capsys):
    skill = refs_skill(tmp_path)
    for argv in (["apply"], ["apply", "--no-change"], ["apply", "--source", "x"]):
        with pytest.raises(SystemExit) as exit_info:
            refcheck.main(["--skill-dir", str(skill), *argv])
        assert exit_info.value.code == 2


def test_cli_reports_bad_input_on_stderr(tmp_path, capsys):
    skill = refs_skill(tmp_path)
    update = tmp_path / "update.json"
    update.write_text(json.dumps({**UPDATE, "source": "new-framework"}))
    assert refcheck.main(["--skill-dir", str(skill), "apply", str(update)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("refcheck.py: ") and "unknown source" in captured.err
    assert refcheck.main(["--skill-dir", str(skill), "apply", str(tmp_path / "missing.json")]) == 1
    assert refcheck.main(["--skill-dir", str(skill), "apply", "--no-change", "--source", "nope"]) == 1
    capsys.readouterr()
    assert refcheck.main(["--skill-dir", str(skill), "apply", "--no-change", "--source", "owasp-mcp"]) == 0
    assert json.loads(capsys.readouterr().out) == {"source": "owasp-mcp", "dismissed": False}


def test_fetch_url_returns_http_errors_and_raises_on_network_errors():
    import http.server
    import socket
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/x"
    try:
        assert refcheck.fetch_url(url) == refcheck.Page(404, url, "")
    finally:
        server.shutdown()
        server.server_close()
    with pytest.raises(refcheck.FetchError):
        refcheck.fetch_url(url)  # the port is closed now
