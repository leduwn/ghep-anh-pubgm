const $=id=>document.getElementById(id);let entries=[],busy=false,editing,selection,startPoint,editSelections;let lvFont='Impact, Arial Black, sans-serif';let workerPromises=[],modelPromise=null;
function workerCount(){return 2}
function canvas(w,h){const c=document.createElement('canvas');c.width=w;c.height=h;return c}
function imageLoad(src){return new Promise((resolve,reject)=>{let i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(Error('Không đọc được ảnh'));i.src=src})}
function detect(img){const w=Math.min(1280,img.width),h=Math.round(img.height*w/img.width),c=canvas(w,h),ctx=c.getContext('2d');ctx.drawImage(img,0,0,w,h);return WeaponVision.detectBorder(ctx.getImageData(0,0,w,h).data,w,h)}
function detectBadge(img){const w=Math.min(1280,img.width),h=Math.round(img.height*w/img.width),c=canvas(w,h),ctx=c.getContext('2d');ctx.drawImage(img,0,0,w,h);return WeaponVision.detectBadge(ctx.getImageData(0,0,w,h).data,w,h)}
function detectRegions(img){const w=Math.min(1280,img.width),h=Math.round(img.height*w/img.width),c=canvas(w,h),ctx=c.getContext('2d');ctx.drawImage(img,0,0,w,h);const data=ctx.getImageData(0,0,w,h).data;return {rect:WeaponVision.detectBorder(data,w,h),badgeRect:WeaponVision.detectBadge(data,w,h)}}
function drawBadge(ctx,e,x,y,width){
 if(!e.badgeRect)return;const r=e.badgeRect;
 if(!e.badgeCanvas){const c=canvas(Math.round(e.img.width*r.w),Math.round(e.img.height*r.h));c.getContext('2d').drawImage(e.img,e.img.width*r.x,e.img.height*r.y,e.img.width*r.w,e.img.height*r.h,0,0,c.width,c.height);e.badgeCanvas=c;}
 const bw=width*.36,bh=bw*e.badgeCanvas.height/e.badgeCanvas.width;ctx.drawImage(e.badgeCanvas,x+width-bw-width*.02,y+width*.018,bw,bh);
}
function crop(e){
 if(!e.rect)return e.img;
 const r=e.rect,key=[r.x,r.y,r.w,r.h,JSON.stringify(e.badgeRect)].join(':');if(e.cropKey===key&&e.cropCanvas)return e.cropCanvas;
 const x=Math.round(e.img.width*r.x),y=Math.round(e.img.height*r.y),w=Math.max(1,Math.round(e.img.width*(r.x+r.w))-x),h=Math.max(1,Math.round(e.img.height*(r.y+r.h))-y),c=canvas(w,h);c.getContext('2d').drawImage(e.img,x,y,w,h,0,0,w,h);
 e.cropKey=key;e.cropCanvas=c;const thumb=canvas(216,Math.max(1,Math.round(216*c.height/c.width))),tc=thumb.getContext('2d');tc.drawImage(c,0,0,thumb.width,thumb.height);drawBadge(tc,e,0,0,thumb.width);e.thumbnail=thumb.toDataURL('image/jpeg',.85);return c;
}
function runtimeError(error){return String(error?.message||error||'Không rõ nguyên nhân').slice(0,240)}
async function getWorker(){
 for(let attempt=0;attempt<240;attempt++){
  const status=await (await fetch('/api/status')).json();
  if(status.error)throw Error(status.error);
  if(status.ready)return {python:true};
  await new Promise(resolve=>setTimeout(resolve,500));
 }
 throw Error('Bộ đọc LV chưa khởi động xong. Kiểm tra thông báo lỗi bên dưới.');
}
async function readLv(img,entry,force=false){
 const prepared=performance.now(),sourceWidth=img.naturalWidth||img.width,sourceHeight=img.naturalHeight||img.height,scale=Math.min(1,2048/sourceWidth),logicalWidth=Math.max(1,Math.round(sourceWidth*scale)),logicalHeight=Math.max(1,Math.round(sourceHeight*scale));
 const c=canvas(Math.max(1,Math.ceil(logicalWidth*.80)),Math.max(1,Math.ceil(logicalHeight*.20)));
 c.getContext('2d').drawImage(img,0,0,sourceWidth*.80,sourceHeight*.20,0,0,c.width,c.height);
 const body=await new Promise((resolve,reject)=>c.toBlob(blob=>blob?resolve(blob):reject(Error('Không tạo được vùng OCR')),'image/jpeg',.95));
 const response=await fetch('/api/ocr',{method:'POST',headers:{'Content-Type':'image/jpeg','X-LV-Token':window.LV_PYTHON.token,'X-LV-Force':force?'1':'0','X-LV-Logical-Width':String(logicalWidth),'X-LV-Logical-Height':String(logicalHeight)},body});
 const result=await response.json();if(!response.ok){const error=Error(result.error||'Không kết nối được EasyOCR Python.');error.engineUnavailable=!!result.engine_unavailable;throw error}
 result.timings=result.timings||{};result.timings.client_prepare_ms=Math.round((performance.now()-prepared)*100)/100;result.timings.upload_bytes=body.size;result.timings.original_bytes=entry?.file?.size||0;return result;
}
let originalEntry=null,originalZoom=1;
function updateOriginalZoom(){
 const image=$('originalImage'),viewer=$('originalViewport');
 image.style.width=Math.round(Math.max(1,viewer.clientWidth-24)*originalZoom)+'px';
 $('originalZoomLabel').textContent=Math.round(originalZoom*100)+'%';
}
function zoomOriginal(factor){originalZoom=Math.min(8,Math.max(.5,originalZoom*factor));updateOriginalZoom()}
function openOriginal(e){
 originalEntry=e;originalZoom=1;$('originalImage').src=e.img.src;$('originalImage').alt='Ảnh gốc '+e.name;
 $('originalName').textContent=e.name;$('originalLv').value=e.lv??'';$('originalSave').disabled=busy;
 $('originalViewer').showModal();updateOriginalZoom();$('originalViewport').scrollTo(0,0);
}
function initOriginalViewer(){
 $('originalClose').onclick=()=>$('originalViewer').close();
 $('originalZoomIn').onclick=()=>zoomOriginal(1.25);$('originalZoomOut').onclick=()=>zoomOriginal(.8);
 $('originalFit').onclick=()=>{originalZoom=1;updateOriginalZoom();$('originalViewport').scrollTo(0,0)};
 $('originalViewport').addEventListener('wheel',e=>{if(e.ctrlKey){e.preventDefault();zoomOriginal(e.deltaY<0?1.15:1/1.15)}},{passive:false});
 $('originalSave').onclick=()=>{
  const value=Number($('originalLv').value);if(!Number.isInteger(value)||value<1||value>99){$('originalLv').reportValidity();return}
  if(originalEntry){originalEntry.lv=value;originalEntry.ocrError=null;originalEntry.message='Đã điền thủ công';refresh()}
  $('originalViewer').close();
 };
 window.addEventListener('resize',()=>{if($('originalViewer').open)updateOriginalZoom()});
}
function missingWeapon(e){return !e.weapon||(e.weapon==='OTHER'&&!e.weaponManual&&!e.weaponKnown)}
function isLevelFailed(e){return e.attempted&&!e.processing&&(!e.lv||!Number.isFinite(e.lv))}
function isFailed(e){return e.attempted&&!e.processing&&(!e.rect||isLevelFailed(e))}
function entryMessage(e){if(e.processing)return 'Đang đọc…';if(!e.attempted)return 'Chưa xử lý';if(e.ocrError)return (e.rect?'Đã cắt · ':'')+'Chưa đọc được LV: '+e.ocrError;if(!e.rect&&!e.lv)return 'Không thấy viền cam và chưa đọc được cấp';if(!e.rect)return 'Không thấy viền cam · chọn vùng cắt';if(!e.lv)return 'Chưa đọc được cấp · điền LV';if(missingWeapon(e))return e.ocrAttempted?'Đã cắt · LV'+e.lv+' · Khác (không ưu tiên)':'Chưa kiểm tra nhóm súng ưu tiên';return e.message||'Đã cắt · LV'+e.lv}
function populateWeaponSelect(select,e){
 for(const [value,text] of [['','Chưa nhận diện'],...['M416','AUG','UMP','AKM'].map(name=>[name,name]),['OTHER','Khác (không ưu tiên)']]){const opt=document.createElement('option');opt.value=value;opt.textContent=text;select.append(opt)}
 select.value=e.weapon||'';select.onchange=()=>{e.weapon=select.value;e.weaponManual=true;e.message=null;refresh()};
}
function renderErrorPanel(){
 const panel=$('errorSection'),list=$('errorItems');if(!panel||!list)return;
 const failed=entries.filter(isLevelFailed);panel.hidden=!failed.length;$('errorCount').textContent=failed.length+' khẩu';list.replaceChildren();
 for(const e of failed){
  const card=document.createElement('div');card.className='error-item';
  const im=document.createElement('img');im.src=e.img.src;im.alt='Ảnh gốc '+e.name;
  const view=document.createElement('button');view.className='original-thumbnail';view.title='Bấm để phóng to ảnh gốc';view.setAttribute('aria-label','Phóng to ảnh gốc '+e.name);view.append(im);view.onclick=()=>openOriginal(e);
  const info=document.createElement('div'),name=document.createElement('div');name.className='name';name.textContent=e.name;
  const reason=document.createElement('small');reason.className='error-reason';reason.textContent=e.ocrError||entryMessage(e);
  const controls=document.createElement('div');controls.className='item-controls';const lab=document.createElement('label');lab.textContent='LV ';
  const n=document.createElement('input');n.type='number';n.min=1;n.max=99;n.value=e.lv??'';n.disabled=busy;n.placeholder='?';n.setAttribute('aria-label','Điền cấp súng '+e.name);n.onchange=()=>{e.lv=n.value?Math.min(99,Math.max(1,Number(n.value))):null;e.message='Đã điền thủ công';refresh()};lab.append(n);controls.append(lab);
  const gunLabel=document.createElement('label');gunLabel.className='weapon-select';gunLabel.textContent='Loại súng';const gun=document.createElement('select');gun.disabled=busy;gun.setAttribute('aria-label','Chọn loại súng '+e.name);populateWeaponSelect(gun,e);gunLabel.append(gun);
  const actions=document.createElement('div');actions.className='error-actions';const edit=document.createElement('button');edit.className='secondary';edit.textContent='Sửa vùng cắt';edit.disabled=busy;edit.onclick=()=>openEditor(e);actions.append(edit);
  info.append(name,reason,controls,gunLabel,actions);card.append(view,info);list.append(card);
 }
}
function refreshProcessedEntry(e){
 if(!e.view)return;
 const {container,image,level,weapon,status}=e.view;
 if(e.rect){crop(e);image.src=e.thumbnail;}
 level.value=e.lv??'';weapon.value=e.weapon||'';
 status.textContent=entryMessage(e);container.classList.toggle('failed',isFailed(e));
}
function refresh(renderResult=true){
 $('count').textContent=entries.length+' ảnh';$('items').replaceChildren();
 for(const e of entries){
  const div=document.createElement('div');div.className='item'+(isFailed(e)?' failed':'');
  const im=document.createElement('img');if(e.rect)crop(e);im.src=e.rect?e.thumbnail:e.img.src;
  const info=document.createElement('div'),name=document.createElement('div');name.className='name';name.textContent=e.name;
  const ctr=document.createElement('div');ctr.className='item-controls';const lab=document.createElement('label');lab.textContent='LV ';
  const n=document.createElement('input');n.type='number';n.min=1;n.max=99;n.value=e.lv??'';n.disabled=busy;n.setAttribute('aria-label','Cấp súng '+e.name);n.onchange=()=>{e.lv=n.value?Math.min(99,Math.max(1,Number(n.value))):null;e.message=null;refresh()};lab.append(n);
  const edit=document.createElement('button');edit.textContent='Sửa cắt';edit.disabled=busy;edit.onclick=()=>openEditor(e);
  const del=document.createElement('button');del.textContent='×';del.disabled=busy;del.setAttribute('aria-label','Xóa '+e.name);del.onclick=()=>{if(e.url)URL.revokeObjectURL(e.url);entries=entries.filter(v=>v!==e);refresh()};
  ctr.append(lab,edit,del);const status=document.createElement('small');status.textContent=entryMessage(e);
  const gunLabel=document.createElement('label');gunLabel.className='weapon-select';gunLabel.textContent='Loại súng';const gun=document.createElement('select');gun.disabled=busy;gun.setAttribute('aria-label','Loại súng '+e.name);populateWeaponSelect(gun,e);gunLabel.append(gun);
  e.view={container:div,image:im,level:n,weapon:gun,status};
  info.append(name,ctr,gunLabel,status);div.append(im,info);$('items').append(div);
 }
 renderErrorPanel();
 $('process').disabled=busy||!entries.length;$('retry').disabled=busy;$('files').disabled=busy;$('demo').disabled=busy;$('clear').disabled=busy;$('download').disabled=busy||!entries.some(e=>e.rect&&e.lv);$('copy').disabled=$('download').disabled;if(renderResult)compose();
}
function gunColumns(count){const value=$('columns').value;return value==='auto'?(count<10?1:count<=24?2:3):Math.max(1,Number(value)||1);}
function gunOutputWidth(valid,cols,rows,gap){const requested=$('size').value,sourceWidth=valid.length?Math.max(...valid.map(e=>crop(e).width)):400;const width=requested==='auto'?sourceWidth:Number(requested);return Math.max(1,Math.floor(Math.min(width,(5000-(cols-1)*gap)/cols,(5000-(rows-1)*gap)/(rows*.49))));}
function compose(){let valid=entries.filter(e=>e.attempted||e.rect).sort(WeaponVision.compareEntries);let out=$('result');out.hidden=!valid.length;$('empty').hidden=!!valid.length;$('download').disabled=busy||!valid.length;$('copy').disabled=$('download').disabled;$('copyStatus').textContent=''; if(!valid.length){$('dimensions').textContent='PNG · nền gốc · chữ LV trắng';if(!busy&&window.parent!==window)window.parent.LVAccGunChanged?.(gunSnapshot());return}let cols=Math.min(gunColumns(valid.length),valid.length),rows=Math.ceil(valid.length/cols),gap=Number($('gap').value),width=gunOutputWidth(valid,cols,rows,gap),height=Math.max(1,Math.floor(width*.49));out.width=cols*width+(cols-1)*gap;out.height=rows*height+(rows-1)*gap;const ctx=out.getContext('2d');ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='medium';ctx.fillStyle='#100f18';ctx.fillRect(0,0,out.width,out.height);valid.forEach((e,i)=>{const col=Math.floor(i/rows),row=i%rows,x=col*(width+gap),y=row*(height+gap),c=crop(e);ctx.drawImage(c,x,y,width,height);drawBadge(ctx,e,x,y,width);ctx.save();ctx.fillStyle='#fff';ctx.shadowColor='#0008';ctx.shadowBlur=width*.015;ctx.font=`900 ${Math.round(width*.19)}px ${lvFont}`;ctx.textBaseline='alphabetic';ctx.fillText('LV'+(e.lv||'?'),x+width*.018,y+height-width*.018);ctx.restore()});$('dimensions').textContent=`${valid.length} súng · ${out.width} × ${out.height} px · PNG`;if(!busy&&window.parent!==window)window.parent.LVAccGunChanged?.(gunSnapshot());}
async function add(files){const added=[];if(files.length)for(let i=0;i<workerCount();i++)getWorker(i).catch(()=>{});for(const f of files){if(!f.type.startsWith('image/'))continue;if(f.size>20*1024*1024){$('status').textContent='Ảnh '+f.name+' vượt 20 MB.';continue}try{let src=URL.createObjectURL(f),img=await imageLoad(src),entry={name:f.name,file:f,img,order:Date.now()+entries.length,url:src,lv:null,rect:null};entries.push(entry);added.push(entry)}catch{$('status').textContent='Có ảnh không đọc được.'}}refresh();if(added.length){$('status').textContent=`Đã thêm ${added.length} ảnh. Đang tự động cắt và đọc LV…`;await processEntries(added)}}
$('files').onchange=async e=>{await add([...e.target.files]);e.target.value=''};for(const type of ['dragover','dragenter'])$('drop').addEventListener(type,e=>{e.preventDefault();$('drop').classList.add('drag')});$('drop').ondragleave=()=>$('drop').classList.remove('drag');$('drop').ondrop=async e=>{e.preventDefault();$('drop').classList.remove('drag');if(!busy)await add([...e.dataTransfer.files])};$('clear').onclick=()=>{entries.forEach(e=>e.url&&URL.revokeObjectURL(e.url));entries=[];refresh();$('timingPanel').hidden=true;$('status').textContent='Đã xóa ảnh đầu vào.'};$('demo').onclick=async()=>{let img=await imageLoad('sample.jpg');entries.push({name:'Ảnh mẫu · AUG',img,order:Date.now(),lv:null,rect:null});refresh();$('process').click()};async function processEntries(targets,forceNames=false){
 if(busy)return;targets=targets.filter(e=>!e.rect||!e.lv||((forceNames||!e.ocrAttempted)&&missingWeapon(e))||(!e.badgeManual&&e.badgeVersion!==14));if(!targets.length){$('status').textContent='Các ảnh đã được xử lý đầy đủ.';return;}
 busy=true;const started=performance.now();let next=0,completed=0,engineError=null;
 const timings={cropMs:0,waitMs:0,requestMs:0,ocrWallMs:0,renderMs:0,lvMs:0,nameMs:0,decodeMs:0,clientPrepareMs:0,uploadBytes:0,originalBytes:0,cached:0,requests:0};
 $('timingPanel').hidden=true;let phaseStarted=performance.now();refresh(false);timings.renderMs+=performance.now()-phaseStarted;
 const needsOCR=targets.some(e=>!e.lv||((forceNames||!e.ocrAttempted)&&missingWeapon(e)));
 for(const e of targets){e.attempted=true;e.processing=true;e.message=null;e.ocrError=null;}
 // Two local requests form a pipeline: one image can upload/decode while EasyOCR reads the other.
 const boot=needsOCR?Promise.allSettled(Array.from({length:Math.min(workerCount(),targets.length)},(_,i)=>getWorker(i))):Promise.resolve([]);
 try{
  phaseStarted=performance.now();const results=await boot;timings.waitMs+=performance.now()-phaseStarted;
  const workers=results.filter(r=>r.status==='fulfilled').map(r=>r.value);
  if(needsOCR&&!workers.length){engineError=runtimeError(results.find(r=>r.status==='rejected')?.reason);for(const e of targets)if(!e.lv||missingWeapon(e))e.ocrError=engineError;}
  const run=async wk=>{while(next<targets.length){const e=targets[next++];
   try{const cropStarted=performance.now();
    try{if(!e.rect){const regions=detectRegions(e.img);e.rect=regions.rect;if(!e.badgeManual){e.badgeRect=regions.badgeRect;e.badgeVersion=14;e.badgeCanvas=null;}}else if(!e.badgeManual&&e.badgeVersion!==14){e.badgeRect=detectBadge(e.img);e.badgeVersion=14;e.badgeCanvas=null;}}
    catch(error){e.message='Chưa cắt được ảnh: '+runtimeError(error);}
    timings.cropMs+=performance.now()-cropStarted;
    if(engineError){e.ocrError=engineError;}else if(wk&&(!e.lv||((forceNames||!e.ocrAttempted)&&missingWeapon(e)))){const requestStarted=performance.now();let lv;timings.requests++;
    try{lv=await readLv(e.img,e,forceNames);}finally{timings.requestMs+=performance.now()-requestStarted;}
    if(lv?.cached)timings.cached++;timings.lvMs+=Number(lv?.timings?.lv_ms)||0;timings.nameMs+=Number(lv?.timings?.name_ms)||0;timings.decodeMs+=Number(lv?.timings?.decode_ms)||0;timings.clientPrepareMs+=Number(lv?.timings?.client_prepare_ms)||0;timings.uploadBytes+=Number(lv?.timings?.upload_bytes)||0;timings.originalBytes+=Number(lv?.timings?.original_bytes)||0;
    e.ocrAttempted=true;if(lv){if(!e.lv)e.lv=lv.lv;if(lv.reviewReason)e.ocrError=lv.reviewReason;if(!e.weaponManual){e.weapon=lv.weapon;e.weaponKnown=lv.name_known??lv.weapon!=='OTHER';}e.message=lv.confidence<65?'Đã cắt · kiểm tra lại LV':'Đã cắt · LV'+e.lv;}}}
   catch(error){e.ocrError=runtimeError(error);if(error.engineUnavailable)engineError=e.ocrError;e.message='Đã cắt · bộ đọc chữ gặp lỗi';}finally{e.processing=false;}
   completed++;if(window.parent!==window)window.parent.LVAccGunProgress?.(completed,targets.length);$('status').textContent=`Đã cắt và đọc ${completed}/${targets.length} ảnh…`;
   const renderStarted=performance.now();refreshProcessedEntry(e);timings.renderMs+=performance.now()-renderStarted;
   if(completed%8===0)await new Promise(resolve=>setTimeout(resolve,0));
  }};
  const ocrWallStarted=performance.now();await Promise.all((workers.length?workers:[null]).map(run));timings.ocrWallMs+=performance.now()-ocrWallStarted;
 }catch(error){engineError=runtimeError(error);}
 finally{for(const e of targets)e.processing=false;busy=false;const renderStarted=performance.now();refresh();timings.renderMs+=performance.now()-renderStarted;}
 const review=entries.filter(isFailed).length,elapsed=((performance.now()-started)/1000).toFixed(1),cuts=targets.filter(e=>e.rect).length;
 const seconds=value=>(value/1000).toFixed(2)+' giây';
 const megabytes=value=>(value/1048576).toFixed(1)+' MB';
 $('timingDetails').textContent=`Luồng cắt + OCR thực tế: ${seconds(timings.ocrWallMs)}
Tìm vùng cắt và bộ đếm: ${seconds(timings.cropMs)} (chạy xen kẽ OCR)
Chờ bộ đọc sẵn sàng: ${seconds(timings.waitMs)}
Tổng thời gian của 2 luồng yêu cầu: ${seconds(timings.requestMs)}
  Chuẩn bị vùng chữ: ${seconds(timings.clientPrepareMs)} · mở vùng chữ: ${seconds(timings.decodeMs)}
  Đọc LV: ${seconds(timings.lvMs)} · tên súng: ${seconds(timings.nameMs)}
  Dữ liệu gửi: ${megabytes(timings.uploadBytes)} / ${megabytes(timings.originalBytes||timings.uploadBytes)} ảnh gốc
Cập nhật ảnh xem trước và ghép: ${seconds(timings.renderMs)}
Dùng lại kết quả: ${timings.cached}/${timings.requests} ảnh. Khi so tốc độ, đóng/mở app để tránh dùng lại kết quả cũ.`;
 $('timingPanel').hidden=false;
 const readErrors=targets.filter(e=>e.ocrError);
 if(engineError)$('status').textContent=`Đã cắt ${cuts}/${targets.length} ảnh. Bộ đọc LV chưa hoạt động: ${engineError} Bấm “Lưu log lỗi OCR” để kiểm tra; ảnh đã cắt vẫn được giữ.`;
 else if(readErrors.length)$('status').textContent=`Đã cắt ${cuts}/${targets.length} ảnh; ${readErrors.length} ảnh gặp lỗi đọc chữ: ${readErrors[0].ocrError}. Có thể thử đọc lại.`;
 else $('status').textContent=review?`Đã xử lý trong ${elapsed} giây. ${review} ảnh cần kiểm tra thông tin; tất cả vẫn có trong ảnh ghép.`:`Xong ${targets.length} ảnh trong ${elapsed} giây. Kiểm tra LV trước khi tải.`;
}

$('process').onclick=()=>processEntries(entries,true);$('retry').onclick=()=>processEntries(entries.filter(e=>isFailed(e)||missingWeapon(e)),true);for(const id of ['columns','size','gap'])$(id).onchange=compose;$('download').onclick=saveResult;
function openEditor(e){editing=e;editSelections={gun:e.rect?{...e.rect}:null,badge:e.badgeRect?{...e.badgeRect}:null};$('editMode').value='gun';selection=editSelections.gun;$('editLv').value=e.lv??'';let c=$('editCanvas');c.width=Math.min(1400,e.img.width);c.height=Math.round(c.width*e.img.height/e.img.width);drawEdit();$('editor').showModal()}
function drawEdit(){let c=$('editCanvas'),ctx=c.getContext('2d');ctx.drawImage(editing.img,0,0,c.width,c.height);if(selection){let r=selection;ctx.fillStyle='#0008';ctx.beginPath();ctx.rect(0,0,c.width,c.height);ctx.rect(r.x*c.width,r.y*c.height,r.w*c.width,r.h*c.height);ctx.fill('evenodd');ctx.strokeStyle='#91ffdb';ctx.lineWidth=3;ctx.strokeRect(r.x*c.width,r.y*c.height,r.w*c.width,r.h*c.height)}}
function point(e){let r=$('editCanvas').getBoundingClientRect();return{x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}}$('editCanvas').onpointerdown=e=>{startPoint=point(e);$('editCanvas').setPointerCapture(e.pointerId)};$('editCanvas').onpointermove=e=>{if(!startPoint)return;let p=point(e);selection={x:Math.min(p.x,startPoint.x),y:Math.min(p.y,startPoint.y),w:Math.abs(p.x-startPoint.x),h:Math.abs(p.y-startPoint.y)};drawEdit()};$('editCanvas').onpointerup=()=>startPoint=null;$('close').onclick=()=>$('editor').close();$('editMode').onchange=()=>{editSelections[$('editMode').value==='gun'?'badge':'gun']=selection;selection=editSelections[$('editMode').value];drawEdit()};$('removeBadge').onclick=()=>{editSelections[$('editMode').value]=selection;$('editMode').value='badge';selection=null;editSelections.badge=null;drawEdit()};$('save').onclick=()=>{editSelections[$('editMode').value]=selection;const r=editSelections.gun;if(!r||r.w<.005||r.h<.005)return;editing.rect=r;editing.badgeRect=editSelections.badge&&editSelections.badge.w>.002&&editSelections.badge.h>.002?editSelections.badge:null;editing.badgeManual=true;editing.badgeCanvas=null;let lv=Number($('editLv').value);editing.lv=lv>=1&&lv<=99?lv:null;editing.attempted=true;editing.message='Đã chỉnh thủ công';$('editor').close();refresh()};refresh();

async function activateAachen(source){
 const face=new FontFace('LV Aachen',source,{weight:'900'});await face.load();document.fonts.add(face);lvFont='"LV Aachen"';$('fontStatus').textContent='Đang dùng Aachen';compose();
}
$('fontFile').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>10*1024*1024)throw Error('large');await activateAachen(await file.arrayBuffer())}catch{$('fontStatus').textContent='Không nạp được font. Hãy chọn file TTF, OTF hoặc WOFF hợp lệ.'}e.target.value=''};
activateAachen('url("fonts/aachen-bold.otf")').catch(()=>{$('fontStatus').textContent='Chưa tải được Aachen · tạm dùng Impact. Thử tải lại trang hoặc nạp font.'});

async function copyResult(){
 if(busy||$('result').hidden)return;
 if(window.pywebview?.api?.copy_png){
  $('copy').disabled=true;$('copyStatus').textContent='Đang copy ảnh…';
  try{await window.pywebview.api.copy_png($('result').toDataURL('image/png').split(',')[1]);$('copyStatus').textContent='Đã copy ảnh. Mở Photoshop và nhấn Ctrl + V.';}
  catch(error){$('copyStatus').textContent='Chưa copy được: '+runtimeError(error);}
  finally{$('copy').disabled=busy||$('result').hidden;}return;
 }
 if(!navigator.clipboard?.write||typeof ClipboardItem==='undefined'){$('copyStatus').textContent='Trình duyệt chưa hỗ trợ copy ảnh. Hãy dùng Chrome / Edge hoặc tải PNG.';return;}
 $('copy').disabled=true;$('copyStatus').textContent='Đang copy ảnh…';
 try{
  // Give ClipboardItem a Promise immediately so the click's user activation is retained.
  const png=new Promise((resolve,reject)=>$('result').toBlob(blob=>blob?resolve(blob):reject(Error('Không tạo được PNG')),'image/png'));
  await navigator.clipboard.write([new ClipboardItem({'image/png':png})]);
  $('copyStatus').textContent='Đã copy ảnh. Mở Photoshop và nhấn Ctrl + V.';
 }catch{$('copyStatus').textContent='Không copy được ảnh. Kiểm tra quyền Clipboard của trình duyệt hoặc tải PNG.';}
 finally{$('copy').disabled=busy||$('result').hidden;}
}
$('copy').onclick=copyResult;

initOriginalViewer();

async function saveResult(){
 if(busy||$('result').hidden)return;
 const filename='LV-Studio-'+new Date().toISOString().slice(0,10)+'.png';
 if(window.pywebview?.api?.save_png){
  $('download').disabled=true;
  try{const saved=await window.pywebview.api.save_png($('result').toDataURL('image/png').split(',')[1],filename);if(saved.saved)$('copyStatus').textContent='Đã lưu '+saved.name;}
  catch(error){$('copyStatus').textContent='Chưa lưu được: '+runtimeError(error);}
  finally{$('download').disabled=busy||$('result').hidden;}return;
 }
 $('result').toBlob(blob=>{if(!blob)return;const link=document.createElement('a'),url=URL.createObjectURL(blob);link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000)},'image/png');
}

let lastEngineError=null;
async function refreshEngineStatus(){
 try{
  const result=await (await fetch('/api/status')).json();
  lastEngineError=result.error;
  $('engineStatus').textContent=result.error?'Bộ đọc LV chưa khởi động: '+result.error:result.status || 'Đang chuẩn bị bộ đọc LV…';
  $('engineStatus').classList.toggle('error',!!result.error);
  $('engineLog').hidden=!(result.error&&window.pywebview?.api?.save_log);
  if(result.error)return;
 }catch{$('engineStatus').textContent='Đang kết nối bộ đọc LV…';}
 setTimeout(refreshEngineStatus,1500);
}
$('engineLog').onclick=async()=>{try{await window.pywebview.api.save_log()}catch(error){$('engineStatus').textContent='Chưa lưu được log: '+runtimeError(error)}};
window.addEventListener('pywebviewready',()=>{$('engineLog').hidden=!(lastEngineError&&window.pywebview?.api?.save_log)});
refreshEngineStatus();

function gunSnapshot(){const out=$('result'),valid=entries.filter(e=>e.attempted||e.rect).sort(WeaponVision.compareEntries),cols=Math.max(1,Math.min(gunColumns(valid.length),valid.length)),rows=Math.ceil(valid.length/cols),gap=Number($('gap').value),width=gunOutputWidth(valid,cols,rows,gap),height=Math.max(1,Math.floor(width*.49)),font=lvFont,ow=out.width,oh=out.height,tiles=valid.map(e=>({image:crop(e),badge:e.badgeCanvas,lv:e.lv}));const paint=(ctx,r)=>{ctx.save();ctx.translate(r.x,r.y);ctx.scale(r.w/ow,r.h/oh);tiles.forEach((e,i)=>{const x=Math.floor(i/rows)*(width+gap),y=(i%rows)*(height+gap);ctx.drawImage(e.image,x,y,width,height);if(e.badge){const bw=width*.36,bh=bw*e.badge.height/e.badge.width;ctx.drawImage(e.badge,x+width-bw-width*.02,y+width*.018,bw,bh);}ctx.save();ctx.fillStyle='#fff';ctx.shadowColor='#0008';ctx.shadowBlur=width*.015;ctx.font='900 '+Math.round(width*.19)+'px '+font;ctx.textBaseline='alphabetic';ctx.fillText('LV'+(e.lv||'?'),x+width*.018,y+height-width*.018);ctx.restore();});ctx.restore();};return {busy,canvas:out,paint,cellW:width,cellH:height,count:entries.length,unresolved:entries.filter(e=>!e.rect||!e.lv).length};}
window.LVGuns={settings(){return {columnModeVersion:1,columns:$('columns').value,size:$('size').value,gap:$('gap').value};},applySettings(data){if(data&&!data.columnModeVersion)data={...data,columns:'auto'};for(const [id,allowed]of [['columns',['auto','1','2','3','4','5','6']],['size',['auto','400','600','800']],['gap',['0','4','12']]])if(allowed.includes(String(data?.[id])))$(id).value=String(data[id]);compose();},clear(){if(!busy)$('clear').click();},async importFiles(files){if(busy)throw Error('Tool súng đang xử lý');$('clear').click();await add(files);return gunSnapshot();},snapshot:gunSnapshot};
