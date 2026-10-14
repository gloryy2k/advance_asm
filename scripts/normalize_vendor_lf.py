"""Normalize image-copy shell scripts; parent gitattributes cannot govern a submodule."""
from pathlib import Path
import sys


def normalize_shell_files(root):
    changed = 0
    for path in Path(root).rglob("*.sh"):
        if path.is_symlink():
            raise ValueError(f"Refusing shell symlink: {path}")
        content = path.read_bytes()
        normalized = content.replace(b"\r\n", b"\n")
        if content != normalized:
            path.write_bytes(normalized)
            changed += 1
    return changed


if __name__ == "__main__":
    print(f"Normalized {normalize_shell_files(sys.argv[1])} shell files to LF")
