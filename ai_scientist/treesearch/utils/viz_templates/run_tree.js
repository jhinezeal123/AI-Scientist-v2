const treeData = "PLACEHOLDER_TREE_DATA";
const stageNames = ['Implementation', 'Tuning', 'Research', 'Ablation'];
const svgNS = 'http://www.w3.org/2000/svg';
const nodeElements = new Map();
const byId = new Map(treeData.nodes.map(node => [node.id, node]));
const text = value => value == null ? '' : Array.isArray(value) ? value.map(text).join('\n') : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
const number = value => typeof value === 'number' && Number.isFinite(value) ? Number(value.toFixed(6)).toString() : 'Chưa có';
function svgElement(tag, attributes, content) {
  const element = document.createElementNS(svgNS, tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  if (content != null) element.textContent = content;
  return element;
}
function showSection(section, target, value) {
  const content = text(value);
  document.getElementById(section).hidden = !content;
  document.getElementById(target).textContent = content;
}
function showMetrics(metric) {
  const container = document.getElementById('metrics');
  container.replaceChildren();
  const groups = metric?.metric_names || [];
  document.getElementById('metrics-section').hidden = !groups.length;
  for (const group of groups) {
    const heading = document.createElement('h3');
    heading.textContent = group.metric_name;
    const direction = document.createElement('p');
    direction.className = 'muted';
    direction.textContent = `${group.lower_is_better ? 'Minimize' : 'Maximize'}${group.description ? ' · ' + group.description : ''}`;
    const scroll = document.createElement('div');
    scroll.className = 'table-scroll';
    const table = document.createElement('table');
    const head = document.createElement('thead');
    const row = document.createElement('tr');
    for (const label of ['Dataset', 'Giá trị cuối', 'Tốt nhất']) {
      const cell = document.createElement('th'); cell.textContent = label; cell.scope = 'col'; row.append(cell);
    }
    head.append(row); table.append(head);
    const body = document.createElement('tbody');
    for (const item of group.data || []) {
      const row = document.createElement('tr');
      for (const value of [item.dataset_name, number(item.final_value), number(item.best_value)]) {
        const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
      }
      body.append(row);
    }
    table.append(body); scroll.append(table); container.append(heading, direction, scroll);
  }
}
function selectNode(node) {
  for (const [id, element] of nodeElements) element.setAttribute('aria-pressed', String(id === node.id));
  document.getElementById('node-detail').hidden = false;
  document.getElementById('node-heading').textContent = `Node ${node.index + 1} · ${node.id.slice(0, 8)}`;
  const stage = document.getElementById('node-stage');
  stage.textContent = `${node.stage} · ${stageNames[node.stage - 1]}`;
  stage.style.setProperty('--stage-color', `var(--s${node.stage})`);
  document.getElementById('node-action').textContent = node.action;
  document.getElementById('node-status').textContent = node.is_buggy === true ? 'Có lỗi' : node.is_buggy === false ? 'Thành công' : 'Chưa đánh giá';
  document.getElementById('node-time').textContent = node.exec_time == null ? '' : `Thời gian node: ${number(node.exec_time)} giây`;
  document.getElementById('node-id').textContent = node.id;
  document.getElementById('plan').textContent = node.plan || 'Chưa có mô tả thay đổi.';
  showSection('analysis-section', 'analysis', node.analysis);
  showSection('feedback-section', 'feedback', node.feedback);
  showSection('timing-section', 'timing', node.exec_time_feedback);
  showSection('datasets-section', 'datasets', node.datasets);
  showSection('log-section', 'log', node.term_out);
  showSection('code-section', 'code', node.code);
  showSection('plot-code-section', 'plot-code', node.plot_code);
  const plots = document.getElementById('plots');
  plots.replaceChildren();
  document.getElementById('plots-section').hidden = !(node.plots?.length || node.plot_plan || node.plot_analyses?.length);
  document.getElementById('plot-plan').textContent = text(node.plot_plan);
  document.getElementById('plot-analyses').textContent = text(node.plot_analyses);
  for (const path of node.plots || []) {
    try {
      const url = new URL(path, window.location.href);
      const prefix = window.location.pathname.includes('/artifacts/')
        ? window.location.pathname.split('/artifacts/')[0] + '/artifacts/'
        : window.location.pathname.slice(0, window.location.pathname.lastIndexOf('/') + 1);
      if (url.origin !== window.location.origin || !url.pathname.startsWith(prefix)) continue;
      const link = document.createElement('a'); link.href = url.href; link.textContent = path;
      const image = document.createElement('img'); image.src = url.href; image.alt = 'Hình ảnh của node'; image.loading = 'lazy';
      image.addEventListener('error', () => {image.hidden = true;});
      plots.append(link, image);
    } catch (_) { /* Invalid image paths do not block the node details. */ }
  }
  showSection('error-section', 'error', [node.exc_type, node.exc_info, node.exc_stack].filter(Boolean));
  showMetrics(node.metric);
  const parent = byId.get(node.parent_id);
  const button = document.getElementById('parent-button');
  button.hidden = !parent;
  button.textContent = parent ? `Xem node cha · ${parent.index + 1}` : 'Xem node cha';
  button.onclick = parent ? () => selectNode(parent) : null;
}
function drawTree() {
  const container = document.getElementById('canvas-container');
  if (!treeData.nodes.length) {
    const message = document.createElement('p'); message.textContent = 'Chưa có bản thử được lưu.'; message.style.padding = '24px'; container.append(message); return;
  }
  // Use the original exporter layout. Node identity and edges come from journals,
  // not their stage-local step numbers, which restart at every transition.
  const breadth = new Set(treeData.layout.map(point => point[0])).size;
  const width = Math.max(640, breadth * 230 + 80);
  const height = Math.max(200, treeData.depth * 116 + 160);
  const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, height, 'aria-label': 'Cây thí nghiệm của toàn bộ lượt Working'});
  const points = treeData.layout.map(([x, y]) => [110 + x * (width - 220), 65 + y * (height - 130)]);
  for (const [parentIndex, childIndex] of treeData.edges) {
    const [px, py] = points[parentIndex], [cx, cy] = points[childIndex];
    const middle = (py + cy) / 2;
    svg.append(svgElement('path', {class: 'tree-edge', 'data-parent': treeData.nodes[parentIndex].id,
      'data-child': treeData.nodes[childIndex].id, d: `M ${px} ${py + 33} V ${middle} H ${cx} V ${cy - 33}`}));
  }
  for (const node of treeData.nodes) {
    const [x, y] = points[node.index];
    const label = `Node ${node.index + 1} · ${stageNames[node.stage - 1]} · ${node.action}`;
    const element = svgElement('g', {class: 'tree-node', transform: `translate(${x},${y})`, role: 'button',
      tabindex: '0', 'aria-label': label, 'aria-pressed': 'false', 'aria-controls': 'node-detail',
      'data-node-id': node.id, 'data-stage': node.stage, style: `--stage-color:var(--s${node.stage})`});
    element.append(svgElement('title', {}, `${label}\n${node.id}`));
    element.append(svgElement('rect', {class: 'selection-ring', x: -104, y: -40, width: 208, height: 80, rx: 9}));
    element.append(svgElement('rect', {class: 'node-body', x: -98, y: -34, width: 196, height: 68, rx: 6}));
    element.append(svgElement('rect', {class: 'node-band', x: -98, y: -34, width: 6, height: 68, rx: 3}));
    element.append(svgElement('text', {class: 'node-label', x: -80, y: -10}, `#${node.index + 1} · ${node.action} · ${node.is_buggy === true ? 'Có lỗi' : node.is_buggy === false ? 'OK' : '…'}`));
    element.append(svgElement('text', {class: 'node-caption', x: -80, y: 11}, `${node.id.slice(0, 8)} · ${stageNames[node.stage - 1]}`));
    const metric = node.metric?.metric_names?.[0]?.data?.[0]?.final_value;
    element.append(svgElement('text', {class: 'node-caption', x: -80, y: 27}, metric == null ? '' : `Metric: ${number(metric)}`));
    element.addEventListener('click', () => selectNode(node));
    element.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); selectNode(node);}
    });
    nodeElements.set(node.id, element); svg.append(element);
  }
  container.append(svg);
  selectNode(byId.get(treeData.selected_node_id) || treeData.nodes[0]);
}
document.getElementById('run-title').textContent = treeData.title || '';
document.getElementById('tree-count').textContent = `${treeData.nodes.length} node · ${treeData.edges.length} liên kết`;
if (treeData.warnings.length) {
  document.getElementById('warnings').hidden = false;
  document.getElementById('warnings').textContent = treeData.warnings.join('\n');
}
drawTree();
document.getElementById('refresh-tree').addEventListener('click', () => window.location.reload());
// Preserve the existing live viewer behavior while a run is active. Completed
// runs do not poll. A manual refresh remains available if HEAD is unavailable.
if (treeData.status === 'running') {
  let modified = null;
  setInterval(async () => {
    if (document.hidden) return;
    try {
      const response = await fetch(window.location.href, {method: 'HEAD', cache: 'no-store'});
      const next = response.headers.get('Last-Modified');
      if (modified && next && next !== modified) window.location.reload();
      modified = next;
    } catch (_) { /* Read-only refresh can be retried with the visible button. */ }
  }, 15000);
}
