# plate prep: chroma matte of the screen, 4 corners, despill, glare map. numpy + PIL-free (ffmpeg does the decode/encode).
import numpy as np, subprocess, json, sys
import shutil,re,os
FF=shutil.which('ffmpeg') or os.path.expanduser('~/.local/bin/ffmpeg')
SRC=sys.argv[1] if len(sys.argv)>1 else 'plate_src.jpg'   # usage: python prep.py plate.jpg  (run inside the mockup work folder)
def load(p,w,h): return np.frombuffer(subprocess.run([FF,'-v','error','-i',p,'-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True).stdout,np.uint8).reshape(h,w,3).astype(np.float32)
def save(a,p,pix):
    a=np.clip(a,0,255).astype(np.uint8); h,w=a.shape[:2]
    subprocess.run([FF,'-v','error','-y','-f','rawvideo','-pix_fmt',pix,'-s',f'{w}x{h}','-i','-',p],input=a.tobytes(),check=True)
_i=subprocess.run([FF,'-hide_banner','-i',SRC],capture_output=True,text=True).stderr
W,H=[int(v) for v in re.search(r', (\d{2,5})x(\d{2,5})',_i).groups()]
im=load(SRC,W,H); r,g,b=im[...,0],im[...,1],im[...,2]
green=(g>1.35*np.maximum(r,b))&(g>110)
ys,xs=np.nonzero(green); print('green px',green.sum(), xs.min(),xs.max(),ys.min(),ys.max())
# keep only the big screen blob: restrict to rows/cols with many green pixels
rows=green.sum(1); cols=green.sum(0)
keep=green.copy(); keep[rows<60,:]=False; keep[:,cols<60]=False
ys,xs=np.nonzero(keep)
P=np.stack([xs,ys],1).astype(np.float32)
tl=P[np.argmin(P[:,0]+P[:,1])]; br=P[np.argmax(P[:,0]+P[:,1])]; tr=P[np.argmax(P[:,0]-P[:,1])]; bl=P[np.argmin(P[:,0]-P[:,1])]
print('corners',tl,tr,br,bl)
json.dump({'tl':tl.tolist(),'tr':tr.tolist(),'br':br.tolist(),'bl':bl.tolist(),'W':W,'H':H},open('corners.json','w'))
# quad matte (convex), feathered
yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
def edge(a,b_):  # signed distance (px) to the edge a->b, positive inside for clockwise order in image coords
    ex,ey=b_[0]-a[0],b_[1]-a[1]; L=np.hypot(ex,ey); return ((xx-a[0])*ey-(yy-a[1])*ex)/L*-1
d=np.min(np.stack([edge(tl,tr),edge(tr,br),edge(br,bl),edge(bl,tl)]),0)
d=-d if d.max()<0 else d
matte=np.clip((d-3)/2.0+0.5,0,1)   # inset 3 px (rounded screen corners, bezel) and about 2 px feather
save(matte*255,'matte.png','gray')
# despill: green never above the larger of red and blue (only green-dominant pixels change)
gd=np.minimum(g,np.maximum(r,b)*1.02)
gd=gd*0.86   # the green screen lit the whole scene green: pull the cast back
clean=np.stack([r,gd,b],-1)
# inside the screen keep the plate untouched for glare extraction
glare=np.clip((np.minimum(r,b)-45)/150,0,1)*(matte>0.5)
glare=glare*(matte>0.5)
save(clean,'plate_clean.png','rgb24'); save(np.stack([matte*255,glare*255,np.zeros_like(matte)],-1),'aux.png','rgb24'); save(glare*255,'glare.png','gray')
print('ok',float(matte.mean()),float(glare.max()))
