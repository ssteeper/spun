"""Deterministic anatomical spider glyphs, in millimetres from the spinnerets.

The moderately exaggerated scales are catalogue values, not canvas-pixel geometry.
Legs are ordered left I–IV, right I–IV; Deinopis I/II tips hold the net.
"""

from __future__ import annotations

import math
from functools import lru_cache

# body length, display scale, pose, carapace, abdomen, legs, bands, leg span
_ANATOMY = {
    "golden-orb-weaver": (30, 1.6, "head-down", "#aeb2b5", "#abb5ae", "#302b29", "#e8bd69", 1.30),
    "st-andrews-cross": (15, 1.8, "hub-x", "#cbd4d9", "#d8cd66", "#292a2e", "#e2d676", 1.40),
    "garden-orb-weaver": (22, 1.6, "hub-rest", "#9a7654", "#715642", "#5d4939", None, 1.18),
    "leaf-curling-spider": (12, 1.8, "in-leaf", "#ae8c61", "#9e805c", "#735a3c", None, 1.12),
    "christmas-jewel-spider": (8, 2.0, "hub-rest", "#17191d", "#1d1e22", "#39383a", "#edcb62", 1.24),
    "scorpion-tailed-spider": (16, 1.6, "hub-tail", "#ae884d", "#c49a5d", "#856235", None, 1.10),
    "net-casting-spider": (25, 1.0, "net", "#80684e", "#624d3b", "#61503e", None, 1.35),
    "magnificent-spider": (14, 1.0, "hanging", "#eee3c4", "#dbc8ae", "#b89985", "#dca0a2", 1.30),
    "redback-spider": (10, 1.8, "retreat", "#15151b", "#1a1920", "#29252a", None, 1.25),
}


def _ellipse(x, y, rx, ry, fill, stroke=None, lw=0, rot=0, alpha=1):
    return dict(type="ellipse", x=x, y=y, rx=rx, ry=ry, rot=rot,
                fill=fill, stroke=stroke, lw=lw, alpha=alpha)


def _polygon(points, fill, stroke=None, lw=0, alpha=1):
    return dict(type="polygon", points=points, fill=fill, stroke=stroke,
                lw=lw, alpha=alpha)


def _body(species_id, length, carapace, abdomen):
    compact = species_id in ("christmas-jewel-spider", "redback-spider")
    back = .32 * length
    body = [
        _ellipse(back, 0, (.31 if compact else .29)*length,
                 (.25 if compact else .19)*length, abdomen, "#271f20", .04*length),
        _ellipse(.76*length, 0, .21*length, .14*length, carapace,
                 "#35292a", .036*length),
        _ellipse(.90*length, -.048*length, .065*length, .065*length,
                 "#e8dfcc" if species_id == "magnificent-spider" else carapace),
    ]
    if species_id == "golden-orb-weaver":
        for dx in (.12, .29, .45):
            body.append(_ellipse(dx*length, 0, .032*length, .17*length, "#d8bd70", alpha=.9))
        body.append(_ellipse(.36*length, 0, .18*length, .064*length, "#5b584e"))
    elif species_id == "st-andrews-cross":
        for dx in (.13, .30, .47):
            body.append(_ellipse(dx*length, 0, .033*length, .195*length, "#24252a"))
        body.append(_ellipse(.29*length, 0, .055*length, .19*length, "#f1dd72"))
        body.append(_ellipse(.77*length, 0, .1*length, .07*length, "#343841"))
    elif species_id == "garden-orb-weaver":
        for side in (-1, 1):
            body.append(_ellipse(.57*length, side*.155*length, .12*length,
                                 .07*length, "#a78a63", rot=side*.35))
        for dx, dy in ((.18, -.085), (.34, .09), (.40, -.05)):
            body.append(_ellipse(dx*length, dy*length, .035*length, .023*length, "#b19b7b"))
    elif species_id == "leaf-curling-spider":
        body.append(_ellipse(.30*length, 0, .16*length, .075*length, "#634e35"))
    elif species_id == "christmas-jewel-spider":
        # The six polygonal spines belong to the abdomen, not to the legs.
        for x, y, ex, ey in ((.05,-.16,-.08,-.32), (.30,-.23,.30,-.42),
                             (.49,-.13,.64,-.29), (.05,.16,-.08,.32),
                             (.30,.23,.30,.42), (.49,.13,.64,.29)):
            body.append(_polygon([[x*length,y*length], [ex*length,ey*length],
                                  [(x+.09)*length,y*length]], "#222228", "#ddd4ad", .016*length))
        for x, y, r in ((.20,-.12,.06), (.35,.12,.065), (.45,-.07,.04), (.16,.1,.032)):
            body.append(_ellipse(x*length,y*length,r*length,r*length,"#f2ebd5"))
        body.append(_ellipse(.37*length, 0, .045*length, .064*length, "#f2d254"))
    elif species_id == "scorpion-tailed-spider":
        body.extend((_polygon([[.09*length, 0], [-.31*length, -.09*length],
                               [-.63*length, -.22*length], [-.49*length, -.26*length],
                               [-.26*length, -.02*length]], "#b5904e", "#594832", .025*length),
                     _ellipse(.22*length, -.07*length, .17*length, .06*length, "#ddbd78")))
    elif species_id == "net-casting-spider":
        body.append(_ellipse(.37*length, 0, .22*length, .075*length, "#45392f"))
        body.append(_ellipse(.78*length, 0, .155*length, .055*length, "#a48966"))
    elif species_id == "magnificent-spider":
        for x, y, r, colour in ((.20,-.10,.055,"#dc9da4"),(.41,.11,.065,"#eac46b"),
                                 (.50,-.075,.04,"#d996a4"),(.71,.08,.035,"#d9ab68")):
            body.append(_ellipse(x*length,y*length,r*length,r*length,colour))
        for x in (.12, .30, .48):
            body.append(_ellipse(x*length,-.19*length,.046*length,.055*length,"#e9cfb5"))
    elif species_id == "redback-spider":
        body.extend((_ellipse(.28*length, -.07*length, .18*length, .045*length, "#42404b", alpha=.65),
                     _polygon([[.06*length, -.018*length], [.49*length, -.025*length],
                               [.39*length, .04*length], [.17*length, .035*length]], "#cf3440")))
    return body


def _legs(length, span):
    legs = []
    # Three articulated segments: femur out/forward, tibia out, tarsus inward.
    for side in (-1, 1):
        for i in range(4):
            x = length*(.84-.095*i)
            reach = length*span*(1.00 if i in (0,3) else .85)
            forward = (1.0, .42, -.45, -1.0)[i]
            base = [x, side*.10*length]
            knee = [x+forward*.42*reach, side*(.34*reach+.07*length)]
            ankle = [x+forward*.75*reach, side*(.69*reach+.07*length)]
            tip = [x+forward*reach, side*(.92*reach+.07*length)]
            legs.append([base, knee, ankle, tip])
    return legs


def _rest_legs(species_id, length, span):
    legs = _legs(length, span)
    if species_id == "st-andrews-cross":
        # Legs I+II, III+IV pair along the upper/lower arms of a hub X.
        for j, leg in enumerate(legs):
            side = -1 if j < 4 else 1
            i = j % 4
            direction = 1 if i < 2 else -1
            r = length*(1.37 if i in (0,3) else 1.24)
            # Separate each close pair just enough for four legs to read
            # on each side without losing the paired X silhouette.
            offset = (-.045 if i in (0, 2) else .045)*length
            for k, fraction in ((1,.37),(2,.70),(3,1.0)):
                leg[k] = [leg[0][0]+direction*r*fraction*.71,
                          side*(r*fraction*.71+offset*fraction)]
    elif species_id == "leaf-curling-spider":
        for leg in legs:
            tip = leg[-1]
            for k in (1,2):
                leg[k] = [leg[0][0]+(tip[0]-leg[0][0])*k/3,
                          leg[0][1]+(tip[1]-leg[0][1])*k/3]
    elif species_id == "net-casting-spider":
        # Four tips are exact corners; x spans 20 mm, y spans 16 mm.
        for index, tx, ty in ((0,46,-8),(1,26,-8),(4,46,8),(5,26,8)):
            leg = legs[index]
            leg[1] = [length*.96, ty*.60]
            leg[2] = [(leg[1][0]+tx)*.5, ty*1.25]
            leg[3] = [tx, ty]
    elif species_id == "magnificent-spider":
        # Left leg II touches the bolas filament at (0,+8) from the spinnerets.
        leg = legs[1]
        leg[1], leg[2], leg[3] = [length*.52, -length*.42], [length*.14, 0], [0,8]
    elif species_id == "redback-spider":
        for leg in legs:
            for joint in leg[1:]:
                joint[0] *= .73
                joint[1] *= .73
    return legs


@lru_cache(maxsize=16)
def glyph(species_id: str) -> dict:
    """Return C4 data. Do not mutate this cached geometry."""
    length, scale, pose, carapace, abdomen, leg_colour, band, span = _ANATOMY[species_id]
    legs = _legs(length, span)
    stride = max(2., length*.24)
    gait = []
    for frame in range(8):
        current = []
        for index, original in enumerate(legs):
            leg = [joint[:] for joint in original]
            # Alternating tetrapods L1 R2 L3 R4 / R1 L2 R3 L4.
            stance_first = (index % 4 + index // 4) % 2 == 0
            phase = (frame + (0 if stance_first else 4)) % 8
            swing = phase >= 4
            shift = stride*(.25-phase/8 if not swing else -.25+(phase-4)/8)
            leg[3][0] += shift
            if swing:
                lift = math.sin(math.pi*(phase-4)/4)
                leg[3][1] -= (1 if index < 4 else -1)*.13*length*lift
            leg[2][0] += shift*.45
            leg[2][1] += (leg[3][1]-original[3][1])*.5
            current.append(leg)
        gait.append(current)
    eyes = []
    if species_id == "net-casting-spider":
        for side in (-1, 1):
            y = side*.064*length
            eyes.append(dict(x=.85*length, y=y, r=.064*length,
                             fill="#e2cc9f", glint=dict(x=.835*length,y=y-.017*length,r=.018*length)))
    else:
        for side in (-1, 1):
            y=side*.074*length
            eyes.append(dict(x=.925*length,y=y,r=.019*length,
                             fill="#ddd8c7",glint=dict(x=.919*length,y=y-.007*length,r=.006*length)))
    return dict(scale=scale, strideMm=stride,
                legs=dict(color=leg_colour, band=band, width=[.041*length,.028*length,.012*length]),
                body=_body(species_id,length,carapace,abdomen), eyes=eyes,
                gait=gait, rest=_rest_legs(species_id,length,span),
                restVisible=dict(body=pose!="in-leaf",eyes=pose!="in-leaf",
                                 legFromJoint=2 if pose=="in-leaf" else 0))


def rest_points_px(species_id: str, x: float, y: float, angle: float,
                   mm_per_px: float) -> list[tuple[float,float]]:
    """Rest tarsus positions in specimen coordinates, in left I–IV/right I–IV order."""
    g=glyph(species_id)
    c,s=math.cos(angle),math.sin(angle)
    factor=g["scale"]/mm_per_px
    return [(x+factor*(leg[3][0]*c-leg[3][1]*s),
             y+factor*(leg[3][0]*s+leg[3][1]*c)) for leg in g["rest"]]


def extent_px(species_id: str, x: float, y: float, angle: float,
              mm_per_px: float) -> tuple[float,float,float,float]:
    """Bounding box of the rest-visible glyph (not hidden parts inside a leaf)."""
    g=glyph(species_id)
    points=[]
    for leg in g["rest"]:
        points.extend(leg[g["restVisible"]["legFromJoint"]:])
    if g["restVisible"]["body"]:
        for shape in g["body"]:
            if shape["type"]=="polygon":
                points.extend(shape["points"])
            else:
                # Bounding rotated ellipses exactly along local axes.
                theta=shape["rot"]
                dx=math.hypot(shape["rx"]*math.cos(theta),shape["ry"]*math.sin(theta))
                dy=math.hypot(shape["rx"]*math.sin(theta),shape["ry"]*math.cos(theta))
                points.extend(((shape["x"]-dx,shape["y"]-dy),
                               (shape["x"]+dx,shape["y"]+dy)))
    if g["restVisible"]["eyes"]:
        for eye in g["eyes"]:
            points.extend(((eye["x"]-eye["r"],eye["y"]-eye["r"]),
                           (eye["x"]+eye["r"],eye["y"]+eye["r"])))
    c,s=math.cos(angle),math.sin(angle)
    factor=g["scale"]/mm_per_px
    rotated=[(x+factor*(px*c-py*s),y+factor*(px*s+py*c)) for px,py in points]
    return (min(px for px,_ in rotated),min(py for _,py in rotated),
            max(px for px,_ in rotated),max(py for _,py in rotated))
