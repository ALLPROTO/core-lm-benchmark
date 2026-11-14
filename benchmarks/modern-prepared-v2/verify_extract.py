#!/usr/bin/env python3
"""Verify frozen delivery and extract into a NEW directory. Does not execute it."""
import argparse, hashlib, json, pathlib, zipfile
SHA256 = 'cca62c180509da48436da82a68eb7a9aba3adbb8da6cb72834fde806b40c89d4'
p = argparse.ArgumentParser()
p.add_argument('--destination', required=True, type=pathlib.Path)
a = p.parse_args()
zpath = pathlib.Path(__file__).with_name('Core-LM-modern-prepared-v2.zip')
assert hashlib.sha256(zpath.read_bytes()).hexdigest() == SHA256, 'Archive hash mismatch'
assert not a.destination.exists(), 'Destination exists; refusing overwrite'
with zipfile.ZipFile(zpath) as z:
    names = z.namelist()
    assert len(names) == len(set(names)), 'Duplicate members'
    for name in names:
        q = pathlib.PurePosixPath(name)
        assert not q.is_absolute() and '..' not in q.parts, 'Unsafe archive path'
    manifest = json.loads(z.read('MANIFEST.json'))
    expected = {x['path'] for x in manifest['files']} | {'MANIFEST.json'}
    assert set(names) == expected, 'Unregistered archive members'
    for entry in manifest['files']:
        data = z.read(entry['path'])
        assert len(data) == entry['bytes'], entry['path']
        assert hashlib.sha256(data).hexdigest() == entry['sha256'], entry['path']
    z.extractall(a.destination)
for entry in manifest['files']:
    data = (a.destination / entry['path']).read_bytes()
    assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256'], entry['path']
print(f'Verified archive and {len(manifest["files"])} files at {a.destination}; no GPU test executed.')
