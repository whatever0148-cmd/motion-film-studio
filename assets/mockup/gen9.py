# 9:16 (1080x1920) version: the 16:9 film plays inside the real laptop screen; the screen is the focus, the surround is graded down and softened by masks
import json, re, sys
import os
P=json.load(open('params.json')) if os.path.exists('params.json') else {}   # optional: dur, punch (beat times that get a camera thump), ty (screen centre y)
c=json.load(open('corners.json')); DUR=P.get('dur',38.6); W,H=c['W'],c['H']
OW,OH=1080,1920
PADX,PADT,PADB=60,420,140
PW,PH=W+2*PADX,H+PADT+PADB
cx=(c['tl'][0]+c['tr'][0]+c['br'][0]+c['bl'][0])/4+PADX; cy=(c['tl'][1]+c['tr'][1]+c['br'][1]+c['bl'][1])/4+PADT
TX,TY=540,P.get('ty',650)                                   # where the screen centre sits in the frame
S0,S1=0.78,0.855
x='(t/%s)'%DUR; E='(%s*%s*(3-2*%s))'%(x,x,x)
PUNCH="+".join("gte(t,%s)*exp(-9*(t-%s))"%(p,p) for p in P.get('punch',[]) ) or '0'   # a small camera thump on the beats that carry the long gaps
S="((%.4f+%.4f*%s)*(1+0.18*pow(1-min(t/0.8,1),2)+0.035*(%s)))"%(S0,S1-S0,E,PUNCH)
DX="(4*sin(0.9*t)+2*sin(2.3*t+1))"; DY="(4*sin(0.7*t+2)+2*sin(1.9*t))"
def Tn(e): return re.sub(r"(?<![a-z])t(?![a-z(])","(in/60)",e)
fx=lambda px:"((%.2f-%.2f)*%s+%d+%s)"%(px+PADX,cx,S,TX,DX)
fy=lambda py:"((%.2f-%.2f)*%s+%d+%s)"%(py+PADT,cy,S,TY,DY)
q=lambda k:c[k]
persp="perspective=sense=destination:eval=frame:interpolation=cubic:x0='%s':y0='%s':x1='%s':y1='%s':x2='%s':y2='%s':x3='%s':y3='%s'"%tuple(Tn(v) for v in (fx(q('tl')[0]),fy(q('tl')[1]),fx(q('tr')[0]),fy(q('tr')[1]),fx(q('bl')[0]),fy(q('bl')[1]),fx(q('br')[0]),fy(q('br')[1])))
cam="scale=w='%d*%s':h='%d*%s':eval=frame:flags=bicubic,crop=%d:%d:x='(%.2f*%s-%d-%s)':y='(%.2f*%s-%d-%s)'"%(PW,S,PH,S,OW,OH,cx,S,TX,DX,cy,S,TY,DY)
g=[]
# plate: blurred stretched pad behind, the sharp photo feathered over it
g.append("[0:v]format=rgb24,split[pp1][pp2];[pp1]scale=%d:%d,gblur=sigma=45,format=rgba[ppb];[pp2]format=yuva444p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='255*min(1,min(X,%d-X)/120)*min(1,Y/300)*min(1,(%d-Y)/100)',format=rgba[pps];[ppb][pps]overlay=%d:%d,format=rgb24,%s[plate]"%(PW,PH,W-1,H-1,PADX,PADT,cam))
g.append("[1:v]format=rgb24,pad=%d:%d:%d:%d,%s,split[auxa][auxb]"%(PW,PH,PADX,PADT,cam))
g.append("[auxa]format=gbrp,extractplanes=r,split[matte][mneg0];[auxb]format=gbrp,extractplanes=g,format=gbrp[glare]")
# film into the screen quad: 16:9 film inside the 16:10 panel, black bars like a real full-screen player
g.append("[2:v]fps=60,scale=1920:1080,pad=1920:1200:0:60:black,format=gbrp,%s,crop=%d:1200:0:0,pad=%d:%d:0:0,format=rgb24,curves=all='0/0 0.5/0.49 0.85/0.80 1/0.93',format=yuv444p,hue=s=1.12,format=rgb24,split[film][filmb]"%(persp,OW,OW,OH))
g.append("[filmb]gblur=sigma=60,format=yuv444p,hue=s=1.9,format=rgb24[spl]")
# surround: darker, cooler, less saturated, vignette; softened away from the screen by a mask (shallow depth of field)
g.append("[plate]split[pa][pb]")
g.append("[pa]format=rgb24,curves=all='0/0 0.25/0.17 0.5/0.40 0.75/0.67 1/0.92':b='0/0.01 0.5/0.43 1/0.96',format=yuv444p,hue=s=0.8,vignette=angle=PI/3.3:eval=init,format=rgb24[sa]")
g.append("[pb]format=rgb24,gblur=sigma=7,curves=all='0/0 0.25/0.15 0.5/0.36 0.75/0.62 1/0.84':b='0/0.01 0.5/0.39 1/0.90',format=yuv444p,hue=s=0.72,vignette=angle=PI/3.3:eval=init,format=rgb24[sb]")
g.append("[mneg0]negate,gblur=sigma=90,curves=all='0/0 0.15/0.0 0.7/1 1/1'[m2]")
g.append("[sa]format=gbrp[sag];[sb]format=gbrp[sbg];[sag][sbg][m2]maskedmerge,format=rgb24[surr]")
# the screen's own light on the body: tinted, low, only near the screen
g.append("[surr][spl]blend=all_mode=screen:all_opacity=0.10[b1]")
g.append("[b1]format=gbrp[b1g];[film]format=gbrp[fg];[b1g][fg][matte]maskedmerge,format=rgb24[b3]")
g.append("[b3]format=gbrp[b3g];[glare]format=gbrp[gg];[b3g][gg]blend=all_mode=screen:all_opacity=0.35,format=rgb24,noise=alls=4:allf=t,format=yuv420p[v]")
open('graph9.txt','w').write(';\n'.join(g))
