"""Render final-state plates, catalogue and timeline video from shipped .silk data."""

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from species import BY_ID
from spun.kinds import BUILDER_MASK, BUILDER_SHIFT, ENV, GLUE, INVISIBLE, STICKY
from spun.silkfile import NEVER, read_silk

SUPERSAMPLE=4
BACKGROUND=(5,6,12)
INDEX=ROOT/"web"/"specimens"/"index.json"


def _stroke(layer,row,multiplier=SUPERSAMPLE,fraction=1,fade=1):
    x0,y0,x1,y1=(int(row[key])/4*multiplier for key in ("x0","y0","x1","y1"))
    x1=x0+(x1-x0)*fraction
    y1=y0+(y1-y0)*fraction
    width_px=max(int(row["width"])/32,.55)
    diameter=max(1,round(max(width_px,1)*multiplier))
    radius=diameter/2
    alpha=round(int(row["alpha"])*min(width_px,1)*fade)
    margin=diameter+2
    min_x=max(0,int(min(x0,x1)-margin))
    min_y=max(0,int(min(y0,y1)-margin))
    max_x=min(layer.width,int(max(x0,x1)+margin+1))
    max_y=min(layer.height,int(max(y0,y1)+margin+1))
    if max_x<=min_x or max_y<=min_y or alpha<=0:
        return
    tile=Image.new("RGBA",(max_x-min_x,max_y-min_y),(0,0,0,0))
    draw=ImageDraw.Draw(tile)
    color=(int(row["r"]),int(row["g"]),int(row["b"]),alpha)
    first,second=(x0-min_x,y0-min_y),(x1-min_x,y1-min_y)
    draw.line((first,second),fill=color,width=diameter)
    for x,y in (first,second):
        draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
    layer.alpha_composite(tile,dest=(min_x,min_y))


def _bead(layer,host,bead,multiplier=SUPERSAMPLE):
    t=int(bead["t"])/65535
    x=(int(host["x0"])+(int(host["x1"])-int(host["x0"]))*t)/4*multiplier
    y=(int(host["y0"])+(int(host["y1"])-int(host["y0"]))*t)/4*multiplier
    r=int(bead["radius"])/16*multiplier
    if r<=0:
        return
    margin=int(2*r+multiplier+3)
    left=max(0,int(x-margin)); top=max(0,int(y-margin))
    right=min(layer.width,int(x+margin+1));bottom=min(layer.height,int(y+margin+1))
    if right<=left or bottom<=top:
        return
    x-=left;y-=top
    tile=Image.new("RGBA",(right-left,bottom-top))
    draw=ImageDraw.Draw(tile)
    alpha=int(host["alpha"])
    color=(int(host["r"]),int(host["g"]),int(host["b"]))
    draw.ellipse((x-r,y-r,x+r,y+r),fill=(*color,round(alpha*.35)))
    # The marks are distinct source-over passes, matching the Canvas renderer.
    rim_layer=Image.new("RGBA",tile.size)
    rim_draw=ImageDraw.Draw(rim_layer)
    w=max(.12*r,multiplier)
    rim_alpha=round(alpha*.86*.85*min(.12*r/multiplier,1))
    rim=.85*r
    rim_draw.ellipse((x-rim,y-rim,x+rim,y+rim),outline=(255,255,255,rim_alpha),
                     width=max(1,round(w)))
    tile.alpha_composite(rim_layer)
    glint_layer=Image.new("RGBA",tile.size)
    gx=x-.35*r; gy=y-.35*r;glint=.28*r
    ImageDraw.Draw(glint_layer).ellipse((gx-glint,gy-glint,gx+glint,gy+glint),
                                      fill=(255,255,255,alpha))
    tile.alpha_composite(glint_layer)
    layer.alpha_composite(tile,dest=(left,top))


def _background(width,height,dawn):
    if not dawn:
        return Image.new("RGB",(width,height),BACKGROUND)
    top=np.array((11,17,36),dtype=float)
    bottom=np.array((29,21,33),dtype=float)
    ramp=np.linspace(0,1,height,dtype=float)[:,None,None]
    colors=np.rint(top[None,None,:]*(1-ramp)+bottom[None,None,:]*ramp).astype(np.uint8)
    return Image.fromarray(np.repeat(colors,width,axis=1),"RGB")


def _glyph(canvas,spider,mm_per_unit,at=None,moving_legs=None,rest_progress=0.):
    g=spider["glyph"]
    pose=spider["rest"]
    x,y,heading=(pose["x"],pose["y"],pose["angle"]) if at is None else at
    size=g["scale"]/mm_per_unit*SUPERSAMPLE
    c,s=math.cos(heading),math.sin(heading)
    visible=g["restVisible"]
    resting=moving_legs is None
    x0,y0=x*SUPERSAMPLE,y*SUPERSAMPLE
    def pt(xx,yy):
        return (x0+size*(xx*c-yy*s),y0+size*(xx*s+yy*c))
    def hex_rgba(color,alpha=1):
        return (*bytes.fromhex(color[1:]),round(alpha*255))
    # Render an oversize local tile (small compared with an entire 4x plate).
    extent=max(abs(p) for leg in (moving_legs or g["rest"]) for joint in leg for p in joint)
    reach=math.ceil((extent+max((shape.get("rx",0) for shape in g["body"]),default=0)+5)*size)
    left=max(0,int(x0-reach));top=max(0,int(y0-reach))
    right=min(canvas.width,int(x0+reach+1));bottom=min(canvas.height,int(y0+reach+1))
    if right<=left or bottom<=top:
        return
    tile=Image.new("RGBA",(right-left,bottom-top),(0,0,0,0))
    draw=ImageDraw.Draw(tile)
    def local(point):
        xx,yy=pt(*point)
        return (xx-left,yy-top)
    legs=moving_legs or g["rest"]
    for leg in legs:
        for segment in range(visible["legFromJoint"] if resting else 0,3):
            opacity=(1-rest_progress if segment<visible["legFromJoint"] and not resting else 1)
            if opacity<=0:
                continue
            start,end=local(leg[segment]),local(leg[segment+1])
            width=max(1,round(g["legs"]["width"][segment]*size))
            color=hex_rgba(g["legs"]["color"],opacity)
            draw.line((start,end),fill=color,width=width,joint="curve")
            radius=width/2
            for px,py in (start,end):
                draw.ellipse((px-radius,py-radius,px+radius,py+radius),fill=color)
            band=g["legs"]["band"]
            if band and segment>=1:
                a=tuple(start[j]+(end[j]-start[j])/3 for j in (0,1))
                b=tuple(start[j]+(end[j]-start[j])*2/3 for j in (0,1))
                draw.line((a,b),fill=hex_rgba(band,opacity),width=width)
    body_opacity=(1-rest_progress if not visible["body"] and not resting else 1)
    if (not resting or visible["body"]) and body_opacity>0:
        for shape in g["body"]:
            if shape["type"]=="polygon":
                polygon=[local(point) for point in shape["points"]]
            else:
                # Polygonal ellipse approximation maintains rotated anatomy.
                rx,ry,angle=shape["rx"],shape["ry"],shape["rot"]
                ac,as_=math.cos(angle),math.sin(angle)
                polygon=[]
                for i in range(40):
                    theta=2*math.pi*i/40
                    px,py=rx*math.cos(theta),ry*math.sin(theta)
                    polygon.append(local((shape["x"]+px*ac-py*as_,
                                          shape["y"]+px*as_+py*ac)))
            if shape["fill"]:
                draw.polygon(polygon,fill=hex_rgba(shape["fill"],shape["alpha"]*body_opacity))
            if shape["stroke"] and shape["lw"]>0:
                draw.line(polygon+[polygon[0]],fill=hex_rgba(shape["stroke"],shape["alpha"]*body_opacity),
                          width=max(1,round(shape["lw"]*size)),joint="curve")
    eye_opacity=(1-rest_progress if not visible["eyes"] and not resting else 1)
    if (not resting or visible["eyes"]) and eye_opacity>0:
        for eye in g["eyes"]:
            for point,r,color in ((eye,eye["r"],eye["fill"]),
                                  (eye["glint"],eye["glint"]["r"],"#ffffff")):
                px,py=local((point["x"],point["y"]))
                radius=max(.15,r*size)
                draw.ellipse((px-radius,py-radius,px+radius,py+radius),
                             fill=hex_rgba(color,eye_opacity))
    canvas.alpha_composite(tile,dest=(left,top))


def _walking_pose(records,entry,spider,cursor):
    builder=spider["builder"]
    indices=np.flatnonzero(((records["flags"]&BUILDER_MASK)>>BUILDER_SHIFT)==builder)
    indices=indices[(records["flags"][indices]&ENV)==0]
    if len(indices)==0 or cursor<=int(indices[0]):
        return None
    index=indices[min(np.searchsorted(indices,int(cursor),side="right")-1,len(indices)-1)]
    row=records[index]
    frac=min(1.,max(0.,cursor-index))
    x=(int(row["x0"])+(int(row["x1"])-int(row["x0"]))*frac)/4
    y=(int(row["y0"])+(int(row["y1"])-int(row["y0"]))*frac)/4
    angle=math.atan2(int(row["y1"])-int(row["y0"]),int(row["x1"])-int(row["x0"]))
    segment=records[indices[indices<index]]
    lengths=np.hypot(segment["x1"].astype(float)-segment["x0"],
                     segment["y1"].astype(float)-segment["y0"])/4
    distance=lengths.sum()+math.hypot(int(row["x1"])-int(row["x0"]),
                                       int(row["y1"])-int(row["y0"]))/4*frac
    phase=(distance*entry["mmPerUnit"]/spider["glyph"]["strideMm"]%1)*8
    a=int(phase)%8; amount=phase-int(phase)
    first=spider["glyph"]["gait"][a]
    second=spider["glyph"]["gait"][(a+1)%8]
    legs=[[[u+(v-u)*amount for u,v in zip(p,q)] for p,q in zip(leg,other)]
          for leg,other in zip(first,second)]
    return (x,y,angle),legs


def plate(silk,entry,*,dawn=False,cursor=None,rest_progress=None):
    rows,beads=silk.records,silk.beads
    width,height=silk.width,silk.height
    sample=SUPERSAMPLE
    sharp=Image.new("RGBA",(width*sample,height*sample),(0,0,0,0))
    count=len(rows)
    final=cursor is None
    cursor=float(count if final else min(max(0.,cursor),count))
    bead_index=0
    upto=min(count,math.ceil(cursor))
    for i in range(upto):
        row=rows[i]
        if row["flags"]&INVISIBLE:
            continue
        fraction=1 if i+1<=cursor else cursor-i
        if fraction<=0:
            continue
        death=int(row["death"])
        if final and death!=NEVER:
            continue
        alpha=1 if death==NEVER or cursor<death else max(0.,1-(cursor-death)/min(6,count-death))
        if alpha<=0:
            continue
        _stroke(sharp,row,fraction=fraction,fade=alpha)
        while bead_index<len(beads) and int(beads[bead_index]["host"])<i:
            bead_index+=1
        while bead_index<len(beads) and int(beads[bead_index]["host"])==i:
            bead=beads[bead_index]
            if bead["flags"]&GLUE and fraction>=int(bead["t"])/65535:
                _bead(sharp,row,bead)
            bead_index+=1
    if dawn and final:
        for bead in beads:
            if not bead["flags"]&GLUE:
                _bead(sharp,rows[int(bead["host"])],bead)
    sharp=sharp.resize((width,height),Image.Resampling.LANCZOS)
    base=_background(width,height,dawn)
    base.paste(sharp,(0,0),sharp)
    glow=np.asarray(sharp.filter(ImageFilter.GaussianBlur(14)),dtype=np.float32)
    pixels=np.asarray(base,dtype=np.float32).copy()
    pixels+=glow[...,:3]*(glow[...,3:4]/255)*(.6 if dawn else .5)
    base=Image.fromarray(np.uint8(np.clip(np.rint(pixels),0,255)),"RGB").convert("RGBA")
    # The glyph is painted last: no body, eyes or legs bleed into the glow.
    over=Image.new("RGBA",(width*sample,height*sample))
    for spider in entry["spiders"]:
        builder=spider["builder"]
        own=np.flatnonzero((((rows["flags"]&BUILDER_MASK)>>BUILDER_SHIFT)==builder)
                           & ((rows["flags"]&ENV)==0))
        if final or (len(own) and cursor>int(own[-1])+1):
            _glyph(over,spider,entry["mmPerUnit"])
            continue
        moving=_walking_pose(rows,entry,spider,cursor)
        if moving:
            if rest_progress is None:
                _glyph(over,spider,entry["mmPerUnit"],*moving)
            else:
                progress=max(0.,min(1.,rest_progress))
                position,legs=moving
                rest=spider["rest"]
                delta=math.atan2(math.sin(rest["angle"]-position[2]),
                                 math.cos(rest["angle"]-position[2]))
                at=(position[0]+(rest["x"]-position[0])*progress,
                    position[1]+(rest["y"]-position[1])*progress,
                    position[2]+delta*progress)
                rest_legs=spider["glyph"]["rest"]
                blended=[[[v+(q-v)*progress for v,q in zip(joint,target)]
                          for joint,target in zip(leg,relax)]
                         for leg,relax in zip(legs,rest_legs)]
                _glyph(over,spider,entry["mmPerUnit"],at,blended,progress)
    base.alpha_composite(over.resize((width,height),Image.Resampling.LANCZOS))
    return base.convert("RGB")


def _font(size,italic=False):
    options=("georgiai.ttf","Georgia Italic.ttf") if italic else ("georgia.ttf","Georgia.ttf")
    options+=(("DejaVuSerif-Italic.ttf",) if italic else ("DejaVuSerif.ttf",))
    for name in options:
        try:
            return ImageFont.truetype(name,size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def catalogue(entries,dawn,output):
    grid=Image.new("RGB",(720*3,760*3),BACKGROUND)
    draw=ImageDraw.Draw(grid)
    common,scientific,detail=_font(26),_font(19,True),_font(17)
    for n,entry in enumerate(entries):
        col,row=n%3,n//3
        if row>=3:
            break
        path=output/f"{BY_ID[entry['id']].stem}_{'dawn' if dawn else 'dusk'}.png"
        with Image.open(path) as im:
            im.thumbnail((666,626),Image.Resampling.LANCZOS)
            grid.paste(im,(col*720+(720-im.width)//2,row*760+8+(626-im.height)//2))
        visible=(read_silk(ROOT/"web"/"specimens"/entry["file"]).records)
        threads=int(np.count_nonzero((visible["death"]==NEVER)&((visible["flags"]&(ENV|INVISIBLE))==0)))
        cx=col*720+360
        draw.text((cx,row*760+640),entry["name"],font=common,fill="#e6e9ed",anchor="mt")
        draw.text((cx,row*760+672),entry["scientific"],font=scientific,fill="#b6c0cd",anchor="mt")
        draw.text((cx,row*760+703),f"{threads:,} threads · {entry['silkMetres']:.1f} m of silk",
                  font=detail,fill="#9ca9ba",anchor="mt")
    file=output/f"catalogue_{'dawn' if dawn else 'dusk'}.png"
    grid.save(file)
    print(file.relative_to(ROOT).as_posix())


def _entries():
    return json.loads(INDEX.read_text(encoding="utf-8"))["specimens"]


def _specimen(species_id):
    for entry in _entries() if INDEX.exists() else []:
        if entry["id"]==species_id and (INDEX.parent/entry["file"]).exists():
            return read_silk(INDEX.parent/entry["file"]),entry
    from tools.build import build_specimen
    data,entry,_,_=build_specimen(BY_ID[species_id])
    return read_silk(data),entry


def video(species_id):
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg:
        print("--video requires ffmpeg on PATH (MP4 and GIF not written)",file=sys.stderr)
        return 2
    silk,entry=_specimen(species_id)
    output=ROOT/"renders"/"video"
    output.mkdir(parents=True,exist_ok=True)
    stem=BY_ID[species_id].stem
    # Compress the authored timeline to a short clip, with a separate 0.5 s
    # ease to the same rest pose that the overlay uses, then an exact hold.
    duration=min(6.,entry["durationSeconds"])
    with tempfile.TemporaryDirectory(prefix="spun-video-") as temp:
        frames=Path(temp)
        timeline=entry["timeline"]
        build_frames=math.ceil(duration*30)
        settle_frames=15
        frame_count=build_frames+settle_frames+1
        for frame in range(frame_count):
            u=min(1.,frame/build_frames)
            index=u*(len(timeline)-1)
            sample=int(index)
            cursor=timeline[-1] if sample>=len(timeline)-1 else (
                timeline[sample]+(timeline[sample+1]-timeline[sample])*(index-sample))
            progress=max(0.,(frame-build_frames)/settle_frames)
            image=plate(silk,entry,cursor=cursor,rest_progress=progress) if frame<frame_count-1 else plate(silk,entry)
            image.thumbnail((720,720),Image.Resampling.LANCZOS)
            if image.width%2 or image.height%2:
                image=image.resize((image.width-image.width%2,image.height-image.height%2),
                                   Image.Resampling.LANCZOS)
            image.save(frames/f"f{frame:04}.png")
        listing=frames/"frames.txt"
        names=[f"f{frame:04}.png" for frame in range(frame_count)]
        with listing.open("w",encoding="utf-8") as handle:
            for name in names[:-1]:
                handle.write(f"file '{name}'\nduration {1/30:.12f}\n")
            handle.write(f"file '{names[-1]}'\nduration 0.6\nfile '{names[-1]}'\n")
        common=[ffmpeg,"-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",str(listing)]
        mp4=output/f"{stem}.mp4"
        subprocess.run(common+["-fps_mode","cfr","-r","30","-c:v","libx264","-crf","17",
                               "-pix_fmt","yuv420p",str(mp4)],check=True)
        palette=frames/"palette.png"
        subprocess.run(common+["-vf","fps=15,palettegen=max_colors=128:stats_mode=full",str(palette)],check=True)
        gif=output/f"{stem}.gif"
        subprocess.run(common+["-i",str(palette),"-filter_complex",
                               "[0:v]fps=15[v];[v][1:v]paletteuse=dither=bayer:bayer_scale=4",
                               str(gif)],check=True)
    print(mp4.relative_to(ROOT).as_posix())
    print(gif.relative_to(ROOT).as_posix())
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    selection=parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--only",choices=list(BY_ID))
    selection.add_argument("--all",action="store_true")
    selection.add_argument("--video",choices=list(BY_ID))
    parser.add_argument("--dawn",action="store_true",help="render Dawn only for --only")
    args=parser.parse_args()
    if args.video:
        return video(args.video)
    output=ROOT/"renders"
    output.mkdir(exist_ok=True)
    entries=_entries() if args.all else [entry for entry in _entries() if entry["id"]==args.only] if INDEX.exists() else []
    if args.only and not entries:
        entries=[_specimen(args.only)[1]]
    for entry in entries:
        silk,_=_specimen(entry["id"])
        for dawn in ([args.dawn] if args.only else [False,True]):
            path=output/f"{BY_ID[entry['id']].stem}_{'dawn' if dawn else 'dusk'}.png"
            plate(silk,entry,dawn=dawn).save(path)
            print(path.relative_to(ROOT).as_posix())
    if args.all:
        for dawn in (False,True):
            catalogue(entries,dawn,output)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
