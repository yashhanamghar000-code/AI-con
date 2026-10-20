(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  let statusSnapshot = null;
  let toastTimer = null;

  function showToast(message) {
    const toast = $('#toast');
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3600);
  }

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  }

  function setView(name) {
    const names = { dashboard: 'Overview', colleges: 'College explorer', counsellor: 'AI counsellor', cutoffs: 'Cutoff lookup' };
    $$('.view').forEach(view => view.classList.toggle('active', view.id === `view-${name}`));
    $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === name));
    $('#crumb-current').textContent = names[name] || 'Overview';
    $('#sidebar').classList.remove('mobile-open');
    if (name === 'colleges') loadColleges();
    if (name === 'counsellor') $('#chat-input').focus({ preventScroll: true });
    if (name === 'cutoffs') updateCutoffBanner();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function getJson(url, options = {}) {
    let response;
    try {
      response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
    } catch (error) {
      throw new Error('Cannot connect to the local UI API. Is the server running?');
    }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || body.message || `Request failed (${response.status})`);
    return body;
  }

  function addService(name, detail, good, label, symbol) {
    return `<div class="service-row"><span class="service-icon">${symbol}</span><div class="service-copy"><strong>${esc(name)}</strong><small>${esc(detail || '')}</small></div><span class="service-status ${good ? 'good' : 'bad'}">${esc(label)}</span></div>`;
  }

  async function refreshStatus() {
    try {
      const data = await getJson('/api/health');
      statusSnapshot = data;
      const pill = $('#connection-pill');
      const ok = Boolean(data.pipeline_found && data.vector_index_found);
      pill.classList.toggle('online', ok);
      pill.classList.toggle('offline', !ok);
      $('#connection-text').textContent = ok ? 'Retrieval ready' : 'Setup incomplete';
      $('#stat-colleges').textContent = '—';
      $('#stat-colleges-foot').textContent = 'Loading college directory';
      $('#stat-pipeline').textContent = data.pipeline_found ? 'Detected' : 'Missing';
      $('#stat-pipeline-foot').textContent = data.pipeline_found ? 'Existing pipeline found' : 'No rag_pipeline.py found';
      $('#stat-cutoffs').textContent = data.cutoff_data_found ? 'Detected' : 'Not found';
      $('#stat-cutoffs-foot').textContent = data.cutoff_data_found ? 'Structured cutoff path found' : 'No structured cutoff folder detected';
      const trained = data.trained_model || {};
      $('#stat-llm').textContent = trained.loaded ? 'Loaded' : (trained.available ? 'Available' : 'Not ready');
      $('#stat-llm-foot').textContent = trained.message || 'Trained model status unavailable';
      $('#chat-engine-meta').textContent = ok ? 'Local retrieval pipeline detected' : 'Pipeline/index setup incomplete';
      $('#project-root').textContent = data.project_root || 'Not reported';
      $('#llm-toggle-status').textContent = trained.loaded ? 'Trained model loaded' : (trained.available ? (trained.base_model_cached ? 'Ready on first use' : 'Base weights download on first use') : 'Adapter/dependencies missing');
      $('#use-llm').disabled = !trained.available;
      if (!trained.available) $('#use-llm').checked = false;
      const services = [];
      services.push(addService('Retrieval pipeline', data.pipeline_path || 'rag_pipeline.py was not found', Boolean(data.pipeline_found), data.pipeline_found ? 'DETECTED' : 'MISSING', '⌘'));
      services.push(addService('Vector index', data.vector_index_path || 'Build the index using the project README', Boolean(data.vector_index_found), data.vector_index_found ? 'DETECTED' : 'MISSING', '▦'));
      services.push(addService('Structured cutoff data', data.cutoff_data_path || 'No valid cutoff store found', Boolean(data.cutoff_data_found), data.cutoff_data_found ? 'DETECTED' : 'NOT FOUND', '⌁'));
      services.push(addService('TinyLlama + AI-CON LoRA', trained.message || 'Trained adapter not detected', Boolean(trained.available), trained.loaded ? 'LOADED' : (trained.available ? 'AVAILABLE' : 'NOT READY'), '✳'));
      $('#service-list').innerHTML = services.join('');
      updateCutoffBanner();
      loadCollegeCountOnly();
      return data;
    } catch (error) {
      $('#connection-pill').classList.add('offline');
      $('#connection-text').textContent = 'UI API disconnected';
      $('#service-list').innerHTML = `<div class="empty-inline">${esc(error.message)}</div>`;
      $('#project-root').textContent = 'No health response received';
      return null;
    }
  }

  function updateCutoffBanner() {
    const data = statusSnapshot;
    if (!data) return;
    $('#cutoff-status-title').textContent = data.cutoff_data_found ? 'Structured cutoff store detected' : 'No structured cutoff store detected';
    $('#cutoff-status-copy').textContent = data.cutoff_data_found
      ? `A cutoff data directory was found at ${data.cutoff_data_path}. The query still needs an exact matching record.`
      : 'Cutoff data was not detected in the configured locations. The pipeline should return unavailable rather than inventing a figure.';
    $('#cutoff-status-chip').textContent = data.cutoff_data_found ? 'STORE FOUND' : 'NOT AVAILABLE';
    $('#cutoff-status-chip').classList.toggle('ready', Boolean(data.cutoff_data_found));
  }

  async function loadCollegeCountOnly() {
    try {
      const data = await getJson('/api/colleges?limit=1');
      $('#stat-colleges').textContent = Number(data.total_loaded || 0).toLocaleString('en-IN');
      $('#stat-colleges-foot').textContent = data.total_loaded ? 'Records loaded from local dataset' : 'No records detected in known folders';
      $('#nav-college-count').textContent = data.total_loaded ? Number(data.total_loaded).toLocaleString('en-IN') : '0';
    } catch (_) {
      $('#stat-colleges').textContent = '—';
      $('#stat-colleges-foot').textContent = 'Dataset scan unavailable';
    }
  }

  function collegeCard(college) {
    const meta = [college.city, college.district].filter((v, i, arr) => v && arr.indexOf(v) === i).join(', ');
    const chips = [college.institute_code ? `CET ${college.institute_code}` : '', college.institution_type || '', meta].filter(Boolean);
    return `<article class="college-card"><div class="college-card-top"><div class="college-symbol">▦</div><div class="college-card-title"><h3>${esc(college.name)}</h3><p>${esc(college.record_id || 'College profile record')}</p></div><span class="college-chip">COLLEGE</span></div><div class="college-details">${chips.length ? chips.map(chip => `<span class="data-chip">${esc(chip)}</span>`).join('') : '<span class="data-chip">Sparse profile</span>'}${college.affiliation ? `<span class="data-chip">${esc(college.affiliation)}</span>` : ''}</div><div class="college-card-bottom"><span class="source-label" title="${esc(college.source_file || '')}">${esc(college.source_file || 'Local dataset record')}</span><button class="ask-college" data-ask-college="${esc(college.name)}" data-college-code="${esc(college.institute_code || '')}">Ask AI ↗</button></div></article>`;
  }

  let collegeSearchTimer = null;
  async function loadColleges() {
    const query = $('#college-search').value.trim();
    $('#college-results').innerHTML = '<div class="loading-card">Searching the actual local college records…</div>';
    try {
      const data = await getJson(`/api/colleges?q=${encodeURIComponent(query)}&limit=80`);
      $('#college-results-count').textContent = `${Number(data.count || 0).toLocaleString('en-IN')} result${data.count === 1 ? '' : 's'}`;
      $('#college-source-label').textContent = data.total_loaded ? `${Number(data.total_loaded).toLocaleString('en-IN')} records loaded` : 'No college records detected';
      $('#stat-colleges').textContent = Number(data.total_loaded || 0).toLocaleString('en-IN');
      $('#nav-college-count').textContent = data.total_loaded ? Number(data.total_loaded).toLocaleString('en-IN') : '0';
      if (!data.colleges?.length) {
        $('#college-results').innerHTML = `<div class="empty-state">${esc(data.message || 'No records found.')}<br>Check the dataset folder layout in the project README.</div>`;
      } else {
        $('#college-results').innerHTML = data.colleges.map(collegeCard).join('');
      }
    } catch (error) {
      $('#college-results').innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
      $('#college-results-count').textContent = 'Could not load records';
    }
  }

  function addMessage(role, label, content, kind = 'text') {
    const messages = $('#chat-messages');
    const wrapper = document.createElement('div');
    wrapper.className = `message ${role}`;
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? 'Y' : '✳';
    const section = document.createElement('div');
    section.className = 'message-content';
    const labelEl = document.createElement('div');
    labelEl.className = 'message-label';
    labelEl.textContent = label;
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    if (kind === 'typing') {
      bubble.innerHTML = '<span class="typing-dots"><i></i><i></i><i></i></span> <span>Querying the local pipeline…</span>';
    } else if (kind === 'html') {
      bubble.innerHTML = content;
    } else {
      bubble.textContent = content;
    }
    section.append(labelEl, bubble);
    wrapper.append(avatar, section);
    messages.append(wrapper);
    messages.scrollTop = messages.scrollHeight;
    return wrapper;
  }

  function summarizeResult(payload) {
    if (payload.status === 'pipeline_error') {
      return `<span class="response-status">PIPELINE ERROR · EXIT ${esc(payload.return_code)}</span><div class="response-detail">${esc(payload.message || 'The pipeline failed.')}</div>${payload.stderr ? `<pre class="response-evidence">${esc(payload.stderr)}</pre>` : ''}${payload.stdout ? `<pre class="response-evidence">${esc(payload.stdout)}</pre>` : ''}`;
    }
    if (payload.status === 'unparsed_output') {
      return `<span class="response-status">UNPARSED OUTPUT</span><div class="response-detail">${esc(payload.message || '')}</div><pre class="response-evidence">${esc(payload.stdout || '')}</pre>`;
    }
    const result = payload.result ?? payload;
    if (typeof result === 'string') return `<div class="response-detail">${esc(result)}</div>`;
    const status = result.status || result.intent || 'RESPONSE';
    const headline = result.message || result.answer || result.response || result.summary || '';
    const meta = [];
    if (result.matched_college) meta.push(`College: ${result.matched_college}`);
    if (result.institute_code) meta.push(`CET code: ${result.institute_code}`);
    if (result.record_id) meta.push(`Record: ${result.record_id}`);
    if (result.intent) meta.push(`Intent: ${result.intent}`);
    let body = `<span class="response-status">${esc(String(status).replace(/_/g, ' ').toUpperCase())}</span>`;
    if (headline) body += `<div class="response-detail">${esc(headline)}</div>`;
    if (meta.length) body += `<div class="response-detail" style="margin-top:7px">${esc(meta.join(' · '))}</div>`;
    const evidence = result.evidence;
    if (evidence) body += `<pre class="response-evidence">${esc(evidence)}</pre>`;
    const extra = { ...result };
    ['status', 'intent', 'message', 'answer', 'response', 'summary', 'matched_college', 'institute_code', 'record_id', 'evidence'].forEach(key => delete extra[key]);
    if (Object.keys(extra).length) body += `<pre class="response-evidence">${esc(JSON.stringify(extra, null, 2))}</pre>`;
    if (!headline && !evidence && !Object.keys(extra).length) body += `<pre class="response-evidence">${esc(JSON.stringify(result, null, 2))}</pre>`;
    return body;
  }

  async function askQuestion(question, target = 'chat') {
    const query = question.trim();
    if (!query) return;
    if (target === 'chat') {
      const welcome = $('.welcome-message');
      if (welcome) welcome.remove();
      addMessage('user', 'YOU', query);
      const typing = addMessage('assistant', 'AI-CON GUIDE', '', 'typing');
      const button = $('.send-button');
      if (button) button.disabled = true;
      $('#chat-input').value = '';
      try {
        const payload = await getJson('/api/chat', { method: 'POST', body: JSON.stringify({ question: query, use_llm: $('#use-llm').checked }) });
        typing.remove();
        addMessage('assistant', 'AI-CON GUIDE · LOCAL PIPELINE', summarizeResult(payload), 'html');
      } catch (error) {
        typing.remove();
        addMessage('assistant', 'AI-CON GUIDE · CONNECTION STATUS', error.message);
        showToast(error.message);
      } finally {
        if (button) button.disabled = false;
        $('#chat-input').focus({ preventScroll: true });
      }
    } else {
      const result = $('#cutoff-result');
      result.innerHTML = '<div class="cutoff-result-empty"><span class="empty-search-icon">⌁</span><strong>Query running</strong><p>Waiting for the local pipeline…</p></div>';
      try {
        const payload = await getJson('/api/chat', { method: 'POST', body: JSON.stringify({ question: query, use_llm: $('#use-llm').checked }) });
        result.innerHTML = `<div class="cutoff-response"><pre>${esc(JSON.stringify(payload.result ?? payload, null, 2))}</pre></div>`;
      } catch (error) {
        result.innerHTML = `<div class="cutoff-response"><pre>${esc(error.message)}</pre></div>`;
        showToast(error.message);
      }
    }
  }

  $$('.nav-item').forEach(item => item.addEventListener('click', () => setView(item.dataset.view)));
  $$('[data-go]').forEach(item => item.addEventListener('click', () => setView(item.dataset.go)));
  $('#mobile-menu').addEventListener('click', () => $('#sidebar').classList.toggle('mobile-open'));
  $('#refresh-status').addEventListener('click', refreshStatus);
  $('#refresh-status-2').addEventListener('click', refreshStatus);
  $('#college-search-button').addEventListener('click', loadColleges);
  $('#college-search').addEventListener('input', () => {
    clearTimeout(collegeSearchTimer);
    collegeSearchTimer = setTimeout(loadColleges, 250);
  });
  $('#college-search').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); loadColleges(); } });
  $('#college-results').addEventListener('click', event => {
    const button = event.target.closest('[data-ask-college]');
    if (!button) return;
    const name = button.dataset.askCollege;
    const code = button.dataset.collegeCode;
    setView('counsellor');
    $('#chat-input').value = `Tell me about ${name}${code ? ` (CET institute code ${code})` : ''}.`;
    $('#chat-input').focus();
  });
  $$('.prompt-chips button').forEach(button => button.addEventListener('click', () => { $('#chat-input').value = button.dataset.prompt; $('#chat-input').focus(); }));
  $('#chat-form').addEventListener('submit', event => { event.preventDefault(); askQuestion($('#chat-input').value, 'chat'); });
  $('#chat-input').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('#chat-form').requestSubmit(); }
  });
  $$('[data-cutoff-prompt]').forEach(button => button.addEventListener('click', () => { $('#cutoff-question').value = button.dataset.cutoffPrompt; $('#cutoff-question').focus(); }));
  $('#cutoff-form').addEventListener('submit', event => { event.preventDefault(); askQuestion($('#cutoff-question').value, 'cutoff'); });
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) {
      event.preventDefault(); setView('colleges'); $('#college-search').focus();
    }
    if (event.key === 'Escape') $('#sidebar').classList.remove('mobile-open');
  });

  refreshStatus();
})();
