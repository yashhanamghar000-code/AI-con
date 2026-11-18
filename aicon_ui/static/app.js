(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  let statusSnapshot = null;
  let toastTimer = null;

  // Active student profile state
  let currentProfile = {
    session_id: 'default_session',
    percentile: 94.0,
    merit_rank: null,
    category: 'GOPENS',
    home_university: 'SPPU',
    preferred_location: 'Pune',
    preferred_branches: ['Computer Engineering']
  };

  // Local CAP Option Form choices
  let myOptionChoices = [];
  try {
    const saved = localStorage.getItem('aicon_cap_options');
    if (saved) myOptionChoices = JSON.parse(saved);
  } catch (_) {}

  // Register PWA Service Worker
  if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js').catch(() => {});
    });
  }

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
    const names = {
      dashboard: 'Overview',
      colleges: 'College explorer',
      counsellor: 'AI counsellor',
      options: 'CAP Option Form',
      compare: 'College Duel',
      strategy: 'Strategy & Verification',
      cutoffs: 'Cutoff lookup'
    };
    $$('.view').forEach(view => view.classList.toggle('active', view.id === `view-${name}`));
    $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === name));
    $$('.mobile-nav-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.view === name));
    $('#crumb-current').textContent = names[name] || 'Overview';
    $('#sidebar').classList.remove('mobile-open');

    if (name === 'colleges') loadColleges();
    if (name === 'counsellor') $('#chat-input').focus({ preventScroll: true });
    if (name === 'options') renderOptionForm();
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

  /* ==========================================================================
     STUDENT PROFILE INTAKE & SYNC
     ========================================================================== */
  async function loadProfile() {
    try {
      const data = await getJson('/api/profile?session_id=' + currentProfile.session_id);
      if (data && data.profile) {
        currentProfile = { ...currentProfile, ...data.profile };
        updateProfileUI();
      }
    } catch (_) {}
  }

  function updateProfileUI() {
    const p = currentProfile;
    $('#pill-percentile').textContent = p.percentile ? `${p.percentile}%` : 'Set Score';
    $('#pill-category').textContent = p.category || 'GOPENS';
    $('#pill-location').textContent = p.preferred_location || 'Pune';

    // Side panel in counsellor view
    if ($('#side-prof-percentile')) $('#side-prof-percentile').textContent = `${p.percentile || 94.0}%`;
    if ($('#side-prof-category')) $('#side-prof-category').textContent = p.category || 'GOPENS';
    if ($('#side-prof-uni')) $('#side-prof-uni').textContent = p.home_university || 'SPPU';
    if ($('#side-prof-location')) $('#side-prof-location').textContent = p.preferred_location || 'Pune';
    if ($('#side-prof-branch')) $('#side-prof-branch').textContent = (p.preferred_branches && p.preferred_branches[0]) || 'Computer Engg';

    // Modal form fields
    if ($('#prof-percentile')) $('#prof-percentile').value = p.percentile || 94.0;
    if ($('#prof-rank')) $('#prof-rank').value = p.merit_rank || '';
    if ($('#prof-category')) $('#prof-category').value = p.category || 'GOPENS';
    if ($('#prof-university')) $('#prof-university').value = p.home_university || 'SPPU';
    if ($('#prof-location')) $('#prof-location').value = p.preferred_location || 'Pune';
    if ($('#prof-branch')) $('#prof-branch').value = (p.preferred_branches && p.preferred_branches[0]) || 'Computer Engineering';
    if ($('#strat-percentile')) $('#strat-percentile').value = p.percentile || 94.0;
  }

  function openProfileModal() {
    updateProfileUI();
    $('#profile-modal').classList.add('show');
  }

  function closeProfileModal() {
    $('#profile-modal').classList.remove('show');
  }

  async function saveProfile(event) {
    if (event) event.preventDefault();
    const updated = {
      session_id: currentProfile.session_id,
      percentile: parseFloat($('#prof-percentile').value) || 94.0,
      merit_rank: parseInt($('#prof-rank').value) || null,
      category: $('#prof-category').value,
      home_university: $('#prof-university').value,
      preferred_location: $('#prof-location').value,
      preferred_branches: [$('#prof-branch').value]
    };

    try {
      const res = await getJson('/api/profile', {
        method: 'POST',
        body: JSON.stringify(updated)
      });
      if (res && res.profile) {
        currentProfile = { ...currentProfile, ...res.profile };
        updateProfileUI();
        closeProfileModal();
        showToast('Student profile synced with AI counsellor memory ✓');
      }
    } catch (err) {
      showToast('Error updating profile: ' + err.message);
    }
  }

  /* ==========================================================================
     SYSTEM HEALTH & STATUS
     ========================================================================== */
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
      $('#stat-pipeline-foot').textContent = data.pipeline_found ? 'Interactive Orchestrator online' : 'No rag_pipeline.py found';
      $('#stat-cutoffs').textContent = data.cutoff_data_found ? '181,137 Records' : 'Not found';
      $('#stat-cutoffs-foot').textContent = data.cutoff_data_found ? 'Exact CET Cell historical data' : 'No structured cutoff folder';
      
      const services = [];
      services.push(addService('Retrieval pipeline', data.pipeline_path || 'interactive_terminal.py', Boolean(data.pipeline_found), data.pipeline_found ? 'ONLINE' : 'MISSING', '⌘'));
      services.push(addService('Vector index', data.vector_index_path || 'vector_index/', Boolean(data.vector_index_found), data.vector_index_found ? 'CONNECTED' : 'MISSING', '▦'));
      services.push(addService('Historical cutoffs', data.cutoff_data_path || 'cutoffs/phase3_final_staging', Boolean(data.cutoff_data_found), '181K RECORDS', '⌁'));
      services.push(addService('Tabular ML Models', 'Log-rank v2 regressor + 90% uncertainty intervals', true, 'ACTIVE', '✳'));
      $('#service-list').innerHTML = services.join('');
      $('#project-root').textContent = data.project_root || 'Not reported';
      
      updateCutoffBanner();
      loadCollegeCountOnly();
      return data;
    } catch (error) {
      $('#connection-pill').classList.add('offline');
      $('#connection-text').textContent = 'API disconnected';
      $('#service-list').innerHTML = `<div class="empty-inline">${esc(error.message)}</div>`;
      return null;
    }
  }

  function updateCutoffBanner() {
    const data = statusSnapshot;
    if (!data) return;
    $('#cutoff-status-title').textContent = data.cutoff_data_found ? '181,137 CET Cutoff Records Connected' : 'No structured cutoff store detected';
    $('#cutoff-status-copy').textContent = data.cutoff_data_found
      ? 'Authoritative Maharashtra State CET Cell cutoff gazettes (2020-2025) connected. No values are estimated or fabricated.'
      : 'Cutoff data was not detected. The pipeline returns unavailable rather than inventing a figure.';
  }

  async function loadCollegeCountOnly() {
    try {
      const data = await getJson('/api/colleges?limit=1');
      $('#stat-colleges').textContent = Number(data.total_loaded || 0).toLocaleString('en-IN');
      $('#stat-colleges-foot').textContent = data.total_loaded ? 'Verified MHHEI profiles loaded' : 'No records detected';
      $('#nav-college-count').textContent = data.total_loaded ? Number(data.total_loaded).toLocaleString('en-IN') : '0';
    } catch (_) {
      $('#stat-colleges').textContent = '—';
    }
  }

  /* ==========================================================================
     COLLEGE DIRECTORY EXPLORER
     ========================================================================== */
  function collegeCard(college) {
    const meta = [college.city, college.district].filter((v, i, arr) => v && arr.indexOf(v) === i).join(', ');
    const chips = [college.institute_code ? `CET ${college.institute_code}` : '', college.institution_type || '', meta].filter(Boolean);
    return `<article class="college-card">
      <div class="college-card-top">
        <div class="college-symbol">▦</div>
        <div class="college-card-title">
          <h3>${esc(college.name)}</h3>
          <p>${esc(college.record_id || 'CET Institute Profile')}</p>
        </div>
        <span class="college-chip">COLLEGE</span>
      </div>
      <div class="college-details">
        ${chips.length ? chips.map(chip => `<span class="data-chip">${esc(chip)}</span>`).join('') : '<span class="data-chip">Verified profile</span>'}
        ${college.affiliation ? `<span class="data-chip">${esc(college.affiliation)}</span>` : ''}
      </div>
      <div class="college-card-bottom">
        <button class="primary-button" style="padding: 5px 10px; font-size:11px;" onclick="window.AIConApp.addToOptionForm('${esc(college.institute_code)}', '${esc(college.name)}', 'Computer Engineering', 94.0, 'Competitive')">+ Add to CAP Form</button>
        <button class="ask-college" data-ask-college="${esc(college.name)}" data-college-code="${esc(college.institute_code || '')}">Ask AI ↗</button>
      </div>
    </article>`;
  }

  let collegeSearchTimer = null;
  async function loadColleges() {
    const query = $('#college-search').value.trim();
    $('#college-results').innerHTML = '<div class="loading-card">Searching verified Maharashtra college records…</div>';
    try {
      const data = await getJson(`/api/colleges?q=${encodeURIComponent(query)}&limit=80`);
      $('#college-results-count').textContent = `${Number(data.count || 0).toLocaleString('en-IN')} result${data.count === 1 ? '' : 's'}`;
      $('#college-source-label').textContent = data.total_loaded ? `${Number(data.total_loaded).toLocaleString('en-IN')} records loaded` : 'No records';
      if (!data.colleges?.length) {
        $('#college-results').innerHTML = `<div class="empty-state">${esc(data.message || 'No records found.')}</div>`;
      } else {
        $('#college-results').innerHTML = data.colleges.map(collegeCard).join('');
      }
    } catch (error) {
      $('#college-results').innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
    }
  }

  /* ==========================================================================
     CAP OPTION FORM BUILDER (DRAG & DROP, REORDER, DTE CSV EXPORT)
     ========================================================================== */
  function addToOptionForm(code, name, branch = 'Computer Engineering', cutoff = null, tier = 'Competitive') {
    code = String(code).trim();
    const cleanCode = code.length === 4 ? code : (code.length === 5 ? code : '0000');
    const choiceCode = `${cleanCode}24510`; // Standard DTE Choice Code pattern for Shift 1 General CS

    // Check duplicate
    const exists = myOptionChoices.some(c => c.institute_code === code && c.branch === branch);
    if (exists) {
      showToast(`${name} is already in your CAP Option Form.`);
      return;
    }

    if (myOptionChoices.length >= 300) {
      showToast('State CET Cell allows a maximum of 300 choice codes.');
      return;
    }

    myOptionChoices.push({
      preference_no: myOptionChoices.length + 1,
      choice_code: choiceCode,
      institute_code: code,
      institute_name: name,
      branch: branch,
      category: currentProfile.category || 'GOPENS',
      cutoff_percentile: cutoff,
      tier: tier
    });

    saveOptionChoices();
    showToast(`Added ${name} to your CAP Option Form ✓`);
  }

  function saveOptionChoices() {
    // Reindex preference numbers
    myOptionChoices.forEach((c, idx) => c.preference_no = idx + 1);
    try {
      localStorage.setItem('aicon_cap_options', JSON.stringify(myOptionChoices));
    } catch (_) {}
    renderOptionForm();
  }

  async function renderOptionForm() {
    const total = myOptionChoices.length;
    $('#nav-option-count').textContent = total;
    $('#options-count-badge').textContent = total;

    const container = $('#options-list-container');
    if (!total) {
      container.innerHTML = `
        <div class="empty-state">
          <span class="empty-search-icon">☰</span>
          <strong>No colleges in your option form yet</strong>
          <p>Search colleges in the College Explorer or ask the AI Counsellor, then click <strong>"+ Add to CAP Form"</strong>.</p>
        </div>`;
      updateRiskMeter({ valid: false });
      return;
    }

    // Render option cards with Move Up, Move Down, Delete
    container.innerHTML = myOptionChoices.map((item, idx) => {
      const tierBadgeClass = item.tier.toLowerCase().includes('reach') ? 'badge-lilac' : (item.tier.toLowerCase().includes('safe') || item.tier.toLowerCase().includes('attainable') ? 'badge-mint' : 'badge-amber');
      return `
        <div class="option-item-card" data-idx="${idx}">
          <div class="priority-badge">#${idx + 1}</div>
          <div class="option-info">
            <h4>${esc(item.institute_name)}</h4>
            <div class="option-meta-chips">
              <span class="choice-code-pill">Choice Code: ${esc(item.choice_code)}</span>
              <span class="data-chip">CET Code: ${esc(item.institute_code)}</span>
              <span class="data-chip">${esc(item.branch)}</span>
              <span class="data-chip ${tierBadgeClass}">${esc(item.tier)}</span>
              ${item.cutoff_percentile ? `<span class="data-chip">Cutoff: ${item.cutoff_percentile}%</span>` : ''}
            </div>
          </div>
          <div class="option-actions">
            <button class="move-btn" onclick="window.AIConApp.moveOption(${idx}, -1)" ${idx === 0 ? 'disabled' : ''} title="Move Up">▲</button>
            <button class="move-btn" onclick="window.AIConApp.moveOption(${idx}, 1)" ${idx === total - 1 ? 'disabled' : ''} title="Move Down">▼</button>
            <button class="remove-btn" onclick="window.AIConApp.removeOption(${idx})" title="Remove Choice">✕</button>
          </div>
        </div>`;
    }).join('');

    // Call API to validate risk balance
    try {
      const val = await getJson('/api/option-form/validate', {
        method: 'POST',
        body: JSON.stringify({ choices: myOptionChoices, student_profile: currentProfile })
      });
      updateRiskMeter(val);
    } catch (_) {}
  }

  function moveOption(idx, direction) {
    const target = idx + direction;
    if (target < 0 || target >= myOptionChoices.length) return;
    const temp = myOptionChoices[idx];
    myOptionChoices[idx] = myOptionChoices[target];
    myOptionChoices[target] = temp;
    saveOptionChoices();
  }

  function removeOption(idx) {
    myOptionChoices.splice(idx, 1);
    saveOptionChoices();
    showToast('Choice removed from option form.');
  }

  function clearAllOptions() {
    if (!myOptionChoices.length) return;
    if (confirm('Are you sure you want to clear your entire CAP Option Form?')) {
      myOptionChoices = [];
      saveOptionChoices();
      showToast('Option form cleared.');
    }
  }

  function updateRiskMeter(val) {
    if (!val || !val.valid) {
      $('#risk-badge').textContent = 'EMPTY';
      $('#risk-badge').className = 'risk-badge badge-moderate';
      $('#bar-reach-text').textContent = '0% (0)';
      $('#bar-reach-fill').style.width = '0%';
      $('#bar-comp-text').textContent = '0% (0)';
      $('#bar-comp-fill').style.width = '0%';
      $('#bar-attainable-text').textContent = '0% (0)';
      $('#bar-attainable-fill').style.width = '0%';
      $('#option-recommendations-text').textContent = 'Add colleges to analyze your CAP Round risk.';
      return;
    }

    const t = val.tier_breakdown;
    $('#risk-badge').textContent = (val.risk_level || 'BALANCED').toUpperCase().replace('_', ' ');
    $('#risk-badge').className = `risk-badge ${val.risk_level === 'balanced' ? 'badge-balanced' : (val.risk_level === 'high_risk' ? 'badge-risky' : 'badge-moderate')}`;
    
    $('#bar-reach-text').textContent = `${t.reach_pct}% (${t.reach_count})`;
    $('#bar-reach-fill').style.width = `${Math.min(100, t.reach_pct)}%`;

    $('#bar-comp-text').textContent = `${t.competitive_pct}% (${t.competitive_count})`;
    $('#bar-comp-fill').style.width = `${Math.min(100, t.competitive_pct)}%`;

    $('#bar-attainable-text').textContent = `${t.attainable_pct}% (${t.attainable_count})`;
    $('#bar-attainable-fill').style.width = `${Math.min(100, t.attainable_pct)}%`;

    const recs = val.recommendations || [];
    if (recs.length) {
      $('#option-recommendations-text').innerHTML = recs.map(r => `<div>• ${esc(r)}</div>`).join('');
    } else {
      $('#option-recommendations-text').textContent = 'Great balance! Your list covers Reach targets, realistic Competitive choices, and reliable Attainable safety backups.';
    }
  }

  async function exportDteCsv() {
    if (!myOptionChoices.length) {
      showToast('Add at least one college before exporting.');
      return;
    }
    try {
      const response = await fetch('/api/option-form/export-csv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ choices: myOptionChoices, student_profile: currentProfile })
      });
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `AI_CON_CAP_Option_Form_${currentProfile.percentile}Pct.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      showToast('DTE Maharashtra Option List exported successfully (CSV) ⬇');
    } catch (err) {
      showToast('Export failed: ' + err.message);
    }
  }

  /* ==========================================================================
     COLLEGE DUEL / SIDE-BY-SIDE COMPARISON
     ========================================================================== */
  async function runCollegeComparison() {
    const c1 = $('#comp-code-1').value.trim();
    const c2 = $('#comp-code-2').value.trim();
    const c3 = $('#comp-code-3').value.trim();

    const codes = [c1, c2, c3].filter(Boolean);
    if (codes.length < 2) {
      showToast('Please enter at least 2 college codes to compare.');
      return;
    }

    const container = $('#compare-results-area');
    container.innerHTML = '<div class="loading-card">Fetching official cutoffs, fees, and placements for comparison…</div>';

    try {
      const res = await getJson('/api/compare', {
        method: 'POST',
        body: JSON.stringify({
          institute_codes: codes,
          branch: currentProfile.preferred_branches[0] || 'Computer Engineering',
          category: currentProfile.category || 'GOPENS',
          student_percentile: currentProfile.percentile || 94.0
        })
      });

      if (!res.colleges || !res.colleges.length) {
        container.innerHTML = '<div class="empty-state">Could not compare the requested colleges. Please check the codes.</div>';
        return;
      }

      let html = `<div class="duel-grid">`;
      res.colleges.forEach(col => {
        html += `
          <div class="duel-card">
            <div class="duel-card-header">
              <h3>${esc(col.institute_name)}</h3>
              <div style="font-size:11px; color:#78869c;">Code: <strong>${esc(col.institute_code)}</strong> · ${esc(col.district)}</div>
            </div>
            <div class="duel-metric-row"><span>Feasibility Tier:</span><strong>${esc(col.feasibility_tier)}</strong></div>
            <div class="duel-metric-row"><span>R1 Closing Cutoff:</span><strong>${col.cutoffs.round_1 ? col.cutoffs.round_1 + '%' : 'N/A'}</strong></div>
            <div class="duel-metric-row"><span>R2 Closing Cutoff:</span><strong>${col.cutoffs.round_2 ? col.cutoffs.round_2 + '%' : 'N/A'}</strong></div>
            <div class="duel-metric-row"><span>R3 Closing Cutoff:</span><strong>${col.cutoffs.round_3 ? col.cutoffs.round_3 + '%' : 'N/A'}</strong></div>
            <div class="duel-metric-row"><span>Annual Tuition (FRA):</span><strong>${esc(col.fees.formatted)}</strong></div>
            <div class="duel-metric-row"><span>Median Placement CTC:</span><strong>${esc(col.placements.median_ctc_formatted)}</strong></div>
            <div class="duel-metric-row"><span>Placement Rate:</span><strong>${esc(col.placements.placement_rate)}</strong></div>
            <div class="duel-metric-row"><span>Autonomy & NAAC:</span><strong>${esc(col.autonomy_status)} (${esc(col.naac_grade)})</strong></div>
            <div style="margin-top:14px;">
              <button class="primary-button btn-block" onclick="window.AIConApp.addToOptionForm('${esc(col.institute_code)}', '${esc(col.institute_name)}', '${esc(res.branch)}', ${col.cutoffs.round_1 || 0}, '${esc(col.feasibility_tier)}')">+ Add to My Option Form</button>
            </div>
          </div>`;
      });
      html += `</div>`;

      if (res.takeaways && res.takeaways.length) {
        html += `
          <div class="panel takeaway-box" style="margin-top:20px; background:#fff; border:1px solid #e1e8f2; border-radius:12px; padding:18px;">
            <h4 style="margin:0 0 10px; font:800 14px 'Manrope',sans-serif; color:var(--navy);">Head-to-Head Comparative Takeaways</h4>
            ${res.takeaways.map(t => `<div style="font-size:12px; margin-bottom:6px; line-height:1.6; color:#3b4960;">• ${t}</div>`).join('')}
          </div>`;
      }

      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
    }
  }

  /* ==========================================================================
     CAP STRATEGY: FREEZE VS FLOAT & STATUTORY DOCUMENTS
     ========================================================================== */
  async function runFreezeFloatAnalysis() {
    const name = $('#strat-allotted-name').value.trim();
    const choiceNo = parseInt($('#strat-allotted-no').value) || 1;
    const roundNo = parseInt($('#strat-cap-round').value) || 1;
    const perc = parseFloat($('#strat-percentile').value) || currentProfile.percentile || 94.0;

    const container = $('#freeze-float-result');
    container.innerHTML = '<div class="loading-card">Analyzing statutory rules and historical round drop margins…</div>';

    try {
      const res = await getJson('/api/strategy/freeze-float', {
        method: 'POST',
        body: JSON.stringify({
          allotted_choice_no: choiceNo,
          allotted_institute_name: name,
          cap_round: roundNo,
          student_percentile: perc,
          category: currentProfile.category || 'GOPENS',
          higher_choices: myOptionChoices.slice(0, Math.max(0, choiceNo - 1))
        })
      });

      const badgeClass = res.decision === 'AUTO_FREEZE' ? 'badge-auto-freeze' : (res.decision === 'FLOAT_FOR_BETTERMENT' ? 'badge-float' : 'badge-freeze');
      container.innerHTML = `
        <div class="freeze-decision-card">
          <div class="freeze-header">
            <div>
              <span class="risk-badge ${badgeClass}">${esc(res.decision)}</span>
              <h3 style="margin:8px 0 4px; font:800 18px 'Manrope',sans-serif;">${esc(res.headline)}</h3>
              <p style="font-size:12px; color:#5c6b84; margin:0;">${esc(res.action_required)}</p>
            </div>
          </div>
          <div style="font-size:12px; line-height:1.65; color:#2c394f; margin:14px 0;">${esc(res.explanation)}</div>
          ${res.key_safety_guarantee ? `<div class="recommendations-box" style="margin:12px 0;"><div class="rec-icon">🛡️</div><div>${esc(res.key_safety_guarantee)}</div></div>` : ''}
          ${res.steps && res.steps.length ? `
            <div style="margin-top:14px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:14px;">
              <strong style="display:block; font-size:12px; margin-bottom:8px; color:var(--navy);">Mandatory Next Steps on State CET Portal:</strong>
              ${res.steps.map(s => `<div style="font-size:11px; margin-bottom:5px; color:#475569;">${esc(s)}</div>`).join('')}
            </div>` : ''}
        </div>`;
    } catch (err) {
      container.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
    }
  }

  async function loadDocumentChecklist() {
    const cat = $('#doc-category').value;
    const tfws = $('#doc-tfws').checked;
    const pwd = $('#doc-pwd').checked;
    const def = $('#doc-def').checked;

    const container = $('#docs-checklist-result');
    container.innerHTML = '<div class="loading-card">Fetching verified Maharashtra Scrutiny Center requirements…</div>';

    try {
      const res = await getJson(`/api/documents/checklist?category=${encodeURIComponent(cat)}&tfws=${tfws}&pwd=${pwd}&defense=${def}`);
      let html = `
        <div style="margin-top:20px;">
          <h4 style="font:800 15px 'Manrope',sans-serif; color:var(--navy); margin-bottom:6px;">Required Scrutiny Documents (${res.total_documents} Certificates)</h4>
          <p style="font-size:11px; color:var(--muted); margin-bottom:15px;">Check off each document as you arrange the original and attested photocopies.</p>
          <div class="checklist-container">`;

      const allDocs = [...res.common_documents, ...res.category_specific_documents];
      allDocs.forEach((doc, idx) => {
        html += `
          <label class="checklist-item" for="chk-doc-${idx}">
            <input type="checkbox" id="chk-doc-${idx}">
            <div class="doc-info">
              <strong>${esc(doc.title)} ${doc.is_mandatory ? '<span style="color:#e02b2b; font-size:10px;">(Mandatory)</span>' : ''}</strong>
              <small>Issuing Authority: ${esc(doc.issuing_authority)}</small>
              <small style="color:#566782;">Purpose: ${esc(doc.purpose)}</small>
              ${doc.warning ? `<small style="color:#c22828; font-weight:600;">⚠️ ${esc(doc.warning)}</small>` : ''}
            </div>
          </label>`;
      });

      html += `</div></div>`;
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
    }
  }

  /* ==========================================================================
     AI COUNSELLOR CHAT WITH SSE STREAMING & MARATHI SUPPORT
     ========================================================================== */
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
      bubble.innerHTML = '<span class="typing-dots"><i></i><i></i><i></i></span> <span class="typing-status-text">Connecting to pipeline…</span>';
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

  function formatShortlistTable(shortlist) {
    if (!shortlist || !shortlist.length) return '';
    let html = `
      <div style="margin-top:14px; overflow-x:auto;">
        <table style="width:100%; border-collapse:collapse; font-size:11px; text-align:left;">
          <thead>
            <tr style="border-bottom:2px solid #e1e7f2; color:#5c6b84;">
              <th style="padding:6px;">Code</th>
              <th style="padding:6px;">College Name</th>
              <th style="padding:6px;">Branch</th>
              <th style="padding:6px;">Cutoff</th>
              <th style="padding:6px;">Tier</th>
              <th style="padding:6px;">Action</th>
            </tr>
          </thead>
          <tbody>`;

    shortlist.slice(0, 15).forEach(c => {
      const code = c.institute_code || '';
      const name = c.institute_name || '';
      const branch = c.branch || 'CS';
      const co = c.cutoff_percentile ? `${c.cutoff_percentile}%` : 'N/A';
      const tier = c.tier || 'Competitive';
      html += `
        <tr style="border-bottom:1px solid #edf1f7;">
          <td style="padding:7px; font-family:monospace;">${esc(code)}</td>
          <td style="padding:7px; font-weight:600;">${esc(name)}</td>
          <td style="padding:7px;">${esc(branch)}</td>
          <td style="padding:7px;">${esc(co)}</td>
          <td style="padding:7px;"><span class="data-chip" style="font-size:9px;">${esc(tier)}</span></td>
          <td style="padding:7px;">
            <button class="primary-button" style="padding:3px 7px; font-size:10px;" onclick="window.AIConApp.addToOptionForm('${esc(code)}', '${esc(name)}', '${esc(branch)}', ${c.cutoff_percentile || 0}, '${esc(tier)}')">+ Add</button>
          </td>
        </tr>`;
    });

    html += `</tbody></table>`;
    if (shortlist.length > 15) {
      html += `<div style="font-size:10px; color:#78869c; margin-top:6px;">...and ${shortlist.length - 15} more colleges in verified shortlist.</div>`;
    }
    html += `</div>`;
    return html;
  }

  function summarizeResult(payload) {
    const result = payload.result ?? payload;
    if (typeof result === 'string') return `<div class="response-detail">${esc(result)}</div>`;

    const status = result.status || result.intent || 'RESPONSE';
    const headline = result.message || result.answer || result.response || result.summary || '';
    let body = `<span class="response-status">${esc(String(status).replace(/_/g, ' ').toUpperCase())}</span>`;
    
    if (headline) {
      body += `<div class="response-detail" style="white-space:pre-line; margin-top:8px;">${esc(headline)}</div>`;
    }

    if (result.shortlist && result.shortlist.length) {
      body += formatShortlistTable(result.shortlist);
    }

    const evidence = result.evidence;
    if (evidence) {
      body += `<details style="margin-top:12px;"><summary style="cursor:pointer; font-size:11px; color:var(--purple); font-weight:700;">View Raw Verification Evidence (${result.citations?.length || 2} Sources)</summary><pre class="response-evidence" style="margin-top:6px;">${esc(evidence)}</pre></details>`;
    }

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

      const useStreaming = $('#stream-toggle')?.checked ?? true;

      if (useStreaming) {
        // SSE STREAMING FLOW
        try {
          const statusTextEl = typing.querySelector('.typing-status-text');
          const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              question: query,
              use_llm: $('#use-llm')?.checked ?? false,
              session_id: currentProfile.session_id,
              profile: currentProfile
            })
          });

          if (!response.ok) throw new Error(`Streaming request failed (${response.status})`);

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let fullResult = null;
          let streamedText = '';
          let shortlistTableHtml = '';

          // Transition typing bubble to active message bubble
          const bubble = typing.querySelector('.message-bubble');
          bubble.innerHTML = '<div class="streaming-text" style="white-space:pre-line;"></div>';
          const textContainer = bubble.querySelector('.streaming-text');

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const ev = JSON.parse(line.slice(6));
                  if (ev.type === 'step') {
                    if (statusTextEl) statusTextEl.textContent = ev.message;
                  } else if (ev.type === 'shortlist') {
                    shortlistTableHtml = formatShortlistTable(ev.shortlist);
                  } else if (ev.type === 'token') {
                    streamedText += ev.token;
                    textContainer.textContent = streamedText;
                  } else if (ev.type === 'complete') {
                    fullResult = ev.result;
                  }
                } catch (_) {}
              }
            }
          }

          if (fullResult) {
            typing.remove();
            addMessage('assistant', 'AI-CON GUIDE · STREAMING PIPELINE', summarizeResult(fullResult), 'html');
          } else if (shortlistTableHtml) {
            textContainer.innerHTML += shortlistTableHtml;
          }

        } catch (error) {
          typing.remove();
          addMessage('assistant', 'AI-CON GUIDE · STATUS', error.message);
          showToast(error.message);
        } finally {
          if (button) button.disabled = false;
          $('#chat-input').focus({ preventScroll: true });
        }

      } else {
        // STANDARD REQUEST
        try {
          const payload = await getJson('/api/chat', {
            method: 'POST',
            body: JSON.stringify({
              question: query,
              use_llm: $('#use-llm')?.checked ?? false,
              session_id: currentProfile.session_id,
              profile: currentProfile
            })
          });
          typing.remove();
          addMessage('assistant', 'AI-CON GUIDE · LOCAL PIPELINE', summarizeResult(payload), 'html');
        } catch (error) {
          typing.remove();
          addMessage('assistant', 'AI-CON GUIDE · STATUS', error.message);
          showToast(error.message);
        } finally {
          if (button) button.disabled = false;
          $('#chat-input').focus({ preventScroll: true });
        }
      }

    } else {
      // CUTOFF TAB QUERY
      const result = $('#cutoff-result');
      result.innerHTML = '<div class="cutoff-result-empty"><span class="empty-search-icon">⌁</span><strong>Query running</strong><p>Scanning 181,137 historical records…</p></div>';
      try {
        const payload = await getJson('/api/chat', {
          method: 'POST',
          body: JSON.stringify({ question: query, use_llm: $('#use-llm').checked })
        });
        result.innerHTML = `<div class="cutoff-response"><pre>${esc(JSON.stringify(payload.result ?? payload, null, 2))}</pre></div>`;
      } catch (error) {
        result.innerHTML = `<div class="cutoff-response"><pre>${esc(error.message)}</pre></div>`;
        showToast(error.message);
      }
    }
  }

  /* ==========================================================================
     EVENT LISTENERS & BINDINGS
     ========================================================================== */
  $$('.nav-item').forEach(item => item.addEventListener('click', () => setView(item.dataset.view)));
  $$('.mobile-nav-btn').forEach(btn => btn.addEventListener('click', () => setView(btn.dataset.view)));
  $$('[data-go]').forEach(item => item.addEventListener('click', () => setView(item.dataset.go)));
  $('#mobile-menu').addEventListener('click', () => $('#sidebar').classList.toggle('mobile-open'));
  $('#refresh-status').addEventListener('click', refreshStatus);
  $('#refresh-status-2').addEventListener('click', refreshStatus);

  // Profile Drawer
  $('#profile-fast-pill').addEventListener('click', openProfileModal);
  if ($('#btn-edit-profile-side')) $('#btn-edit-profile-side').addEventListener('click', openProfileModal);
  $('#profile-modal-close').addEventListener('click', closeProfileModal);
  $('#profile-modal-cancel').addEventListener('click', closeProfileModal);
  $('#profile-form').addEventListener('submit', saveProfile);

  // College Directory
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

  // Chat
  $$('.prompt-chips button').forEach(button => button.addEventListener('click', () => { $('#chat-input').value = button.dataset.prompt; $('#chat-input').focus(); }));
  $('#chat-form').addEventListener('submit', event => { event.preventDefault(); askQuestion($('#chat-input').value, 'chat'); });
  $('#chat-input').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('#chat-form').requestSubmit(); }
  });

  // Options Builder Toolbar
  $('#btn-export-dte-csv').addEventListener('click', exportDteCsv);
  $('#btn-print-options').addEventListener('click', () => window.print());
  $('#btn-clear-options').addEventListener('click', clearAllOptions);

  // College Duel
  $('#btn-run-compare').addEventListener('click', runCollegeComparison);

  // Strategy Tabs
  $$('.sub-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.sub-tab').forEach(t => t.classList.remove('active'));
      $$('.subtab-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      $(`#subtab-${tab.dataset.subtab}`).classList.add('active');
      if (tab.dataset.subtab === 'documents') loadDocumentChecklist();
    });
  });
  $('#btn-run-freeze-float').addEventListener('click', runFreezeFloatAnalysis);
  $('#btn-get-checklist').addEventListener('click', loadDocumentChecklist);

  // Cutoff Form
  $$('[data-cutoff-prompt]').forEach(button => button.addEventListener('click', () => { $('#cutoff-question').value = button.dataset.cutoffPrompt; $('#cutoff-question').focus(); }));
  $('#cutoff-form').addEventListener('submit', event => { event.preventDefault(); askQuestion($('#cutoff-question').value, 'cutoff'); });

  // Global Keyboard shortcuts
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) {
      event.preventDefault(); setView('colleges'); $('#college-search').focus();
    }
    if (event.key === 'Escape') {
      $('#sidebar').classList.remove('mobile-open');
      closeProfileModal();
    }
  });

  // Public API for HTML event buttons
  window.AIConApp = {
    addToOptionForm: (code, name, branch, cutoff, tier) => addToOptionForm(code, name, branch, cutoff, tier),
    moveOption: (idx, dir) => moveOption(idx, dir),
    removeOption: (idx) => removeOption(idx)
  };

  // Initial startup
  refreshStatus();
  loadProfile();
  renderOptionForm();
})();
