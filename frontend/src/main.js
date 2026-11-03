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
let mobileNav = false;
let sending = false;
let prefs;
try { prefs = JSON.parse(localStorage.getItem('parallax-preferences') || '{}'); } catch { prefs = {}; }
let selected = prefs.models || [];
let modelSlots = prefs.slots || [];
let judge = prefs.judge || '';
let mode = prefs.mode || 'auto';
let chatModel = prefs.chatModel || '';
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
  localStorage.setItem('parallax-preferences', JSON.stringify({ models: selected, slots: modelSlots, judge, depth, context, mode, chatModel }));
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
function sourceList(run = current) {
  const byURL = new Map();
  Object.values(run?.sources || {}).flat().forEach(s => {
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
        <button class="settings-nav" data-action="settings">${ico('settings-2')} Settings <span class="connection-count">${config.keys.openrouter ? 'Connected' : 'Add key'}</span></button>
      </div>
    </aside>
    <main class="main ${current ? 'has-results' : 'empty'}">
      <header class="topbar"><div class="topbar-left"><button class="icon-button history-toggle" data-action="toggle-nav" aria-label="Open conversations" aria-expanded="${mobileNav}">${ico('panel-left-open')}</button><span class="brand">${brandMark}<span class="app-name">Parallax</span></span><button class="icon-button header-new" data-action="new" aria-label="New conversation" title="New conversation">${ico('plus')}</button></div><div class="topbar-right">${themeButton()}<button class="icon-button" data-action="settings" aria-label="Settings" title="Settings">${ico('settings-2')}</button><button class="icon-button help-button" data-action="help" aria-label="How Parallax works">${ico('circle-help')}</button></div></header>
      <div class="chat-surface"><div id="desk"></div>
      <div class="composer-area"><div id="composer"></div><p class="composer-footnote">Parallax can make mistakes. Check important sources.</p></div></div>
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
  const models = [...new Set([...modelSlots, ...selected, chatModel])].filter(Boolean);
  container.innerHTML = `<div class="composer-panel"><form class="composer ${running() ? 'busy' : ''}" id="question-form">
    <label class="sr-only" for="question">Your message</label>
    <textarea id="question" rows="${current ? 1 : 2}" maxlength="12000" placeholder="${current ? 'Reply to Parallax…' : 'Ask anything…'}" ${running() ? 'disabled' : ''}>${esc(draft)}</textarea>
    <div class="composer-controls"><div class="composer-left"><label class="chat-model-picker"><span class="sr-only">Chat model</span><select id="chat-model" aria-label="Chat model" ${running() ? 'disabled' : ''}>${models.map(id => `<option value="${esc(id)}" ${id === chatModel ? 'selected' : ''}>${esc(identity(id).name)}</option>`).join('')}</select>${ico('chevron-down')}</label><details class="research-options"><summary aria-label="Chat options" title="Chat options">${ico('settings-2')}<span class="options-label">${mode === 'auto' ? 'Auto' : mode === 'chat' ? 'Chat' : 'Research'}</span></summary><div class="options-panel">
      <label class="depth-select">Mode<select id="mode" aria-label="Response mode" ${running() ? 'disabled' : ''}><option value="auto" ${mode === 'auto' ? 'selected' : ''}>Auto — search when needed</option><option value="chat" ${mode === 'chat' ? 'selected' : ''}>Chat — no web search</option><option value="research" ${mode === 'research' ? 'selected' : ''}>Research — use the team</option></select></label>
      <button type="button" class="composer-option" data-action="context">${ico('plus')} ${context ? 'Edit context' : 'Add context'}</button>
      <label class="depth-select">Research depth<select id="depth" aria-label="Research depth" ${running() ? 'disabled' : ''}><option value="standard" ${depth === 'standard' ? 'selected' : ''}>Standard</option><option value="deep" ${depth === 'deep' ? 'selected' : ''}>Deeper</option></select></label>
      <button type="button" class="composer-option" data-action="settings">${ico('layers-3')} Research team (${selected.length} models)</button>
      ${current ? `<button type="button" class="fresh-toggle ${fresh ? 'on' : ''}" data-action="fresh" aria-pressed="${fresh}">${ico('rotate-ccw')} Skip conversation history</button>` : ''}
    </div></details></div><span class="composer-shortcut"><kbd>Enter</kbd> to send</span>${running() ? `<button class="send-button stop" type="button" data-action="stop" aria-label="Stop response">${ico('square')}</button>` : `<button class="send-button" type="submit" aria-label="Send message" ${sending || !draft.trim() ? 'disabled' : ''}>${ico(sending ? 'loader-circle' : 'arrow-up', sending ? 'spin' : '')}</button>`}</div>
  </form></div>`;
  const textarea = container.querySelector('textarea');
  textarea.style.height = `${Math.min(textarea.scrollHeight, 190)}px`;
  decorate();
}
function safeURL(url) { try { const u = new URL(url); return ['http:', 'https:'].includes(u.protocol) ? u.href : '#'; } catch { return '#'; } }
function hostname(url) { try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; } }
function researchDetails(run) {
  const reports = Object.values(run.reports);
  const sources = sourceList(run);
  const comparison = run.comparison;
  return `<details class="research-evidence" data-evidence="${run.id}"><summary>${ico('search')} Research details (${reports.length} models, ${sources.length} sources) ${ico('chevron-down')}</summary><div class="evidence-body">${sources.length ? `<h3>Sources</h3><ol class="chat-sources">${sources.map(s => `<li><a href="${esc(safeURL(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a><small>${esc(hostname(s.url))} · ${s.read ? 'Page read' : run.request.demo ? 'Example reference' : 'Search excerpt'}</small></li>`).join('')}</ol>` : ''}${reports.length ? `<h3>Independent answers</h3>${reports.map(r => `<details class="original-answer"><summary>${modelChip(r.model)} <span>${r.status === 'completed' ? 'View answer' : esc(r.status)}</span>${ico('chevron-down')}</summary><article class="markdown">${md(r.answer)}</article>${r.error ? `<p class="answer-note">${esc(r.error)}</p>` : ''}</details>`).join('')}` : ''}${comparison ? ['agreements','disagreements'].map(key => comparison[key]?.length ? `<h3>${key === 'agreements' ? 'Where the models agree' : 'Where they differ'}</h3>${comparison[key].map(p => `<p><strong>${esc(p.claim)}</strong><br>${esc(p.detail)}</p>`).join('')}` : '').join('') : ''}${comparison?.limitations?.length ? `<h3>Limitations</h3>${comparison.limitations.map(p => `<p>${esc(p)}</p>`).join('')}` : ''}<a class="export-message" href="/api/runs/${run.id}/export" download>${ico('download')} Export details</a></div></details>`;
}
function renderDesk() {
  const desk = document.querySelector('#desk');
  const nearBottom = desk.scrollHeight - desk.scrollTop - desk.clientHeight < 100;
  const open = new Set([...desk.querySelectorAll('[data-evidence][open]')].map(e => e.dataset.evidence));
  if (!current) {
    desk.innerHTML = `<section class="welcome"><h1>What’s on your mind?</h1><p>Just ask. I’ll research when it helps.</p></section>`;
    decorate();
    return;
  }
  const turns = [...rounds.filter(r => r.id !== current.id).map(stateFromRun), current];
  desk.innerHTML = `<section class="chat-thread" aria-label="Conversation">${turns.map(run => {
    const isRunning = run.status === 'running';
    const answer = run.answer || run.comparison?.answer;
    const status = run.mode === 'research' ? run.comparing ? 'Comparing findings…' : 'Researching with your team…' : 'Thinking…';
    return `<article class="chat-turn"><div class="user-message"><span class="sr-only">You</span><div>${esc(run.request.question)}</div></div><div class="assistant-message"><div class="assistant-label">${brandMark}<span>Parallax</span>${run.request.demo ? '<span class="sample-label">Saved demo</span>' : ''}</div>${answer ? `<div class="markdown">${md(answer)}</div>` : isRunning ? `<p class="response-status" role="status">${ico('loader-circle','spin')}${status}</p>` : `<p class="answer-note">${esc(run.message || 'This response stopped. Send another message to continue.')}</p>`}${run.mode === 'research' && (Object.keys(run.reports).length || sourceList(run).length) ? researchDetails(run) : ''}${run.id === current.id && answer && !isRunning ? `<div class="message-actions"><button data-action="copy" aria-label="Copy response">${ico('copy')}</button></div>` : ''}</div></article>`;
  }).join('')}</section>`;
  desk.querySelectorAll('[data-evidence]').forEach(e => { if (open.has(e.dataset.evidence)) e.open = true; });
  decorate();
  if (nearBottom) desk.scrollTop = desk.scrollHeight;
}
function stateFromRun(run) {
  if (run.activity && run.sources && run.reports) return run;
  const state = { id: run.id, status: run.status, request: run.request, reports: {}, sources: {}, usage: {}, activity: [], comparison: run.result?.comparison || null, answer: run.result?.answer || '', mode: run.result?.mode || (run.request.demo ? 'research' : null), comparing: false, message: '' };
  (run.events || []).forEach(e => applyEvent(e.payload, false, state));
  state.status = run.status;
  for (const report of run.result?.reports || []) { state.reports[report.agent] = report; state.sources[report.agent] = report.sources; }
  return state;
}
function hydrate(run) { current = stateFromRun(run); }
function applyEvent(event, render = true, target = current) {
  if (!target) return;
  switch (event.type) {
    case 'route': target.mode = event.mode; break;
    case 'chat_done': target.mode = 'chat'; target.answer = event.answer; break;
    case 'activity': target.activity.push(event); break;
    case 'sources': target.sources[event.agent] = event.sources; break;
    case 'usage': target.usage[event.agent] = event; break;
    case 'researcher_start': target.mode = 'research'; break;
    case 'researcher_done': target.reports[event.agent] = event.report; target.sources[event.agent] = event.report.sources; target.usage[event.agent] = event.report.usage; break;
    case 'comparison_start': target.comparing = true; break;
    case 'comparison_done': target.comparison = event.comparison; target.sources.judge = event.sources; target.usage.judge = event.usage; break;
    case 'done': target.status = 'completed'; break;
    case 'cancelled': case 'interrupted': case 'error': target.status = event.type === 'error' ? 'failed' : event.type; target.message = event.message; break;
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
  if (!config.keys.openrouter) { notify('Add your OpenRouter key to start chatting.'); openSettings(); return; }
  sending = true;
  renderComposer();
  try {
    const request = { question: question.trim(), context, models: selected, judge, demo: false, mode, chat_model: chatModel, depth, fresh, session_id: sessionId, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone };
    const result = await post('/api/runs', request);
    stream?.close();
    if (current && !rounds.some(r => r.id === current.id)) rounds.push({ ...current });
    sessionId = result.session_id;
    draft = '';
    hydrate({ id: result.run_id, request, status: 'running', events: [] });
    mobileNav = false;
    sending = false;
    shell();
    connect(result.run_id);
    refreshSessions();
    document.querySelector('#desk').scrollTop = document.querySelector('#desk').scrollHeight;
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
  const dialog = modal(`<div class="modal-header"><div><h2>Settings</h2><p>Connect providers and manage your models.</p></div><button class="icon-button" data-close aria-label="Close settings">${ico('x')}</button></div><form id="settings-form"><section class="settings-section"><h3>Connections</h3><p>${config.managed_credentials ? 'OpenRouter connects chat and web research. Tavily is an optional search provider. Keys are managed in Vercel.' : 'OpenRouter connects chat and web research. Tavily is optional. Keys are saved locally on this app’s server.'}</p><label class="key-label">OpenRouter <span>${config.keys.openrouter ? 'Key saved' : 'No key saved'}</span><input type="password" name="openrouter" ${config.managed_credentials ? 'disabled' : ''} autocomplete="off" placeholder="${config.keys.openrouter ? 'Saved · enter a new key to replace' : 'Paste your OpenRouter API key'}" /></label><label class="key-label">Tavily search (optional) <span>${config.keys.tavily ? 'Key saved' : 'No key saved'}</span><input type="password" name="tavily" ${config.managed_credentials ? 'disabled' : ''} autocomplete="off" placeholder="${config.keys.tavily ? 'Saved · enter a new key to replace' : 'Paste your Tavily API key'}" /></label><div class="provider-links"><a href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer">Get an OpenRouter key ${ico('external-link')}</a><a href="https://app.tavily.com" target="_blank" rel="noreferrer">Get a Tavily key ${ico('external-link')}</a></div></section><section class="settings-section"><div class="section-title"><h3>Independent researchers</h3><span>Choose 2–4</span></div><p>Every selected model gets its own research loop and private notes.</p><div class="model-settings">${config.models.map((m, index) => { const currentId = modelSlots[index] || m.id; return `<label class="model-setting"><input type="checkbox" name="enabled-${index}" ${selected.includes(currentId) ? 'checked' : ''} />${modelChip(currentId)}<input type="text" name="model-${index}" aria-label="Researcher ${index+1} model ID" list="model-catalog" value="${esc(currentId)}" /></label>`; }).join('')}</div><datalist id="model-catalog"></datalist><label class="judge-label">Comparison model<input type="text" name="judge" list="model-catalog" value="${esc(judge)}" required /></label><p class="settings-hint">Use any tool-capable OpenRouter model ID. The comparison model can also check sources.</p></section><div id="settings-error" class="form-error" role="alert"></div><div class="modal-footer"><span>Live runs use paid API credits.</span><button class="primary-button" type="submit">Save settings ${ico('check')}</button></div></form>`, true);
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
      notify('Settings saved. You can keep chatting.');
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
  const action = e.target.closest('[data-action]')?.dataset.action;
  switch (action) {
    case 'new': newConversation(); break;
    case 'toggle-nav': mobileNav = !mobileNav; document.querySelector('.workspace').classList.toggle('nav-open', mobileNav); syncNavigation(); document.querySelector(mobileNav ? '.drawer-heading button' : '.history-toggle')?.focus(); break;
    case 'theme': toggleTheme(); break;
    case 'settings': openSettings(); break;
    case 'reload': location.reload(); break;
    case 'context': openContext(); break;
    case 'fresh': fresh = !fresh; renderComposer(); break;
    case 'stop': try { await post(`/api/runs/${current.id}/cancel`, {}); } catch (err) { notify(err.message); } break;
    case 'copy': try { await navigator.clipboard.writeText(current.answer || current.comparison?.answer || ''); notify('Answer copied.'); } catch { notify('Copy is unavailable in this browser. Select the response text to copy it.'); } break;
    case 'help': modal(`<div class="modal-header"><h2>Chat naturally. Research when it helps.</h2><button class="icon-button" data-close aria-label="Close help">${ico('x')}</button></div><div class="help-body"><p>Everyday messages go to your chat model. In Auto mode, questions needing current sources or independent perspectives go to your research team.</p><p>Each researcher searches and reads independently. Parallax brings the findings into one reply. Open <strong>Research details</strong> under a response to inspect sources, original answers, and disagreements. Agreement is not proof.</p><p>OpenRouter handles chat and search using your API credits. You can optionally connect Tavily in Settings. Auto, Chat, and Research modes are in the message options.</p><p>Your conversation is saved. Research may continue after you close this page.</p></div>`); break;
  }
});
document.addEventListener('submit', e => { if (e.target.id === 'question-form') { e.preventDefault(); submit(document.querySelector('#question').value); } });
document.addEventListener('input', e => { if (e.target.id === 'question') { draft = e.target.value; e.target.style.height = 'auto'; e.target.style.height = `${Math.min(e.target.scrollHeight, 190)}px`; const send = document.querySelector('.send-button:not(.stop)'); if (send) send.disabled = sending || !draft.trim(); } });
document.addEventListener('change', e => { if (e.target.id === 'depth') depth = e.target.value; else if (e.target.id === 'mode') { mode = e.target.value; renderComposer(); } else if (e.target.id === 'chat-model') chatModel = e.target.value; savePrefs(); });
window.addEventListener('resize', syncNavigation);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.querySelector('.research-options')?.removeAttribute('open');
  if (e.key === 'Escape' && mobileNav && !document.querySelector('dialog[open]')) { mobileNav = false; document.querySelector('.workspace').classList.remove('nav-open'); syncNavigation(); document.querySelector('.history-toggle')?.focus(); }
  if (e.target.id === 'question' && e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(e.target.value); }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) { e.preventDefault(); newConversation(); }

});
async function init() {
  try {
    [config, sessions] = await Promise.all([api('/api/config'), api('/api/sessions')]);
    if (selected.length < 2 || selected.length > 4) selected = config.models.slice(0, 3).map(m => m.id);
    if (modelSlots.length !== 4) modelSlots = config.models.map(m => selected.find(s => s.split('/')[0] === m.id.split('/')[0]) || m.id);
    judge ||= config.judge;
    chatModel ||= config.chat_model;
    shell();
  } catch (error) { app.innerHTML = `<div class="startup-error"><h1>Let’s reconnect.</h1><p>${esc(error.message)}</p><p>Start the local server, then refresh this page.</p><button data-action="reload">Refresh</button></div>`; }
}
init();
