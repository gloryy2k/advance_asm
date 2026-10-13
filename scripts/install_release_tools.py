"""Install pinned Linux release binaries; never execute downloads at build time."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import struct
import tarfile
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
import zipfile

MACHINES = {"amd64": 62, "arm64": 183}


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(pin, cache):
    """Cache only verified archives, so interrupted builds reuse downloads."""
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / pin["sha256"]
    if destination.exists():
        if checksum(destination) != pin["sha256"]:
            raise ValueError(f"Cached release checksum mismatch: {destination}")
        return destination
    for attempt in range(3):
        path = None
        try:
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as temporary:
                path = Path(temporary.name)
                with urlopen(pin["url"], timeout=60) as response:
                    shutil.copyfileobj(response, temporary)
            if checksum(path) != pin["sha256"]:
                raise ValueError(f"Release checksum mismatch: {pin['url']}")
            path.replace(destination)
            return destination
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
        finally:
            if path:
                path.unlink(missing_ok=True)


def extract_binary(archive, binary, output, arch):
    """Read one regular member; never extract archive paths or links to disk."""
    def copy_member(source):
        header = source.read(20)
        if (len(header) != 20 or header[:4] != b"\x7fELF" or header[4:6] != b"\x02\x01"
                or struct.unpack("<H", header[18:20])[0] != MACHINES[arch]):
            raise ValueError(f"Expected Linux {arch} ELF binary: {binary}")
        output.write(header)
        shutil.copyfileobj(source, output)

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            members = [m for m in bundle.infolist() if Path(m.filename).name == binary and not m.is_dir()]
            if len(members) != 1 or stat.S_ISLNK(members[0].external_attr >> 16):
                raise ValueError(f"Expected one regular {binary} archive member")
            with bundle.open(members[0]) as source:
                copy_member(source)
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            members = [m for m in bundle.getmembers() if Path(m.name).name == binary]
            if len(members) != 1 or not members[0].isfile():
                raise ValueError(f"Expected one regular {binary} archive member")
            with bundle.extractfile(members[0]) as source:
                copy_member(source)


def install(manifest, arch, destination, cache):
    if arch not in MACHINES:
        raise ValueError(f"Unsupported architecture: {arch}; supported: amd64, arm64")
    destination.mkdir(parents=True, exist_ok=True)
    for name, tool in manifest["tools"].items():
        binary = tool["binary"]
        if Path(binary).name != binary or binary in {".", ".."}:
            raise ValueError("Invalid binary name")
        pin = tool["platforms"][arch]
        print(f"Installing {name} {tool['version']} linux/{arch}", flush=True)
        archive = download(pin, cache)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination, delete=False) as output:
                temporary = Path(output.name)
                extract_binary(archive, binary, output, arch)
            temporary.chmod(0o755)
            temporary.replace(destination / binary)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("tool-releases.json"))
    parser.add_argument("--arch", required=True, choices=list(MACHINES))
    parser.add_argument("--destination", type=Path, default=Path("/out"))
    parser.add_argument("--cache", type=Path, default=Path("/var/cache/bbasm-releases"))
    parser.add_argument("--tool", help="Install only this manifest entry (for independent Docker layer caching)")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if args.tool:
        if args.tool not in manifest["tools"]:
            parser.error(f"Unknown pinned tool: {args.tool}")
        manifest["tools"] = {args.tool: manifest["tools"][args.tool]}
    install(manifest, args.arch, args.destination, args.cache)
