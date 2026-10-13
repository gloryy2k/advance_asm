"""Offline archive fixtures; never download or execute a real recon tool."""
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tarfile
from unittest.mock import Mock
from urllib.error import URLError
import zipfile

import pytest

from scripts import install_release_tools as installer


def elf(arch="amd64"):
    return b"\x7fELF\x02\x01" + bytes(12) + struct.pack("<H", installer.MACHINES[arch]) + b"fixture-only"


def bundle(kind, binary, *, member="nested/demo", duplicate=False, link=False):
    stream = io.BytesIO()
    if kind == "zip":
        with zipfile.ZipFile(stream, "w") as archive:
            info = zipfile.ZipInfo(member)
            if link:
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, binary)
            if duplicate:
                archive.writestr("other/demo", binary)
            archive.writestr("../../unexpected.txt", "must not extract")
    else:
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            info = tarfile.TarInfo(member)
            info.size = len(binary)
            if link:
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                info.size = 0
            archive.addfile(info, io.BytesIO(binary))
            if duplicate:
                info = tarfile.TarInfo("other/demo")
                info.size = len(binary)
                archive.addfile(info, io.BytesIO(binary))
    return stream.getvalue()


def manifest(payload, digest=None):
    pin = {"url": "https://github.com/fixture/releases/download/v1/demo.zip",
           "sha256": digest or hashlib.sha256(payload).hexdigest()}
    return {"tools": {"demo": {"version": "v1", "binary": "demo",
                               "platforms": {arch: pin for arch in installer.MACHINES}}}}


@pytest.mark.parametrize("kind", ["zip", "tar"])
@pytest.mark.parametrize("arch", ["amd64", "arm64"])
def test_installs_exact_member_and_reuses_verified_cache(tmp_path, monkeypatch, kind, arch):
    content = elf(arch)
    payload = bundle(kind, content)
    request = Mock(side_effect=lambda *a, **k: io.BytesIO(payload))
    monkeypatch.setattr(installer, "urlopen", request)
    out, cache = tmp_path / "out", tmp_path / "cache"
    installer.install(manifest(payload), arch, out, cache)
    assert (out / "demo").read_bytes() == content
    assert list(out.iterdir()) == [out / "demo"]
    assert not (tmp_path / "unexpected.txt").exists()
    installer.install(manifest(payload), arch, out, cache)
    assert request.call_count == 1


def test_digest_mismatch_fails_before_install_and_preserves_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "urlopen", lambda *a, **k: io.BytesIO(b"tampered"))
    out = tmp_path / "out"
    out.mkdir()
    (out / "demo").write_bytes(b"existing")
    with pytest.raises(ValueError, match="checksum mismatch"):
        installer.install(manifest(b"expected"), "amd64", out, tmp_path / "cache")
    assert (out / "demo").read_bytes() == b"existing"
    assert not list((tmp_path / "cache").iterdir())


@pytest.mark.parametrize("kind", ["zip", "tar"])
@pytest.mark.parametrize("problem", ["link", "duplicate", "wrong_arch", "missing"])
def test_rejects_ambiguous_or_invalid_binary(tmp_path, monkeypatch, kind, problem):
    payload = bundle(kind, elf("arm64" if problem == "wrong_arch" else "amd64"),
                     member="absent" if problem == "missing" else "nested/demo",
                     duplicate=problem == "duplicate", link=problem == "link")
    monkeypatch.setattr(installer, "urlopen", lambda *a, **k: io.BytesIO(payload))
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="Expected"):
        installer.install(manifest(payload), "amd64", out, tmp_path / "cache")
    assert not list(out.iterdir())


def test_retries_transport_error_but_never_caches_partial_download(tmp_path, monkeypatch):
    payload = bundle("zip", elf())
    request = Mock(side_effect=[URLError("offline"), io.BytesIO(payload)])
    monkeypatch.setattr(installer, "urlopen", request)
    monkeypatch.setattr(installer.time, "sleep", lambda _: None)
    installer.install(manifest(payload), "amd64", tmp_path / "out", tmp_path / "cache")
    assert request.call_count == 2
    assert len(list((tmp_path / "cache").iterdir())) == 1


def test_corrupt_cache_and_unsupported_arch_fail_closed(tmp_path, monkeypatch):
    request = Mock()
    monkeypatch.setattr(installer, "urlopen", request)
    plan = manifest(b"original")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / plan["tools"]["demo"]["platforms"]["amd64"]["sha256"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Cached release checksum"):
        installer.install(plan, "amd64", tmp_path / "out", cache)
    with pytest.raises(ValueError, match="Unsupported architecture"):
        installer.install(plan, "386", tmp_path / "out", cache)
    request.assert_not_called()


def test_committed_manifest_has_pinned_https_releases_for_both_architectures():
    plan = json.loads(Path(installer.__file__).with_name("tool-releases.json").read_text())
    assert len(plan["tools"]) == 9
    for name, tool in plan["tools"].items():
        assert tool["binary"] == name
        assert set(tool["platforms"]) == {"amd64", "arm64"}
        for pin in tool["platforms"].values():
            assert pin["url"].startswith("https://github.com/")
            assert "/releases/download/" + tool["version"] + "/" in pin["url"]
            assert len(bytes.fromhex(pin["sha256"])) == 32
