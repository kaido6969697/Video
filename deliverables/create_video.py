#!/usr/bin/env python3
"""Render an original, code-drawn explainer with Pillow + FFmpeg.

Run from the repository root after generating voice_01.wav ... voice_04.wav:
  .venv/bin/python deliverables/create_video.py
The art uses generic original puppets; it does not reproduce real people's likenesses.
"""
from __future__ import annotations
import math
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H, FPS = 1280, 720, 24
INK = (24, 22, 27)
NAVY = (11, 17, 47)
NAVY2 = (25, 37, 83)
GOLD = (242, 193, 78)
CREAM = (255, 246, 220)
LIME = (184, 240, 74)
RED = (200, 36, 44)
BLUE = (77, 123, 205)
FONT_DIR = ROOT / "fonts"
HAND = ImageFont.truetype(str(FONT_DIR / "CaveatBrush-Regular.ttf"), 56)
LABEL = ImageFont.truetype(str(FONT_DIR / "Kalam-Bold.ttf"), 28)
MARKER = ImageFont.truetype(str(FONT_DIR / "PermanentMarker-Regular.ttf"), 46)
SMALL = ImageFont.truetype(str(FONT_DIR / "Kalam-Bold.ttf"), 22)

PARAGRAPHS = [p.strip() for p in (ROOT / "narration.txt").read_text().split("\n\n") if p.strip()]
AUDIO_GROUPS = [(0, 1, 2), (3, 4), (5, 6, 7), (8, 9)]
AUDIO_PATHS = [ROOT / f"voice_{i:02d}.wav" for i in range(1, 5)]
SCENE_NAMES = [
    "A DOORBELL. A FUNERAL. A SCAM.", "HOW DOES A REFUND BECOME CASH?",
    "THE CALL", "THE FAKE REFUND", "THE CASH PICKUP",
    "THE STING", "FOLLOWING THE EVIDENCE", "THE SCALE OF THE CASE",
    "PAUSE. VERIFY. ASK FOR HELP.", "WHAT WAS HIDING OFF-CAMERA",
]


def rounded(d, box, radius, fill, outline=INK, width=4):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def centered(d, xy, text, font, fill, stroke=0, anchor="mm"):
    d.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=INK)


def wrap_text(text, font, max_width, draw):
    words, lines, line = text.split(), [], ""
    for word in words:
        attempt = word if not line else line + " " + word
        if draw.textbbox((0, 0), attempt, font=font, stroke_width=1)[2] <= max_width:
            line = attempt
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def fit_text(d, text, box, font=HAND, fill=CREAM, max_lines=3, align="center"):
    x0, y0, x1, y1 = box
    lines = wrap_text(text, font, x1 - x0, d)[:max_lines]
    line_h = int(font.size * 1.04)
    y = y0 + max(0, ((y1 - y0) - line_h * len(lines)) // 2)
    for line in lines:
        anchor = "ma" if align == "center" else "la"
        x = (x0 + x1) / 2 if align == "center" else x0
        d.text((x, y), line, font=font, fill=fill, anchor=anchor, stroke_width=2, stroke_fill=INK)
        y += line_h


def background(d, t, scene):
    # A restrained night-paper palette, tiny stars, window silhouettes, and a floor line.
    for y in range(0, H, 4):
        u = y / H
        c = tuple(int(NAVY[k] * (1-u) + NAVY2[k] * u) for k in range(3))
        d.rectangle((0, y, W, y + 4), fill=c)
    for i in range(34):
        x = (i * 173 + (scene * 71)) % W
        y = 36 + (i * 97) % 460
        r = 1 + (i % 3 == 0)
        d.ellipse((x-r, y-r, x+r, y+r), fill=(105, 127, 176))
    # Night skyline through a high window.
    d.rectangle((815, 68, 1190, 352), fill=(14, 23, 58), outline=INK, width=6)
    d.line((1000, 70, 1000, 350), fill=(75, 94, 145), width=4)
    d.line((817, 210, 1188, 210), fill=(75, 94, 145), width=4)
    for i in range(13):
        x = 828 + i * 27
        h = 28 + (i * 37) % 108
        d.rectangle((x, 210-h, x+12, 210), fill=(GOLD if i % 4 == 0 else (64, 77, 126)))
    d.rectangle((0, 590, W, H), fill=(18, 25, 57))
    d.line((0, 590, W, 590), fill=INK, width=8)
    # Warm pool of light, placed behind the main illustration.
    d.ellipse((760, 390, 1300, 890), fill=(34, 39, 70))
    # Painterly desk lamp in the corner.
    d.line((1130, 590, 1130, 438, 1075, 390), fill=INK, width=14)
    d.ellipse((1044, 360, 1128, 415), fill=GOLD, outline=INK, width=6)
    for j in range(3):
        d.line((1056+j*18, 414, 1008+j*35, 560), fill=(99, 88, 89), width=3)


def puppet(d, x, foot, scale=1.0, suit=(55, 75, 135), skin=(226, 185, 143), name=None, pose="idle", t=0):
    # Original simple round-head puppet: consistent outline, no real-person likeness.
    bob = math.sin(t * 2.2 + x * .01) * 4
    x, foot = int(x), int(foot + bob)
    def pt(px, py): return (int(x + px*scale), int(foot + py*scale))
    sw = max(3, int(6 * scale))
    # legs and pill body
    d.line([pt(-20, -108), pt(-25, -10)], fill=INK, width=sw)
    d.line([pt(20, -108), pt(25, -10)], fill=INK, width=sw)
    d.rounded_rectangle((x-int(58*scale), int(foot-224*scale), x+int(58*scale), int(foot-104*scale)), radius=int(42*scale), fill=suit, outline=INK, width=sw)
    d.polygon([pt(-23,-214), pt(0,-170), pt(23,-214)], fill=CREAM, outline=INK)
    d.polygon([pt(-7,-208), pt(7,-208), pt(11,-170), pt(0,-160), pt(-11,-170)], fill=RED, outline=INK)
    # arms
    if pose == "point":
        d.line([pt(-52,-199), pt(-92,-165), pt(-112,-144)], fill=INK, width=sw)
        d.line([pt(52,-199), pt(100,-252), pt(136,-270)], fill=INK, width=sw)
    elif pose == "phone":
        d.line([pt(-52,-198), pt(-86,-158), pt(-50,-137)], fill=INK, width=sw)
        d.line([pt(52,-198), pt(94,-150), pt(72,-130)], fill=INK, width=sw)
    else:
        d.line([pt(-52,-198), pt(-88,-162), pt(-86,-124)], fill=INK, width=sw)
        d.line([pt(52,-198), pt(88,-162), pt(86,-124)], fill=INK, width=sw)
    d.ellipse((x-int(11*scale), int(foot-136*scale), x+int(11*scale), int(foot-114*scale)), fill=skin, outline=INK, width=max(2,sw//2))
    d.ellipse((x-int(98*scale), int(foot-386*scale), x+int(98*scale), int(foot-190*scale)), fill=skin, outline=INK, width=sw)
    # hard-edged crescent shadow, eyes and mouth
    d.arc((x-int(87*scale), int(foot-330*scale), x+int(87*scale), int(foot-207*scale)), 8, 170, fill=(173, 130, 102), width=max(3,sw))
    eye_y = int(foot-296*scale)
    d.ellipse((x-int(41*scale), eye_y, x-int(27*scale), eye_y+int(15*scale)), fill=INK)
    d.ellipse((x+int(26*scale), eye_y, x+int(40*scale), eye_y+int(15*scale)), fill=INK)
    d.arc((x-int(24*scale), int(foot-282*scale), x+int(30*scale), int(foot-245*scale)), 5, 165, fill=INK, width=max(3,sw//2))
    if name:
        rounded(d, (x-int(116*scale), int(foot+4), x+int(116*scale), int(foot+44)), 10, (15,20,39), GOLD, 2)
        centered(d, (x, int(foot+24)), name, SMALL, CREAM)


def label_card(d, x, y, text, color=GOLD, w=280):
    rounded(d, (x-w//2, y-25, x+w//2, y+25), 10, (19, 24, 48), color, 3)
    centered(d, (x, y), text, SMALL, color)


def scene_art(d, scene, local, t):
    # All scenes are drawn from code using vector primitives, with gentle motion.
    if scene == 0:
        # Doorway + theatrical casket setup
        d.rectangle((72, 150, 280, 565), fill=(38, 42, 69), outline=INK, width=8)
        d.rectangle((98, 176, 254, 565), fill=(19, 24, 47), outline=(119, 119, 142), width=3)
        # Casket
        d.polygon([(340,455),(682,455),(742,520),(300,520)], fill=(103,57,44), outline=INK)
        d.polygon([(350,405),(675,405),(710,455),(320,455)], fill=(153,104,63), outline=INK)
        d.line((376,434,663,434), fill=GOLD, width=8)
        centered(d,(520,482),"MORTIMER",SMALL,CREAM)
        puppet(d, 160, 566, .72, suit=(54,62,91), name="THE VISITOR", pose="phone", t=t)
        puppet(d, 825, 567, .82, suit=(116,62,63), name="THE HOST", pose="point", t=t)
        puppet(d, 1040, 567, .78, suit=(62,94,102), name="THE HOST", pose="idle", t=t)
        label_card(d, 510, 345, "A CASH PICKUP", RED, 235)
    elif scene == 1:
        rounded(d,(350,170,928,490),24,(21,29,58),GOLD,6)
        centered(d,(640,228),"THE QUESTION",SMALL,GOLD)
        fit_text(d,"How does a refund become a box of cash?",(405,258,875,410),MARKER,CREAM,3)
        d.line((470,448,810,448),fill=RED,width=8)
        d.ellipse((608,432,672,496),fill=RED,outline=INK,width=4)
        centered(d,(640,464),"?",HAND,CREAM)
    elif scene == 2:
        # Scammer's pitch as a phone screen and split scene.
        rounded(d,(392,150,876,516),34,(32,42,74),CREAM,7)
        rounded(d,(420,184,848,476),24,(235,229,207),INK,4)
        centered(d,(634,226),"INCOMING CALL",SMALL,INK)
        d.ellipse((580,254,688,362),fill=(86,131,188),outline=INK,width=5)
        centered(d,(634,307),"?",HAND,CREAM)
        rounded(d,(463,390,805,447),14,RED,INK,4)
        centered(d,(634,419),"ACCOUNT ALERT",SMALL,CREAM)
        puppet(d,215,580,.72,suit=(56,81,116),name="THE TARGET",pose="phone",t=t)
        # dotted pressure lines
        for j in range(5):
            y=190+j*54
            d.line((300,y,380,y),fill=GOLD,width=3)
            d.polygon([(380,y),(365,y-8),(365,y+8)],fill=GOLD)
    elif scene == 3:
        # fake refund spreadsheet and the money that was never sent.
        rounded(d,(260,170,1012,490),22,(230,224,203),INK,8)
        d.rectangle((260,170,1012,222),fill=(61,76,117),outline=INK,width=5)
        centered(d,(638,196),"REFUND PROCESSING",SMALL,CREAM)
        centered(d,(435,277),"REFUND",SMALL,INK)
        centered(d,(822,277),"$ 3,000",MARKER,(42,112,76))
        d.line((330,305,940,305),fill=(145,139,120),width=3)
        centered(d,(435,354),"CORRECTION",SMALL,INK)
        centered(d,(822,354),"SEND IT BACK",LABEL,RED)
        rounded(d,(402,404,865,457),12,(255,241,202),RED,4)
        centered(d,(634,430),"THE REFUND WASN'T REAL",SMALL,RED)
        # red marker circle animates around the false amount
        extent=int(330*local)
        d.arc((714,245,940,385),start=205,end=205+extent,fill=RED,width=9)
    elif scene == 4:
        # parcel at retail pickup, ID and route to money network.
        d.polygon([(365,310),(660,270),(895,350),(590,405)],fill=(179,132,77),outline=INK)
        d.polygon([(365,310),(590,405),(590,558),(365,454)],fill=(131,88,57),outline=INK)
        d.polygon([(590,405),(895,350),(895,500),(590,558)],fill=(157,108,68),outline=INK)
        d.line((590,405,590,557),fill=CREAM,width=6)
        d.line((510,286,592,405,678,286),fill=GOLD,width=12)
        rounded(d,(448,438,553,495),8,CREAM,INK,3)
        centered(d,(500,466),"FAKE ID",SMALL,RED)
        puppet(d,1040,566,.78,suit=(68,76,109),name="THE PICKUP",pose="idle",t=t)
        # transfer route
        for j in range(5):
            x=190+j*175
            d.ellipse((x,190,x+16,206),fill=GOLD)
            if j<4: d.line((x+18,198,x+150,198),fill=GOLD,width=4)
        label_card(d,640,606,"CASH → COURIERS → CRYPTO",GOLD,440)
    elif scene == 5:
        # Original generic funeral sting tableau. No likenesses.
        d.rectangle((75,146,1205,564),fill=(25,29,52),outline=(70,79,114),width=6)
        d.rectangle((115,180,1165,564),fill=(36,38,61))
        d.polygon([(335,410),(676,410),(720,475),(290,475)],fill=(94,51,47),outline=INK)
        d.polygon([(346,365),(665,365),(694,410),(316,410)],fill=(143,94,61),outline=INK)
        d.line((375,388,642,388),fill=GOLD,width=7)
        puppet(d,220,565,.74,suit=(52,63,103),name="CHEN",pose="phone",t=t)
        puppet(d,840,565,.86,suit=(140,60,61),name="ASHTON",pose="point",t=t)
        puppet(d,1050,565,.82,suit=(57,105,106),name="ART",pose="idle",t=t)
        label_card(d,500,285,"THE FUNERAL WAS A SET",RED,330)
    elif scene == 6:
        # Investigative timeline and evidence folders.
        rounded(d,(210,176,1068,472),18,(231,224,205),INK,8)
        centered(d,(640,218),"EVIDENCE, NOT JUST A VIRAL CLIP",LABEL,INK)
        d.line((330,342,948,342),fill=INK,width=7)
        for i,(yr,cap) in enumerate([("2021","SCHEME BEGINS"),("2023","PICKUPS / VIDEO"),("2026","GUILTY PLEA"),("NOV 13","SENTENCED")]):
            x=350+i*195
            d.ellipse((x-13,328,x+13,354),fill=RED,outline=INK,width=3)
            centered(d,(x,290),yr,SMALL,INK)
            fit_text(d,cap,(x-81,373,x+81,431),SMALL,INK,2)
        for i in range(3):
            x=260+i*40
            d.rectangle((x,490,x+230,518),fill=(70,83,122),outline=INK,width=3)
            d.line((x+12,503,x+190,503),fill=CREAM,width=2)
    elif scene == 7:
        # Scale and sentence: numbers as in-world handwritten cards.
        rounded(d,(270,160,1010,493),25,(19,26,55),GOLD,6)
        centered(d,(640,215),"THE WIDER SCHEME",SMALL,CREAM)
        centered(d,(640,300),"$27 MILLION",MARKER,GOLD)
        centered(d,(640,356),"2,000+ VICTIMS",LABEL,CREAM)
        d.line((380,390,900,390),fill=RED,width=5)
        centered(d,(640,431),"CHEN: $9.5M+ ADMITTED LOSS",SMALL,CREAM)
        d.polygon([(940,500),(1090,452),(1130,470),(1065,524)],fill=(112,80,57),outline=INK)
        d.line((940,500,1108,560),fill=INK,width=18)
        label_card(d,640,576,"78 MONTHS  ·  6½ YEARS",RED,420)
    elif scene == 8:
        # Three practical steps, presented as a paper checklist.
        rounded(d,(330,145,950,535),22,(233,226,207),INK,8)
        centered(d,(640,194),"WHEN A CALL CREATES URGENCY",LABEL,INK)
        items=[("1","HANG UP"),("2","VERIFY INDEPENDENTLY"),("3","ASK SOMEONE YOU TRUST")]
        for i,(n,txt) in enumerate(items):
            y=266+i*82
            d.ellipse((390,y-22,434,y+22),fill=LIME,outline=INK,width=3)
            centered(d,(412,y),n,SMALL,INK)
            d.line((458,y,500,y),fill=RED,width=5)
            d.text((526,y),txt,font=LABEL,fill=INK,anchor="lm")
        d.line((500,503,778,503),fill=RED,width=int(3+4*local))
    else:
        # Quiet closing image.
        rounded(d,(300,160,980,494),20,(19,26,55),GOLD,6)
        centered(d,(640,228),"A VIRAL STING SHOWS A FACE.",LABEL,CREAM)
        centered(d,(640,300),"EVIDENCE REVEALS THE SYSTEM.",MARKER,GOLD)
        centered(d,(640,390),"STOP  ·  VERIFY  ·  ASK FOR HELP",SMALL,LIME)
        d.ellipse((586,450,694,558),outline=RED,width=8)
        centered(d,(640,504),"✓",HAND,LIME)


def make_base(scene, local, t):
    image = Image.new("RGB", (W,H), NAVY)
    d = ImageDraw.Draw(image)
    background(d,t,scene)
    # restrained frame-specific camera motion; drawing itself stays stable and legible.
    scene_art(d,scene,local,t)
    title=SCENE_NAMES[scene]
    d.rectangle((0,0,W,76),fill=(9,13,33))
    d.line((0,76,W,76),fill=GOLD,width=3)
    d.text((62,39),title,font=SMALL,fill=GOLD,anchor="lm")
    d.text((W-56,39),f"CASE FILE  /  {scene+1:02d}",font=SMALL,fill=CREAM,anchor="rm")
    # Slow, subtle zoom into each scene.
    zoom=1.0+0.022*local
    nw,nh=int(W*zoom),int(H*zoom)
    if (nw,nh)!=(W,H):
        image=image.resize((nw,nh),Image.Resampling.BICUBIC)
        ox=int((nw-W)/2); oy=int((nh-H)/2)
        image=image.crop((ox,oy,ox+W,oy+H))
    return image


def alloc_timeline():
    audios=[]
    durations=[]
    for p in AUDIO_PATHS:
        arr,sr=sf.read(p,dtype="float32")
        if arr.ndim>1: arr=arr.mean(axis=1)
        audios.append((arr,sr)); durations.append(len(arr)/sr)
    # timeline estimates paragraph timings within each TTS chunk based on spoken word counts.
    gap=0.38
    timeline=[]
    cursor=0.0
    for gi,(indices,(arr,sr),dur) in enumerate(zip(AUDIO_GROUPS,audios,durations)):
        if sr!=24000:
            raise ValueError(f"Expected 24 kHz speech, got {sr} in voice_{gi+1:02d}.wav")
        words=[len(PARAGRAPHS[i].split()) for i in indices]
        pause_budget=min(0.65*max(0,len(indices)-1),dur*0.08)
        speaking=max(0.01,dur-pause_budget)
        total=sum(words)
        for idx,nw in zip(indices,words):
            span=speaking*nw/total
            timeline.append((idx,cursor,cursor+span))
            cursor+=span
            # TTS emits paragraph pauses; model a small portion of them in the visual timing.
            if idx != indices[-1]: cursor+=pause_budget/max(1,len(indices)-1)
        cursor += gap if gi < len(AUDIO_GROUPS)-1 else 0
    return audios,timeline,cursor,gap


def make_underscore_music(length, sr=24000):
    """Create a subtle, original minor-key underscore with code (no borrowed audio)."""
    n = int(length * sr)
    music = np.zeros((n, 2), dtype=np.float32)
    sec = np.arange(n, dtype=np.float32) / sr
    beat = 60.0 / 84.0
    bar = beat * 4
    progression = [
        (146.83, 174.61, 220.00, 293.66),  # D minor
        (116.54, 174.61, 233.08, 293.66),  # B-flat
        (130.81, 174.61, 220.00, 261.63),  # F
        (130.81, 196.00, 261.63, 329.63),  # C
    ]
    chord_len = bar * 2
    total_chords = int(math.ceil(length / chord_len))
    for ci in range(total_chords):
        start = ci * chord_len
        end = min(length, start + chord_len)
        i0, i1 = int(start * sr), min(n, int(end * sr))
        if i1 <= i0:
            continue
        local = np.arange(i1-i0, dtype=np.float32) / sr
        env = np.minimum(1.0, local / 0.7) * np.minimum(1.0, (end-start-local) / 0.9)
        chord = progression[ci % len(progression)]
        pad = np.zeros(i1-i0, dtype=np.float32)
        for j, hz in enumerate(chord):
            phase = 2 * np.pi * hz * local
            pad += (np.sin(phase) + 0.18*np.sin(2*phase)) * (0.22 if j == 0 else 0.12)
        # Gentle high notes every other beat create forward motion without competing with speech.
        pattern = [293.66, 349.23, 392.00, 349.23, 261.63, 329.63, 392.00, 329.63]
        for beat_i in range(int(math.ceil((end-start)/beat))):
            if beat_i % 2 == 1:
                continue
            note_start = start + beat_i * beat + 0.08
            if note_start >= end:
                continue
            ni0 = int(note_start*sr)
            dur = min(0.5, end-note_start)
            ni1 = min(n, ni0+int(dur*sr))
            x = np.arange(ni1-ni0,dtype=np.float32)/sr
            e = np.exp(-x*5.2) * np.minimum(1.0,x/0.025)
            hz=pattern[(ci*4+beat_i//2)%len(pattern)]
            tone=(np.sin(2*np.pi*hz*x)+0.2*np.sin(2*np.pi*hz*2*x))*e*0.055
            music[ni0:ni1,0]+=tone*0.82
            music[ni0:ni1,1]+=tone*1.0
        music[i0:i1,0] += pad*env*0.04
        music[i0:i1,1] += pad*env*0.045
    # Fade music edges, and duck beneath speech using a 20 ms RMS envelope.
    ramp=min(int(sr*1.1),n//2)
    if ramp:
        fade=np.linspace(0,1,ramp,dtype=np.float32)
        music[:ramp]*=fade[:,None]
        music[-ramp:]*=fade[::-1,None]
    return music


def fmt_srt(seconds):
    ms=int(round(seconds*1000)); h=ms//3600000; ms%=3600000; m=ms//60000; ms%=60000; s=ms//1000; ms%=1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_subtitles(timeline):
    subs=[]
    for idx,start,end in timeline:
        words=PARAGRAPHS[idx].split()
        # 8–10 words per card for comfortable reading.
        groups=[words[i:i+9] for i in range(0,len(words),9)]
        weights=[len(g) for g in groups]; total=sum(weights)
        t=start
        for group,w in zip(groups,weights):
            e=t+(end-start)*w/total
            text=" ".join(group)
            # keep subtitles in at most two lines
            lines=textwrap.wrap(text,width=52)
            formatted="\n".join(lines[:2])
            subs.append((t,e,formatted))
            t=e
    path=ROOT/"fake_funeral_27m_scam.srt"
    with path.open("w") as f:
        for i,(s,e,txt) in enumerate(subs,1):
            f.write(f"{i}\n{fmt_srt(s)} --> {fmt_srt(e)}\n{txt}\n\n")
    return subs


def main():
    missing=[str(p) for p in AUDIO_PATHS if not p.exists()]
    if missing:
        raise SystemExit("Missing generated speech files: "+", ".join(missing))
    audios,timeline,total,gap=alloc_timeline()
    subs=build_subtitles(timeline)
    # Join the four voice parts with natural breaths.
    pieces=[]
    for i,(arr,sr) in enumerate(audios):
        pieces.append(arr)
        if i<len(audios)-1: pieces.append(np.zeros(int(gap*sr),dtype=np.float32))
    voice=np.concatenate(pieces)
    total=len(voice)/24000
    music=make_underscore_music(total)
    hop=480  # 20 ms at 24 kHz
    padded=np.pad(voice,(0,(-len(voice))%hop))
    rms=np.sqrt(np.mean(padded.reshape(-1,hop)**2,axis=1)+1e-10)
    duck=0.17+0.13*(1-np.clip(rms*5.0,0,1))
    duck=np.repeat(duck,hop)[:len(voice)]
    mix=np.column_stack((voice*0.88,voice*0.88))+music*duck[:,None]
    mix=np.tanh(mix*1.08)/np.tanh(1.08)
    voice_path=ROOT/"voiceover_combined.wav"
    sf.write(voice_path,mix.astype(np.float32),24000,subtype="PCM_16")
    out=ROOT/"fake_funeral_27m_scam.mp4"
    ffmpeg=os.environ.get("FFMPEG","ffmpeg")
    cmd=[ffmpeg,"-hide_banner","-loglevel","error","-y",
         "-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-",
         "-i",str(voice_path),"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","22","-pix_fmt","yuv420p",
         "-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart",str(out)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    scene_edges=[(a,b,i) for i,(idx,a,b) in enumerate(timeline)]
    # A paragraph is one visual chapter; all scenes use the same order as the narration.
    for frame in range(math.ceil(total*FPS)):
        t=frame/FPS
        idx=next((i for i,a,b in timeline if a<=t<b),len(PARAGRAPHS)-1)
        start,end=next((a,b) for i,a,b in timeline if i==idx)
        local=min(1,max(0,(t-start)/max(.001,end-start)))
        image=make_base(idx,local,t)
        d=ImageDraw.Draw(image,"RGBA")
        active=next((item for item in subs if item[0]<=t<item[1]),None)
        if active:
            _,_,caption=active
            rounded(d,(52,606,1228,690),16,(7,10,24,220),(242,193,78,255),2)
            lines=caption.split("\n")
            if len(lines)==1:
                centered(d,(640,648),lines[0],LABEL,CREAM)
            else:
                centered(d,(640,631),lines[0],SMALL,CREAM)
                centered(d,(640,660),lines[1],SMALL,CREAM)
        raw=image.tobytes()
        try:
            proc.stdin.write(raw)
        except BrokenPipeError:
            raise RuntimeError("FFmpeg stopped while encoding; check FFmpeg/libx264 setup")
        if frame % FPS == 0:
            print(f"Rendering {frame/FPS:6.1f}s / {total:6.1f}s",flush=True)
    proc.stdin.close()
    code=proc.wait()
    if code:
        raise SystemExit(f"FFmpeg exited with status {code}")
    print(f"Saved {out} ({out.stat().st_size/1_000_000:.1f} MB)")
    print(f"Duration: {total:.1f}s; subtitles: {ROOT/'fake_funeral_27m_scam.srt'}")

if __name__=="__main__":
    main()
