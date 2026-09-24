"""Rayleigh–Plateau spacing, paired thinning, and bead host eligibility."""

import math

import numpy as np
import pytest

from spun import beads
from spun.kinds import BY_NAME, ENV, GLUE, INVISIBLE, LURE, SATELLITE, STICKY
from spun.silkfile import NEVER, RECORD_DTYPE


def records(*data):
    rows=np.zeros(len(data), dtype=RECORD_DTYPE)
    for i,(x0,x1,kind,flags,death) in enumerate(data):
        rows[i]=(x0,40,x1,40,death,BY_NAME[kind].id,24,230,240,248,255,flags,220)
    return rows


def test_wavelength_and_conserved_volume():
    rng=np.random.default_rng(19)
    radii=np.array([beads.coating_radius(1.,rng) for _ in range(4000)])
    assert np.median(radii)==pytest.approx(1.,rel=.025)
    wavelengths=np.array([beads.spacing(1.,rng) for _ in range(200)])
    assert np.all(wavelengths >= .9*2*math.pi*math.sqrt(2))
    assert np.all(wavelengths <= 1.1*2*math.pi*math.sqrt(2))
    b=beads.primary_radius(1.,2*math.pi*math.sqrt(2))
    assert b==pytest.approx((.75* .91 *2*math.pi*math.sqrt(2))**(1/3))
    assert b==pytest.approx(1.82,rel=.08)


def test_satellite_volume_and_sorted_deterministic_output():
    rows=records((0,1000,"CAPTURE",STICKY,NEVER))
    first=beads.generate(rows,"st-andrews-cross",.9)
    second=beads.generate(rows,"st-andrews-cross",.9)
    assert first.tobytes()==second.tobytes()
    primary=first[(first["flags"] & SATELLITE)==0]
    satellites=first[(first["flags"] & SATELLITE)!=0]
    assert len(primary)>15 and len(satellites)>5
    for sat in satellites:
        nearby=primary[np.abs(primary["t"].astype(int)-int(sat["t"]))<5000]
        assert len(nearby)>=1
        assert any(int(sat["radius"])==pytest.approx(.28*int(p["radius"]),abs=1)
                   for p in nearby)
    assert all((int(a["host"]),int(a["t"]))<=(int(b["host"]),int(b["t"]))
               for a,b in zip(first,first[1:]))



def test_sparse_dry_droplets_are_smaller_than_capture_droplets():
    sticky=beads.generate(records((0,3000,"CAPTURE",STICKY,NEVER)),
                          "golden-orb-weaver",1.)
    dry=beads.generate(records((0,3000,"FRAME",0,NEVER)),
                       "golden-orb-weaver",1.)
    sticky_primary=sticky[sticky["flags"]==0]
    assert 0<len(dry)<.25*len(sticky_primary)
    assert not np.any(dry["flags"] & SATELLITE)
    assert np.median(dry["radius"])<np.median(sticky_primary["radius"])
    assert beads.primary_radius(.8,2*math.pi*math.sqrt(2)*.8) < (
        beads.primary_radius(1.,2*math.pi*math.sqrt(2)))

def test_no_beads_on_environment_walk_or_dying_hosts():
    rows=records((0,500,"CAPTURE",STICKY,NEVER),
                 (0,500,"CAPTURE",STICKY,4),
                 (0,500,"SCAFFOLD",ENV,NEVER),
                 (0,500,"WALK",INVISIBLE,NEVER),
                 (0,500,"GUMFOOT",STICKY,NEVER),
                 (0,500,"BOLAS",STICKY,NEVER))
    out=beads.generate(rows,"redback-spider",1.)
    assert set(out["host"]) == {0,4,5}
    assert all(rows[int(b["host"])]["flags"] & STICKY for b in out if b["flags"] & GLUE)
    assert all(b["flags"] & GLUE for b in out if b["host"] in (4,5))
    assert len(out[(out["flags"] & LURE)!=0])==1
    assert out[(out["flags"] & LURE)!=0]["t"].tolist()==[65535]


def test_budget_preserves_glue_and_primary_satellite_pairs(monkeypatch):
    source=records((0,6000,"CAPTURE",STICKY,NEVER),
                   (0,800,"GUMFOOT",STICKY,NEVER))
    full=beads.generate(source,"redback-spider",.75)
    monkeypatch.setattr(beads,"_MAX_BEADS",63)
    thin=beads.generate(source,"redback-spider",.75)
    assert len(thin)<=63
    assert len(thin[(thin["flags"] & GLUE)!=0])==len(full[(full["flags"] & GLUE)!=0])
    missing={int(b["t"]) for b in full if not b["flags"] & SATELLITE and b["host"]==0}
    included={int(b["t"]) for b in thin if not b["flags"] & SATELLITE and b["host"]==0}
    assert len(included)<len(missing)
    primary_t=sorted(missing)
    for bead in thin:
        if bead["flags"] & SATELLITE:
            t=int(bead["t"])
            prev=max(p for p in primary_t if p<t)
            following=min(p for p in primary_t if p>t)
            assert following in included
