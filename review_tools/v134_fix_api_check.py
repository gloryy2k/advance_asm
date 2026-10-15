"""QA localhost only: read exports and test reversible schedule/profile CRUD, no scan launch."""
import io
import json
import time
import zipfile
import httpx

BASE = "http://127.0.0.1:18765"
client = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
result = {}
name = f"qa-v134-fixcheck-{int(time.time())}"
profile_id = None
schedule_enabled = False

def send(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response

try:
    for mode in ("brief", "filtered", "full"):
        response = send("GET", f"/api/programs/wolt/export?mode={mode}")
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            files = archive.namelist()
            assert archive.testzip() is None
            manifest_name = next(x for x in files if x.endswith("MANIFEST.json"))
            manifest = json.loads(archive.read(manifest_name))
            assert manifest["recon"]["mode"] == mode
            result["zip_" + mode] = {"http": response.status_code, "files": len(files),
                                     "has_manifest": True,
                                     "has_recon": any("/recon/" in "/" + x for x in files),
                                     "bytes": len(response.content),
                                     "manifest_scan_id": manifest["scan_id"],
                                     "manifest_recon_mode": manifest["recon"]["mode"]}
    response = send("GET", "/api/programs/wolt/urls/export?scan=all&min_score=0")
    lines = [x for x in response.text.splitlines() if x]
    result["txt_all"] = {"http": response.status_code, "lines": len(lines),
                         "filename": response.headers.get("content-disposition"),
                         "all_wolt": all("wolt" in x.lower() for x in lines)}
    everything = send("GET", "/api/programs/wolt/urls/export?scan=all&min_score=0&include_static=true")
    result["txt_all"]["including_static_lines"] = len([x for x in everything.text.splitlines() if x])

    slug = "qa-v134-ui"
    before = send("GET", f"/api/programs/{slug}/summary").json()
    assert not (before.get("schedule") or {}).get("enabled"), "QA schedule already enabled"
    scans_before = len(send("GET", f"/api/programs/{slug}").json().get("scans", []))
    active = send("POST", f"/api/programs/{slug}/schedule", json={
        "interval": "weekly", "depth": "passive", "enabled": True, "automation_ack": False,
    }).json()
    schedule_enabled = True
    running = send("GET", f"/api/programs/{slug}/summary").json()["schedule"]
    assert running["enabled"] and running["depth"] == "passive"
    assert active["next_run_at"] > active["created_at"]
    stopped = send("POST", f"/api/programs/{slug}/schedule", json={
        "interval": "weekly", "depth": "passive", "enabled": False,
    }).json()
    schedule_enabled = False
    after = send("GET", f"/api/programs/{slug}/summary").json()["schedule"]
    scans_after = len(send("GET", f"/api/programs/{slug}").json().get("scans", []))
    result["schedule"] = {"enabled_seen": running["enabled"], "disabled_seen": not after["enabled"],
                          "scan_count_before": scans_before, "scan_count_after": scans_after,
                          "next_run_at": active["next_run_at"]}
    assert scans_before == scans_after

    made = send("POST", "/api/profiles", json={"name": name, "description": "temporary QA", "based_on": "passive", "config": {}}).json()
    profile_id = made["id"]
    edited = send("PUT", f"/api/profiles/{profile_id}", json={"name": name, "description": "edited QA", "based_on": "passive", "config": {"threads": 1}}).json()
    listed = send("GET", "/api/profiles").json()["custom"]
    assert any(x["id"] == profile_id and x["description"] == "edited QA" and x["config"]["threads"] == 1 for x in listed)
    send("DELETE", f"/api/profiles/{profile_id}")
    profile_id = None
    listed_after = send("GET", "/api/profiles").json()["custom"]
    result["profile"] = {"created": made["id"], "edited_description": edited["description"],
                         "edited_threads": edited["config"]["threads"],
                         "deleted": not any(x["name"] == name for x in listed_after)}
finally:
    if schedule_enabled:
        send("POST", "/api/programs/qa-v134-ui/schedule", json={"interval": "weekly", "depth": "passive", "enabled": False})
    if profile_id is not None:
        send("DELETE", f"/api/profiles/{profile_id}")
    client.close()

print(json.dumps(result, ensure_ascii=True, indent=2))
