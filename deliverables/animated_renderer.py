"""Frame-by-frame character animation pass over the approved 24-shot plate art."""
from __future__ import annotations
import importlib.util, math, sys, subprocess, functools
from pathlib import Path
import numpy as np
from PIL import Image,ImageChops,ImageDraw,ImageEnhance,ImageFilter,ImageFont
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parent
W,H,FPS=1920,1080,30
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('base_art',HERE/'create_video.py')
base=importlib.util.module_from_spec(spec);sys.modules['base_art']=base;spec.loader.exec_module(base)
INK=(24,22,27);CREAM='#FFF6DC';GOLD='#F2C14E';RED='#C8242C';LIME='#B8F04A';CYAN='#8FC8EE'
FONT_HAND=HERE/'fonts/CaveatBrush-Regular.ttf';FONT_KALAM=HERE/'fonts/Kalam-Bold.ttf';FONT_MARKER=HERE/'fonts/PermanentMarker-Regular.ttf'

# Skill-style articulated pose library; coordinates are relative to the torso anchor.
POSES={'down':((-76,-230),(-92,-163),True),'pocket':((-88,-233),(-67,-176),False),'hip':((-114,-238),(-79,-190),True),'present':((-125,-296),(-190,-334),True),'gesture':((-125,-255),(-149,-351),True),'chin':((-113,-257),(-61,-312),True),'hold':((-88,-230),(-43,-205),True),'push':((-116,-265),(-184,-255),True),'phone':((-92,-245),(-50,-268),True),'reassure':((-120,-275),(-165,-295),True)}

def back(u,k=1.7):u=max(0,min(1,u))-1;return 1+(k+1)*u**3+k*u**2
def smooth(u):u=max(0,min(1,u));return .5-.5*math.cos(math.pi*u)
def fnt(size,kind='hand'):
 path=FONT_HAND if kind=='hand' else FONT_KALAM if kind=='kalam' else FONT_MARKER
 return ImageFont.truetype(str(path),max(1,int(size)))
def label(d,s,xy,size,color=CREAM,kind='hand',stroke=7,anchor='mm',angle=0):
 font=fnt(size,kind);box=d.textbbox((0,0),s,font=font,stroke_width=max(0,int(stroke)));w=box[2]-box[0]+40;h=box[3]-box[1]+32
 lay=Image.new('RGBA',(w,h),(0,0,0,0));ld=ImageDraw.Draw(lay);ld.text((w//2,h//2),s,font=font,fill=color,anchor='mm',stroke_width=max(0,int(stroke)),stroke_fill=INK)
 if angle:lay=lay.rotate(angle,Image.Resampling.BICUBIC,expand=True)
 d._image.paste(lay,(int(xy[0]-lay.width/2),int(xy[1]-lay.height/2)),lay)

def move_pose(name,t,states):
 if not states:return POSES['down']
 if t<=states[0][0]:return POSES[states[0][1]]
 for i in range(len(states)-1):
  t0,a=states[i];t1,b=states[i+1]
  if t<t1:
   q=back((t-t0)/max(.001,t1-t0));p=POSES[a];r=POSES[b]
   e=tuple(p[0][j]+(r[0][j]-p[0][j])*q for j in range(2));h=tuple(p[1][j]+(r[1][j]-p[1][j])*q for j in range(2))
   return e,h,r[2] if q>.5 else p[2]
 return POSES[states[-1][1]]

def draw_puppet(im,name,x,feet,scale=1,face=0,t=0,emotion='calm',mouth='closed',left='down',right='down',walk=False,phase=0,sweat=False,tag=None):
 sp=base.CAST[name];d=ImageDraw.Draw(im);s=scale
 bob=math.sin(t*3.1+phase)*5*s+(abs(math.sin(t*6.0+phase))*4*s if walk else 0)
 # squash-and-stretch lands on pose changes and impacts
 squash=.055*math.sin(math.pi*max(0,min(1,t/.28))) if t<.28 else 0
 ft=feet+bob;shadow=(x-94*s,ft-11*s,x+94*s,ft+9*s);d.ellipse(shadow,fill=(4,6,13))
 gait=math.sin(t*6.2+phase)*29*s if walk else math.sin(t*2+phase)*2*s
 for i,(lx,sgn) in enumerate(((-25,1),(25,-1))):
  swing=gait*sgn;lift=max(0,math.cos(t*6.2+phase+i*math.pi))*19*s if walk else 0
  d.line((x+lx*s,ft-63*s,x+lx*s+swing,ft-lift),fill=INK,width=max(4,int(8*s)))
 # pill body + cutout jacket shadow
 top=ft-344*s;bot=ft-126*s;body=(x-82*s,top,x+82*s,bot)
 d.rounded_rectangle(body,radius=int(65*s),fill=sp['suit'],outline=INK,width=max(5,int(8*s)))
 jacket=Image.new('RGBA',(int(164*s),int(218*s)),(0,0,0,0));jd=ImageDraw.Draw(jacket);jd.rounded_rectangle((0,0,jacket.width,jacket.height),radius=int(65*s),fill=sp.get('suit_d',sp.get('dark',sp['suit'])))
 cut=Image.new('L',jacket.size,0);cd=ImageDraw.Draw(cut);cd.rounded_rectangle((int(18*s),int(4*s),jacket.width-int(18*s),jacket.height),radius=int(52*s),fill=255)
 outer=Image.new('L',jacket.size,0);ImageDraw.Draw(outer).rounded_rectangle((0,0,jacket.width-1,jacket.height-1),radius=int(65*s),fill=255)
 mask=ImageChops.subtract(outer,ImageChops.offset(cut,int(9*s),-int(5*s)))
 im.paste(jacket,(int(x-82*s),int(top)),mask);d=ImageDraw.Draw(im);d.rounded_rectangle(body,radius=int(65*s),outline=INK,width=max(5,int(8*s)))
 # shirt V, lapels, tie, seams
 d.polygon([(x-39*s,top+3*s),(x,top+96*s),(x+39*s,top+3*s)],fill=sp['shirt'],outline=INK)
 d.line((x-37*s,top+4*s,x,top+99*s,x+37*s,top+4*s),fill=sp['shirt'],width=max(3,int(5*s)))
 if sp.get('bowtie'):
  yy=top+43*s;d.polygon([(x,yy),(x-27*s,yy-15*s),(x-27*s,yy+15*s)],fill=sp['tie'],outline=INK);d.polygon([(x,yy),(x+27*s,yy-15*s),(x+27*s,yy+15*s)],fill=sp['tie'],outline=INK)
  d.ellipse((x-7*s,yy-7*s,x+7*s,yy+7*s),fill=sp['tie'],outline=INK,width=3)
 else:d.polygon([(x-11*s,top+28*s),(x+11*s,top+28*s),(x+15*s,top+84*s),(x,top+101*s),(x-15*s,top+84*s)],fill=sp['tie'],outline=INK)
 # dynamic arms: overshoot pose changes, curved shoulder-elbow-hand path
 for side,pose in ((-1,left),(1,right)):
  states=pose if isinstance(pose,list) else [(0,pose)];el,hand,show=move_pose(name,t,states);mirror=1 if side<0 else -1
  sx=x+side*56*s;sy=top+54*s;ex=x+mirror*el[0]*s;ey=ft+el[1]*s;hx=x+mirror*hand[0]*s;hy=ft+hand[1]*s
  pts=[]
  for q in np.linspace(0,1,10):
   v=1-q;pts.append((v*v*sx+2*v*q*ex+q*q*hx,v*v*sy+2*v*q*ey+q*q*hy))
  d.line(pts,fill=INK,width=max(5,int(11*s)),joint='curve')
  d.line(pts,fill=sp['suit'],width=max(2,int(4*s)),joint='curve')
  if show:
   rr=15*s;d.ellipse((hx-rr,hy-rr,hx+rr,hy+rr),fill=sp['skin'],outline=INK,width=max(3,int(5*s)))
 # round head, face anchor shifts for 3/4 turn
 cx=x+face*20*s+math.sin(t*1.5+phase)*3*s;cy=ft-419*s-squash*90*s;r=88*s
 # soft face gradient from lamp side, then skill-style cutout crescent
 d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=sp['skin'],outline=INK,width=max(5,int(8*s)))
 mask=Image.new('L',(max(1,int(2*r)),max(1,int(2*r))),0);md=ImageDraw.Draw(mask);md.ellipse((0,0,2*r-1,2*r-1),fill=255);md.ellipse((10*s,-18*s,2*r+10*s,2*r-18*s),fill=0)
 shade=Image.new('RGBA',mask.size,base.rgb(sp.get('skin_d',sp.get('shade',sp['skin'])))+(255,));im.paste(shade,(int(cx-r),int(cy-r)),mask);d=ImageDraw.Draw(im)
 d.arc((cx-r+4,cy-r+4,cx+r-4,cy+r-4),210 if face<0 else 330,325 if face<0 else 145,fill='#FFE5AE',width=max(3,int(6*s)))
 # hair silhouette / bald side tufts
 if sp.get('hair')=='slick':
  d.pieslice((cx-r,cy-r-4,cx+r,cy+r*.20),180,357,fill=sp['hair_col'],outline=INK,width=max(4,int(6*s)))
  d.arc((cx-r*.65,cy-r*.92,cx+r*.55,cy-r*.30),205,320,fill='#82705E',width=max(2,int(4*s)))
 else:
  for side in (-1,1):
   bx=cx+side*r*.6;d.arc((bx-r*.42,cy-r*.40,bx+r*.12,cy+r*.42),70 if side<0 else 100,280,fill=sp.get('hair_col','#777983'),width=max(3,int(9*s)))
 # eyes blink every 2.5-3.0s; expression state animates with speaking / reaction
 blink=(t+phase)%2.7<.12;eye_y=cy-7*s;shift=face*31*s
 near=cx+shift+(29 if face>0 else -29)*s;far=cx+shift+(-29 if face>0 else 29)*s
 for j,ex in enumerate((far,near)):
  er=(8 if j==0 else 11)*s*(.68 if j==0 and abs(face)>.35 else 1)
  wide=emotion=='surprised'
  if blink or emotion=='blink':d.line((ex-er,eye_y,ex+er,eye_y),fill=INK,width=max(4,int(6*s)))
  elif wide:
   d.ellipse((ex-er*1.5,eye_y-er*1.45,ex+er*1.5,eye_y+er*1.45),fill='#FFFEF5',outline=INK,width=max(3,int(4*s)));d.ellipse((ex-er*.42,eye_y-er*.30,ex+er*.42,eye_y+er*.58),fill=INK);d.ellipse((ex-er*.15,eye_y-er*.28,ex+er*.04,eye_y-er*.08),fill='#FFFFFF')
  elif emotion=='smug':
   d.ellipse((ex-er*.55,eye_y-er*.2,ex+er*.55,eye_y+er*.65),fill=INK);d.line((ex-er*1.4,eye_y-er*.3,ex+er*1.4,eye_y-er*.2),fill=INK,width=max(3,int(5*s)))
  else:
   d.ellipse((ex-er*.55,eye_y-er*.35,ex+er*.55,eye_y+er*.65),fill=INK);d.ellipse((ex-er*.18,eye_y-er*.28,ex+er*.08,eye_y-er*.08),fill='#FFFFFF')
 # animated expressive brows
 brow={'calm':0,'worried':-0.7,'angry':1,'surprised':-1,'smug':.55,'relieved':.15}.get(emotion,0)
 by=eye_y-27*s;d.line((far-17*s,by+brow*7*s,far+18*s,by-brow*3*s),fill=INK,width=max(4,int(7*s)))
 d.line((near-18*s,by-brow*3*s,near+17*s,by+brow*7*s),fill=INK,width=max(4,int(7*s)))
 # eyewear and facial hair remain attached to the head
 if sp.get('glasses'):
  for ex in (far,near):d.ellipse((ex-20*s,eye_y-17*s,ex+20*s,eye_y+17*s),outline=INK,width=max(3,int(5*s)));d.line((far+15*s,eye_y,near-15*s,eye_y),fill=INK,width=max(3,int(4*s)))
 mx=cx+shift;my=cy+37*s
 if sp.get('moustache'):
  d.arc((mx-31*s,my-16*s,mx+3*s,my+12*s),190,350,fill=sp.get('hair_col',sp.get('hair',INK)),width=max(5,int(9*s)));d.arc((mx-3*s,my-16*s,mx+31*s,my+12*s),190,350,fill=sp.get('hair_col',sp.get('hair',INK)),width=max(5,int(9*s)))
 if mouth in ('open','mid','o'):
  mw,mh=(16,22) if mouth=='open' else (13,15) if mouth=='mid' else (9,14)
  d.ellipse((mx-mw*s,my-mh*s,mx+mw*s,my+mh*s),fill='#451B25',outline=INK,width=max(2,int(4*s)))
  if mouth=='open':d.arc((mx-10*s,my+1*s,mx+10*s,my+18*s),0,180,fill='#D85B67',width=max(2,int(3*s)))
 elif emotion=='smile':d.arc((mx-22*s,my-11*s,mx+22*s,my+22*s),10,170,fill=INK,width=max(3,int(5*s)))
 elif emotion=='smug':d.arc((mx-20*s,my-12*s,mx+22*s,my+20*s),15,150,fill=INK,width=max(3,int(5*s)))
 else:d.line((mx-15*s,my,mx+15*s,my),fill=INK,width=max(3,int(5*s)))
 if emotion=='surprised':
  ex=cx+(70 if face<0 else -70)*s;ey=cy-40*s;d.polygon([(ex,ey-18*s),(ex-10*s,ey+3*s),(ex,ey+18*s),(ex+10*s,ey+3*s)],fill=CYAN,outline=INK)
 if sweat:
  ex=cx+(72 if face<0 else -72)*s;ey=cy-40*s+math.sin(t*6+phase)*8*s;d.polygon([(ex,ey-17*s),(ex-9*s,ey+3*s),(ex,ey+17*s),(ex+9*s,ey+3*s)],fill=CYAN,outline=INK)
 if emotion=='smile':
  sx=cx+60*s;sy=cy-65*s;d.line((sx-12*s,sy,sx+12*s,sy),fill=GOLD,width=3);d.line((sx,sy-12*s,sx,sy+12*s),fill=GOLD,width=3)
 if tag:
  box=(x-95*s,ft+6*s,x+95*s,ft+44*s);d.rounded_rectangle(box,radius=5*s,fill='#C5AD84',outline=INK,width=3);d.text((x,ft+25*s),tag,font=fnt(17*s,'kalam'),fill=INK,anchor='mm')

def pop_text(im,txt,x,y,local,size=72,color=LIME,angle=-4,kind='hand'):
 if local<=0:return
 q=1.14 if local<.24 else 1+.14*math.exp(-5*(local-.24));d=ImageDraw.Draw(im);label(d,txt,(x,y),size*q,color,kind,stroke=12,angle=angle)

def stamp_text(im,txt,x,y,progress,angle=-7,size=68,color=RED):
 if progress<=0:return
 q=1+.18*math.sin(min(1,progress/.24)*math.pi)*math.exp(-3*progress/.24)
 font=fnt(size*q,'marker');d=ImageDraw.Draw(im);bb=d.textbbox((0,0),txt,font=font,stroke_width=2);w=bb[2]-bb[0]+60;h=bb[3]-bb[1]+48
 lay=Image.new('RGBA',(w,h),(0,0,0,0));ld=ImageDraw.Draw(lay);ld.rounded_rectangle((5,5,w-5,h-5),radius=8,outline=color,width=6);ld.text((w//2,h//2),txt,font=font,fill=color,anchor='mm',stroke_width=1,stroke_fill=INK)
 lay=lay.rotate(angle,Image.Resampling.BICUBIC,expand=True);im.paste(lay,(int(x-lay.width/2),int(y-lay.height/2)),lay)
 if progress<.16:
  dx=int(12*(1-progress/.16)*math.sin(progress*90));im=ImageChops.offset(im,dx,0)
 return im

def type_card(im,shot,local):
 d=ImageDraw.Draw(im);d.rectangle((0,0,W,H),fill='#000000')
 title={5:'CHAPTER ONE - THE BAIT',10:'CHAPTER TWO - THE CASH BOX',14:'CHAPTER THREE - THE STING',18:'CHAPTER FOUR - THE RECKONING',24:'PAUSE FIRST. VERIFY ALWAYS.'}[shot['i']]
 words=title.split();speed=1.55 if shot['i']!=24 else 1.4;count=min(len(words),max(1,int(local*len(words)*speed)+1));shown=' '.join(words[:count])
 size=74 if shot['i']!=14 else 61
 label(d,shown,(W/2,H/2),size,CREAM,'hand',stroke=2)
 if local>.84 and shot['i']==24:label(d,'THE END',(W/2,H/2+110),34,GOLD,'kalam',stroke=1)
 return im

def enhance_plate(sh,local):
 # Detailed photographed-style plate art from the shot layout; upgraded to 1080p.
 if sh['card']:return Image.new('RGB',(W,H),(0,0,0))
 plate=base.set_base(sh['set']).copy();base.draw_props(plate,sh,local);plate=base.lit(plate,sh['set'])
 return plate.resize((W,H),Image.Resampling.LANCZOS)

@functools.lru_cache(maxsize=24)
def plate_cache(idx):
 sh=base.SHOTS[idx];return enhance_plate(sh,.45)

def dynamic_effects(im,sh,local,t):
 d=ImageDraw.Draw(im);k=sh['kind'];n=sh['i']
 # Cinematic motes, practical monitor flicker and moving spot details.
 if k in ('porch','courthouse'):
  for j in range(18):
   x=(j*197+int(t*15*(1 if j%2 else -1)))%W;y=(j*91+int(math.sin(t*1.4+j)*9))%400
   if j%3==0:d.ellipse((x,y,x+4,y+4),fill=(180,198,233))
 if k=='caller':
  for j in range(8):
   x=110+j*239;y=168+(j%2)*354
   d.ellipse((x+333,y+201,x+351,y+219),fill=RED if int(t*4+j)%7==0 else '#47747C')
   if int(t*2+j)%9==0:d.rectangle((x+26,y+25,x+210,y+40),fill='#315D68')
 if k in ('losses','refund','parcel','map','evidence','ledger'):
  # Softly moving practical overhead sweep across physical paper.
  u=.5+.5*math.sin(t*.85);x=int(430+u*1040);glow=Image.new('RGBA',(W,H),(0,0,0,0));gd=ImageDraw.Draw(glow);gd.ellipse((x-260,180,x+260,950),fill=(255,225,160,18));glow=glow.filter(ImageFilter.GaussianBlur(75));im.alpha_composite(glow) if im.mode=='RGBA' else im.paste(glow,(0,0),glow)
 if n==4:
  # Tick-up is printed on the evidence ledger, not a floating HUD.
  d.rectangle((1195,342,1540,472),fill='#EEE3CB');amount=int(27_000_000*min(1,local*1.3));label(d,f'${amount:,}',(1370,405),74,LIME,'hand',stroke=10)
  arc=Image.new('RGBA',(W,H),(0,0,0,0));ad=ImageDraw.Draw(arc);ad.arc((1170,325,1570,493),188,188+350*max(0,min(1,(local-.18)*1.5)),fill=RED,width=13);im.paste(arc,(0,0),arc)
 if n==8:
  arc=Image.new('RGBA',(W,H),(0,0,0,0));ad=ImageDraw.Draw(arc);ad.arc((1124,380,1570,600),190,190+340*max(0,min(1,(local-.15)*1.5)),fill=RED,width=13);im.paste(arc,(0,0),arc)
 if n==11:
  # package shifts onto a counter with a small overshoot
  q=1-smooth(min(1,max(0,(local-.15)*2.2)));x=int(710+q*360);y=int(420+8*math.sin(t*4)*(1-q));d.rectangle((x-15,y-10,x+130,y+95),fill='#A7794C',outline=INK,width=8);d.polygon([(x-15,y-10),(x+45,y-43),(x+145,y-14),(x+86,y+19)],fill='#C7955F',outline=INK,width=7);d.text((x+56,y+46),'CASH',font=fnt(21,'kalam'),fill=CREAM,anchor='mm')
 if n==13:
  # route advances on the physical paper map
  p=[(410,550),(680,490),(1010,416),(1470,380)];parts=int(1+local*(len(p)-1));d.line(p[:parts+1],fill=RED,width=12,joint='curve')
  if parts<len(p)-1:
   q=local*(len(p)-1)-parts;x=int(p[parts][0]+(p[parts+1][0]-p[parts][0])*q);y=int(p[parts][1]+(p[parts+1][1]-p[parts][1])*q);d.ellipse((x-15,y-15,x+15,y+15),fill=GOLD,outline=INK,width=5)
 if n==19:
  # gavel swing with impact pulse
  swing=math.sin(min(1,local*2.5)*math.pi/2);x0,y0=1040,600;x1=1170+int(90*swing);y1=720+int(80*swing);d.line((x0,y0,x1,y1),fill='#754628',width=36);d.ellipse((x0-55,y0-27,x0+58,y0+27),fill='#9C6947',outline=INK,width=7);d.ellipse((x1-58,y1-29,x1+58,y1+29),fill='#9C6947',outline=INK,width=7)
 if n==21:
  yy=int(500+280*smooth(local));d.arc((430,yy-45,590,yy+45),190,350,fill=INK,width=20);d.line((439,yy,464,yy-8),fill=INK,width=15);d.line((558,yy-8,582,yy),fill=INK,width=15)
 if n==23 and local<.16:
  alpha=int(205*(1-local/.16));flash=Image.new('RGB',(W,H),(255,248,222));im=Image.blend(im,flash,alpha/255)
 # Hand-lettered words and physical stamps animate onto the world with overshoot.
 if n==1 and local>.43:pop_text(im,'KNOCK',1440,414,local-.43,54,GOLD,-4)
 if n==3:stamp_text(im,'CAUGHT ON CAMERA',1430,263,local-.10,-8,55,RED)
 if n==6:pop_text(im,'UNKNOWN CALLER',1475,222,local-.12,41,GOLD,-3)
 if n==12:stamp_text(im,'FORGED ID',1420,620,local-.17,-9,48,RED)
 if n==16:stamp_text(im,'DOJ RECORD',1440,760,local-.18,-6,49,RED)
 if n==17:stamp_text(im,'COURT RECORD',1455,310,local-.22,-8,64,RED)
 if n==19:stamp_text(im,'78 MONTHS',1418,315,local-.25,-5,59,RED)
 if n==20:stamp_text(im,'78 MONTHS',965,770,local-.34,-4,50,RED)
 # warm practical lamp flicker, non-distracting film grain
 if int(t*FPS)%4==0:
  ar=np.asarray(im).astype(np.int16);noise=np.random.default_rng(int(t*1000)%65535).integers(-2,3,(H,W,1),dtype=np.int16);im=Image.fromarray(np.clip(ar+noise,0,255).astype(np.uint8),'RGB')
 return im

def cast_frame(im,sh,local,t,events):
 n=sh['i'];mouths={e['speaker']:e['mouth'][max(0,min(len(e['mouth'])-1,int((t-e['start'])*base.FPS)))] for e in events if e['shot']==n and e['start']<=t<e['end']}
 def m(who):return mouths.get(who,'closed')
 def actor(role,x,y,s,face,emo='calm',speaker='',walk=False,phase=0,arms=None,sweat=False):
  if emo=='surprised' and local>.58:emo='worried'
  if role=='MARGARET' and n==21 and local>.58:emo='relieved'
  if role=='MARGARET' and n==22:emo='smile'
  left,right=arms or ('down','down');states=[]
  if emo in ('talk','present') or (speaker and emo=='calm'):
   left=[(0,'down'),(.35,'gesture'),(2.8,'present'),(4.4,'down')];right=[(0,'down'),(1.1,'chin'),(3.8,'present'),(5.0,'down')]
  elif emo=='surprised':
   left=[(0,'down'),(.25,'gesture'),(1.35,'down')];right=[(0,'down'),(.45,'chin'),(1.65,'down')]
  elif emo=='comfort':left=[(0,'down'),(.4,'reassure'),(2,'hold')];right='present'
  return draw_puppet(im,role,x,y,s,face,t=t-sh['start'],emotion=emo,mouth=m(speaker) if speaker else 'closed',left=left,right=right,walk=walk,phase=phase,sweat=sweat)
 if n==1:
  x=300+int(365*smooth(local));actor('CHEN',x,1035,.83,-.62,'surprised','',True,.4,('down','phone'),local>.72)
  if .48<local<.78:label(ImageDraw.Draw(im),'KNOCK',(1500,350),58,GOLD,'hand',stroke=8)
 elif n==2:
  actor('CHEN',430,1038,.86,-.60,'surprised','MULE',phase=.5,arms=('down','chin'),sweat=True)
  actor('ASHTON',1272,1038,.90,.64,'calm','HOST1',phase=1.1)
  actor('ART',1570,1034,.78,-.45,'calm',phase=2.1)
 elif n==3:
  actor('CHEN',960,1440,1.68,-.70,'surprised','',phase=.6,sweat=True)
 elif n==6:
  actor('MARGARET',570,1040,.96,.55,'worried','',phase=.4,arms=('phone','chin'))
 elif n==7:
  actor('CALLER',966,1042,.97,-.52,'smug','CALL',phase=1.0)
 elif n==9:
  actor('MARGARET',960,1460,1.84,.64,'surprised','VICT',phase=.2,sweat=True)
 elif n==12:
  actor('CHEN',1030,1390,1.75,.65,'worried','',phase=.7,sweat=True,arms=('hold','push'))
 elif n==15:
  actor('CHEN',398,1032,.85,-.65,'surprised','MULE',True,.2,sweat=True)
  actor('ASHTON',1284,1032,.91,.67,'calm','HOST1',phase=1.1,arms=('present','gesture'))
  actor('ART',1570,1032,.78,-.47,'calm',phase=2.1)
 elif n==17:
  actor('CHEN',955,1030,.70,-.50,'worried','',True,.3)
 elif n==19:
  actor('JUDGE',958,680,.82,-.35,'calm','JUDG',phase=.5)
  actor('CHEN',1545,1030,.80,.62,'worried','',phase=1.8,sweat=True)
 elif n==21:
  actor('MARGARET',555,1030,.90,.6,'calm','',phase=.4,arms=('phone','down'))
 elif n==22:
  actor('MARGARET',674,1430,1.7,.58,'smile','',phase=.3,arms=('present','hold'))
  actor('ART',1510,1325,1.22,-.33,'smile','',phase=1.4,arms=('reassure','present'))
 elif n==23:
  actor('CHEN',762,760,.52,-.58,'surprised','',phase=.7)
  actor('ASHTON',1307,760,.52,.60,'calm','',phase=1.2,arms=('present','gesture'))
 return im

def scene_frame(sh,local,t,events):
 if sh['card']:return type_card(Image.new('RGB',(W,H),(0,0,0)),sh,local)
 im=plate_cache(sh['i']-1).copy();im=dynamic_effects(im,sh,local,t);im=cast_frame(im,sh,local,t,events)
 # add smooth camera shake only on impact beats; otherwise persistent 6% push/pan
 z=1+.045*smooth(local);nw,nh=int(W*z),int(H*z);im=im.resize((nw,nh),Image.Resampling.BILINEAR)
 cx=int((nw-W)*(.25+.48*local));cy=int((nh-H)*(.44+.1*math.sin(math.pi*local)));im=im.crop((cx,cy,cx+W,cy+H))
 if sh['whip_in'] and local<.08:im=im.filter(ImageFilter.GaussianBlur((int(18*(1-local/.08)),0)))
 if sh['whip_out'] and local>.92:im=im.filter(ImageFilter.GaussianBlur((int(18*(local-.92)/.08),0)))
 return im

def render_contact(events,path):
 cw,ch,lh,cols=480,270,30,4;sheet=Image.new('RGB',(cw*cols,6*(ch+lh)),(10,10,14));d=ImageDraw.Draw(sheet)
 for i,sh in enumerate(base.SHOTS):
  t=(sh['start']+sh['end'])/2;im=scene_frame(sh,.5,t,events).resize((cw,ch),Image.Resampling.LANCZOS);x=(i%cols)*cw;y=(i//cols)*(ch+lh);sheet.paste(im,(x,y));d.rectangle((x,y+ch,x+cw,y+ch+lh),fill=(10,10,14));d.text((x+8,y+6),f"{sh['i']:02} {sh['kind']} / {sh['set']}",font=fnt(17,'kalam'),fill=CREAM)
 sheet.save(path,quality=92)

def render_movie(events):
 ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();out=ROOT/'fake_funeral_27m_scam.mp4';audio=ROOT/'cinema_mix.wav'
 cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r','30','-i','-','-i',str(audio),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-af','loudnorm=I=-14:TP=-1.5:LRA=7','-shortest','-movflags','+faststart',str(out)]
 p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
 try:
  for frame in range(209*30):
   t=frame/30;sh=next((s for s in base.SHOTS if s['start']<=t<s['end']),base.SHOTS[-1]);local=(t-sh['start'])/(sh['end']-sh['start']);im=scene_frame(sh,local,t,events);p.stdin.write(im.tobytes())
   if frame%300==0:print(f"Shot {sh['i']:02}/24 {t:.1f}s",flush=True)
 except BrokenPipeError:raise RuntimeError('FFmpeg pipe closed')
 finally:
  if p.stdin and not p.stdin.closed:p.stdin.close()
 rc=p.wait()
 if rc:raise SystemExit(rc)
 print(f'Wrote {out}, 1920x1080 30fps, 209 seconds')

def main():
 events,activity=base.build_voice_events();base.write_srt(events);base.write_audio(events,activity)
 render_contact(events,ROOT/'qa_contact_sheet.jpg');render_movie(events)
if __name__=='__main__':main()
