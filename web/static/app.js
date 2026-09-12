(() => {
  "use strict";

  const analyzeForm = document.getElementById("analyze-form");
  const urlInput = document.getElementById("url-input");
  const analyzeBtn = document.getElementById("analyze-btn");
  const analyzeError = document.getElementById("analyze-error");

  const configureCard = document.getElementById("configure-card");
  const previewThumb = document.getElementById("preview-thumb");
  const previewTitle = document.getElementById("preview-title");
  const previewSite = document.getElementById("preview-site");
  const previewCount = document.getElementById("preview-count");
  const previewDuration = document.getElementById("preview-duration");
  const previewWarning = document.getElementById("preview-warning");

  const jobForm = document.getElementById("job-form");
  const qualitySelect = document.getElementById("quality-select");
  const namingSelect = document.getElementById("naming-select");
  const subfolderInput = document.getElementById("subfolder-input");
  const concurrencyInput = document.getElementById("concurrency-input");
  const startBtn = document.getElementById("start-btn");
  const jobError = document.getElementById("job-error");

  const jobsList = document.getElementById("jobs-list");
  const jobsEmpty = document.getElementById("jobs-empty");
  const jobCardTemplate = document.getElementById("job-card-template");

  let currentUrl = null;
  const jobCards = new Map(); // job_id -> DOM element

  function jsonFetch(url, options = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
    return fetch(url, Object.assign({}, options, { headers })).then(async (res) => {
      let body = null;
      try {
        body = await res.json();
      } catch (_) {
        body = null;
      }
      if (!res.ok) {
        const message = (body && body.error) || `Request failed (${res.status})`;
        throw new Error(message);
      }
      return body;
    });
  }

  function showError(el, message) {
    el.textContent = message;
    el.hidden = false;
  }

  function hideError(el) {
    el.hidden = true;
    el.textContent = "";
  }

  function formatDuration(seconds) {
    if (!seconds && seconds !== 0) return "";
    seconds = Math.round(seconds);
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  }

  function formatSpeed(bytesPerSec) {
    if (!bytesPerSec) return "";
    const units = ["B", "KB", "MB", "GB"];
    let value = bytesPerSec;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    return `${value.toFixed(1)} ${units[unit]}/s`;
  }

  // ---- Analyze ----

  analyzeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideError(analyzeError);
    hideError(jobError);
    configureCard.hidden = true;

    const url = urlInput.value.trim();
    if (!url) return;

    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "Analyzing…";
    try {
      const data = await jsonFetch("/api/analyze", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      currentUrl = data.url;
      renderPreview(data);
      configureCard.hidden = false;
    } catch (err) {
      showError(analyzeError, err.message);
    } finally {
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = "Analyze";
    }
  });

  function renderPreview(data) {
    previewTitle.textContent = data.title;
    previewSite.textContent = data.site;
    previewCount.textContent = data.is_playlist ? `${data.item_count} items` : "";
    previewDuration.textContent = data.duration ? formatDuration(data.duration) : "";

    if (data.thumbnail) {
      previewThumb.src = data.thumbnail;
      previewThumb.hidden = false;
    } else {
      previewThumb.hidden = true;
    }

    if (data.warnings && data.warnings.length) {
      previewWarning.textContent = data.warnings.join(" ");
      previewWarning.hidden = false;
    } else {
      previewWarning.hidden = true;
    }

    qualitySelect.innerHTML = "";
    for (const q of data.qualities) {
      const opt = document.createElement("option");
      opt.value = q.key;
      opt.textContent = q.label;
      qualitySelect.appendChild(opt);
    }
  }

  // ---- Start job ----

  jobForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideError(jobError);
    if (!currentUrl) return;

    startBtn.disabled = true;
    try {
      const data = await jsonFetch("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          url: currentUrl,
          quality: qualitySelect.value,
          filename_mode: namingSelect.value,
          subfolder: subfolderInput.value.trim(),
          concurrency: Number(concurrencyInput.value) || 1,
        }),
      });
      // The job card is created from the SSE stream / the follow-up
      // fetch below, whichever arrives first -- ensureJobCard() is
      // idempotent by job id.
      const job = await jsonFetch(`/api/jobs/${data.job_id}`);
      renderJob(job);
    } catch (err) {
      showError(jobError, err.message);
    } finally {
      startBtn.disabled = false;
    }
  });

  // ---- Job rendering ----

  function ensureJobCard(jobId) {
    let card = jobCards.get(jobId);
    if (card) return card;

    const fragment = jobCardTemplate.content.cloneNode(true);
    card = fragment.querySelector(".job");
    card.dataset.jobId = jobId;
    card.querySelector(".job-cancel").addEventListener("click", () => {
      jsonFetch(`/api/jobs/${jobId}/cancel`, { method: "POST", body: "{}" }).catch(() => {});
    });

    jobsEmpty.hidden = true;
    jobsList.prepend(card);
    jobCards.set(jobId, card);
    return card;
  }

  function renderJob(job) {
    const card = ensureJobCard(job.id);

    card.querySelector(".job-title").textContent = job.title;

    const stateEl = card.querySelector(".job-state");
    stateEl.textContent = job.state;
    stateEl.className = `job-state badge state-${job.state}`;

    const progress = job.progress;
    const fraction = progress ? progress.overall_fraction : job.state === "completed" ? 1 : 0;
    card.querySelector(".job-bar-fill").style.width = `${Math.round(fraction * 100)}%`;

    const statsEl = card.querySelector(".job-stats");
    if (progress) {
      const parts = [`${progress.completed}/${progress.total} done`];
      if (progress.active_count > 0) parts.push(`${progress.active_count} active`);
      if (progress.total_speed > 0) parts.push(formatSpeed(progress.total_speed));
      statsEl.textContent = parts.join(" · ");
    } else {
      statsEl.textContent = "";
    }

    const errorEl = card.querySelector(".job-error");
    if (job.error) {
      errorEl.textContent = job.error;
      errorEl.hidden = false;
    } else {
      errorEl.hidden = true;
    }

    const filesEl = card.querySelector(".job-files");
    filesEl.innerHTML = "";
    for (const r of job.results || []) {
      const li = document.createElement("li");
      if (r.success && r.has_file) {
        const a = document.createElement("a");
        a.href = `/api/jobs/${job.id}/files/${r.index}`;
        a.textContent = r.title;
        a.setAttribute("download", "");
        li.appendChild(a);
      } else if (!r.success) {
        li.className = "failed";
        li.textContent = `${r.title}: ${r.error || "failed"}`;
      }
      if (li.textContent || li.childNodes.length) filesEl.appendChild(li);
    }

    const cancelBtn = card.querySelector(".job-cancel");
    cancelBtn.hidden = job.state !== "queued" && job.state !== "running";
  }

  // ---- Live updates: one shared SSE connection for the whole page ----

  function connectEvents() {
    const source = new EventSource("/api/events");
    source.onmessage = (event) => {
      try {
        const job = JSON.parse(event.data);
        if (job && job.id) renderJob(job);
      } catch (_) {
        /* ignore malformed events */
      }
    };
    source.onerror = () => {
      // EventSource auto-reconnects; nothing to do here.
    };
  }

  // ---- Resume in-flight/completed jobs on load ----

  async function loadExistingJobs() {
    try {
      const jobs = await jsonFetch("/api/jobs");
      for (const job of jobs) renderJob(job);
    } catch (_) {
      /* best-effort */
    }
  }

  connectEvents();
  loadExistingJobs();
})();
