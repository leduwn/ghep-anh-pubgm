'use strict';
async function importMiscImage(file,img,url){
 const mode=el('miscImportMode').value||'auto',keep=(message)=>{groups.misc.push({file,img,url,miscImportNote:message});el('miscImportStatus').textContent=file.name+': '+message;};
 if(mode==='cropped'){keep('Giữ ảnh đã cắt');return;}
 try{
  const preview=cut(img,[0,0,img.width,img.height],1200),api=window.pywebview?.api;let result;
  el('miscImportStatus').textContent='Đang tìm ô: '+file.name;
  if(api?.read_misc)result=await api.read_misc(preview.toDataURL('image/png').split(',')[1]);
  else if(window.LV_PYTHON?.token){const blob=await new Promise(resolve=>preview.toBlob(resolve,'image/png'));const response=await fetch('/api/misc',{method:'POST',headers:{'Content-Type':'image/png','X-LV-Token':window.LV_PYTHON.token},body:blob});if(!response.ok)throw Error('Cần build EXE bản 18 để tự cắt Linh tinh');result=await response.json();}
  else throw Error('Cần build EXE bản 18 để tự cắt Linh tinh');
  if(!result.detected){keep(mode==='grid'?'Chưa tìm được lưới · giữ ảnh để kiểm tra':'Giữ nguyên · chưa thấy lưới ô');return;}
  const rectangles=result.rects||[];if(rectangles.length>6||rectangles.some(r=>r.length!==4||!r.every(Number.isFinite)||r[0]<0||r[1]<0||r[2]<=r[0]||r[3]<=r[1]||r[2]>preview.width||r[3]>preview.height))throw Error('Vùng cắt chưa hợp lệ');
  for(let i=0;i<rectangles.length;i++){const r=rectangles[i].map((v,j)=>v*(j%2?img.height/preview.height:img.width/preview.width)),tile=cut(img,r),tileURL=tile.toDataURL('image/png'),part={name:file.name.replace(/\.[^.]+$/,'')+' · ô '+(i+1)+'.png',lastModified:file.lastModified,webkitRelativePath:file.webkitRelativePath};groups.misc.push({file:part,img:tile,url:tileURL,miscMode:'small',miscImportNote:'Tự cắt từ '+file.name});}
  URL.revokeObjectURL(url);el('miscImportStatus').textContent=file.name+': '+rectangles.length+' ô · bỏ '+(result.locked||0)+' ô khoá · bỏ '+(result.partial||0)+' ô cụt';
 }catch(error){keep('Giữ ảnh gốc · '+error.message);}
}
