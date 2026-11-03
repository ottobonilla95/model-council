import { createIcons, Sun, Moon, Plus, Settings2, ArrowUp, ArrowLeft, PanelLeftClose, PanelLeftOpen, Search, BookOpen, Layers3, Check, X, ChevronDown, ChevronRight, ArrowUpRight, Download, Copy, Square, CircleHelp, FlaskConical, MessageSquare, RotateCcw, ExternalLink, LoaderCircle, AlertCircle, Sparkles, CheckCheck, Link, Clock3 } from 'lucide';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import './style.css';

const iconSet = { Sun, Moon, Plus, Settings2, ArrowUp, ArrowLeft, PanelLeftClose, PanelLeftOpen, Search, BookOpen, Layers3, Check, X, ChevronDown, ChevronRight, ArrowUpRight, Download, Copy, Square, CircleHelp, FlaskConical, MessageSquare, RotateCcw, ExternalLink, LoaderCircle, AlertCircle, Sparkles, CheckCheck, Link, Clock3 };
const ico = (name, cls = '') => `<i data-lucide="${name}" class="${cls}"></i>`;
const esc = (s = '') => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const md = s => DOMPurify.sanitize(marked.parse(s || ''), { USE_PROFILES: { html: true }, FORBID_TAGS: ['img', 'iframe', 'style', 'input', 'form'], FORBID_ATTR: ['style'] });
const brandMark = `<svg class="brand-mark" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="m5 9 14-4v18L5 27V9Z"/><path d="m13 5 14 4v18l-14-4V5Z"/></svg>`;
const app = document.querySelector('#app');
let config;
let sessions = [];
let sessionId = null;
let rounds = [];
let current = null;
let stream = null;
let activeTab = 'answer';
let mobileNav = false;
let sending = false;
let prefs;
try { prefs = JSON.parse(localStorage.getItem('parallax-preferences') || '{}'); } catch { prefs = {}; }
let selected = prefs.models || [];
let modelSlots = prefs.slots || [];
let judge = prefs.judge || '';
let demo = true;
let depth = prefs.depth || 'standard';
let context = prefs.context || '';
let fresh = false;
let draft = '';

function notify(message) {
  const toast = document.querySelector('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => toast.classList.remove('show'), 4500);
}
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.[0]?.msg || 'The request could not be completed.');
  return data;
}
const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body) });
function savePrefs() {
  localStorage.setItem('parallax-preferences', JSON.stringify({ models: selected, slots: modelSlots, judge, depth, context }));
}
function identity(id) {
  const provider = id.split('/')[0];
  const known = config.models.find(m => m.id === id);
  const map = { openai: ['GPT', 'green'], anthropic: ['Claude', 'orange'], 'x-ai': ['Grok', 'blue'], google: ['Gemini', 'purple'] };
  const [name, color] = map[provider] || [provider, 'gray'];
  return known || { id, name, color };
}
function modelChip(id, small = false) {
  const m = identity(id);
  return `<span class="model-chip ${small ? 'small' : ''}" title="${esc(id)}"><span class="model-dot ${m.color}"></span>${esc(m.name)}</span>`;
}
function decorate() {
  createIcons({ icons: iconSet, attrs: { 'stroke-width': 1.65 } });
  document.querySelectorAll('.markdown a').forEach(a => { a.target = '_blank'; a.rel = 'noopener noreferrer'; });
}
function themeButton() {
  const dark = document.documentElement.dataset.theme !== 'light';
  const label = `Switch to ${dark ? 'light' : 'dark'} mode`;
  return `<button class="icon-button theme-toggle" data-action="theme" aria-label="${label}" title="${label}">${ico(dark ? 'sun' : 'moon')}</button>`;
}
function toggleTheme() {
  const theme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('parallax-theme', theme); } catch { /* Keep the current session usable. */ }
  document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#141619' : '#f7f8fa';
  const button = document.querySelector('.theme-toggle');
  const label = `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`;
  button.setAttribute('aria-label', label);
  button.title = label;
  button.innerHTML = ico(theme === 'dark' ? 'sun' : 'moon');
  decorate();
}
function running() { return current?.status === 'running'; }
function totalUsage() {
  const values = Object.values(current?.usage || {});
  return values.reduce((sum, v) => sum + (v.input_tokens || 0) + (v.output_tokens || 0), 0);
}
function sourceList() {
  const byURL = new Map();
  Object.values(current?.sources || {}).flat().forEach(s => {
    const previous = byURL.get(s.url);
    byURL.set(s.url, { ...previous, ...s, read: s.read || previous?.read, agents: [...new Set([...(previous?.agents || []), s.id.split('-s')[0]])] });
  });
  return [...byURL.values()];
}
function shell() {
  app.innerHTML = `<div class="workspace ${mobileNav ? 'nav-open' : ''}">
    <div class="nav-scrim" data-action="toggle-nav"></div>
    <aside class="sidebar">
      <div class="drawer-heading"><span>Conversations</span><button class="icon-button" data-action="toggle-nav" aria-label="Close conversations">${ico('x')}</button></div>
      <button class="new-chat" data-action="new">${ico('plus')} New conversation <span>⌘ K</span></button>
      <div class="history-heading">Your conversations</div>
      <nav class="history" aria-label="Saved conversations">${sessions.length ? sessions.map(s => `<button class="history-item ${s.id === sessionId ? 'selected' : ''}" data-session="${s.id}" title="${esc(s.title)}">${ico('message-square')}<span>${esc(s.title)}</span></button>`).join('') : `<p class="history-empty">A place for your questions.<br>Your conversations appear here.</p>`}</nav>
      <div class="sidebar-bottom">
        <div class="local-note"><span class="local-dot"></span><div>${config.managed_credentials ? 'Saved in your private workspace' : 'Saved on your computer'}<small>Questions, answers, and sources</small></div></div>
        <button class="settings-nav" data-action="settings">${ico('settings-2')} Settings <span class="connection-count">${Object.values(config.keys).filter(Boolean).length}/2 keys saved</span></button>
      </div>
    </aside>
    <main class="main ${current ? 'has-results' : 'empty'}">
      <header class="topbar"><div class="topbar-left"><button class="icon-button history-toggle" data-action="toggle-nav" aria-label="Open conversations" aria-expanded="${mobileNav}">${ico('panel-left-open')}</button><span class="brand">${brandMark}<span class="app-name">Parallax</span></span><button class="icon-button header-new" data-action="new" aria-label="New conversation" title="New conversation">${ico('plus')}</button></div><div class="topbar-right"><button class="demo-switch ${demo ? 'on' : ''}" data-action="demo" aria-pressed="${demo}" title="${demo ? 'Switch to live research' : 'Switch to demo mode'}">${demo ? ico('flask-conical') : '<span class="live-dot"></span>'}<span>${demo ? 'Demo mode' : 'Live research'}</span></button>${themeButton()}<button class="icon-button" data-action="settings" aria-label="Settings" title="Settings">${ico('settings-2')}</button><button class="icon-button help-button" data-action="help" aria-label="How Parallax works">${ico('circle-help')}</button></div></header>
      <div class="chat-surface"><div id="desk"></div>
      <div class="composer-area"><div id="composer"></div><p class="composer-footnote">${demo ? 'Demo uses sample answers. No model calls or web searches.' : 'Your question goes to OpenRouter; searches go to Tavily. AI can make mistakes.'}</p></div></div>
    </main>
  </div>`;
  renderDesk();
  renderComposer();
  decorate();
  syncNavigation();
}
function syncNavigation() {
  const sidebar = document.querySelector('.sidebar');
  if (sidebar) sidebar.inert = !mobileNav;
  const main = document.querySelector('.main');
  if (main) main.inert = mobileNav;
  document.querySelector('.history-toggle')?.setAttribute('aria-expanded', String(mobileNav));
}
function renderComposer() {
  const container = document.querySelector('#composer');
  const models = [...new Set([...modelSlots, ...selected])];
  container.innerHTML = `<div class="composer-panel"><form class="composer ${running() ? 'busy' : ''}" id="question-form">
    <label class="sr-only" for="question">Your research question</label>
    <textarea id="question" rows="2" maxlength="12000" placeholder="${current ? 'Ask a follow-up…' : 'Ask anything…'}" ${running() ? 'disabled' : ''}>${esc(draft)}</textarea>
    <div class="composer-controls"><details class="research-options"><summary aria-label="Research options" title="Research options">${ico('settings-2')}<span class="options-label">Options</span>${context || depth === 'deep' || fresh ? '<span class="context-dot"></span>' : ''}</summary><div class="options-panel">
      <button type="button" class="composer-option" data-action="context" aria-label="Shared context">${ico('plus')} ${context ? 'Edit context' : 'Add context'}</button>
      <label class="depth-select">${ico('layers-3')}<select id="depth" aria-label="Research depth" ${running() ? 'disabled' : ''}><option value="standard" ${depth === 'standard' ? 'selected' : ''}>Standard research</option><option value="deep" ${depth === 'deep' ? 'selected' : ''}>Deeper research</option></select>${ico('chevron-down')}</label>
      ${current ? `<button type="button" class="fresh-toggle ${fresh ? 'on' : ''}" data-action="fresh" aria-pressed="${fresh}" title="Skip previous rounds">${ico('rotate-ccw')} Fresh round</button>` : ''}
    </div></details><span class="composer-shortcut"><kbd>Enter</kbd> to ask</span>${running() ? `<button class="send-button stop" type="button" data-action="stop" aria-label="Stop research">${ico('square')}</button>` : `<button class="send-button" type="submit" aria-label="Start research" ${sending || !draft.trim() ? 'disabled' : ''}>${ico(sending ? 'loader-circle' : 'arrow-up', sending ? 'spin' : '')}</button>`}</div>
  </form>
  <div class="model-selection" role="group" aria-label="Research models. Choose 2 to 4.">${models.map(id => `<button type="button" class="model-choice ${selected.includes(id) ? 'selected' : ''}" data-model="${esc(id)}" aria-pressed="${selected.includes(id)}" aria-label="${esc(identity(id).name)} — ${esc(id)}" title="${esc(id)}" ${running() ? 'disabled' : ''}>${modelChip(id)}<span class="choice-check">${ico('check')}</span></button>`).join('')}<button class="manage-models" data-action="settings" aria-label="Manage models" title="Manage models">${ico('plus')}</button><span class="selection-count" aria-live="polite">${selected.length} researchers selected</span></div></div>`;
  const textarea = container.querySelector('textarea');
  textarea.style.height = `${Math.min(textarea.scrollHeight, 190)}px`;
  decorate();
}
function renderDesk() {
  const desk = document.querySelector('#desk');
  const researchOpen = desk.querySelector('.research-details')?.open;
  if (!current) {
    desk.innerHTML = `<section class="welcome"><h1>What would you like to know?</h1></section>`;
    decorate();
    return;
  }
  const count = sourceList().length;
  const finished = Object.keys(current.reports).length;
  const isDemo = current.request.demo;
  desk.innerHTML = `<section class="conversation"><div class="conversation-main"><div class="round-history">${rounds.filter(r => r.id !== current.id).map((r, i) => `<button data-round="${r.id}"><span>Round ${i+1}</span>${esc(r.request.question)}${ico('chevron-right')}</button>`).join('')}</div><div class="question-meta">${isDemo ? `${ico('flask-conical')} Demo walkthrough` : `${ico('message-square')} Your question`}<span>${current.request.depth === 'deep' ? 'Deeper research' : 'Standard research'}</span></div><h1 class="question-title">${esc(current.request.question)}</h1>${isDemo ? `<div class="demo-banner">${ico('flask-conical')}<span>Sample findings, not a researched answer to your question. <button data-action="settings">Connect your keys</button> to start live research.</span></div>` : ''}<div class="tabbar" role="tablist" aria-label="Research views">${[['answer', 'Combined answer', ''], ['disagreements', 'Comparison', current.comparison ? current.comparison.disagreements.length : ''], ['originals', 'Originals', finished], ['sources', 'Sources', count]].map(([id, text, n]) => `<button role="tab" id="tab-${id}" aria-selected="${activeTab === id}" aria-controls="tab-content" tabindex="${activeTab === id ? 0 : -1}" class="tab ${activeTab === id ? 'active' : ''}" data-tab="${id}">${text}${n !== '' ? `<span>${n}</span>` : ''}</button>`).join('')}</div><div id="tab-content" role="tabpanel" aria-labelledby="tab-${activeTab}">${tabContent()}</div><div class="answer-actions">${current.comparison ? `<button data-action="copy">${ico('copy')} Copy answer</button>` : ''}<a href="/api/runs/${current.id}/export" download>${ico('download')} Export round</a>${!running() ? `<span>${isDemo ? 'Sample data' : `${totalUsage().toLocaleString()} tokens reported`}</span>` : ''}</div><details class="research-details" ${(researchOpen ?? running()) ? 'open' : ''}><summary>Research activity <span>${finished}/${current.request.models.length} models finished</span>${ico('chevron-down')}</summary><div class="research-sidebar">${researchSidebar()}</div></details></div></section>`;
  decorate();
}
function tabContent() {
  const comparison = current.comparison;
  if (activeTab === 'answer') {
    if (!comparison) return `<div class="working-state"><div class="working-symbol">${ico(running() ? 'loader-circle' : 'alert-circle', running() ? 'spin' : '')}</div><h2>${running() ? (current.comparing ? 'Connecting the findings' : 'A few minds on your question') : 'This round has stopped'}</h2><p>${running() ? (current.comparing ? 'Checking the evidence, preserving the differences, and shaping a useful answer.' : 'Each researcher works independently. Their answers come together here when they finish.') : esc(current.message || 'You can inspect saved research in Originals and Sources, or start another round.')}</p><div class="working-models">${current.request.models.map(m => modelChip(m)).join('')}</div>${current.comparing ? '<span class="working-caption">Independent answers are ready in Originals.</span>' : ''}</div>`;
    return `<div class="answer-heading"><span class="answer-emblem">${ico('layers-3')}</span><div><strong>${current.request.demo ? 'Sample combined answer' : 'Parallax’s perspective'}</strong><small>${current.request.models.length} researchers, compared by ${esc(identity(current.request.judge).name)}</small></div></div><article class="markdown">${md(comparison.answer)}</article>${comparison.limitations.length ? `<div class="limitations">${ico('circle-help')}<div><strong>Keep in mind</strong>${comparison.limitations.map(x => `<p>${esc(x)}</p>`).join('')}</div></div>` : ''}${comparison.next_steps.length ? `<div class="next-steps"><h3>A useful next step</h3>${comparison.next_steps.map(s => `<p>${ico('arrow-up-right')}<span>${esc(s)}</span></p>`).join('')}</div>` : ''}`;
  }
  if (activeTab === 'disagreements') {
    if (!comparison) return empty('The comparison comes after the independent research.', 'Originals and sources appear as each researcher finishes.');
    return `<div class="comparison-intro"><h2>What holds up. What’s still open.</h2><p>Agreement is a starting point. Evidence decides how much weight to give it.</p></div>${[['agreements', 'Where the answers align', 'check-check'], ['disagreements', 'Where the answers differ', 'layers-3']].map(([key, title, icon]) => `<section class="comparison-group ${key}"><h3>${ico(icon)}${title}<span>${comparison[key].length}</span></h3>${comparison[key].length ? comparison[key].map(point => `<div class="comparison-point"><h4>${esc(point.claim)}</h4><p>${esc(point.detail)}</p>${point.source_ids.length ? `<div class="point-sources">${point.source_ids.map(id => { const s = Object.values(current.sources).flat().find(s => s.id === id); return s ? `<a target="_blank" rel="noreferrer noopener" href="${esc(safeURL(s.url))}">${ico('link')}${esc(s.title)}</a>` : ''; }).join('')}</div>` : ''}</div>`).join('') : '<p class="muted">No material points identified in this category.</p>'}</section>`).join('')}`;
  }
  if (activeTab === 'originals') {
    return `<div class="view-intro"><h2>Before the answers came together</h2><p>The original findings, with each researcher’s reasoning and sources intact.</p></div>${current.request.models.map((model, index) => {
      const agent = `r${index+1}`;
      const report = current.reports[agent];
      return `<details class="original" ${index === 0 ? 'open' : ''}><summary>${modelChip(model)}<span class="original-model">${esc(model.split('/')[1])}</span><span class="original-status">${esc(report?.status || (running() ? 'Researching' : 'Stopped'))}</span>${ico('chevron-down')}</summary>${report ? `<div class="original-body">${report.error ? `<div class="inline-error">${ico('alert-circle')}${esc(report.error)}</div>` : ''}<div class="markdown">${md(report.answer || 'No answer was returned.')}</div><div class="original-footer">${report.sources.length} sources · ${report.usage.model_calls || 0} model calls · ${report.seconds}s${report.usage.actual_models?.length ? `<br>Provider-reported model: ${esc(report.usage.actual_models.join(', '))}` : ''}</div></div>` : `<p class="original-body muted">${running() ? 'This researcher is still working independently.' : 'This researcher did not finish before the round stopped.'}</p>`}</details>`;
    }).join('')}`;
  }
  const sources = sourceList();
  return `<div class="view-intro"><h2>Follow the evidence</h2><p>“Page read” means the reader fetched text. It does not mean every claim has been verified.</p></div>${sources.length ? `<div class="sources-list">${sources.map((s, i) => `<article class="source"><div class="source-number">${i+1}</div><div><div class="source-meta"><span>${esc(hostname(s.url))}</span><span class="source-badge ${s.read ? 'read' : ''}">${s.read ? 'Page read' : (current.request.demo ? 'Example reference' : 'Search excerpt')}</span></div><a href="${esc(safeURL(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.title)}${ico('arrow-up-right')}</a><p>${esc(s.excerpt)}</p><div class="source-bottom">${s.agents.map(agent => agent === 'judge' ? '<span class="small muted">Comparison</span>' : current.request.models[Number(agent.slice(1))-1] ? modelChip(current.request.models[Number(agent.slice(1))-1], true) : '').join('')}${s.retrieved_at ? `<span>Collected ${new Date(s.retrieved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>` : ''}</div></div></article>`).join('')}</div>` : empty('The source trail starts here.', 'Sources appear as researchers search and read. No sources collected yet.')}`;
}
function empty(title, detail) { return `<div class="empty-view">${ico('book-open')}<h3>${title}</h3><p>${detail}</p></div>`; }
function safeURL(url) { try { const u = new URL(url); return ['http:', 'https:'].includes(u.protocol) ? u.href : '#'; } catch { return '#'; } }
function hostname(url) { try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; } }
function researchSidebar() {
  const completed = Object.keys(current.reports).length;
  return `<div class="research-title">${ico('layers-3')}<strong>Independent research</strong><span>${completed}/${current.request.models.length}</span></div><p class="research-description">Same question. Separate investigations.</p><div class="researchers">${current.request.models.map((model, index) => {
    const agent = `r${index+1}`;
    const report = current.reports[agent];
    const events = current.activity.filter(e => e.agent === agent);
    const usage = current.usage[agent];
    return `<div class="researcher"><div class="researcher-top">${modelChip(model)}<span class="agent-indicator ${report?.status || (running() ? 'running' : 'stopped')}">${ico(report ? (report.status === 'completed' ? 'check' : 'alert-circle') : (running() ? 'loader-circle' : 'square'), !report && running() ? 'spin' : '')}</span></div><div class="researcher-model">${esc(model.split('/')[1])}</div><div class="researcher-progress">${esc(report ? report.status === 'completed' ? (current.request.demo ? 'Sample answer ready' : 'Answer ready') : report.status : events.at(-1)?.action === 'read' ? 'Reading a source' : events.at(-1)?.action === 'search' ? 'Searching the web' : running() ? 'Investigating independently' : 'Stopped')}</div>${events.length ? `<div class="latest-activity">${ico(events.at(-1).action === 'search' ? 'search' : 'book-open')}<span>${esc(events.at(-1).detail)}</span></div>` : ''}<div class="researcher-stats"><span>${(current.sources[agent] || []).length} sources</span>${usage?.model_calls ? `<span>${usage.model_calls} calls</span>` : ''}</div></div>`;
  }).join('')}</div><div class="synthesis-step ${current.comparing || current.comparison ? 'active' : ''}"><span class="synthesis-icon">${ico(current.comparing && !current.comparison ? 'loader-circle' : 'layers-3', current.comparing && !current.comparison ? 'spin' : '')}</span><div><strong>Compare & connect</strong><p>${current.comparison ? 'Comparison ready' : current.comparing ? 'Comparing evidence' : 'After every researcher finishes'}</p></div></div><div class="research-budget"><span>${ico('clock-3')} Research limits</span><p>Up to ${current.request.depth === 'deep' ? 12 : 8} model calls and ${current.request.depth === 'deep' ? 24 : 12} web actions per researcher.</p><p>${current.request.demo ? 'No credits used in demo.' : 'Usage limits bound work, not a guaranteed dollar amount. Provider charges vary.'}</p></div>${current.activity.length ? `<details class="activity-log"><summary>Activity log ${ico('chevron-down')}</summary>${current.activity.map(e => `<div>${ico(e.action === 'search' ? 'search' : 'book-open')}<span><small>${esc(e.agent === 'judge' ? 'Comparison' : identity(current.request.models[Number(e.agent.slice(1))-1] || '').name)}</small>${esc(e.detail)}</span></div>`).join('')}</details>` : ''}`;
}
function hydrate(run) {
  current = { id: run.id, status: run.status, request: run.request, reports: {}, sources: {}, usage: {}, activity: [], comparison: null, comparing: false, message: '' };
  (run.events || []).forEach(e => applyEvent(e.payload, false));
  current.status = run.status;
  if (run.result?.comparison && !current.comparison) current.comparison = run.result.comparison;
  for (const report of run.result?.reports || []) { current.reports[report.agent] = report; current.sources[report.agent] = report.sources; }
}
function applyEvent(event, render = true) {
  if (!current) return;
  switch (event.type) {
    case 'activity': current.activity.push(event); break;
    case 'sources': current.sources[event.agent] = event.sources; break;
    case 'usage': current.usage[event.agent] = event; break;
    case 'researcher_done': current.reports[event.agent] = event.report; current.sources[event.agent] = event.report.sources; current.usage[event.agent] = event.report.usage; break;
    case 'comparison_start': current.comparing = true; break;
    case 'comparison_done': current.comparison = event.comparison; current.sources.judge = event.sources; current.usage.judge = event.usage; break;
    case 'done': current.status = 'completed'; break;
    case 'cancelled': case 'interrupted': case 'error': current.status = event.type === 'error' ? 'failed' : event.type; current.message = event.message; break;
  }
  if (render) { renderDesk(); if (!running()) { stream?.close(); renderComposer(); refreshSessions(); } }
}
function connect(runId, after = 0) {
  stream?.close();
  stream = new EventSource(`/api/runs/${runId}/events?after=${after}`);
  stream.onmessage = e => { if (current?.id === runId) applyEvent(JSON.parse(e.data)); };
  stream.onerror = async () => {
    try {
      const saved = await api(`/api/runs/${runId}`);
      if (current?.id !== runId) return;
      if (saved.status !== 'running') { stream.close(); hydrate(saved); renderDesk(); renderComposer(); }
    } catch { notify('Connection interrupted. Your round is saved; reconnecting…'); }
  };
}
async function refreshSessions() {
  sessions = await api('/api/sessions');
  const nav = document.querySelector('.history');
  if (nav && sessions.length) { nav.innerHTML = sessions.map(s => `<button class="history-item ${s.id === sessionId ? 'selected' : ''}" data-session="${s.id}" title="${esc(s.title)}">${ico('message-square')}<span>${esc(s.title)}</span></button>`).join(''); decorate(); }
}
async function submit(question) {
  if (running() || sending || !question.trim()) return;
  if (!demo && !Object.values(config.keys).every(Boolean)) { notify('Connect both providers to start live research.'); openSettings(); return; }
  sending = true;
  renderComposer();
  try {
    const request = { question: question.trim(), context, models: selected, judge, demo, depth, fresh, session_id: sessionId, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone };
    const result = await post('/api/runs', request);
    stream?.close();
    if (current && !rounds.some(r => r.id === current.id)) rounds.push({ ...current });
    sessionId = result.session_id;
    draft = '';
    activeTab = 'answer';
    hydrate({ id: result.run_id, request, status: 'running', events: [] });
    mobileNav = false;
    sending = false;
    shell();
    connect(result.run_id);
    refreshSessions();
    document.querySelector('#desk').scrollTop = 0;
  } catch (error) { notify(error.message); } finally { sending = false; renderComposer(); }
}
async function loadSession(id) {
  try {
    const saved = await api(`/api/sessions/${id}`);
    if (!saved.length) return;
    stream?.close();
    sessionId = id;
    rounds = saved;
    const last = saved.at(-1);
    hydrate(last);
    demo = last.request.demo;
    activeTab = 'answer';
    draft = '';
    mobileNav = false;
    shell();
    if (running()) connect(last.id, saved.at(-1).events.at(-1)?.id || 0);
  } catch (error) { notify(error.message); }
}
function newConversation() {
  stream?.close();
  current = null;
  sessionId = null;
  rounds = [];
  draft = '';
  mobileNav = false;
  shell();
  document.querySelector('#question').focus();
}
function modal(content, wide = false) {
  const previousFocus = document.activeElement;
  const dialog = document.createElement('dialog');
  dialog.className = `modal ${wide ? 'wide' : ''}`;
  dialog.innerHTML = content;
  document.body.append(dialog);
  dialog.addEventListener('close', () => { dialog.remove(); previousFocus?.focus(); });
  dialog.addEventListener('click', e => { if (e.target === dialog || e.target.closest('[data-close]')) dialog.close(); });
  dialog.showModal();
  decorate();
  return dialog;
}
function openSettings() {
  const dialog = modal(`<div class="modal-header"><div><h2>Settings</h2><p>Connect providers and manage your models.</p></div><button class="icon-button" data-close aria-label="Close settings">${ico('x')}</button></div><form id="settings-form"><section class="settings-section"><h3>Connections</h3><p>${config.managed_credentials ? 'Provider keys are managed in this project’s Vercel environment variables.' : 'Keys are saved locally and used by this app’s server. They are never included in research prompts.'}</p><label class="key-label">OpenRouter <span>${config.keys.openrouter ? 'Key saved' : 'No key saved'}</span><input type="password" name="openrouter" ${config.managed_credentials ? 'disabled' : ''} autocomplete="off" placeholder="${config.keys.openrouter ? 'Saved · enter a new key to replace' : 'Paste your OpenRouter API key'}" /></label><label class="key-label">Tavily search <span>${config.keys.tavily ? 'Key saved' : 'No key saved'}</span><input type="password" name="tavily" ${config.managed_credentials ? 'disabled' : ''} autocomplete="off" placeholder="${config.keys.tavily ? 'Saved · enter a new key to replace' : 'Paste your Tavily API key'}" /></label><div class="provider-links"><a href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer">Get an OpenRouter key ${ico('external-link')}</a><a href="https://app.tavily.com" target="_blank" rel="noreferrer">Get a Tavily key ${ico('external-link')}</a></div></section><section class="settings-section"><div class="section-title"><h3>Independent researchers</h3><span>Choose 2–4</span></div><p>Every selected model gets its own research loop and private notes.</p><div class="model-settings">${config.models.map((m, index) => { const currentId = modelSlots[index] || m.id; return `<label class="model-setting"><input type="checkbox" name="enabled-${index}" ${selected.includes(currentId) ? 'checked' : ''} />${modelChip(currentId)}<input type="text" name="model-${index}" aria-label="Researcher ${index+1} model ID" list="model-catalog" value="${esc(currentId)}" /></label>`; }).join('')}</div><datalist id="model-catalog"></datalist><label class="judge-label">Comparison model<input type="text" name="judge" list="model-catalog" value="${esc(judge)}" required /></label><p class="settings-hint">Use any tool-capable OpenRouter model ID. The comparison model can also check sources.</p></section><div id="settings-error" class="form-error" role="alert"></div><div class="modal-footer"><span>Live runs use paid API credits.</span><button class="primary-button" type="submit">Save settings ${ico('check')}</button></div></form>`, true);
  api('/api/models').then(data => {
    const list = dialog.querySelector('#model-catalog');
    if (list) list.innerHTML = data.models.map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
  }).catch(() => {});
  dialog.querySelector('form').addEventListener('submit', async e => {
    e.preventDefault();
    const data = new FormData(e.target);
    const models = config.models.map((_, i) => data.has(`enabled-${i}`) ? String(data.get(`model-${i}`)).trim() : null).filter(Boolean);
    const error = dialog.querySelector('#settings-error');
    if (models.length < 2 || models.length > 4 || new Set(models).size !== models.length) { error.textContent = 'Choose 2–4 different models.'; return; }
    if (models.some(m => !m.includes('/')) || !String(data.get('judge')).includes('/')) { error.textContent = 'Use full OpenRouter model IDs, such as provider/model.'; return; }
    try {
      config = await post('/api/settings', { openrouter: data.get('openrouter') || '', tavily: data.get('tavily') || '' });
      selected = models;
      modelSlots = config.models.map((m, i) => String(data.get(`model-${i}`)).trim() || m.id);
      judge = String(data.get('judge')).trim();
      savePrefs();
      dialog.close();
      shell();
      notify('Settings saved. Choose Live research when you are ready.');
    } catch (err) { error.textContent = err.message; }
  });
}
function openContext() {
  const dialog = modal(`<div class="modal-header"><div><h2>A little background</h2><p>The same context goes to every researcher.</p></div><button class="icon-button" data-close aria-label="Close context">${ico('x')}</button></div><form id="context-form"><label for="shared-context" class="context-label">Your goals, preferences, and constraints</label><textarea id="shared-context" name="context" rows="7" maxlength="12000" placeholder="For example: I live in Sweden, prefer practical advice, and want to understand the tradeoffs before making a decision.">${esc(context)}</textarea><p class="settings-hint">Saved in this browser. Only add information you want sent to your selected model providers.</p><div class="modal-footer"><button type="button" class="text-button" id="clear-context">Clear context</button><button type="submit" class="primary-button">Save context ${ico('check')}</button></div></form>`);
  dialog.querySelector('#clear-context').onclick = () => { dialog.querySelector('textarea').value = ''; };
  dialog.querySelector('form').onsubmit = e => { e.preventDefault(); context = new FormData(e.target).get('context').trim(); savePrefs(); dialog.close(); renderComposer(); };
}
document.addEventListener('click', async e => {
  if (!e.target.closest('.research-options')) document.querySelector('.research-options')?.removeAttribute('open');
  const session = e.target.closest('[data-session]');
  if (session) return loadSession(session.dataset.session);
  const tab = e.target.closest('[data-tab]');
  if (tab) { activeTab = tab.dataset.tab; renderDesk(); document.querySelector(`[data-tab="${activeTab}"]`)?.focus(); return; }
  const model = e.target.closest('[data-model]');
  if (model && !running()) {
    const id = model.dataset.model;
    if (selected.includes(id)) {
      if (selected.length === 2) { notify('Keep at least 2 models selected to compare answers.'); return; }
      selected = selected.filter(m => m !== id);
    } else {
      if (selected.length === 4) { notify('Choose up to 4 models. Deselect one first.'); return; }
      selected = [...selected, id];
    }
    savePrefs();
    renderComposer();
    document.querySelector(`[data-model="${CSS.escape(id)}"]`)?.focus();
    return;
  }
  const round = e.target.closest('[data-round]');
  if (round) { try { const saved = await api(`/api/runs/${round.dataset.round}`); stream?.close(); hydrate(saved); activeTab = 'answer'; shell(); if (running()) connect(saved.id, saved.events.at(-1)?.id || 0); } catch (err) { notify(err.message); } return; }
  const action = e.target.closest('[data-action]')?.dataset.action;
  switch (action) {
    case 'new': newConversation(); break;
    case 'toggle-nav': mobileNav = !mobileNav; document.querySelector('.workspace').classList.toggle('nav-open', mobileNav); syncNavigation(); document.querySelector(mobileNav ? '.drawer-heading button' : '.history-toggle')?.focus(); break;
    case 'theme': toggleTheme(); break;
    case 'settings': openSettings(); break;
    case 'reload': location.reload(); break;
    case 'context': openContext(); break;
    case 'fresh': fresh = !fresh; renderComposer(); break;
    case 'demo':
      if (running()) { notify('Wait for this round to finish before changing mode.'); break; }
      demo = !demo; shell();
      if (!demo && !Object.values(config.keys).every(Boolean)) openSettings();
      break;
    case 'stop': try { await post(`/api/runs/${current.id}/cancel`, {}); } catch (err) { notify(err.message); } break;
    case 'copy': try { await navigator.clipboard.writeText(current.comparison.answer); notify('Answer copied.'); } catch { notify('Copy is unavailable in this browser. Use Export round to save the answer.'); } break;
    case 'help': modal(`<div class="modal-header"><h2>A few minds. One clear view.</h2><button class="icon-button" data-close aria-label="Close help">${ico('x')}</button></div><div class="help-body"><p>Each selected model independently researches the same question using search and source reading. It cannot see the other researchers’ notes or answers.</p><p>A separate model compares their findings, can check disputed sources, and preserves meaningful differences. Agreement is not proof.</p><p>Follow-ups include your previous questions and each model’s own answers. <strong>Fresh round</strong> skips that history. Your shared context still applies.</p><p><strong>Demo mode</strong> shows clearly labeled sample data. Live research needs OpenRouter and Tavily keys and uses their API credits.</p><p>The first version reads text web pages. PDFs, paywalls and pages requiring JavaScript may need another source. ${config.managed_credentials ? 'Rounds are saved in your private workspace. Queued research continues when you close this page; interrupted jobs may retry.' : 'Rounds are saved locally, but an in-flight run cannot resume automatically after a server restart.'}</p></div>`); break;
  }
});
document.addEventListener('submit', e => { if (e.target.id === 'question-form') { e.preventDefault(); submit(document.querySelector('#question').value); } });
document.addEventListener('input', e => { if (e.target.id === 'question') { draft = e.target.value; e.target.style.height = 'auto'; e.target.style.height = `${Math.min(e.target.scrollHeight, 190)}px`; const send = document.querySelector('.send-button:not(.stop)'); if (send) send.disabled = sending || !draft.trim(); } });
document.addEventListener('change', e => { if (e.target.id === 'depth') { depth = e.target.value; savePrefs(); } });
window.addEventListener('resize', syncNavigation);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.querySelector('.research-options')?.removeAttribute('open');
  if (e.key === 'Escape' && mobileNav && !document.querySelector('dialog[open]')) { mobileNav = false; document.querySelector('.workspace').classList.remove('nav-open'); syncNavigation(); document.querySelector('.history-toggle')?.focus(); }
  if (e.target.id === 'question' && e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(e.target.value); }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) { e.preventDefault(); newConversation(); }
  if (e.target.matches('[role="tab"]') && ['ArrowLeft', 'ArrowRight'].includes(e.key)) {
    e.preventDefault(); const tabs = ['answer', 'disagreements', 'originals', 'sources']; activeTab = tabs[(tabs.indexOf(activeTab) + (e.key === 'ArrowRight' ? 1 : 3)) % tabs.length]; renderDesk(); document.querySelector(`[data-tab="${activeTab}"]`).focus();
  }
});
async function init() {
  try {
    [config, sessions] = await Promise.all([api('/api/config'), api('/api/sessions')]);
    if (selected.length < 2 || selected.length > 4) selected = config.models.slice(0, 3).map(m => m.id);
    if (modelSlots.length !== 4) modelSlots = config.models.map(m => selected.find(s => s.split('/')[0] === m.id.split('/')[0]) || m.id);
    judge ||= config.judge;
    demo = !Object.values(config.keys).every(Boolean);
    shell();
  } catch (error) { app.innerHTML = `<div class="startup-error"><h1>Let’s reconnect.</h1><p>${esc(error.message)}</p><p>Start the local server, then refresh this page.</p><button data-action="reload">Refresh</button></div>`; }
}
init();
