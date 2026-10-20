'use strict';

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
const clone = value => JSON.parse(JSON.stringify(value));
const symbols = {read_orders:'↳', validate_orders:'✓', discount_orders:'%', summarize_orders:'▥'};
const state = {modules:[], workflow:null, saved:null, dirty:true, selected:null, selectedEdge:null, connection:null, zoom:1, pan:{x:0,y:0}, lastRun:null, busy:false, tab:'result', workflows:[], runs:[], csrf:null,projectId:'default',project:null,projects:[],language:'en',chat:[],skillSnapshot:null};
let toastTimer, drag = null;

async function api(path, body, projectId=state.projectId) {
  const headers={'X-FlowReuse-Project':projectId,'X-FlowReuse-Language':state.language};
  if(body!==undefined){headers['Content-Type']='application/json';headers['X-FlowReuse-Token']=state.csrf;}
  const response = await fetch(path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body)});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'Operation failed');
  if(value.skill_snapshot){state.skillSnapshot=value.skill_snapshot;renderSkillStatus();}
  return value;
}
function toast(message, error = false) {
  clearTimeout(toastTimer);
  $('#toast').textContent = message;
  $('#toast').className = 'toast' + (error ? ' error' : '');
  toastTimer = setTimeout(() => $('#toast').classList.add('hidden'), error ? 6500 : 3500);
}
function moduleOf(node) { return state.modules.find(item => item.id === node.module); }
function rememberRevision() { try { localStorage.setItem('flowreuse.'+state.projectId+'.activeRevision',state.saved.revision_id); } catch {} }
function symbolOf(module) { return esc(module.symbol || symbols[module.id] || '◇'); }
function hasUnsavedChanges(){return !!(state.dirty&&state.workflow&&(state.workflow.nodes.length||state.workflow.name!=='New workflow'));}
function markDirty() { state.dirty = true; state.lastRun = null; updateSaveState(); renderResult(); }
function updateSaveState() {
  $('#save-status').textContent = state.dirty ? (state.saved ? 'Unsaved changes' : 'Unsaved') : `Version ${state.saved.number}`;
  $('#save-status').className = 'save-status' + (state.dirty ? '' : ' saved');
  $('#save-button').textContent = state.dirty ? 'Save version' : 'Saved';
  $('#saved-count').textContent = state.workflows.length;
}
function setBusy(value) {
  state.busy = value;
  for (const button of document.querySelectorAll('#save-button,#run-button,#new-button,#templates-button,#layout-button,#validate-button,#library-history,#workflow-name,#module-list button,#module-search,#module-category,#inspector-content button,#inspector-content input')) button.disabled = value;
  $('#run-button').innerHTML = value ? '<span class="running-spinner"></span> Executing…' : '<span>▶</span> Run workflow';
  for(const element of document.querySelectorAll('#project-select,#project-new,#ai-settings,#profile-chip,#language-select,#chat-send,#chat-input,#export-skill'))element.disabled=value;
}
function renderModules() {
  const query = $('#module-search').value.trim().toLowerCase();
  const category=$('#module-category').value;
  const items = state.modules.filter(module => (category==='all'||module.category===category)&&`${module.name} ${tr(module.name)} ${module.description} ${module.id}`.toLowerCase().includes(query));
  $('#module-count').textContent=items.length;
  $('#module-list').innerHTML = items.length ? items.map(module => `<button class="module-card" draggable="true" data-module="${esc(module.id)}" aria-label="Add ${esc(module.name)}"><span class="module-icon ${esc(module.color)}">${symbolOf(module)}</span><span class="module-info"><strong>${esc(module.name)}</strong><small>PYTHON · v${esc(module.version)}</small></span><span class="module-plus">＋</span></button>`).join('') : '<p class="small muted">No matching modules</p>';
}
function renderCanvas() {
  const workflow = state.workflow;
  if (!workflow) return;
  const statuses = new Map((state.lastRun?.revision_id === state.saved?.revision_id && !state.dirty ? state.lastRun.nodes : []).map(node => [node.node_id,node.status]));
  $('#nodes').innerHTML = workflow.nodes.map(node => {
    const module = moduleOf(node), status = statuses.get(node.id);
    const statusText = {success:'✓ Complete',failed:'! Failed',skipped:'Skipped',running:'Executing…'}[status] || 'Ready';
    return `<div class="node${state.selected === node.id ? ' selected' : ''}${status ? ' '+status : ''}" data-node="${esc(node.id)}" style="left:${node.x}px;top:${node.y}px" tabindex="0" aria-label="${esc(module.name)}，${esc(statusText)}">${module.input ? `<button class="port port-in" data-input="${esc(node.id)}" aria-label="Connect input of ${esc(module.name)}"></button>` : ''}<div class="node-top"><span class="module-icon ${esc(module.color)}">${symbolOf(module)}</span><div><div class="node-title">${esc(module.name)}</div><div class="node-version">PYTHON · v${esc(node.version)}</div></div><span class="node-dots">⋮</span></div><div class="node-description">${esc(module.description)}</div><div class="node-footer"><span>Reusable code</span><span class="${status === 'success' ? 'success-text' : status === 'failed' ? 'error-text' : ''}">${esc(statusText)}</span></div><button class="port port-out${state.connection === node.id ? ' pending' : ''}" data-output="${esc(node.id)}" aria-label="Connect output of ${esc(module.name)}"></button></div>`;
  }).join('');
  $('#node-count').textContent = `${workflow.nodes.length} modules · ${workflow.edges.length} connections`;
  $('#canvas-empty').classList.toggle('hidden', workflow.nodes.length > 0);
  $('#connection-hint').classList.toggle('hidden', !state.connection);
  $('#connection-hint').textContent = 'Click a target input · Esc to cancel';
  renderEdges();
  transformWorld();
}
function renderEdges() {
  if (!state.workflow) return;
  const nodes = new Map(state.workflow.nodes.map(node => [node.id,node]));
  $('#edges').innerHTML = `<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9bb28b"/></marker></defs>` + state.workflow.edges.map(edge => {
    const source = nodes.get(edge.source), target = nodes.get(edge.target);
    if (!source || !target) return '';
    const x1 = source.x + 228, y1 = source.y + 76, x2 = target.x, y2 = target.y + 76;
    const curve = Math.max(55, Math.abs(x2-x1)*.5);
    const path = `M${x1},${y1} C${x1+curve},${y1} ${x2-curve},${y2} ${x2},${y2}`;
    const label=`Select ${moduleOf(source).name} to ${moduleOf(target).name} connection`;
    return `<g data-edge="${esc(edge.id)}" role="button" tabindex="0" aria-label="${esc(label)}"><path d="${path}" class="edge${state.selectedEdge === edge.id ? ' selected' : ''}" marker-end="url(#arrow)"/><path d="${path}" class="edge-hit"/><rect class="edge-control" x="${(x1+x2)/2-12}" y="${(y1+y2)/2-12}" width="24" height="24"/></g>`;
  }).join('');
}
function transformWorld() {
  $('#world').style.transform = `translate(${state.pan.x}px,${state.pan.y}px) scale(${state.zoom})`;
  $('#zoom-label').textContent = `${Math.round(state.zoom * 100)}%`;
  $('#canvas').style.backgroundSize = `${18*state.zoom}px ${18*state.zoom}px`;
  $('#canvas').style.backgroundPosition = `${state.pan.x}px ${state.pan.y}px`;
}
function fit() {
  const nodes = state.workflow?.nodes;
  if (!nodes?.length) { state.zoom = 1; state.pan={x:0,y:0}; transformWorld(); return; }
  const rect = $('#canvas').getBoundingClientRect();
  const minX = Math.min(...nodes.map(n=>n.x)), minY = Math.min(...nodes.map(n=>n.y));
  const width = Math.max(...nodes.map(n=>n.x))+228-minX, height = Math.max(...nodes.map(n=>n.y))+160-minY;
  state.zoom = Math.max(.25, Math.min(1, (rect.width-90)/width, (rect.height-140)/height));
  state.pan = {x:(rect.width-width*state.zoom)/2-minX*state.zoom,y:(rect.height-height*state.zoom)/2-minY*state.zoom+12};
  transformWorld();
}
function changeZoom(factor, point) {
  const rect = $('#canvas').getBoundingClientRect(), target = point || {x:rect.width/2,y:rect.height/2};
  const next = Math.max(.25,Math.min(1.7,state.zoom*factor));
  state.pan = {x:target.x-(target.x-state.pan.x)*next/state.zoom,y:target.y-(target.y-state.pan.y)*next/state.zoom};
  state.zoom=next; transformWorld();
}
function selectNode(id) {
  state.selected=id; state.selectedEdge=null; showPane('details');
  renderCanvas(); renderInspector();
  $('.inspector').classList.toggle('open', !!id);
}
function renderInspector() {
  const node = state.workflow?.nodes.find(item=>item.id===state.selected);
  if (!node) {
    if (state.selectedEdge) {
      $('#inspector-content').innerHTML = '<div class="inspector-main connection-selected">Connection selected<br><button class="delete-button" id="delete-edge">Delete connection</button></div>';
      return;
    }
    $('#inspector-content').innerHTML = '<div class="inspector-placeholder"><span>⌘</span>Select a module to inspect its parameters, contract and code.<br></div>';
    return;
  }
  const module=moduleOf(node);
  $('#inspector-content').innerHTML = `<div class="inspector-main"><div class="inspector-node-title"><span class="module-icon ${esc(module.color)}">${symbolOf(module)}</span><div><strong>${esc(module.name)}</strong><small>Registered module · v${esc(node.version)}</small></div></div><p class="inspector-description">${esc(module.description)}</p><span class="section-label">Parameters</span>${module.fields.length ? module.fields.map(field=>`<label class="field"><span>${esc(field.label)}</span><input data-param="${esc(field.key)}" type="${field.type === 'number' ? 'number' : 'text'}" value="${esc(node.params[field.key])}" ${field.type === 'number' ? `min="${field.min}" max="${field.max}" step="any"` : 'maxlength="80"'}></label>`).join('') : '<p class="small muted">No parameters required.</p>'}<span class="section-label">Data contract</span><div class="contract-row"><span>Input</span><code>${esc(module.input || 'Run input')}</code></div><div class="contract-row"><span>Output</span><code>${esc(module.output)}</code></div><button class="code-button" id="view-code"><span>〈/〉 View Python code</span><span>↗</span></button><div class="version-note">This implementation is pinned. Save parameter changes as a new workflow version.</div><button class="delete-button" id="delete-node">Remove module</button></div>`;
}
function addModule(key, position) {
  if (state.busy) return;
  const module=state.modules.find(item=>item.id===key);
  if (!module) return;
  const rect=$('#canvas').getBoundingClientRect();
  const point=position || {x:(rect.width/2-state.pan.x)/state.zoom-114,y:(rect.height/2-state.pan.y)/state.zoom-76};
  const node={id:crypto.randomUUID(),module:key,version:module.version,hash:module.hash,params:clone(module.defaults),x:Math.round(point.x),y:Math.round(point.y)};
  state.workflow.nodes.push(node); markDirty(); selectNode(node.id);
  toast(`Module added: ${module.name}. Connect its ports when needed.`);
}
function connect(targetId) {
  if (!state.connection) { toast('Select an output port first.'); return; }
  const source=state.workflow.nodes.find(n=>n.id===state.connection), target=state.workflow.nodes.find(n=>n.id===targetId);
  if (source.id===target.id) return toast('A module cannot connect to itself.',true);
  if (moduleOf(source).output !== moduleOf(target).input) return toast('Port types are incompatible.',true);
  if (state.workflow.edges.some(edge=>edge.target===target.id)) return toast('Delete the existing input connection first.',true);
  const reachable=new Set([target.id]);
  for (let changed=true;changed;) { changed=false; for(const edge of state.workflow.edges) if(reachable.has(edge.source)&&!reachable.has(edge.target)){reachable.add(edge.target);changed=true;} }
  if (reachable.has(source.id)) return toast('This connection would create a cycle.',true);
  state.workflow.edges.push({id:crypto.randomUUID(),source:source.id,target:target.id});
  state.connection=null; markDirty(); renderCanvas(); toast('Connection created.');
}
function deleteSelected() {
  if(state.busy) return;
  if(state.selected){const id=state.selected;state.workflow.nodes=state.workflow.nodes.filter(node=>node.id!==id);state.workflow.edges=state.workflow.edges.filter(edge=>edge.source!==id&&edge.target!==id);state.selected=null;state.connection=null;}
  else if(state.selectedEdge){state.workflow.edges=state.workflow.edges.filter(edge=>edge.id!==state.selectedEdge);state.selectedEdge=null;}
  else return;
  markDirty();renderCanvas();renderInspector();$('.inspector').classList.remove('open');
}
function autoLayout() {
  const incoming=new Map(state.workflow.nodes.map(n=>[n.id,0])), outgoing=new Map(state.workflow.nodes.map(n=>[n.id,[]]));
  for(const edge of state.workflow.edges){incoming.set(edge.target,incoming.get(edge.target)+1);outgoing.get(edge.source).push(edge.target);}
  const queue=[...incoming].filter(([,count])=>count===0).map(([id])=>id), depths=new Map(queue.map(id=>[id,0]));
  let count=0;
  while(queue.length){const id=queue.shift();count++;for(const target of outgoing.get(id)){depths.set(target,Math.max(depths.get(target)||0,depths.get(id)+1));incoming.set(target,incoming.get(target)-1);if(incoming.get(target)===0)queue.push(target);}}
  if(count!==state.workflow.nodes.length) return toast('Workflow has a cycle.',true);
  const rows=new Map();
  for(const node of state.workflow.nodes){const depth=depths.get(node.id)||0,row=rows.get(depth)||0;node.x=80+depth*300;node.y=100+row*215;rows.set(depth,row+1);}
  markDirty();renderCanvas();fit();toast('Layout updated.');
}
async function saveWorkflow() {
  if(!state.dirty && state.saved) return state.saved;
  state.workflow.name=$('#workflow-name').value.trim();
  const saved=await api('/api/workflows',{workflow:state.workflow,workflow_id:state.saved?.workflow_id || null});
  state.saved=saved;state.dirty=false;
  rememberRevision();
  state.workflows=await api('/api/workflows');
  updateSaveState();
  return saved;
}
async function runWorkflow() {
  if(state.busy)return;
  let input;
  try{input=JSON.parse($('#input-data').value);}catch{switchTab('input');return toast('Input is not valid JSON.',true);}
  try{
    setBusy(true);
    const saved=await saveWorkflow();
    state.lastRun=null;renderResult(true);switchTab('result');
    const result=await api('/api/run',{revision_id:saved.revision_id,input});
    state.lastRun=result;
    state.runs=await api('/api/runs');
    renderCanvas();renderResult();renderHistory();
    toast(result.status==='success'?'Run complete. No engine model calls.':result.error?.message || 'Failed',result.status!=='success');
  }catch(error){toast(error.message,true);renderResult();}
  finally{setBusy(false);}
}
function renderResult(running=false) {
  if(running){$('#result-content').innerHTML='<div class="result-empty"><span class="running-spinner"></span><div><h3>Running the saved workflow</h3><p>Processing fresh input without a model call.</p></div></div>';return;}
  const run=state.lastRun;
  $('#result-dot').textContent=run ? '·' : '';
  $('#execution-badge').textContent=run ? `AI calls: ${run.ai_calls} ` : 'Deterministic execution';
  if(!run){$('#result-content').innerHTML='<div class="result-empty"><div class="empty-symbol">▷</div><div><h3>Describe your task to build a reusable workflow.</h3><p>The copilot selects and connects modules; execution reuses saved code.<br></p></div></div>';return;}
  if(run.status!=='success'){
    const failed=run.nodes.find(node=>node.status==='failed'),module=state.modules.find(m=>m.id===failed?.module);
    $('#result-content').innerHTML=`<div class="result-header"><strong class="failed-text">! Execution stopped</strong><span>${esc(run.workflow_name)} · Version ${run.revision_number}</span></div><div class="error-box">${esc(module?.name || 'Workflow')}：${esc(run.error?.message)}<small>Failure context is available to the invoking AI.</small></div><div class="result-footer"><span>AI calls: ${run.ai_calls} </span><button class="text-button" id="view-run">View details ↗</button></div>`;return;
  }
  const outputs=Object.values(run.outputs);
  const elapsed=Date.parse(run.finished_at)-Date.parse(run.started_at);
  const preview=outputs.length===1?outputs[0]:run.outputs;
  const previewText=typeof preview==='string'?preview:JSON.stringify(preview,null,2);
  $('#result-content').innerHTML=`<div class="result-header"><strong>✓ All modules completed</strong><span>${esc(run.workflow_name)} · Version ${run.revision_number}</span></div><pre class="generic-preview">${esc(previewText.slice(0,1200))}${previewText.length>1200?'\n… Full output is available in the JSON export.':''}</pre><div class="result-footer"><span>${run.nodes.length} modules completed</span><span>${outputs.length} outputs</span><span>Duration: ${elapsed} ms</span><span>AI calls: ${run.ai_calls} </span><button class="text-button" id="download-result">Download JSON ↓</button><button class="text-button" id="view-run">View details ↗</button></div>`;
}
function renderHistory() {
  $('#history-content').innerHTML=state.runs.length ? state.runs.map(run=>`<button class="history-item" data-run="${esc(run.id)}"><span><strong>${esc(run.workflow_name)}</strong><small>${esc(formatDate(run.created_at))} · AI ${run.ai_calls} </small></span><span class="history-status${run.status==='failed'?' failed':''}">${run.status==='success'?'✓ Success':run.status==='failed'?'! Failed':'Running'}</span></button>`).join('') : '<div class="result-empty"><p>No runs in this project yet.</p></div>';
}
function formatDate(value) { return new Intl.DateTimeFormat(state.language==='fr'?'fr-FR':'en-GB',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(value)); }
function switchTab(tab) {
  state.tab=tab;
  for(const element of document.querySelectorAll('[data-tab]')){const active=element.dataset.tab===tab;element.classList.toggle('active',active);element.setAttribute('aria-selected',active);}
  for(const name of ['result','input','history'])$(`#${name}-content`).classList.toggle('hidden',name!==tab);
}
function modal(title,content) { $('#modal-title').textContent=title;$('#modal-content').innerHTML=content;$('#modal').showModal(); }
async function showSaved() {
  try{
    state.workflows=await api('/api/workflows');updateSaveState();
    modal('Saved workflows',state.workflows.length ? state.workflows.map(workflow=>`<div class="history-item"><button class="text-button" data-load="${esc(workflow.revision_id)}"><strong>${esc(workflow.name)}</strong><small>Version ${workflow.number} · ${esc(formatDate(workflow.created_at))}</small></button><button class="text-button" data-versions="${esc(workflow.workflow_id)}">Versions ↗</button></div>`).join('') : '<p class="muted">No saved workflows in this project.</p>');
  }catch(error){toast(error.message,true);}
}
async function loadRevision(id) {
  if(hasUnsavedChanges() && !confirm(tr('Discard unsaved changes?')))return;
  const revision=await api(`/api/revisions/${encodeURIComponent(id)}`);
  state.workflow=revision.workflow;state.saved={workflow_id:revision.workflow_id,revision_id:revision.id,number:revision.number};state.dirty=false;state.selected=null;state.selectedEdge=null;state.lastRun=null;state.connection=null;
  rememberRevision();
  $('#workflow-name').value=state.workflow.name;
  $('#modal').close();updateSaveState();renderCanvas();renderInspector();renderResult();fit();
  toast(`Opened version ${revision.number}`);
}
function newWorkflow() {
  if(state.busy)return;
  if(hasUnsavedChanges()&&!confirm(tr('Discard unsaved changes?')))return;
  state.workflow={name:'New workflow',nodes:[],edges:[]};state.saved=null;state.selected=null;state.selectedEdge=null;state.connection=null;state.dirty=true;state.lastRun=null;
  try{localStorage.removeItem('flowreuse.'+state.projectId+'.activeRevision');}catch{}
  state.demoInput={};$('#input-data').value='{}';$('#module-category').value='general';renderModules();
  $('#workflow-name').value=state.workflow.name;updateSaveState();renderCanvas();renderInspector();renderResult();fit();
  toast('Start a new conversation or add a module.');
}
function showTemplates(){
  modal('Optional examples',state.templates.map(template=>`<button class="history-item" data-template="${esc(template.id)}"><span><strong>${esc(template.name)}</strong><small>${esc(template.description)}</small></span><span>${template.category==='general'?'General example':'Domain example'} ↗</span></button>`).join(''));
}
function loadTemplate(id){
  const template=state.templates.find(item=>item.id===id);
  if(!template)return;
  if(hasUnsavedChanges()&&!confirm(tr('Discard unsaved changes?')))return;
  state.workflow=clone(template.workflow);state.demoInput=clone(template.input);state.saved=null;state.selected=null;state.selectedEdge=null;state.connection=null;state.lastRun=null;state.dirty=true;
  $('#workflow-name').value=state.workflow.name;$('#input-data').value=JSON.stringify(template.input,null,2);$('#module-category').value=template.category;
  $('#modal').close();renderModules();renderCanvas();renderInspector();renderResult();updateSaveState();fit();
  toast('Example opened.');
}

$('#canvas').addEventListener('pointerdown',event=>{
  if(state.busy||event.button!==0)return;
  if(event.target.closest('.port,.zoom-controls,[data-edge]'))return;
  const element=event.target.closest('[data-node]');
  if(element){const id=element.dataset.node;selectNode(id);const node=state.workflow.nodes.find(n=>n.id===id);drag={type:'node',id,startX:event.clientX,startY:event.clientY,x:node.x,y:node.y,moved:false};}
  else{state.selected=null;state.selectedEdge=null;state.connection=null;renderCanvas();renderInspector();$('.inspector').classList.remove('open');drag={type:'pan',startX:event.clientX,startY:event.clientY,x:state.pan.x,y:state.pan.y};}
  $('#canvas').setPointerCapture(event.pointerId);
});
$('#canvas').addEventListener('pointermove',event=>{
  if(!drag)return;
  const dx=event.clientX-drag.startX,dy=event.clientY-drag.startY;
  if(drag.type==='pan'){state.pan={x:drag.x+dx,y:drag.y+dy};transformWorld();return;}
  if(Math.abs(dx)+Math.abs(dy)<3&&!drag.moved)return;
  drag.moved=true;
  const node=state.workflow.nodes.find(n=>n.id===drag.id);
  node.x=Math.round(Math.max(-90000,Math.min(90000,drag.x+dx/state.zoom)));node.y=Math.round(Math.max(-90000,Math.min(90000,drag.y+dy/state.zoom)));
  const element=[...document.querySelectorAll('[data-node]')].find(el=>el.dataset.node===node.id);
  element.style.left=node.x+'px';element.style.top=node.y+'px';renderEdges();
});
function endDrag(){if(drag?.type==='node'&&drag.moved){markDirty();renderCanvas();}drag=null;}
$('#canvas').addEventListener('pointerup',endDrag);
$('#canvas').addEventListener('pointercancel',endDrag);
$('#canvas').addEventListener('wheel',event=>{event.preventDefault();const rect=$('#canvas').getBoundingClientRect();changeZoom(event.deltaY<0?1.08:1/1.08,{x:event.clientX-rect.left,y:event.clientY-rect.top});},{passive:false});
$('#canvas').addEventListener('dragover',event=>{event.preventDefault();event.dataTransfer.dropEffect='copy';});
$('#canvas').addEventListener('drop',event=>{event.preventDefault();const key=event.dataTransfer.getData('application/flowreuse-module'),rect=$('#canvas').getBoundingClientRect();addModule(key,{x:(event.clientX-rect.left-state.pan.x)/state.zoom-114,y:(event.clientY-rect.top-state.pan.y)/state.zoom-35});});
$('#module-list').addEventListener('dragstart',event=>{if(state.busy){event.preventDefault();return;}const card=event.target.closest('[data-module]');if(card){event.dataTransfer.setData('application/flowreuse-module',card.dataset.module);event.dataTransfer.effectAllowed='copy';}});
$('#module-list').addEventListener('click',event=>{const card=event.target.closest('[data-module]');if(card)addModule(card.dataset.module);});
$('#module-search').addEventListener('input',renderModules);
$('#module-category').addEventListener('change',renderModules);
$('#canvas').addEventListener('click',event=>{
  if(state.busy)return;
  const output=event.target.closest('[data-output]'),input=event.target.closest('[data-input]'),edge=event.target.closest('[data-edge]');
  if(output){state.connection=state.connection===output.dataset.output?null:output.dataset.output;renderCanvas();}
  if(input)connect(input.dataset.input);
  if(edge){state.selectedEdge=edge.dataset.edge;state.selected=null;showPane('details');renderCanvas();renderInspector();$('.inspector').classList.add('open');}
});
$('#nodes').addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-node]')){event.preventDefault();selectNode(event.target.dataset.node);}});
$('#edges').addEventListener('keydown',event=>{const edge=event.target.closest('[data-edge]');if(edge&&(event.key==='Enter'||event.key===' ')){event.preventDefault();state.selectedEdge=edge.dataset.edge;state.selected=null;showPane('details');renderCanvas();renderInspector();$('.inspector').classList.add('open');}});
$('#inspector-content').addEventListener('input',event=>{
  if(state.busy)return;
  const input=event.target.closest('[data-param]');if(!input)return;
  const node=state.workflow.nodes.find(n=>n.id===state.selected),key=input.dataset.param;
  node.params[key]=input.type==='number'?(input.value===''?null:Number(input.value)):input.value;
  markDirty();renderCanvas();
});
$('#inspector-content').addEventListener('click',event=>{
  if(state.busy)return;
  if(event.target.closest('#delete-node,#delete-edge'))deleteSelected();
  if(event.target.closest('#view-code')){const node=state.workflow.nodes.find(n=>n.id===state.selected),module=moduleOf(node);modal(`${module.name} · Python v${node.version}`,`<pre>${esc(module.source)}</pre><p class="small muted">SHA-256：${esc(module.hash)}</p>`);}
});
$('#workflow-name').addEventListener('input',()=>{state.workflow.name=$('#workflow-name').value;markDirty();});
$('#save-button').addEventListener('click',async()=>{try{setBusy(true);await saveWorkflow();toast(`Saved version ${state.saved.number}`);}catch(error){toast(error.message,true);}finally{setBusy(false);}});
$('#run-button').addEventListener('click',runWorkflow);
$('#new-button').addEventListener('click',newWorkflow);
$('#templates-button').addEventListener('click',showTemplates);
$('#layout-button').addEventListener('click',autoLayout);
$('#fit-button').addEventListener('click',fit);
$('#zoom-in').addEventListener('click',()=>changeZoom(1.15));
$('#zoom-out').addEventListener('click',()=>changeZoom(1/1.15));
$('#validate-button').addEventListener('click',async()=>{try{await api('/api/validate',{workflow:state.workflow});toast('Workflow is valid.');}catch(error){toast(error.message,true);}});
$('#library-history').addEventListener('click',showSaved);
$('#editor-nav').addEventListener('click',()=>{$('#modal').close();$('#canvas').focus();});
$('#reset-input').addEventListener('click',()=>{$('#input-data').value=JSON.stringify(state.demoInput,null,2);toast('Input reset.');});
for(const tab of document.querySelectorAll('[data-tab]'))tab.addEventListener('click',()=>switchTab(tab.dataset.tab));
$('#result-content').addEventListener('click',event=>{
  if(event.target.closest('#view-run'))modal('Execution details',`<pre>${esc(JSON.stringify(state.lastRun,null,2))}</pre>`);
  if(event.target.closest('#download-result')){const blob=new Blob([JSON.stringify(state.lastRun.outputs,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`flowreuse-${state.lastRun.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
});
$('#history-content').addEventListener('click',async event=>{const button=event.target.closest('[data-run]');if(!button)return;try{const run=await api(`/api/runs/${button.dataset.run}`);modal(`${run.workflow_name} · ${run.status==='success'?'Success':'Execution record'}`,`<pre>${esc(JSON.stringify(run,null,2))}</pre>`);}catch(error){toast(error.message,true);}});
$('#modal-content').addEventListener('click',async event=>{
  const template=event.target.closest('[data-template]');if(template){loadTemplate(template.dataset.template);return;}
  const load=event.target.closest('[data-load]'),versions=event.target.closest('[data-versions]');
  try{if(load)await loadRevision(load.dataset.load);if(versions){const items=await api(`/api/workflows/${versions.dataset.versions}/revisions`);$('#modal-title').textContent='Workflow versions';$('#modal-content').innerHTML=items.map(item=>`<button class="history-item" data-load="${esc(item.revision_id)}"><span><strong>Version ${item.number}</strong><small>${esc(formatDate(item.created_at))}</small></span><span>Open ↗</span></button>`).join('');}}catch(error){toast(error.message,true);}
});
$('#modal-close').addEventListener('click',()=>$('#modal').close());
$('#modal').addEventListener('click',event=>{if(event.target===$('#modal')){const rect=$('#modal').getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)$('#modal').close();}});
document.addEventListener('keydown',event=>{
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();if(!state.busy)$('#save-button').click();return;}
  if(event.key==='Escape'){state.connection=null;$('.inspector').classList.remove('open');renderCanvas();}
  if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)||$('#modal').open)return;
  if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();deleteSelected();}
});
window.addEventListener('beforeunload',event=>{if(hasUnsavedChanges()){event.preventDefault();event.returnValue='';}});
let resizeTimer;
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(fit,150);});

function tr(source,variables={}){
  let value=state.language==='fr'?(FRENCH[source]||source):source;
  return value.replace(/\{(\w+)\}/g,(_,key)=>String(variables[key]??`{${key}}`));
}
const originalText=new WeakMap();
const originalAttributes=new WeakMap();
function translateText(source,language=state.language){
  if(language!=='fr')return source;
  if(FRENCH[source])return FRENCH[source];
  for(const [key,value] of Object.entries(FRENCH)){
    if(!key.includes('{'))continue;
    const names=[];
    const escaped=key.replace(/[.*+?^${}()|[\]\\]/g,'\\$&').replace(/\\\{(\w+)\\\}/g,(_,name)=>{names.push(name);return '(.+?)';});
    const match=source.match(new RegExp('^'+escaped+'$'));
    if(match)return value.replace(/\{(\w+)\}/g,(_,name)=>translateText(match[names.indexOf(name)+1],language));
  }
  const icon=source.match(/^([✓!▶▷]\s*)(.+)$/s);
  if(icon)return icon[1]+translateText(icon[2],language);
  return source;
}
let translationPending=false;
const observer=new MutationObserver(()=>{if(!translationPending){translationPending=true;requestAnimationFrame(()=>{translationPending=false;localize();});}});
function localize(){
  observer.disconnect();
  document.documentElement.lang=state.language;
  for(const element of document.querySelectorAll('[data-i18n]'))element.textContent=tr(element.dataset.i18n);
  for(const [attribute,data] of [['placeholder','i18nPlaceholder'],['aria-label','i18nAria'],['title','i18nTitle']])for(const element of document.querySelectorAll(`[data-${data.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())}]`))element.setAttribute(attribute,tr(element.dataset[data]));
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){
    const node=walker.currentNode;
    if(node.parentElement?.closest('script,style,pre,code,textarea,[data-preserve]'))continue;
    const current=node.nodeValue;
    let source=originalText.get(node);
    if(source===undefined||current!==translateText(source,'fr')&&current!==source)source=current;
    originalText.set(node,source);
    const match=source.match(/^(\s*)(.*?)(\s*)$/s);
    const value=match[1]+translateText(match[2])+match[3];
    if(node.nodeValue!==value)node.nodeValue=value;
  }
  for(const element of document.querySelectorAll('[aria-label],[title]')){
    const values=originalAttributes.get(element)||{};
    for(const attribute of ['aria-label','title'])if(element.hasAttribute(attribute)){
      let source=values[attribute],current=element.getAttribute(attribute);
      if(source===undefined||current!==translateText(source,'fr')&&current!==source)source=current;
      values[attribute]=source;element.setAttribute(attribute,translateText(source));
    }
    originalAttributes.set(element,values);
  }
  observer.observe(document.body,{subtree:true,childList:true,characterData:true});
}
function showPane(name){
  $('#copilot-pane').classList.toggle('hidden',name!=='copilot');$('#inspector-content').classList.toggle('hidden',name!=='details');
  $('#copilot-tab').classList.toggle('active',name==='copilot');$('#details-tab').classList.toggle('active',name==='details');
  $('.inspector').classList.add('open');
}
function renderSkillStatus(){
  if($('#skill-status'))$('#skill-status').textContent=state.skillSnapshot?tr('Skill snapshot: {id}',{id:state.skillSnapshot.generation.slice(0,8)}):'';
}
function renderProfile(){
  const profile=state.project?.ai;
  $('#profile-chip').textContent=profile?.configured?`${profile.provider==='ollama'?'Ollama':'API'} · ${profile.model}`:tr('Connect this project to an AI');
  $('#profile-chip').classList.toggle('configured',!!profile?.configured);
}
function renderChat(){
  $('#chat-messages').innerHTML=state.chat.length?state.chat.map(message=>`<div class="chat-message ${message.role==='user'?'user':'assistant'}"><span class="chat-role">${message.role==='user'?'You':'FlowReuse'}</span><div data-preserve>${esc(message.content)}</div>${message.metadata?.ai_calls?`<small>${esc(tr('Model calls: {count}',{count:message.metadata.ai_calls}))}${message.metadata.usage?.total_tokens?` · ${message.metadata.usage.total_tokens} tokens`:''}</small>`:''}</div>`).join(''):`<div class="chat-welcome"><span>✧</span><h3>${esc(tr('Describe your workflow'))}</h3><p>${esc(tr('Tell me the input, the rules and the result you want. I will build and connect the workflow.'))}</p><small>${esc(tr('Only registered capabilities can run. Missing capabilities are reported, never invented.'))}</small></div>`;
  $('#chat-messages').scrollTop=$('#chat-messages').scrollHeight;
  renderProfile();renderSkillStatus();
}
async function bootProject(identifier='default'){
  const data=await api('/api/bootstrap',undefined,identifier);
  Object.assign(state,{projectId:identifier,project:data.project,projects:data.projects,modules:data.modules,workflow:clone(data.workspace),templates:data.templates,demoInput:data.input,workflows:data.workflows,runs:data.runs,chat:data.chat,csrf:data.csrf,saved:null,dirty:true,selected:null,selectedEdge:null,connection:null,lastRun:null,skillSnapshot:data.skill_snapshot});
  $('#project-select').innerHTML=data.projects.map(project=>`<option value="${esc(project.id)}">${esc(project.name)}</option>`).join('');$('#project-select').value=identifier;
  try{
    localStorage.setItem('flowreuse.activeProject',identifier);
    const last=localStorage.getItem('flowreuse.'+identifier+'.activeRevision');
    if(last){const revision=await api(`/api/revisions/${encodeURIComponent(last)}`);state.workflow=revision.workflow;state.saved={workflow_id:revision.workflow_id,revision_id:revision.id,number:revision.number};state.dirty=false;}
  }catch{/* Stale local references never cross into another project's database. */}
  $('#workflow-name').value=state.workflow.name;$('#input-data').value=JSON.stringify(data.input,null,2);$('#chat-input').value='';
  $('#module-category').value='general';$('#module-search').value='';
  renderModules();renderCanvas();renderInspector();renderResult();renderHistory();renderChat();updateSaveState();showPane('copilot');localize();requestAnimationFrame(fit);
}
function showProjectForm(){
  modal(tr('New project'),`<form id="new-project-form"><p class="muted">${esc(tr('Separate workflows, runs, conversations, outputs and AI settings.'))}</p><label class="field"><span>${esc(tr('Project name'))}</span><input name="name" required maxlength="100" autocomplete="off"></label><button class="button primary" type="submit">${esc(tr('Create project'))}</button></form>`);
}
function showSettings(){
  const profile=state.project.ai;
  modal(tr('Project AI'),`<form id="ai-profile-form"><label class="field"><span>${esc(tr('Provider protocol'))}</span><select class="category-select" name="provider"><option value="compatible" ${profile.provider==='compatible'?'selected':''}>${esc(tr('OpenAI-compatible'))}</option><option value="ollama" ${profile.provider==='ollama'?'selected':''}>${esc(tr('Ollama (local)'))}</option></select></label><label class="field"><span>${esc(tr('Endpoint base URL'))}</span><input name="base_url" type="url" required value="${esc(profile.base_url)}"></label><label class="field"><span>${esc(tr('Model ID'))}</span><input name="model" required maxlength="200" value="${esc(profile.model)}" autocomplete="off"></label><p class="small muted">${esc(tr('Choose a model you have access to; no model is selected automatically.'))}</p><label class="field"><span>${esc(tr('API key'))} · ${esc(tr(profile.api_key_set?'Key saved for this endpoint':'No key saved'))}</span><input name="api_key" type="password" autocomplete="new-password" placeholder="${esc(tr('Leave empty to keep the existing key.'))}"></label><p class="small muted">${esc(tr('Keys are protected with Windows DPAPI and never included in skills.'))}</p><p class="small muted">${esc(tr('Prompt and workflow structure are sent only when you press Send. Business input is not attached.'))}</p><button class="button primary" type="submit">${esc(tr('Save AI settings'))}</button></form>`);
}
async function sendChat(event){
  event.preventDefault();if(state.busy)return;
  const message=$('#chat-input').value.trim();if(!message)return;
  if(!state.project.ai.configured){toast(tr('The AI connection must be configured first.'),true);showSettings();return;}
  try{
    setBusy(true);$('#run-button').textContent=tr('Building…');
    state.chat.push({role:'user',content:message});renderChat();$('#chat-input').value='';
    const result=await api('/api/chat',{message,workflow:state.workflow,workflow_id:state.saved?.workflow_id||null});
    state.chat.push({role:'assistant',content:result.message,metadata:{ai_calls:result.ai_calls,usage:result.usage}});
    if(result.workflow){state.workflow=result.workflow;state.saved=result.saved;state.dirty=false;state.lastRun=null;state.selected=null;state.selectedEdge=null;state.connection=null;rememberRevision();$('#workflow-name').value=state.workflow.name;state.workflows=await api('/api/workflows');renderCanvas();renderInspector();renderResult();updateSaveState();fit();toast(tr('Workflow updated on the canvas.'));}
    renderChat();
  }catch(error){state.chat.push({role:'assistant',content:error.message,metadata:{error:true}});renderChat();toast(error.message,true);}
  finally{setBusy(false);}
}
$('#copilot-tab').addEventListener('click',()=>showPane('copilot'));
$('#mobile-copilot').addEventListener('click',()=>showPane('copilot'));
$('#inspector-close').addEventListener('click',()=>$('.inspector').classList.remove('open'));
$('#details-tab').addEventListener('click',()=>showPane('details'));
$('#profile-chip').addEventListener('click',showSettings);
$('#ai-settings').addEventListener('click',showSettings);
$('#project-new').addEventListener('click',showProjectForm);
$('#chat-form').addEventListener('submit',sendChat);
$('#project-select').addEventListener('change',async event=>{
  const next=event.target.value;
  if(hasUnsavedChanges()&&!confirm(tr('Discard unsaved changes?'))){event.target.value=state.projectId;return;}
  try{setBusy(true);await bootProject(next);}catch(error){event.target.value=state.projectId;toast(error.message,true);}finally{setBusy(false);}
});
$('#modal-content').addEventListener('change',event=>{if(event.target.name==='provider'){const form=event.target.form;form.elements.base_url.value=event.target.value==='ollama'?'http://127.0.0.1:11434':'https://api.openai.com/v1';}});
$('#modal-content').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target;
  if(!['new-project-form','ai-profile-form'].includes(form.id))return;
  const button=form.querySelector('button[type=submit]');button.disabled=true;
  try{
    if(form.id==='new-project-form'){
      if(hasUnsavedChanges()&&!confirm(tr('Discard unsaved changes?')))return;
      const result=await api('/api/projects',{name:form.elements.name.value});$('#modal').close();await bootProject(result.project.id);toast(tr('Project created.'));
    }else{
      const data=Object.fromEntries(new FormData(form));
      if(!data.api_key)delete data.api_key;
      const result=await api('/api/project/ai',data);form.elements.api_key.value='';state.project=result.project;$('#modal').close();renderProfile();toast(tr('AI settings saved.'));
    }
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
$('#language-select').addEventListener('change',event=>{
  state.language=event.target.value;try{localStorage.setItem('flowreuse.language',state.language);}catch{}
  renderChat();localize();
});
$('#export-skill').addEventListener('click',async()=>{
  try{
    const response=await fetch('/api/skill/archive',{headers:{'X-FlowReuse-Project':state.projectId}});
    if(!response.ok)throw new Error('Skill export failed.');
    const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`${state.projectId}.frskill.zip`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(tr('Skill package exported.'));
  }catch(error){toast(error.message,true);}
});
$('#help-button').addEventListener('click',()=>modal(tr('How FlowReuse works'),`<div class="help-content"><p>${esc(tr('First conversation → connected DAG → frozen revision → repeat execution.'))}</p><p>${esc(tr('Each project has its own database, conversation, model profile and skill snapshots. This is local single-user isolation, not multi-user access control.'))}</p><p>${esc(tr('Successful code-only runs use no model. The copilot uses your selected model for planning. Arbitrary generated code is not executed.'))}</p><p>${esc(tr('Every skill invocation refreshes a versioned manifest.frskill.json and a short English SKILL.md without an AI call.'))}</p><code>Ctrl / ⌘ + S · Delete · Esc</code></div>`));
async function boot(){
  try{
    let identifier='default';try{state.language=localStorage.getItem('flowreuse.language')==='fr'?'fr':'en';identifier=localStorage.getItem('flowreuse.activeProject')||'default';}catch{}
    $('#language-select').value=state.language;localize();await bootProject(identifier);
  }catch(error){toast(tr('Unable to connect to the local service. Start the application and refresh.')+' '+error.message,true);}
}
boot();
