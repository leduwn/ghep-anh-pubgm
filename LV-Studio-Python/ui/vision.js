/* Pixel-only border detection and title-level parsing; no image leaves this device. */
(function(root){
function detectBorder(data,w,h){
 // Scan through the last row: the selected tile can sit against the bottom edge.
 const left=Math.floor(w*.55),right=Math.min(w-1,Math.floor(w*.995)),top=Math.floor(h*.045),bottom=h;
 const mask=new Uint8Array(w*h);
 for(let y=top;y<bottom;y++)for(let x=left;x<right;x++){
  const i=(y*w+x)*4,r=data[i],g=data[i+1],b=data[i+2];
  // Include amber and reddish-orange outlines, including dim antialiased pixels.
  if(r>90&&g>38&&r-g>23&&g-b>17&&r>g*1.13&&g>b*1.22)mask[y*w+x]=1;
 }
 const runs=[],maxGap=Math.max(2,Math.round(w*.006));
 for(let y=top;y<bottom;y++){
  let first=-1,last=-1,hits=0;
  const flush=()=>{if(first>=0&&last-first>=w*.065&&last-first<=w*.37&&hits/(last-first+1)>.55)runs.push({y,x:first,end:last,hits});first=-1;last=-1;hits=0};
  for(let x=left;x<right;x++){
   if(mask[y*w+x]){if(first<0)first=x;last=x;hits++}
   else if(first>=0&&x-last>maxGap)flush();
  }flush();
 }
 const vertical=(x,y1,y2)=>{let hits=0;for(let y=y1;y<=y2;y++)for(let dx=-3;dx<=3;dx++)if(mask[y*w+x+dx]){hits++;break}return hits/(y2-y1+1)};
 let best=null;
 for(let i=0;i<runs.length;i++)for(let j=i+1;j<runs.length;j++){
  const a=runs[i],b=runs[j],height=b.y-a.y,width=((a.end-a.x)+(b.end-b.x))/2;
  if(height<width*.26||height>width*.78||Math.abs(a.x-b.x)>9||Math.abs(a.end-b.end)>9)continue;
  const x=Math.round((a.x+b.x)/2),end=Math.round((a.end+b.end)/2);
  const vl=vertical(x,a.y,b.y),vr=vertical(end,a.y,b.y);
  if(Math.min(vl,vr)<.35||(vl+vr)/2<.52)continue;
  const horizontal=(a.hits/(a.end-a.x+1)+b.hits/(b.end-b.x+1))/2;
  const score=horizontal*.4+(vl+vr)*.3;
  if(score<.66)continue;
  // Prefer the outside of thick borders when edge evidence is otherwise equal.
  const rank=score+Math.min(width*height/(w*h),.12)*.1;
  if(!best||rank>best.rank)best={rank,x,end,y:a.y,bottom:b.y};
 }
 if(!best)return null;
 const inset=Math.max(2,Math.round(w*.002));
 return {x:(best.x+inset)/w,y:(best.y+inset)/h,w:(best.end-best.x-2*inset)/w,h:(best.bottom-best.y-2*inset)/h};
}
function detectRectangularBadge(data,w,h){
 const left=Math.floor(w*.45),right=Math.floor(w*.765),top=Math.floor(h*.065),bottom=Math.floor(h*.23),mask=new Uint8Array(w*h),runs=[];
 for(let y=top;y<bottom;y++)for(let x=left;x<right;x++){const i=(y*w+x)*4,lo=Math.min(data[i],data[i+1],data[i+2]),hi=Math.max(data[i],data[i+1],data[i+2]);if(lo>125&&hi>185&&hi-lo<105)mask[y*w+x]=1;}
 for(let y=top;y<bottom;y++){let start=-1,last=-1,hits=0;const flush=()=>{if(start>=0&&last-start>w*.065&&last-start<w*.22&&hits/(last-start+1)>.8)runs.push({x:start,end:last,y});start=-1;hits=0;};for(let x=left;x<right;x++){if(mask[y*w+x]){if(start<0)start=x;last=x;hits++;}else if(start>=0&&x-last>3)flush();}flush();}
 const vertical=(x,y0,y1)=>{let hits=0;for(let y=y0;y<=y1;y++)for(let dx=-2;dx<=2;dx++)if(mask[y*w+x+dx]){hits++;break}return hits/(y1-y0+1)};
 let best=null;for(let i=0;i<runs.length;i++)for(let j=i+1;j<runs.length;j++){const a=runs[i],b=runs[j],bw=a.end-a.x,bh=b.y-a.y;if(bh<bw*.12||bh>bw*.3||Math.abs(a.x-b.x)>4||Math.abs(a.end-b.end)>4)continue;const vl=vertical(a.x,a.y,b.y),vr=vertical(a.end,a.y,b.y);if(Math.min(vl,vr)<.8)continue;const score=vl+vr+bw*bh/(w*h);if(!best||score>best.score)best={score,x:a.x,end:a.end,y:a.y,bottom:b.y};}
 if(!best)return null;return {x:Math.max(0,best.x-1)/w,y:Math.max(0,best.y-1)/h,w:(best.end-best.x+3)/w,h:(best.bottom-best.y+3)/h};
}
function detectBadge(data,w,h){
 const numericAnchor=()=>{
  const left=Math.floor(w*.65),right=Math.floor(w*.753),top=Math.floor(h*.089),bottom=Math.floor(h*.114),groups=[];let run=null;
  const flush=()=>{if(run&&run.x1-run.x0>=2&&run.x1-run.x0<w*.023&&run.y1-run.y0>h*.012)groups.push(run);run=null;};
  for(let x=left;x<right;x++){let count=0,y0=bottom,y1=top;for(let y=top;y<bottom;y++){const i=(y*w+x)*4,lo=Math.min(data[i],data[i+1],data[i+2]),hi=Math.max(data[i],data[i+1],data[i+2]);if(lo>130&&hi-lo<90){count++;y0=Math.min(y0,y);y1=Math.max(y1,y);}}if(count>=2){if(!run)run={x0:x,x1:x+1,y0,y1:y1+1};else{run.x1=x+1;run.y0=Math.min(run.y0,y0);run.y1=Math.max(run.y1,y1+1);}}else flush();}flush();
  if(groups.length<3||groups.length>7)return null;const ys=groups.map(g=>g.y0).sort((a,b)=>a-b),baseline=ys[Math.floor(ys.length/2)];for(let i=groups.length-1;i>=0;i--)if(Math.abs(groups[i].y0-baseline)>h*.0025)groups.splice(i,1);if(groups.length<3)return null;const y0=Math.min(...groups.map(g=>g.y0)),y1=Math.max(...groups.map(g=>g.y1));
  if(groups.at(-1).x1<w*.72||y1-y0>h*.035||groups.some(g=>Math.abs(g.y0-y0)>h*.009||Math.abs(g.y1-y1)>h*.009))return null;
  const x0=Math.min(groups[0].x0-w*.05,w*.612),x1=Math.min(w*.757,groups.at(-1).x1+w*.013),a=Math.max(h*.069,y0-h*.014),b=Math.min(h*.145,y1+h*.012);
  return {x:x0/w,y:a/h,w:(x1-x0)/w,h:(b-a)/h};
 };
 // Group contrasting pixels in the known region; no frame color or straight edges required.
 const left=Math.floor(w*.54),right=Math.floor(w*.763),top=Math.floor(h*.066),bottom=Math.floor(h*.18),rw=right-left,rh=bottom-top,mask=new Uint8Array(rw*rh),seen=new Uint8Array(rw*rh);
 const channel=(x,y,c)=>data[(y*w+x)*4+c];
 for(let y=top;y<bottom;y++)for(let x=left;x<right;x++){
  let contrast=0,peak=0;for(let c=0;c<3;c++){const v=channel(x,y,c);peak=Math.max(peak,v);const around=[channel(Math.max(left,x-5),y,c),channel(Math.min(right-1,x+5),y,c),channel(x,Math.max(top,y-5),c),channel(x,Math.min(bottom-1,y+5),c)].sort((a,b)=>a-b);contrast=Math.max(contrast,Math.abs(v-(around[1]+around[2])/2));}
  if(peak>95&&contrast>32)mask[(y-top)*rw+x-left]=1;
 }
 const digits=box=>{
  const bw=box.x1-box.x0,bh=box.y1-box.y0,x0=Math.round(box.x0+bw*.25),x1=Math.round(box.x1-bw*.03),y0=Math.round(box.y0+bh*.2),y1=Math.round(box.y1-bh*.2);let groups=0,run=0;
  const flush=()=>{if(run>=2&&run<bw*.18)groups++;run=0;};
  for(let x=x0;x<x1;x++){let count=0;for(let y=y0;y<y1;y++){const i=(y*w+x)*4,lo=Math.min(data[i],data[i+1],data[i+2]),hi=Math.max(data[i],data[i+1],data[i+2]);if(lo>130&&hi-lo<95)count++;}if(count>=2)run++;else flush();}flush();return groups>=3;
 };
 let best=null;const radius=Math.max(2,Math.round(w*.002)),components=[];
 for(let i=0;i<mask.length;i++){if(!mask[i]||seen[i])continue;const queue=[i];seen[i]=1;let x0=rw,y0=rh,x1=0,y1=0;
  for(let k=0;k<queue.length;k++){const p=queue[k],x=p%rw,y=Math.floor(p/rw);x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);for(let dy=-radius;dy<=radius;dy++)for(let dx=-radius;dx<=radius;dx++){const nx=x+dx,ny=y+dy;if(nx<0||nx>=rw||ny<0||ny>=rh)continue;const n=ny*rw+nx;if(mask[n]&&!seen[n]){seen[n]=1;queue.push(n);}}}
  if(y1-y0>=h*.008)components.push({x0:x0+left,y0:y0+top,x1:x1+left+1,y1:y1+top+1});
 }
 // Join nearby pieces of broken outlines and separately drawn digits.
 for(let i=0;i<components.length;i++)for(let j=i+1;j<components.length;j++){
  const a=components[i],b=components[j],overlap=Math.min(a.y1,b.y1)-Math.max(a.y0,b.y0),gap=Math.max(a.x0-b.x1,b.x0-a.x1,0),x0=Math.min(a.x0,b.x0),x1=Math.max(a.x1,b.x1),y0=Math.min(a.y0,b.y0),y1=Math.max(a.y1,b.y1);
  if(overlap>Math.min(a.y1-a.y0,b.y1-b.y0)*.45&&gap<w*.018&&x1-x0<w*.215&&y1-y0<h*.08){components[i]={x0,x1,y0,y1};components.splice(j,1);j=i;}
 }
 for(const box of components){const bw=box.x1-box.x0,bh=box.y1-box.y0;if(bw<w*.065||bw>w*.215||bh<h*.015||bh>h*.08||bw/bh<2.4||bw/bh>8||box.x1<w*.7||!digits(box))continue;
  const score=bw*bh;if(!best||score>best.score)best={...box,score};
 }
 // The straight-frame path is retained, with numeric evidence to reject empty scenery strips.
 if(!best){const rect=detectRectangularBadge(data,w,h);if(rect){const box={x0:Math.round(rect.x*w),y0:Math.round(rect.y*h),x1:Math.round((rect.x+rect.w)*w),y1:Math.round((rect.y+rect.h)*h)};if(digits(box))return rect;}return numericAnchor();}
 const pad=Math.max(1,Math.round(w*.001));return {x:(best.x0-pad)/w,y:(best.y0-pad)/h,w:(best.x1-best.x0+pad*2)/w,h:(best.y1-best.y0+pad*2)/h};
}
const romans=['','I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII','XIII','XIV','XV','XVI','XVII','XVIII','XIX','XX'];
function parseLevel(text){
 const t=text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
 const confused=t.match(/\b(?:Cap|Level|Lv)\s*[:.\-]?\s*([G|Il])\s*[).,;]*\s*$/i);if(confused)return /G/i.test(confused[1])?6:1;
 let m=t.match(/(?:\bC[aâ]p|\bLevel|\bLv)\s*[:.\-]?\s*(\d{1,2})(?!\d)/i)||t.match(/\(\s*[^()\d]{1,8}\s*(\d{1,2})\s*\)/);
 if(m){const lv=Number(m[1]);if(lv>=1&&lv<=99)return lv;}
 // Only an isolated Roman token at the end of the title or in parentheses.
 // l/1/| are common OCR substitutions for the Roman I.
 m=t.match(/(?:^|[\s(\[\-–:])([IVXil1|]{1,8})\s*[)\].,;]*\s*$/i);
 if(!m)return null;
 const token=m[1].replace(/[il1|]/g,'I').toUpperCase();
 const lv=romans.indexOf(token);
 return lv>0?lv:null;
}
const digitTemplates={"8":"00111111111111111100011111111111111111100111111111111111111011111111111111111111111111111111111111111111111000000011111111111100000000111111111111000000001111111111110000000011111111111100000000111111111111000000001111111111110000000011111111111100000000111111111111000000001111111111110000000011111111111110000001111110011111111001111111100011111111111111110000011111111111111000000011111111111100000001111111111111100000111111111111111100011111111001111111101111111000000111111111111110000000111111111111000000001111111111110000000011111111111100000000111111111111000000001111111111110000000011111111111100000000111111111111000000001111111111110000000011111111111100000000111111111111000000001111111111111000000111111111111111111111111111111111111111111111110111111111111111111001111111111111111110","7": "01111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111101111110000000111111011111100000001111110111111000000011111101111110000000111111011111100000011111100111111000000111111000000000000001111110000000000000011111100000000000000111110000000000000011111100000000000000111111000000000000001111110000000000000011111100000000000001111110000000000000011111100000000000001111111000000000000011111110000000000000111111000000000000001111110000000000000011111000000000000001111110000000000000011111100000000000000111111000000000000001111110000000000000111111000000000000001111110000000000000011111100000000000000111111000000000000011111100000000000000111111000000000000001111110000000000000011111100000000000000111111000000000000011111100000000000000111111000000000", "6": "00111111111111111100011111111111111111101111111111111111111011111111111111111110111111111111111111101111110000000011111011111100000000111110111111000000001111101111110000000011111011111100000000111110111111000000001111101111110000000011111011111100000000000000111111000000000000001111110000000000000011111100000000000000111111000000000000001111111111111111100011111111111111111110111111111111111111101111111111111111111011111111111111111111111111000000001111111111110000000011111111111100000000111111111111000000001111111111110000000011111111111100000000111111111111000000001111111111110000000011111111111100000000111111111111000000001111111111110000000011111111111100000000111111111111000000001111111111110000000011111111111111111111111111111111111111111111100111111111111111111000111111111111111100", "2": "00111111111111111100011111111111111111100111111111111111111101111111111111111111011111111111111111110111110000000011111101111100000000111111011111000000001111110111110000000011111101111100000000111111011111000000001111110111110000000011111100000000000000111111000000000000011111100000000000000111111000000000000011111110000000000001111111000000000000011111110000000000001111111000000000000011111110000000000000111111000000000000011111100000000000001111111000000000000111111100000000000001111110000000000000011111100000000000001111111000000000000111111100000000000001111110000000000000111111000000000000001111110000000000000111111100000000000011111110000000000000111111000000000000011111100000000000000111111100000000000011111111111111111111111111111111111111111111111111111111111111111111111111111111"};
function classifyDigit(data,w,h,orange=false){
 let x0=w,y0=h,x1=-1,y1=-1;const mask=new Uint8Array(w*h);
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){const i=(y*w+x)*4,r=data[i],g=data[i+1],b=data[i+2];const ink=orange?(r>110&&g>45&&r>g*1.2&&g>b*1.3):Math.min(r,g,b)>150;if(ink){mask[y*w+x]=1;x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y)}}
 if(x1<0||y1-y0<5)return null;
 const bits=[];for(let y=0;y<40;y++)for(let x=0;x<20;x++){const sx=x0+Math.min(x1-x0,Math.floor((x+.5)*(x1-x0+1)/20)),sy=y0+Math.min(y1-y0,Math.floor((y+.5)*(y1-y0+1)/40));bits.push(mask[sy*w+sx])}
 const scores=Object.entries(digitTemplates).map(([lv,t])=>({lv:Number(lv),distance:bits.reduce((n,v,i)=>n+Math.abs(v-Number(t[i])),0)/800})).sort((a,b)=>a.distance-b.distance);
 return scores[0].distance<.105&&scores[1].distance-scores[0].distance>.1?{lv:scores[0].lv,confidence:Math.round((1-scores[0].distance)*100)}:null;
}
function levelGlyphBox(blocks){
 const words=[];for(const b of blocks||[])for(const p of b.paragraphs||[])for(const l of p.lines||[])words.push(...(l.words||[]));
 for(let i=0;i<words.length-1;i++){const marker=words[i].text.normalize('NFD').replace(/[\u0300-\u036f]/g,'');if(!/^(?:\(?Cap|Level|Lv)$/i.test(marker))continue;const next=words[i+1];if(!/^[BGSOIl0-9][).,:;]*$/.test(next.text))continue;const symbol=(next.symbols||[]).find(s=>s.text!==')');if(symbol)return symbol.bbox}
 return null;
}
function parseResearchLevel(text){
 const m=String(text||'').match(/(?:^|[^\dA-Za-z])([0-9]{1,2}|[Il|V])\s*\/\s*(\d{1,2})(?!\d)/);
 if(!m)return null;
 const current=/^[Il|V]$/.test(m[1])?1:Number(m[1]),maximum=Number(m[2]);
 if(current<1||maximum<1||current>maximum||maximum>20)return null;
 return {lv:maximum===3&&current===3?4:current,current,maximum,source:'research'};
}
function selectResearchLevel(readings){
 if(!readings.length)return null;
 const groups=new Map();
 for(const r of readings){const key=r.current+'/'+r.maximum;const group=groups.get(key)||[];group.push(r);groups.set(key,group)}
 const ranked=[...groups.values()].sort((a,b)=>b.length-a.length);
 const best=ranked[0];
 if(best.length<2||!best.some(r=>r.confidence>=55)||(ranked[1]&&ranked[1].length===best.length))return {lv:null,source:'research',readings,reviewReason:'Chưa xác nhận được tiến độ nghiên cứu; hãy kiểm tra ảnh gốc.'};
 return {...best.reduce((a,b)=>a.confidence>=b.confidence?a:b),confirmed:true};
}
function selectTitleLevel(readings){
 const valid=readings.filter(r=>Number.isInteger(r.lv)&&r.lv>=1&&r.lv<=20&&r.confidence>=45);
 if(!valid.length)return null;
 const groups=new Map();for(const r of valid){const group=groups.get(r.lv)||[];group.push(r);groups.set(r.lv,group)}
 const ranked=[...groups.values()].sort((a,b)=>b.length-a.length),best=ranked[0];
 if(best.length<2||!best.some(r=>r.confidence>=65)||(ranked[1]&&ranked[1].some(r=>r.confidence>=65)))return {lv:null,reviewReason:'Các lần đọc tiêu đề chưa đủ rõ hoặc không khớp; hãy kiểm tra ảnh gốc.'};
 return {lv:best[0].lv,current:best[0].lv,source:'title',confirmed:true,confidence:Math.max(...best.map(r=>r.confidence))};
}
function parseProgress(text,shape){const m=text.match(/(\d{1,2})\s*\/\s*(\d{1,2})/);if(!m)return null;const max=Number(m[2]),lv=shape?.lv;if(lv&&lv<=max&&max<=20)return {...shape,source:'progress'};return null;}
const weaponPatterns=[['M416',/M4[1IL|][6GE]/],['AUG',/AUG/],['UMP',/UMP(?:45|9)?/],['AKM',/AKM/],['SCAR-L',/SCAR-?L/],['M762',/M762/],['M16A4',/M16A4/],['ACE32',/ACE32/],['G36C',/G36C/],['QBZ',/QBZ/],['FAMAS',/FAMAS/],['GROZA',/GROZA/],['P90',/P90/],['VECTOR',/VECTOR/],['UZI',/UZI/],['PP19',/PP-?19|BIZON/],['MP5K',/MP5K/],['TOMMY GUN',/TOMMY(?:GUN)?|THOMPSON/],['M249',/M249/],['DP28',/DP-?28/],['MG3',/MG3/],['AWM',/AWM/],['AMR',/AMR/],['M24',/M24/],['KAR98K',/KAR98K/],['MINI14',/MINI14/],['SKS',/SKS/],['SLR',/SLR/],['MK14',/MK14/],['MK12',/MK12/],['VSS',/VSS/],['QBU',/QBU/],['DBS',/DBS/],['S12K',/S12K/],['S686',/S686/],['S1897',/S1897/],['NS2000',/NS2000/],['M1014',/M1014/]];
function parseWeapon(text){
 const t=String(text||'').toUpperCase().replace(/\s+/g,'');
 // The narrow title font can turn M416 into MAIE (4→A, 1→I, 6→E).
 if(/M[4A][1IL|][6GE]/.test(t))return 'M416';
 return weaponPatterns.find(([name,pattern])=>pattern.test(t))?.[0]||null;
}
function weaponGlyphBox(blocks){
 const words=[];for(const b of blocks||[])for(const p of b.paragraphs||[])for(const l of p.lines||[])words.push(...(l.words||[]));
 let index=words.findIndex(w=>/^\(?Cap$/i.test(w.text.normalize('NFD').replace(/[\u0300-\u036f]/g,'')));
 if(index>0)return words[index-1].bbox;
 index=words.map(w=>w.text).lastIndexOf('-');if(index>=0&&words[index+1])return words[index+1].bbox;return null;
}
function weaponPixelBox(data,w,h){
 // Locate the title separator and the next word using white pixels, independently of OCR.
 const white=(x,y)=>{const i=(y*w+x)*4;return Math.min(data[i],data[i+1],data[i+2])>170};
 const gap=Math.max(3,Math.round(h*.125)),runs=[];let start=-1,last=-1;
 for(let x=0;x<w;x++){let count=0;for(let y=0;y<h;y++)if(white(x,y))count++;
  if(count>=2){if(start<0)start=x;last=x;}else if(start>=0&&x-last>gap){runs.push([start,last]);start=-1;}
 }if(start>=0)runs.push([start,last]);
 const boxes=runs.map(([x0,x1])=>{let y0=h,y1=-1;for(let y=0;y<h;y++)for(let x=x0;x<=x1;x++)if(white(x,y)){y0=Math.min(y0,y);y1=Math.max(y1,y)}return {x0,x1:x1+1,y0,y1:y1+1}});
 for(let i=0;i<boxes.length-1;i++){const b=boxes[i],n=boxes[i+1],bh=b.y1-b.y0,nh=n.y1-n.y0;
  if(b.x1-b.x0>bh*2&&bh<h*.22&&nh>h*.4&&n.x1-n.x0>h*.35)return n;
 }return null;
}
function compareEntries(a,b){const ranks={M416:0,AUG:1,UMP:2,AKM:3};return (Number(b.lv)||0)-(Number(a.lv)||0)||(ranks[parseWeapon(a.weapon)]??4)-(ranks[parseWeapon(b.weapon)]??4)||a.order-b.order;}
root.WeaponVision={parseResearchLevel,selectResearchLevel,selectTitleLevel,detectBorder,detectBadge,parseLevel,classifyDigit,levelGlyphBox,parseProgress,parseWeapon,compareEntries,weaponGlyphBox,weaponPixelBox,weaponNames:weaponPatterns.map(([name])=>name)};
})(typeof module==='object'?module.exports:globalThis);
