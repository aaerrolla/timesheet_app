(function () {
  "use strict";

  const state = {
    weekStart: null,      // ISO date of Monday currently shown
    days: [],             // 7 ISO dates
    dayLabels: [],        // ["Monday", ...]
    projects: [],         // [{id, name, active}]
    entriesByProjectDay: {}, // { "projectId|date": {id, hours} }
    maxDayHours: 8,
    maxWeekHours: 40,
  };

  const $ = (sel) => document.querySelector(sel);
  const headerRow = $("#headerRow");
  const gridBody = $("#gridBody");
  const totalsRow = $("#totalsRow");
  const weekLabel = $("#weekLabel");
  const banner = $("#banner");
  const weekTotalEl = $("#weekTotal");
  const weekProgress = $("#weekProgress");

  function showBanner(message, type) {
    banner.textContent = message;
    banner.className = "banner " + type;
    banner.classList.remove("hidden");
    clearTimeout(showBanner._t);
    showBanner._t = setTimeout(() => banner.classList.add("hidden"), 5000);
  }

  function fmtDate(iso) {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function key(projectId, date) {
    return projectId + "|" + date;
  }

  // ---------------------------------------------------------------------
  // Auth-aware fetch: redirects to /login or /change-password instead of
  // letting a 401/403 fall through as a generic error, since a session can
  // expire (or a forced password change can still be pending) mid-use.
  // Returns null after redirecting so callers can bail out silently.
  // ---------------------------------------------------------------------
  async function apiFetch(url, options) {
    const res = await fetch(url, options);
    if (res.status === 401) {
      window.location.href = "/login";
      return null;
    }
    if (res.status === 403) {
      let body = {};
      try {
        body = await res.clone().json();
      } catch (e) {
        /* ignore */
      }
      if (body.code === "password_change_required") {
        window.location.href = "/change-password";
        return null;
      }
    }
    return res;
  }

  // ---------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------
  async function loadProjects() {
    const res = await apiFetch("/api/projects");
    if (!res) return;
    state.projects = await res.json();
  }

  async function loadWeek(dateStr) {
    const url = dateStr ? `/api/week?date=${dateStr}` : "/api/week";
    const res = await apiFetch(url);
    if (!res) return;
    const data = await res.json();
    state.weekStart = data.week_start;
    state.days = data.days;
    state.dayLabels = data.day_labels;
    state.maxDayHours = data.max_day_hours;
    state.maxWeekHours = data.max_week_hours;

    state.entriesByProjectDay = {};
    for (const e of data.entries) {
      state.entriesByProjectDay[key(e.project_id, e.entry_date)] = {
        id: e.id,
        hours: e.hours,
      };
    }
    $("#maxDayHint").textContent = state.maxDayHours;
    $("#maxWeekHint").textContent = state.maxWeekHours;
    $("#maxWeek").textContent = state.maxWeekHours;
  }

  async function refreshAll(dateStr) {
    await Promise.all([loadProjects(), loadWeek(dateStr)]);
    render();
  }

  // ---------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------
  function render() {
    renderHeader();
    renderBody();
    renderTotals();
    const start = new Date(state.days[0] + "T00:00:00");
    const end = new Date(state.days[6] + "T00:00:00");
    weekLabel.textContent =
      start.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) +
      " – " +
      end.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function renderHeader() {
    headerRow.innerHTML = '<th class="project-col">Project</th>';
    state.days.forEach((date, i) => {
      const th = document.createElement("th");
      th.className = "day-header";
      th.innerHTML = `<span class="dow">${state.dayLabels[i]}</span><span class="date">${fmtDate(date)}</span>`;
      headerRow.appendChild(th);
    });
  }

  function renderBody() {
    gridBody.innerHTML = "";
    if (state.projects.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 8;
      td.style.textAlign = "center";
      td.style.color = "#6b7280";
      td.textContent = "No projects yet — add one above to start logging time.";
      tr.appendChild(td);
      gridBody.appendChild(tr);
      return;
    }

    for (const project of state.projects) {
      const tr = document.createElement("tr");
      tr.dataset.projectId = project.id;

      const nameTd = document.createElement("td");
      nameTd.className = "project-name";
      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.className = "project-name-input";
      nameInput.value = project.name;
      nameInput.maxLength = 80;
      nameInput.dataset.projectId = project.id;
      nameInput.addEventListener("change", onProjectNameChange);
      nameInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") nameInput.blur();
        if (e.key === "Escape") {
          nameInput.value = project.name;
          nameInput.blur();
        }
      });
      const removeBtn = document.createElement("button");
      removeBtn.className = "remove-project";
      removeBtn.title = "Remove project (keeps historical hours)";
      removeBtn.textContent = "✕";
      removeBtn.addEventListener("click", () => removeProject(project.id, project.name));
      nameTd.appendChild(nameInput);
      nameTd.appendChild(removeBtn);
      tr.appendChild(nameTd);

      for (const date of state.days) {
        const td = document.createElement("td");
        const entry = state.entriesByProjectDay[key(project.id, date)];
        const input = document.createElement("input");
        input.type = "number";
        input.className = "hour-input";
        input.min = "0";
        input.max = String(state.maxDayHours);
        input.step = "0.25";
        input.value = entry ? entry.hours : "";
        input.dataset.projectId = project.id;
        input.dataset.date = date;
        input.addEventListener("change", onHourChange);
        td.appendChild(input);
        tr.appendChild(td);
      }
      gridBody.appendChild(tr);
    }
  }

  function computeDailyTotals() {
    const totals = {};
    state.days.forEach((d) => (totals[d] = 0));
    for (const k in state.entriesByProjectDay) {
      const [, date] = k.split("|");
      totals[date] = round2(totals[date] + state.entriesByProjectDay[k].hours);
    }
    return totals;
  }

  function round2(n) {
    return Math.round(n * 100) / 100;
  }

  function renderTotals() {
    totalsRow.innerHTML = "<th>Daily total</th>";
    const totals = computeDailyTotals();
    let weekTotal = 0;
    state.days.forEach((date) => {
      const th = document.createElement("th");
      th.className = "day-total-cell";
      const total = totals[date] || 0;
      weekTotal += total;
      th.textContent = total;
      if (total > state.maxDayHours + 1e-9) th.classList.add("over");
      totalsRow.appendChild(th);
    });
    weekTotal = round2(weekTotal);
    weekTotalEl.textContent = weekTotal;
    const pct = Math.min(100, (weekTotal / state.maxWeekHours) * 100);
    weekProgress.style.width = pct + "%";
    weekProgress.classList.toggle("over", weekTotal > state.maxWeekHours + 1e-9);
  }

  // ---------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------
  async function onHourChange(evt) {
    const input = evt.target;
    const projectId = parseInt(input.dataset.projectId, 10);
    const date = input.dataset.date;
    let hours = input.value === "" ? 0 : parseFloat(input.value);

    if (isNaN(hours) || hours < 0) {
      input.classList.add("invalid");
      showBanner("Hours must be a number that is 0 or greater.", "error");
      return;
    }

    input.classList.remove("invalid");

    try {
      const res = await apiFetch("/api/entries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, entry_date: date, hours }),
      });
      if (!res) return;
      const data = await res.json();

      if (!res.ok) {
        input.classList.add("invalid");
        showBanner(data.error || "Could not save that entry.", "error");
        // revert to last known good value
        const prev = state.entriesByProjectDay[key(projectId, date)];
        input.value = prev ? prev.hours : "";
        return;
      }

      if (data.deleted) {
        delete state.entriesByProjectDay[key(projectId, date)];
      } else {
        state.entriesByProjectDay[key(projectId, date)] = { id: data.id, hours };
      }
      renderTotals();
    } catch (err) {
      showBanner("Network error while saving. Please try again.", "error");
    }
  }

  async function onProjectNameChange(evt) {
    const input = evt.target;
    const projectId = parseInt(input.dataset.projectId, 10);
    const project = state.projects.find((p) => p.id === projectId);
    const newName = input.value.trim();
    const oldName = project ? project.name : "";

    if (!newName) {
      showBanner("Project name cannot be empty.", "error");
      input.value = oldName;
      return;
    }
    if (newName === oldName) {
      input.value = newName;
      return;
    }

    try {
      const res = await apiFetch(`/api/projects/${projectId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName }),
      });
      if (!res) return;
      const data = await res.json();

      if (!res.ok) {
        showBanner(data.error || "Could not rename project.", "error");
        input.value = oldName;
        return;
      }

      // Rename applies to every saved entry automatically (they're keyed by
      // project_id), so we only need to update the project's name locally.
      if (project) project.name = data.name;
      input.value = data.name;
      showBanner(`Renamed "${oldName}" to "${data.name}".`, "success");
    } catch (err) {
      showBanner("Network error while renaming project.", "error");
      input.value = oldName;
    }
  }

  async function addProject() {
    const input = $("#newProjectName");
    const name = input.value.trim();
    if (!name) return;
    try {
      const res = await apiFetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res) return;
      const data = await res.json();
      if (!res.ok) {
        showBanner(data.error || "Could not add project.", "error");
        return;
      }
      input.value = "";
      await loadProjects();
      renderBody();
      renderTotals();
    } catch (err) {
      showBanner("Network error while adding project.", "error");
    }
  }

  async function removeProject(projectId, name) {
    if (!confirm(`Remove "${name}" from the active project list? Past hours are kept.`)) return;
    try {
      const res = await apiFetch(`/api/projects/${projectId}`, { method: "DELETE" });
      if (!res) return;
      await loadProjects();
      renderBody();
      renderTotals();
    } catch (err) {
      showBanner("Network error while removing project.", "error");
    }
  }

  function isoAddDays(iso, days) {
    // Pure UTC-based date math so this is not affected by the browser's
    // local timezone (toISOString() on a local-time Date can roll the
    // date backward by a day for timezones ahead of UTC, e.g. IST).
    const [y, m, d] = iso.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d + days));
    return dt.toISOString().slice(0, 10);
  }

  function shiftWeek(days) {
    const iso = isoAddDays(state.weekStart, days);
    refreshAll(iso);
  }

  // ---------------------------------------------------------------------
  // Auth: greeting + logout. The server already redirects unauthenticated
  // or must-change-password visitors away from this page, but we still
  // fetch /api/auth/me to get the name to display and as a safety net in
  // case the session expired between page load and now.
  // ---------------------------------------------------------------------
  async function loadCurrentUser() {
    const res = await apiFetch("/api/auth/me");
    if (!res) return null;
    return res.json();
  }

  async function doLogout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      window.location.href = "/login";
    }
  }

  // ---------------------------------------------------------------------
  // Wire up
  // ---------------------------------------------------------------------
  $("#addProjectBtn").addEventListener("click", addProject);
  $("#newProjectName").addEventListener("keydown", (e) => {
    if (e.key === "Enter") addProject();
  });
  $("#prevWeek").addEventListener("click", () => shiftWeek(-7));
  $("#nextWeek").addEventListener("click", () => shiftWeek(7));
  $("#thisWeek").addEventListener("click", () => refreshAll());
  $("#logoutBtn").addEventListener("click", doLogout);

  async function init() {
    const user = await loadCurrentUser();
    if (!user) return; // apiFetch already redirected
    const fullName = `${user.first_name || ""} ${user.last_name || ""}`.trim();
    $("#userGreeting").textContent = `Hi, ${fullName || user.email}`;
    await refreshAll();
  }

  init();
})();
