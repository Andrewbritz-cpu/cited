/* =========================================================
   Cited — frontend JavaScript
   Wires up: upload form submission, FAQ accordion, scanner
   animation, and scroll reveals.
   ========================================================= */

// ---------- FAQ accordion ----------
document.querySelectorAll('.faq-item').forEach(item => {
  item.addEventListener('click', () => item.classList.toggle('open'));
});

// ---------- Hero scanner score animation ----------
(function animateLiveScore() {
  const el = document.getElementById('liveScore');
  if (!el) return;
  const targets = [47, 52, 44, 49, 41, 48, 53, 46];
  let i = 0;
  setInterval(() => {
    const start = parseInt(el.textContent, 10);
    const end = targets[i % targets.length];
    const steps = 20;
    const diff = (end - start) / steps;
    let step = 0;
    const tick = setInterval(() => {
      step++;
      el.textContent = Math.round(start + diff * step);
      if (step >= steps) clearInterval(tick);
    }, 25);
    i++;
  }, 2800);
})();

// ---------- Scroll reveal ----------
const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('in'); });
}, { threshold: 0.1 });
document.querySelectorAll('.stat, .tier, .how-step, .faq-item, .section-title').forEach(el => {
  el.classList.add('reveal');
  revealObserver.observe(el);
});

// ---------- Upload form submission ----------
const form = document.getElementById('scanForm');
const errorBox = document.getElementById('formError');
const resultPanel = document.getElementById('resultPanel');
const submitBtn = document.getElementById('scanSubmit');

if (form) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorBox.classList.remove('visible');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Scanning…';

    const formData = new FormData(form);

    try {
      const response = await fetch('/api/scan/free', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Something went wrong.' }));
        throw new Error(err.detail || 'Scan failed.');
      }

      const data = await response.json();
      renderResult(data);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.classList.add('visible');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Scan my CV — free';
    }
  });
}

function renderResult(data) {
  if (!resultPanel) return;

  const issuesHtml = (data.structural_issues || []).map(issue =>
    `<li><strong>${escapeHtml(issue.severity.toUpperCase())}:</strong> ${escapeHtml(issue.description)}</li>`
  ).join('') || '<li>No critical structural issues detected.</li>';

  const keywordsHtml = (data.missing_keywords || []).map(kw =>
    `<li>${escapeHtml(kw)}</li>`
  ).join('') || '<li>No specific keyword gaps to flag.</li>';

  resultPanel.innerHTML = `
    <div class="result-score-row">
      <div class="result-big-score">${data.score}</div>
      <div>
        <div class="result-meta">ATS Score · ${escapeHtml(data.region)} profile</div>
        <div class="result-meta" style="margin-top: 4px;">
          Estimated rejection: ${data.rejection_estimate}%
        </div>
      </div>
    </div>
    <div class="result-section">
      <h4>Top structural issues</h4>
      <ul>${issuesHtml}</ul>
    </div>
    <div class="result-section">
      <h4>Missing keywords</h4>
      <ul>${keywordsHtml}</ul>
    </div>
    <p style="font-size: 13px; color: var(--ink-muted); font-family: var(--mono);">
      Save this link to come back later: <br>
      <code style="font-family: var(--mono); background: var(--paper-dark); padding: 2px 8px; word-break: break-all;">cited.co.za/upgrade?scan=${data.scan_id}</code>
      <br><br>
      Want the full diagnostic — line-by-line annotations, complete keyword
      analysis, region-tuned fix guide?
    </p>
    <a href="${data.upgrade_url}" class="result-upgrade">
      Get the full report — R99 →
    </a>
  `;
  resultPanel.classList.add('visible');
  if (form) form.style.display = 'none';
  resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}
