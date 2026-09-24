"""The binary catalogue is reproducible and fits the shipped byte budgets."""

import hashlib
import json

from species import CATALOGUE
from tools.build import build


def hashes(directory):
    return {file.name:hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(directory.iterdir()) if file.is_file()}


def test_two_catalogue_builds_byte_identical_and_within_budgets(tmp_path):
    entries,failures=build(output=tmp_path)
    assert not failures
    assert [entry["id"] for entry in entries]==[species.id for species in CATALOGUE]
    first=hashes(tmp_path)
    second,failures=build(output=tmp_path)
    assert not failures
    assert first==hashes(tmp_path)
    index=json.loads((tmp_path/"index.json").read_text(encoding="utf-8"))
    assert len(index["specimens"])==len(CATALOGUE)
    assert sum(entry["bytes"] for entry in entries)<=3*1024*1024
    assert all(entry["bytes"]<=640*1024 and entry["beads"]<=32000
               and len(entry["timeline"])==512 and
               entry["stages"][-1]=={"label":"at rest","start":entry["segments"]}
               for entry in entries)
    default=next(entry for entry in entries if entry["id"]==index["defaultSpecimen"])
    assert (tmp_path/"index.json").stat().st_size+default["bytes"]<=400*1024
    assert all((tmp_path/entry["file"]).stat().st_size==entry["bytes"] for entry in entries)
