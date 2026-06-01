const state = {
  data: null,
  items: [],
  results: [],
  query: "",
  source: "all",
  role: "all",
  sort: "relevance",
  starredOnly: false,
  selectedId: "",
  showTechnical: false,
  compact: false,
  theme: getInitialTheme(),
};

const els = {
  archiveMeta: document.querySelector("#archiveMeta"),
  searchInput: document.querySelector("#searchInput"),
  clearSearch: document.querySelector("#clearSearch"),
  sourceFilter: document.querySelector("#sourceFilter"),
  roleFilter: document.querySelector("#roleFilter"),
  sortSelect: document.querySelector("#sortSelect"),
  starredOnly: document.querySelector("#starredOnly"),
  resultStatus: document.querySelector("#resultStatus"),
  results: document.querySelector("#results"),
  selectedMeta: document.querySelector("#selectedMeta"),
  selectedTitle: document.querySelector("#selectedTitle"),
  selectedSummary: document.querySelector("#selectedSummary"),
  contentPane: document.querySelector("#contentPane"),
  copyLink: document.querySelector("#copyLink"),
  technicalToggle: document.querySelector("#technicalToggle"),
  themeToggle: document.querySelector("#themeToggle"),
  themeIcon: document.querySelector("#themeIcon"),
  densityToggle: document.querySelector("#densityToggle"),
  emptyTemplate: document.querySelector("#emptyStateTemplate"),
};

init();

async function init() {
  readUrlState();
  applyTheme();
  bindEvents();

  try {
    const response = await fetchIndex();
    state.data = await response.json();
    state.items = buildItems(state.data);
    updateMeta();
    applyStateToControls();
    runSearch({ keepSelection: Boolean(state.selectedId) });
  } catch (error) {
    showLoadError(error);
  }
}

async function fetchIndex() {
  const privateResponse = await fetch("data/search-index.json", { cache: "no-store" });
  if (privateResponse.ok) {
    return privateResponse;
  }

  const demoResponse = await fetch("demo/search-index.json", { cache: "no-store" });
  if (demoResponse.ok) {
    return demoResponse;
  }

  throw new Error(`Could not load data/search-index.json (${privateResponse.status}) or demo/search-index.json (${demoResponse.status})`);
}

function bindEvents() {
  els.searchInput.addEventListener("input", () => {
    state.query = els.searchInput.value;
    runSearch();
  });

  els.clearSearch.addEventListener("click", () => {
    state.query = "";
    els.searchInput.value = "";
    els.searchInput.focus();
    runSearch();
  });

  els.sourceFilter.addEventListener("change", () => {
    state.source = els.sourceFilter.value;
    runSearch();
  });

  els.roleFilter.addEventListener("change", () => {
    state.role = els.roleFilter.value;
    runSearch();
  });

  els.sortSelect.addEventListener("change", () => {
    state.sort = els.sortSelect.value;
    runSearch({ keepSelection: true });
  });

  els.starredOnly.addEventListener("change", () => {
    state.starredOnly = els.starredOnly.checked;
    runSearch();
  });

  els.technicalToggle.addEventListener("click", () => {
    state.showTechnical = !state.showTechnical;
    renderSelected();
  });

  els.themeToggle.addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    localStorage.setItem("chatArchiveTheme", state.theme);
    applyTheme();
  });

  els.densityToggle.addEventListener("click", () => {
    state.compact = !state.compact;
    document.body.classList.toggle("compact", state.compact);
  });

  els.copyLink.addEventListener("click", async () => {
    const url = new URL(window.location.href);
    if (state.query) {
      url.searchParams.set("q", state.query);
    } else {
      url.searchParams.delete("q");
    }
    if (state.selectedId) {
      url.searchParams.set("item", state.selectedId);
    }
    await navigator.clipboard.writeText(url.toString());
    els.copyLink.classList.add("copied");
    setTimeout(() => els.copyLink.classList.remove("copied"), 700);
  });
}

function readUrlState() {
  const params = new URLSearchParams(window.location.search);
  state.query = params.get("q") || "";
  state.selectedId = params.get("item") || "";
}

function applyStateToControls() {
  els.searchInput.value = state.query;
  els.sourceFilter.value = state.source;
  els.roleFilter.value = state.role;
  els.sortSelect.value = state.sort;
  els.starredOnly.checked = state.starredOnly;
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  els.themeIcon.textContent = state.theme === "dark" ? "\u2600" : "\u25d0";
  els.themeToggle.title = state.theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
  els.themeToggle.setAttribute("aria-label", els.themeToggle.title);
}

function buildItems(data) {
  const conversations = (data.conversations || []).map((conversation) => {
    const roleTexts = {};
    const searchableMessages = (conversation.messages || []).filter(isDisplayMessage);
    for (const message of searchableMessages) {
      if (!roleTexts[message.role]) {
        roleTexts[message.role] = [];
      }
      roleTexts[message.role].push(message.text || "");
    }
    const text = searchableMessages.map((message) => message.text || "").join("\n\n");
    const title = conversation.title || "Untitled conversation";
    return {
      type: "conversation",
      id: conversation.id,
      title,
      date: conversation.updateTime || conversation.createTime || "",
      sourceLabel: "Chat",
      starred: Boolean(conversation.isStarred),
      archived: Boolean(conversation.isArchived),
      model: conversation.model || "",
      messageCount: conversation.visibleMessageCount || conversation.messageCount || 0,
      text,
      roleTexts,
      snippet: conversation.snippet || text.slice(0, 240),
      raw: conversation,
      normalizedTitle: normalizeText(title),
      normalizedText: normalizeText(text),
      normalizedRoles: Object.fromEntries(
        Object.entries(roleTexts).map(([role, parts]) => [role, normalizeText(parts.join("\n\n"))])
      ),
    };
  });

  const documents = (data.documents || []).map((document) => ({
    type: "pdf",
    id: document.id,
    title: document.title,
    date: "",
    sourceLabel: "PDF",
    starred: false,
    archived: false,
    model: "",
    messageCount: 1,
    text: document.text || "",
    roleTexts: {},
    snippet: document.text || "",
    raw: document,
    normalizedTitle: normalizeText(document.title || ""),
    normalizedText: normalizeText(document.text || ""),
    normalizedRoles: {},
  }));

  return [...conversations, ...documents];
}

function updateMeta() {
  const stats = state.data.stats || {};
  const pieces = [
    `${formatNumber(stats.conversationCount || 0)} chats`,
    `${formatNumber(stats.visibleMessageCount || stats.messageCount || 0)} messages`,
  ];
  if (stats.pdfPageCount) {
    pieces.push(`${formatNumber(stats.pdfPageCount)} PDF pages`);
  }
  els.archiveMeta.textContent = pieces.join(" - ");
}

function runSearch(options = {}) {
  if (!state.data) {
    return;
  }

  const terms = getTerms(state.query);
  const phrase = normalizeText(state.query.trim());
  const results = [];

  for (const item of state.items) {
    if (state.source !== "all" && item.type !== state.source) {
      continue;
    }
    if (state.starredOnly && !item.starred) {
      continue;
    }

    const haystack = state.role === "all"
      ? item.normalizedText
      : item.normalizedRoles[state.role] || "";

    if (state.role !== "all" && item.type !== "conversation") {
      continue;
    }

    const score = scoreItem(item, haystack, terms, phrase);
    if (score === null) {
      continue;
    }
    results.push({ item, score, snippet: makeSnippet(item, haystack, terms) });
  }

  sortResults(results);
  state.results = results.slice(0, 250);

  if (!options.keepSelection || !state.results.some((result) => result.item.id === state.selectedId)) {
    state.selectedId = state.results[0]?.item.id || "";
  }

  renderResults();
  renderSelected();
  syncUrl();
}

function scoreItem(item, haystack, terms, phrase) {
  if (!terms.length) {
    return 1;
  }
  if (!haystack && !item.normalizedTitle) {
    return null;
  }

  let score = 0;
  if (phrase && item.normalizedTitle.includes(phrase)) {
    score += 80;
  }
  if (phrase && haystack.includes(phrase)) {
    score += 35;
  }

  for (const term of terms) {
    const inTitle = item.normalizedTitle.includes(term);
    const inBody = haystack.includes(term);
    if (!inTitle && !inBody) {
      return null;
    }
    if (inTitle) {
      score += 22;
    }
    if (inBody) {
      score += Math.min(18, 4 + countOccurrences(haystack, term));
    }
  }

  if (item.starred) {
    score += 6;
  }
  return score;
}

function sortResults(results) {
  const byDateDesc = (a, b) => (Date.parse(b.item.date) || 0) - (Date.parse(a.item.date) || 0);
  const byDateAsc = (a, b) => (Date.parse(a.item.date) || 0) - (Date.parse(b.item.date) || 0);
  if (state.sort === "newest") {
    results.sort(byDateDesc);
  } else if (state.sort === "oldest") {
    results.sort(byDateAsc);
  } else if (state.sort === "title") {
    results.sort((a, b) => a.item.title.localeCompare(b.item.title));
  } else {
    results.sort((a, b) => b.score - a.score || byDateDesc(a, b));
  }
}

function renderResults() {
  els.results.replaceChildren();
  const shown = state.results.length;
  const total = state.items.length;
  els.resultStatus.textContent = state.query
    ? `${formatNumber(shown)} result${shown === 1 ? "" : "s"} for "${state.query}"`
    : `${formatNumber(Math.min(shown, total))} recent item${shown === 1 ? "" : "s"}`;

  if (!state.results.length) {
    els.results.append(els.emptyTemplate.content.cloneNode(true));
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const result of state.results) {
    const item = result.item;
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.className = "result-card";
    button.type = "button";
    button.setAttribute("aria-current", item.id === state.selectedId ? "true" : "false");
    button.addEventListener("click", () => {
      state.selectedId = item.id;
      renderResults();
      renderSelected();
      syncUrl();
    });

    button.innerHTML = `
      <div class="result-top">
        <p class="result-title">${escapeHtml(item.title)}</p>
        <span class="result-date">${escapeHtml(formatDate(item.date))}</span>
      </div>
      <p class="result-snippet">${highlight(escapeHtml(result.snippet || item.snippet || ""), getTerms(state.query))}</p>
      <div class="result-tags">
        <span class="pill">${escapeHtml(item.sourceLabel)}</span>
        ${item.starred ? '<span class="pill">Starred</span>' : ""}
        ${item.archived ? '<span class="pill">Archived</span>' : ""}
        ${item.messageCount ? `<span class="pill">${formatNumber(item.messageCount)} messages</span>` : ""}
      </div>
    `;
    li.append(button);
    fragment.append(li);
  }
  els.results.append(fragment);
}

function renderSelected() {
  const selected = state.items.find((item) => item.id === state.selectedId);
  els.technicalToggle.hidden = !selected || selected.type !== "conversation";
  els.technicalToggle.textContent = state.showTechnical ? "Hide Technical" : "Technical";

  if (!selected) {
    els.selectedMeta.textContent = "Ready";
    els.selectedTitle.textContent = "Select a conversation";
    els.selectedSummary.textContent = "Search on the left, then open a result here.";
    els.contentPane.replaceChildren();
    return;
  }

  if (selected.type === "pdf") {
    renderDocument(selected);
  } else {
    renderConversation(selected);
  }
}

function renderConversation(item) {
  const conversation = item.raw;
  els.selectedMeta.textContent = [
    formatDate(conversation.updateTime || conversation.createTime),
    conversation.model,
  ].filter(Boolean).join(" - ") || "Conversation";
  els.selectedTitle.textContent = conversation.title || "Untitled conversation";
  els.selectedSummary.textContent = [
    `${formatNumber(conversation.visibleMessageCount || conversation.messageCount || 0)} visible messages`,
    conversation.isStarred ? "starred" : "",
    conversation.isArchived ? "archived" : "",
  ].filter(Boolean).join(" - ");

  const terms = getTerms(state.query);
  const fragment = document.createDocumentFragment();
  const stats = document.createElement("div");
  stats.className = "conversation-stats";
  stats.innerHTML = `
    <span class="pill">${formatNumber(conversation.messageCount || 0)} total messages</span>
    ${Object.entries(conversation.roleCounts || {}).map(([role, count]) => `<span class="pill">${escapeHtml(role)} ${formatNumber(count)}</span>`).join("")}
  `;
  fragment.append(stats);

  const messages = (conversation.messages || []).filter((message) => {
    if (state.showTechnical) {
      return true;
    }
    return isDisplayMessage(message);
  });

  for (const message of messages) {
    const article = document.createElement("article");
    const technical = !isDisplayMessage(message);
    article.className = `message ${technical ? "technical" : escapeAttr(message.role)}`;
    const attachments = (message.attachments || []).map((name) => `<span class="pill">${escapeHtml(name)}</span>`).join("");
    article.innerHTML = `
      <div class="message-meta">
        <strong>${escapeHtml(roleLabel(message.role))}</strong>
        ${message.createTime ? `<span>${escapeHtml(formatDateTime(message.createTime))}</span>` : ""}
        <span>${escapeHtml(message.contentType || "text")}</span>
        ${message.model ? `<span>${escapeHtml(message.model)}</span>` : ""}
        ${attachments}
      </div>
      <div class="message-text">${highlight(escapeHtml(message.text || ""), terms)}</div>
    `;
    fragment.append(article);
  }

  els.contentPane.replaceChildren(fragment);
}

function renderDocument(item) {
  const rawDocument = item.raw;
  els.selectedMeta.textContent = `PDF - page ${rawDocument.page || "?"}`;
  els.selectedTitle.textContent = rawDocument.title || rawDocument.source || "PDF page";
  els.selectedSummary.textContent = rawDocument.pageCount
    ? `${rawDocument.source} - ${formatNumber(rawDocument.pageCount)} pages`
    : rawDocument.source || "";

  const terms = getTerms(state.query);
  const text = document.createElement("div");
  text.className = "document-text";
  text.innerHTML = highlight(escapeHtml(rawDocument.text || ""), terms);
  els.contentPane.replaceChildren(text);
}

function isDisplayMessage(message) {
  return (message.role === "user" || message.role === "assistant")
    && ["text", "multimodal_text", "code", "execution_output"].includes(message.contentType || "text");
}

function makeSnippet(item, haystack, terms) {
  const source = state.role === "all"
    ? item.text
    : (item.roleTexts[state.role] || []).join("\n\n");
  if (!terms.length) {
    return item.snippet || source.slice(0, 260);
  }

  const lower = source.toLowerCase();
  let index = -1;
  for (const term of terms) {
    index = lower.indexOf(term.toLowerCase());
    if (index !== -1) {
      break;
    }
  }
  if (index === -1) {
    return item.snippet || source.slice(0, 260);
  }
  const start = Math.max(0, index - 90);
  const end = Math.min(source.length, index + 210);
  return `${start > 0 ? "... " : ""}${source.slice(start, end)}${end < source.length ? " ..." : ""}`;
}

function syncUrl() {
  const url = new URL(window.location.href);
  if (state.query) {
    url.searchParams.set("q", state.query);
  } else {
    url.searchParams.delete("q");
  }
  if (state.selectedId) {
    url.searchParams.set("item", state.selectedId);
  } else {
    url.searchParams.delete("item");
  }
  window.history.replaceState(null, "", url);
}

function showLoadError(error) {
  els.archiveMeta.textContent = "Index missing";
  els.selectedMeta.textContent = "Setup needed";
  els.selectedTitle.textContent = "Build the local index first";
  els.selectedSummary.textContent = "Run .\\build-index.cmd, then refresh this page.";
  els.contentPane.innerHTML = `
    <div class="empty-state">
      <h3>Could not load the archive</h3>
      <p>${escapeHtml(error.message)}</p>
    </div>
  `;
}

function getTerms(query) {
  return normalizeText(query)
    .split(/\s+/)
    .map((term) => term.trim())
    .filter(Boolean);
}

function getInitialTheme() {
  const saved = localStorage.getItem("chatArchiveTheme");
  if (saved === "dark" || saved === "light") {
    return saved;
  }
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "dark" : "light";
}

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

function countOccurrences(text, term) {
  let count = 0;
  let index = text.indexOf(term);
  while (index !== -1 && count < 20) {
    count += 1;
    index = text.indexOf(term, index + term.length);
  }
  return count;
}

function highlight(escapedHtml, terms) {
  if (!terms.length || !escapedHtml) {
    return escapedHtml;
  }
  const uniqueTerms = [...new Set(terms)].filter((term) => term.length > 1).slice(0, 8);
  if (!uniqueTerms.length) {
    return escapedHtml;
  }
  const pattern = uniqueTerms.map(escapeRegExp).join("|");
  return escapedHtml.replace(new RegExp(`(${pattern})`, "gi"), "<mark>$1</mark>");
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return String(value || "").replace(/[^a-z0-9_-]/gi, "-");
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function roleLabel(role) {
  if (role === "user") {
    return "You";
  }
  if (role === "assistant") {
    return "ChatGPT";
  }
  return role || "Message";
}

function formatDate(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatDateTime(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value || 0);
}
