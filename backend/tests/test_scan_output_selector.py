"""Result selection never reads a draft, another program, or a newer scan by accident."""
from types import SimpleNamespace

import pytest
from fastapi import Request, Response

from backend.api.programs import assets, findings, scan_options, surface
from backend.jobs.scope_resolver import ScopeError
from backend.tests.p2_helpers import environment


def test_latest_has_no_results_before_first_completed_scan(settings):
    db, _, result = environment(settings, ["127.0.0.1"])
    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(database=db))})
    assert assets(result.slug, request, Response(), None, 0, "", None, 100, 0, "latest") == []
    assert findings(result.slug, request, Response(), None, None, 100, 0, "latest") == []
    assert scan_options(result.slug, request) == []


def test_assets_findings_and_surface_follow_completed_scan(settings):
    db, _, result = environment(settings, ["127.0.0.1"])
    with db.connect() as conn, conn:
        program_id = conn.execute("SELECT id FROM program WHERE slug=?", (result.slug,)).fetchone()[0]
        first = result.scan_id
        conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (first,))
        second = conn.execute("INSERT INTO scan_run(program_id,depth,status) VALUES(?,'light','done')", (program_id,)).lastrowid
        draft = conn.execute("INSERT INTO scan_run(program_id,depth,status) VALUES(?,'light','draft')", (program_id,)).lastrowid
        old_asset = conn.execute("INSERT INTO asset(program_id,host,first_seen_scan,last_seen_scan,state) VALUES(?,?,?,?,'gone')", (program_id, "old.local", first, first)).lastrowid
        new_asset = conn.execute("INSERT INTO asset(program_id,host,first_seen_scan,last_seen_scan,state) VALUES(?,?,?,?,'active')", (program_id, "new.local", second, second)).lastrowid
        conn.execute("INSERT INTO finding(program_id,asset_id,type,severity,name,first_seen_scan,last_seen_scan) VALUES(?,?,'nuclei','low','old',?,?)", (program_id, old_asset, first, first))
        conn.execute("INSERT INTO finding(program_id,asset_id,type,severity,name,first_seen_scan,last_seen_scan) VALUES(?,?,'nuclei','high','new',?,?)", (program_id, new_asset, second, second))

    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(database=db))})
    assert [r["id"] for r in scan_options(result.slug, request)] == [second, first]
    def asset_rows(scan):
        return assets(result.slug, request, Response(), None, 0, "", None, 100, 0, scan)
    def finding_rows(scan):
        return findings(result.slug, request, Response(), None, None, 100, 0, scan)
    assert {r["host"] for r in asset_rows("all")} == {"old.local", "new.local"}
    assert [r["host"] for r in asset_rows("latest")] == ["new.local"]
    assert [r["host"] for r in asset_rows(str(first))] == ["old.local"]
    assert [r["host"] for r in surface(result.slug, request, 25, str(first))] == ["old.local"]
    assert [r["name"] for r in finding_rows("latest")] == ["new"]
    assert [r["name"] for r in finding_rows(str(first))] == ["old"]
    for select in (asset_rows, finding_rows, lambda value: surface(result.slug, request, 25, value)):
        with pytest.raises(ScopeError) as exc:
            select(str(draft))
        assert exc.value.code == "invalid_scan"
