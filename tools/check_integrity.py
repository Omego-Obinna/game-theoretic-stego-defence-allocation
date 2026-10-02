"""Check SHA-256 inventories without touching the research files."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((ROOT / 'provenance_manifest.json').read_text())
    for row in manifest['scientific_files']:
        p = ROOT / row['path']
        if not p.is_file() or sha(p) != row['packaged_sha256']:
            raise RuntimeError(f'Scientific-file integrity failure: {row["path"]}')
    inventory = ROOT / 'CHECKSUMS.sha256'
    count = 0
    if inventory.exists():
        for line in inventory.read_text().splitlines():
            expected, name = line.split('  ', 1)
            p = ROOT / name
            if not p.is_file() or sha(p) != expected:
                raise RuntimeError(f'Package-file integrity failure: {name}')
            count += 1
    print(f'PASS: {len(manifest["scientific_files"])} research fingerprints; {count} package files.')


if __name__ == '__main__':
    main()
