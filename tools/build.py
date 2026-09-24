"""Build, validate, budget and publish the canonical .silk catalogue."""

import argparse
import hashlib
import json
import logging
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from species import BY_ID, CATALOGUE
from spun.beads import generate
from spun.kinds import ENV, GLUE, INVISIBLE, SATELLITE, STICKY
from spun.silkfile import NEVER, write_silk
from spun.spider import extent_px, glyph
from spun.validate import validate

WEB = ROOT / "web"
DEST = WEB / "specimens"
INDEX = DEST / "index.json"
VERSION = re.compile(r"(?m)^const VERSION = '[0-9a-f]+';$")
DEFAULT = "st-andrews-cross"

SIGNATURES={
    "golden-orb-weaver":"Upper-third golden hub, retained temporary silk, barrier tangle",
    "st-andrews-cross":"Four zig-zag stabilimentum bands in an X",
    "garden-orb-weaver":"Heavy dusk frame, clear free zone and many capture turns",
    "leaf-curling-spider":"Rolled leaf retreat near the hub",
    "christmas-jewel-spider":"Three shared-support orbs with white silk tufts",
    "scorpion-tailed-spider":"Empty upper V, signal line and seven woolly egg sacs",
    "net-casting-spider":"Small held rectangle of woolly cribellate silk",
    "magnificent-spider":"Single bolas globule below the trapeze and spindle egg sacs",
    "redback-spider":"Timber retreat, dense tangle and glued gumfoot bottoms",
}


def rounded(value):
    """Three decimal places throughout every numeric JSON field, including glyphs."""
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, dict):
        return {key: rounded(item) for key,item in value.items()}
    if isinstance(value, (tuple,list)):
        return [rounded(item) for item in value]
    return value


def _json_bytes(document):
    return (json.dumps(rounded(document), ensure_ascii=False, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def manifest(entries):
    return dict(version=1, defaultSpecimen=DEFAULT,
                stage=dict(background="#05060c", dawn=dict(top="#0b1124",bottom="#1d1521"),
                           glow=dict(radius=14,strength=0.5)),
                specimens=entries)


def build_specimen(species):
    """Single source used by the builder and by render --only when not published."""
    result=species.build()
    records=result.records
    beads=generate(records,species.id,species.r0)
    data=write_silk(result.width,result.height,result.builder_count,records,beads)
    visible=(records["flags"] & INVISIBLE)==0
    silk=visible & ((records["flags"] & ENV)==0) & (records["death"]==NEVER)
    coordinates=np.stack([records["x0"],records["y0"],records["x1"],records["y1"]],axis=-1).astype(float)/4
    length=np.hypot(coordinates[silk,2]-coordinates[silk,0],
                    coordinates[silk,3]-coordinates[silk,1]).sum()*species.mm_per_px/1000
    bounds=[float(np.minimum(coordinates[visible,0],coordinates[visible,2]).min()),
            float(np.minimum(coordinates[visible,1],coordinates[visible,3]).min()),
            float(np.maximum(coordinates[visible,0],coordinates[visible,2]).max()),
            float(np.maximum(coordinates[visible,1],coordinates[visible,3]).max())]
    spiders=[]
    for builder,rest in sorted(result.rest.items()):
        x,y,angle=rest["x"],rest["y"],rest["angle"]
        extent=extent_px(species.id,x,y,angle,species.mm_per_px)
        bounds=[min(bounds[0],extent[0]),min(bounds[1],extent[1]),
                max(bounds[2],extent[2]),max(bounds[3],extent[3])]
        spiders.append(dict(builder=builder,rest=dict(x=x,y=y,angle=angle),
                            pose=rest["pose"],glyph=glyph(species.id)))
    metadata=result.metadata.copy()
    anchor=metadata.get("anchor")
    if anchor is None:
        if species.kind != "snare":
            raise ValueError(f"{species.id}: missing hub anchor metadata")
        anchor=[result.rest[0]["x"],result.rest[0]["y"]]
    entry=dict(id=species.id,name=species.name,scientific=species.scientific,
               kind=species.kind,file=f"{species.stem}.silk",bytes=len(data),
               segments=len(records),beads=len(beads),width=result.width,height=result.height,
               anchor=dict(x=anchor[0],y=anchor[1]),
               bounds=dict(zip(("minX","minY","maxX","maxY"),bounds)),
               durationSeconds=species.duration,timeline=metadata["timeline"],
               stages=metadata["stages"],fadeRecords=6,silkMetres=length,
               mmPerUnit=species.mm_per_px,spiders=spiders)
    # Encode once here so the returned dictionary is exactly what is shipped.
    entry=json.loads(_json_bytes(entry))
    categories=dict(dewPrimaries=int(np.count_nonzero((beads["flags"]==0) &
                               ((records[beads["host"]]["flags"] & STICKY)!=0))),
                    satellites=int(np.count_nonzero((beads["flags"] & SATELLITE)!=0)),
                    dry=int(np.count_nonzero((beads["flags"]==0) &
                            ((records[beads["host"]]["flags"] & STICKY)==0))),
                    glue=int(np.count_nonzero((beads["flags"] & GLUE)!=0)))
    return data,entry,metadata,categories


def content_version():
    sha=hashlib.sha256()
    for file in sorted(WEB.rglob("*"),key=lambda path:path.relative_to(WEB).as_posix()):
        if (not file.is_file() or file==WEB/"sw.js"
                or (WEB/"verification") in file.parents):
            continue
        sha.update(file.relative_to(WEB).as_posix().encode("utf-8")+b"\0")
        sha.update(file.read_bytes())
    return sha.hexdigest()[:16]


def update_service_worker():
    file=WEB/"sw.js"
    text=file.read_text(encoding="utf-8")
    updated,n=VERSION.subn(f"const VERSION = '{content_version()}';",text)
    if n!=1:
        raise ValueError(f"expected exactly one VERSION line in {file}")
    if updated!=text:
        file.write_text(updated,encoding="utf-8")


def _read_entries():
    if not INDEX.exists():
        return {}
    document=json.loads(INDEX.read_text(encoding="utf-8"))
    return {entry["id"]:entry for entry in document["specimens"] if entry["id"] in BY_ID}


def build(only=None, output=DEST):
    """Publish all catalogue entries or merge one; return entries and failures."""
    output.mkdir(parents=True,exist_ok=True)
    index_path=output/"index.json"
    existing=({id:entry for id,entry in _read_entries().items()
               if (output/entry["file"]).exists()} if only is not None and output==DEST else {})
    candidates={}
    failures=[]
    selection=[BY_ID[only]] if only else CATALOGUE
    print("id | segments | beads | bytes | B/segment | silk m | duration | builders | stages | checks")
    for species in selection:
        try:
            data,entry,metadata,counts=build_specimen(species)
            candidates[species.id]=(data,entry,metadata,counts)
        except Exception as exc:
            failures.append(species.id)
            print(f"{species.id} | FAIL | {type(exc).__name__}: {exc}",file=sys.stderr)
    accepted=dict(existing)
    for species in selection:
        built=candidates.get(species.id)
        if built is None:
            continue
        data,entry,metadata,counts=built
        proposed={**accepted,species.id:entry}
        proposed_entries=[proposed[item.id] for item in CATALOGUE if item.id in proposed]
        index_data=_json_bytes(manifest(proposed_entries))
        total=sum(item["bytes"] for item in proposed_entries)
        default_size=proposed.get(DEFAULT,{}).get("bytes",0)
        metadata={**metadata,"catalogueBytes":total,"indexBytes":len(index_data),"defaultBytes":default_size}
        try:
            validate(data,metadata)
        except Exception as exc:
            failures.append(species.id)
            print(f"{species.id} | FAIL | {type(exc).__name__}: {exc}",file=sys.stderr)
            continue
        (output/entry["file"]).write_bytes(data)
        accepted=proposed
        print(f"{species.id} | {entry['segments']} | {entry['beads']} | {len(data)} | "
              f"{len(data)/entry['segments']:.2f} | {entry['silkMetres']:.3f} | "
              f"{entry['durationSeconds']}s | {len(entry['spiders'])} | "
              f"{len(entry['stages'])} | Rules 1–9 PASS "
              f"(dew {counts['dewPrimaries']}, satellites {counts['satellites']}, "
              f"dry {counts['dry']}, glue {counts['glue']})")
    entries=[accepted[item.id] for item in CATALOGUE if item.id in accepted]
    index_path.write_bytes(_json_bytes(manifest(entries)))
    if only is None:
        expected={entry["file"] for entry in entries}
        for file in output.iterdir():
            if file.suffix==".silk" and file.name not in expected:
                file.unlink()
    if output==DEST:
        update_service_worker()
    return entries,failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only",choices=list(BY_ID))
    parser.add_argument("--list",action="store_true")
    parser.add_argument("--markdown",action="store_true")
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.list:
        for specimen in CATALOGUE:
            print(specimen.id)
        return 0
    if args.markdown:
        if not INDEX.exists():
            parser.error("build the catalogue before requesting --markdown")
        entries=_read_entries()
        print("| Spider | Scientific name | Kind | File | Signature | Rest | Segments | Beads | Silk (m) | Bytes |")
        print("|---|---|---|---|---|---|---:|---:|---:|---:|")
        for specimen in CATALOGUE:
            entry=entries.get(specimen.id)
            if entry:
                pose=specimen.pose+(" ×3" if len(entry["spiders"])==3 else "")
                print(f"| {specimen.name} | *{specimen.scientific}* | {entry['kind']} | "
                      f"`{entry['file']}` | {SIGNATURES[specimen.id]} | {pose} | "
                      f"{entry['segments']:,} | {entry['beads']:,} | "
                      f"{entry['silkMetres']:.1f} | {entry['bytes']:,} |")
        return 0
    entries,failures=build(args.only)
    return 1 if failures else 0


if __name__=="__main__":
    raise SystemExit(main())
