"""Derive all shipped PWA icons from an actual reference orb's frozen records."""

from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageFilter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from species import BY_ID
from spun.kinds import BY_NAME, ENV, INVISIBLE
from spun.silkfile import NEVER
from tools.render import _stroke

DEST=ROOT/"web"/"icons"


def orb_lines():
    result=BY_ID["garden-orb-weaver"].build()
    rows=result.records
    allowed=tuple(BY_NAME[name].id for name in ("FRAME","RADIUS","HUB","CAPTURE"))
    eligible=(rows["death"]==NEVER)&((rows["flags"]&(ENV|INVISIBLE))==0)&np.isin(rows["kind"],allowed)
    return rows[eligible]


def _project(rows,size,maskable):
    coords=np.stack((rows["x0"],rows["y0"],rows["x1"],rows["y1"]),axis=-1).astype(float)/4
    bounds=(min(coords[:,0].min(),coords[:,2].min()),
            min(coords[:,1].min(),coords[:,3].min()),
            max(coords[:,0].max(),coords[:,2].max()),
            max(coords[:,1].max(),coords[:,3].max()))
    diameter=size*(.76 if maskable else .86)
    midx=(bounds[0]+bounds[2])/2
    midy=(bounds[1]+bounds[3])/2
    scale=min(diameter/(bounds[2]-bounds[0]),diameter/(bounds[3]-bounds[1]))
    if maskable:
        radius=np.hypot(coords[:,[0,2]]-midx,coords[:,[1,3]]-midy).max()
        scale=min(scale,(size*.4-8)/radius)
    projected=rows.copy()
    for source,dest,mid in (("x0","x0",midx),("x1","x1",midx),
                            ("y0","y0",midy),("y1","y1",midy)):
        projected[dest]=np.rint((coords[:,list(("x0","y0","x1","y1")).index(source)]-mid)*scale*4+size*2).astype(np.uint16)
    projected["width"]=np.maximum(1,np.rint(rows["width"].astype(float)*scale)).astype(np.uint8)
    return projected


def _png(rows,size,maskable):
    projected=_project(rows,size,maskable)
    layer=Image.new("RGBA",(size*4,size*4),(0,0,0,0))
    for row in projected:
        _stroke(layer,row)
    sharp=layer.resize((size,size),Image.Resampling.LANCZOS)
    glow=sharp.filter(ImageFilter.GaussianBlur(size*14/1200))
    canvas=Image.new("RGBA",(size,size),(5,6,12,255))
    canvas.alpha_composite(glow.point(lambda v: int(v*.32)))
    canvas.alpha_composite(sharp)
    return canvas.convert("RGB")


def _svg(rows):
    # The 16 px icon wants the source orb's *structure*, not every microscopic
    # turn. Keep intact capture turns: skipping their internal vertices cuts
    # across the spiral instead of following it.
    mapped=_project(rows,128,False)
    lines=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">',
           '<rect width="128" height="128" fill="#05060c"/>']
    for name,keep,step,stroke in (("FRAME",1,2,1.5),("RADIUS",1,8,1.10),
                                  ("HUB",1,4,1.6),("CAPTURE",2,1,1.0)):
        selected=mapped[mapped["kind"]==BY_NAME[name].id]
        commands=[]
        begin=0
        run_number=0
        for end in range(1,len(selected)+1):
            if (end<len(selected) and selected[end-1]["x1"]==selected[end]["x0"]
                    and selected[end-1]["y1"]==selected[end]["y0"]):
                continue
            if run_number%keep==0:
                run=selected[begin:end]
                first=run[0]
                commands.append(f'M{int(first["x0"])/4:.1f} {int(first["y0"])/4:.1f}')
                for row in run[step-1::step]:
                    commands.append(f'L{int(row["x1"])/4:.1f} {int(row["y1"])/4:.1f}')
                last=run[-1]
                final=f'L{int(last["x1"])/4:.1f} {int(last["y1"])/4:.1f}'
                if not commands[-1]==final:
                    commands.append(final)
            run_number+=1
            begin=end
        first=selected[0]
        rgb=f'#{int(first["r"]):02x}{int(first["g"]):02x}{int(first["b"]):02x}'
        alpha=int(first["alpha"])/255
        lines.append(f'<path d="{"".join(commands)}" fill="none" stroke="{rgb}" '
                     f'stroke-width="{stroke:.2f}" stroke-opacity="{alpha:.2f}" '
                     'stroke-linecap="round" stroke-linejoin="round"/>')
    lines.append('</svg>')
    return ('\n'.join(lines)+'\n').encode('utf-8')


def main():
    DEST.mkdir(parents=True,exist_ok=True)
    rows=orb_lines()
    (DEST/"favicon.svg").write_bytes(_svg(rows))
    for filename,size,maskable in (("apple-touch-icon.png",180,False),
                                   ("icon-192.png",192,False),
                                   ("icon-512.png",512,False),
                                   ("icon-maskable-512.png",512,True)):
        _png(rows,size,maskable).save(DEST/filename,optimize=True)
        print((DEST/filename).relative_to(ROOT).as_posix())
    print((DEST/"favicon.svg").relative_to(ROOT).as_posix())


if __name__=="__main__":
    main()
