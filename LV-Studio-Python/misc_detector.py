"""Locate complete inventory tiles by their rectangular grid; no fixed screen ROI."""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

_TEMPLATE = None

def lock_score(tile):
    global _TEMPLATE
    if _TEMPLATE is None:
        _TEMPLATE = np.asarray(Image.open(Path(__file__).parent / 'ui/assets/misc-lock-mask.png').convert('L')) > 127
    image = np.asarray(tile.resize((160,160)).convert('RGB'))
    corner = image[:52,100:159]
    labels, _ = ndimage.label(corner.min(2) > 175)
    score = 0.0
    for i, box in enumerate(ndimage.find_objects(labels)):
        yy,xx = box
        w,h=xx.stop-xx.start,yy.stop-yy.start
        if w < 7 or h < 9 or not .5 < w/h < 1.15:
            continue
        mask = labels[box] == i+1
        scaled = np.asarray(Image.fromarray(mask.astype('uint8')*255).resize((24,28),Image.Resampling.NEAREST)) > 127
        overlap = np.count_nonzero(scaled & _TEMPLATE) / max(1,np.count_nonzero(scaled | _TEMPLATE))
        score = max(score,overlap)
    return float(score)

def has_content(tile):
    pixels=np.asarray(tile.convert('RGB').resize((64,64))).astype('float32')
    detail=np.abs(pixels-ndimage.gaussian_filter(pixels,sigma=(5,5,0)))
    return float(np.mean(detail[10:54,10:54].max(2)>14))>.018

def detect_misc(image):
    image = image.convert('RGB')
    scale = min(1,1600/image.width)
    scan = image.resize((round(image.width*scale),round(image.height*scale)))
    a=np.asarray(scan);h,w=a.shape[:2]
    dark=(a.min(2)<100)&((a.max(2)<150)|((a.max(2).astype('int16')-a.min(2))>40))
    dark=ndimage.binary_closing(dark,structure=np.ones((3,3)))
    dark=ndimage.binary_fill_holes(dark)
    labels,_=ndimage.label(dark)
    candidates=[]
    for i, box in enumerate(ndimage.find_objects(labels)):
        yy,xx=box;x,y=xx.start,yy.start;cw,ch=xx.stop-x,yy.stop-y
        if not w*.035<cw<w*.99 or ch<h*.045 or not .65<cw/ch<1.15:
            continue
        if x<2 or y<2 or x+cw>w-2 or y+ch>h-2:
            continue
        if np.count_nonzero(labels[box]==i+1)/(cw*ch)<.85:
            continue
        candidates.append((x,y,cw,ch))
    # Group aligned inventory rectangles, including a single row of 2 or 3 tiles.
    grids=[]
    for anchor in candidates:
        ax,ay,aw,ah=anchor
        similar=[r for r in candidates if .84<r[2]/aw<1.19 and .84<r[3]/ah<1.19]
        first=sorted([r for r in similar if abs(r[1]-ay)<ah*.08],key=lambda r:r[0])
        for start in range(max(0,len(first)-1)):
            top=first[start:start+min(3,len(first)-start)];
            if len(top)<2:continue
            centers=[r[0]+r[2]/2 for r in top]
            steps=np.diff(centers)
            if not all(aw*.95<v<aw*1.28 for v in steps) or (len(steps)>1 and abs(steps[0]-steps[1])>aw*.08):
                continue
            selected=[]
            for r in similar:
                center=r[0]+r[2]/2
                col=int(np.argmin(np.abs(np.array(centers)-center)))
                if abs(center-centers[col])>aw*.08 or r[1]<ay-ah*.08:
                    continue
                selected.append((r,col))
            rows=[]
            for r,col in sorted(selected,key=lambda v:v[0][1]):
                row=next((row for row in rows if abs(row[0][0][1]-r[1])<ah*.08),None)
                if row is None:rows.append([(r,col)])
                else:row.append((r,col))
            if len(rows)>1 and not ah*.95<rows[1][0][0][1]-rows[0][0][0][1]<ah*1.28:
                continue
            ordered=[r for row in rows for r,col in sorted(row,key=lambda v:v[1])]
            grids.append((len(ordered),-ay,ordered))
    if not grids:
        singles=[r for r in candidates if r[2]*r[3]>w*h*.55]
        if singles:
            r=max(singles,key=lambda r:r[2]*r[3]);grids.append((1,-r[1],[r]))
    if not grids:
        return {'detected':False,'rects':[],'locked':0,'message':'Chưa xác định được lưới ô. Giữ nguyên ảnh để kiểm tra.'}
    ordered=max(grids,key=lambda g:(g[0],g[1]))[2]
    output=[];locked=0;partial=0
    median_w=float(np.median([r[2] for r in ordered]));median_h=float(np.percentile([r[3] for r in ordered],65))
    for x,y,cw,ch in ordered:
        if cw<median_w*.97-1 or ch<median_h*.97-1:
            partial+=1
            continue
        trim_x=max(0,(cw-median_w)/2);trim_y=max(0,(ch-median_h)/2)
        x+=trim_x;y+=trim_y;cw-=trim_x*2;ch-=trim_y*2
        rect=(round(x/scale),round(y/scale),round((x+cw)/scale),round((y+ch)/scale))
        tile=image.crop(rect)
        if lock_score(tile) >= .65:
            locked+=1
            continue
        if not has_content(tile):
            continue
        inset=max(2,round(min(cw,ch)*.025/scale))
        output.append([rect[0]+inset,rect[1]+inset,rect[2]-inset,rect[3]-inset])
        if len(output)==6:break
    return {'detected':True,'rects':output,'locked':locked,'partial':partial,'message':f'{len(output)} ô · bỏ {locked} ô khóa · bỏ {partial} ô cụt'}
