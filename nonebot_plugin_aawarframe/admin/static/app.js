'use strict';
const $=id=>document.getElementById(id);
let token=sessionStorage.getItem('aawarframe-token')||'', selected=null, aliases=[], searchTimer, searchVersion=0, pendingDelete=null;
function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
async function api(path,method='GET',body){
  const response=await fetch('/api/'+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
  if(response.status===401){sessionStorage.removeItem('aawarframe-token');$('console').hidden=true;$('login').hidden=false;throw Error('登录口令不正确或登录已失效。');}
  const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'操作未成功，请重试。');return data;
}
function describe(item){const box=node('div');box.append(node('strong',item.name),node('p',item.name_en||item.id,'muted'));return box;}
function tradeBadge(item){return node('span',item.tradable?'可交易':'游戏物品',item.tradable?'badge trade':'badge');}
function choose(item){selected=item;$('item-results').replaceChildren();$('selected-item').replaceChildren(describe(item),tradeBadge(item));$('selected-item').hidden=false;$('add-alias').disabled=false;$('form-message').textContent='已选定物品，保存后立即生效。';}
async function findItems(){const version=++searchVersion;const query=$('item-query').value.trim();selected=null;$('selected-item').hidden=true;$('add-alias').disabled=true;$('item-results').replaceChildren();$('form-error').textContent='';if(!query)return;
  try{const data=await api('items?'+new URLSearchParams({q:query}));if(version!==searchVersion)return;
    for(const item of data.items){const button=node('button',undefined,'item-option');button.type='button';button.append(describe(item),tradeBadge(item));button.onclick=()=>choose(item);$('item-results').append(button);}
    if(!data.items.length)$('item-results').append(node('p','未找到物品，请换一个名称搜索。','empty'));
  }catch(e){if(version===searchVersion)$('form-error').textContent=e.message;}}
$('item-query').oninput=()=>{searchVersion++;selected=null;$('selected-item').hidden=true;$('add-alias').disabled=true;$('item-results').replaceChildren();clearTimeout(searchTimer);searchTimer=setTimeout(findItems,250);};
function drawAliases(){const key=$('alias-filter').value.toLocaleLowerCase();$('alias-list').replaceChildren();const rows=aliases.filter(a=>[a.alias,a.name,a.name_en].join(' ').toLocaleLowerCase().includes(key));$('alias-count').textContent=aliases.length+' 个别名';
  for(const entry of rows){const row=node('div',undefined,'alias-row');const text=node('div');text.append(node('strong',entry.alias),node('p',entry.name+(entry.name_en?' · '+entry.name_en:''),'muted'));const remove=node('button','删除','text-button');remove.type='button';remove.onclick=()=>{pendingDelete=entry;$('delete-message').textContent='确定删除“'+entry.alias+'”与“'+entry.name+'”的对应关系？';$('delete-dialog').showModal();};row.append(text,remove);$('alias-list').append(row);}
  if(!rows.length)$('alias-list').append(node('p',aliases.length?'没有符合筛选条件的别名。':'还没有别名，从上方添加第一个吧。','empty'));}
async function loadAliases(){aliases=(await api('aliases')).items;drawAliases();}
async function enter(){await api('session');await loadAliases();$('login').hidden=true;$('console').hidden=false;sessionStorage.setItem('aawarframe-token',token);}
$('login-form').onsubmit=async e=>{e.preventDefault();token=$('password').value;$('login-error').textContent='';try{await enter();$('password').value='';}catch(error){$('login-error').textContent=error.message;}};
$('logout').onclick=()=>{token='';sessionStorage.removeItem('aawarframe-token');$('console').hidden=true;$('login').hidden=false;};
$('alias-filter').oninput=drawAliases;
$('alias-form').onsubmit=async e=>{e.preventDefault();if(!selected)return;$('add-alias').disabled=true;$('form-error').textContent='';try{await api('aliases','POST',{item_id:selected.id,alias:$('alias-name').value.trim()});$('alias-name').value='';$('form-message').textContent='别名已添加。';await loadAliases();}catch(error){$('form-error').textContent=error.message;}finally{$('add-alias').disabled=!selected;}};
$('delete-cancel').onclick=()=>$('delete-dialog').close();
$('delete-confirm').onclick=async()=>{if(!pendingDelete)return;$('delete-confirm').disabled=true;try{await api('aliases','DELETE',{item_id:pendingDelete.item_id,alias:pendingDelete.alias});$('delete-dialog').close();await loadAliases();}catch(error){$('list-error').textContent=error.message;$('delete-dialog').close();}finally{$('delete-confirm').disabled=false;pendingDelete=null;}};
if(token)enter().catch(error=>{$('login-error').textContent=error.message;});

let arbitrationNodes=[];
async function openView(view){
  for(const button of document.querySelectorAll('[data-view]'))button.classList.toggle('active',button.dataset.view===view);
  $('aliases-view').hidden=view!=='aliases';$('arbitration-view').hidden=view!=='arbitration';$('alias-count').hidden=view!=='aliases';
  $('page-title').textContent=view==='aliases'?'别名管理':'仲裁管理';
  $('page-description').textContent=view==='aliases'?'给物品添加常用称呼，查询时便可使用这个名字。':'维护仲裁节点的评级和每分钟生息精华掉落记录。';
  if(view==='arbitration'){
    try{arbitrationNodes=(await api('arbitration/nodes')).items;drawArbitration();}catch(error){$('arbitration-error').textContent=error.message;}
  }
}
function drawArbitration(){
  $('arbitration-list').replaceChildren();const key=$('arbitration-filter').value.trim().toLowerCase();
  for(const item of arbitrationNodes.filter(n=>[n.id,n.name,n.systemName,n.missionName,n.factionName,n.arbitration.grade].join(' ').toLowerCase().includes(key))){
    const row=node('form',undefined,'arbitration-edit');row.dataset.node=item.id;
    const info=node('div');info.append(node('strong',item.name+' / '+item.systemName),node('p',item.missionName+' · '+item.factionName,'muted'));row.append(info);
    const grade=node('select');grade.setAttribute('aria-label',item.name+'评级');
    for(const value of ['S','A','B','C','D','F']){const option=node('option',value);option.value=value;grade.append(option);}grade.value=item.arbitration.grade;
    const vitus=node('input');vitus.type='number';vitus.min='0';vitus.step='any';vitus.required=true;vitus.value=item.arbitration.vitus_per_minute;vitus.setAttribute('aria-label',item.name+'每分钟生息精华');
    const save=node('button','保存','primary');row.append(grade,vitus,save);
    row.onsubmit=async e=>{e.preventDefault();save.disabled=true;$('arbitration-error').textContent='';try{const value=Number(vitus.value);if(!Number.isFinite(value)||value<0)throw Error('掉落数量应为大于等于 0 的数值');await api('arbitration/nodes','PUT',{node_id:item.id,grade:grade.value,vitus_per_minute:value});item.arbitration={grade:grade.value,vitus_per_minute:value};save.textContent='已保存';}catch(error){$('arbitration-error').textContent=error.message;}finally{save.disabled=false;}};
    $('arbitration-list').append(row);
  }
}
for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>openView(button.dataset.view);
$('arbitration-filter').oninput=drawArbitration;
