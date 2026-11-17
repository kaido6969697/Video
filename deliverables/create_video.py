#!/usr/bin/env python3
"""Render the explainer as a code-drawn 2D animation with Pillow + FFmpeg.

Run at the repository root after generating voice_01.wav ... voice_04.wav:
  PATH="$PWD/.venv/bin:$PATH" .venv/bin/python deliverables/create_video.py
Art is original and procedural; puppets are generic, not real-person likenesses.
"""
from __future__ import annotations
import functools
import math
import os
import subprocess
import textwrap
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H, FPS = 1280, 720, 24
INK = (24, 22, 27)
NAVY = (10, 15, 40)
CREAM = (255, 246, 220)
GOLD = (242, 193, 78)
LIME = (184, 240, 74)
RED = (200, 36, 44)
BLUE = (72, 119, 192)
FONT_DIR = ROOT / "fonts"
FONT_HAND = FONT_DIR / "CaveatBrush-Regular.ttf"
FONT_KALAM = FONT_DIR / "Kalam-Bold.ttf"
FONT_MARKER = FONT_DIR / "PermanentMarker-Regular.ttf"

PARAGRAPHS = [p.strip() for p in (ROOT / "narration.txt").read_text().split("\n\n") if p.strip()]
AUDIO_GROUPS = [(0, 1, 2), (3, 4), (5, 6, 7), (8, 9)]
AUDIO_PATHS = [ROOT / f"voice_{i:02d}.wav" for i in range(1, 5)]

# Each paragraph is broken into short visual beats. Fractions are within that
# paragraph's measured narration span; this gives the 3:39 story 25 distinct shots.
LAYOUT = {
    0: [("doorstep",0,.27),("funeral_room",.27,.60),("hook_numbers",.60,1)],
    1: [("question",0,1)],
    2: [("victim_home",0,.34),("call_center",.34,.69),("warning_screen",.69,1)],
    3: [("refund_screen",0,.38),("fake_refund",.38,.72),("cash_wire",.72,1)],
    4: [("parcel_counter",0,.31),("pickup_id",.31,.66),("crypto_route",.66,1)],
    5: [("sting_room",0,.43),("viral_frame",.43,.68),("evidence_wall",.68,1)],
    6: [("courthouse",0,.34),("court_sentence",.34,.67),("case_numbers",.67,1)],
    7: [("human_impact",0,.52),("two_totals",.52,1)],
    8: [("safety_home",0,.60),("verify_steps",.60,1)],
    9: [("closing_polaroid",0,.55),("closing_message",.55,1)],
}
TITLES = {
    "doorstep":"A PICKUP AT THE DOOR", "funeral_room":"THE FUNERAL WAS A SET",
    "hook_numbers":"ONE VISITOR. A MUCH BIGGER CASE.", "question":"HOW DOES A REFUND BECOME CASH?",
    "victim_home":"THE FIRST CALL", "call_center":"A VOICE BUILDS TRUST", "warning_screen":"THE SCREEN CREATES URGENCY",
    "refund_screen":"A REFUND THAT NEVER HAPPENED", "fake_refund":"“SEND THE EXTRA BACK”", "cash_wire":"THE VICTIM SENDS THEIR OWN MONEY",
    "parcel_counter":"A NAME ON A PACKAGE", "pickup_id":"A FAKE ID OPENS THE BOX", "crypto_route":"CASH MOVES THROUGH A NETWORK",
    "sting_room":"THE STING", "viral_frame":"ONE CLIP IS ONE CLUE", "evidence_wall":"THE CASE IS BIGGER THAN THE CLIP",
    "courthouse":"APRIL 2026: GUILTY PLEA", "court_sentence":"NOVEMBER 13: 78 MONTHS", "case_numbers":"TWO DIFFERENT TOTALS",
    "human_impact":"THE LOSS WASN’T ONLY MONEY", "two_totals":"WIDER SCHEME ≠ CHEN’S ADMITTED LOSS",
    "safety_home":"THE MOMENT TO PAUSE", "verify_steps":"HANG UP. VERIFY. ASK.",
    "closing_polaroid":"A VIRAL STING SHOWS A FACE", "closing_message":"EVIDENCE REVEALS THE SYSTEM",
}

def ease_out(u):
    u=max(0.0,min(1.0,u))
    return 1-(1-u)**3


@functools.lru_cache(maxsize=48)
def font(path: str, size: int):
    return ImageFont.truetype(path, size)


def rounded(d, box, radius, fill, outline=INK, width=4):
    d.rounded_rectangle(tuple(int(v) for v in box), radius=int(radius), fill=fill, outline=outline, width=int(width))


def center_text(d, xy, text, f, fill, stroke=0, stroke_fill=INK):
    d.text(xy, text, font=f, fill=fill, anchor="mm", stroke_width=stroke, stroke_fill=stroke_fill)


def fit_lines(d, text, f, max_width):
    words=text.split(); lines=[]; line=""
    for word in words:
        cand=word if not line else line+" "+word
        if d.textbbox((0,0),cand,font=f,stroke_width=1)[2] <= max_width:
            line=cand
        else:
            if line: lines.append(line)
            line=word
    if line: lines.append(line)
    return lines


def pop_scale(u, amp=.13):
    u=max(0,min(1,u))
    return 1 + amp*math.sin(math.pi*u)*math.exp(-3*u)


def arrow(d, p0, p1, color=GOLD, width=5, head=16):
    x0,y0=p0; x1,y1=p1
    d.line((x0,y0,x1,y1),fill=color,width=width)
    a=math.atan2(y1-y0,x1-x0)
    p2=(x1-head*math.cos(a-.55),y1-head*math.sin(a-.55))
    p3=(x1-head*math.cos(a+.55),y1-head*math.sin(a+.55))
    d.polygon((p1,p2,p3),fill=color)


def draw_puppet(d, x, foot, scale, t, role="victim", expr="neutral", pose="idle", speech=0.0, phase=0.0, tag=None):
    """Original round-head puppet with timed blink, brows, mouth, gait, and gestures."""
    palettes={
        "victim":((69,88,124),(226,188,150),(75,53,43)),
        "courier":((53,67,105),(222,177,133),(55,43,38)),
        "host_red":((153,65,59),(220,178,142),(57,42,37)),
        "host_teal":((58,119,116),(223,183,147),(51,40,37)),
        "agent":((50,61,99),(220,177,135),(45,38,34)),
        "judge":((74,46,59),(223,186,150),(58,45,42)),
        "helper":((62,103,83),(227,190,153),(69,47,38)),
    }
    suit,skin,hair=palettes.get(role,palettes["victim"])
    gait=math.sin(t*6.3+phase)
    bob=math.sin(t*3.0+phase)*4
    if pose=="walk": bob=abs(gait)*5
    xx=float(x); ff=float(foot+bob)
    def P(dx,dy): return (int(xx+dx*scale),int(ff+dy*scale))
    lw=max(3,int(5.4*scale))
    # legs: crossed walking cycle or planted stance
    leg_swing=gait*25 if pose=="walk" else math.sin(t*2+phase)*2
    d.line((P(-22,-108),P(-28-leg_swing,-8)),fill=INK,width=lw)
    d.line((P(22,-108),P(28+leg_swing,-8)),fill=INK,width=lw)
    if pose=="walk":
        d.line((P(-28-leg_swing,-8),P(-42-leg_swing,-6)),fill=INK,width=lw)
        d.line((P(28+leg_swing,-8),P(42+leg_swing,-6)),fill=INK,width=lw)
    # pill body + shirt/tie details
    d.rounded_rectangle((P(-62,-231),P(62,-102)),radius=int(44*scale),fill=suit,outline=INK,width=lw)
    d.polygon((P(-25,-226),P(0,-180),P(25,-226)),fill=CREAM,outline=INK)
    d.polygon((P(-8,-219),P(8,-219),P(12,-173),P(0,-162),P(-12,-173)),fill=RED,outline=INK)
    d.line((P(-37,-198),P(-11,-183)),fill=(187,157,119),width=max(2,lw//2))
    d.line((P(37,-198),P(11,-183)),fill=(187,157,119),width=max(2,lw//2))
    # arm joints animate by action, with soft elbow bends and rounded hands
    if pose=="phone":
        phone_bob=math.sin(t*5+phase)*4
        left=[P(-52,-195),P(-88,-159),P(-51,-134+phone_bob)]
        right=[P(52,-195),P(86,-165+phone_bob),P(76,-126+phone_bob)]
    elif pose=="point":
        gesture=math.sin(t*3.8+phase)*9
        left=[P(-52,-195),P(-89,-159),P(-82,-125)]
        right=[P(52,-195),P(88,-235+gesture*.35),P(147+gesture,-270+gesture*.25)]
    elif pose=="open":
        left=[P(-52,-195),P(-96,-243),P(-120,-284)]
        right=[P(52,-195),P(96,-243),P(120,-284)]
    elif pose=="hold":
        left=[P(-52,-195),P(-94,-166),P(-82,-128)]
        right=[P(52,-195),P(94,-166),P(82,-128)]
    elif pose=="reassure":
        wave=math.sin(t*4.2+phase)*10
        left=[P(-52,-195),P(-89,-160),P(-89,-125)]
        right=[P(52,-195),P(82,-212+wave*.3),P(113+wave,-218+wave*.25)]
    else:
        arm_swing=gait*18 if pose=="walk" else 0
        left=[P(-52,-195),P(-88,-161-arm_swing),P(-82,-125-arm_swing)]
        right=[P(52,-195),P(88,-161+arm_swing),P(82,-125+arm_swing)]
    for pts in (left,right):
        d.line(pts,fill=INK,width=lw,joint="curve")
        hx,hy=pts[-1]
        r=max(5,int(10*scale))
        d.ellipse((hx-r,hy-r,hx+r,hy+r),fill=skin,outline=INK,width=max(2,lw//2))
    if pose=="phone":
        hx,hy=right[-1]
        rounded(d,(hx-9,hy-34,hx+10,hy-5),4,(27,33,53),INK,2)
    # Head float plus subtle idle motion.
    headx=xx+math.sin(t*1.7+phase)*3
    heady=ff-326*scale
    rad=92*scale
    d.ellipse((int(headx-rad),int(heady-rad),int(headx+rad),int(heady+rad)),fill=skin,outline=INK,width=lw)
    # hard shadow crescent at lower head edge
    d.arc((int(headx-rad*.82),int(heady-rad*.56),int(headx+rad*.82),int(heady+rad*.86)),8,172,fill=(177,132,105),width=max(3,int(8*scale)))
    # simple hair cap, unique generic silhouette
    d.arc((int(headx-rad*.88),int(heady-rad*.94),int(headx+rad*.88),int(heady+rad*.40)),185,355,fill=hair,width=max(4,int(13*scale)))
    # blinking compresses eyes to expressive lines
    blink=((t+phase)%3.15)<0.12
    eye_y=heady-20*scale
    eye_dx=31*scale
    gaze=0
    if expr in ("suspicious","worried"): gaze=4*scale
    if expr=="shocked": gaze=0
    if blink:
        for ex in (headx-eye_dx,headx+eye_dx): d.line((int(ex-8*scale),int(eye_y),int(ex+8*scale),int(eye_y)),fill=INK,width=max(3,lw//2))
    else:
        for ex in (headx-eye_dx,headx+eye_dx):
            if expr=="shocked":
                r=13*scale; d.ellipse((int(ex-r),int(eye_y-r),int(ex+r),int(eye_y+r)),fill=CREAM,outline=INK,width=max(2,lw//2))
                d.ellipse((int(ex-4*scale+gaze),int(eye_y-3*scale),int(ex+4*scale+gaze),int(eye_y+5*scale)),fill=INK)
            elif expr=="sleepy":
                d.arc((int(ex-10*scale),int(eye_y-2*scale),int(ex+10*scale),int(eye_y+11*scale)),180,355,fill=INK,width=max(3,lw//2))
            else:
                d.ellipse((int(ex-6*scale),int(eye_y-7*scale),int(ex+6*scale),int(eye_y+7*scale)),fill=INK)
                d.ellipse((int(ex-3*scale),int(eye_y-5*scale),int(ex),int(eye_y-2*scale)),fill=CREAM)
    # eyebrows carry the expression
    brow_y=heady-43*scale
    if expr in ("worried","shocked"):
        d.line((int(headx-eye_dx-12*scale),int(brow_y+5*scale),int(headx-eye_dx+9*scale),int(brow_y-5*scale)),fill=INK,width=max(3,lw//2))
        d.line((int(headx+eye_dx-9*scale),int(brow_y-5*scale),int(headx+eye_dx+12*scale),int(brow_y+5*scale)),fill=INK,width=max(3,lw//2))
    elif expr in ("suspicious","stern"):
        d.line((int(headx-eye_dx-12*scale),int(brow_y-5*scale),int(headx-eye_dx+10*scale),int(brow_y+5*scale)),fill=INK,width=max(3,lw//2))
        d.line((int(headx+eye_dx-10*scale),int(brow_y+5*scale),int(headx+eye_dx+12*scale),int(brow_y-5*scale)),fill=INK,width=max(3,lw//2))
    elif expr=="sad":
        d.line((int(headx-eye_dx-10*scale),int(brow_y+5*scale),int(headx-eye_dx+10*scale),int(brow_y-5*scale)),fill=INK,width=max(3,lw//2))
        d.line((int(headx+eye_dx-10*scale),int(brow_y-5*scale),int(headx+eye_dx+10*scale),int(brow_y+5*scale)),fill=INK,width=max(3,lw//2))
    else:
        d.line((int(headx-eye_dx-10*scale),int(brow_y),int(headx-eye_dx+10*scale),int(brow_y-2*scale)),fill=INK,width=max(3,lw//2))
        d.line((int(headx+eye_dx-10*scale),int(brow_y-2*scale),int(headx+eye_dx+10*scale),int(brow_y)),fill=INK,width=max(3,lw//2))
    # mouth: speaking opens/closes from measured narration energy; otherwise expression-specific.
    mx=int(headx+8*scale); my=int(heady+37*scale)
    if speech>0.15:
        mh=int((4+18*min(1,speech))*scale); mw=int((15+5*speech)*scale)
        d.ellipse((mx-mw,my-mh,mx+mw,my+mh),fill=(54,25,35),outline=INK,width=max(2,lw//3))
        if mh>8: d.arc((mx-8*scale,my+mh*.15,mx+8*scale,my+mh),0,180,fill=(224,91,91),width=max(2,lw//3))
    elif expr in ("shocked",):
        r=14*scale; d.ellipse((int(mx-r),int(my-r),int(mx+r),int(my+r*1.35)),fill=(54,25,35),outline=INK,width=max(2,lw//3))
    elif expr in ("worried","sad","stern","suspicious"):
        d.arc((int(mx-20*scale),int(my-1*scale),int(mx+20*scale),int(my+18*scale)),200,345,fill=INK,width=max(3,lw//2))
    elif expr=="smile":
        d.arc((int(mx-20*scale),int(my-17*scale),int(mx+20*scale),int(my+20*scale)),10,165,fill=INK,width=max(3,lw//2))
    else:
        d.line((int(mx-14*scale),my,int(mx+14*scale),my),fill=INK,width=max(3,lw//2))
    if expr in ("worried","sad"):
        # small sweat bead, timed twinkle
        if int((t+phase)*2)%3!=0:
            d.ellipse((int(headx+60*scale),int(heady-22*scale),int(headx+70*scale),int(heady-5*scale)),fill=BLUE)
    if tag:
        tw=max(114,int(len(tag)*12*scale+28))
        y=int(ff+6)
        rounded(d,(int(xx-tw/2),y,int(xx+tw/2),y+34),8,(12,17,38),GOLD,2)
        center_text(d,(xx,y+17),tag,font(str(FONT_KALAM),17),CREAM)


def background(d, kind, t, local):
    """Distinct location plates: exteriors, homes, work rooms, retail, map, court."""
    palettes={
        "night":((9,14,39),(31,43,83)),"funeral":((13,15,31),(41,34,52)),
        "home":((37,45,66),(75,61,55)),"office":((10,17,34),(35,47,72)),
        "retail":((31,42,58),(72,63,59)),"map":((188,171,128),(130,120,98)),
        "court":((32,25,33),(80,55,57)),"warm":((53,54,53),(116,82,57)),
        "paper":((30,33,48),(47,51,66)),
    }
    top,bottom=palettes.get(kind,palettes["night"])
    for y in range(0,H,5):
        u=y/H
        color=tuple(int(top[k]*(1-u)+bottom[k]*u) for k in range(3))
        d.rectangle((0,y,W,y+5),fill=color)
    # environment-specific architectural elements
    if kind=="night":
        # Los Angeles residential street, telephone wires, porch, distant lights
        for i in range(8):
            x=i*176-35; h=120+(i*67)%130
            d.rectangle((x,410-h,x+132,570),fill=(19,27,55),outline=(10,12,28),width=4)
            for j in range(3): d.rectangle((x+18+j*34,430-h//2,x+32+j*34,450-h//2),fill=GOLD if (i+j)%4==0 else (48,65,99))
        d.line((0,130,1280,200),fill=(37,40,62),width=4); d.line((0,155,1280,215),fill=(37,40,62),width=3)
        d.rectangle((0,570,W,H),fill=(15,20,35)); d.line((0,570,W,570),fill=INK,width=7)
        # street lamp with breathing halo
        lx=1110; d.line((lx,570,lx,170),fill=INK,width=14); d.line((lx,180,lx-75,180),fill=INK,width=12)
        glow=24+int(5*math.sin(t*2.4)); d.ellipse((lx-98,112,lx+50,248),fill=(40,47,68))
        d.ellipse((lx-80,150,lx-43,187),fill=GOLD,outline=INK,width=4)
        for j in range(4): d.line((lx-85+j*14,190,lx-150+j*30,500),fill=(42,44,63),width=2)
    elif kind=="funeral":
        d.rectangle((0,90,W,568),fill=(25,24,43)); d.rectangle((62,125,1218,565),fill=(34,31,49),outline=(80,72,83),width=5)
        for x in (150,1115):
            d.rectangle((x,175,x+86,395),fill=(22,31,50),outline=(122,110,103),width=5)
            d.line((x+43,180,x+43,393),fill=(101,88,80),width=3)
        # warm candles / flower stands
        for x in (250,1040):
            d.line((x,530,x,390),fill=INK,width=8); d.ellipse((x-20,372,x+20,410),fill=GOLD,outline=INK,width=3)
            for j in range(6):
                ang=j*math.pi/3
                fx=x+int(32*math.cos(ang)); fy=470+int(26*math.sin(ang))
                d.ellipse((fx-14,fy-14,fx+14,fy+14),fill=(RED if j%2 else (224,203,176)),outline=INK,width=2)
        d.rectangle((0,565,W,H),fill=(29,26,41))
    elif kind=="home":
        d.rectangle((0,96,W,568),fill=(62,54,53))
        d.rectangle((64,128,392,356),fill=(24,37,62),outline=INK,width=7)
        d.line((228,130,228,355),fill=(131,119,100),width=4); d.line((66,243,390,243),fill=(131,119,100),width=4)
        for i in range(6): d.rectangle((83+i*48,170,97+i*48,205),fill=GOLD if i%3==0 else (55,77,111))
        d.rectangle((48,426,438,570),fill=(102,65,58),outline=INK,width=8)
        d.rectangle((72,402,413,460),fill=(131,87,73),outline=INK,width=6)
        d.rectangle((0,568,W,H),fill=(43,34,37))
        d.ellipse((810,430,1200,610),fill=(53,52,52))
        d.rectangle((986,270,1164,450),fill=(31,40,53),outline=INK,width=8)
    elif kind=="office":
        d.rectangle((0,90,W,572),fill=(16,24,44))
        for row in range(2):
            for col in range(5):
                x=55+col*245; y=164+row*165
                rounded(d,(x,y,x+186,y+111),9,(18,26,48),(67,85,125),4)
                d.rectangle((x+14,y+14,x+171,y+83),fill=(25,39,68))
                d.line((x+18,y+32,x+145,y+32),fill=(49,121,130),width=3)
                d.line((x+20,y+52,x+104,y+52),fill=(152,94,78),width=3)
                d.rectangle((x+75,y+111,x+113,y+137),fill=(62,66,80))
                d.rectangle((x+48,y+137,x+144,y+148),fill=INK)
        d.rectangle((0,570,W,H),fill=(15,20,32))
        for i in range(12):
            x=(i*113+int(t*20))%W; d.ellipse((x,102+(i%3)*20,x+3,105+(i%3)*20),fill=(116,151,185))
    elif kind=="retail":
        d.rectangle((0,90,W,565),fill=(52,56,63))
        d.rectangle((70,128,1210,205),fill=(35,65,75),outline=INK,width=6)
        center_text(d,(640,166),"EXPRESS  /  PARCEL PICKUP",font(str(FONT_MARKER),29),CREAM)
        d.rectangle((0,412,W,574),fill=(103,76,58),outline=INK,width=8)
        for x in (124,970):
            d.rectangle((x,235,x+190,395),fill=(33,43,54),outline=INK,width=6)
            for i in range(3): d.rectangle((x+18+i*52,260,x+53+i*52,310),fill=(68,92,117))
        d.rectangle((0,574,W,H),fill=(38,33,32))
    elif kind=="map":
        d.rectangle((0,96,W,575),fill=(203,188,149))
        # stylized US landmass, route lines and roads
        d.polygon([(125,225),(260,178),(360,195),(445,164),(565,191),(675,175),(770,214),(890,202),(1014,235),(1140,268),(1110,348),(1010,391),(927,360),(837,412),(725,387),(649,411),(554,376),(447,390),(375,344),(276,366),(210,307)],fill=(169,159,133),outline=INK)
        for i in range(7):
            y=232+i*27; d.line((220,y,1060,y+int(35*math.sin(i))),fill=(187,171,135),width=2)
        d.line((0,575,W,575),fill=INK,width=7); d.rectangle((0,575,W,H),fill=(31,34,45))
    elif kind=="court":
        d.rectangle((0,92,W,574),fill=(50,39,43))
        for x in (130,360,920,1150):
            d.rectangle((x,105,x+90,512),fill=(110,76,67),outline=INK,width=6)
            d.polygon([(x-24,124),(x+45,80),(x+114,124)],fill=(140,102,81),outline=INK)
        d.rectangle((0,516,W,576),fill=(99,66,59),outline=INK,width=6)
        d.rectangle((0,576,W,H),fill=(34,28,35))
        d.ellipse((548,99,732,164),fill=(75,59,57),outline=GOLD,width=4)
        center_text(d,(640,131),"UNITED STATES",font(str(FONT_KALAM),17),CREAM)
    elif kind=="warm":
        d.rectangle((0,94,W,570),fill=(101,74,57))
        d.rectangle((45,142,400,390),fill=(42,53,68),outline=INK,width=7)
        d.line((220,145,220,390),fill=(163,127,95),width=4)
        for i in range(5): d.rectangle((72+i*57,177,85+i*57,212),fill=GOLD)
        d.rectangle((0,424,500,572),fill=(113,76,63),outline=INK,width=8)
        d.rectangle((46,405,452,466),fill=(152,105,79),outline=INK,width=6)
        d.rectangle((0,572,W,H),fill=(50,38,35))
        # sun-like warm table lamp
        d.ellipse((930,168,1230,470),fill=(92,67,51)); d.line((1080,490,1080,375),fill=INK,width=14)
        d.polygon([(1010,380),(1150,380),(1180,300),(980,300)],fill=(236,183,91),outline=INK)
    elif kind=="paper":
        d.rectangle((0,90,W,570),fill=(31,37,56))
        for i in range(11):
            x=i*127+((int(t*12)%35)-17); y=120+(i*67)%380
            d.ellipse((x,y,x+3,y+3),fill=(90,110,150))
        d.rectangle((0,570,W,H),fill=(19,25,41))


def card(d, box, title=None, fill=(20,26,48), outline=GOLD, radius=18):
    rounded(d,box,radius,fill,outline,5)
    if title:
        x0,y0,x1,y1=box
        rounded(d,(x0+15,y0+13,x1-15,y0+58),10,(37,48,77),outline,2)
        center_text(d,((x0+x1)/2,y0+35),title,font(str(FONT_KALAM),21),CREAM)


def scene_art(image, d, scene, local, t, speech):
    # All major elements have local progress: entrance, pop, count-up, route, or draw-on.
    if scene=="doorstep":
        # Door opens; visitor walks toward porch light; over-shoulder framing.
        d.rectangle((820,128,1096,568),fill=(31,31,46),outline=INK,width=9)
        d.rectangle((855,158,1065,568),fill=(17,22,39),outline=(111,103,102),width=4)
        d.ellipse((1020,370,1040,390),fill=GOLD,outline=INK,width=2)
        d.rectangle((0,558,W,H),fill=(22,25,34)); d.line((0,558,W,558),fill=INK,width=7)
        x=190+min(1,local*2.0)*260
        draw_puppet(d,x,560,.72,t,"courier","worried","walk",0,phase=0.3,tag="THE VISITOR")
        # bell rings in pulses
        if local<.55:
            r=22+int(22*(.5+.5*math.sin(t*9)))
            d.arc((1030-r,225-r,1030+r,225+r),215,325,fill=GOLD,width=5)
            d.arc((1030-r-18,225-r-18,1030+r+18,225+r+18),215,325,fill=GOLD,width=3)
        pop=pop_scale(local)
        center_text(d,(460,198),"CASH PICKUP",font(str(FONT_MARKER),int(38*pop)),RED,2)
        arrow(d,(562,235),(788,294),GOLD,5,17)
    elif scene=="funeral_room":
        # Casket, flowers and a reveal of the fake mourners.
        d.polygon([(400,430),(822,430),(895,505),(333,505)],fill=(101,58,49),outline=INK)
        d.polygon([(415,366),(804,366),(851,430),(370,430)],fill=(150,98,62),outline=INK)
        d.line((456,401,782,401),fill=GOLD,width=8)
        d.rectangle((560,378,676,408),fill=(76,48,43),outline=INK,width=3)
        center_text(d,(618,393),"MORTIMER",font(str(FONT_KALAM),16),CREAM)
        reveal=ease_out(local)
        dialogue=speech if .18<local<.72 else 0
        draw_puppet(d,230,567,.70,t,"courier","shocked","phone",0,phase=.1,tag="THE VISITOR")
        draw_puppet(d,840+int(reveal*22),567,.83,t,"host_red","suspicious","point",dialogue,phase=1.1,tag="ASH / HOST")
        draw_puppet(d,1050+int(reveal*14),567,.77,t,"host_teal","stern","reassure",dialogue*.4,phase=2.1,tag="ART / HOST")
        center_text(d,(640,136),"THE DEAD MAN WAS FICTIONAL",font(str(FONT_MARKER),31),CREAM,2)
        # red marker circle sweeps around the casket plaque
        d.arc((317,343,901,523),205,205+int(350*local),fill=RED,width=7)
    elif scene=="hook_numbers":
        # Big cold-open stakes, count-up and human silhouettes.
        card(d,(254,145,1026,472),"THE WIDER SCHEME",(17,23,46),GOLD)
        amount=int(27_000_000*ease_out(local))
        label=f"${amount/1_000_000:.1f}M" if amount<27_000_000 else "$27M"
        center_text(d,(640,286),label,font(str(FONT_MARKER),98),GOLD,2)
        center_text(d,(640,368),"2,000+ OLDER VICTIMS",font(str(FONT_KALAM),29),CREAM)
        for i in range(13):
            x=300+i*57; h=24+(i*19)%33
            d.ellipse((x-12,510-h,x+12,534-h),fill=(195,164,127),outline=INK,width=2)
            d.rounded_rectangle((x-16,534-h,x+16,574),radius=9,fill=(68,79,112),outline=INK,width=2)
        d.line((320,580,960,580),fill=GOLD,width=3)
    elif scene=="question":
        # Typographic chapter card with pen underline and animated question mark.
        d.rectangle((0,96,W,590),fill=(8,11,27))
        text="HOW DOES A REFUND"
        visible=max(1,int(len(text)*min(1,local*2.2)))
        center_text(d,(640,262),text[:visible],font(str(FONT_MARKER),48),CREAM)
        text2="BECOME A BOX OF CASH?"
        visible2=max(0,int(len(text2)*max(0,min(1,(local-.2)*2.3))))
        center_text(d,(640,337),text2[:visible2],font(str(FONT_MARKER),52),LIME)
        d.line((252,410,252+int(775*ease_out(local)),410),fill=RED,width=9)
        qy=483+int(14*math.sin(t*3.3))
        center_text(d,(640,qy),"?",font(str(FONT_HAND),140),GOLD)
    elif scene=="victim_home":
        draw_puppet(d,320,565,.78,t,"victim","worried","phone",0,phase=.4,tag="THE TARGET")
        # phone buzz rings; incoming message pops onto phone screen
        for k in range(3):
            r=28+k*14+int(5*math.sin(t*8+k))
            d.arc((610-r,350-r,610+r,350+r),225,315,fill=GOLD,width=3)
        card(d,(712,182,1155,387),"UNKNOWN NUMBER",(20,27,48),RED)
        center_text(d,(934,274),"ACCOUNT ALERT",font(str(FONT_MARKER),29),CREAM)
        center_text(d,(934,326),"CALL THIS NUMBER",font(str(FONT_KALAM),23),GOLD)
        d.line((0,577,W,577),fill=INK,width=8)
        center_text(d,(640,168),"UNSOLICITED CALL  ·  EMAIL  ·  POP-UP",font(str(FONT_KALAM),21),CREAM)
    elif scene=="call_center":
        # Dark operation room with a generic caller at a headset.
        for i in range(4):
            x=98+i*285
            rounded(d,(x,159,x+226,325),12,(16,23,43),(81,104,148),4)
            d.rectangle((x+16,177,x+210,291),fill=(19,37,60))
            d.line((x+32,208,x+190,208),fill=(67,141,153),width=4)
            d.line((x+32,232,x+154,232),fill=(181,103,79),width=4)
        draw_puppet(d,636,570,.84,t,"agent","smile","phone",speech,phase=1.2,tag="CALLER")
        d.arc((697,280,777,364),85,275,fill=GOLD,width=5)
        for i in range(3):
            x=130+i*410; d.line((x,377,x+280,377),fill=(71,85,117),width=3)
            d.line((x,393,x+205,393),fill=(71,85,117),width=3)
        center_text(d,(640,120),"SCRIPTS  /  TRUST  /  PRESSURE",font(str(FONT_MARKER),30),GOLD)
    elif scene=="warning_screen":
        card(d,(202,147,1078,510),"SYSTEM MESSAGE",(222,216,196),RED)
        center_text(d,(640,250),"SECURITY ALERT",font(str(FONT_MARKER),44),RED)
        center_text(d,(640,321),"YOUR ACCOUNT MAY BE AT RISK",font(str(FONT_KALAM),27),INK)
        progress=int(550*ease_out(local))
        rounded(d,(363,371,917,414),14,(177,170,157),INK,3)
        rounded(d,(363,371,363+progress,414),14,RED,RED,2)
        # cursor travels to the call button
        cx=430+min(1,local*1.6)*395; cy=456
        rounded(d,(467,438,813,485),10,(42,65,105),INK,4)
        center_text(d,(640,461),"CALL SUPPORT NOW",font(str(FONT_KALAM),22),CREAM)
        d.polygon([(cx,cy),(cx+21,cy+35),(cx+23,cy+19),(cx+40,cy+13)],fill=CREAM,outline=INK)
    elif scene=="refund_screen":
        card(d,(177,142,1103,514),"REFUND PROCESSING",(232,226,207),INK)
        center_text(d,(404,257),"RETAIL CHARGE",font(str(FONT_KALAM),24),INK)
        center_text(d,(848,257),"$ 49.99",font(str(FONT_MARKER),31),INK)
        d.line((270,293,1010,293),fill=(145,133,110),width=3)
        center_text(d,(404,349),"REFUND SENT",font(str(FONT_KALAM),25),INK)
        cents=int(300000*ease_out(local))
        center_text(d,(848,349),f"$ {cents/100:.2f}",font(str(FONT_MARKER),36),(42,108,76))
        # progress bar over the alleged credit
        d.rectangle((300,405,980,439),fill=(177,168,148),outline=INK,width=2)
        d.rectangle((300,405,300+int(680*local),439),fill=LIME)
        center_text(d,(640,477),"A NUMBER ON A SCREEN IS NOT PROOF",font(str(FONT_KALAM),19),RED)
    elif scene=="fake_refund":
        # Split screen: supposed overpayment versus the actual bank balance.
        card(d,(76,156,602,483),"WHAT THE CALLER CLAIMS",(222,217,199),RED)
        card(d,(678,156,1204,483),"WHAT REALLY HAPPENED",(28,34,56),GOLD)
        center_text(d,(339,276),"+ $3,000",font(str(FONT_MARKER),58),(35,117,80))
        center_text(d,(339,350),"“WE SENT TOO MUCH”",font(str(FONT_KALAM),20),INK)
        center_text(d,(941,276),"$0",font(str(FONT_MARKER),86),RED)
        center_text(d,(941,350),"NO REFUND WAS SENT",font(str(FONT_KALAM),20),CREAM)
        # animated cross-out slash and marker circle
        d.line((205,385,205+int(265*local),385-int(92*local)),fill=RED,width=12)
        d.arc((770,210,1110,370),220,220+int(340*local),fill=RED,width=7)
        arrow(d,(614,321),(663,321),GOLD,6,16)
    elif scene=="cash_wire":
        # Money departs by wire or paper parcel; route animates one currency token.
        card(d,(94,160,594,488),"WIRE TRANSFER",(20,29,53),GOLD)
        card(d,(686,160,1186,488),"CASH IN THE MAIL",(20,29,53),GOLD)
        for j in range(5):
            y=233+j*38; d.line((146,y,510,y),fill=(70,87,119),width=3)
        d.rectangle((245,294,452,395),fill=(61,99,72),outline=INK,width=5)
        center_text(d,(348,345),"$",font(str(FONT_MARKER),58),GOLD)
        d.rectangle((826,282,1048,408),fill=(156,105,62),outline=INK,width=5)
        d.line((937,282,937,408),fill=GOLD,width=7)
        arrow(d,(410,452),(870,452),RED,5,16)
        token_x=432+int(395*local)
        d.ellipse((token_x-28,419,token_x+28,475),fill=GOLD,outline=INK,width=4)
        center_text(d,(token_x,447),"$",font(str(FONT_KALAM),25),INK)
        center_text(d,(640,543),"THE VICTIM’S OWN MONEY",font(str(FONT_MARKER),25),CREAM)
    elif scene=="parcel_counter":
        # Retail package shop; boxes pass across a counter in a visible conveyor loop.
        for i in range(4):
            bx=(95+i*300-int((t*52)%240))%1280
            d.rectangle((bx,306,bx+150,438),fill=(167,120,72),outline=INK,width=5)
            d.line((bx+75,306,bx+75,438),fill=GOLD,width=5)
            d.line((bx+21,307,bx+75,357,bx+130,307),fill=GOLD,width=5)
            if i==1:
                rounded(d,(bx+22,355,bx+124,397),5,CREAM,INK,2)
                center_text(d,(bx+73,376),"FAKE NAME",font(str(FONT_KALAM),14),RED)
        d.rectangle((0,470,W,574),fill=(94,65,51),outline=INK,width=7)
        draw_puppet(d,1050,568,.67,t,"victim","sad","hold",0,phase=2.4,tag="SENDER")
        center_text(d,(340,240),"A FALSE NAME ON THE LABEL",font(str(FONT_MARKER),25),CREAM)
        center_text(d,(340,278),"A REAL PERSON SENT THE CASH",font(str(FONT_KALAM),18),GOLD)
    elif scene=="pickup_id":
        # Close-up of package label, a mismatched ID, and a handoff.
        d.polygon([(110,285),(660,240),(900,321),(340,374)],fill=(171,124,74),outline=INK)
        d.polygon([(340,374),(900,321),(900,529),(340,578)],fill=(143,97,62),outline=INK)
        d.polygon([(110,285),(340,374),(340,578),(110,480)],fill=(116,76,53),outline=INK)
        d.line((340,374,340,576),fill=CREAM,width=6)
        d.line((440,260,530,356,625,247),fill=GOLD,width=11)
        # ID card slides in and flips to red side
        slide=int(560*ease_out(local))
        rounded(d,(120+slide,415,365+slide,533),12,(230,224,207),INK,5)
        d.ellipse((143+slide,437,190+slide,484),fill=(178,132,101),outline=INK,width=3)
        d.line((208+slide,448,335+slide,448),fill=INK,width=4)
        d.line((208+slide,467,324+slide,467),fill=(95,99,106),width=3)
        center_text(d,(242+slide,507),"FALSE ID",font(str(FONT_MARKER),19),RED)
        draw_puppet(d,1080,565,.7,t,"courier","suspicious","hold",0,phase=.8,tag="COLLECTOR")
    elif scene=="crypto_route":
        # Stylized route from pickup locations to overseas money movement.
        d.rectangle((76,142,1204,505),fill=(201,185,145),outline=INK,width=6)
        d.polygon([(135,242),(240,202),(334,221),(411,189),(515,214),(619,197),(741,235),(831,219),(952,252),(1090,284),(1064,350),(981,391),(882,358),(812,407),(720,376),(622,404),(526,370),(426,385),(355,343),(260,363),(194,310)],fill=(165,155,128),outline=INK)
        # points: California / Nevada / overseas counterparty
        pts=[(283,310),(430,300),(984,278)]
        for x,y in pts: d.ellipse((x-13,y-13,x+13,y+13),fill=RED,outline=INK,width=3)
        d.line((pts[0][0],pts[0][1],pts[1][0],pts[1][1]),fill=RED,width=5)
        d.line((pts[1][0],pts[1][1],pts[2][0],pts[2][1]),fill=RED,width=5)
        u=(local*1.8)%1; mx=int(pts[1][0]+(pts[2][0]-pts[1][0])*u); my=int(pts[1][1]+(pts[2][1]-pts[1][1])*u)
        d.ellipse((mx-18,my-18,mx+18,my+18),fill=GOLD,outline=INK,width=4)
        center_text(d,(mx,my),"$",font(str(FONT_KALAM),20),INK)
        label=font(str(FONT_KALAM),18)
        center_text(d,(283,346),"SOUTHERN CA",label,INK)
        center_text(d,(430,336),"NEVADA",label,INK)
        center_text(d,(984,325),"OVERSEAS",label,INK)
        center_text(d,(640,546),"CRYPTO TRANSFERRED PROCEEDS",font(str(FONT_MARKER),24),CREAM)
    elif scene=="sting_room":
        d.polygon([(335,432),(727,432),(797,500),(281,500)],fill=(101,57,47),outline=INK)
        d.polygon([(349,369),(709,369),(759,432),(310,432)],fill=(150,97,62),outline=INK)
        d.line((387,400,681,400),fill=GOLD,width=8)
        dialogue=speech if .08<local<.67 else 0
        draw_puppet(d,216,568,.70,t,"courier","shocked","phone",0,phase=.2,tag="CHEN")
        draw_puppet(d,842,568,.82,t,"host_red","suspicious","point",dialogue,phase=1.2,tag="ASHTON")
        draw_puppet(d,1062,568,.80,t,"host_teal","stern","reassure",dialogue*.3,phase=2.2,tag="ART")
        # Soft amber spotlight opens on the hosts as the sting is revealed.
        spotlight=Image.new("RGBA",(W,H),(0,0,0,0))
        sd=ImageDraw.Draw(spotlight)
        sd.polygon([(590,90),(690,90),(971,364),(310,364)],fill=(GOLD[0],GOLD[1],GOLD[2],int(62*ease_out(local))))
        image.paste(Image.alpha_composite(image.convert("RGBA"),spotlight).convert("RGB"))
        d=ImageDraw.Draw(image)
        # red camera tally lamp pulses
        if math.sin(t*8)>0:
            d.ellipse((1180,111,1208,139),fill=RED,outline=CREAM,width=2)
        center_text(d,(640,197),"CONFRONTING SCAMMERS",font(str(FONT_MARKER),32),CREAM,2)
    elif scene=="viral_frame":
        # Video monitor framing: the clip is a single clue, not the whole case.
        rounded(d,(142,132,1138,526),22,(8,12,24),GOLD,6)
        d.rectangle((164,154,1116,492),fill=(31,37,54),outline=INK,width=4)
        # grayscale-ish staged frame
        d.rectangle((185,173,1096,480),fill=(50,48,57))
        d.rectangle((250,230,430,480),fill=(33,36,48),outline=(128,114,97),width=4)
        d.polygon([(555,374),(800,374),(850,420),(517,420)],fill=(97,57,48),outline=INK)
        dialogue=speech if local<.64 else 0
        draw_puppet(d,485,475,.49,t,"courier","suspicious","walk",0,phase=.5,tag=None)
        draw_puppet(d,797,474,.51,t,"host_red","stern","point",dialogue,phase=1.5,tag=None)
        center_text(d,(640,557),"ONE MOMENT FROM A MUCH LARGER RECORD",font(str(FONT_KALAM),22),CREAM)
        # recording ring expands, then fades
        r=20+int(14*(.5+.5*math.sin(t*5)))
        d.ellipse((1050-r,188-r,1050+r,188+r),outline=RED,width=5)
        center_text(d,(1050,188),"REC",font(str(FONT_KALAM),12),RED)
    elif scene=="evidence_wall":
        # corkboard with separate evidence cards sliding into place.
        d.rectangle((105,133,1175,518),fill=(107,72,50),outline=INK,width=9)
        for i,(title,txt) in enumerate([("PACKAGES","cash pickups"),("VIDEO","counting cash"),("TIMELINE","2023 → Dec 22"),("PLEA","admitted role")]):
            x=145+i*253; y=184+(i%2)*104
            slide=int((1-ease_out(min(1,local*2.2)))*60)
            rounded(d,(x,y+slide,x+209,y+slide+122),8,(230,223,202),INK,4)
            center_text(d,(x+104,y+slide+34),title,font(str(FONT_MARKER),17),RED)
            center_text(d,(x+104,y+slide+80),txt,font(str(FONT_KALAM),18),INK)
            d.line((x+104,y+slide,x+104,y+slide+122),fill=(99,78,61),width=2)
        # connecting string draws between cards
        d.line((351,286,397,391),fill=RED,width=4)
        d.line((604,391,651,286),fill=RED,width=4)
        d.line((856,286,909,391),fill=RED,width=4)
        d.ellipse((617,299,633,315),fill=GOLD,outline=INK,width=2)
        center_text(d,(640,552),"PROSECUTORS DESCRIBED OTHER EVIDENCE TOO",font(str(FONT_KALAM),20),CREAM)
    elif scene=="courthouse":
        # Exterior courthouse and a generic defendant walking toward the steps.
        d.rectangle((220,205,1060,504),fill=(125,91,74),outline=INK,width=7)
        d.polygon([(180,220),(640,112),(1100,220)],fill=(162,119,86),outline=INK,width=8)
        for x in (330,485,640,795,950):
            d.rectangle((x,236,x+50,480),fill=(214,192,155),outline=INK,width=4)
        for i in range(4): d.rectangle((140-i*24,490+i*19,1140+i*24,510+i*19),fill=(111,79,66),outline=INK,width=3)
        draw_puppet(d,635,560,.63,t,"courier","stern","walk",0,phase=.1,tag="GUILTY PLEA")
        center_text(d,(640,92),"APRIL 2026",font(str(FONT_MARKER),30),GOLD)
    elif scene=="court_sentence":
        # Courtroom bench + gavel, impact rings, 78-month stamp.
        d.rectangle((0,426,W,575),fill=(91,57,50),outline=INK,width=7)
        d.rectangle((0,535,W,577),fill=(128,79,62),outline=INK,width=5)
        judge_speech=speech if local>.47 else 0
        draw_puppet(d,251,566,.66,t,"judge","stern","point",judge_speech,phase=.4,tag="THE JUDGE")
        draw_puppet(d,1000,566,.68,t,"courier","sad","idle",0,phase=1.7,tag="CHEN")
        # gavel swings down on a sharply timed beat
        swing=math.sin(min(1,local*2.2)*math.pi/2)*0.8
        x1,y1=676,323; x2=int(794-76*swing); y2=int(395+30*swing)
        d.line((x1,y1,x2,y2),fill=(143,86,54),width=32)
        d.ellipse((x1-34,y1-18,x1+39,y1+18),fill=(178,117,71),outline=INK,width=5)
        d.ellipse((x2-52,y2-20,x2+52,y2+20),fill=(177,118,73),outline=INK,width=5)
        if local>.35:
            r=int(25+80*ease_out((local-.35)/.65))
            d.arc((x2-r,y2-r,x2+r,y2+r),195,345,fill=GOLD,width=5)
        # sentence stamp drops in
        u=max(0,min(1,(local-.28)*2.2)); scale=pop_scale(u,.18)
        center_text(d,(650,198),"78 MONTHS",font(str(FONT_MARKER),int(61*scale)),RED,2)
        center_text(d,(650,252),"SIX AND A HALF YEARS",font(str(FONT_KALAM),23),CREAM)
    elif scene=="case_numbers":
        # Distinguish the aggregate scheme from Chen's admitted losses.
        card(d,(91,153,611,487),"WIDER SCHEME",(18,25,48),GOLD)
        card(d,(669,153,1189,487),"CHEN’S ADMITTED ROLE",(18,25,48),RED)
        a=int(27*ease_out(local)); b=int(9.5*ease_out(local))
        center_text(d,(351,294),f"${a}M+",font(str(FONT_MARKER),72),GOLD)
        center_text(d,(929,294),f"${b}M+",font(str(FONT_MARKER),72),CREAM)
        center_text(d,(351,382),"2,000+ VICTIMS",font(str(FONT_KALAM),24),CREAM)
        center_text(d,(929,382),"LOSS DURING HIS ROLE",font(str(FONT_KALAM),21),CREAM)
        arrow(d,(614,319),(666,319),RED,5,14)
        center_text(d,(640,540),"RELATED FIGURES. DIFFERENT SCOPES.",font(str(FONT_MARKER),23),LIME)
    elif scene=="human_impact":
        # Real human cost shown respectfully, not as spectacle.
        d.rectangle((122,144,1158,498),fill=(25,29,47),outline=(108,98,90),width=5)
        for i in range(5):
            x=232+i*205
            skin=(219-i*4,184-i*5,147-i*3)
            d.ellipse((x-48,203,x+48,299),fill=skin,outline=INK,width=5)
            d.arc((x-63,185,x+63,317),185,355,fill=(201,192,164),width=13)
            d.rounded_rectangle((x-57,294,x+57,431),radius=36,fill=(62+i*5,72+i*4,101+i*3),outline=INK,width=5)
            if i%2==0: d.arc((x-15,250,x+14,280),205,330,fill=INK,width=3)
        # words arrive with separate handwritten underlines
        words=["DIGNITY","TRUST","PEACE"]
        for i,w in enumerate(words):
            x=320+i*320; u=max(0,min(1,(local-i*.2)*3))
            center_text(d,(x,514),w[:max(1,int(len(w)*u))],font(str(FONT_MARKER),24),GOLD)
            d.line((x-74,539,x-74+int(148*u),539),fill=RED,width=4)
        center_text(d,(640,584),"THE JUDGE SAID THE HARM WAS MORE THAN MONEY",font(str(FONT_KALAM),18),CREAM)
    elif scene=="two_totals":
        # Final accounting correction with visual, animated scale comparison.
        center_text(d,(640,136),"A NECESSARY DISTINCTION",font(str(FONT_MARKER),30),CREAM)
        heights=[int(230*ease_out(local)),int(130*ease_out(local))]
        d.rectangle((305,493-heights[0],490,493),fill=GOLD,outline=INK,width=5)
        d.rectangle((790,493-heights[1],975,493),fill=RED,outline=INK,width=5)
        center_text(d,(397,226),"$27M+",font(str(FONT_MARKER),43),GOLD)
        center_text(d,(882,328),"$9.5M+",font(str(FONT_MARKER),43),CREAM)
        center_text(d,(397,532),"ALL IDENTIFIED VICTIMS",font(str(FONT_KALAM),17),CREAM)
        center_text(d,(882,532),"CHEN’S ADMITTED LOSS",font(str(FONT_KALAM),17),CREAM)
        center_text(d,(640,590),"NOT THE SAME MEASURE",font(str(FONT_MARKER),23),LIME)
    elif scene=="safety_home":
        draw_puppet(d,272,565,.76,t,"victim","worried","phone",0,phase=.1,tag="PAUSE FIRST")
        card(d,(590,159,1158,465),"THE CALLER SAYS…",(28,33,48),RED)
        center_text(d,(874,261),"“ACT NOW”",font(str(FONT_MARKER),41),CREAM)
        center_text(d,(874,335),"“SEND MONEY”",font(str(FONT_MARKER),39),RED)
        # Incoming pressure pulses, then pause glyph grows.
        for i in range(3):
            r=32+i*22+int(6*math.sin(t*8+i))
            d.arc((885-r,367-r,885+r,367+r),205,335,fill=GOLD,width=3)
        d.ellipse((468,443,544,519),fill=LIME,outline=INK,width=5)
        center_text(d,(506,480),"Ⅱ",font(str(FONT_KALAM),34),INK)
        center_text(d,(640,565),"URGENCY IS A REASON TO STOP",font(str(FONT_MARKER),24),CREAM)
    elif scene=="verify_steps":
        # Animated checklist cards slide in one at a time.
        items=[("01","HANG UP"),("02","USE AN OFFICIAL NUMBER"),("03","ASK SOMEONE YOU TRUST")]
        for i,(num,label) in enumerate(items):
            target_y=168+i*128
            reveal=max(0,min(1,(local-i*.20)*3.0))
            y=int(target_y+(1-reveal)*95)
            rounded(d,(230,y,1050,y+94),17,(232,226,208),INK,5)
            d.ellipse((252,y+20,306,y+74),fill=LIME,outline=INK,width=3)
            center_text(d,(279,y+47),num,font(str(FONT_KALAM),18),INK)
            d.text((339,y+46),label,font=font(str(FONT_MARKER),27),fill=INK,anchor="lm")
            if reveal>.88:
                d.line((960,y+47,994,y+64),fill=RED,width=6)
                d.line((994,y+64,1034,y+24),fill=RED,width=6)
        center_text(d,(640,574),"NEVER MAIL CASH TO FIX A COMPUTER",font(str(FONT_KALAM),19),CREAM)
    elif scene=="closing_polaroid":
        # Final callback: paper frame swings into place and gets circled.
        u=ease_out(local)
        cx=640; cy=int(335+(1-u)*145)
        d.rounded_rectangle((312,126,968,529),radius=10,fill=(13,17,32),outline=(7,9,18),width=9)
        d.rectangle((336,151,944,454),fill=(27,34,57),outline=CREAM,width=6)
        d.polygon([(430,350),(645,350),(695,405),(392,405)],fill=(119,70,54),outline=INK)
        draw_puppet(d,496,447,.48,t,"courier","suspicious","walk",0,phase=.3,tag=None)
        draw_puppet(d,750,447,.48,t,"host_red","stern","point",0,phase=1.3,tag=None)
        d.rectangle((336,454,944,505),fill=CREAM)
        center_text(d,(640,479),"THE CASE BEHIND THE CLIP",font(str(FONT_MARKER),22),INK)
        end=int(350*local)
        d.arc((367,167,915,476),205,205+end,fill=RED,width=10)
        center_text(d,(640,576),"THE RECORD REVEALED THE SYSTEM",font(str(FONT_KALAM),22),LIME)
    else:  # closing_message
        d.rectangle((0,95,W,590),fill=(7,10,25))
        headline="EVIDENCE REVEALS THE SYSTEM"
        count=max(1,int(len(headline)*min(1,local*2.4)))
        pop=pop_scale(local)
        center_text(d,(640,238),headline[:count],font(str(FONT_MARKER),int(51*pop)),GOLD,2)
        sub="STOP  ·  VERIFY  ·  ASK FOR HELP"
        v=max(0,int(len(sub)*max(0,min(1,(local-.18)*2.5))))
        center_text(d,(640,341),sub[:v],font(str(FONT_KALAM),28),LIME)
        # red marker ring draws around final checkmark
        d.arc((550,399,730,579),210,210+int(360*local),fill=RED,width=9)
        a=(604,493); b=(632,521); c=(683,454)
        if local<.48:
            q=ease_out(local/.48); end=(int(a[0]+(b[0]-a[0])*q),int(a[1]+(b[1]-a[1])*q))
            d.line((a,end),fill=CREAM,width=12)
        else:
            d.line((a,b),fill=CREAM,width=12)
            q=ease_out((local-.48)/.52); end=(int(b[0]+(c[0]-b[0])*q),int(b[1]+(c[1]-b[1])*q))
            d.line((b,end),fill=CREAM,width=12)
        for i in range(3):
            x=430+i*210
            d.line((x,576,x+125,576),fill=GOLD,width=4)


def make_base(scene, local, t, speech):
    image=Image.new("RGB",(W,H),NAVY)
    d=ImageDraw.Draw(image)
    bg_kind={
        "doorstep":"night","funeral_room":"funeral","hook_numbers":"paper","question":"paper",
        "victim_home":"home","call_center":"office","warning_screen":"office",
        "refund_screen":"home","fake_refund":"paper","cash_wire":"paper",
        "parcel_counter":"retail","pickup_id":"retail","crypto_route":"map",
        "sting_room":"funeral","viral_frame":"paper","evidence_wall":"paper",
        "courthouse":"court","court_sentence":"court","case_numbers":"paper",
        "human_impact":"warm","two_totals":"paper","safety_home":"warm","verify_steps":"warm",
        "closing_polaroid":"paper","closing_message":"night",
    }[scene]
    background(d,bg_kind,t,local)
    scene_art(image,d,scene,local,t,speech)
    # Chapter header slides in and types itself; changing locations no longer share one generic backdrop.
    d.rectangle((0,0,W,76),fill=(8,11,27))
    d.line((0,76,W,76),fill=GOLD,width=3)
    title=TITLES[scene]
    chars=max(1,int(len(title)*ease_out(min(1,local*3.0))))
    d.text((48,38),title[:chars],font=font(str(FONT_KALAM),20),fill=GOLD,anchor="lm")
    # persistent chapter-progress rail
    d.rectangle((W-239,30,W-59,42),fill=(44,52,75))
    d.rectangle((W-239,30,W-239+int(180*local),42),fill=RED)
    d.text((W-55,36),"CASE FILE",font=font(str(FONT_KALAM),13),fill=CREAM,anchor="rm")
    # shot-specific slow push and lateral drift
    zoom=1.0+0.045*ease_out(local)
    nw,nh=int(W*zoom),int(H*zoom)
    image=image.resize((nw,nh),Image.Resampling.BICUBIC)
    maxx=nw-W; maxy=nh-H
    dx=int(maxx*(.25+.5*local)); dy=int(maxy*(.52+.08*math.sin(local*math.pi)))
    image=image.crop((dx,dy,dx+W,dy+H))
    return image


def alloc_timeline():
    audios=[]
    durations=[]
    for p in AUDIO_PATHS:
        arr,sr=sf.read(p,dtype="float32")
        if arr.ndim>1: arr=arr.mean(axis=1)
        audios.append((arr,sr)); durations.append(len(arr)/sr)
    gap=.38; timeline=[]; cursor=0.0
    for gi,(indices,(arr,sr),dur) in enumerate(zip(AUDIO_GROUPS,audios,durations)):
        if sr!=24000: raise ValueError(f"Expected 24 kHz speech, got {sr} in voice_{gi+1:02d}.wav")
        weights=[len(PARAGRAPHS[i].split()) for i in indices]
        pause_budget=min(.65*max(0,len(indices)-1),dur*.08)
        speaking=max(.01,dur-pause_budget); total=sum(weights)
        for idx,nw in zip(indices,weights):
            span=speaking*nw/total
            timeline.append((idx,cursor,cursor+span))
            cursor+=span
            if idx!=indices[-1]: cursor+=pause_budget/max(1,len(indices)-1)
        cursor += gap if gi<len(AUDIO_GROUPS)-1 else 0
    return audios,timeline,cursor,gap


def build_subtitles(timeline):
    subs=[]
    for idx,start,end in timeline:
        words=PARAGRAPHS[idx].split()
        groups=[words[i:i+9] for i in range(0,len(words),9)]
        weights=[len(g) for g in groups]; total=sum(weights); cur=start
        for group,n in zip(groups,weights):
            stop=cur+(end-start)*n/total
            txt=" ".join(group)
            subs.append((cur,stop,txt))
            cur=stop
    path=ROOT/"fake_funeral_27m_scam.srt"
    def stamp(s):
        ms=int(round(s*1000)); hh=ms//3600000; ms%=3600000; mm=ms//60000; ms%=60000; ss=ms//1000; ms%=1000
        return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"
    with path.open("w") as f:
        for i,(a,b,txt) in enumerate(subs,1):
            lines=textwrap.wrap(txt,width=50)
            f.write(f"{i}\n{stamp(a)} --> {stamp(b)}\n"+"\n".join(lines[:2])+"\n\n")
    return subs


def make_music(length,sr=24000):
    """Original low-level minor-key underscore, synthesized in code and ducked."""
    n=int(length*sr); music=np.zeros((n,2),dtype=np.float32)
    beat=60/84; bar=beat*4; chord_len=bar*2
    progression=[(146.83,174.61,220.,293.66),(116.54,174.61,233.08,293.66),(130.81,174.61,220.,261.63),(130.81,196.,261.63,329.63)]
    for ci in range(int(math.ceil(length/chord_len))):
        start=ci*chord_len; end=min(length,start+chord_len)
        i0=int(start*sr); i1=min(n,int(end*sr))
        if i1<=i0: continue
        local=np.arange(i1-i0,dtype=np.float32)/sr
        env=np.minimum(1,local/.7)*np.minimum(1,(end-start-local)/.9)
        pad=np.zeros(i1-i0,dtype=np.float32)
        for j,hz in enumerate(progression[ci%4]):
            phase=2*np.pi*hz*local
            pad+=(np.sin(phase)+.16*np.sin(2*phase))*(.20 if j==0 else .11)
        pattern=[293.66,349.23,392.,349.23,261.63,329.63,392.,329.63]
        for bi in range(int(math.ceil((end-start)/beat))):
            if bi%2: continue
            ns=start+bi*beat+.08
            if ns>=end: continue
            ni0=int(ns*sr); ni1=min(n,ni0+int(min(.5,end-ns)*sr))
            x=np.arange(ni1-ni0,dtype=np.float32)/sr; e=np.exp(-x*5.2)*np.minimum(1,x/.025)
            hz=pattern[(ci*4+bi//2)%len(pattern)]
            tone=(np.sin(2*np.pi*hz*x)+.18*np.sin(4*np.pi*hz*x))*e*.052
            music[ni0:ni1,0]+=tone*.82; music[ni0:ni1,1]+=tone
        music[i0:i1,0]+=pad*env*.038; music[i0:i1,1]+=pad*env*.043
    ramp=min(int(sr*1.1),n//2)
    if ramp:
        f=np.linspace(0,1,ramp,dtype=np.float32); music[:ramp]*=f[:,None]; music[-ramp:]*=f[::-1,None]
    return music


def speech_energy(voice,sr,t):
    center=int(t*sr); half=int(.025*sr)
    lo=max(0,center-half); hi=min(len(voice),center+half)
    if hi<=lo:return 0.0
    rms=float(np.sqrt(np.mean(voice[lo:hi]**2)+1e-10))
    return max(0,min(1,(rms-.018)/.105))


def caption_frame(image, t, subs):
    active=next((item for item in subs if item[0]<=t<item[1]),None)
    if not active:return image
    a,b,text=active; words=text.split()
    progress=max(0,min(1,(t-a)/max(.001,b-a)))
    count=max(1,min(len(words),int(math.ceil(progress*len(words)))))
    shown=words[:count]
    # Wrap manually to two lines, with the latest word highlighted as it pops in.
    lines=[]; line=[]
    d=ImageDraw.Draw(image)
    f=font(str(FONT_KALAM),25)
    for word in shown:
        cand=line+[word]
        width=sum(d.textbbox((0,0),w,font=f)[2] for w in cand)+10*(len(cand)-1)
        if width>1080 and line:
            lines.append(line); line=[word]
        else:line=cand
    if line:lines.append(line)
    lines=lines[-2:]
    overlay=Image.new("RGBA",(W,H),(0,0,0,0)); od=ImageDraw.Draw(overlay)
    slide=int(22*(1-min(1,progress*8)))
    od.rounded_rectangle((48,610+slide,1232,701+slide),radius=17,fill=(6,9,23,238),outline=(242,193,78,245),width=3)
    line_h=31; start_y=635+slide+(25-len(lines)*line_h)//2
    for li,tokens in enumerate(lines):
        measurements=[]
        for k,wrd in enumerate(tokens):
            ff=font(str(FONT_KALAM),28 if li==len(lines)-1 and k==len(tokens)-1 else 24)
            measurements.append((wrd,ff,od.textbbox((0,0),wrd,font=ff)[2]))
        gap=10; total=sum(x[2] for x in measurements)+gap*(len(measurements)-1)
        x=(W-total)//2
        for k,(wrd,ff,ww) in enumerate(measurements):
            color=GOLD if (li==len(lines)-1 and k==len(measurements)-1 and count<len(words)) else CREAM
            od.text((x,start_y+li*line_h),wrd,font=ff,fill=color,stroke_width=1,stroke_fill=INK)
            x+=ww+gap
    return Image.alpha_composite(image.convert("RGBA"),overlay).convert("RGB")


def prepare_shots(timeline):
    shots=[]
    for p,a,b in timeline:
        for scene,u0,u1 in LAYOUT[p]:
            shots.append({"paragraph":p,"scene":scene,"start":a+(b-a)*u0,"end":a+(b-a)*u1})
    return shots


def transition(current,previous,local):
    if previous is None or local>=.12:return current
    u=max(0,min(1,local/.12)); edge=int(W*u)
    mask=Image.new("L",(W,H),0); md=ImageDraw.Draw(mask); md.rectangle((0,0,edge,H),fill=255)
    blended=Image.composite(current,previous,mask)
    if edge<W:
        d=ImageDraw.Draw(blended)
        d.polygon([(edge-26,0),(edge+8,0),(edge+70,H),(edge+34,H)],fill=GOLD)
        d.polygon([(edge-60,0),(edge-48,0),(edge+14,H),(edge+2,H)],fill=(110,125,153))
    return blended


def main():
    missing=[str(p) for p in AUDIO_PATHS if not p.exists()]
    if missing:raise SystemExit("Missing speech clips: "+", ".join(missing))
    audios,timeline,_,gap=alloc_timeline()
    subs=build_subtitles(timeline); shots=prepare_shots(timeline)
    pieces=[]
    for i,(arr,sr) in enumerate(audios):
        pieces.append(arr)
        if i<len(audios)-1:pieces.append(np.zeros(int(gap*sr),dtype=np.float32))
    voice=np.concatenate(pieces); sr=24000; total=len(voice)/sr
    music=make_music(total,sr)
    hop=480; padded=np.pad(voice,(0,(-len(voice))%hop))
    rms=np.sqrt(np.mean(padded.reshape(-1,hop)**2,axis=1)+1e-10)
    duck=.17+.13*(1-np.clip(rms*5,0,1)); duck=np.repeat(duck,hop)[:len(voice)]
    mix=np.column_stack((voice*.88,voice*.88))+music*duck[:,None]
    mix=np.tanh(mix*1.08)/np.tanh(1.08)
    voice_path=ROOT/"voiceover_combined.wav"
    sf.write(voice_path,mix.astype(np.float32),sr,subtype="PCM_16")
    out=ROOT/"fake_funeral_27m_scam.mp4"
    ffmpeg=os.environ.get("FFMPEG","ffmpeg")
    cmd=[ffmpeg,"-hide_banner","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-i",str(voice_path),"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-shortest","-movflags","+faststart",str(out)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    prev=None; shot_idx=0
    for frame in range(math.ceil(total*FPS)):
        t=frame/FPS
        while shot_idx+1<len(shots) and t>=shots[shot_idx]["end"]:shot_idx+=1
        sh=shots[shot_idx]; local=max(0,min(1,(t-sh["start"])/max(.001,sh["end"]-sh["start"])))
        energy=speech_energy(voice,sr,t)
        base=make_base(sh["scene"],local,t,energy)
        base=transition(base,prev,local)
        image=caption_frame(base,t,subs)
        try:proc.stdin.write(image.tobytes())
        except BrokenPipeError:raise RuntimeError("FFmpeg stopped while encoding; check FFmpeg/libx264")
        prev=base
        if frame%(FPS*4)==0:print(f"Animating {t:6.1f}s / {total:6.1f}s — {sh['scene']}",flush=True)
    proc.stdin.close(); code=proc.wait()
    if code:raise SystemExit(f"FFmpeg exited with status {code}")
    print(f"Saved {out} ({out.stat().st_size/1_000_000:.1f} MB); {len(shots)} animated shots, {total:.2f}s")

if __name__=="__main__":main()
