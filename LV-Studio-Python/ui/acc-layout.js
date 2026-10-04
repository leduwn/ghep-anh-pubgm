(function(root){
 'use strict';
 function characterLayout(n,featured='auto'){
  if(!Number.isInteger(n)||n<1)throw Error('Chưa có ảnh nhân vật');
  let top=Number(featured);
  if(featured==='auto')top=n>=28&&n<=30?n-18:n>=36&&n<=39?n-24:0;
  if(!Number.isInteger(top)||top<0||top>=n)throw Error('Số ảnh nổi bật phải nhỏ hơn tổng ảnh');
  const rest=n-top,known={12:[3,4],15:[3,5],18:[3,6],24:[4,6]};
  if(!known[rest])throw Error('Chưa có mẫu cho '+rest+' ảnh thường. Hãy chỉnh số ảnh nổi bật hoặc hàng/cột.');
  return {featured:top,rows:known[rest][0],cols:known[rest][1]};
 }
 function characterForms(n){if(!Number.isInteger(n)||n<1)return [];const forms=[];const add=(featured,rows,cols)=>forms.push({id:[featured,rows,cols].join('-'),featured,rows,cols});for(let rest=9;rest<=n-8;rest++)for(let rows=3;rows<=Math.floor(rest/3);rows++)if(rest%rows===0&&rest/rows>=3)add(n-rest,rows,rest/rows);const preferred=n>=28&&n<=30?18:n>=36&&n<=39?24:null;forms.sort((a,b)=>(b.rows*b.cols===preferred?1:0)-(a.rows*a.cols===preferred?1:0)||b.rows*b.cols-a.rows*a.cols||Math.abs(a.cols/a.rows-1.5)-Math.abs(b.cols/b.rows-1.5));const plain=[];for(let rows=3;rows<=Math.floor(n/3);rows++)if(n%rows===0&&n/rows>=3)plain.push({id:[0,rows,n/rows].join('-'),featured:0,rows,cols:n/rows});if(!plain.length){const rows=n<9?1:3;plain.push({id:[0,rows,Math.ceil(n/rows)].join('-'),featured:0,rows,cols:Math.ceil(n/rows)});}plain.sort((a,b)=>Math.abs(a.cols/a.rows-1.5)-Math.abs(b.cols/b.rows-1.5));return [...forms,...plain];}
 function itemLayout(n){const map={6:[3,2],9:[3,3],12:[3,4],16:[4,4],24:[6,4]};if(!map[n])throw Error('Chưa có mẫu đồ cho '+n+' ảnh. Hãy chọn hàng/cột thủ công.');return {rows:map[n][0],cols:map[n][1]};}
 function chronological(files){return [...files].sort((a,b)=>a.lastModified-b.lastModified||a.name.localeCompare(b.name,'vi',{numeric:true}));}
 function safeRect(r,w,h){if(r.length!==4||!r.every(Number.isFinite)||r[0]<0||r[1]<0||r[2]<=r[0]||r[3]<=r[1]||r[2]>w||r[3]>h)throw Error('Vùng cắt nằm ngoài ảnh hoặc không hợp lệ');return r;}
 root.AccLayout={characterLayout,characterForms,itemLayout,chronological,safeRect};
})(typeof module==='object'?module.exports:globalThis);
