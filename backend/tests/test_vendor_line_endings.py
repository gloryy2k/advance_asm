from scripts.normalize_vendor_lf import normalize_shell_files


def test_normalize_shell_crlf_is_idempotent_and_preserves_other_files(tmp_path):
    scripts = tmp_path / "tools"
    scripts.mkdir()
    shell = scripts / "engine.sh"
    shell.write_bytes(b"#!/bin/bash\r\nset -euo pipefail\r\necho ok\r\n")
    shell.chmod(0o755)
    mode = shell.stat().st_mode
    other = scripts / "data.bin"
    other.write_bytes(b"\x00\r\n\xff")
    assert normalize_shell_files(tmp_path) == 1
    assert shell.read_bytes() == b"#!/bin/bash\nset -euo pipefail\necho ok\n"
    assert shell.stat().st_mode == mode
    assert other.read_bytes() == b"\x00\r\n\xff"
    assert normalize_shell_files(tmp_path) == 0
