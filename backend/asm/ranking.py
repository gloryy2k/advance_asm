"""Deterministic §12.3 ranking. Each feature contributes at most once."""
import json
import re


def score_asset(asset, scan_id, urls=(), severities=()):
    text = " ".join([asset["host"], asset.get("title") or "", *urls]).lower()
    tech = " ".join(json.loads(asset.get("tech_json") or "[]")).lower()
    score, reasons = 0.0, []

    def add(condition, weight, reason):
        nonlocal score
        if condition:
            score += weight
            reasons.append(reason)

    add(bool(re.search(r"\b(api|graphql|v1|v2|rest)\b", text + " " + tech)), 2.5, "api")
    add(bool(re.search(r"\b(login|sso|oauth|admin|account)\b", text)), 2.0, "auth")
    add(asset["first_seen_scan"] == scan_id, 1.5, "fresh")
    risks = [t for t in ("graphql", "flask", "express", "wordpress", "jenkins", "gitlab", "grafana", "s3", "firebase") if t in tech]
    add(bool(risks), 1.5, "tech_risk")
    reasons.extend(risks)
    if set(severities) & {"medium", "high", "critical"}:
        add(True, 2.0, "nuclei_medium_plus")
    else:
        add("low" in severities, 1.0, "nuclei_low")
    add(asset.get("status_code") == 200, 0.5, "status_200")
    add(asset.get("status_code") in {401, 403}, 1.0, "status_restricted")
    add(bool(re.search(r"\b(dev|staging|test|internal)\b", asset["host"].lower())), 1.0, "nonproduction")
    return min(10.0, max(0.0, score)), reasons


def rank_program(database, program_id, scan_id):
    with database.connect() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        for row in conn.execute("SELECT * FROM asset WHERE program_id=?", (program_id,)).fetchall():
            if row["state"] == "gone":
                score, reasons = 0.0, []
            else:
                urls = [r[0] for r in conn.execute("SELECT url FROM url WHERE asset_id=? AND last_seen_scan=?", (row["id"], scan_id))]
                severity = [r[0] for r in conn.execute("SELECT severity FROM finding WHERE asset_id=? AND type='nuclei' AND last_seen_scan=?", (row["id"], scan_id))]
                score, reasons = score_asset(dict(row), scan_id, urls, severity)
            conn.execute("UPDATE asset SET rank_score=?,rank_reasons_json=? WHERE id=?", (score, json.dumps(reasons), row["id"]))
