(() => {
  const $ = (id) => document.getElementById(id);
  const searchForm = $("searchForm");
  const searchInput = $("searchInput");
  const searchBtn = $("searchBtn");
  const clearBtn = $("clearBtn");
  const source1337 = $("source1337");
  const sourceTpb = $("sourceTpb");
  const limitSelect = $("limitSelect");
  const resultsGrid = $("resultsGrid");
  const resultsTitle = $("resultsTitle");
  const resultMeta = $("resultMeta");
  const welcomeCard = $("welcomeCard");
  const skeletonGrid = $("skeletonGrid");
  const emptyState = $("emptyState");
  const errorState = $("errorState");
  const errorMessage = $("errorMessage");
  const retryBtn = $("retryBtn");
  const apiStatus = $("apiStatus");
  const versionText = $("versionText");
  const fullscreenBtn = $("fullscreenBtn");
  const recentWrap = $("recentWrap");
  const recentList = $("recentList");
  const clearHistoryBtn = $("clearHistoryBtn");
  const toast = $("toast");

  let lastQuery = "";
  let activeController = null;
  let toastTimer = null;
  const HISTORY_KEY = "supreme-search-history-v1";

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function setApiStatus(state, text) {
    apiStatus.classList.remove("online", "offline");
    if (state) apiStatus.classList.add(state);
    apiStatus.querySelector("span:last-child").textContent = text;
  }

  async function checkHealth() {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 14000);
      const res = await fetch("/health", { signal: controller.signal, cache: "no-store" });
      clearTimeout(timer);
      if (!res.ok) throw new Error("health");
      const data = await res.json();
      setApiStatus("online", "API online");
      versionText.textContent = `API v${data.version || "?"}`;
    } catch (_) {
      setApiStatus("offline", "API indisponível");
    }
  }

  function getSources() {
    const sources = [];
    if (source1337.checked) sources.push("1337x");
    if (sourceTpb.checked) sources.push("piratebay");
    return sources;
  }

  function sourceLabel(source) {
    return String(source || "Fonte").replace("PirateBay", "PirateBay");
  }

  function escText(value) {
    return String(value ?? "");
  }

  function buildMagnetButton(magnet, title) {
    const a = document.createElement("a");
    a.className = "magnet-button focusable";
    a.href = magnet;
    a.setAttribute("data-tv-focus", "");
    a.setAttribute("aria-label", `Abrir magnet: ${title}`);
    a.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3v10a6 6 0 0 0 12 0V7M6 8h4M14 8h4M6 3h4M14 3h4"/></svg>
      <span>ABRIR MAGNET</span>`;
    a.addEventListener("click", () => showToast("A abrir na app de downloads…"));
    return a;
  }

  function buildCopyButton(magnet) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copy-button focusable";
    button.setAttribute("data-tv-focus", "");
    button.textContent = "COPIAR";
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(magnet);
        showToast("Magnet copiado");
      } catch (_) {
        const ta = document.createElement("textarea");
        ta.value = magnet;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
        showToast("Magnet copiado");
      }
    });
    return button;
  }

  function metric(label, value, kind = "") {
    const span = document.createElement("span");
    span.className = `metric ${kind}`;
    const safeValue = escText(value || "?");
    span.innerHTML = `<span>${label}</span><strong></strong>`;
    span.querySelector("strong").textContent = safeValue;
    return span;
  }

  function createResultCard(item, index) {
    const card = document.createElement("article");
    card.className = "result-card";

    const top = document.createElement("div");
    top.className = "card-top";
    const badge = document.createElement("span");
    badge.className = "source-badge";
    badge.textContent = sourceLabel(item.source);
    const rank = document.createElement("span");
    rank.className = "seed-rank";
    rank.textContent = `#${index + 1}`;
    top.append(badge, rank);

    const title = document.createElement("h3");
    title.className = "result-title";
    title.textContent = escText(item.title || "Sem título");

    const metrics = document.createElement("div");
    metrics.className = "metrics";
    metrics.append(
      metric("SEED", item.seeders ?? 0, "seed"),
      metric("LEECH", item.leechers ?? 0, "leech"),
      metric("TAMANHO", item.size || "?")
    );
    if (item.category) metrics.append(metric("CAT", item.category));
    if (item.date) metrics.append(metric("DATA", item.date));

    const actions = document.createElement("div");
    actions.className = "card-actions";
    actions.append(buildMagnetButton(item.magnet, item.title || "resultado"), buildCopyButton(item.magnet));

    card.append(top, title, metrics, actions);
    return card;
  }

  function setLoading(loading) {
    searchBtn.disabled = loading;
    searchBtn.querySelector("span").textContent = loading ? "A PESQUISAR…" : "PESQUISAR";
    skeletonGrid.hidden = !loading;
    if (loading) {
      skeletonGrid.innerHTML = "";
      for (let i = 0; i < 6; i++) {
        const sk = document.createElement("div");
        sk.className = "skeleton-card";
        skeletonGrid.appendChild(sk);
      }
    }
  }

  function hideStates() {
    welcomeCard.hidden = true;
    emptyState.hidden = true;
    errorState.hidden = true;
  }

  function readHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }
    catch (_) { return []; }
  }

  function writeHistory(query) {
    const next = [query, ...readHistory().filter((q) => q.toLowerCase() !== query.toLowerCase())].slice(0, 7);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
    renderHistory();
  }

  function renderHistory() {
    const history = readHistory();
    recentList.innerHTML = "";
    recentWrap.hidden = history.length === 0;
    history.forEach((query) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "recent-chip focusable";
      btn.setAttribute("data-tv-focus", "");
      btn.textContent = query;
      btn.addEventListener("click", () => {
        searchInput.value = query;
        performSearch(query);
      });
      recentList.appendChild(btn);
    });
  }

  async function performSearch(rawQuery) {
    const query = String(rawQuery ?? searchInput.value).trim().replace(/\s+/g, " ");
    if (query.length < 2) {
      showToast("Escreve pelo menos 2 caracteres");
      searchInput.focus();
      return;
    }
    const sources = getSources();
    if (!sources.length) {
      showToast("Ativa pelo menos uma fonte");
      return;
    }

    lastQuery = query;
    searchInput.value = query;
    writeHistory(query);
    const params = new URLSearchParams({ q: query, sources: sources.join(","), limit: limitSelect.value });
    history.replaceState(null, "", `/?q=${encodeURIComponent(query)}`);

    if (activeController) activeController.abort();
    activeController = new AbortController();
    const started = performance.now();
    let timer = null;

    hideStates();
    resultsGrid.innerHTML = "";
    resultsTitle.textContent = `A procurar “${query}”`;
    resultMeta.textContent = "A consultar fontes…";
    setLoading(true);

    try {
      timer = setTimeout(() => activeController.abort(), 70000);
      const res = await fetch(`/search?${params.toString()}`, { signal: activeController.signal, cache: "no-store" });
      const elapsed = ((performance.now() - started) / 1000).toFixed(1);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `Erro HTTP ${res.status}`);

      setLoading(false);
      resultsTitle.textContent = `Resultados para “${query}”`;
      resultMeta.textContent = `${data.length} resultado${data.length === 1 ? "" : "s"} • ${elapsed}s`;

      if (!data.length) {
        emptyState.hidden = false;
        return;
      }

      data.forEach((item, index) => resultsGrid.appendChild(createResultCard(item, index)));
      const first = resultsGrid.querySelector(".magnet-button");
      if (first && matchMedia("(pointer: coarse)").matches) first.focus({ preventScroll: true });
    } catch (err) {
      if (err?.name === "AbortError") {
        errorMessage.textContent = "A pesquisa demorou demasiado. No plano gratuito do Render, o serviço pode estar a acordar. Tenta novamente.";
      } else {
        errorMessage.textContent = err?.message || "Erro inesperado.";
      }
      setLoading(false);
      resultsTitle.textContent = "Pesquisa interrompida";
      resultMeta.textContent = "";
      errorState.hidden = false;
    } finally {
      clearTimeout(timer);
    }
  }

  function clearSearch() {
    if (activeController) activeController.abort();
    searchInput.value = "";
    resultsGrid.innerHTML = "";
    skeletonGrid.hidden = true;
    emptyState.hidden = true;
    errorState.hidden = true;
    welcomeCard.hidden = false;
    resultsTitle.textContent = "Pronto para pesquisar";
    resultMeta.textContent = "";
    history.replaceState(null, "", "/");
    searchInput.focus();
  }

  function spatialFocus(direction) {
    const current = document.activeElement;
    if (!current) return;
    const candidates = [...document.querySelectorAll('[data-tv-focus]:not([disabled]), a[href], button:not([disabled]), input:not([disabled]), select:not([disabled])')]
      .filter((el) => el.offsetParent !== null && el !== current);
    if (!candidates.length) return;

    const a = current.getBoundingClientRect();
    const ax = a.left + a.width / 2;
    const ay = a.top + a.height / 2;
    let best = null;
    let bestScore = Infinity;

    for (const el of candidates) {
      const b = el.getBoundingClientRect();
      const bx = b.left + b.width / 2;
      const by = b.top + b.height / 2;
      const dx = bx - ax;
      const dy = by - ay;
      const valid = direction === "left" ? dx < -8 : direction === "right" ? dx > 8 : direction === "up" ? dy < -8 : dy > 8;
      if (!valid) continue;
      const primary = direction === "left" || direction === "right" ? Math.abs(dx) : Math.abs(dy);
      const secondary = direction === "left" || direction === "right" ? Math.abs(dy) : Math.abs(dx);
      const score = primary + secondary * 2.2;
      if (score < bestScore) { bestScore = score; best = el; }
    }
    if (best) {
      best.focus({ preventScroll: true });
      best.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    }
  }

  searchForm.addEventListener("submit", (e) => { e.preventDefault(); performSearch(searchInput.value); });
  clearBtn.addEventListener("click", clearSearch);
  retryBtn.addEventListener("click", () => performSearch(lastQuery));
  clearHistoryBtn.addEventListener("click", () => { localStorage.removeItem(HISTORY_KEY); renderHistory(); searchInput.focus(); });

  [source1337, sourceTpb].forEach((box) => {
    box.closest("label").addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); box.checked = !box.checked; }
    });
  });

  fullscreenBtn.addEventListener("click", async () => {
    try {
      if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
      else await document.exitFullscreen();
    } catch (_) { showToast("Ecrã inteiro não disponível neste navegador"); }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== searchInput) {
      e.preventDefault(); searchInput.focus(); return;
    }
    if (e.key === "Escape") { clearSearch(); return; }
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key) && document.activeElement !== searchInput) {
      e.preventDefault();
      spatialFocus(e.key.replace("Arrow", "").toLowerCase());
    }
  });

  const initialQuery = new URLSearchParams(location.search).get("q");
  renderHistory();
  checkHealth();
  if (initialQuery) {
    searchInput.value = initialQuery;
    performSearch(initialQuery);
  } else {
    setTimeout(() => searchInput.focus(), 180);
  }
})();
