#!/usr/bin/env python3
"""Render the 24-shot documentary at 1080p/30 with Pillow art and FFmpeg."""
from __future__ import annotations
import functools, json, math, os, subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parent
W,H,FPS,SR=960,540,30,48000
OUT_W,OUT_H=1920,1080
INK='#18161B'; CREAM='#FFF6DC'; GOLD='#F2C14E'; RED='#C8242C'; LIME='#B8F04A'; NAVY='#10172F'
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REG='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

TIMES=[(0,9,'porch','porch'),(9,19,'funeral','funeral'),(19,27,'funeral','close_chen'),(27,35,'table','losses'),(35,38,'card','card1'),(38,49,'victim_home','victim'),(49,59,'boiler_room','caller'),(59,71,'table','refund'),(71,80,'victim_home','victim_close'),(80,83,'card','card2'),(83,94,'delivery_loading','parcel'),(94,104,'parcel_counter','id_pickup'),(104,115,'table','map'),(115,118,'card','card3'),(118,130,'funeral','sting'),(130,141,'evidence_room','evidence'),(141,152,'courthouse','courthouse'),(152,155,'card','card4'),(155,167,'courtroom','court'),(167,177,'table','ledger'),(177,188,'victim_home','hangup'),(188,197,'victim_home','help'),(197,205,'porch','polaroid'),(205,209,'card','end')]
SHOTS=[dict(i=i+1,start=a,end=b,set=s,kind=k,card=s=='card',whip_in=i in (0,2,5,7,10,12,14,16,18,20,22),whip_out=i in (1,3,6,8,11,13,15,17,19,21,23)) for i,(a,b,s,k) in enumerate(TIMES)]

CAST={
 'CHEN':dict(skin='#E5BD91',shade='#BD916B',suit='#293044',dark='#191E2B',shirt='#F6F0E5',tie='#A9252B',hair='#19171B',kind='slick'),
 'ASHTON':dict(skin='#EBC79C',shade='#C69569',suit='#22202A',dark='#131219',shirt='#F5EEDD',tie='#D1A54D',hair='#54351F',kind='slick',moustache=True),
 'ART':dict(skin='#E4B38A',shade='#B77D59',suit='#263A30',dark='#17251E',shirt='#F6F0E5',tie='#347253',hair='#56535A',kind='bald',glasses=True),
 'MARGARET':dict(skin='#F0D0B4',shade='#CDA88A',suit='#684B68',dark='#48324C',shirt='#FFF6DC',tie='#D0A548',hair='#D6D9E0',kind='bald',glasses=True),
 'CALLER':dict(skin='#DCAE84',shade='#B17B58',suit='#493526',dark='#302319',shirt='#E9DFC7',tie='#B8F04A',hair='#211C1C',kind='slick',moustache=True),
 'JUDGE':dict(skin='#D9A57E',shade='#AE7C59',suit='#201C20',dark='#111014',shirt='#FFFDF5',tie='#801D27',hair='#8B8C92',kind='bald',glasses=True)}

@functools.lru_cache(maxsize=128)
def font(sz,bold=True): return ImageFont.truetype(FONT if bold else FONT_REG,int(sz))
def rgb(h): return tuple(bytes.fromhex(h.lstrip('#')))
def ease(x): x=max(0,min(1,x));return .5-.5*math.cos(math.pi*x)
def back(x): x=max(0,min(1,x))-1;return 1+2.6*x**3+1.6*x**2
def text(d,xy,s,size=22,color=CREAM,anchor='mm',stroke=0,sw=INK,bold=True):
 d.text(xy,s,font=font(size,bold),fill=color,anchor=anchor,stroke_width=stroke,stroke_fill=sw)
def outlined_label(im,s,x,y,size=22,color=CREAM,angle=0):
 d=ImageDraw.Draw(im);f=font(size);bb=d.textbbox((0,0),s,font=f,stroke_width=2);w,h=bb[2]-bb[0]+28,bb[3]-bb[1]+24
 lay=Image.new('RGBA',(w,h),(0,0,0,0));ld=ImageDraw.Draw(lay);ld.text((w//2,h//2),s,font=f,fill=color,anchor='mm',stroke_width=3,stroke_fill=INK)
 if angle:lay=lay.rotate(angle,Image.Resampling.BICUBIC,expand=True)
 im.paste(lay,(int(x-lay.width/2),int(y-lay.height/2)),lay)
def box(d,xy,fill,outline=INK,width=4,r=8):d.rounded_rectangle(xy,radius=r,fill=fill,outline=outline,width=width)

def char(im,name,x,feet,scale=1,face=.35,t=0,emotion='calm',talk='closed',pose='idle',tag=None):
 q=CAST[name];d=ImageDraw.Draw(im);r=43*scale
 # ground contact and crossing stick-leg gait
 gait=math.sin(t*6.3)*(13*scale if pose=='walk' else 2*scale)
 d.ellipse((x-46*scale,feet-4*scale,x+46*scale,feet+6*scale),fill=(5,7,13))
 d.line((x-13*scale,feet-62*scale,x-13*scale+gait,feet),fill=INK,width=max(3,int(4*scale)))
 d.line((x+13*scale,feet-62*scale,x+13*scale-gait,feet),fill=INK,width=max(3,int(4*scale)))
 # body and crescent cel shadow
 top=feet-172*scale;bot=feet-58*scale;body=(x-39*scale,top,x+39*scale,bot)
 d.rounded_rectangle(body,radius=29*scale,fill=q['suit'],outline=INK,width=max(3,int(4*scale)))
 d.polygon([(x-22*scale,top+4*scale),(x,top+55*scale),(x+22*scale,top+4*scale)],fill=q['shirt'],outline=INK)
 d.polygon([(x-8*scale,top+5*scale),(x+8*scale,top+5*scale),(x+10*scale,top+53*scale),(x,top+65*scale),(x-10*scale,top+53*scale)],fill=q['tie'],outline=INK)
 # arms; snap from resting to gesture with a back-eased pose
 lift=14*scale*ease(min(1,t/1.2))
 for side in (-1,1):
  sx=x+side*31*scale;sy=top+28*scale
  if emotion in ('present','talk','surprised'):
   ex=x+side*62*scale;ey=top-2*scale-lift
  elif emotion in ('phone','comfort') and side==1:
   ex=x+side*25*scale;ey=top-28*scale
  else:ex=x+side*43*scale;ey=top+54*scale
  d.line((sx,sy,ex,ey),fill=INK,width=max(3,int(4*scale)))
  if emotion in ('present','talk','surprised') or (emotion in ('phone','comfort') and side==1):
   d.ellipse((ex-6*scale,ey-6*scale,ex+6*scale,ey+6*scale),fill=q['skin'],outline=INK,width=2)
 # head floating directly above pill body
 cx=x+face*5*scale;cy=feet-224*scale;r=43*scale;head=(cx-r,cy-r,cx+r,cy+r)
 d.ellipse(head,fill=q['skin'],outline=INK,width=max(3,int(4*scale)))
 # shifted cutout gives a hard edged lower crescent shadow
 mask=Image.new('L',(int(2*r),int(2*r)),0);md=ImageDraw.Draw(mask);md.ellipse((0,0,2*r-1,2*r-1),fill=255);md.ellipse((8*scale,-14*scale,2*r+8*scale,2*r-14*scale),fill=0)
 shade=Image.new('RGBA',mask.size,rgb(q['shade'])+(255,));im.paste(shade,(int(cx-r),int(cy-r)),mask);d=ImageDraw.Draw(im);d.ellipse(head,outline=INK,width=max(3,int(4*scale)))
 # hair and pale rim
 if q['kind']=='slick':d.pieslice((cx-r,cy-r-2,cx+r,cy+r*.2),180,355,fill=q['hair'],outline=INK,width=2)
 else:
  for sx in (-1,1):
   bb=(cx-r*.96,cy-r*.25,cx-r*.40,cy+r*.46) if sx<0 else (cx+r*.40,cy-r*.25,cx+r*.96,cy+r*.46)
   d.arc(bb,80,275,fill=q['hair'],width=max(2,int(4*scale)))
 d.arc((cx-r+2,cy-r+2,cx+r-2,cy+r-2),205,326,fill='#FFE6B0',width=max(2,int(3*scale)))
 fx=face*12*scale;ey=cy-5*scale
 for ex0 in (-13,13):
  ex=cx+ex0*scale+fx;far=ex0*face<0;er=(3.3 if far else 4.2)*scale
  blink=(t%2.7)<.10
  if blink:d.line((ex-er,ey,ex+er,ey),fill=INK,width=max(2,int(2*scale)))
  elif emotion=='surprised':
   d.ellipse((ex-er*1.4,ey-er*1.5,ex+er*1.4,ey+er*1.5),fill=CREAM,outline=INK,width=1);d.ellipse((ex-1.3,ey-1.3,ex+1.3,ey+1.3),fill=INK)
  else:d.ellipse((ex-2.7*scale,ey-2.7*scale,ex+2.7*scale,ey+2.7*scale),fill=INK)
 # brow, mouth and character-specific facial notes
 by=ey-10*scale;d.line((cx+fx-21*scale,by,cx+fx-9*scale,by-2*scale),fill=INK,width=2);d.line((cx+fx+9*scale,by-2*scale,cx+fx+21*scale,by),fill=INK,width=2)
 mx=cx+fx;my=cy+14*scale
 if talk=='open':d.ellipse((mx-5*scale,my-6*scale,mx+5*scale,my+6*scale),fill='#361922',outline=INK,width=1)
 elif emotion=='smile':d.arc((mx-8*scale,my-5*scale,mx+8*scale,my+8*scale),10,170,fill=INK,width=max(2,int(2*scale)))
 elif emotion=='surprised':d.ellipse((mx-4*scale,my-5*scale,mx+4*scale,my+6*scale),fill='#351923',outline=INK,width=1)
 else:d.line((mx-5*scale,my,mx+5*scale,my),fill=INK,width=2)
 if q.get('moustache'):
  d.arc((mx-10*scale,my-5*scale,mx+1*scale,my+4*scale),190,350,fill=q['hair'],width=max(2,int(3*scale)));d.arc((mx,my-5*scale,mx+10*scale,my+4*scale),190,350,fill=q['hair'],width=max(2,int(3*scale)))
 if q.get('glasses'):
  for ex0 in (-13,13):d.ellipse((cx+(ex0-8)*scale+fx,ey-7*scale,cx+(ex0+8)*scale+fx,ey+7*scale),outline=INK,width=2)
  d.line((cx-5*scale+fx,ey,cx+5*scale+fx,ey),fill=INK,width=2)
 if emotion=='surprised':
  sx=cx+31*scale;sy=cy-25*scale;d.polygon([(sx,sy-6*scale),(sx-4*scale,sy+2*scale),(sx,sy+7*scale),(sx+4*scale,sy+2*scale)],fill='#8FC8EE',outline=INK)
 if tag:
  box(d,(x-45*scale,feet+2,x+45*scale,feet+20), '#C5AD84',INK,2,2);text(d,(x,feet+11),tag,9*scale,INK)

@functools.lru_cache(maxsize=8)
def set_base(kind):
 im=Image.new('RGB',(W,H),(14,20,39));d=ImageDraw.Draw(im)
 if kind=='porch':
  for y in range(H):
   c=(13+int(y*.025),21+int(y*.035),46+int(y*.08));d.line((0,y,W,y),fill=c)
  for i in range(30):
   x=(i*73+31)%W;y=(i*47+21)%210;r=1+i%2;d.ellipse((x-r,y-r,x+r,y+r),fill=(154,165,195))
  d.ellipse((94,53,155,114),fill='#DDDCCB');d.ellipse((111,39,171,101),fill='#18213E')
  d.polygon([(0,255),(110,174),(205,242),(325,163),(465,240),(625,150),(960,245),(960,420),(0,420)],fill='#18213A')
  d.rectangle((168,182,765,372),fill='#50484A',outline=INK,width=7);d.polygon([(130,187),(464,77),(813,187)],fill='#39333C',outline=INK)
  for x in (223,604):d.rectangle((x,216,x+94,311),fill='#22314C',outline=INK,width=4);d.line((x+47,218,x+47,309),fill='#B78A50',width=2)
  d.rectangle((394,174,521,371),fill='#2B2730',outline=INK,width=6);d.ellipse((497,271,505,279),fill=GOLD)
  d.rectangle((142,359,798,392),fill='#735741',outline=INK,width=5);d.rectangle((0,403,W,H),fill='#1A1920')
  for j in range(8):d.line((150+j*95,420,106+j*112,537),fill='#494048',width=2)
  # visible porch sconce
  d.rectangle((707,187,731,230),fill='#F5D389',outline=INK,width=3)
 elif kind=='funeral':
  d.rectangle((0,0,W,H),fill='#292434');d.rectangle((0,40,W,425),fill='#393443')
  d.rectangle((0,45,145,440),fill='#54202F');d.rectangle((815,45,W,440),fill='#54202F')
  for x in range(4,144,20):d.line((x,46,x+15,438),fill='#742B3A',width=5)
  for x in range(823,960,20):d.line((x,46,x-14,438),fill='#742B3A',width=5)
  for x in range(150,815,85):d.rectangle((x,138,x+66,380),fill='#333B4F',outline='#211F2C',width=4)
  d.rectangle((0,425,W,H),fill='#24212A');d.rectangle((254,332,706,426),fill='#5A342F',outline=INK,width=6)
  d.polygon([(267,281),(684,281),(725,337),(235,337)],fill='#835332',outline=INK);d.polygon([(300,236),(653,236),(684,282),(267,282)],fill='#A06B43',outline=INK)
  d.rectangle((410,249,551,271),fill='#6C4233',outline=GOLD,width=2);text(d,(480,260),'MORTIMER',11,CREAM)
  for cx in (188,774):
   d.ellipse((cx-43,212,cx+43,298),outline='#6A553A',width=8)
   for j in range(10):
    a=j*math.tau/10;px=cx+int(32*math.cos(a));py=255+int(32*math.sin(a));d.ellipse((px-10,py-10,px+10,py+10),fill=RED if j%2 else '#E4D4B4',outline=INK,width=2)
  d.ellipse((437,33,523,60),fill='#D6B465',outline=INK,width=3)
 elif kind=='victim_home':
  d.rectangle((0,0,W,H),fill='#3A594D')
  for x in range(0,W,54):d.line((x,30,x,430),fill='#345045',width=2)
  for y in range(50,430,48):d.line((0,y,W,y),fill='#345045',width=2)
  d.rectangle((662,54,889,226),fill='#17233D',outline=INK,width=6);d.line((775,56,775,224),fill='#87704C',width=3);d.line((664,140,887,140),fill='#87704C',width=3)
  d.rectangle((76,73,257,192),fill='#795B43',outline=INK,width=6);d.rectangle((88,85,245,180),fill='#48635C')
  for x,y in ((125,123),(204,120)):
   d.ellipse((x-17,y-17,x+17,y+17),fill='#E1BD9A');d.rounded_rectangle((x-19,y+8,x+19,y+47),radius=12,fill='#7B6276')
  d.ellipse((355,49,425,119),fill='#E0D5B4',outline=INK,width=5);d.line((390,55,390,83),fill=INK,width=3);d.line((390,83,409,99),fill=INK,width=3)
  d.rectangle((64,323,628,430),fill='#5C3F2F',outline=INK,width=6);d.rectangle((242,211,517,335),fill='#282F39',outline=INK,width=6);d.rectangle((258,226,501,310),fill='#172D3A')
  # desk lamp, phone and rug
  d.line((125,322,165,260,222,260),fill=INK,width=9);d.polygon([(187,245),(256,245),(236,214),(204,214)],fill='#D8A955',outline=INK)
  d.rectangle((115,288,151,324),fill='#171718',outline=INK,width=3);d.arc((106,271,160,301),185,355,fill=INK,width=5)
  d.rectangle((0,440,W,H),fill='#302923')
 elif kind=='boiler_room':
  d.rectangle((0,0,W,H),fill='#101728');d.rectangle((0,431,W,H),fill='#0D1320')
  for row in range(2):
   for col in range(4):
    x=35+col*227;y=65+row*178;d.rectangle((x,y,x+184,y+120),fill='#1D2635',outline=INK,width=5);d.rectangle((x+8,y+8,x+176,y+94),fill='#152C3C',outline='#486178',width=2)
    for j in range(3):d.line((x+20,y+26+j*20,x+148-(j%2)*22,y+26+j*20),fill='#547F89',width=2)
    d.rectangle((x+68,y+120,x+116,y+135),fill='#45464A',outline=INK,width=2)
  d.rectangle((42,25,253,57),fill='#342D29',outline=INK,width=3);text(d,(147,41),'CALL LOG',17,CREAM)
  d.rectangle((725,28,920,57),fill='#372524',outline=INK,width=3);text(d,(820,42),'03:00 AM',15,RED)
 elif kind=='table':
  d.rectangle((0,0,W,H),fill='#E7DDC6')
  for i in range(440):
   x=(i*197+13)%W;y=(i*113+9)%H;d.point((x,y),fill=(202+i%24,193+i%18,171+i%15))
  d.rectangle((0,0,40,H),fill='#553B30');d.rectangle((W-40,0,W,H),fill='#553B30');d.rectangle((0,0,W,28),fill='#553B30');d.rectangle((0,H-28,W,H),fill='#553B30')
  d.rectangle((48,39,912,501),outline='#39734C',width=12)
 elif kind=='parcel_counter':
  d.rectangle((0,0,W,H),fill='#343F48');d.rectangle((0,40,W,400),fill='#42494B');d.rectangle((70,57,890,124),fill='#21404A',outline=INK,width=6);text(d,(480,90),'EXPRESS PARCEL PICKUP',20,CREAM)
  for x in (93,356,619):
   d.rectangle((x,161,x+228,353),fill='#222D37',outline=INK,width=6)
   for j in range(3):d.rectangle((x+20+j*65,180,x+75+j*65,260),fill='#455D6C',outline='#9C9681',width=2)
  d.rectangle((0,400,W,478),fill='#624631',outline=INK,width=6)
 elif kind=='courthouse':
  d.rectangle((0,0,W,H),fill='#0C1735')
  for i in range(35):
   x=(i*51+7)%W;y=(i*31+5)%230;d.ellipse((x,y,x+2,y+2),fill='#9BAAC8')
  d.ellipse((792,43,862,113),fill='#D6D7C7');d.polygon([(0,365),(240,288),(456,367),(740,286),(960,360),(960,540),(0,540)],fill='#172645')
  d.rectangle((140,208,822,442),fill='#76614E',outline=INK,width=7);d.polygon([(101,226),(481,94),(861,226)],fill='#9B8062',outline=INK,width=6)
  for x in range(188,801,104):d.rectangle((x,240,x+45,410),fill='#D4C4A5',outline=INK,width=4)
  for j in range(4):d.rectangle((90-j*12,441+j*23,870+j*12,460+j*23),fill='#684F43',outline=INK,width=3)
 elif kind=='courtroom':
  d.rectangle((0,0,W,H),fill='#392D31');d.rectangle((0,402,W,H),fill='#2E2329')
  for x in (48,220,739,912):
   d.rectangle((x,40,x+75,330),fill='#906A50',outline=INK,width=5);d.polygon([(x-17,55),(x+37,19),(x+92,55)],fill='#A27B5C',outline=INK,width=4)
  d.rectangle((287,237,673,367),fill='#67413B',outline=INK,width=7);d.rectangle((255,356,705,420),fill='#815543',outline=INK,width=6)
  d.ellipse((426,56,534,164),fill='#59433B',outline=GOLD,width=5);text(d,(480,110),'UNITED STATES',9,CREAM)
  d.line((480,157,480,207),fill=GOLD,width=4);d.line((411,169,549,169),fill=GOLD,width=4);d.arc((390,164,438,198),0,180,fill=GOLD,width=3);d.arc((522,164,570,198),0,180,fill=GOLD,width=3)
 elif kind=='delivery_loading':
  d.rectangle((0,0,W,H),fill='#27323A');d.rectangle((0,42,W,400),fill='#3B474B')
  for x in range(34,960,155):
   d.line((x,42,x,398),fill='#2A3538',width=6);d.line((x+6,50,x+6,396),fill='#596367',width=2)
  d.rectangle((120,90,820,322),fill='#1B252B',outline=INK,width=7);d.rectangle((140,106,800,300),fill='#172A35',outline='#6B7774',width=4)
  for x in range(168,780,84):d.line((x,109,x,298),fill='#273D46',width=2)
  d.rectangle((0,391,W,450),fill='#66472F',outline=INK,width=6)
  for x in (55,332,608,816):
   d.rectangle((x,282,x+130,385),fill='#845B3B',outline=INK,width=5);d.line((x+8,302,x+122,302),fill='#BF9566',width=3);d.line((x+66,284,x+66,383),fill='#493322',width=3)
  d.rectangle((680,62,904,126),fill='#263E44',outline=INK,width=4);text(d,(792,94),'NIGHT DISPATCH',16,CREAM)
 elif kind=='evidence_room':
  d.rectangle((0,0,W,H),fill='#3D4747');d.rectangle((0,390,W,H),fill='#3A2D25')
  for x in range(32,960,92):d.line((x,0,x,393),fill='#35403F',width=2)
  # three corkboards with maps, photographs and typed filings
  for x in (58,354,650):
   d.rectangle((x,62,x+250,342),fill='#76563C',outline=INK,width=7);d.rectangle((x+10,73,x+240,332),fill='#B49A70')
   for j in range(6):d.line((x+22,105+j*32,x+223-(j%2)*25,105+j*32),fill='#75644D',width=2)
   d.rectangle((x+23,88,x+108,144),fill='#EEE3CE',outline=INK,width=2);d.rectangle((x+128,175,x+220,242),fill='#D9CEB9',outline=INK,width=2)
   d.line((x+95,146,x+139,179),fill=RED,width=3);d.line((x+145,237,x+196,152),fill=RED,width=3)
  d.rectangle((0,392,W,452),fill='#6F4B32',outline=INK,width=5)
  for x in (150,470,790):d.rectangle((x,451,x+44,540),fill='#463021',outline=INK,width=3)
 return im

# Practical pools, additive amber/cyan glows and restrained vignette.
RIGS={'porch':[(720,145,95,'#FFD98A',.24),(570,300,90,'#FFE6B0',.10)],'funeral':[(480,105,115,'#FFD98A',.20),(230,285,90,'#FFE6B0',.10),(790,280,90,'#FFE6B0',.10)],'victim_home':[(320,250,120,'#FFD98A',.13),(760,160,105,'#8FC8EE',.12)],'boiler_room':[(180,180,100,'#8FC8EE',.11),(480,180,100,'#8FC8EE',.11),(790,180,100,'#C8242C',.08)],'table':[(480,175,220,'#FFD98A',.16)],'parcel_counter':[(220,160,120,'#FFD98A',.11),(740,150,120,'#8FC8EE',.12)],'courthouse':[(480,180,170,'#FFD98A',.11)],'courtroom':[(480,160,150,'#FFF0C0',.15)],'delivery_loading':[(230,100,120,'#FFD98A',.13),(800,130,140,'#8FC8EE',.12)],'evidence_room':[(480,90,170,'#FFF0C0',.12),(830,330,110,'#C8242C',.06)]}

def lit(im,scene):
 # Darkness wash; practical glows are built in RGBA then correctly composited on black.
 night=Image.new('RGB',(W,H),(27,39,78));im=Image.blend(im,ImageChops.multiply(im,night),.48)
 layer=Image.new('RGBA',(W,H),(0,0,0,0));ld=ImageDraw.Draw(layer)
 for x,y,r,c,a in RIGS.get(scene,[]):
  for k in range(12,0,-1):
   rr=int(r*k/12);aa=int(255*a*(1-k/12)**1.3)
   if aa>0:ld.ellipse((x-rr,y-rr,x+rr,y+rr),fill=rgb(c)+(aa,))
 layer=layer.filter(ImageFilter.GaussianBlur(18));black=Image.new('RGB',(W,H),(0,0,0));black.paste(layer,(0,0),layer.getchannel('A'));im=ImageChops.screen(im,black)
 im=ImageEnhance.Contrast(im).enhance(1.06)
 yy,xx=np.mgrid[0:H,0:W];rad=np.sqrt(((xx-W/2)/(W*.75))**2+((yy-H/2)/(H*.8))**2);m=np.uint8(np.clip(255*(1-.42*np.clip((rad-.45)/.8,0,1)),0,255));mask=Image.fromarray(m,'L')
 return ImageChops.multiply(im,Image.merge('RGB',(mask,mask,mask)))

def draw_props(im,shot,local):
 d=ImageDraw.Draw(im);n=shot['i'];k=shot['kind']
 if k in ('porch','polaroid'):
  if k=='porch':
   box(d,(55,406,303,497),'#754F35',INK,4,3);text(d,(179,432),'THE $27 MILLION',18,CREAM);text(d,(179,461),'FAKE FUNERAL STING',16,CREAM)
   if n==1:text(d,(790,130),'LOS ANGELES - 2023',16,CREAM,stroke=2)
  if k=='polaroid':
   # Polaroid photo is a physical object, not a full-frame text treatment.
   d.rectangle((244,77,715,458),fill='#F5EEDD',outline=INK,width=5);d.rectangle((264,96,695,391),fill='#19233B',outline=INK,width=3)
   for x,col in ((377,'#293044'),(570,'#702C34')):
    d.ellipse((x-35,159,x+35,229),fill='#E6BE94',outline=INK,width=4);d.rounded_rectangle((x-29,225,x+29,358),radius=20,fill=col,outline=INK,width=4)
   text(d,(480,423),'78 MONTHS - CASE CLOSED',18,INK)
   d.arc((406,130,614,337),195,345,fill=RED,width=6)
 elif k=='funeral':
  d.polygon([(316,406),(360,393),(393,407),(350,421)],fill='#A7794C',outline=INK)
  d.polygon([(316,406),(350,421),(350,456),(316,444)],fill='#805337',outline=INK)
  d.polygon([(350,421),(393,407),(393,444),(350,456)],fill='#9C6844',outline=INK)
  text(d,(351,434),'CASH',10,CREAM)
 elif k in ('close_chen','id_pickup'):
  if k=='close_chen':pass
  else:
   box(d,(558,346,871,485),'#DDD6C3',INK,4,6);text(d,(715,369),'DRIVER LICENSE',16,INK);d.ellipse((582,383,642,443),fill='#BD916B',outline=INK,width=3);text(d,(747,449),'FALSE ID',19,RED)
 elif k=='losses':
  d.polygon([(96,120),(463,115),(472,315),(100,322)],fill='#F3E8D0',outline=INK);text(d,(281,149),'LOSS REGISTER',21,INK)
  for j in range(4):d.line((130,185+j*28,432,185+j*28),fill='#A59A83',width=2)
  for j in range(6):
   x=106+j*123;y=395+(j%2)*13;d.rounded_rectangle((x,y,x+93,y+34),radius=5,fill='#47684A',outline=INK,width=3)
  outlined_label(im,'$27M+',662,202,40,LIME,0);outlined_label(im,'2,000+ OLDER VICTIMS',660,258,20,CREAM,0)
 elif k=='refund':
  d.polygon([(105,94),(853,96),(827,398),(126,407)],fill='#F0E6D0',outline=INK);text(d,(478,141),'BANK REFUND LEDGER',24,INK)
  for j in range(4):d.line((208,192+j*46,763,192+j*46),fill='#B5A98F',width=2)
  text(d,(290,226),'ORIGINAL: $30.00',18,INK);text(d,(685,226),'REFUND: $3,000',22,RED)
  d.ellipse((594,197,783,266),outline=RED,width=5);outlined_label(im,'FAKE OVERPAYMENT',657,329,24,RED,-4)
 elif k=='victim':
  # The alert stays inside the physical CRT glass.
  text(d,(380,267),'SECURITY ALERT',15,RED,stroke=1);text(d,(380,292),'CALL SUPPORT NOW',13,CREAM,stroke=1)
  # animated caller tag is added by the per-frame renderer
 elif k=='caller':
  outlined_label(im,'SCRIPT',169,107,22,CREAM);outlined_label(im,'TRUST',811,107,22,CREAM)
 elif k=='parcel':
  d.rounded_rectangle((316,170,654,382),radius=9,fill='#A7794C',outline=INK,width=5);text(d,(480,253),'CASH PACKAGE',22,CREAM);text(d,(480,290),'TO: FALSE NAME',17,INK)
  d.rectangle((275,118,696,163),fill='#EEE5D2',outline=INK,width=3);text(d,(486,141),'EXPRESS STORE PICKUP',16,INK)
 elif k=='map':
  d.polygon([(118,212),(230,141),(346,183),(487,125),(660,168),(826,141),(866,234),(775,310),(615,277),(468,338),(325,292),(206,330)],fill='#C7B792',outline=INK)
  pts=[(208,276),(342,245),(510,208),(734,192)];d.line(pts,fill=RED,width=5)
  for x,y,label in ((208,276,'LOS ANGELES'),(342,245,'UPLAND'),(510,208,'NEVADA'),(734,192,'OVERSEAS')):
   d.ellipse((x-7,y-7,x+7,y+7),fill=RED,outline=INK,width=2);text(d,(x,y+17),label,10,INK)
  outlined_label(im,'CASH TO CRYPTO',480,425,24,RED)
 elif k=='sting':
  d.rectangle((125,83,834,118),fill=(15,13,15,0));outlined_label(im,'DRAMATIZED RECONSTRUCTION',480,98,16,CREAM)
  d.ellipse((102,224,202,324),outline=RED,width=5);text(d,(146,366),'JULY 2023 PICKUP',16,CREAM)
 elif k=='evidence':
  for j,(x,title) in enumerate(((93,'PICKUP LOGS'),(343,'VIDEO STILLS'),(595,'COURT FILINGS'))):
   d.polygon([(x,94),(x+224,103),(x+212,391),(x-6,383)],fill='#EEE3CE',outline=INK);text(d,(x+108,133),title,17,INK)
   for z in range(5):d.line((x+21,178+z*32,x+193-(z%2)*24,178+z*32),fill='#A4977E',width=2)
  # The animated DOJ stamp is added by the frame renderer.
 elif k=='courthouse':
  # The animated court-record stamp is added by the frame renderer.
  pass
 elif k=='court':
  # Sentence stamp arrives on the gavel strike in the frame renderer.
  pass
 elif k=='ledger':
  d.polygon([(110,82),(852,91),(827,423),(121,416)],fill='#F3E8D0',outline=INK);text(d,(480,127),'SENTENCING DOSSIER',22,INK)
  for j,(a,b) in enumerate((('WIDER SCHEME','$27M+'),('CHEN ROLE','$9.5M+'))):
   y=215+j*83;d.line((208,y+26,758,y+26),fill='#A79A7F',width=2);text(d,(304,y),a,20,INK);text(d,(670,y),b,28,RED)
  # Animated sentence stamp is placed on the dossier during the shot.
 elif k=='hangup':
  d.arc((107,280,183,348),190,350,fill=INK,width=7);text(d,(728,400),'HANG UP - VERIFY',18,INK)
 elif k=='help':
  box(d,(558,352,878,419),'#EEE5D2',INK,3,4);text(d,(718,384),'OFFICIAL NUMBER ON YOUR CARD',12,INK)
 elif k.startswith('card') or k=='card':
  im.paste((0,0,0),(0,0,W,H));d=ImageDraw.Draw(im)
  title={5:'CHAPTER ONE - THE BAIT',10:'CHAPTER TWO - THE CASH BOX',14:'CHAPTER THREE - THE STING',18:'CHAPTER FOUR - THE RECKONING'}[n]
  if local<1:
   count=max(1,int(len(title)*min(1,local*1.7)));title=title[:count]
  text(d,(480,281),title,34 if n==14 else 43,CREAM)
  return im
 elif k=='end':
  im.paste((0,0,0),(0,0,W,H));text(ImageDraw.Draw(im),(480,280),'PAUSE FIRST. VERIFY ALWAYS.',32,CREAM);return im
 return im

def scene_art(sh,local,t,mouths):
 im=Image.new('RGB',(W,H),(0,0,0)) if sh['card'] else set_base(sh['set']).copy();k=sh['kind'];n=sh['i']
 # Actor staging, camera composition and emotional blocking.
 def say(who):return mouths.get(who,'closed')
 if k=='porch':
  char(im,'CHEN',274+int(170*ease(local)),500,.80,-.55,t,'surprised' if local>.75 else 'calm',pose='walk')
 elif k=='funeral':
  if n==2:
   char(im,'CHEN',225,507,.72,-.58,t,'surprised',say('MULE'))
   char(im,'ASHTON',626,507,.78,.55,t,'calm',say('HOST1'),'idle')
   char(im,'ART',767,507,.71,-.45,t,'calm')
  else:
   char(im,'CHEN',166,508,.76,-.55,t,'surprised',say('MULE'))
   char(im,'ASHTON',615,508,.78,.55,t,'calm',say('HOST1'))
   char(im,'ART',778,508,.72,-.40,t,'calm')
 elif k=='close_chen':char(im,'CHEN',480,728,1.7,-.6,t,'surprised',say('MULE'))
 elif k in ('losses','refund','parcel','map','evidence','ledger'):
  # table hands/sleeves act on practical documents
  d=ImageDraw.Draw(im)
  yy=478-int(12*math.sin(t*2));d.line((56,533,295,yy),fill='#3F5069',width=30);d.ellipse((279,yy-12,303,yy+12),fill='#E5B990',outline=INK,width=3)
  if k=='parcel':d.line((900,528,670,377),fill='#6B473A',width=28);d.ellipse((657,365,681,389),fill='#E5B990',outline=INK,width=3)
 elif k=='victim':
  char(im,'MARGARET',220,508,.88,.45,t,'phone',say('VICT'))
 elif k=='caller':char(im,'CALLER',480,524,.94,-.45,t,'talk',say('CALL'))
 elif k=='victim_close':char(im,'MARGARET',480,730,1.75,.56,t,'surprised',say('VICT'))
 elif k=='id_pickup':
  char(im,'CHEN',376,525,.95,.56,t,'calm')
 elif k=='sting':
  char(im,'CHEN',194,506,.76,-.60,t,'surprised',say('MULE'),pose='walk')
  char(im,'ASHTON',626,507,.79,.55,t,'calm',say('HOST1'))
  char(im,'ART',781,507,.70,-.45,t,'calm')
 elif k=='courthouse':char(im,'CHEN',480,526,.66,-.50,t,'calm',pose='walk')
 elif k=='court':
  char(im,'JUDGE',483,360,.75,-.35,t,'calm',say('JUDG'))
  char(im,'CHEN',773,512,.77,.56,t,'surprised')
 elif k=='hangup':char(im,'MARGARET',242,507,.86,.55,t,'calm')
 elif k=='help':
  char(im,'MARGARET',298,507,.88,.55,t,'smile')
  char(im,'ART',744,507,.73,-.35,t,'smile')
 elif k=='polaroid':
  char(im,'CHEN',347,462,.49,-.5,t,'surprised');char(im,'ASHTON',608,462,.49,.5,t,'calm')
 im=draw_props(im,sh,local)
 if not sh['card']:im=lit(im,sh['set'])
 return im

# Ensure speaking mouth shapes follow actual synthesized energy with a 3-frame hold.
def mouth_track(x):
 hop=SR//FPS;rms=[]
 for i in range(0,len(x),hop):rms.append(float(np.sqrt(np.mean(x[i:min(i+hop,len(x))]**2)+1e-12)))
 peak=max(rms) if rms else 0;cur='closed';hold=0;out=[]
 for r in rms:
  target='open' if r>peak*.42 else 'mid' if r>peak*.14 else 'closed'
  if target!=cur and hold>=3:cur=target;hold=0
  hold+=1;out.append(cur)
 return out

NARR_LINES={
 'narr_a':[(1,"Los Angeles, July 2023. A man arrives for a cash pickup at a funeral. The casket is part of a set. The dead man is a prop."),(2,"The collector doesn't know he has walked into a sting. The visitors are Ashton Bingham and Art Kulik, from Trilogy Media. They ask one question: who sent you?"),(3,"The clip went viral. But one confrontation is only a glimpse of a wider fraud case."),(4,"Investigators described thousands of older victims, fake refund stories, cash pickups and money moved overseas. Across the wider scheme, losses topped twenty-seven million dollars."),(6,"This film separates that total from the losses Jiandong Chen admitted during his own role. First, the bait. Some victims saw a computer alert, received a call, or were told a bank refund had gone wrong."),(7,"The caller sounded helpful. The pressure came next.")],
 'narr_b1':[(11,"Scammers sometimes used remote access and invented an overpayment. Victims were told to send their own money back, by wire or in bulk cash."),(12,"Many were directed to mail cash to a retail address under a fictitious name. Chen admitted using false identification to retrieve packages."),(13,"Prosecutors also described cryptocurrency transfers to overseas co-conspirators, and trips to collect packages in places including Nevada."),(15,"The fake funeral pickup was not the whole case."),(16,"Other videos, records and testimony showed a broader pattern."),(17,"The investigation continued beyond that viral moment, with pickups traced through December twenty twenty-three, including an attempted collection in Upland.")],
 'narr_b2':[(18,"Chen pleaded guilty in April 2026."),(19,"On November thirteenth, he was sentenced to seventy-eight months in federal prison."),(20,"He admitted losses during his role exceeded nine and a half million dollars. That is not the same figure as the wider scheme's losses, which exceeded twenty-seven million."),(21,"Scams like these also take trust, dignity and peace of mind. If a caller creates urgency around money, pause. Hang up, then find the organization's official number yourself."),(22,"Never mail cash to fix a computer or return a surprise refund. Don't grant remote access to an unexpected caller. Before sending a large payment, talk with someone you trust."),(23,"The sting put one collector on camera. The court record showed a wider system."),(24,"Pause first. Verify always.")]}
MANIFEST=[('narr_a','cinema_narr_a.wav','NARR',NARR_LINES['narr_a']),('narr_b1','cinema_narr_b1.wav','NARR',NARR_LINES['narr_b1']),('narr_b2','cinema_narr_b2.wav','NARR',NARR_LINES['narr_b2']),('caller','cinema_caller.wav','CALL',[(7,"Ma'am, I can help you check that charge. I'll guide you through a refund."),(8,'The screen shows too much. Please send the extra back.')]),('victim','cinema_victim.wav','VICT',[(8,'I thought it was real. What do I do?')]),('host','cinema_host.wav','HOST1',[(15,'Come in. Meet Uncle Mortimer. Who sent you for this cash?')]),('mule','cinema_mule.wav','MULE',[(15,"I'm here to collect a package. I was told to pick it up.")]),('judge','cinema_judge.wav','JUDG',[(19,'The harm goes beyond money. It touches trust, dignity, and peace of mind.')])]
OFFSETS={('CALL',7):4.05,('CALL',8):3.30,('VICT',8):7.20,('HOST1',15):4.50,('MULE',15):9.00,('JUDG',19):5.15}

def build_voice_events():
 events=[];activity=np.zeros(209*SR,dtype=np.float32)
 for key,file,speaker,rows in MANIFEST:
  audio,sr=sf.read(ROOT/file,dtype='float32');audio=audio.mean(axis=1) if audio.ndim>1 else audio
  if sr!=SR:audio=resample_poly(audio,SR//math.gcd(sr,SR),sr//math.gcd(sr,SR)).astype(np.float32)
  weights=[max(1,len(txt.split())) for _,txt in rows];gap=min(.24,(len(audio)/SR*.07)/(len(rows)-1)) if len(rows)>1 else 0
  speechdur=max(.01,len(audio)/SR-gap*(len(rows)-1));tot=sum(weights);cursor=0
  for (shotnum,txt),wt in zip(rows,weights):
   span=speechdur*wt/tot;seg=audio[int(cursor*SR):min(len(audio),int((cursor+span)*SR))];cursor+=span+gap
   shot=SHOTS[shotnum-1];start=shot['start']+OFFSETS.get((speaker,shotnum),.28);maxdur=shot['end']-start-.06
   if speaker in ('HOST1','MULE') and shotnum==15:maxdur=shot['end']-start-.10
   if len(seg)/SR>maxdur:
    n=max(1,int(maxdur*SR));seg=np.interp(np.linspace(0,len(seg)-1,n),np.arange(len(seg)),seg).astype(np.float32)
   if not len(seg):continue
   wet={'NARR':.035,'CALL':.13,'VICT':.15,'HOST1':.13,'MULE':.13,'JUDG':.16}[speaker]
   rev=seg.copy()
   for delay,gain in ((.031,.22),(.057,.12),(.091,.07)):
    q=int(delay*SR)
    if q<len(seg):rev[q:]+=seg[:-q]*gain*wet/.16
   pan={'NARR':0,'CALL':-.28,'VICT':.28,'HOST1':.23,'MULE':-.23,'JUDG':0}[speaker];l=math.sqrt((1-pan)/2);r=math.sqrt((1+pan)/2)
   stereo=np.column_stack((rev*l,rev*r)).astype(np.float32);mouth=mouth_track(seg)
   e=dict(speaker=speaker,shot=shotnum,text=txt,start=start,end=start+len(seg)/SR,mono=seg,stereo=stereo,mouth=mouth);events.append(e)
   a=int(start*SR);b=min(len(activity),a+len(seg));activity[a:b]=np.maximum(activity[a:b],np.abs(seg[:b-a]))
 return events,activity

def audio_fx():
 n=209*SR;fx=np.zeros(n,dtype=np.float32);rng=np.random.default_rng(2026)
 def add(wave,t,g=1.0):
  i=int(t*SR);j=min(n,i+len(wave))
  if j>i:fx[i:j]+=wave[:j-i]*g
 def tone(freq,dur,amp,decay=4,drop=0):
  tt=np.arange(max(1,int(dur*SR)),dtype=np.float32)/SR
  hz=freq*(1-drop*np.minimum(1,tt/max(dur,.001)))
  return (np.sin(2*np.pi*hz*tt)*np.exp(-decay*tt)*amp).astype(np.float32)
 def noise_hit(dur=.22,amp=.25,tail=12):
  n0=max(1,int(dur*SR));z=rng.standard_normal(n0).astype(np.float32)
  z=np.r_[0,np.diff(z)].astype(np.float32);env=np.exp(-np.linspace(0,tail,dur and n0,dtype=np.float32)/max(tail,1))
  return z*env*amp
 def whoosh(dur=.52):
  n0=int(dur*SR);z=rng.standard_normal(n0).astype(np.float32);z=np.r_[0,np.diff(z)].astype(np.float32)
  env=np.sin(np.linspace(0,np.pi,n0,dtype=np.float32))**2
  return z*env*.22
 def thud(dur=.62,wood=False):
  sub=tone(58 if not wood else 92,dur,.52 if not wood else .32,5.5,.20)
  atk=noise_hit(.09,.34 if wood else .24,10)
  return np.pad(sub,(0,max(0,len(atk)-len(sub))))+np.pad(atk,(0,max(0,len(sub)-len(atk))))
 def paper(dur=.66):
  n0=int(dur*SR);z=rng.standard_normal(n0).astype(np.float32);z=np.r_[0,np.diff(z)].astype(np.float32)
  env=np.maximum(0,np.sin(np.linspace(0,np.pi,n0,dtype=np.float32)))**.7
  return z*env*.075
 def phone_ring(dur=1.1):
  tt=np.arange(int(dur*SR),dtype=np.float32)/SR;gate=(np.sin(2*np.pi*2.1*tt)>.15).astype(np.float32)
  return (gate*(.19*np.sin(2*np.pi*930*tt)+.12*np.sin(2*np.pi*1175*tt))*np.exp(-tt*.25)).astype(np.float32)
 # Quiet door chime, approaching steps and phone alert.
 for freq,amp,at in ((659,.26,5.65),(880,.18,5.79)):add(tone(freq,.75,amp,2.6),at)
 for at in (.65,1.35,2.08,141.5,142.2,142.9):add(thud(.22,True),at,.27)
 add(phone_ring(),39.8,.62);add(phone_ring(.72),178.3,.30)
 # Mute score on cards, but leave each sculpted low-frequency chapter impact.
 for shot in SHOTS:
  if shot['card']:
   add(tone(36,1.28,.82,2.15,.08),shot['start'],.92)
   add(thud(.72,False),shot['start']+.015,.62)
  if shot['whip_in']:add(whoosh(.42),max(0,shot['start']-.22),.55)
  if shot['whip_out']:add(whoosh(.46),shot['end']-.34,.52)
 # Paper slides, package taps, ink stamps, gavel and instant-camera shutter.
 for at in (61.8,83.15,86.7,130.2,135.1,168.0):add(paper(.5),at,.75)
 for at in (87.1,96.8,97.2):add(thud(.42,True),at,.55)
 for at in (32.5,63.4,97.0,135.4,143.3,162.8,171.5,197.4):
  add(thud(.48,True),at,.50);add(tone(740,.13,.09,11),at+.03,.60)
 add(noise_hit(.06,.55,24),200.4,.75);add(whoosh(.18),200.32,.28)
 # Short resonant room tail is tucked behind the direct Foley.
 dry=fx.copy()
 for delay,gain in ((.075,.15),(.145,.08),(.24,.035)):
  off=int(delay*SR);fx[off:]+=dry[:-off]*gain
 return fx

def score(length=209):
 n=length*SR;music=np.zeros((n,2),np.float32);beat=60/104;bar=beat*4;progression=[(45,[57,60,64]),(41,[53,57,60]),(38,[50,53,57]),(40,[52,56,59])]
 def note(m,start,dur,amp,pan=0,kind='pluck'):
  i=int(start*SR);count=min(int(dur*SR),n-i)
  if count<=0:return
  tt=np.arange(count,dtype=np.float32)/SR;f=440*2**((m-69)/12)
  if kind=='bass':env=np.exp(-tt*5.8)*np.minimum(1,tt/.012);sig=np.sin(2*np.pi*f*tt)*env
  elif kind=='pad':env=np.exp(-tt*3.1);sig=(np.sin(2*np.pi*f*tt)+.25*np.sin(4*np.pi*f*tt))*env
  else:env=np.exp(-tt*8)*np.minimum(1,tt/.004);sig=(np.sin(2*np.pi*f*tt)+.2*np.sin(4*np.pi*f*tt))*env
  l=math.sqrt((1-pan)/2);r=math.sqrt((1+pan)/2);music[i:i+count,0]+=sig*amp*l;music[i:i+count,1]+=sig*amp*r
 t=0;bi=0
 while t<length:
  root,ch=progression[bi%4]
  for m in ch:note(m,t,bar*1.8,.026,-.15,'pad')
  for j,k in enumerate((0,3,7,3)):note(root+k,t+j*beat,beat*.78,.055,-.18,'bass')
  for j in (1,3):
   for m in ch:note(m+12,t+j*beat,.21,.026,.20)
  t+=bar;bi+=1
 return music

def write_audio(events,activity):
 voice=np.zeros((209*SR,2),dtype=np.float32)
 for e in events:
  i=int(e['start']*SR);b=min(len(voice),i+len(e['stereo']));voice[i:b]+=e['stereo'][:b-i]*.82
 music=score();fx=audio_fx();hop=480;p=np.pad(activity,(0,(-len(activity))%hop));rms=np.sqrt(np.mean(p.reshape(-1,hop)**2,axis=1)+1e-10);env=np.repeat(np.clip(rms*5,0,1),hop)[:len(activity)];duck=1-.60*env
 for s in SHOTS:
  if s['card']:duck[int(s['start']*SR):int(s['end']*SR)]=0
 mix=voice+music*(.58*duck[:,None])+fx[:,None]*.42
 mix=np.tanh(mix*1.08)/np.tanh(1.08);mix=np.clip(mix,-.97,.97)
 sf.write(ROOT/'cinema_mix.wav',mix,SR,subtype='PCM_16')

def timecode(t):
 ms=int(round(max(0,t)*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
def write_srt(events):
 with (ROOT/'fake_funeral_27m_scam.srt').open('w',encoding='utf8') as f:
  for i,e in enumerate(sorted(events,key=lambda z:z['start']),1):f.write(f"{i}\n{timecode(e['start'])} --> {timecode(e['end'])}\n{e['text']}\n\n")

def apply_camera(im,shot,local):
 z=1+.06*ease(local);nw,nh=int(W*z),int(H*z);x=int((nw-W)*(.25+.5*local));y=int((nh-H)*.48)
 if z>1:im=im.resize((nw,nh),Image.Resampling.BILINEAR).crop((x,y,x+W,y+H))
 if shot['whip_in'] and local<.16:
  dx=int(W*(1-local/.16)**2);im=ImageChops.offset(im,dx,0)
 elif shot['whip_out'] and local>.84:
  dx=int(W*((local-.84)/.16)**2);im=ImageChops.offset(im,-dx,0)
 return im

def render_contact(events,path):
 from PIL import ImageDraw
 cw,ch,lh,cols=480,270,30,4;sheet=Image.new('RGB',(cw*cols,6*(ch+lh)),(10,10,14));d=ImageDraw.Draw(sheet)
 for i,s in enumerate(SHOTS):
  t=(s['start']+s['end'])/2;mouths={e['speaker']:e['mouth'][min(len(e['mouth'])-1,int((t-e['start'])*FPS))] for e in events if e['shot']==s['i'] and e['start']<=t<e['end']}
  im=scene_art(s,.5,t,mouths).resize((cw,ch),Image.Resampling.LANCZOS);x=(i%cols)*cw;y=(i//cols)*(ch+lh);sheet.paste(im,(x,y));d.rectangle((x,y+ch,x+cw,y+ch+lh),fill=(10,10,14));d.text((x+8,y+6),f"{s['i']:02} {s['kind']}  {s['set']}",font=font(17),fill=CREAM)
 sheet.save(path,quality=91)

def main():
 events,activity=build_voice_events();write_srt(events);write_audio(events,activity)
 # Contact sheet is rendered before the final movie, for visual QA.
 render_contact(events,ROOT/'qa_contact_sheet.jpg')
 ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();out=ROOT/'fake_funeral_27m_scam.mp4';audio=ROOT/'cinema_mix.wav'
 cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-i',str(audio),'-map','0:v:0','-map','1:a:0','-vf',f'scale={OUT_W}:{OUT_H}:flags=lanczos,format=yuv420p','-c:v','libx264','-preset','veryfast','-crf','19','-c:a','aac','-b:a','192k','-ar','48000','-af','loudnorm=I=-14:TP=-1.5:LRA=7','-shortest','-movflags','+faststart',str(out)]
 proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
 try:
  for frame in range(209*FPS):
   t=frame/FPS;s=next((x for x in SHOTS if x['start']<=t<x['end']),SHOTS[-1]);local=(t-s['start'])/(s['end']-s['start'])
   mouths={e['speaker']:e['mouth'][max(0,min(len(e['mouth'])-1,int((t-e['start'])*FPS)))] for e in events if e['shot']==s['i'] and e['start']<=t<e['end']}
   im=scene_art(s,local,t,mouths)
   if not s['card']:im=apply_camera(im,s,local)
   proc.stdin.write(im.tobytes())
   if frame%(FPS*10)==0:print(f"Shot {s['i']:02}/24 at {t:.1f}s",flush=True)
 except BrokenPipeError:raise RuntimeError('FFmpeg closed the input pipe')
 finally:
  if proc.stdin and not proc.stdin.closed:proc.stdin.close()
 rc=proc.wait()
 if rc:raise SystemExit(rc)
 print(f'Wrote {out}: 1920x1080, 30 fps, 209 s')
if __name__=='__main__':
 from animated_renderer import main as animated_main
 animated_main()
