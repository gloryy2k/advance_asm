"""BACKLOG mục 4: "Đường dẫn dò được" / "Cổng/Dịch vụ" là bảng dữ liệu riêng, không chỉ đọc lúc dựng Run.

/api/programs/{slug}/ports và /{slug}/dirs đọc đúng thư mục scan trên đĩa bằng cùng hàm backend.asm.results
mà Run dùng (results.summarize_ports/summarize_dirs) — không có bảng DB riêng cho dữ liệu này."""
import json

from fastapi.testclient import TestClient

from backend.asm.phases import scan_root
from backend.main import create_app
from backend.tests.p2_helpers import environment, write_output

GREP = ("# Nmap 7.94 scan initiated\n"
        "Host: 192.0.2.10 (api.example.com)\tPorts: 80/open/tcp//http//nginx/, 443/open/tcp//ssl|http//nginx/\tIgnored State: filtered (998)\n"
        "# Nmap done at Thu Oct 17 00:00:00 2026 -- 1 IP address (1 host up) scanned in 10.00 seconds\n")


def ffuf_payload(host, rows):
    return json.dumps({"commandline": f"ffuf -u https://{host}/FUZZ", "config": {"autocalibration": True}, "results": [
        {"input": {"FUZZ": name}, "status": status, "length": length, "words": words, "url": f"https://{host}/{name}", "host": host}
        for name, status, length, words in rows]})


def _slug_and_scan(settings):
    db, _, result = environment(settings, ["example.com"])
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (result.scan_id,))
        slug = conn.execute("SELECT p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?", (result.scan_id,)).fetchone()[0]
    return db, slug, result.scan_id


def test_ports_endpoint_reads_the_scans_own_nmap_output(settings):
    db, slug, scan_id = _slug_and_scan(settings)
    root = scan_root(settings, slug, scan_id)
    write_output(root, "4/ports/nmap_greppable.txt", GREP)
    with TestClient(create_app(settings)) as client:
        body = client.get(f"/api/programs/{slug}/ports").json()
        assert body["scan_id"] == scan_id and body["hosts"] == 1 and body["unique_ports"] == 2 and body["complete"] is True
        assert {(p["host"], p["port"]) for p in body["rows"]} == {("api.example.com", 80), ("api.example.com", 443)}
        # a specific scan number resolves the same way "latest" does when there is only one scan
        same = client.get(f"/api/programs/{slug}/ports?scan={scan_id}").json()
        assert same["rows"] == body["rows"]
        assert client.get(f"/api/programs/{slug}/ports?scan=999999").json() == {
            "found": False, "scan_id": None, "pairs": [], "hosts": 0, "unique_ports": 0, "complete": False,
            "files": [], "rows": [], "cdn": [], "cdn_hosts": [], "cdn_pairs": 0}


def test_dirs_endpoint_reads_the_scans_own_ffuf_output_noise_already_removed(settings):
    db, slug, scan_id = _slug_and_scan(settings)
    root = scan_root(settings, slug, scan_id)
    write_output(root, "4/dirs/ffuf_api.json", ffuf_payload("api.example.com",
                 [(f"p{i}", 403, 4547, 656) for i in range(24)] + [("admin", 200, 812, 40)]))
    with TestClient(create_app(settings)) as client:
        body = client.get(f"/api/programs/{slug}/dirs").json()
        assert body["scan_id"] == scan_id and body["total"] == 25 and body["noise"] == 24 and body["significant"] == 1
        assert body["hosts"][0]["significant"][0]["url"].endswith("/admin")


def test_ports_and_dirs_return_empty_shape_with_no_scan_yet(settings):
    db, _, result = environment(settings, ["nodata.example.com"])     # draft scan: no 'done'/'done_partial' yet
    with db.connect() as conn:
        slug = conn.execute("SELECT p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?", (result.scan_id,)).fetchone()[0]
    with TestClient(create_app(settings)) as client:
        body = client.get(f"/api/programs/{slug}/ports").json()
        assert body["found"] is False and body["pairs"] == []
        assert client.get(f"/api/programs/{slug}/dirs").json()["found"] is False


def test_invalid_scan_param_is_rejected(settings):
    db, slug, scan_id = _slug_and_scan(settings)
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/programs/{slug}/ports?scan=not-a-number").status_code == 422
