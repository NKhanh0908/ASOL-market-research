(() => {
  'use strict';
  const app = document.getElementById('android-app');
  const $ = id => document.getElementById(id);
  const history = $('android-history');
  const crawl = $('android-crawl');
  const toggle = $('android-schedule');
  const cards = new Map();
  let jobId = new URLSearchParams(location.search).get('job_id') || '';
  let feed = 'top-free';
  let latest = null;
  let epoch = 0;
  let scheduleBusy = false;
  let crawlBusy = false;
  const statuses = {pending:'Đang chờ collector rảnh',queued:'Đang mở Chrome',running:'Đang thu thập',succeeded:'Hoàn tất',partial:'Hoàn tất một phần',failed:'Thu thập thất bại',interrupted:'Đã gián đoạn'};
  const metadataStates = {pending:'Đang chờ metadata',complete:'Đã phân tích',cached:'Đã phân tích · dùng cache',failed:'Metadata lỗi · giữ thứ hạng'};
  const fmt = value => value ? new Intl.DateTimeFormat('vi-VN',{dateStyle:'short',timeStyle:'medium',timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(value)) : '—';
  const casualLabels = {casual:'Casual',not_casual:'Không phải Casual',unknown:'Chưa xác định'};
  const node = (tag, text, cls) => { const el=document.createElement(tag); if(text!=null)el.textContent=text; if(cls)el.className=cls; return el; };
  const safeUrl = (value, image=false) => {
    try { const url=new URL(value); return url.protocol==='https:' && (image ? url.hostname.endsWith('.googleusercontent.com') : url.hostname==='play.google.com') ? url.href : null; } catch {return null;}
  };
  const error = message => { $('android-error').textContent=message || ''; $('android-error').hidden=!message; };
  async function request(url, options={}) {
    const response=await fetch(url,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':app.dataset.csrf,...options.headers}});
    const data=await response.json();
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Không thể tải dữ liệu.');
    return data;
  }
  function item(row) {
    const card=node('article',null,'android-game');
    card.dataset.package=row.package;
    const top=node('div',null,'android-game-head');
    top.append(node('span','#'+(feed==='top-free'?row.free_rank:row.grossing_rank),'android-rank'));
    const icon=safeUrl(row.icon_url,true);
    if(icon){const img=node('img',null,'android-icon');img.src=icon;img.alt='';img.loading='lazy';top.append(img);}
    const title=node('div');title.append(node('h2',row.name),node('p',row.developer || 'Nhà phát triển: đang chờ dữ liệu','android-developer'));
    top.append(title);card.append(top,node('span',metadataStates[row.metadata_status] || row.metadata_status,'android-row-state '+row.metadata_status));
    card.append(node('span',casualLabels[row.casual_status] || 'Chưa phân loại','android-category '+(row.casual_status || 'unknown')));
    const stats=node('div',null,'android-details');
    const delta=feed==='top-free'?row.delta_free_1d:row.delta_grossing_1d;
    const rating=row.rating==null?'Chưa có dữ liệu':`${Number(row.rating).toFixed(1)} ★ · ${Number(row.rating_count||0).toLocaleString('vi-VN')} đánh giá`;
    for(const [label,value] of [
      ['Đánh giá',rating],['Biến động 1 ngày',delta==null?'Chưa có mốc so sánh':`${delta>0?'+':''}${delta} hạng`],
      ['Top Free / Grossing',`${row.free_rank?'#'+row.free_rank:'—'} / ${row.grossing_rank?'#'+row.grossing_rank:'—'}`],
      ['Thể loại con',row.subgenre || row.google_play_genres?.map(g=>g.label).filter(Boolean).join(', ') || 'Chưa có dữ liệu'],
      ['Cơ chế (suy luận)',row.mechanic?`${row.mechanic} · ${row.mechanic_confidence}`:'Đang chờ phân tích'],
      ['Kiếm tiền (tín hiệu)',row.monetization_model || 'UNKNOWN'],['Metadata cập nhật',fmt(row.fetched_at)]
    ]){const field=node('div');field.append(node('span',label),node('strong',value));stats.append(field);}
    card.append(stats);
    const details=node('details');details.append(node('summary','Mô tả và nguồn'),node('p',row.description || 'Chưa có mô tả.'),node('p',row.package));
    if(row.metadata_error)details.append(node('p',row.metadata_error));
    const url=safeUrl(row.store_url);
    if(url){const a=node('a','Mở Google Play ↗');a.href=url;a.target='_blank';a.rel='noopener noreferrer';details.append(a);}
    card.append(details);
    return card;
  }
  function renderRows() {
    if(!latest)return;
    const rank=feed==='top-free'?'free_rank':'grossing_rank';
    const chartRows=latest.entries.filter(r=>r[rank]!=null);
    const excluded=chartRows.filter(r=>r.casual_status==='not_casual').length;
    const rows=chartRows.filter(r=>r.casual_status!=='not_casual').sort((a,b)=>a[rank]-b[rank]);
    const container=$('android-results');
    const wanted=new Set(rows.map(r=>r.package));
    for(const [key,entry] of cards){if(!wanted.has(key)){entry.element.remove();cards.delete(key);}}
    for(const [index,row] of rows.entries()){
      const signature=feed+JSON.stringify(row);
      let previous=cards.get(row.package);
      if(!previous || previous.signature!==signature){
        const replacement=item(row);
        if(previous?.element.querySelector('details').open)replacement.querySelector('details').open=true;
        if(previous)previous.element.replaceWith(replacement);
        previous={element:replacement,signature};cards.set(row.package,previous);
      }
      if(container.children[index]!==previous.element)container.insertBefore(previous.element,container.children[index]||null);
    }
    $('android-empty').hidden=rows.length>0;
    $('android-empty').textContent=latest.job?(excluded?'Không còn game Casual trong bảng này sau khi lọc.':'Bảng này chưa có kết quả trong lần thu thập đã chọn.'):'Bấm “Crawl Android ngay” để bắt đầu.';
    const chart=latest.charts.find(c=>c.feed===feed);
    const unknown=chartRows.filter(r=>r.casual_status==='unknown' || !r.casual_status).length;
    $('android-chart-note').textContent=`${chart?`${rows.filter(r=>r.casual_status==='casual').length} Casual / ${chart.count} hạng · loại ${excluded} game khác thể loại · chưa rõ ${unknown} · quan sát ${fmt(chart.observed_at)}`:'Đang chờ bảng xếp hạng'}. Chỉ game xác nhận Casual được tính vào danh sách; Top Grossing là thứ hạng, không phải doanh thu.`;
  }
  function render(data) {
    latest=data;
    const job=data.job;
    $('android-status').textContent=job?`${statuses[job.status] || job.status}${job.status==='running'?' · '+({metadata:'metadata và phân tích', 'top-free':'Top Free', 'top-grossing':'Top Grossing', charts:'bảng xếp hạng'}[job.phase]||job.phase):''}`:'Chưa có lượt crawl Android';
    $('android-count').textContent=job?`${job.processed}/${job.total} game đã xử lý`:'Chưa có dữ liệu';
    $('android-batch').textContent=job?`${job.batches} batch đã lưu · ${data.entries.filter(r=>r.metadata_status==='failed').length} game lỗi`:'';
    $('android-updated').textContent=job?'Cập nhật '+fmt(job.updated_at):'';
    $('android-progress').max=Math.max(job?.total||0,1);
    $('android-progress').value=job?.processed||0;
    $('android-errors').textContent=(job?.errors||[]).join(' · ');
    crawl.disabled=crawlBusy || Boolean(data.active_job_id);
    crawl.textContent=data.active_job_id?'Đang có lượt crawl Android':'Crawl Android ngay';
    if(!scheduleBusy)toggle.checked=data.schedule.enabled;
    const historySignature=JSON.stringify(data.jobs);
    if(history.dataset.signature!==historySignature){
      history.replaceChildren(new Option('Mới nhất',''));
      for(const j of data.jobs)history.add(new Option(`${fmt(j.created_at)} · ${statuses[j.status]||j.status}`,j.id));
      history.dataset.signature=historySignature;history.value=jobId;
    }
    renderRows();
  }
  async function refresh() {
    const current=++epoch;
    const requestedId=jobId;
    try {
      const data=await request('/api/android/data'+(requestedId?'?job_id='+encodeURIComponent(requestedId):''));
      if(current!==epoch || requestedId!==jobId)return;
      error('');render(data);
    }catch(e){if(current===epoch)error(e.message+' Sẽ thử cập nhật lại; dữ liệu đang hiển thị được giữ nguyên.');}
  }
  async function poll(){await refresh();setTimeout(poll,2000);}
  crawl.addEventListener('click',async()=>{
    crawlBusy=true;crawl.disabled=true;
    try{const data=await request('/api/android/runs',{method:'POST'});jobId=data.job_id;
      window.history.replaceState(null,'','/android?job_id='+encodeURIComponent(jobId));await refresh();
    }catch(e){error(e.message);}finally{crawlBusy=false;crawl.disabled=Boolean(latest?.active_job_id);}
  });
  toggle.addEventListener('change',async()=>{
    scheduleBusy=true;toggle.disabled=true;
    try{await request('/api/android/schedule',{method:'PATCH',body:JSON.stringify({enabled:toggle.checked})});}
    catch(e){toggle.checked=!toggle.checked;error(e.message);}finally{scheduleBusy=false;toggle.disabled=false;}
  });
  history.addEventListener('change',()=>{jobId=history.value;window.history.replaceState(null,'',jobId?'/android?job_id='+encodeURIComponent(jobId):'/android');refresh();});
  app.querySelectorAll('[data-feed]').forEach(button=>button.addEventListener('click',()=>{
    feed=button.dataset.feed;app.querySelectorAll('[data-feed]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));renderRows();
  }));
  poll();
})();
