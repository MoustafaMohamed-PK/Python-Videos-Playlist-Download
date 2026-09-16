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
  const subtitleOptionsEl = document.getElementById("subtitle-options");
  const subtitleLangsInput = document.getElementById("subtitle-langs-input");
  const subtitlesOnlyCheckbox = document.getElementById("subtitles-only-checkbox");
  const destinationInput = document.getElementById("destination-input");
  const existingSelect = document.getElementById("existing-select");
  const concurrencyInput = document.getElementById("concurrency-input");
  const startBtn = document.getElementById("start-btn");
  const jobError = document.getElementById("job-error");

  const jobsList = document.getElementById("jobs-list");
  const jobsEmpty = document.getElementById("jobs-empty");
  const jobCardTemplate = document.getElementById("job-card-template");

  const browseBtn = document.getElementById("browse-btn");
  const browsePanel = document.getElementById("browse-panel");
  const browseClose = document.getElementById("browse-close");
  const browseBreadcrumb = document.getElementById("browse-breadcrumb");
  const browseList = document.getElementById("browse-list");
  const browseError = document.getElementById("browse-error");
  const browseSelectBtn = document.getElementById("browse-select-btn");
  const newFolderForm = document.getElementById("new-folder-form");
  const newFolderName = document.getElementById("new-folder-name");

  let currentUrl = null;
  let browseCurrentPath = null;
  let subtitleCheckboxes = [];
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
    return `${formatBytes(bytesPerSec)}/s`;
  }

  function formatBytes(bytes) {
    if (!bytes && bytes !== 0) return "";
    const units = ["B", "KB", "MB", "GB"];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    return `${value.toFixed(1)} ${units[unit]}`;
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

    renderSubtitleOptions(data.subtitles || []);
    subtitlesOnlyCheckbox.checked = false;
    qualitySelect.disabled = false;
  }

  // ---- Subtitles ----

  function renderSubtitleOptions(subs) {
    subtitleOptionsEl.innerHTML = "";
    subtitleCheckboxes = [];

    if (subs.length === 0) {
      // No subtitle list known upfront (e.g. a playlist) -- fall back
      // to letting the user type language codes directly.
      subtitleLangsInput.hidden = false;
      return;
    }

    subtitleLangsInput.hidden = true;
    for (const sub of subs) {
      const label = document.createElement("label");
      label.className = "checkbox-row";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = sub.lang;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(sub.label));
      subtitleOptionsEl.appendChild(label);
      subtitleCheckboxes.push(cb);
    }
  }

  function selectedSubtitleLangs() {
    if (subtitleCheckboxes.length > 0) {
      return subtitleCheckboxes.filter((cb) => cb.checked).map((cb) => cb.value);
    }
    return subtitleLangsInput.value
      .split(",")
      .map((code) => code.trim())
      .filter(Boolean);
  }

  // Subtitles-only downloads don't use a video/audio quality -- gray
  // out the selector so it's clear it won't apply.
  subtitlesOnlyCheckbox.addEventListener("change", () => {
    qualitySelect.disabled = subtitlesOnlyCheckbox.checked;
  });

  // ---- Start job ----

  jobForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideError(jobError);
    if (!currentUrl) return;

    const subtitleLangs = selectedSubtitleLangs();
    const subtitlesOnly = subtitlesOnlyCheckbox.checked;
    if (subtitlesOnly && subtitleLangs.length === 0) {
      showError(jobError, "Choose at least one subtitle language, or uncheck “Subtitles only”.");
      return;
    }

    startBtn.disabled = true;
    try {
      const data = await jsonFetch("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          url: currentUrl,
          quality: qualitySelect.value,
          filename_mode: namingSelect.value,
          destination_path: destinationInput.value.trim(),
          existing_file_behavior: existingSelect.value,
          concurrency: Number(concurrencyInput.value) || 1,
          subtitle_langs: subtitleLangs,
          subtitles_only: subtitlesOnly,
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
    card.querySelector(".job-conflict-skip").addEventListener("click", () => {
      jsonFetch(`/api/jobs/${jobId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ action: "skip" }),
      }).catch(() => {});
    });
    card.querySelector(".job-conflict-overwrite").addEventListener("click", () => {
      jsonFetch(`/api/jobs/${jobId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ action: "overwrite" }),
      }).catch(() => {});
    });

    jobsEmpty.hidden = true;
    jobsList.prepend(card);
    jobCards.set(jobId, card);
    return card;
  }

  function renderJob(job) {
    const card = ensureJobCard(job.id);

    card.querySelector(".job-title").textContent = job.title;

    const thumbEl = card.querySelector(".job-thumb");
    if (job.thumbnail) {
      if (thumbEl.src !== job.thumbnail) thumbEl.src = job.thumbnail;
      thumbEl.hidden = false;
    } else {
      thumbEl.hidden = true;
    }

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
      if (progress.total_bytes) {
        parts.push(`${formatBytes(progress.downloaded_bytes)}/${formatBytes(progress.total_bytes)}`);
      }
      if (progress.eta !== null && progress.eta !== undefined && job.state === "running") {
        parts.push(`ETA ${formatDuration(progress.eta)}`);
      }
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

    const conflictEl = card.querySelector(".job-conflict");
    if (job.pending_conflict) {
      conflictEl.querySelector(".job-conflict-text").textContent =
        `Already exists: ${job.pending_conflict.path} — skip it, or overwrite?`;
      conflictEl.hidden = false;
    } else {
      conflictEl.hidden = true;
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
        if (r.warning) {
          const warn = document.createElement("span");
          warn.className = "file-warning";
          warn.textContent = ` — ${r.warning}`;
          li.appendChild(warn);
        }
      } else if (!r.success) {
        li.className = "failed";
        li.textContent = `${r.title}: ${r.error || "failed"}`;
      }
      if (li.textContent || li.childNodes.length) filesEl.appendChild(li);
    }

    const cancelBtn = card.querySelector(".job-cancel");
    cancelBtn.hidden = job.state !== "queued" && job.state !== "running";
  }

  // ---- Folder browser ----

  function renderBreadcrumb(path) {
    browseBreadcrumb.innerHTML = "";
    const segments = path.split("/").filter(Boolean);
    let acc = "";

    const rootBtn = document.createElement("button");
    rootBtn.type = "button";
    rootBtn.textContent = "/";
    rootBtn.addEventListener("click", () => loadBrowsePath("/"));
    browseBreadcrumb.appendChild(rootBtn);

    for (const seg of segments) {
      acc += `/${seg}`;
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = "›";
      browseBreadcrumb.appendChild(sep);

      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = seg;
      const target = acc;
      btn.addEventListener("click", () => loadBrowsePath(target));
      browseBreadcrumb.appendChild(btn);
    }
  }

  async function loadBrowsePath(path) {
    hideError(browseError);
    try {
      const data = await jsonFetch(`/api/browse?path=${encodeURIComponent(path)}`, {
        method: "GET",
      });
      browseCurrentPath = data.path;
      renderBreadcrumb(data.path);

      browseList.innerHTML = "";
      if (data.directories.length === 0) {
        const li = document.createElement("li");
        li.className = "empty-row";
        li.textContent = "No subfolders here.";
        browseList.appendChild(li);
      } else {
        for (const name of data.directories) {
          const li = document.createElement("li");
          li.textContent = `📁 ${name}`;
          li.addEventListener("click", () => {
            const sep = data.path.endsWith("/") ? "" : "/";
            loadBrowsePath(`${data.path}${sep}${name}`);
          });
          browseList.appendChild(li);
        }
      }
    } catch (err) {
      showError(browseError, err.message);
    }
  }

  browseBtn.addEventListener("click", () => {
    browsePanel.showModal();
    loadBrowsePath(destinationInput.value.trim() || "");
  });

  browseClose.addEventListener("click", () => browsePanel.close());

  // Clicking the backdrop (a click landing on the <dialog> element
  // itself, not one of its children) closes it, matching normal modal
  // behavior -- <dialog> doesn't do this on its own.
  browsePanel.addEventListener("click", (event) => {
    if (event.target === browsePanel) browsePanel.close();
  });

  browseSelectBtn.addEventListener("click", () => {
    if (browseCurrentPath) destinationInput.value = browseCurrentPath;
    browsePanel.close();
  });

  newFolderForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = newFolderName.value.trim();
    if (!name || !browseCurrentPath) return;
    hideError(browseError);
    try {
      await jsonFetch("/api/browse/mkdir", {
        method: "POST",
        body: JSON.stringify({ path: browseCurrentPath, name }),
      });
      newFolderName.value = "";
      loadBrowsePath(browseCurrentPath);
    } catch (err) {
      showError(browseError, err.message);
    }
  });

  // ---- Prefill destination with the configured download root ----

  async function loadSettings() {
    try {
      const settings = await jsonFetch("/api/settings", { method: "GET" });
      if (settings.download_root) destinationInput.value = settings.download_root;
      if (settings.concurrency) concurrencyInput.value = settings.concurrency;
    } catch (_) {
      /* best-effort */
    }
  }

  // ---- Live updates: one shared SSE connection for the whole page ----

  let eventSource = null;

  function connectEvents() {
    const source = new EventSource("/api/events");
    eventSource = source;
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

  // ---- Stopping the whole app ----

  const stopAppBtn = document.getElementById("stop-app-btn");
  const stoppedCard = document.getElementById("stopped-card");

  stopAppBtn.addEventListener("click", async () => {
    let message = "Stop Media Downloader? The page will stop working until you start the app again.";
    try {
      const status = await jsonFetch("/api/status");
      if (status.active_jobs > 0) {
        message =
          `${status.active_jobs} download(s) are still in progress and will be cancelled ` +
          "(they resume where they left off next time).\n\n" + message;
      }
    } catch (_) {
      /* best-effort -- fall back to the generic message */
    }
    if (!window.confirm(message)) return;

    stopAppBtn.disabled = true;
    stopAppBtn.textContent = "Stopping…";
    try {
      await jsonFetch("/api/shutdown", { method: "POST", body: "{}" });
    } catch (err) {
      stopAppBtn.disabled = false;
      stopAppBtn.textContent = "Stop app";
      window.alert(`Could not stop the app: ${err.message}`);
      return;
    }
    // Stop the auto-reconnecting event stream so it doesn't spin forever.
    if (eventSource) eventSource.close();
    document.querySelector("main").hidden = true;
    stopAppBtn.hidden = true;
    stoppedCard.hidden = false;
  });

  connectEvents();
  loadExistingJobs();
  loadSettings();
})();
