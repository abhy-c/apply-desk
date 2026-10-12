let state = null;
let selectedRole = null;
let selectedPacket = null;
let selectedResumePlan = null;
let activePacketTab = "application";
let selectedConnection = null;
let selectedCompany = null;
let selectedLegaltechRole = null;
let resumeLibrary = null;
let resumeInventory = null;
const selectedDrafts = new Set();
const selectedBullets = new Map();

const views = {
  focus: document.querySelector("#focusView"),
  roles: document.querySelector("#rolesView"),
  legaltech: document.querySelector("#legaltechView"),
  companies: document.querySelector("#companiesView"),
  sources: document.querySelector("#sourcesView"),
  library: document.querySelector("#libraryView"),
  profile: document.querySelector("#profileView"),
  network: document.querySelector("#networkView"),
  outreach: document.querySelector("#outreachView"),
  add: document.querySelector("#addView"),
};

const titleByView = {
  focus: "Today's job search",
  roles: "Ranked applications",
  legaltech: "Legal-tech opportunities",
  companies: "Target companies",
  sources: "Job source management",
  library: "Your approved resume bullets",
  profile: "Candidate profile",
  network: "Network intelligence",
  outreach: "Outreach queue",
  add: "Manual role intake",
};

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

document.querySelector("#refreshBtn").addEventListener("click", () => loadState(true));
document.querySelector("#saveProfileBtn").addEventListener("click", saveProfile);
document.querySelector("#refreshJobApplyProfileBtn").addEventListener("click", loadJobApplyProfile);
document.querySelector("#addRoleBtn").addEventListener("click", addRole);
document.querySelector("#roleFilter").addEventListener("change", renderRoles);
document.querySelector("#legaltechSearch").addEventListener("input", renderLegaltechRoles);
document.querySelector("#legaltechLaneFilter").addEventListener("change", renderLegaltechRoles);
document.querySelector("#legaltechTierFilter").addEventListener("change", renderLegaltechRoles);
document.querySelector("#legaltechSponsorFilter").addEventListener("change", renderLegaltechRoles);
document.querySelector("#companySearch").addEventListener("input", renderCompanies);
document.querySelector("#companyTierFilter").addEventListener("change", renderCompanies);
document.querySelector("#companyVisaFilter").addEventListener("change", renderCompanies);
document.querySelector("#saveStatusBtn").addEventListener("click", saveStatus);
document.querySelector("#savePacketBtn").addEventListener("click", savePacketDraft);
document.querySelector("#exportPacketBtn").addEventListener("click", exportPacketDraft);
document.querySelector("#exportCoverLetterBtn").addEventListener("click", exportCoverLetter);
document.querySelector("#openRoleBtn").addEventListener("click", () => openSelectedRole());
document.querySelector("#fetchAtsBtn").addEventListener("click", fetchAtsSources);
document.querySelector("#discoverySourceSearch").addEventListener("input", renderDiscoverySources);
document.querySelector("#copyDiscoveryRefreshBtn").addEventListener("click", async () => {
  const request = "Use $apply-desk:apply-desk to find jobs now in my confirmed Apply Desk workspace. Use thorough research and my saved focus, sources and ranking rules. Verify missing evidence and record source results. Do not approve resume changes or submit applications.";
  try { await navigator.clipboard.writeText(request); document.querySelector("#copyDiscoveryRefreshBtn").textContent = "Copied — paste into Codex"; }
  catch { document.querySelector("#discoveryRefreshSummary").textContent = request; }
});
document.querySelector("#saveSourceBtn").addEventListener("click", saveAtsSource);
document.querySelector("#cancelSourceEditBtn").addEventListener("click", clearSourceForm);
document.querySelector("#officialUrlImportForm").addEventListener("submit", importOfficialUrls);
document.querySelector("#resumeTemplate").addEventListener("change", loadResumePlan);
document.querySelector("#rerankResumeBtn").addEventListener("click", loadResumePlan);
document.querySelector("#buildWordBtn").addEventListener("click", (event) => exportResume(event, false));
document.querySelector("#exportResumeBtn").addEventListener("click", (event) => exportResume(event, true));
document.querySelector("#networkSearch").addEventListener("input", renderNetwork);
document.querySelector("#networkFilter").addEventListener("change", renderNetwork);
document.querySelector("#refreshLinkedinBtn").addEventListener("click", refreshLinkedinExport);
document.querySelector("#connectionReviewForm").addEventListener("submit", saveConnectionReview);
document.querySelector("#actionForm").addEventListener("submit", saveAction);
document.querySelector("#refreshLibraryBtn").addEventListener("click", loadResumeLibrary);
document.querySelector("#draftSearch").addEventListener("input", renderDraftInventory);
document.querySelector("#importDraftsBtn").addEventListener("click", importSelectedDrafts);
document.querySelector("#bulletSearch").addEventListener("input", renderBulletLibrary);
document.querySelector("#bulletStatusFilter").addEventListener("change", renderBulletLibrary);
document.querySelector("#bulletGroupFilter").addEventListener("change", renderBulletLibrary);
document.querySelector("#proposalStatusFilter").addEventListener("change", renderProposalLibrary);
document.querySelector("#addBulletProposalForm").addEventListener("submit", saveAdditionProposal);
document.querySelector("#approveBulletsBtn").addEventListener("click", () => reviewSelectedBullets("approved"));
document.querySelector("#excludeBulletsBtn").addEventListener("click", () => reviewSelectedBullets("excluded"));
document.querySelectorAll("[data-library-tab]").forEach((button) => button.addEventListener("click", () => setLibraryTab(button.dataset.libraryTab)));
document.querySelectorAll("[data-packet-tab]").forEach((button) => {
  button.addEventListener("click", () => setPacketTab(button.dataset.packetTab));
});

document.querySelector('#unlockForm').addEventListener('submit',async event => {
  event.preventDefault();
  const form=event.currentTarget;
  const status=document.querySelector('#unlockStatus');
  try {
    await postJson('/api/session',{code:form.elements.code.value});
    form.reset(); status.textContent='';
    await loadState(false);
  } catch (error) { status.textContent=error.message; }
});
loadState(false);
if (views[location.hash.slice(1)]) setView(location.hash.slice(1));

function setView(name) {
  if (!views[name]) return;
  history.replaceState(null, "", `#${name}`);
  Object.entries(views).forEach(([key, element]) => element.classList.toggle("is-visible", key === name));
  document.querySelector(".metrics").hidden = name === "network" || name === "library";
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === name);
  });
  document.querySelector("#workspaceTitle").textContent = titleByView[name] || "Apply Desk";
  if (name === "library") loadResumeLibrary();
}

async function loadState(rebuild = false) {
  const response = await fetch(`/api/state?rebuild=${rebuild ? "1" : "0"}`);
  const payload=await response.json();
  if (!response.ok) {
    if (response.status===401) {
      document.querySelector('#unlockPanel').hidden=false;
      document.querySelector('#unlockStatus').textContent='Enter the private code to access this workspace.';
      return;
    }
    const box=document.querySelector('#workspaceWarnings');
    box.hidden=false; box.textContent=payload.error || 'The workspace could not be loaded.';
    return;
  }
  state = payload;
  document.querySelector('#unlockPanel').hidden=true;
  renderState();
}

function renderState() {
  if (typeof renderWorkspace === "function") renderWorkspace();
  const warnings=state.validation_warnings || [];
  const warningBox=document.querySelector('#workspaceWarnings');
  warningBox.hidden=!warnings.length;
  warningBox.textContent=warnings.length ? `Some imported rows were excluded: ${warnings.join('; ')}. Repair or re-import these rows.` : '';
  document.querySelector("#rolesCount").textContent = state.stats.roles;
  document.querySelector("#highFitCount").textContent = state.stats.high_fit;
  document.querySelector("#appliedCount").textContent = state.stats.applied;
  document.querySelector("#queueCount").textContent = state.stats.weekly_queue;
  document.querySelector("#sourceCount").textContent = state.stats.ats_enabled || 0;
  document.querySelector("#openActionCount").textContent = state.stats.open_actions || 0;
  document.querySelector("#dueActionCount").textContent = state.stats.due_actions || 0;
  document.querySelector("#updatedAt").textContent =
    `Updated ${new Date(state.updated_at).toLocaleString()} · your confirmed ranking rules`;
  renderProfile();
  renderRoleProgress();
  renderRoles();
  renderLegaltechRoles();
  renderCompanies();
  renderSources();
  renderDiscoveryStatus(state.discovery_status || {});
  renderNetwork();
  renderOutreach();
  renderFocus();
}

function renderLegaltechRoles() {
  if (!state) return;
  const rows = state.legaltech_roles || [];
  const stats = state.legaltech_stats || {};
  document.querySelector("#legaltechTotal").textContent = stats.total || 0;
  document.querySelector("#legaltechPriority").textContent = stats.priority || 0;
  document.querySelector("#legaltechFresh").textContent = stats.fresh_week || 0;
  document.querySelector("#legaltechSponsor").textContent = stats.sponsor_evidence || 0;
  document.querySelector("#legaltechPolicy").textContent = state.legaltech_sponsorship_disclaimer || "";

  const search = document.querySelector("#legaltechSearch").value.trim().toLowerCase();
  const lane = document.querySelector("#legaltechLaneFilter").value;
  const tier = document.querySelector("#legaltechTierFilter").value;
  const sponsor = document.querySelector("#legaltechSponsorFilter").value;
  const filtered = rows.filter((role) => {
    const haystack = `${role.company} ${role.role_title} ${role.location} ${role.role_lane}`.toLowerCase();
    if (search && !haystack.includes(search)) return false;
    if (lane !== "all" && role.role_lane !== lane) return false;
    if (tier !== "all" && role.fit_tier !== tier) return false;
    if (sponsor === "evidence" && !["role_confirmed", "employer_history"].includes(role.sponsorship_status)) return false;
    if (sponsor === "unverified" && role.sponsorship_status !== "unverified") return false;
    return true;
  });

  document.querySelector("#legaltechResultCount").textContent = `${filtered.length} of ${rows.length} verified roles`;
  const list = document.querySelector("#legaltechList");
  if (!filtered.length) {
    selectedLegaltechRole = null;
    list.innerHTML = `<div class="empty">No legal-tech roles match these filters.</div>`;
    renderLegaltechDetail();
    return;
  }

  if (!filtered.some((role) => role.role_id === selectedLegaltechRole?.role_id)) {
    selectedLegaltechRole = filtered[0];
  }
  list.innerHTML = "";
  filtered.forEach((role) => {
    const button = document.createElement("button");
    button.className = `legaltech-row ${role.fit_tier.toLowerCase()}`;
    button.classList.toggle("selected", selectedLegaltechRole?.role_id === role.role_id);
    button.innerHTML = `
      <div class="role-top">
        <div>
          <div class="role-title">${escapeHtml(role.role_title)}</div>
          <div class="role-company">${escapeHtml(role.company)} · ${escapeHtml(role.location)}</div>
        </div>
        <span class="score">${escapeHtml(role.fit_score)}</span>
      </div>
      <div class="badge-row">
        <span class="badge">${escapeHtml(role.fit_tier)}</span>
        <span class="badge">${escapeHtml(role.role_lane)}</span>
        <span class="badge ${role.sponsorship_status === "unverified" ? "risk-unverified" : ""}">${escapeHtml(legaltechSponsorLabel(role.sponsorship_status))}</span>
      </div>
      <div class="company-row-meta">
        <span>${escapeHtml(freshnessLabel(role))}</span>
        <span>${Number(role.lca_cases || 0).toLocaleString()} employer LCA cases</span>
      </div>
    `;
    button.addEventListener("click", () => selectLegaltechRole(role));
    list.appendChild(button);
  });

  renderLegaltechDetail();
}

function selectLegaltechRole(role) {
  selectedLegaltechRole = role;
  renderLegaltechRoles();
  if (window.matchMedia("(max-width: 980px)").matches) {
    document.querySelector(".legaltech-detail-panel").scrollIntoView({ block: "start" });
  }
}

function renderLegaltechDetail() {
  const empty = document.querySelector("#legaltechDetailEmpty");
  const detail = document.querySelector("#legaltechDetail");
  if (!selectedLegaltechRole) {
    empty.hidden = false;
    detail.hidden = true;
    return;
  }

  const role = selectedLegaltechRole;
  empty.hidden = true;
  detail.hidden = false;
  document.querySelector("#legaltechRoleTitle").textContent = role.role_title;
  document.querySelector("#legaltechRoleCompany").textContent = `${role.company} · ${role.location}`;
  document.querySelector("#legaltechRoleScore").textContent = role.fit_score;
  document.querySelector("#legaltechRoleBadges").innerHTML = `
    <span class="badge">${escapeHtml(role.fit_tier)}</span>
    <span class="badge">${escapeHtml(role.role_lane)}</span>
    <span class="badge ${role.sponsorship_status === "unverified" ? "risk-unverified" : ""}">${escapeHtml(legaltechSponsorLabel(role.sponsorship_status))}</span>
  `;
  document.querySelector("#legaltechRoleFreshness").textContent =
    `Posted ${role.posted_date} · ${freshnessLabel(role)} · ${role.date_basis} · ${role.workplace}`;
  const visa = document.querySelector("#legaltechRoleVisa");
  visa.classList.toggle("warn", role.sponsorship_status !== "role_confirmed");
  visa.textContent = role.sponsorship_evidence;
  document.querySelector("#legaltechRoleLca").textContent = Number(role.lca_cases || 0).toLocaleString();
  document.querySelector("#legaltechRoleRelevantLca").textContent = Number(role.relevant_lca_cases || 0).toLocaleString();
  document.querySelector("#legaltechRoleDescription").textContent = role.description || "No role description was returned by the ATS.";
  const link = document.querySelector("#legaltechRoleLink");
  link.href = safeUrl(role.role_url);
}

function renderCompanies() {
  const rows = state.target_companies || [];
  const stats = state.company_stats || {};
  document.querySelector("#companyTotal").textContent = stats.total || 0;
  document.querySelector("#companyTier1").textContent = stats.tier1 || 0;
  document.querySelector("#companySponsorHistory").textContent = stats.relevant_sponsor_history || 0;
  document.querySelector("#companyMonitored").textContent = stats.monitored || 0;
  document.querySelector("#sponsorshipPolicy").textContent = state.sponsorship_disclaimer || "";

  const search = document.querySelector("#companySearch").value.trim().toLowerCase();
  const tier = document.querySelector("#companyTierFilter").value;
  const visa = document.querySelector("#companyVisaFilter").value;
  const filtered = rows.filter((row) => {
    const haystack = `${row.company} ${row.company_type} ${row.fit_lanes} ${row.target_roles}`.toLowerCase();
    if (search && !haystack.includes(search)) return false;
    if (tier !== "all" && row.tier !== tier) return false;
    if (visa === "relevant" && Number(row.relevant_lca_cases || 0) === 0) return false;
    if (visa === "selective" && !["selective", "unverified"].includes(row.sponsorship_risk)) return false;
    if (visa === "monitored" && row.source_status !== "monitored") return false;
    return true;
  });

  document.querySelector("#companyResultCount").textContent =
    `${filtered.length} of ${rows.length} target companies`;
  const list = document.querySelector("#companyList");
  if (!filtered.length) {
    list.innerHTML = `<div class="empty">No companies match these filters.</div>`;
    renderCompanyDetail();
    return;
  }

  list.innerHTML = "";
  filtered.forEach((company) => {
    const button = document.createElement("button");
    button.className = `company-row ${company.tier.toLowerCase().replace(" ", "")}`;
    button.classList.toggle("selected", selectedCompany?.company === company.company);
    button.innerHTML = `
      <div class="role-top">
        <div>
          <div class="role-title">${escapeHtml(company.company)}</div>
          <div class="role-company">${escapeHtml(company.company_type)} · ${escapeHtml(company.location_strategy)}</div>
        </div>
        <span class="score">${escapeHtml(company.target_score)}</span>
      </div>
      <div class="badge-row">
        <span class="badge">${escapeHtml(company.tier)}</span>
        <span class="badge risk-${escapeHtml(company.sponsorship_risk)}">${escapeHtml(sponsorshipLabel(company.sponsorship_risk))}</span>
        <span class="badge ${company.source_status === "monitored" ? "" : "warn"}">${company.source_status === "monitored" ? "source monitored" : "not monitored"}</span>
      </div>
      <div class="company-row-meta">
        <span>${Number(company.network_connections || 0)} connections</span>
        <span>${Number(company.relevant_lca_cases || 0).toLocaleString()} relevant LCA cases</span>
      </div>
    `;
    button.addEventListener("click", () => selectCompany(company));
    list.appendChild(button);
  });

  if (selectedCompany) {
    selectedCompany = rows.find((row) => row.company === selectedCompany.company) || null;
  }
  renderCompanyDetail();
}

function selectCompany(company) {
  selectedCompany = company;
  renderCompanies();
  if (window.matchMedia("(max-width: 980px)").matches) {
    document.querySelector(".company-detail-panel").scrollIntoView({ block: "start" });
  }
}

function renderCompanyDetail() {
  const empty = document.querySelector("#companyDetailEmpty");
  const detail = document.querySelector("#companyDetail");
  if (!selectedCompany) {
    empty.hidden = false;
    detail.hidden = true;
    return;
  }

  empty.hidden = true;
  detail.hidden = false;
  const row = selectedCompany;
  document.querySelector("#companyName").textContent = row.company;
  document.querySelector("#companyHeadline").textContent = `${row.company_type} · ${row.location_strategy}`;
  document.querySelector("#companyScore").textContent = row.target_score;
  document.querySelector("#companyBadges").innerHTML = `
    <span class="badge">${escapeHtml(row.tier)}</span>
    <span class="badge risk-${escapeHtml(row.sponsorship_risk)}">${escapeHtml(row.sponsorship_posture)}</span>
    <span class="badge ${row.source_status === "monitored" ? "" : "warn"}">${row.source_status === "monitored" ? "source monitored" : "source gap"}</span>
  `;
  document.querySelector("#companyNotes").textContent = row.notes;
  document.querySelector("#companyFitLanes").innerHTML = tags(row.fit_lanes)
    .map((tag) => `<span class="badge">${escapeHtml(tag)}</span>`)
    .join("");
  document.querySelector("#companyRoles").textContent = `Target roles: ${row.target_roles}`;

  const visaStatus = document.querySelector("#companyVisaStatus");
  visaStatus.classList.toggle("warn", row.sponsorship_risk !== "verify_role");
  visaStatus.textContent = `${row.sponsorship_posture}. ${row.sponsorship_evidence}.`;
  document.querySelector("#companyLcaTotal").textContent = Number(row.lca_cases || 0).toLocaleString();
  document.querySelector("#companyLcaRelevant").textContent = Number(row.relevant_lca_cases || 0).toLocaleString();
  document.querySelector("#companyLcaLocation").textContent = Number(row.preferred_location_lca_cases || 0).toLocaleString();
  document.querySelector("#companyVisaRule").textContent = row.sponsorship_rule;
  document.querySelector("#companyLcaTitles").textContent = row.relevant_titles_sample
    ? `Recent relevant LCA titles: ${row.relevant_titles_sample}`
    : `No relevant-title LCA appeared in ${row.evidence_period || "the current evidence period"}.`;

  document.querySelector("#companyConnections").textContent = Number(row.network_connections || 0);
  document.querySelector("#companyStrategicConnections").textContent = Number(row.strategic_connections || 0);
  document.querySelector("#companyCurrentRoles").textContent = Number(row.current_roles || 0);
  document.querySelector("#companySourceStatus").textContent =
    `${row.career_source} · ${row.source_status === "monitored" ? "included in Apply Desk source refresh" : "adapter still required"}`;

  const careersLink = document.querySelector("#companyCareersLink");
  careersLink.href = safeUrl(row.careers_url);
  const evidenceLink = document.querySelector("#companyEvidenceLink");
  evidenceLink.hidden = !row.evidence_source_url;
  evidenceLink.href = safeUrl(row.evidence_source_url || "#");
}

function renderFocus() {
  const feed = state.focus?.feed || {};
  const feedNotice = document.querySelector("#focusFeed");
  const isActionableFeed = feed.state === "stale" || feed.state === "empty";
  feedNotice.hidden = !isActionableFeed;
  feedNotice.classList.toggle("warn", feed.state === "stale");
  if (isActionableFeed) {
    feedNotice.innerHTML = `${escapeHtml(feed.message || "Refresh sources before acting on the role list.")} <button class="text-button" data-focus-sources="true">Open sources</button>`;
    bindFocusActions();
  }

  const actionRows = (state.actions || []).filter((action) => action.status !== "done");
  renderFocusList(
    "#focusActions",
    actionRows,
    (action) => `
      <div class="focus-row priority-${escapeHtml(action.priority || "normal")}">
        <div>
          <strong>${escapeHtml(action.title)}</strong>
          <p>${escapeHtml([action.company, action.action_type, dueLabel(action.due_date)].filter(Boolean).join(" · "))}</p>
          ${action.next_step ? `<span>${escapeHtml(action.next_step)}</span>` : ""}
        </div>
        <button class="ghost-button compact-button" data-complete-action="${escapeHtml(action.action_id)}">Done</button>
      </div>`,
    "No personal actions yet. Add the next concrete move, not a vague reminder.",
  );

  const roles = state.focus?.roles || [];
  renderFocusList(
    "#focusRoles",
    roles,
    (role) => `
      <button class="focus-row focus-button" data-focus-role="${escapeHtml(role.role_id)}">
        <div><strong>${escapeHtml(role.role_title)}</strong><p>${escapeHtml(role.company)} · ${escapeHtml(freshnessLabel(role))} · ${escapeHtml(role.role_tier)}</p></div>
        <span class="score">${escapeHtml(role.role_score || "0")}</span>
      </button>`,
    "No eligible roles are available. Refresh sources, then review the strongest new matches.",
  );

  const outreach = state.focus?.outreach || [];
  renderFocusList(
    "#focusOutreach",
    outreach,
    (row) => `
      <div class="focus-row">
        <div><strong>${escapeHtml(row.name || "Research needed")}</strong><p>${escapeHtml([row.company, row.touch_type, row.channel_suggestion].filter(Boolean).join(" · "))}</p><span>${escapeHtml(row.why_useful || "")}</span></div>
      </div>`,
    "No outreach is queued. Review your network or add a follow-up that already has context.",
  );

  renderFocusList(
    "#actionList",
    state.actions || [],
    (action) => `
      <div class="focus-row ${action.status === "done" ? "is-done" : ""}">
        <div><strong>${escapeHtml(action.title)}</strong><p>${escapeHtml([action.company, action.action_type, action.status, dueLabel(action.due_date)].filter(Boolean).join(" · "))}</p></div>
        ${action.status === "done" ? "" : `<button class="ghost-button compact-button" data-complete-action="${escapeHtml(action.action_id)}">Done</button>`}
      </div>`,
    "Your action queue is empty.",
  );
  bindFocusActions();
}

function renderFocusList(selector, rows, renderRow, emptyMessage) {
  const element = document.querySelector(selector);
  element.innerHTML = rows.length ? rows.map(renderRow).join("") : `<div class="empty">${escapeHtml(emptyMessage)}</div>`;
}

function bindFocusActions() {
  document.querySelectorAll("[data-complete-action]").forEach((button) => {
    button.addEventListener("click", () => completeAction(button.dataset.completeAction));
  });
  document.querySelectorAll("[data-focus-role]").forEach((button) => {
    button.addEventListener("click", () => {
      const role = state.roles.find((item) => item.role_id === button.dataset.focusRole);
      if (!role) return;
      setView("roles");
      selectRole(role);
    });
  });
  document.querySelectorAll("[data-focus-sources]").forEach((button) => {
    button.addEventListener("click", () => setView("sources"));
  });
}

function dueLabel(value) {
  if (!value) return "No due date";
  const due = new Date(`${value}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (due < today) return `Overdue ${value}`;
  if (due.getTime() === today.getTime()) return "Due today";
  return `Due ${value}`;
}

function renderProfile() {
  const form = document.querySelector("#profileForm");
  Object.entries(state.profile).forEach(([key, value]) => {
    const input = form.elements[key];
    if (input) input.value = value;
  });
}

async function loadJobApplyProfile() {
  const status = document.querySelector("#jobApplyProfileStatus");
  status.textContent = "Loading Job Apply profile…";
  try {
    renderJobApplyProfile(await postJson('/api/job-apply-profile', {consent:true}));
  } catch {
    renderJobApplyProfile({ connected: false, message: "Job Apply profile is unavailable." });
  }
}

function renderJobApplyProfile(result) {
  const status = document.querySelector("#jobApplyProfileStatus");
  const details = document.querySelector("#jobApplyProfileDetails");
  details.replaceChildren();
  if (!result.connected) {
    status.textContent = result.message || "Job Apply profile is unavailable.";
    details.hidden = true;
    return;
  }

  status.textContent = "Connected to the local Job Apply profile.";
  details.hidden = false;
  const profile = result.profile || {};
  [
    ["Name", profile.full_name],
    ["Email", profile.email],
    ["Phone", profile.phone],
    ["Location", profile.location],
    ["LinkedIn", profile.linkedin_url],
    ["Default resume", profile.resume_path],
  ].forEach(([label, value]) => addLinkedProfileField(details, label, value));

  if (profile.work_history?.length) {
    const jobs = profile.work_history.map((job) => {
      const dates = [job.startDate, job.current ? "Present" : job.endDate].filter(Boolean).join("–");
      return [job.company, job.title, dates].filter(Boolean).join(" · ");
    });
    addLinkedProfileField(details, "Work history", jobs.join("; "));
  }
  if (profile.education?.length) {
    const schools = profile.education.map((item) =>
      [item.school, item.degree, item.field, item.endDate].filter(Boolean).join(" · ")
    );
    addLinkedProfileField(details, "Education", schools.join("; "));
  }
  if (profile.skills?.length) {
    addLinkedProfileField(details, "Skills", profile.skills.join(", "));
  }
}

function addLinkedProfileField(container, label, value) {
  if (!value) return;
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  description.textContent = value;
  if (label === "Default resume") description.classList.add("linked-profile-path");
  container.append(term, description);
}

function renderRoles() {
  const list = document.querySelector("#rolesList");
  const filter = document.querySelector("#roleFilter").value;
  const roles = state.roles.filter((role) => {
    const status = role.application_status || "";
    if (filter === "all") return status !== "applied" && status !== "skip";
    if (filter === "high") return role.role_tier === "High-fit apply first" && status !== "applied" && status !== "skip";
    if (filter === "review") return role.role_tier === "Review" && status !== "applied" && status !== "skip";
    if (filter === "applied") return role.application_status === "applied";
    return false;
  }).sort((first, second) => {
    const statusRank = { ready_to_apply: 0, saved: 1, "": 2 };
    const rankDifference = (statusRank[first.application_status || ""] ?? 3) - (statusRank[second.application_status || ""] ?? 3);
    if (rankDifference) return rankDifference;
    return Number(second.role_score || 0) - Number(first.role_score || 0);
  });

  if (!roles.length) {
    list.innerHTML = `<div class="empty">No roles in this view.</div>`;
    return;
  }

  list.innerHTML = "";
  roles.forEach((role) => {
    const button = document.createElement("button");
    const tierClass = role.role_tier === "High-fit apply first" ? "high" : role.role_tier === "Low priority" ? "low" : "";
    button.className = `role-row ${tierClass}`;
    button.classList.toggle("selected", selectedRole?.role_id === role.role_id);
    button.innerHTML = `
      <div class="role-top">
        <div>
          <div class="role-title">${escapeHtml(role.role_title)}</div>
          <div class="role-company">${escapeHtml(role.company)} · ${escapeHtml(role.location || "Location TBD")}</div>
        </div>
        <span class="score">${escapeHtml(role.role_score || "0")}</span>
      </div>
      <div class="badge-row">
        <span class="badge">${escapeHtml(role.role_tier || "Review")}</span>
        <span class="badge ${Number(role.role_age_days) > 7 ? "warn" : ""}">${escapeHtml(freshnessLabel(role))}</span>
        ${role.application_status ? `<span class="badge warn">${escapeHtml(role.application_status)}</span>` : ""}
        ${tags(role.domain_tags).map((tag) => `<span class="badge">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="role-meta">${escapeHtml(role.source || "manual")} · ${escapeHtml(role.posted_date || "undated")}</div>
    `;
    button.addEventListener("click", () => selectRole(role));
    list.appendChild(button);
  });
}

function renderRoleProgress() {
  const counts = { unstarted: 0, saved: 0, ready: 0, applied: 0, skipped: 0 };
  state.roles.forEach((role) => {
    const status = role.application_status || "";
    if (status === "ready_to_apply") counts.ready += 1;
    else if (status === "saved") counts.saved += 1;
    else if (status === "applied") counts.applied += 1;
    else if (status === "skip") counts.skipped += 1;
    else counts.unstarted += 1;
  });

  const active = counts.unstarted + counts.saved + counts.ready;
  document.querySelector("#roleProgressHeadline").textContent = `${active} role${active === 1 ? "" : "s"} need${active === 1 ? "s" : ""} a decision`;
  document.querySelector("#roleProgressDetail").textContent =
    `${counts.ready} ready · ${counts.applied} applied · ${counts.saved} saved`;

  const total = state.roles.length || 1;
  const segments = [
    ["unstarted", counts.unstarted],
    ["saved", counts.saved],
    ["ready", counts.ready],
    ["applied", counts.applied],
    ["skipped", counts.skipped],
  ];
  document.querySelector("#roleProgressBar").innerHTML = segments
    .filter(([, count]) => count)
    .map(([name, count]) => `<span class="progress-segment ${name}" style="width:${(count / total) * 100}%"></span>`)
    .join("");
}

async function selectRole(role) {
  selectedRole = role;
  selectedResumePlan = null;
  activePacketTab = "application";
  renderRoles();
  const templateId = (state.resume_templates || []).find((template) => template.default)?.id || "pm";
  renderResumeTemplateOptions(templateId);
  const packetResponse = await postJson("/api/application-packet", { role_id: role.role_id });
  selectedPacket = packetResponse.packet;
  renderPacket();
  if (window.matchMedia("(max-width: 980px)").matches) {
    document.querySelector(".packet-panel").scrollIntoView({ block: "start" });
  }
}

function renderPacket() {
  document.querySelector("#packetEmpty").hidden = true;
  document.querySelector("#packetBody").hidden = false;
  document.querySelector("#packetExportPath").hidden = true;
  document.querySelector("#resumeResult").hidden = true;
  document.querySelector("#coverLetterResult").hidden = true;
  document.querySelector("#packetSubhead").textContent = `${selectedPacket.role_title} · ${selectedPacket.company}`;
  document.querySelector("#packetScore").textContent = selectedPacket.fit_score || "0";
  document.querySelector("#coverLetter").value = selectedPacket.cover_letter;
  document.querySelector("#statusSelect").value = selectedRole.application_status || "saved";
  document.querySelector("#statusNotes").value = selectedRole.application_notes || "";
  document.querySelector("#packetDraftMeta").textContent = selectedPacket.saved_at
    ? `Draft saved ${new Date(selectedPacket.saved_at).toLocaleString()}`
    : "Draft is generated locally and unsaved.";

  const focus = document.querySelector("#resumeFocus");
  focus.innerHTML = selectedPacket.resume_focus.map((point) => `<li>${escapeHtml(point)}</li>`).join("");

  const answers = document.querySelector("#screeningAnswers");
  answers.innerHTML = selectedPacket.screening_answers
    .map(
      (item, index) => `
        <label class="answer">
          <strong>${escapeHtml(item.question)}</strong>
          <textarea data-answer-index="${index}" spellcheck="true">${escapeHtml(item.answer)}</textarea>
        </label>
      `,
    )
    .join("");
  renderInterviewBrief();
  renderResumePlan();
  setPacketTab(activePacketTab);
}

function setPacketTab(name) {
  activePacketTab = name;
  document.querySelector("#resumePane").hidden = name !== "resume";
  document.querySelector("#applicationPane").hidden = name !== "application";
  document.querySelector("#interviewPane").hidden = name !== "interview";
  document.querySelectorAll("[data-packet-tab]").forEach((button) => {
    const active = button.dataset.packetTab === name;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
}

function renderInterviewBrief() {
  const brief = selectedPacket.interview_brief || {};
  const container = document.querySelector("#interviewBrief");
  const meta = document.querySelector("#interviewBriefMeta");
  const fitMap = Array.isArray(brief.fit_map) ? brief.fit_map : [];
  const stories = Array.isArray(brief.star_stories) ? brief.star_stories : [];
  const questions = Array.isArray(brief.questions_for_interviewer) ? brief.questions_for_interviewer : [];
  const context = Array.isArray(brief.thread_context) ? brief.thread_context : [];

  meta.textContent = stories.length
    ? "Saved locally for interview preparation. This workspace cannot send email."
    : "No interview brief has been saved for this role.";
  if (!stories.length && !fitMap.length) {
    container.innerHTML = '<div class="empty">No interview brief yet.</div>';
    return;
  }

  container.innerHTML = `
    <section class="brief-section">
      <h4>Thread context</h4>
      <ul>${context.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
    <section class="brief-section">
      <h4>Positioning</h4>
      <p>${escapeHtml(brief.positioning || "")}</p>
    </section>
    <section class="brief-section">
      <h4>JD-to-resume evidence map</h4>
      <div class="brief-cards">
        ${fitMap
          .map(
            (item) => `
              <article class="brief-card">
                <strong>${escapeHtml(item.jd_need || "Role requirement")}</strong>
                <p>${escapeHtml(item.evidence || "")}</p>
                <p><span>Frame it:</span> ${escapeHtml(item.readout || "")}</p>
                <small>${escapeHtml((item.evidence_ids || []).join(" · "))}</small>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
    <section class="brief-section">
      <h4>60-second pitch</h4>
      <div class="brief-copy">${escapeHtml(brief.pitch_60_seconds || "")}</div>
    </section>
    <section class="brief-section">
      <h4>Six STAR stories</h4>
      <div class="brief-cards">
        ${stories
          .map(
            (story) => `
              <article class="brief-card star-card">
                <strong>${escapeHtml(story.title || "STAR story")}</strong>
                <p><span>Situation:</span> ${escapeHtml(story.situation || "")}</p>
                <p><span>Task:</span> ${escapeHtml(story.task || "")}</p>
                <p><span>Action:</span> ${escapeHtml(story.action || "")}</p>
                <p><span>Result:</span> ${escapeHtml(story.result || "")}</p>
                <small>${escapeHtml((story.evidence_ids || []).join(" · "))}</small>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
    <section class="brief-section">
      <h4>Questions for Jeremy Young</h4>
      <ol>${questions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
    </section>
    <section class="brief-section">
      <h4>Follow-up note draft</h4>
      <div class="brief-copy">${escapeHtml(brief.follow_up_note || "")}</div>
    </section>
    <section class="brief-section accuracy-note">
      <h4>Accuracy note</h4>
      <p>${escapeHtml(brief.accuracy_note || "")}</p>
    </section>
  `;
}

function renderResumeTemplateOptions(selectedId) {
  const select = document.querySelector("#resumeTemplate");
  select.innerHTML = (state.resume_templates || [])
    .map(
      (template) =>
        `<option value="${escapeHtml(template.id)}" ${template.id === selectedId ? "selected" : ""}>${escapeHtml(template.label)}</option>`,
    )
    .join("");
}

async function loadResumePlan(event) {
  if (event) event.preventDefault();
  if (!selectedRole) return;
  const button = document.querySelector("#rerankResumeBtn");
  const templateId = document.querySelector("#resumeTemplate").value || "pm";
  button.disabled = true;
  document.querySelector("#resumePlanEmpty").hidden = false;
  document.querySelector("#resumePlanEmpty").textContent = "Choosing the document and changes...";
  document.querySelector("#resumeGroups").innerHTML = "";
  try {
    const response = await postJson("/api/resume-plan", { role_id: selectedRole.role_id, template_id: templateId });
    selectedResumePlan = response.plan;
    renderResumeTemplateOptions(templateId);
    renderResumePlan();
  } catch (error) {
    document.querySelector("#resumePlanEmpty").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function renderResumePlan() {
  const empty = document.querySelector("#resumePlanEmpty");
  const groups = document.querySelector("#resumeGroups");
  if (!selectedResumePlan) { empty.hidden = false; groups.innerHTML = ""; return; }
  empty.hidden = true;
  const documentInfo = selectedResumePlan.recommended_document;
  document.querySelector("#resumeDocument").innerHTML = documentInfo
    ? `<strong>Apply with: ${escapeHtml(documentInfo.name)}</strong><p>${escapeHtml(documentInfo.reason)}</p><p><a href="/api/resume-master?format=docx" target="_blank" rel="noreferrer">Open Word document</a> · <a href="/api/resume-master?format=pdf" target="_blank" rel="noreferrer">Open matching PDF</a></p>`
    : "";
  groups.innerHTML = "";
  const changes = selectedResumePlan.recommended_changes || [];
  const pending = selectedResumePlan.pending_changes || [];
  if (!changes.length && !pending.length) {
    groups.innerHTML = '<p class="empty">Use the recommended document as it is. No specific bullet changes are recommended from your approved library.</p>';
  }
  changes.forEach(change => {
    const card = document.createElement("article");
    card.className = "library-bullet proposal-card";
    card.innerHTML = `<h4>${escapeHtml(change.group_label)} · ${escapeHtml(change.slot_id)} · approved replacement</h4>${resumeChangeComparison(change)}<p>${escapeHtml(change.reason)}</p><button class="ghost-button" type="button">Keep original instead</button>`;
    card.querySelector("button").addEventListener("click", () => {
      const slot = selectedResumePlan.groups.flatMap(group => group.slots).find(slot => slot.id === change.slot_id);
      const original = slot.recommendations.find(candidate => candidate.text === slot.original_text);
      slot.selected_text = slot.original_text; slot.selected_candidate_id = original.candidate_id;
      selectedResumePlan.recommended_changes = changes.filter(item => item.slot_id !== change.slot_id);
      renderResumePlan();
    });
    groups.appendChild(card);
  });
  pending.forEach(proposal => {
    const group = selectedResumePlan.groups.find(group => group.slots.some(slot => "pm:" + slot.id === proposal.base_bullet_id));
    const bulletNumber = group ? group.slots.findIndex(slot => "pm:" + slot.id === proposal.base_bullet_id) + 1 : "";
    const card = document.createElement("article");
    card.className = "library-bullet proposal-card";
    card.innerHTML = `<h4>${escapeHtml(group?.label || proposal.group)} · Bullet ${bulletNumber} · awaiting approval</h4>${resumeChangeComparison(proposal)}<p>${escapeHtml(proposal.reason)}</p><p class="subtle">Not included in the resume until you approve this wording.</p><div class="inline-actions"><button type="button" data-approve>Approve this exact wording</button><button type="button" class="ghost-button" data-reject>Keep original</button></div>`;
    const actions = card.querySelector(".inline-actions");
    actions.querySelector("[data-approve]").addEventListener("click", () => decideResumeChange(proposal, "approved", actions));
    actions.querySelector("[data-reject]").addEventListener("click", () => decideResumeChange(proposal, "rejected", actions));
    groups.appendChild(card);
  });
  updateResumeBudget();
}

function resumeChangeComparison(change) {
  const original = change.diff.filter(part => part.kind !== "added").map(part => part.kind === "removed" ? `<del class="proposal-removed">${escapeHtml(part.text)}</del>` : escapeHtml(part.text)).join("");
  const proposed = change.diff.filter(part => part.kind !== "removed").map(part => part.kind === "added" ? `<mark class="proposal-added">${escapeHtml(part.text)}</mark>` : escapeHtml(part.text)).join("");
  return `<div class="proposal-comparison"><div><h5>Original</h5><p>${original}</p></div><div><h5>Recommended wording</h5><p>${proposed}</p></div></div>`;
}

async function decideResumeChange(proposal, decision, actions) {
  actions.querySelectorAll("button").forEach(button => {button.disabled = true;});
  try {
    await postJson("/api/resume-library/proposal-review", {proposal_id: proposal.proposal_id, decision,
      expected_text_sha256: proposal.proposed_text_sha256, expected_evidence_sha256: proposal.evidence_sha256});
    await loadResumePlan();
  } catch (error) {
    document.querySelector("#resumeResult").hidden = false;
    document.querySelector("#resumeResult").textContent = error.message;
  } finally { actions.querySelectorAll("button").forEach(button => {button.disabled = false;}); }
}

async function exportCoverLetter() {
  if (!selectedPacket) return;
  const button = document.querySelector("#exportCoverLetterBtn");
  const notice = document.querySelector("#coverLetterResult");
  button.disabled = true; notice.hidden = false; notice.textContent = "Building the cover letter in your uploaded layout...";
  try {
    const response = await postJson("/api/cover-letter-export", {role_id: selectedPacket.role_id, cover_letter: document.querySelector("#coverLetter").value});
    notice.innerHTML = `<a href="${escapeHtml(response.cover_letter.download_url)}" target="_blank" rel="noreferrer">Open formatted cover letter PDF</a>`;
  } catch (error) { notice.textContent = error.message; }
  finally { button.disabled = false; }
}

function resumeSlotMeta(text, matchedTerms, candidate) {
  const matches = matchedTerms?.length ? ` · matches ${matchedTerms.slice(0, 5).join(", ")}` : "";
  const source = candidate?.source_files?.length ? ` · source: ${candidate.source_files.join("; ")}` : "";
  return `${String(text || "").length} characters${matches}${source} · ${candidate?.proposal_id ? "approved proposal" : "original wording"}`;
}

function updateResumeBudget() {
  if (!selectedResumePlan) return;
  const pending = (selectedResumePlan.pending_changes || []).length;
  const approved = (selectedResumePlan.recommended_changes || []).length;
  document.querySelector("#resumeBudget").textContent =
    `${pending} proposed edit${pending === 1 ? "" : "s"} awaiting approval · ${approved} approved replacement${approved === 1 ? "" : "s"} selected`;
}

async function exportResume(event, exportPdf) {
  event.preventDefault();
  if (!selectedRole || !selectedResumePlan) return;
  const wordButton = document.querySelector("#buildWordBtn");
  const pdfButton = document.querySelector("#exportResumeBtn");
  const notice = document.querySelector("#resumeResult");
  const replacements = {};
  const selectedCandidates = {};
  selectedResumePlan.groups.forEach((group) => {
    group.slots.forEach((slot) => {
      const input = document.querySelector(`[data-resume-slot="${slot.id}"]`);
      const select = document.querySelector(`[data-resume-candidate="${slot.id}"]`);
      replacements[slot.id] = input ? input.value : slot.selected_text;
      selectedCandidates[slot.id] = select ? select.value : slot.selected_candidate_id;
    });
  });

  wordButton.disabled = true;
  pdfButton.disabled = true;
  notice.hidden = false;
  notice.classList.remove("warn");
  notice.textContent = exportPdf ? "Building the Word resume and checking the PDF page count..." : "Building the Word resume...";
  try {
    const response = await postJson("/api/resume-export", {
      role_id: selectedRole.role_id,
      template_id: selectedResumePlan.template_id,
      replacements,
      selected_candidates: selectedCandidates,
      export_pdf: exportPdf,
    });
    const result = response.resume;
    notice.classList.toggle("warn", !["ready", "docx_ready"].includes(result.status));
    if (result.status === "ready") {
      notice.textContent = `One-page resume ready: ${result.pdf_path}`;
    } else if (result.status === "docx_ready") {
      notice.textContent = `Word resume ready: ${result.docx_path}`;
    } else {
      notice.textContent = `${result.warning} Word draft: ${result.docx_path}`;
    }
  } catch (error) {
    notice.classList.add("warn");
    notice.textContent = error.message;
  } finally {
    wordButton.disabled = false;
    pdfButton.disabled = false;
  }
}

function setLibraryTab(name) {
  document.querySelector("#draftsLibraryPane").hidden = name !== "drafts";
  document.querySelector("#bulletsLibraryPane").hidden = name !== "bullets";
  document.querySelector("#proposalsLibraryPane").hidden = name !== "proposals";
  document.querySelectorAll("[data-library-tab]").forEach((button) => {
    const active = button.dataset.libraryTab === name;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
}

function libraryNotice(message, warning = false) {
  const notice = document.querySelector("#libraryNotice");
  notice.hidden = false;
  notice.classList.toggle("warn", warning);
  notice.textContent = message;
}

async function loadResumeLibrary() {
  try {
    const response = await fetch("/api/resume-library");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not load the bullet library");
    resumeLibrary = payload.library;
    resumeInventory = payload.inventory;
    const available = new Set(resumeInventory.files.map((file) => file.file_id));
    [...selectedDrafts].forEach((id) => { if (!available.has(id)) selectedDrafts.delete(id); });
    const stats = resumeLibrary.stats;
    document.querySelector("#libraryStats").textContent = `${resumeInventory.files.length} draft files available · ${stats.sources} imported · ${stats.approved} approved bullets · ${stats.pending} need review · ${stats.pending_proposals || 0} language proposals`;
    document.querySelector("#proposalCount").textContent = stats.pending_proposals || 0;
    const additionGroup = document.querySelector("#proposalAdditionGroup");
    const additionValue = additionGroup.value;
    additionGroup.innerHTML = '<option value="">Choose employer / role</option>' + Object.entries(resumeLibrary.groups).map(([id, label]) => `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`).join("");
    additionGroup.value = additionValue;
    const groupFilter = document.querySelector("#bulletGroupFilter");
    const currentGroup = groupFilter.value;
    groupFilter.innerHTML = '<option value="all">All</option><option value="">Needs employer assignment</option>' + Object.entries(resumeLibrary.groups).map(([id, label]) => `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`).join("");
    groupFilter.value = currentGroup;
    renderDraftInventory();
    renderBulletLibrary();
    renderProposalLibrary();
  } catch (error) { libraryNotice(error.message, true); }
}

function renderDraftInventory() {
  if (!resumeInventory) return;
  const search = document.querySelector("#draftSearch").value.trim().toLowerCase();
  const list = document.querySelector("#draftInventory");
  list.innerHTML = "";
  const visible = resumeInventory.files.filter((file) => file.relative_path.toLowerCase().includes(search));
  if (!visible.length) list.innerHTML = '<p class="empty">No matching draft files.</p>';
  let folder = null;
  visible.forEach((file) => {
    if (file.folder !== folder) {
      const heading = document.createElement("h4");
      heading.textContent = file.folder === "." ? "Main folder" : file.folder;
      list.appendChild(heading);
      folder = file.folder;
    }
    const row = document.createElement("label");
    row.className = "draft-file-row";
    row.innerHTML = `<input type="checkbox" aria-label="Import ${escapeHtml(file.relative_path)}" ${selectedDrafts.has(file.file_id) ? "checked" : ""} /><span><strong>${escapeHtml(file.name)}</strong><small>${escapeHtml(file.format)} · ${Math.ceil(file.bytes / 1024)} KB${file.imported ? " · previously imported" : ""}</small></span>`;
    row.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) selectedDrafts.add(file.file_id); else selectedDrafts.delete(file.file_id);
      updateLibrarySelections();
    });
    list.appendChild(row);
  });
  updateLibrarySelections();
}

function updateLibrarySelections() {
  const importButton = document.querySelector("#importDraftsBtn");
  importButton.disabled = !selectedDrafts.size;
  importButton.textContent = `Import selected drafts (${selectedDrafts.size})`;
  document.querySelector("#approveBulletsBtn").disabled = !selectedBullets.size;
  document.querySelector("#excludeBulletsBtn").disabled = !selectedBullets.size;
  document.querySelector("#bulletSelectionCount").textContent = `${selectedBullets.size} selected`;
}

async function importSelectedDrafts() {
  if (!selectedDrafts.size) return;
  const button = document.querySelector("#importDraftsBtn");
  button.disabled = true;
  libraryNotice("Parsing only your selected drafts. Extracted bullets will need your approval.");
  try {
    const result = await postJson("/api/resume-library/import", {file_ids: [...selectedDrafts]});
    selectedDrafts.clear();
    await loadResumeLibrary();
    const warnings = result.library.sources.filter((source) => source.warning).map((source) => `${source.relative_path}: ${source.warning}`);
    libraryNotice(`Imported ${result.selected_files} selected files; ${result.new_bullets} new bullets need review.${warnings.length ? " " + warnings.join(" ") : ""}`, !!warnings.length);
    setLibraryTab("bullets");
  } catch (error) { libraryNotice(error.message, true); }
  finally { updateLibrarySelections(); }
}

function renderBulletLibrary() {
  if (!resumeLibrary) return;
  const search = document.querySelector("#bulletSearch").value.trim().toLowerCase();
  const status = document.querySelector("#bulletStatusFilter").value;
  const group = document.querySelector("#bulletGroupFilter").value;
  const sources = new Map(resumeLibrary.sources.map((source) => [source.source_id, source]));
  const list = document.querySelector("#bulletLibraryList");
  list.innerHTML = "";
  const visible = resumeLibrary.bullets.filter((bullet) => {
    const sourceNames = bullet.provenance.map((p) => provenanceLabel(p, sources)).join(" ");
    return (status === "all" || bullet.status === status) && (group === "all" || bullet.group === group) && `${bullet.text} ${sourceNames}`.toLowerCase().includes(search);
  });
  if (!visible.length) list.innerHTML = '<p class="empty">No bullets in this view. Choose drafts to import, or change the filters.</p>';
  visible.forEach((bullet) => {
    const row = document.createElement("article");
    row.className = "library-bullet";
    const selection = selectedBullets.get(bullet.bullet_id);
    const groupValue = selection?.group ?? bullet.group;
    row.innerHTML = `<div class="library-bullet-heading"><label><input type="checkbox" aria-label="Select bullet for review" ${selection ? "checked" : ""} /> ${escapeHtml(bullet.status)}${bullet.origin === "approved_proposal" ? " · approved proposal" : ""}</label><label>Employer / role<select aria-label="Employer and role for this bullet" ${bullet.origin === "approved_proposal" ? "disabled" : ""}><option value="">Confirm employer / role</option>${Object.entries(resumeLibrary.groups).map(([id, label]) => `<option value="${escapeHtml(id)}" ${id === groupValue ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></label></div><p class="library-bullet-text">${escapeHtml(bullet.text)}</p><p class="slot-meta">${bullet.character_count} characters · ${bullet.provenance.map((p) => escapeHtml(`${provenanceLabel(p, sources)}, ${p.location}`)).join("; ")}</p>`;
    const checkbox = row.querySelector('input[type="checkbox"]');
    const select = row.querySelector("select");
    select.value = groupValue;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selectedBullets.set(bullet.bullet_id, {group: select.value}); else selectedBullets.delete(bullet.bullet_id);
      updateLibrarySelections();
    });
    select.addEventListener("change", () => {
      selectedBullets.set(bullet.bullet_id, {group: select.value});
      checkbox.checked = true;
      updateLibrarySelections();
    });
    if (bullet.group) row.appendChild(proposalEditor(bullet));
    list.appendChild(row);
  });
  updateLibrarySelections();
}

async function reviewSelectedBullets(status) {
  if (!selectedBullets.size) return;
  document.querySelector("#approveBulletsBtn").disabled = true;
  document.querySelector("#excludeBulletsBtn").disabled = true;
  try {
    const updates = [...selectedBullets].map(([bullet_id, review]) => ({bullet_id, group: review.group, status}));
    await postJson("/api/resume-library/review", {updates});
    selectedBullets.clear();
    await loadResumeLibrary();
    libraryNotice(`${updates.length} bullets ${status}. Resume selection uses approved wording only.`);
    selectedResumePlan = null;
    document.querySelector("#resumeGroups").innerHTML = "";
    document.querySelector("#resumePlanEmpty").hidden = false;
    document.querySelector("#resumePlanEmpty").textContent = "Rank bullets again to use the updated library.";
  } catch (error) { libraryNotice(error.message, true); }
  finally { updateLibrarySelections(); }
}

function provenanceLabel(proof, sources) {
  if (proof.source_type === "user_facts") return "Facts supplied by you";
  if (proof.source_type === "registered_master") return "Approved master";
  return sources.get(proof.source_id)?.relative_path || "Source resume";
}

function proposalEditor(base) {
  const details = document.createElement("details");
  details.className = "proposal-editor";
  if (!base) return details;
  details.innerHTML = `<summary>Propose a wording change</summary><form class="form-grid"><label class="wide">Proposed wording<textarea name="proposed_text" required maxlength="2000">${escapeHtml(base.text)}</textarea></label><label class="wide">Why change it?<textarea name="reason" required maxlength="4000" placeholder="Explain the role relevance or wording issue"></textarea></label><label class="wide">Additional facts you supplied (if needed)<textarea name="supporting_facts" maxlength="10000" placeholder="Support any new ownership, tools, or metrics; otherwise leave blank"></textarea></label><button type="submit">Save proposal for approval</button><p class="subtle">This saves a proposal. It does not change the selected resume bullet.</p></form>`;
  const form = details.querySelector("form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      await postJson("/api/resume-library/proposal", {...Object.fromEntries(new FormData(form)), base_bullet_id: base.candidate_id || base.bullet_id, group: base.group});
      await loadResumeLibrary();
      setView("library");
      setLibraryTab("proposals");
      libraryNotice("Proposed wording saved. Review the highlighted changes and supporting facts before approving.");
    } catch (error) { libraryNotice(error.message, true); setView("library"); }
    finally { button.disabled = false; }
  });
  return details;
}

async function saveAdditionProposal(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    await postJson("/api/resume-library/proposal", Object.fromEntries(new FormData(form)));
    form.reset();
    await loadResumeLibrary();
    libraryNotice("Addition saved for review. The entire new bullet is highlighted and remains unavailable until approval.");
  } catch (error) { libraryNotice(error.message, true); }
  finally { button.disabled = false; }
}

function renderProposalLibrary() {
  if (!resumeLibrary) return;
  const status = document.querySelector("#proposalStatusFilter").value;
  const list = document.querySelector("#proposalLibraryList");
  const sources = new Map(resumeLibrary.sources.map((source) => [source.source_id, source]));
  const visible = (resumeLibrary.proposals || []).filter((proposal) => status === "all" || proposal.status === status);
  list.innerHTML = "";
  if (!visible.length) list.innerHTML = '<p class="empty">No proposals in this view. Propose a change from a source bullet or a new addition above.</p>';
  visible.forEach((proposal) => {
    const original = proposal.diff.filter((part) => part.kind !== "added").map((part) => part.kind === "removed" ? `<del class="proposal-removed">${escapeHtml(part.text)}</del>` : escapeHtml(part.text)).join("");
    const proposed = proposal.diff.filter((part) => part.kind !== "removed").map((part) => part.kind === "added" ? `<mark class="proposal-added">${escapeHtml(part.text)}</mark>` : escapeHtml(part.text)).join("");
    const row = document.createElement("article");
    row.className = "library-bullet proposal-card";
    const facts = proposal.provenance.filter((proof) => proof.source_type === "user_facts");
    row.innerHTML = `<h4>${escapeHtml(resumeLibrary.groups[proposal.group])} · ${proposal.kind === "addition" ? "New bullet" : "Wording change"} · ${escapeHtml(proposal.status)}</h4><div class="proposal-comparison"><div><h5>Original</h5><p class="library-bullet-text">${original || "No existing bullet. This is an addition."}</p></div><div><h5>Proposed wording</h5><p class="library-bullet-text">${proposed}</p></div></div><p><strong>Reason:</strong> ${escapeHtml(proposal.reason)}</p><div class="proposal-evidence"><h5>Supporting evidence</h5>${proposal.evidence.map((evidence) => `<p>${escapeHtml(evidence.text)}</p>`).join("")}${facts.map((proof) => `<p><strong>Facts supplied by you:</strong> ${escapeHtml(proof.facts)}</p>`).join("")}<p class="slot-meta">${proposal.provenance.map((proof) => escapeHtml(`${provenanceLabel(proof, sources)}, ${proof.location}`)).join("; ")}</p></div>`;
    if (proposal.status === "pending") {
      const actions = document.createElement("div");
      actions.className = "inline-actions proposal-actions";
      actions.innerHTML = '<button type="button" data-proposal-approve>Approve this exact wording</button><button type="button" class="ghost-button" data-proposal-reject>Reject proposal</button>';
      actions.querySelector("[data-proposal-approve]").addEventListener("click", () => decideProposal(proposal, "approved", actions));
      actions.querySelector("[data-proposal-reject]").addEventListener("click", () => decideProposal(proposal, "rejected", actions));
      row.appendChild(actions);
    } else {
      const reviewed = document.createElement("p");
      reviewed.className = "subtle";
      reviewed.textContent = `${proposal.status === "approved" ? "Exact wording approved" : "Proposal rejected"} ${new Date(proposal.reviewed_at).toLocaleString()}. Original source text retained.`;
      row.appendChild(reviewed);
    }
    list.appendChild(row);
  });
}

async function decideProposal(proposal, decision, actions) {
  actions.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  try {
    await postJson("/api/resume-library/proposal-review", {proposal_id: proposal.proposal_id, decision, expected_text_sha256: proposal.proposed_text_sha256, expected_evidence_sha256: proposal.evidence_sha256});
    await loadResumeLibrary();
    selectedResumePlan = null;
    libraryNotice(decision === "approved" ? "Exact proposal wording approved and added to your library. Rank bullets again to select it." : "Proposal rejected. Your original bullet is unchanged.");
  } catch (error) { libraryNotice(error.message, true); }
  finally { actions.querySelectorAll("button").forEach((button) => { button.disabled = false; }); }
}

function renderSources() {
  renderDiscoverySources();
  const list = document.querySelector("#atsSourcesList");
  const sources = state.ats_sources || [];
  const enabled = sources.filter((source) => source.enabled === "true").length;
  document.querySelector("#sourceSyncStatus").textContent =
    `${enabled}/${sources.length} enabled · ${state.stats.fetched_roles || 0} fetched roles in the last refresh`;

  if (!sources.length) {
    list.innerHTML = `<div class="empty">No ATS sources yet.</div>`;
    return;
  }

  list.innerHTML = "";
  sources.forEach((source) => {
    const row = document.createElement("div");
    row.className = "source-row";
    row.innerHTML = `
      <div>
        <div class="role-title">${escapeHtml(source.company)}</div>
        <div class="role-company">${escapeHtml(source.ats)} · ${escapeHtml(source.slug)} · ${escapeHtml(source.location_hint || "No location hint")}</div>
      </div>
      <div class="badge-row">
        <span class="badge ${source.enabled === "true" ? "" : "warn"}">${source.enabled === "true" ? "enabled" : "paused"}</span>
        ${tags(source.domain_tags).map((tag) => `<span class="badge">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="source-actions">
        <button class="ghost-button" data-source-toggle>${source.enabled === "true" ? "Pause" : "Enable"}</button>
        <button class="ghost-button" data-source-edit>Edit</button>
        <button class="danger-button" data-source-delete>Delete</button>
      </div>
    `;
    row.querySelector("[data-source-edit]").addEventListener("click", () => editSource(source));
    row.querySelector("[data-source-toggle]").addEventListener("click", () =>
      saveSourcePayload({ ...source, original_key: source.key, enabled: source.enabled === "true" ? "false" : "true" }),
    );
    row.querySelector("[data-source-delete]").addEventListener("click", () => deleteSource(source));
    list.appendChild(row);
  });
}

function renderDiscoverySources() {
  const list = document.querySelector("#discoverySourcesList");
  const sources = state.discovery_sources || [];
  document.querySelector("#discoveryCoverageSummary").textContent = `${state.stats.ats_enabled || 0} enabled employer ATS collectors · ${sources.length} directory sources. Fetch sources checks ATS collectors. Ask Codex to refresh the connected discovery sources below.`;
  const sourceSelect = document.querySelector('#addRoleForm select[name="source"]');
  const selectedSource = sourceSelect.value;
  sourceSelect.innerHTML = '<option value="manual">Manual</option>' + sources.map((source) => `<option value="${escapeHtml(source.id)}_discovery">${escapeHtml(source.name)}</option>`).join("");
  sourceSelect.value = [...sourceSelect.options].some((option) => option.value === selectedSource) ? selectedSource : "manual";
  if (!sources.length) {
    list.innerHTML = `<div class="empty">No manual discovery sources configured.</div>`;
    return;
  }

  list.innerHTML = "";
  const query = document.querySelector("#discoverySourceSearch").value.trim().toLowerCase();
  const visible = sources.filter((source) => `${source.name} ${source.category || ""} ${source.priority || ""} ${source.description || ""}`.toLowerCase().includes(query));
  if (!visible.length) list.innerHTML = '<p class="empty">No sources match this search.</p>';
  visible.forEach((source) => {
    const row = document.createElement("div");
    row.className = "discovery-source-row";
    const searches = Array.isArray(source.searches) ? source.searches : [];
    const observation = state.discovery_status?.source_status?.[source.id];
    row.innerHTML = `
      <div class="discovery-source-copy">
        <div class="role-title">${escapeHtml(source.name)}</div>
        <p>${escapeHtml(source.description || "")}</p>
        <div class="badge-row">
          <span class="badge warn">no automatic board checks</span>
          ${observation ? `<span class="badge">Codex refresh: ${escapeHtml(observation.status)}</span>` : ""}
          ${source.category ? `<span class="badge">${escapeHtml(source.category)}</span>` : ""}
          ${source.priority ? `<span class="badge">${escapeHtml(source.priority)} priority</span>` : ""}
        </div>
        ${source.recommended_reader ? `<p class="subtle">Suggested reader: ${escapeHtml(source.recommended_reader)}</p>` : ""}
      </div>
      <div class="source-policy">${escapeHtml(source.policy || "")}</div>
      <div class="discovery-source-actions">
        ${searches.map((search) => `<a class="ghost-link" href="${escapeHtml(safeUrl(search.url))}" target="_blank" rel="noreferrer">${escapeHtml(search.label)}</a>`).join("")}
        <button class="ghost-button" type="button" data-add-discovered-role>Add official role</button>
      </div>
    `;
    row.querySelector("[data-add-discovered-role]").addEventListener("click", () => {
      const form = document.querySelector("#addRoleForm");
      form.elements.source.value = `${source.id}_discovery`;
      setView("add");
      form.elements.company.focus();
    });
    list.appendChild(row);
  });
}

let discoveryStatusTimer;
let discoveryRunSeen;
async function pollDiscoveryStatus() {
  try {
    const response = await fetch("/api/discovery-status");
    if (!response.ok) throw new Error("Discovery progress is unavailable");
    const payload = await response.json();
    if (state) state.discovery_status = payload;
    renderDiscoveryStatus(payload);
    const run = payload.latest_run;
    if (discoveryRunSeen === run?.run_id && run?.status !== "running") {
      discoveryRunSeen = null;
      await loadState(false);
    } else if (run?.status === "running") discoveryRunSeen = run.run_id;
  } catch (error) { document.querySelector("#discoveryRefreshSummary").textContent = error.message; }
  finally { discoveryStatusTimer = setTimeout(pollDiscoveryStatus, 5000); }
}

function renderDiscoveryStatus(payload) {
  const run = payload.latest_run;
  const summary = document.querySelector("#discoveryRefreshSummary");
  const list = document.querySelector("#discoveryRunSources");
  summary.textContent = run ? `${run.status === "running" ? "Refresh in progress" : "Last refresh: " + run.status} · started ${new Date(run.started_at).toLocaleString()}${run.finished_at ? " · run elapsed " + Math.round((Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000) + " seconds (includes pauses)" : ""} · ${payload.stats?.ready || 0} verified postings · ${payload.stats?.needs_review || 0} need verification` : "No discovery refresh yet. Copy the request and paste it into this Codex chat.";
  list.innerHTML = run ? Object.values(run.sources).map((source) => `<div class="discovery-run-source"><strong>${escapeHtml(source.name)}</strong><span class="badge ${source.status === "failed" ? "warn" : ""}">${escapeHtml(source.status)}</span><p>${escapeHtml(source.phase)} · ${source.fetched} details · ${source.new} new · ${source.duplicates} duplicate observations · ${source.ready} verified</p>${source.coverage ? `<p class="subtle">${escapeHtml(source.coverage)}</p>` : ""}${source.error ? `<p class="source-policy">${escapeHtml(source.error)}</p>` : ""}</div>`).join("") : "";
  document.querySelector("#discoveryReviewSummary").textContent = `${payload.stats?.needs_review || 0} postings needing verification`;
  document.querySelector("#discoveryNeedsReview").innerHTML = (payload.needs_review || []).slice(0,60).map((row) => `<div class="discovery-run-source"><strong>${escapeHtml(row.company || "Employer unverified")} · ${escapeHtml(row.role_title)}</strong><p>${row.review_reasons.map(escapeHtml).join("; ")}</p><a class="ghost-link" href="${escapeHtml(safeUrl(row.role_url))}" target="_blank" rel="noreferrer">Review posting</a></div>`).join("");
}
discoveryStatusTimer = setTimeout(pollDiscoveryStatus, 5000);

function renderNetwork() {
  const rows = state.connections_ranked || [];
  const stats = state.network_stats || {};
  document.querySelector("#networkTotal").textContent = stats.total || 0;
  document.querySelector("#networkTier1").textContent = stats.tier1 || 0;
  document.querySelector("#networkTier2").textContent = stats.tier2 || 0;
  document.querySelector("#networkHistory").textContent = stats.with_history || 0;

  const source = state.linkedin_source || {};
  const sourceStatus = document.querySelector("#linkedinSourceStatus");
  if (source.filename) {
    const imported = source.imported_at ? new Date(source.imported_at).toLocaleString() : "unknown time";
    sourceStatus.textContent = `${source.filename} · imported ${imported}`;
  } else {
    sourceStatus.textContent = "No local LinkedIn export imported";
  }

  const search = document.querySelector("#networkSearch").value.trim().toLowerCase();
  const filter = document.querySelector("#networkFilter").value;
  const filtered = rows.filter((row) => {
    const haystack = `${row.name} ${row.company} ${row.title}`.toLowerCase();
    if (search && !haystack.includes(search)) return false;
    if (filter === "priority") return !["Unranked", "Excluded"].includes(row.outreach_tier);
    if (filter === "tier1") return row.outreach_tier.startsWith("Tier 1");
    if (filter === "tier2") return row.outreach_tier.startsWith("Tier 2");
    if (filter === "watchlist") return row.outreach_tier === "Watchlist";
    if (filter === "history") {
      return Number(row.message_inbound_count || 0) + Number(row.message_outbound_count || 0) > 0;
    }
    return true;
  });

  document.querySelector("#networkResultCount").textContent =
    `Showing ${Math.min(filtered.length,200).toLocaleString()} of ${filtered.length.toLocaleString()} matches. Refine search to find more.`;
  const list = document.querySelector("#networkList");
  if (!filtered.length) {
    list.innerHTML = `<div class="empty">No connections match this filter.</div>`;
    renderConnectionDetail();
    return;
  }

  list.innerHTML = "";
  filtered.slice(0,200).forEach((connection) => {
    const button = document.createElement("button");
    const tierClass = connection.outreach_tier.startsWith("Tier 1")
      ? "tier1"
      : connection.outreach_tier.startsWith("Tier 2")
        ? "tier2"
        : connection.outreach_tier === "Watchlist"
          ? "watchlist"
          : "";
    button.className = `network-row ${tierClass}`;
    button.classList.toggle("selected", selectedConnection?.connection_id === connection.connection_id);
    button.innerHTML = `
      <div class="role-top">
        <div>
          <div class="contact-title">${escapeHtml(connection.name || "Unnamed connection")}</div>
          <div class="role-company">${escapeHtml(connection.company || "Company unknown")} · ${escapeHtml(connection.title || "Title unknown")}</div>
        </div>
        <span class="score">${escapeHtml(connection.connection_score || "0")}</span>
      </div>
      <div class="badge-row">
        <span class="badge ${connection.outreach_tier === "Watchlist" ? "warn" : ""}">${escapeHtml(connection.outreach_tier)}</span>
        ${connection.recent_hiring === "true" ? '<span class="badge">Hiring ≤90d</span>' : ""}
        <span class="badge">${escapeHtml(connection.relationship_label)}</span>
      </div>
      <div class="contact-meta">${escapeHtml(connection.priority_reasons)}</div>
    `;
    button.addEventListener("click", () => selectConnection(connection));
    list.appendChild(button);
  });

  if (selectedConnection) {
    selectedConnection = rows.find((row) => row.connection_id === selectedConnection.connection_id) || null;
  }
  renderConnectionDetail();
}

function selectConnection(connection) {
  selectedConnection = connection;
  renderNetwork();
  if (window.matchMedia("(max-width: 980px)").matches) {
    document.querySelector(".network-detail-panel").scrollIntoView({ block: "start" });
  }
}

function renderConnectionDetail() {
  const empty = document.querySelector("#networkDetailEmpty");
  const detail = document.querySelector("#networkDetail");
  if (!selectedConnection) {
    empty.hidden = false;
    detail.hidden = true;
    return;
  }
  empty.hidden = true;
  detail.hidden = false;
  const row = selectedConnection;
  document.querySelector("#connectionName").textContent = row.name || "Unnamed connection";
  document.querySelector("#connectionHeadline").textContent =
    `${row.company || "Company unknown"} · ${row.title || "Title unknown"}`;
  document.querySelector("#connectionScore").textContent = row.connection_score || "0";
  document.querySelector("#connectionBadges").innerHTML = `
    <span class="badge">${escapeHtml(row.outreach_tier)}</span>
    <span class="badge">Warmth ${escapeHtml(row.warmth_score)}</span>
    <span class="badge">Strategic ${escapeHtml(row.strategic_score)}</span>
    <span class="badge ${row.review_status === "needs_review" ? "warn" : ""}">${escapeHtml(row.review_status)}</span>
  `;
  document.querySelector("#connectionReasons").textContent = row.priority_reasons;

  const evidence = document.querySelector("#hiringEvidenceStatus");
  const hasRecentEvidence = row.recent_hiring === "true";
  evidence.classList.toggle("warn", !hasRecentEvidence);
  evidence.textContent = hasRecentEvidence
    ? `${evidenceLabel(row.hiring_evidence_type)} · ${row.hiring_evidence_date}`
    : "No verified person-specific hiring signal in the last 90 days.";

  const roleSection = document.querySelector("#matchingRoleSection");
  const roleLink = document.querySelector("#matchingRoleLink");
  roleSection.hidden = !row.matching_role_title;
  if (row.matching_role_title) {
    roleLink.textContent = `${row.matching_role_title} · posted ${row.matching_role_posted_date}`;
    roleLink.href = safeUrl(row.matching_role_url || "#");
  }

  const profileLink = document.querySelector("#openConnectionBtn");
  profileLink.hidden = !row.profile_url;
  profileLink.href = safeUrl(row.profile_url || "#");

  const form = document.querySelector("#connectionReviewForm");
  form.elements.status.value = row.review_status || "needs_review";
  form.elements.notes.value = row.review_notes || "";
  form.elements.do_not_contact.checked = row.do_not_contact === "true";
  const manualTypes = ["hiring_post", "direct_conversation", "recruiter_owned_opening", "other_person_specific"];
  const manualEvidence = manualTypes.includes(row.hiring_evidence_type);
  form.elements.hiring_evidence_type.value = manualEvidence ? row.hiring_evidence_type : "";
  form.elements.hiring_evidence_date.value = manualEvidence ? row.hiring_evidence_date : "";
  form.elements.hiring_evidence_url.value = manualEvidence ? row.hiring_evidence_url : "";
}

async function refreshLinkedinExport(event) {
  event.preventDefault();
  const button = document.querySelector("#refreshLinkedinBtn");
  const sourceStatus = document.querySelector("#linkedinSourceStatus");
  button.disabled = true;
  sourceStatus.textContent = "Refreshing the saved local export...";
  try {
    const result = await postJson("/api/linkedin-refresh", {});
    state = result.state;
    renderState();
  } catch (error) {
    sourceStatus.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function saveConnectionReview(event) {
  event.preventDefault();
  if (!selectedConnection) return;
  const form = document.querySelector("#connectionReviewForm");
  const payload = Object.fromEntries(new FormData(form));
  payload.connection_id = selectedConnection.connection_id;
  payload.do_not_contact = form.elements.do_not_contact.checked ? "true" : "false";
  const button = document.querySelector("#saveConnectionReviewBtn");
  button.disabled = true;
  try {
    const result = await postJson("/api/connection-review", payload);
    state = result.state;
    selectedConnection = state.connections_ranked.find(
      (row) => row.connection_id === selectedConnection.connection_id,
    );
    renderState();
  } finally {
    button.disabled = false;
  }
}

function renderOutreach() {
  const list = document.querySelector("#outreachList");
  const rows = state.weekly_queue.length ? state.weekly_queue : state.contacts.slice(0, 20);
  if (!rows.length) {
    list.innerHTML = `<div class="empty">No outreach rows yet.</div>`;
    return;
  }
  list.innerHTML = rows
    .map(
      (row) => `
        <div class="contact-row">
          <div>
            <div class="contact-title">${escapeHtml(row.name || "Research needed")}</div>
            <div class="role-company">${escapeHtml(row.company || "")} · ${escapeHtml(row.title || "")}</div>
          </div>
          <span class="score">${escapeHtml(row.queue_rank || row.contact_score || "0")}</span>
          <div class="contact-meta">${escapeHtml(row.why_useful || row.suggested_angle || row.contact_score_reasons || "")}</div>
        </div>
      `,
    )
    .join("");
}

async function saveAction(event) {
  event.preventDefault();
  const form = document.querySelector("#actionForm");
  if (!form.reportValidity()) return;
  const button = document.querySelector("#saveActionBtn");
  button.disabled = true;
  try {
    const result = await postJson("/api/action", Object.fromEntries(new FormData(form)));
    state = result.state;
    form.reset();
    renderState();
  } finally {
    button.disabled = false;
  }
}

async function completeAction(actionId) {
  const action = (state.actions || []).find((item) => item.action_id === actionId);
  if (!action) return;
  const result = await postJson("/api/action", { ...action, status: "done" });
  state = result.state;
  renderState();
}

async function saveProfile(event) {
  event.preventDefault();
  const form = document.querySelector("#profileForm");
  const result = await postJson("/api/profile", Object.fromEntries(new FormData(form)));
  state.profile = result.profile;
  renderProfile();
}

async function addRole(event) {
  event.preventDefault();
  const form = document.querySelector("#addRoleForm");
  if (!form.reportValidity()) return;
  const payload = Object.fromEntries(new FormData(form));
  const result = await postJson("/api/jobs", payload);
  state = result.state;
  form.reset();
  setView("roles");
  renderState();
}

async function saveStatus(event) {
  event.preventDefault();
  if (!selectedRole) return;
  const result = await postJson("/api/application-status", {
    role_id: selectedRole.role_id,
    status: document.querySelector("#statusSelect").value,
    notes: document.querySelector("#statusNotes").value,
  });
  state = result.state;
  selectedRole = state.roles.find((role) => role.role_id === selectedRole.role_id) || selectedRole;
  renderState();
  renderPacket();
}

async function savePacketDraft(event) {
  event.preventDefault();
  if (!selectedPacket) return;
  const result = await postJson("/api/application-packet/save", collectPacketEdits());
  selectedPacket = result.packet;
  renderPacket();
}

async function exportPacketDraft(event) {
  event.preventDefault();
  if (!selectedPacket) return;
  const result = await postJson("/api/application-packet/export", collectPacketEdits());
  selectedPacket = result.packet;
  renderPacket();
  const exportPath = document.querySelector("#packetExportPath");
  exportPath.textContent = `Exported to ${result.export.path}`;
  exportPath.hidden = false;
}

async function fetchAtsSources(event) {
  event.preventDefault();
  const status = document.querySelector("#sourceSyncStatus");
  const button = document.querySelector("#fetchAtsBtn");
  button.disabled = true;
  status.textContent = "Fetching enabled sources...";
  try {
    const result = await postJson("/api/fetch-ats", {});
    state = result.state;
    renderState();
    status.textContent = `Fetched ${result.fetched} product roles from enabled sources.`;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function importOfficialUrls(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const button = document.querySelector("#importOfficialUrlsBtn");
  const resultPanel = document.querySelector("#officialImportResult");
  button.disabled = true;
  resultPanel.hidden = false;
  resultPanel.classList.remove("warn");
  resultPanel.textContent = "Checking official postings...";
  try {
    const response = await postJson("/api/discovery-import", { urls: form.elements.urls.value });
    state = response.state;
    renderState();
    renderOfficialImportResult(response.import);
  } catch (error) {
    resultPanel.classList.add("warn");
    resultPanel.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function renderOfficialImportResult(result) {
  const panel = document.querySelector("#officialImportResult");
  panel.hidden = false;
  panel.classList.toggle("warn", Number(result.rejected || 0) > 0);
  panel.innerHTML = `
    <strong>${Number(result.imported || 0)} imported · ${Number(result.duplicates || 0)} duplicate · ${Number(result.rejected || 0)} rejected</strong>
    <div class="official-import-rows">
      ${(result.results || []).map((item) => `
        <div class="official-import-row ${escapeHtml(item.status)}">
          <span class="badge ${item.status === "rejected" ? "warn" : ""}">${escapeHtml(item.status)}</span>
          <div>
            <strong>${escapeHtml(item.message)}</strong>
            ${item.final_url ? `<a href="${escapeHtml(safeUrl(item.final_url))}" target="_blank" rel="noreferrer">Open official posting</a>` : `<span>${escapeHtml(item.url)}</span>`}
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

async function saveAtsSource(event) {
  event.preventDefault();
  const form = document.querySelector("#atsSourceForm");
  if (!form.reportValidity()) return;
  const payload = Object.fromEntries(new FormData(form));
  payload.enabled = form.elements.enabled.checked ? "true" : "false";
  await saveSourcePayload(payload);
  clearSourceForm();
}

async function saveSourcePayload(payload) {
  const result = await postJson("/api/ats-source", payload);
  state = result.state;
  renderState();
}

async function deleteSource(source) {
  const result = await postJson("/api/ats-source-delete", { key: source.key });
  state = result.state;
  renderState();
  clearSourceForm();
}

function editSource(source) {
  const form = document.querySelector("#atsSourceForm");
  form.elements.original_key.value = source.key;
  form.elements.enabled.checked = source.enabled === "true";
  form.elements.company.value = source.company;
  form.elements.ats.value = source.ats;
  form.elements.slug.value = source.slug;
  form.elements.location_hint.value = source.location_hint;
  form.elements.domain_tags.value = source.domain_tags;
}

function clearSourceForm() {
  const form = document.querySelector("#atsSourceForm");
  form.reset();
  form.elements.original_key.value = "";
  form.elements.enabled.checked = true;
}

function collectPacketEdits() {
  const packet = {
    ...selectedPacket,
    cover_letter: document.querySelector("#coverLetter").value,
    screening_answers: selectedPacket.screening_answers.map((item, index) => {
      const input = document.querySelector(`[data-answer-index="${index}"]`);
      return { ...item, answer: input ? input.value : item.answer };
    }),
  };
  selectedPacket = packet;
  return packet;
}

function openSelectedRole() {
  if (selectedRole?.role_url) window.open(safeUrl(selectedRole.role_url), "_blank", "noopener");
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Apply-Desk-Request": "1" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed: ${response.status}`);
  return result;
}

function tags(value) {
  return String(value || "")
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
    .slice(0, 4);
}

function freshnessLabel(role) {
  const age = Number(role.role_age_days);
  if (age <= 7) return `${age}d fresh`;
  return `${age}d old`;
}

function evidenceLabel(value) {
  const labels = {
    direct_hiring_message: "Direct hiring message",
    hiring_post: "Hiring post",
    direct_conversation: "Direct conversation",
    recruiter_owned_opening: "Recruiter-owned opening",
    other_person_specific: "Person-specific evidence",
  };
  return labels[value] || "Hiring evidence";
}

function sponsorshipLabel(value) {
  const labels = {
    verify_role: "history · verify role",
    selective: "selective · verify role",
    unverified: "unverified",
  };
  return labels[value] || "verify role";
}

function legaltechSponsorLabel(value) {
  const labels = {
    role_confirmed: "role-confirmed",
    employer_history: "employer history · verify role",
    unverified: "unverified",
  };
  return labels[value] || "verify role";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeUrl(value) {
  try {
    const url=new URL(value);
    if (url.protocol!=='https:' || url.username || url.password) return '#';
    return url.href;
  } catch { return '#'; }
}

window.addEventListener('unhandledrejection', event => {
  const box=document.querySelector('#workspaceWarnings');
  box.hidden=false; box.textContent=event.reason?.message || 'The operation could not be completed.';
  event.preventDefault();
});
