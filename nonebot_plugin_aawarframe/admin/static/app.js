'use strict';

const $ = id => document.getElementById(id);
const node = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
};

let token = sessionStorage.getItem('aawarframe-token') || '';
let selectedItem = null;
let aliases = [];
let searchTimer = null;
let searchVersion = 0;
let pendingDelete = null;
let previewItems = [];
let selectedPreview = null;
let htmlOptions = [];
let themeOptions = [];
let selectedTheme = 'default.css';
let editorFiles = [];
let selectedFile = null;
let editorRevision = '';
let editorOriginal = '';
let toastTimer = null;

function toast(message) {
  const target = $('toast');
  target.textContent = message;
  target.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => target.classList.remove('show'), 2600);
}

function expireSession() {
  token = '';
  sessionStorage.removeItem('aawarframe-token');
  $('console').hidden = true;
  $('login').hidden = false;
  $('password').value = '';
}

async function api(path, method = 'GET', body) {
  const headers = { Authorization: 'Bearer ' + token };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch('/api/' + path, {
    method, headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store'
  });
  if (response.status === 401) {
    expireSession();
    throw new Error('登录已失效，请重新输入管理口令。');
  }
  let data = {};
  try { data = await response.json(); } catch (_) { /* keep a useful fallback */ }
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : '操作未成功，请重试。');
    error.status = response.status;
    throw error;
  }
  return data;
}

function showError(id, error) {
  $(id).textContent = error && error.message ? error.message : String(error);
}

function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return '—';
  return value < 1 ? (value * 1000).toFixed(0) + ' ms' : value.toFixed(2) + ' s';
}

function openView(view) {
  for (const section of document.querySelectorAll('.page-view')) {
    section.hidden = section.id !== view + '-view';
  }
  for (const button of document.querySelectorAll('[data-view]')) {
    button.classList.toggle('active', button.dataset.view === view);
  }
  if (view === 'dashboard') loadDashboard();
  if (view === 'aliases') loadAliases();
  if (view === 'arbitration') loadArbitration();
  if (view === 'previews') loadPreviews();
  if (view === 'editor') loadEditorFiles();
}

async function enter() {
  await api('session');
  sessionStorage.setItem('aawarframe-token', token);
  $('login').hidden = true;
  $('console').hidden = false;
  openView('dashboard');
}

$('login-form').addEventListener('submit', async event => {
  event.preventDefault();
  token = $('password').value;
  $('login-error').textContent = '';
  const submit = $('login-form').querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    await enter();
    $('password').value = '';
  } catch (error) {
    showError('login-error', error);
  } finally {
    submit.disabled = false;
  }
});

$('logout').addEventListener('click', () => {
  expireSession();
  toast('已退出管理台。');
});

for (const button of document.querySelectorAll('[data-view]')) {
  button.addEventListener('click', () => openView(button.dataset.view));
}

/* Dashboard */
async function loadDashboard() {
  $('dashboard-error').textContent = '';
  try {
    const data = await api('status');
    $('connection-label').textContent = '服务正常';
    $('stat-resources').textContent = Number(data.resource_count || 0).toLocaleString('zh-CN');
    $('stat-aliases').textContent = Number(data.alias_count || 0).toLocaleString('zh-CN');
    $('stat-subscriptions').textContent = Number(data.subscription_count || 0).toLocaleString('zh-CN');
    $('stat-commands').textContent = Number(data.enabled_command_count || 0).toLocaleString('zh-CN');
    $('stat-command-detail').textContent = (data.enabled_command_count || 0) + ' / ' + (data.command_count || 0) + ' 项命令已启用';
    $('bot-count').textContent = (data.bot_count || 0) + ' 个 Bot';
    $('resource-total').textContent = Number(data.resource_count || 0).toLocaleString('zh-CN') + ' 项';

    const protocols = $('protocol-list');
    protocols.replaceChildren();
    if (!data.protocols || !data.protocols.length) {
      protocols.append(node('p', '暂未检测到已注册的协议适配器。', 'empty'));
    } else {
      for (const protocol of data.protocols) {
        const card = node('div', undefined, 'protocol-card');
        card.append(node('span', protocol.name.toLowerCase().includes('qq') ? 'Q' : protocol.name.toLowerCase().includes('onebot') ? 'O' : 'P', 'protocol-symbol'));
        const details = node('div');
        details.append(node('strong', protocol.name));
        details.append(node('small', (protocol.bots || 0) + ' 个在线 Bot'));
        card.append(details);
        protocols.append(card);
      }
    }

    const metrics = data.renderer || {};
    $('metric-render-count').textContent = Number(metrics.render_count || 0).toLocaleString('zh-CN');
    $('metric-hit-rate').textContent = (Number(metrics.cache_hit_rate || 0) * 100).toFixed(1) + '%';
    $('metric-average').textContent = formatDuration(metrics.average_render_seconds);
    $('metric-p95').textContent = formatDuration(metrics.p95_render_seconds);

    const body = $('resource-list');
    body.replaceChildren();
    if (!data.resources || !data.resources.length) {
      const row = node('tr'); const cell = node('td', '没有可展示的资源索引。', 'empty');
      cell.colSpan = 4; row.append(cell); body.append(row);
    } else {
      for (const resource of data.resources) {
        const row = node('tr');
        row.append(node('td', resource.title || resource.name));
        row.append(node('td', Number(resource.count || 0).toLocaleString('zh-CN')));
        row.append(node('td', Number(resource.enabled || 0).toLocaleString('zh-CN')));
        const status = node('td');
        const tag = node('span', undefined, 'state-tag');
        tag.append(node('i')); tag.append(document.createTextNode('已加载'));
        status.append(tag); row.append(status); body.append(row);
      }
    }
  } catch (error) {
    $('connection-label').textContent = '连接异常';
    showError('dashboard-error', error);
  }
}
$('refresh-dashboard').addEventListener('click', loadDashboard);

/* Resource aliases */
function describeItem(item) {
  const box = node('div');
  box.append(node('strong', item.name));
  box.append(node('p', item.name_en || item.id));
  return box;
}
function tradeBadge(item) {
  return node('span', item.tradable ? '可交易' : '游戏物品', item.tradable ? 'badge trade' : 'badge');
}
function chooseItem(item) {
  selectedItem = item;
  $('item-results').replaceChildren();
  $('selected-item').replaceChildren(describeItem(item), tradeBadge(item));
  $('selected-item').hidden = false;
  $('add-alias').disabled = false;
  $('form-message').textContent = '已选定物品，保存后立即生效。';
}
async function findItems() {
  const version = ++searchVersion;
  const query = $('item-query').value.trim();
  selectedItem = null;
  $('selected-item').hidden = true;
  $('add-alias').disabled = true;
  $('item-results').replaceChildren();
  $('form-error').textContent = '';
  if (!query) return;
  try {
    const data = await api('items?' + new URLSearchParams({ q: query }));
    if (version !== searchVersion) return;
    for (const item of data.items || []) {
      const button = node('button', undefined, 'item-option');
      button.type = 'button';
      button.append(describeItem(item), tradeBadge(item));
      button.addEventListener('click', () => chooseItem(item));
      $('item-results').append(button);
    }
    if (!data.items || !data.items.length) {
      $('item-results').append(node('p', '未找到物品，请换一个名称搜索。', 'empty'));
    }
  } catch (error) {
    if (version === searchVersion) showError('form-error', error);
  }
}
$('item-query').addEventListener('input', () => {
  searchVersion++;
  selectedItem = null;
  $('selected-item').hidden = true;
  $('add-alias').disabled = true;
  $('item-results').replaceChildren();
  clearTimeout(searchTimer);
  searchTimer = setTimeout(findItems, 250);
});
function drawAliases() {
  const key = $('alias-filter').value.trim().toLocaleLowerCase();
  const rows = aliases.filter(item =>
    [item.alias, item.name, item.name_en].join(' ').toLocaleLowerCase().includes(key)
  );
  $('alias-count').textContent = aliases.length + ' 个别名';
  $('alias-total').textContent = aliases.length + ' 条';
  const list = $('alias-list');
  list.replaceChildren();
  for (const entry of rows) {
    const row = node('div', undefined, 'alias-row');
    const info = node('div');
    info.append(node('strong', entry.alias));
    info.append(node('p', entry.name + (entry.name_en ? ' · ' + entry.name_en : '')));
    const remove = node('button', '删除', 'text-button');
    remove.type = 'button';
    remove.addEventListener('click', () => {
      pendingDelete = entry;
      $('delete-message').textContent = '确定删除“' + entry.alias + '”与“' + entry.name + '”的对应关系？';
      $('delete-dialog').showModal();
    });
    row.append(info, remove);
    list.append(row);
  }
  if (!rows.length) {
    list.append(node('p', aliases.length ? '没有符合筛选条件的别名。' : '还没有别名，从左侧添加第一个吧。', 'empty'));
  }
}
async function loadAliases() {
  $('list-error').textContent = '';
  try {
    aliases = (await api('aliases')).items || [];
    drawAliases();
  } catch (error) {
    showError('list-error', error);
  }
}
$('alias-filter').addEventListener('input', drawAliases);
$('alias-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!selectedItem) return;
  const button = $('add-alias');
  button.disabled = true;
  $('form-error').textContent = '';
  try {
    await api('aliases', 'POST', { item_id: selectedItem.id, alias: $('alias-name').value.trim() });
    $('alias-name').value = '';
    $('form-message').textContent = '别名已添加并立即生效。';
    toast('别名已保存。');
    await loadAliases();
  } catch (error) {
    showError('form-error', error);
  } finally {
    button.disabled = !selectedItem;
  }
});
$('delete-cancel').addEventListener('click', () => $('delete-dialog').close());
$('delete-confirm').addEventListener('click', async () => {
  if (!pendingDelete) return;
  const button = $('delete-confirm');
  button.disabled = true;
  $('list-error').textContent = '';
  try {
    await api('aliases', 'DELETE', { item_id: pendingDelete.item_id, alias: pendingDelete.alias });
    $('delete-dialog').close();
    toast('别名已删除。');
    await loadAliases();
  } catch (error) {
    showError('list-error', error);
    $('delete-dialog').close();
  } finally {
    button.disabled = false;
    pendingDelete = null;
  }
});

/* Arbitration */
let arbitrationNodes = [];
async function loadArbitration() {
  $('arbitration-error').textContent = '';
  try {
    arbitrationNodes = (await api('arbitration/nodes')).items || [];
    $('arbitration-count').textContent = arbitrationNodes.length + ' 个节点';
    drawArbitration();
  } catch (error) {
    showError('arbitration-error', error);
  }
}
function drawArbitration() {
  const list = $('arbitration-list');
  list.replaceChildren();
  const key = $('arbitration-filter').value.trim().toLocaleLowerCase();
  const rows = arbitrationNodes.filter(item =>
    [item.id, item.name, item.systemName, item.missionName, item.factionName,
      item.arbitration.grade, item.arbitration.vitus_per_minute].join(' ').toLocaleLowerCase().includes(key)
  );
  for (const item of rows) {
    const row = node('form', undefined, 'arbitration-edit');
    row.dataset.node = item.id;
    const info = node('div');
    info.append(node('strong', item.name + ' / ' + item.systemName));
    info.append(node('p', item.missionName + ' · ' + item.factionName));
    row.append(info);
    const grade = node('select');
    grade.setAttribute('aria-label', item.name + '评级');
    for (const value of ['S', 'A', 'B', 'C', 'D', 'F']) {
      const option = node('option', value); option.value = value; grade.append(option);
    }
    grade.value = item.arbitration.grade;
    const vitus = node('input');
    vitus.type = 'number'; vitus.min = '0'; vitus.step = 'any'; vitus.required = true;
    vitus.value = item.arbitration.vitus_per_minute;
    vitus.setAttribute('aria-label', item.name + '每分钟生息精华');
    const save = node('button', '保存', 'button primary'); save.type = 'submit';
    row.append(grade, vitus, save);
    row.addEventListener('submit', async event => {
      event.preventDefault();
      save.disabled = true;
      $('arbitration-error').textContent = '';
      try {
        const value = Number(vitus.value);
        if (!Number.isFinite(value) || value < 0) throw new Error('掉落数量应为大于等于 0 的数值');
        await api('arbitration/nodes', 'PUT', { node_id: item.id, grade: grade.value, vitus_per_minute: value });
        item.arbitration = { grade: grade.value, vitus_per_minute: value };
        save.textContent = '已保存';
        toast(item.name + ' 的仲裁数据已更新。');
      } catch (error) {
        showError('arbitration-error', error);
      } finally {
        save.disabled = false;
      }
    });
    list.append(row);
  }
  if (!rows.length) list.append(node('p', '没有符合条件的仲裁节点。', 'empty'));
}
$('arbitration-filter').addEventListener('input', drawArbitration);

/* Render previews: one HTML binding per feature, one global CSS theme. */
function fillSelect(select, options, selected) {
  select.replaceChildren();
  for (const item of options) {
    const option = node('option', item.title);
    option.value = item.id;
    select.append(option);
  }
  select.value = selected || '';
}
async function loadPreviews() {
  $('preview-error').textContent = '';
  try {
    const data = await api('previews');
    previewItems = data.items || [];
    htmlOptions = data.html_options || [];
    themeOptions = data.theme_options || [];
    selectedTheme = data.selected_theme || 'default.css';
    $('preview-count').textContent = previewItems.length + ' 项';
    fillSelect($('preview-theme-select'), themeOptions, selectedTheme);
    drawPreviewList();
    const current = selectedPreview && previewItems.find(item => item.id === selectedPreview.id);
    const next = current || previewItems[0];
    if (next) await selectPreview(next.id);
  } catch (error) {
    showError('preview-error', error);
  }
}
function drawPreviewList() {
  const key = $('preview-filter').value.trim().toLocaleLowerCase();
  const list = $('preview-list');
  list.replaceChildren();
  const rows = previewItems.filter(item =>
    [item.title, item.description, item.template].join(' ').toLocaleLowerCase().includes(key)
  );
  for (const item of rows) {
    const button = node('button', undefined, 'preview-option' + (selectedPreview && selectedPreview.id === item.id ? ' active' : ''));
    button.type = 'button';
    button.append(node('strong', item.title), node('small', item.description));
    button.append(node('small', '固定离线预览数据 · ' + (item.selected_template || item.template), 'preview-data-ready'));
    button.addEventListener('click', () => selectPreview(item.id));
    list.append(button);
  }
  if (!rows.length) list.append(node('p', '没有匹配的功能模板。', 'empty'));
}
async function renderPreview(id, targetImage, errorId) {
  const error = $(errorId);
  error.textContent = '';
  try {
    const result = await api('previews', 'POST', { template: id });
    $('preview-raw-template').textContent = result.raw_template || '';
    $('preview-rendered-html').textContent = result.rendered_html || '';
    $('preview-template-meta').textContent = 'HTML：' + result.html_template + ' · CSS：' + result.theme;
    const source = 'data:' + (result.media_type || 'image/webp') + ';base64,' + result.images[0];
    targetImage.src = source;
    targetImage.hidden = false;
    return true;
  } catch (failure) {
    showError(errorId, failure);
    return false;
  }
}
async function selectPreview(id) {
  selectedPreview = previewItems.find(item => item.id === id) || null;
  drawPreviewList();
  if (!selectedPreview) return;
  $('preview-title').textContent = selectedPreview.title;
  $('preview-description').textContent = selectedPreview.description + ' · 功能绑定独立 HTML，所有功能共享全局 CSS。';
  fillSelect($('preview-template-select'), htmlOptions, selectedPreview.selected_template || selectedPreview.template);
  fillSelect($('preview-theme-select'), themeOptions, selectedTheme);
  $('preview-image').hidden = true;
  $('preview-image-wrap').querySelector('.preview-placeholder').hidden = false;
  $('save-preview-selection').disabled = false;
  $('preview-error').textContent = '';
  $('preview-data-meta').textContent = '数据来源：项目内固定预览数据 · rendering/preview_data.py';
  $('preview-empty-message').textContent = '正在使用固定数据生成原始模板、填充后的 HTML 和最终图片…';
  const success = await renderPreview(id, $('preview-image'), 'preview-error');
  if (success) $('preview-image-wrap').querySelector('.preview-placeholder').hidden = true;
  else $('preview-empty-message').textContent = '固定预览数据渲染失败，请检查 HTML 模板或 CSS 主题。';
}
async function applyPreviewSelection() {
  if (!selectedPreview) return;
  const button = $('save-preview-selection');
  button.disabled = true;
  $('preview-error').textContent = '';
  try {
    const htmlTemplate = $('preview-template-select').value;
    const theme = $('preview-theme-select').value;
    await api('previews/selection', 'PUT', {
      feature: selectedPreview.id,
      html_template: htmlTemplate,
      theme
    });
    selectedPreview.selected_template = htmlTemplate;
    selectedTheme = theme;
    for (const item of previewItems) item.selected_theme = theme;
    fillSelect($('preview-theme-select'), themeOptions, selectedTheme);
    toast('已更新当前功能的 HTML 绑定和全局 CSS 主题。');
    const success = await renderPreview(selectedPreview.id, $('preview-image'), 'preview-error');
    if (success) $('preview-image-wrap').querySelector('.preview-placeholder').hidden = true;
    drawPreviewList();
  } catch (error) {
    showError('preview-error', error);
  } finally {
    button.disabled = false;
  }
}
$('preview-filter').addEventListener('input', drawPreviewList);
$('refresh-preview').addEventListener('click', loadPreviews);
$('save-preview-selection').addEventListener('click', applyPreviewSelection);

/* Template editor: manage HTML and CSS files only. Bindings and theme selection live in previews. */
let editorMode = 'idle';
let selectedKind = null;

function editorHasUnsavedChanges() {
  return $('editor-content').value !== editorOriginal
    || (editorMode === 'new' && Boolean($('editor-new-name').value.trim()));
}

async function loadEditorFiles() {
  $('editor-error').textContent = '';
  try {
    editorFiles = (await api('editor/files')).items || [];
    drawEditorFiles();
    if (selectedFile && !editorFiles.some(item => item.name === selectedFile)) {
      clearEditorSelection();
    } else if (selectedFile) {
      const file = editorFiles.find(item => item.name === selectedFile);
      if (file) updateEditorState();
    } else if (editorMode !== 'new') {
      clearEditorSelection();
    }
  } catch (error) {
    showError('editor-error', error);
  }
}

function drawEditorFiles() {
  const key = $('editor-filter').value.trim().toLocaleLowerCase();
  const drawGroup = (kind, targetId, countId) => {
    const list = $(targetId);
    list.replaceChildren();
    const all = editorFiles.filter(item => item.kind === kind);
    const rows = all.filter(item => item.name.toLocaleLowerCase().includes(key));
    $(countId).textContent = all.length + ' 个文件';
    for (const item of rows) {
      const button = node('button', undefined, 'editor-file-option' + (selectedFile === item.name ? ' active' : ''));
      button.type = 'button';
      button.append(node('span', kind === 'html' ? 'HTML' : 'CSS', 'file-type'));
      button.append(node('span', item.name.replace(/^(html|css)\//, ''), 'editor-file-name'));
      if (item.overridden) button.append(node('i', undefined, 'override-dot'));
      button.addEventListener('click', () => selectEditorFile(item.name));
      list.append(button);
    }
    if (!rows.length) list.append(node('p', key ? '没有匹配的文件。' : '暂无文件。', 'empty'));
  };
  drawGroup('html', 'editor-html-list', 'editor-html-count');
  drawGroup('css', 'editor-css-list', 'editor-css-count');
}

function clearEditorSelection() {
  selectedFile = null;
  selectedKind = null;
  editorMode = 'idle';
  editorRevision = '';
  editorOriginal = '';
  $('editor-file-name').textContent = '选择一个文件';
  $('editor-file-status').textContent = '未选择';
  $('editor-content').value = '';
  $('editor-content').disabled = true;
  $('editor-new-file-row').hidden = true;
  $('editor-new-name').value = '';
  $('editor-message').textContent = '';
  updateEditorState();
  drawEditorFiles();
}

function updateEditorState() {
  const file = editorFiles.find(item => item.name === selectedFile);
  const isNew = editorMode === 'new';
  const dirty = editorHasUnsavedChanges();
  const canSave = isNew
    ? Boolean($('editor-new-name').value.trim() && $('editor-content').value.trim())
    : Boolean(selectedFile && dirty);
  $('editor-save').disabled = !canSave;
  $('editor-save').textContent = isNew ? '创建并保存' : '保存修改';
  $('editor-reset').hidden = isNew || !file || !file.overridden || file.custom || file.version || file.theme;
  $('editor-reset').disabled = $('editor-reset').hidden;
  $('editor-delete').hidden = isNew || !file || !(file.custom || file.version || file.theme);
  $('editor-delete').disabled = $('editor-delete').hidden;
  $('editor-new-file-row').hidden = !isNew;
  if (isNew) {
    $('editor-file-status').textContent = selectedKind === 'html' ? '新建 HTML 模板' : '新建 CSS 主题';
  } else if (selectedFile) {
    $('editor-file-status').textContent = dirty
      ? '有未保存修改'
      : (file && file.overridden ? '本地自定义文件' : '安装包内置文件');
  } else {
    $('editor-file-status').textContent = '未选择';
  }
  $('editor-file-status').classList.toggle('modified', dirty);
}

async function selectEditorFile(name) {
  if ((editorMode === 'new' || selectedFile) && editorHasUnsavedChanges()) {
    if (!window.confirm('当前文件有未保存修改，确定放弃并切换文件吗？')) return;
  }
  $('editor-error').textContent = '';
  try {
    const data = await api('editor/file?' + new URLSearchParams({ name }));
    selectedFile = name;
    selectedKind = name.startsWith('css/') ? 'css' : 'html';
    editorMode = 'edit';
    editorRevision = data.revision;
    editorOriginal = data.content;
    $('editor-file-name').textContent = name;
    $('editor-content').disabled = false;
    $('editor-content').value = data.content;
    $('editor-new-name').value = '';
    $('editor-new-file-row').hidden = true;
    $('editor-message').textContent = '';
    drawEditorFiles();
    updateEditorState();
  } catch (error) {
    showError('editor-error', error);
  }
}

function startNewEditorFile(kind) {
  if ((editorMode === 'new' || selectedFile) && editorHasUnsavedChanges()) {
    if (!window.confirm('当前文件有未保存修改，确定放弃并新建文件吗？')) return;
  }
  selectedFile = null;
  selectedKind = kind;
  editorMode = 'new';
  editorRevision = '';
  editorOriginal = kind === 'html'
    ? '<!doctype html>\n<html lang="zh-CN">\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=device-width,initial-scale=1">\n  <title>{{ card.title }}</title>\n</head>\n<body>\n  <main>\n    <h1>{{ card.title }}</h1>\n  </main>\n</body>\n</html>\n'
    : '/* Aa Warframe custom theme */\n';
  $('editor-file-name').textContent = kind === 'html' ? '新建 HTML 模板' : '新建 CSS 主题';
  $('editor-content').disabled = false;
  $('editor-content').value = editorOriginal;
  $('editor-new-name').value = '';
  $('editor-new-file-row').hidden = false;
  $('editor-new-file-hint').textContent = kind === 'html'
    ? '保存时会自动添加 .html 扩展名；新模板不需要预先绑定功能。'
    : '保存时会自动添加 .css 扩展名；主题启用与切换请在渲染预览中完成。';
  $('editor-message').textContent = '';
  $('editor-error').textContent = '';
  drawEditorFiles();
  updateEditorState();
  $('editor-new-name').focus();
}

$('editor-content').addEventListener('input', updateEditorState);
$('editor-filter').addEventListener('input', drawEditorFiles);
$('editor-new-name').addEventListener('input', updateEditorState);
$('editor-new-html').addEventListener('click', () => startNewEditorFile('html'));
$('editor-new-css').addEventListener('click', () => startNewEditorFile('css'));

async function saveEditorFile() {
  const button = $('editor-save');
  button.disabled = true;
  $('editor-error').textContent = '';
  $('editor-message').textContent = '正在保存文件…';
  try {
    if (editorMode === 'new') {
      const data = await api('editor/files', 'POST', {
        kind: selectedKind,
        name: $('editor-new-name').value.trim(),
        content: $('editor-content').value
      });
      editorFiles = (await api('editor/files')).items || [];
      drawEditorFiles();
      editorMode = 'idle';
      $('editor-new-name').value = '';
      $('editor-message').textContent = '新文件已创建。';
      await selectEditorFile(data.name);
      toast('文件已创建并保存。');
      return;
    }
    if (!selectedFile) return;
    const data = await api('editor/file', 'PUT', {
      name: selectedFile,
      content: $('editor-content').value,
      revision: editorRevision
    });
    editorRevision = data.revision;
    editorOriginal = $('editor-content').value;
    editorFiles = (await api('editor/files')).items || [];
    drawEditorFiles();
    updateEditorState();
    $('editor-message').textContent = '保存成功。';
    toast('文件修改已保存。');
  } catch (error) {
    $('editor-message').textContent = '';
    showError('editor-error', error);
  } finally {
    updateEditorState();
  }
}

async function resetEditorFile() {
  const file = editorFiles.find(item => item.name === selectedFile);
  if (!selectedFile || !file || !file.overridden || file.custom || file.version || file.theme) return;
  if (!window.confirm('恢复这个文件的安装包内置版本？本地覆盖将被删除。')) return;
  $('editor-reset').disabled = true;
  try {
    await api('editor/file?' + new URLSearchParams({ name: selectedFile }), 'DELETE');
    editorFiles = (await api('editor/files')).items || [];
    await selectEditorFile(selectedFile);
    toast('已恢复安装包内置版本。');
  } catch (error) {
    showError('editor-error', error);
  } finally {
    updateEditorState();
  }
}

async function deleteEditorFile() {
  const file = editorFiles.find(item => item.name === selectedFile);
  if (!file || !(file.custom || file.version || file.theme)) return;
  if (!window.confirm('确定删除自定义文件「' + selectedFile + '」？如果预览中正在使用它，对应选择会自动恢复默认。')) return;
  try {
    await api('editor/file?' + new URLSearchParams({ name: selectedFile }), 'DELETE');
    editorFiles = (await api('editor/files')).items || [];
    clearEditorSelection();
    toast('自定义文件已删除。');
  } catch (error) {
    showError('editor-error', error);
  }
}

$('editor-save').addEventListener('click', saveEditorFile);
$('editor-reset').addEventListener('click', resetEditorFile);
$('editor-delete').addEventListener('click', deleteEditorFile);

/* Restore an existing session when the page is reopened. */
if (token) {
  enter().catch(error => {
    showError('login-error', error);
    if (token) expireSession();
  });
}
