const BACKEND_URL = 'http://127.0.0.1:8000';

// Helper: Escape HTML to prevent XSS
function escapeHTML(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Helper: Toggle Button Loading State
function setButtonLoading(btn, isLoading) {
  if (isLoading) {
    btn.disabled = true;
    btn.dataset.originalText = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span> <span>Processing...</span>`;
  } else {
    btn.disabled = false;
    if (btn.dataset.originalText) {
      btn.innerHTML = btn.dataset.originalText;
    }
  }
}

// Helper: Render Error Alert
function renderError(containerId, message) {
  const container = document.getElementById(containerId);
  container.innerHTML = `
    <div class="alert-error">
      <span>⚠️</span>
      <div>
        <strong>Error:</strong> ${escapeHTML(message)}
      </div>
    </div>
  `;
}

// ==========================================
// BACKEND HEALTH STATUS CHECK
// ==========================================
async function checkBackendHealth() {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  
  try {
    const res = await fetch(`${BACKEND_URL}/health`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    });
    
    if (res.ok) {
      dot.className = 'status-dot connected';
      text.textContent = 'Connected to Backend';
    } else {
      dot.className = 'status-dot disconnected';
      text.textContent = `Server Error (${res.status})`;
    }
  } catch (error) {
    dot.className = 'status-dot disconnected';
    text.textContent = 'Backend Disconnected';
  }
}

// Initialize and schedule health check
checkBackendHealth();
setInterval(checkBackendHealth, 10000);


// ==========================================
// SECTION 1 & 2: ISSUE TRIAGE & DUPLICATES
// ==========================================
async function handleIssueTriage(event) {
  event.preventDefault();
  
  const repoInput = document.getElementById('repo-input').value.trim();
  const issueNumInput = document.getElementById('issue-number-input').value.trim();
  const analyzeBtn = document.getElementById('analyze-btn');
  const triageContainer = document.getElementById('triage-result-container');
  const duplicatesContainer = document.getElementById('duplicates-result-container');

  if (!repoInput || !issueNumInput) return;

  // Split owner/repo
  const parts = repoInput.split('/');
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    renderError('triage-result-container', 'Invalid repository format. Please use "owner/repo" (e.g., spring-projects/spring-boot).');
    return;
  }
  const [owner, repo] = parts;
  const issueNumber = parseInt(issueNumInput, 10);

  // Set loading states
  setButtonLoading(analyzeBtn, true);
  
  // Render Triage skeleton
  triageContainer.innerHTML = `
    <div class="results-header">
      <div class="issue-meta-title-area">
        <div class="skeleton-pulse skeleton-text short" style="height: 14px; width: 80px;"></div>
        <div class="skeleton-pulse skeleton-text heading" style="height: 28px; width: 90%;"></div>
        <div class="meta-badges-row" style="margin-top: 10px;">
          <div class="skeleton-pulse" style="width: 60px; height: 20px; border-radius: 9999px;"></div>
          <div class="skeleton-pulse" style="width: 80px; height: 20px; border-radius: 9999px;"></div>
        </div>
      </div>
    </div>
    <div class="details-grid" style="margin-top: 20px;">
      <div class="skeleton-pulse info-box" style="height: 90px; border: none;"></div>
      <div class="skeleton-pulse info-box" style="height: 90px; border: none;"></div>
    </div>
    <div class="skeleton-pulse" style="height: 120px; border-radius: var(--border-radius-md); margin-top: 20px;"></div>
  `;

  // Render Duplicates skeleton
  duplicatesContainer.innerHTML = `
    <div class="duplicates-container">
      <div class="skeleton-pulse" style="height: 60px; border-radius: var(--border-radius-md);"></div>
      <div class="skeleton-pulse" style="height: 60px; border-radius: var(--border-radius-md);"></div>
    </div>
  `;

  try {
    const res = await fetch(`${BACKEND_URL}/github/${owner}/${repo}/issues/${issueNumber}/analyze`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    });

    if (!res.ok) {
      const errBody = await res.text();
      throw new Error(`Server returned status ${res.status}: ${errBody || 'Unknown Error'}`);
    }

    const data = await res.json();
    renderTriageReport(data);
    renderDuplicateReport(data.duplicate_candidates);

  } catch (error) {
    console.error('Triage analysis failed:', error);
    renderError('triage-result-container', `Triage failed: ${error.message}`);
    renderError('duplicates-result-container', 'Could not evaluate duplicates due to triage analysis error.');
  } finally {
    setButtonLoading(analyzeBtn, false);
  }
}

function renderTriageReport(data) {
  const container = document.getElementById('triage-result-container');
  
  const issue = data.issue || {};
  const analysis = data.analysis || {};
  const moduleIntel = analysis.module_intelligence || {};
  
  // Build state badge
  const stateClass = (issue.state || 'open').toLowerCase() === 'open' ? 'open' : 'closed';
  const stateBadge = `<span class="badge badge-state ${stateClass}">${escapeHTML(issue.state || 'open')}</span>`;
  
  // Build severity badge
  const severity = (analysis.severity || 'low').toLowerCase();
  const severityBadge = `<span class="badge badge-severity ${severity}">${escapeHTML(analysis.severity || 'low')}</span>`;
  
  // Build labels list
  let labelPills = '';
  if (issue.labels && Array.isArray(issue.labels)) {
    labelPills = issue.labels.map(l => `<span class="label-pill">${escapeHTML(typeof l === 'string' ? l : l.name)}</span>`).join(' ');
  }

  // Build suggested labels pills
  let suggestedPills = '<span style="font-size: 0.85rem; color: var(--text-muted);">None suggested</span>';
  if (analysis.suggested_labels && Array.isArray(analysis.suggested_labels) && analysis.suggested_labels.length > 0) {
    suggestedPills = `
      <div class="list-pills-container">
        ${analysis.suggested_labels.map(label => `<span class="pill-suggested-label">${escapeHTML(label)}</span>`).join('')}
      </div>
    `;
  }

  // Build missing information warnings
  let missingInfoContent = '<span style="font-size: 0.85rem; color: var(--text-muted);">None reported</span>';
  if (analysis.missing_information && Array.isArray(analysis.missing_information) && analysis.missing_information.length > 0) {
    missingInfoContent = `
      <div class="list-pills-container">
        ${analysis.missing_information.map(info => `<span class="pill-missing-info">⚠️ ${escapeHTML(info)}</span>`).join('')}
      </div>
    `;
  }

  container.innerHTML = `
    <!-- Header -->
    <div class="results-header">
      <div class="issue-meta-title-area">
        <span class="issue-number-tag">Issue #${escapeHTML(issue.number)}</span>
        <h3 class="issue-title">
          <a href="${escapeHTML(issue.html_url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(issue.title)} ↗</a>
        </h3>
        <div class="meta-badges-row">
          ${stateBadge}
          ${severityBadge}
          <span class="badge" style="background-color: rgba(99,102,241,0.1); color: #818cf8; border-color: rgba(99,102,241,0.2);">
            ${escapeHTML(analysis.issue_type || 'unknown')}
          </span>
          ${labelPills}
        </div>
      </div>
    </div>

    <!-- Analytics Cards Grid -->
    <div class="details-grid">
      <!-- Module Info -->
      <div class="info-box">
        <h4>📦 Module & Component Ownership</h4>
        <div class="module-intel-list">
          <div class="module-intel-item">
            <span>Probable Module</span>
            <span>${escapeHTML(analysis.probable_module || 'N/A')}</span>
          </div>
          <div class="module-intel-item">
            <span>Probable Subsystem</span>
            <span>${escapeHTML(moduleIntel.probable_subsystem || 'N/A')}</span>
          </div>
          <div class="module-intel-item">
            <span>Component Ownership</span>
            <span>${escapeHTML(moduleIntel.component_ownership || 'N/A')}</span>
          </div>
          <div class="module-intel-item">
            <span>Affected Area</span>
            <span>${escapeHTML(moduleIntel.affected_area || 'N/A')}</span>
          </div>
        </div>
      </div>

      <!-- Triage Metadata labels/missing -->
      <div class="info-box" style="display: flex; flex-direction: column; gap: 0.75rem;">
        <div>
          <h4 style="margin-bottom: 0.25rem;">🏷️ Suggested Labels</h4>
          ${suggestedPills}
        </div>
        <div>
          <h4 style="margin-bottom: 0.25rem;">🔍 Missing Information</h4>
          ${missingInfoContent}
        </div>
      </div>
    </div>

    <!-- Summary Box -->
    <div class="analysis-summary-box">
      <h4>⚡ Copilot Triage Summary</h4>
      <p class="analysis-summary-text">${escapeHTML(analysis.summary || 'No summary provided.')}</p>
      
      <div class="analysis-reasoning-box">
        <strong>Reasoning:</strong> ${escapeHTML(analysis.reasoning || 'No explanation provided.')}
      </div>
    </div>
  `;
}

function renderDuplicateReport(candidates) {
  const container = document.getElementById('duplicates-result-container');
  
  if (!candidates || !Array.isArray(candidates) || candidates.length === 0) {
    container.innerHTML = `
      <div class="hub-placeholder" style="padding: 2rem 1rem;">
        <div class="hub-placeholder-icon">✅</div>
        <h3>No Duplicate Candidates Found</h3>
        <p>This issue seems to describe a unique problem based on current reports.</p>
      </div>
    `;
    return;
  }

  const cardsHtml = candidates.map(cand => {
    const confidence = (cand.confidence || 'low').toLowerCase();
    const scorePct = typeof cand.similarity_score === 'number' 
      ? `${(cand.similarity_score * 100).toFixed(0)}%` 
      : 'N/A';
      
    return `
      <div class="duplicate-card">
        <div class="duplicate-header">
          <a class="duplicate-issue-link" href="${escapeHTML(cand.issue_url || '#')}" target="_blank" rel="noopener noreferrer">
            Issue #${escapeHTML(cand.issue_number)} ↗
          </a>
          <div class="duplicate-badge-row">
            <span class="score-badge">Similarity: ${scorePct}</span>
            <span class="badge badge-confidence ${confidence}">${escapeHTML(cand.confidence)} confidence</span>
          </div>
        </div>
        <p class="duplicate-reasoning">${escapeHTML(cand.reasoning || 'No details provided.')}</p>
      </div>
    `;
  }).join('');

  container.innerHTML = `<div class="duplicates-container">${cardsHtml}</div>`;
}


// ==========================================
// SECTION 3: SEMANTIC ISSUE SEARCH
// ==========================================
async function handleSemanticSearch(event) {
  event.preventDefault();
  
  const queryInput = document.getElementById('search-query-input').value.trim();
  const searchBtn = document.getElementById('search-btn');
  const searchContainer = document.getElementById('search-result-container');

  if (!queryInput) return;

  setButtonLoading(searchBtn, true);

  // Loading skeleton
  searchContainer.innerHTML = `
    <div class="issue-results-list">
      <div class="skeleton-pulse" style="height: 80px; border-radius: var(--border-radius-md);"></div>
      <div class="skeleton-pulse" style="height: 80px; border-radius: var(--border-radius-md);"></div>
    </div>
  `;

  try {
    const res = await fetch(`${BACKEND_URL}/issues/search?query=${encodeURIComponent(queryInput)}`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    });

    if (!res.ok) {
      const errBody = await res.text();
      throw new Error(`Server returned status ${res.status}: ${errBody || 'Unknown Error'}`);
    }

    const data = await res.json();
    renderSearchResults(data);

  } catch (error) {
    console.error('Semantic search failed:', error);
    renderError('search-result-container', `Search failed: ${error.message}`);
  } finally {
    setButtonLoading(searchBtn, false);
  }
}

function renderSearchResults(data) {
  const container = document.getElementById('search-result-container');
  
  // Extract issue array robustly
  let issues = [];
  
  // Unwrap results if wrapped in an outer object from the backend
  let resultsObj = data;
  if (data && data.results && !Array.isArray(data.results)) {
    resultsObj = data.results;
  }
  
  if (resultsObj && resultsObj.metadatas && Array.isArray(resultsObj.metadatas[0])) {
    // ChromaDB style response: metadatas[0] is array of metadata objects, documents[0] is array of strings
    issues = resultsObj.metadatas[0].map((meta, i) => {
      // Extract title from documents if possible
      let title = meta.title || "Untitled Issue";
      const docText = resultsObj.documents && resultsObj.documents[0] && resultsObj.documents[0][i];
      if (docText) {
        // Look for Title: header in document text
        const titleMatch = docText.match(/^Title:\s*\n?([^\n]+)/i);
        if (titleMatch) {
          title = titleMatch[1].trim();
        }
      }
      return {
        ...meta,
        title: title,
        number: meta.issue_number || meta.number,
        html_url: meta.issue_url || meta.html_url,
        summary: meta.analysis_summary || meta.summary || ""
      };
    });
  } else if (Array.isArray(data)) {
    issues = data;
  } else if (data && Array.isArray(data.issues)) {
    issues = data.issues;
  } else if (data && Array.isArray(data.results)) {
    issues = data.results;
  }

  if (issues.length === 0) {
    container.innerHTML = `
      <div class="hub-placeholder" style="padding: 2.5rem 1rem;">
        <div class="hub-placeholder-icon">📭</div>
        <h3>No Matching Issues</h3>
        <p>Try rephrasing your search terms or look for general topics.</p>
      </div>
    `;
    return;
  }

  const itemsHtml = issues.map(issue => {
    const state = (issue.state || 'open').toLowerCase();
    const stateBadge = `<span class="badge badge-state ${state === 'open' ? 'open' : 'closed'}">${escapeHTML(issue.state || 'open')}</span>`;
    
    let labelPills = '';
    const rawLabels = issue.labels || issue.current_labels;
    if (rawLabels) {
      if (Array.isArray(rawLabels)) {
        labelPills = rawLabels.map(l => `<span class="label-pill">${escapeHTML(typeof l === 'string' ? l : l.name)}</span>`).join(' ');
      } else if (typeof rawLabels === 'string') {
        const list = rawLabels.includes(',') ? rawLabels.split(',') : [rawLabels];
        labelPills = list.map(l => `<span class="label-pill">${escapeHTML(l.trim())}</span>`).join(' ');
      }
    }

    const titleLink = issue.html_url 
      ? `<a href="${escapeHTML(issue.html_url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(issue.title)} ↗</a>`
      : escapeHTML(issue.title);

    const issueNumberText = issue.number ? `Issue #${escapeHTML(issue.number)}` : 'Issue';

    return `
      <div class="search-result-item">
        <div class="search-result-header">
          <div>
            <h4 class="search-result-title">${titleLink}</h4>
            <div class="search-result-meta">
              <span style="font-size: 0.8rem; color: var(--text-muted); font-weight: 500;">${issueNumberText}</span>
              ${stateBadge}
              ${labelPills}
            </div>
          </div>
        </div>
        ${issue.summary ? `<p class="search-result-summary" style="margin-top: 0.5rem;">${escapeHTML(issue.summary)}</p>` : ''}
      </div>
    `;
  }).join('');

  container.innerHTML = `<div class="issue-results-list">${itemsHtml}</div>`;
}


// ==========================================
// SECTION 4: CONTRIBUTOR ONBOARDING ASSISTANT
// ==========================================
async function handleContributorAsk(event) {
  event.preventDefault();
  
  const questionInput = document.getElementById('contributor-question-input').value.trim();
  const askBtn = document.getElementById('ask-btn');
  const answerContainer = document.getElementById('contributor-result-container');

  if (!questionInput) return;

  setButtonLoading(askBtn, true);

  // Loading skeleton
  answerContainer.innerHTML = `
    <div class="contributor-answer-box">
      <div class="contributor-header-row">
        <div class="skeleton-pulse" style="width: 80px; height: 16px;"></div>
        <div class="skeleton-pulse" style="width: 100px; height: 16px;"></div>
      </div>
      <div class="skeleton-pulse" style="height: 120px; border-radius: var(--border-radius-md);"></div>
    </div>
  `;

  try {
    const res = await fetch(`${BACKEND_URL}/contributors/ask`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        question: questionInput,
        limit: 5
      })
    });

    if (!res.ok) {
      const errBody = await res.text();
      throw new Error(`Server returned status ${res.status}: ${errBody || 'Unknown Error'}`);
    }

    const data = await res.json();
    renderContributorAnswer(data);

  } catch (error) {
    console.error('Contributor question failed:', error);
    renderError('contributor-result-container', `Failed to get onboarding response: ${error.message}`);
  } finally {
    setButtonLoading(askBtn, false);
  }
}

function renderContributorAnswer(data) {
  const container = document.getElementById('contributor-result-container');
  
  if (!data) {
    renderError('contributor-result-container', 'Malformed backend response: data missing.');
    return;
  }

  // Handle both nested and flat responses
  let answerObj = data;
  if (data.answer && typeof data.answer === 'object') {
    // Nested structure: { "answer": { "answer": "...", "confidence": "..." } }
    answerObj = data.answer;
  } else if (typeof data.answer === 'string') {
    // Flat structure: { "answer": "...", "confidence": "..." }
    answerObj = data;
  }

  const confidence = (answerObj.confidence || 'low').toLowerCase();
  
  // Format referenced issues
  let referencedHtml = '';
  if (answerObj.referenced_issues && Array.isArray(answerObj.referenced_issues) && answerObj.referenced_issues.length > 0) {
    const pills = answerObj.referenced_issues.map(num => `
      <span class="ref-issue-pill">Issue #${escapeHTML(num)}</span>
    `).join('');
    
    referencedHtml = `
      <div class="referenced-section" style="margin-top: 1rem;">
        <h4 class="referenced-title">🔗 Referenced Knowledge Tickets</h4>
        <div class="referenced-issues-pills">
          ${pills}
        </div>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="contributor-answer-box">
      <!-- Confidence & Meta header -->
      <div class="contributor-header-row">
        <div class="contributor-confidence">
          <span>Confidence:</span>
          <span class="badge badge-confidence ${confidence}">${escapeHTML(answerObj.confidence)}</span>
        </div>
        <div style="font-size: 0.8rem; color: var(--text-muted);">
          Onboarding AI Assistant
        </div>
      </div>

      <!-- Core Answer Body -->
      <div class="answer-body">${escapeHTML(answerObj.answer)}</div>

      <!-- Optional Reasoning / Background -->
      ${answerObj.reasoning ? `
        <div class="analysis-reasoning-box" style="margin-bottom: 0.5rem;">
          <strong>Explanation:</strong> ${escapeHTML(answerObj.reasoning)}
        </div>
      ` : ''}

      <!-- Referenced Issues -->
      ${referencedHtml}
    </div>
  `;
}


// ==========================================
// EVENT LISTENERS REGISTER
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('triage-form').addEventListener('submit', handleIssueTriage);
  document.getElementById('search-form').addEventListener('submit', handleSemanticSearch);
  document.getElementById('contributor-form').addEventListener('submit', handleContributorAsk);
});
