/**
 * Career Readiness Dashboard — Industry Upgrade v3.0
 * Handles all data fetching, chart rendering, and UI updates for career_dashboard.html
 */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let radarChartInstance   = null;
let progressChartInstance = null;
let scoreRingAnim        = null;

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
  loadProjects();
  loadProgress();
});

// ---------------------------------------------------------------------------
// Dashboard data
// ---------------------------------------------------------------------------
async function loadDashboard() {
  try {
    const res  = await fetch('/dashboard');
    const data = await res.json();

    if (data.error) {
      if (data.redirect) { window.location.href = data.redirect; return; }
      showError(data.error);
      hideDashLoading();
      return;
    }

    renderHeader(data);
    renderScoreRing(data.readiness.overall_score);
    renderRadarChart(data.readiness);
    renderBreakdownDetails(data.readiness);
    renderSkillGaps(data.gap_analysis);
    renderMatchedSkills(data.gap_analysis);
    renderRecommendations(data.recommendations);

    if (data.ats_score) {
      renderATSCard(data.ats_score);
    }

    hideDashLoading();

  } catch (err) {
    showError('Failed to load dashboard. Please try again.');
    hideDashLoading();
  }
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------
function renderHeader(data) {
  const r = data.readiness;

  // Sub-scores
  setText('skillMatchScore', r.skill_match_score + '%');
  setText('experienceScore',  r.experience_score  + '%');
  setText('evidenceScore',    r.evidence_score    + '%');
  setText('targetRole',       data.target_role    || '—');

  // Status pill
  const { label, cls, msg } = getStatusInfo(r.overall_score);
  const pill = document.getElementById('statusPill');
  if (pill) { pill.textContent = label; pill.className = `status-pill ${cls}`; }
  setText('statusMessage', msg);
}

function getStatusInfo(score) {
  if (score >= 80) return { label:'🎉 Ready to Apply!',  cls:'status-excellent', msg:'Excellent match! Start applying with confidence.' };
  if (score >= 60) return { label:'👍 Almost There',      cls:'status-good',      msg:'Good foundation! Close the gaps and start applying.' };
  if (score >= 40) return { label:'📚 Keep Learning',     cls:'status-moderate',  msg:'Moderate match — invest time in the missing skills.' };
  return                  { label:'🚀 Getting Started',  cls:'status-poor',      msg:'Follow the recommendations below to build your path.' };
}

// ---------------------------------------------------------------------------
// Score ring (animated arc on canvas)
// ---------------------------------------------------------------------------
function renderScoreRing(score) {
  const canvas  = document.getElementById('scoreRingCanvas');
  if (!canvas) return;
  const ctx     = canvas.getContext('2d');
  const cx      = canvas.width  / 2;
  const cy      = canvas.height / 2;
  const radius  = 68;
  const lw      = 10;
  const color   = scoreColor(score);

  let current = 0;
  const target = score;
  const step   = target / 60;   // ~60 frames

  function draw(val) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Track
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255,255,255,0.15)';
    ctx.lineWidth   = lw;
    ctx.stroke();

    // Fill arc
    const startAngle = -Math.PI / 2;
    const endAngle   = startAngle + (Math.PI * 2 * (val / 100));
    ctx.beginPath();
    ctx.arc(cx, cy, radius, startAngle, endAngle);
    ctx.strokeStyle = color;
    ctx.lineWidth   = lw;
    ctx.lineCap     = 'round';
    ctx.stroke();
  }

  function animate() {
    current = Math.min(current + step, target);
    draw(current);
    setText('overallScore', Math.round(current) + '%');
    if (current < target) {
      scoreRingAnim = requestAnimationFrame(animate);
    }
  }

  cancelAnimationFrame(scoreRingAnim);
  animate();
}

// ---------------------------------------------------------------------------
// Radar chart
// ---------------------------------------------------------------------------
function renderRadarChart(readiness) {
  const canvas = document.getElementById('radarChart');
  if (!canvas) return;

  if (radarChartInstance) { radarChartInstance.destroy(); }

  radarChartInstance = new Chart(canvas.getContext('2d'), {
    type: 'radar',
    data: {
      labels: ['Skill Match', 'Experience', 'Evidence', 'Overall'],
      datasets: [{
        label: 'Your Score',
        data: [
          readiness.skill_match_score,
          readiness.experience_score,
          readiness.evidence_score,
          readiness.overall_score,
        ],
        backgroundColor: 'rgba(79,70,229,0.15)',
        borderColor:     'rgba(79,70,229,0.85)',
        borderWidth: 2,
        pointBackgroundColor: '#4f46e5',
        pointRadius: 5,
        pointHoverRadius: 7,
      }, {
        label: 'Target (100%)',
        data:  [100, 100, 100, 100],
        backgroundColor: 'transparent',
        borderColor: 'rgba(156,163,175,0.35)',
        borderWidth: 1,
        borderDash: [5, 5],
        pointRadius: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          beginAtZero: true,
          max: 100,
          ticks: { stepSize: 25, font: { size: 10 }, color: '#9ca3af', backdropColor: 'transparent' },
          grid:       { color: 'rgba(0,0,0,0.06)' },
          angleLines: { color: 'rgba(0,0,0,0.08)' },
          pointLabels:{ font: { size: 11, weight: '600' }, color: '#374151' },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.raw}%` },
        },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// Breakdown details (beside radar chart)
// ---------------------------------------------------------------------------
function renderBreakdownDetails(readiness) {
  const el = document.getElementById('breakdownDetails');
  if (!el) return;

  const items = [
    { label: 'Skill Match',  score: readiness.skill_match_score, weight: '50%', icon: 'bi-code-slash'    },
    { label: 'Experience',   score: readiness.experience_score,  weight: '30%', icon: 'bi-briefcase'      },
    { label: 'Evidence',     score: readiness.evidence_score,    weight: '20%', icon: 'bi-folder-check'   },
  ];

  el.innerHTML = items.map(item => {
    const color = scoreColor(item.score);
    return `
      <div class="mb-3">
        <div class="d-flex justify-content-between align-items-center mb-1">
          <span class="fw-semibold" style="font-size:0.88rem;">
            <i class="bi ${item.icon} me-1" style="color:${color};"></i>${item.label}
          </span>
          <div>
            <span class="fw-bold" style="color:${color};font-size:0.9rem;">${item.score}%</span>
            <span class="text-muted" style="font-size:0.75rem;"> · ${item.weight}</span>
          </div>
        </div>
        <div style="height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden;">
          <div style="height:8px;background:${color};border-radius:4px;width:${item.score}%;transition:width 1s ease;"></div>
        </div>
      </div>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Skill gaps
// ---------------------------------------------------------------------------
function renderSkillGaps(gapAnalysis) {
  const el = document.getElementById('skillGaps');
  if (!el) return;

  const missing_req = gapAnalysis.missing_required || [];
  const missing_opt = gapAnalysis.missing_optional || [];

  document.getElementById('gapCount').textContent =
    (missing_req.length + missing_opt.length) || '';

  if (missing_req.length === 0 && missing_opt.length === 0) {
    el.innerHTML = `<div class="empty-state"><i class="bi bi-check-circle text-success"></i>
      <p class="fw-semibold text-success">No skill gaps — you have everything required!</p></div>`;
    return;
  }

  let html = '';

  if (missing_req.length) {
    html += `<p class="fw-semibold mb-2" style="font-size:0.88rem;">
      <span class="badge priority-high me-2">HIGH PRIORITY</span>Required — learn these first</p>`;
    html += '<div class="mb-3">' + missing_req.map(s => `
      <span class="skill-tag skill-missing">
        <i class="bi bi-x-circle me-1"></i>${s.skill || s}
      </span>`).join('') + '</div>';
  }

  if (missing_opt.length) {
    html += `<p class="fw-semibold mb-2" style="font-size:0.88rem;">
      <span class="badge priority-medium me-2">MEDIUM</span>Optional — nice to have</p>`;
    html += '<div>' + missing_opt.map(s => `
      <span class="skill-tag skill-optional">
        <i class="bi bi-dash-circle me-1"></i>${s.skill || s}
      </span>`).join('') + '</div>';
  }

  el.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Matched skills (strengths)
// ---------------------------------------------------------------------------
function renderMatchedSkills(gapAnalysis) {
  const el = document.getElementById('matchedSkills');
  if (!el) return;

  const matched_req = gapAnalysis.matched_required || [];
  const matched_opt = gapAnalysis.matched_optional || [];
  const total = matched_req.length + matched_opt.length;

  document.getElementById('strengthCount').textContent = total || '';

  if (total === 0) {
    el.innerHTML = `<div class="empty-state"><i class="bi bi-search"></i>
      <p>No matched skills detected yet.</p></div>`;
    return;
  }

  let html = '';
  if (matched_req.length) {
    html += '<p class="fw-semibold mb-2" style="font-size:0.82rem;color:#6b7280;">REQUIRED SKILLS</p>';
    html += matched_req.map(s => {
      const yrs = s.experience_years ? ` · ${s.experience_years}y` : '';
      return `<span class="skill-tag skill-matched">
        <i class="bi bi-check-circle me-1"></i>${s.skill || s}${yrs}
      </span>`;
    }).join('');
  }
  if (matched_opt.length) {
    html += '<p class="fw-semibold mt-3 mb-2" style="font-size:0.82rem;color:#6b7280;">OPTIONAL SKILLS</p>';
    html += matched_opt.map(s =>
      `<span class="skill-tag skill-pref-ok">
        <i class="bi bi-check me-1"></i>${s.skill || s}
      </span>`
    ).join('');
  }

  el.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Recommendations
// ---------------------------------------------------------------------------
function renderRecommendations(recs) {
  const el = document.getElementById('recommendations');
  if (!el) return;

  if (!recs || recs.length === 0) {
    el.innerHTML = `<div class="empty-state"><i class="bi bi-lightbulb"></i>
      <p>No recommendations yet.</p></div>`;
    return;
  }

  el.innerHTML = recs.map((r, i) => `
    <div class="rec-card">
      <div class="d-flex gap-3 align-items-start">
        <div class="rec-num">${r.priority || i + 1}</div>
        <div>
          <div class="fw-bold mb-1" style="font-size:0.92rem;">${r.title || r.message || ''}</div>
          ${r.detail ? `<div class="text-muted" style="font-size:0.83rem;line-height:1.5;">${r.detail}</div>` : ''}
          ${r.type   ? `<span class="badge mt-2 text-white" style="background:linear-gradient(135deg,#4f46e5,#7c3aed);font-size:0.72rem;">${r.type.replace(/_/g,' ')}</span>` : ''}
        </div>
      </div>
    </div>`).join('');
}

// ---------------------------------------------------------------------------
// ATS card
// ---------------------------------------------------------------------------
function renderATSCard(ats) {
  const card = document.getElementById('atsCard');
  const body = document.getElementById('atsCardBody');
  if (!card || !body) return;

  const gradeColors = { A:'#10b981', B:'#3b82f6', C:'#f59e0b', D:'#f97316', F:'#ef4444' };
  const color = gradeColors[ats.grade] || '#6b7280';

  document.getElementById('atsGradeBadge').innerHTML =
    `<span style="color:${color};">${ats.grade}</span>`;

  const bkd = ats.breakdown || {};
  const bkdHtml = Object.entries(bkd).map(([key, val]) => `
    <div class="col-6 col-md-4 mb-2">
      <div class="p-2 rounded" style="background:#f9fafb;border:1px solid #e5e7eb;">
        <div class="d-flex justify-content-between mb-1">
          <span style="font-size:0.75rem;font-weight:600;">${key.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}</span>
          <span style="font-size:0.75rem;font-weight:700;color:${val.score>=70?'#10b981':val.score>=50?'#f59e0b':'#ef4444'};">${val.score}%</span>
        </div>
        <div style="height:4px;background:#e5e7eb;border-radius:2px;">
          <div style="height:4px;background:${val.score>=70?'#10b981':val.score>=50?'#f59e0b':'#ef4444'};border-radius:2px;width:${val.score}%;"></div>
        </div>
        <div style="font-size:0.7rem;color:#9ca3af;margin-top:2px;">${val.weight}</div>
      </div>
    </div>`).join('');

  const tips = (ats.improvement_tips || []).filter(t => t.impact !== 'LOW').slice(0, 3);
  const tipsHtml = tips.map(t => `
    <div class="d-flex gap-2 mb-2 p-2 rounded" style="background:#fafafa;border:1px solid #f3f4f6;">
      <span class="badge flex-shrink-0" style="height:fit-content;margin-top:2px;background:${
        t.impact==='CRITICAL'?'#fee2e2':t.impact==='HIGH'?'#fef3c7':'#dbeafe'};color:${
        t.impact==='CRITICAL'?'#991b1b':t.impact==='HIGH'?'#92400e':'#1e40af'};">${t.impact}</span>
      <span style="font-size:0.82rem;">${t.tip}</span>
    </div>`).join('');

  body.innerHTML = `
    <div class="d-flex align-items-center gap-3 mb-3">
      <div class="ats-grade-badge" style="background:${color}15;border:3px solid ${color};color:${color};">
        ${ats.grade}
      </div>
      <div>
        <div class="fw-bold fs-4" style="color:${color};">${ats.total_score}%</div>
        <div class="text-muted" style="font-size:0.85rem;">${ats.grade_label}</div>
        <div class="text-muted" style="font-size:0.8rem;">${ats.word_count} words in resume</div>
      </div>
    </div>
    <div class="row g-1 mb-3">${bkdHtml}</div>
    ${tipsHtml ? `<p class="fw-semibold mb-2" style="font-size:0.88rem;"><i class="bi bi-tools me-1 text-warning"></i>Top Improvements</p>${tipsHtml}` : ''}`;

  card.style.display = '';
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------
async function loadProjects() {
  try {
    const res  = await fetch('/api/projects');
    const data = await res.json();
    renderProjects(data.projects || []);
  } catch {
    document.getElementById('projectsList').innerHTML =
      '<p class="text-muted text-center">Failed to load projects.</p>';
  }
}

function renderProjects(projects) {
  const el = document.getElementById('projectsList');
  if (!el) return;

  if (!projects.length) {
    el.innerHTML = `
      <div class="empty-state">
        <i class="bi bi-folder-x"></i>
        <p class="fw-semibold">No projects yet</p>
        <p>Add projects to boost your evidence score by up to +20 points.</p>
      </div>`;
    return;
  }

  el.innerHTML = projects.map(p => {
    const skills = (p.skills_used || []).map(s =>
      `<span class="project-skill-tag">${s}</span>`).join('');
    const dates = p.start_date
      ? `<span class="text-muted" style="font-size:0.78rem;">${p.start_date} → ${p.end_date || 'Present'}</span>`
      : '';
    const urlBadge = p.project_url
      ? `<a href="${p.project_url}" target="_blank" class="badge text-decoration-none ms-2"
           style="background:#d1fae5;color:#065f46;"><i class="bi bi-link me-1"></i>URL ✓</a>`
      : '';

    return `
      <div class="project-item" id="proj-${p.id}">
        <div class="d-flex justify-content-between align-items-start mb-1">
          <span class="fw-bold" style="font-size:0.92rem;">${p.title}${urlBadge}</span>
          <button class="btn btn-link btn-sm p-0 text-danger" onclick="deleteProject(${p.id})" title="Delete">
            <i class="bi bi-trash"></i>
          </button>
        </div>
        ${p.description ? `<p class="text-muted mb-1" style="font-size:0.82rem;">${p.description}</p>` : ''}
        ${dates}
        ${skills ? `<div class="mt-2">${skills}</div>` : ''}
      </div>`;
  }).join('');
}

async function addProject() {
  const title = document.getElementById('projectTitle').value.trim();
  if (!title) { showToast('Project title is required', 'warning'); return; }

  const skillsRaw = document.getElementById('projectSkills').value;
  const skills = skillsRaw.split(',').map(s => s.trim()).filter(Boolean);

  const btn = document.getElementById('saveProjectBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Saving…';

  try {
    const res = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        description:  document.getElementById('projectDescription').value.trim(),
        skills_used:  skills,
        start_date:   document.getElementById('projectStartDate').value || null,
        end_date:     document.getElementById('projectEndDate').value   || null,
        project_url:  document.getElementById('projectUrl').value.trim() || null,
      }),
    });

    const data = await res.json();
    if (data.error) { showToast(data.error, 'danger'); return; }

    // Close modal, reset form, reload
    bootstrap.Modal.getInstance(document.getElementById('addProjectModal')).hide();
    ['projectTitle','projectDescription','projectSkills','projectStartDate',
     'projectEndDate','projectUrl'].forEach(id => { document.getElementById(id).value = ''; });

    showToast('Project added! Recalculating your score…', 'success');
    await loadProjects();
    await loadDashboard();     // re-score with new evidence
    await loadProgress();

  } catch {
    showToast('Failed to add project. Please try again.', 'danger');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-plus-circle me-1"></i>Add Project';
  }
}

async function deleteProject(id) {
  if (!confirm('Delete this project? This will affect your evidence score.')) return;
  try {
    const res = await fetch(`/api/projects/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.error) { showToast(data.error, 'danger'); return; }
    showToast('Project deleted', 'info');
    await loadProjects();
    await loadDashboard();
    await loadProgress();
  } catch {
    showToast('Failed to delete project', 'danger');
  }
}

// ---------------------------------------------------------------------------
// Progress chart
// ---------------------------------------------------------------------------
async function loadProgress() {
  try {
    const res  = await fetch('/api/progress');
    const data = await res.json();
    renderProgressChart(data);
    renderProgressTimeline(data);
  } catch {
    document.getElementById('progressTimeline').innerHTML =
      '<p class="text-muted text-center">Failed to load progress.</p>';
  }
}

function renderProgressChart(data) {
  const canvas = document.getElementById('progressChart');
  if (!canvas) return;

  const timeline = data.timeline || [];

  if (progressChartInstance) { progressChartInstance.destroy(); }

  if (timeline.length < 2) {
    // Not enough data — show placeholder message
    canvas.style.display = 'none';
    return;
  }

  canvas.style.display = '';
  const labels = timeline.map(t => {
    const d = new Date(t.date);
    const datePart = d.toLocaleDateString('en-GB', { day:'2-digit', month:'short' });
    const timePart = d.toLocaleTimeString('en-GB', { hour:'2-digit', minute:'2-digit' });
    return `${datePart} ${timePart}`;
  });

  progressChartInstance = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Overall',
          data:  timeline.map(t => t.overall_score),
          borderColor: '#4f46e5',
          backgroundColor: 'rgba(79,70,229,0.08)',
          borderWidth: 2.5,
          tension: 0.4,
          fill: true,
          pointBackgroundColor: '#4f46e5',
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: 'Skill Match',
          data:  timeline.map(t => t.skill_match_score),
          borderColor: '#10b981',
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          tension: 0.4,
          pointRadius: 3,
          borderDash: [4, 3],
        },
        {
          label: 'Evidence',
          data:  timeline.map(t => t.evidence_score),
          borderColor: '#f59e0b',
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          tension: 0.4,
          pointRadius: 3,
          borderDash: [4, 3],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          ticks: { stepSize: 25, font: { size: 10 }, color: '#9ca3af' },
          grid: { color: 'rgba(0,0,0,0.05)' },
        },
        x: {
          ticks: { font: { size: 10 }, color: '#9ca3af' },
          grid:  { display: false },
        },
      },
      plugins: {
        legend: {
          position: 'top',
          labels: { boxWidth: 12, font: { size: 10 }, padding: 10 },
        },
        tooltip: { mode: 'index', intersect: false },
      },
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
    },
  });
}

function renderProgressTimeline(data) {
  const el = document.getElementById('progressTimeline');
  if (!el) return;

  const timeline = data.timeline || [];

  // Improvement banner
  const impEl = document.getElementById('progressImprovement');
  if (impEl && data.improvement !== undefined && data.improvement !== 0) {
    const positive = data.improvement > 0;
    impEl.innerHTML = `
      <div class="d-flex align-items-center gap-2 p-2 rounded mb-2" style="background:${positive?'#d1fae5':'#fee2e2'};">
        <i class="bi bi-${positive?'arrow-up':'arrow-down'}-circle text-${positive?'success':'danger'}"></i>
        <span style="font-size:0.85rem;font-weight:600;color:${positive?'#065f46':'#991b1b'};">
          ${positive?'+':''}${data.improvement}% overall improvement
        </span>
      </div>`;
    impEl.style.display = '';
  }

  if (!timeline.length) {
    el.innerHTML = '<p class="text-muted text-center" style="font-size:0.83rem;">No progress data yet — re-visit after upskilling!</p>';
    return;
  }

  // Show last 5 snapshots
  el.innerHTML = timeline.slice(-5).reverse().map(t => {
    const d = new Date(t.date);
    const datePart = d.toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'2-digit' });
    const timePart = d.toLocaleTimeString('en-GB', { hour:'2-digit', minute:'2-digit' });
    const label = `${datePart} ${timePart}`;
    const color = scoreColor(t.overall_score);
    return `
      <div class="timeline-row">
        <span class="timeline-date">${label}</span>
        <div class="timeline-bar-wrap">
          <div class="timeline-bar-fill" style="width:${t.overall_score}%;background:${color};"></div>
        </div>
        <span class="timeline-score" style="color:${color};">${t.overall_score}%</span>
      </div>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function scoreColor(score) {
  if (score >= 80) return '#10b981';
  if (score >= 60) return '#3b82f6';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function hideDashLoading() {
  const overlay = document.getElementById('dashLoading');
  if (overlay) {
    overlay.style.opacity = '0';
    overlay.style.transition = 'opacity 0.4s';
    setTimeout(() => { overlay.style.display = 'none'; }, 400);
  }
}

function showError(msg) {
  const main = document.querySelector('.container.py-4');
  if (main) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-danger alert-dismissible d-flex align-items-center gap-2 mb-3';
    alert.innerHTML = `
      <i class="bi bi-exclamation-circle-fill"></i>
      <div>${msg} <a href="/" class="alert-link">Upload a resume to get started →</a></div>
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    main.insertBefore(alert, main.firstChild);
  }
}

function showToast(msg, type = 'info') {
  const typeMap = { success:'success', danger:'danger', warning:'warning', info:'primary' };
  const div = document.createElement('div');
  div.className = `alert alert-${typeMap[type]||'secondary'} alert-dismissible toast-float`;
  div.innerHTML = `${msg}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 5000);
}
