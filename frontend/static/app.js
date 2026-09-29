// EasiApply — shared runtime for every Stitch screen.
// Navigation is driven here and always operates on window.top so it also works
// when a design page is embedded inside an iframe wrapper.
(function () {
  "use strict";

  var lastLogId = 0;
  var pollTimer = null;
  var SCRIPT_ERR_REPORTED = false;

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function getEl(id) {
    var activeWrapper = document.querySelector("#state-default:not(.hidden), #state-loading:not(.hidden), #state-success:not(.hidden), #state-error:not(.hidden)");
    if (activeWrapper) {
      var found = activeWrapper.querySelector("#" + id + ", [id='" + id + "']");
      if (found) return found;
    }
    return document.getElementById(id);
  }

  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function escapeHTML(text) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(String(text == null ? "" : text)));
    return div.innerHTML;
  }

  function api(path, opts) {
    opts = opts || {};
    var reqBody = opts.body;
    if (reqBody !== undefined && typeof reqBody !== "string") {
      reqBody = JSON.stringify(reqBody);
    }
    return fetch(path, {
      method: opts.method || "GET",
      headers: reqBody ? { "Content-Type": "application/json" } : undefined,
      body: reqBody,
    }).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          var msg = "";
          if (data && data.detail) {
            if (typeof data.detail === "string") {
              msg = data.detail;
            } else if (Array.isArray(data.detail)) {
              msg = data.detail.map(function (d) { return d.msg || JSON.stringify(d); }).join(", ");
            } else {
              msg = JSON.stringify(data.detail);
            }
          }
          throw new Error(msg || (opts.method || "GET") + " " + path + " -> " + res.status);
        });
      }
      return res.json().catch(function () { return null; });
    });
  }

  // ---------------------------------------------------------------------------
  // Navigation — the critical fix: always navigate the true top window so the
  // browser URL changes and the server can serve the next section's screen.
  // ---------------------------------------------------------------------------
  var SECTIONS = ["dashboard", "matches", "outreach", "applications", "analytics", "settings", "profile"];

  function navigateTo(path) {
    if (!path) return;
    var hash = "";
    var hashIdx = String(path).indexOf("#");
    if (hashIdx !== -1) {
      hash = String(path).slice(hashIdx + 1);
      path = String(path).slice(0, hashIdx);
    }
    path = String(path).split("/")[0].split("?")[0];
    if (SECTIONS.indexOf(path) === -1) return;
    var top = window.top || window;
    // Same page: just scroll to the section card.
    try {
      var here = (window.location.pathname || "").toLowerCase();
      if (here.indexOf("/" + path) !== -1 && hash) {
        scrollToSection(hash);
        return;
      }
    } catch (err) {}
    top.location.href = "/" + path + (hash ? "#" + hash : "");
  }

  function scrollToSection(id) {
    if (!id) return;
    var run = function () {
      var el = document.getElementById(id);
      if (!el) {
        // fall back: first partial id match (duplicate ids across states)
        var all = document.querySelectorAll("[id]");
        for (var i = 0; i < all.length; i++) {
          if (all[i].id === id) { el = all[i]; break; }
        }
      }
      if (!el) return;
      try { el.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (err) {
        el.scrollIntoView();
      }
      el.classList.add("ring-2", "ring-primary-container");
      setTimeout(function () { el.classList.remove("ring-2", "ring-primary-container"); }, 1800);
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () { setTimeout(run, 350); });
    } else {
      setTimeout(run, 350);
    }
  }

  function currentSection() {
    var p = window.location.pathname.toLowerCase();
    if (p.indexOf("/settings") !== -1 || p.indexOf("settings") === 0) return "settings";
    if (p.indexOf("/profile") !== -1 || p.indexOf("profile") === 0) return "profile";
    if (p.indexOf("/matches") !== -1 || p.indexOf("job_matches") !== -1) return "matches";
    if (p.indexOf("/outreach") !== -1 || p.indexOf("/applications") !== -1 || p.indexOf("job_detail_composer") !== -1) return "outreach";
    if (p.indexOf("/analytics") !== -1 || p.indexOf("analytics_history") !== -1) return "analytics";
    if (p.indexOf("/dashboard") !== -1 || p.indexOf("dashboard") === 0) return "dashboard";
    var f = (p.split("/").pop() || "");
    if (f.indexOf("dashboard") === 0) return "dashboard";
    if (f.indexOf("settings") === 0) return "settings";
    if (f.indexOf("profile") === 0) return "profile";
    return "";
  }

  function bindUniversalStates() {
    if (!window.__showState) return;
    var sec = currentSection();
    if (!sec) return;
    api("/api/state").then(function (state) {
      if (!state) return;
      var hasResume = !!state.has_resume;
      var hasApps = !!(state.has_applications || state.application_count > 0);
      var target = "default";
      
      // Strict per-section state mapping
      if (sec === "dashboard" || sec === "matches" || sec === "outreach" || sec === "analytics") {
        // Only show success states on these pages IF we actually have applications/scraped data!
        target = hasApps ? "success" : "default";
      } else if (sec === "profile" || sec === "settings") {
        // Profile and Settings flip to success if resume exists
        target = hasResume ? "success" : "default";
      }
      
      window.__showState(target);
      // Dynamic system status pill (header) — show Setup Required until AI keys present
      var statusPill = document.querySelector("header .bg-primary-container");
      if (statusPill && statusPill.textContent.trim() === "Operational" && !state.has_ai_config) {
        // keep visual but app.js will handle via settings card status
      }
    }).catch(function () {});
  }

  function highlightActiveNav() {
    var section = currentSection();
    if (!section) return;
    var links = $$("[data-path]");
    links.forEach(function (link) {
      if (link.getAttribute("data-path") === section) {
        link.classList.add("bg-primary-container", "text-on-primary-fixed", "font-bold");
        var icon = link.querySelector(".material-symbols-outlined");
        if (icon) icon.style.fontVariationSettings = "'FILL' 1";
      }
    });
  }

  function bindNavigation() {
    document.addEventListener("click", function (e) {
      var el = e.target && e.target.closest ? e.target.closest("[data-path]") : null;
      if (el) {
        var path = el.getAttribute("data-path");
        if (path) {
          // Deep-link common quick actions straight to their section card.
          var label = (el.textContent || "").toLowerCase();
          if (label.indexOf("upload resume") !== -1) path += "#resume-file-input";
          else if (label.indexOf("connect gmail") !== -1) path += "#email-card";
          e.preventDefault();
          e.stopPropagation();
          navigateTo(path);
        }
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Toast feedback
  // ---------------------------------------------------------------------------
  var toastTimer = null;
  function showToast(text) {
    var toast = document.getElementById("toast");
    var msg = document.getElementById("toast-message");
    if (!toast || !msg) return;
    msg.innerText = text;
    toast.classList.remove("translate-y-24", "opacity-0");
    toast.classList.add("translate-y-0", "opacity-100", "pointer-events-none");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toast.classList.add("translate-y-24", "opacity-0");
      toast.classList.remove("translate-y-0", "opacity-100");
    }, 3200);
  }

  // ---------------------------------------------------------------------------
  // Unified confirmation modal
  // ---------------------------------------------------------------------------
  function showConfirmModal(opts) {
    opts = opts || {};
    var title = opts.title || "Confirm Action";
    var message = opts.message || "Are you sure you want to proceed?";
    var confirmText = opts.confirmText || "Confirm";
    var cancelText = opts.cancelText || "Cancel";
    var isDanger = opts.danger !== false;

    var scrim = document.createElement("div");
    scrim.className = "fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs app-modal";

    var card = document.createElement("div");
    card.className = "bg-surface-container-lowest border border-surface-container-high/80 rounded-3xl p-6 shadow-2xl max-w-md w-full flex flex-col gap-4 text-left animate-fade-in";

    var iconName = isDanger ? "warning" : "help";
    var iconColor = isDanger ? "text-error bg-error-container/20" : "text-primary bg-primary-container/20";
    var btnColor = isDanger
      ? "bg-error text-white hover:brightness-110"
      : "bg-primary-container text-on-primary-fixed hover:brightness-105";

    var msgLines = message.split("\n").map(function (line) {
      line = line.trim();
      if (!line) return '<div class="h-1"></div>';
      if (line.indexOf("- ") === 0) {
        return '<li class="ml-4 list-disc text-secondary text-xs">' + escapeHTML(line.slice(2)) + '</li>';
      }
      return '<p class="font-body-sm text-secondary text-sm leading-relaxed">' + escapeHTML(line) + '</p>';
    }).join("");

    card.innerHTML =
      '<div class="flex items-start gap-3.5">' +
        '<div class="w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 ' + iconColor + '">' +
          '<span class="material-symbols-outlined text-[22px]">' + iconName + '</span>' +
        '</div>' +
        '<div class="flex-1">' +
          '<h3 class="font-headline-sm text-lg font-bold text-on-surface">' + escapeHTML(title) + '</h3>' +
          '<div class="mt-2 flex flex-col gap-1">' + msgLines + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="flex items-center justify-end gap-2.5 pt-2 border-t border-surface-container-high/40">' +
        '<button id="app-modal-cancel" type="button" class="px-4 py-2 rounded-full font-label-md text-sm font-semibold bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors cursor-pointer">' + escapeHTML(cancelText) + '</button>' +
        '<button id="app-modal-confirm" type="button" class="px-5 py-2 rounded-full font-label-md text-sm font-bold transition-all shadow-sm cursor-pointer ' + btnColor + '">' + escapeHTML(confirmText) + '</button>' +
      '</div>';

    scrim.appendChild(card);
    document.body.appendChild(scrim);

    function cleanup() {
      scrim.remove();
      document.removeEventListener("keydown", onKey);
    }
    function onKey(e) {
      if (e.key === "Escape") cleanup();
    }
    document.addEventListener("keydown", onKey);

    scrim.addEventListener("click", function (e) {
      if (e.target === scrim) cleanup();
    });

    card.querySelector("#app-modal-cancel").addEventListener("click", cleanup);
    card.querySelector("#app-modal-confirm").addEventListener("click", function () {
      cleanup();
      if (typeof opts.onConfirm === "function") opts.onConfirm();
    });
  }

  // ---------------------------------------------------------------------------
  // In-App Resume & Document Preview Modal (no external download popup)
  // ---------------------------------------------------------------------------
  function openResumePreviewModal(filename) {
    if (!filename) {
      showToast("No resume selected. Upload resumes in Profile section.");
      return;
    }
    var existing = document.getElementById("resume-preview-modal");
    if (existing) existing.remove();

    var safeName = filename.split(/[/\\]/).pop();
    var isPdf = safeName.toLowerCase().endsWith(".pdf");
    var resumeUrl = "/api/resume/" + encodeURIComponent(safeName);

    var scrim = document.createElement("div");
    scrim.id = "resume-preview-modal";
    scrim.className = "fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/75 backdrop-blur-xs app-modal";

    var card = document.createElement("div");
    card.className = "bg-surface-container-lowest border border-surface-container-high/80 rounded-3xl shadow-2xl w-full max-w-5xl h-[90vh] flex flex-col overflow-hidden animate-fade-in";

    card.innerHTML =
      '<div class="flex items-center justify-between px-5 py-3.5 border-b border-surface-container-high/60 bg-surface-container-low shrink-0">' +
        '<div class="flex items-center gap-2.5 min-w-0">' +
          '<div class="w-9 h-9 rounded-xl bg-primary-container/20 text-primary flex items-center justify-center shrink-0">' +
            '<span class="material-symbols-outlined text-[20px]">' + (isPdf ? 'picture_as_pdf' : 'description') + '</span>' +
          '</div>' +
          '<div class="min-w-0">' +
            '<h3 class="font-label-lg text-sm font-bold text-on-surface truncate">' + escapeHTML(safeName) + '</h3>' +
            '<p class="text-[11px] text-tertiary">In-Browser Document Preview</p>' +
          '</div>' +
        '</div>' +
        '<div class="flex items-center gap-2 shrink-0">' +
          '<a href="' + resumeUrl + '" target="_blank" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md text-xs font-semibold transition-all shadow-xs" title="Open in dedicated tab">' +
            '<span class="material-symbols-outlined text-[15px]">open_in_new</span>' +
            '<span class="hidden sm:inline">New Tab</span>' +
          '</a>' +
          '<button id="resume-preview-modal-close" type="button" class="w-8 h-8 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface flex items-center justify-center transition-all cursor-pointer" title="Close Preview">' +
            '<span class="material-symbols-outlined text-[18px]">close</span>' +
          '</button>' +
        '</div>' +
      '</div>' +
      '<div class="flex-1 w-full h-full bg-surface-container-low relative overflow-hidden">' +
        '<iframe src="' + resumeUrl + '" class="w-full h-full border-0 bg-white" title="Resume Preview"></iframe>' +
      '</div>';

    scrim.appendChild(card);
    document.body.appendChild(scrim);

    function cleanup() {
      scrim.remove();
      document.removeEventListener("keydown", onKey);
    }
    function onKey(e) {
      if (e.key === "Escape") cleanup();
    }
    document.addEventListener("keydown", onKey);

    scrim.addEventListener("click", function (e) {
      if (e.target === scrim) cleanup();
    });

    var closeBtn = card.querySelector("#resume-preview-modal-close");
    if (closeBtn) closeBtn.addEventListener("click", cleanup);
  }
  window.openResumePreviewModal = openResumePreviewModal;

  // ---------------------------------------------------------------------------
  // Live activity log streaming (#log-feed)
  // ---------------------------------------------------------------------------
  function formatSystemTime(ts, isoTime) {
    if (!ts && !isoTime) return "";
    try {
      var d = null;
      if (isoTime) {
        d = new Date(isoTime);
      } else if (ts) {
        if (ts.indexOf("T") !== -1 || ts.indexOf("-") !== -1) {
          d = new Date(ts);
        } else {
          var parts = ts.split(":");
          if (parts.length >= 2) {
            d = new Date();
            d.setHours(parseInt(parts[0], 10), parseInt(parts[1], 10), parseInt(parts[2] || "0", 10), 0);
          }
        }
      }
      if (d && !isNaN(d.getTime())) {
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      }
    } catch (e) {}
    return ts || "";
  }

  function renderLogRow(entry) {
    var tag = entry.status_tag || "INFO";
    var desc = entry.description || "";
    var when = formatSystemTime(entry.timestamp, entry.iso_time);
    var row = document.createElement("div");
    row.className = "flex items-start gap-space-sm";
    row.innerHTML =
      '<span class="text-tertiary-fixed-dim shrink-0 font-mono text-[11px]">' + escapeHTML(when) + "</span>" +
      '<div class="flex flex-col min-w-0"><span class="text-primary-container font-bold">' + escapeHTML(tag) + ":</span>" +
      '<span class="text-surface-container-highest">' + escapeHTML(desc) + "</span></div>";
    return row;
  }

  function pollLogs() {
    api("/api/logs?since=" + lastLogId)
      .then(function (rows) {
        if (!rows || !rows.length) return;
        var feeds = document.querySelectorAll('[id="log-feed"]');
        if (!feeds.length) return;
        rows.forEach(function (entry) {
          if (entry.id && entry.id > lastLogId) lastLogId = entry.id;
          feeds.forEach(function(feed) {
            feed.insertBefore(renderLogRow(entry), feed.firstChild);
          });
        });
        feeds.forEach(function(feed) {
          while (feed.children.length > 40) feed.removeChild(feed.lastChild);
        });
      })
      .catch(function () {});
  }

  function startLogPolling() {
    if (pollTimer) return;
    var feeds = document.querySelectorAll('[id="log-feed"]');
    if (!feeds.length) return;
    // Clear static mocks in all feeds
    feeds.forEach(function(f){ f.innerHTML = ""; });
    api("/api/logs").then(function (rows) {
      if (rows && rows.length) {
        var last = rows[rows.length - 1];
        lastLogId = last && last.id ? last.id : 0;
        // Optionally initially populate
        rows.slice(-40).forEach(function(entry){
          feeds.forEach(function(feed){
            feed.insertBefore(renderLogRow(entry), feed.firstChild);
          });
        });
      }
    }).catch(function () {});
    pollTimer = setInterval(pollLogs, 1500);
  }

  // ---------------------------------------------------------------------------
  // Tag / chip inputs (Advanced panel: multiple keywords + locations)
  // ---------------------------------------------------------------------------
  function tagValues(tagsEl) {
    var out = [];
    if (!tagsEl) return out;
    var chips = tagsEl.querySelectorAll("[data-tag]");
    for (var i = 0; i < chips.length; i++) {
      var v = chips[i].getAttribute("data-tag");
      if (v) out.push(v);
    }
    return out;
  }

  function renderTag(tagsEl, value) {
    var chip = document.createElement("span");
    chip.className = "inline-flex items-center gap-1 pl-2.5 pr-1.5 py-1 rounded-full " +
      "bg-primary-container/25 text-on-surface font-label-md text-[12px] font-bold";
    chip.setAttribute("data-tag", value);
    var label = document.createElement("span");
    label.textContent = value;
    var x = document.createElement("button");
    x.type = "button";
    x.className = "w-4 h-4 rounded-full bg-surface-container-highest text-secondary hover:text-error " +
      "flex items-center justify-center text-[12px] leading-none";
    x.textContent = "\u00d7";
    x.setAttribute("aria-label", "Remove " + value);
    x.addEventListener("click", function () {
      chip.remove();
    });
    chip.appendChild(label);
    chip.appendChild(x);
    tagsEl.appendChild(chip);
  }

  var SEARCH_STATE_KEY = "easapply_dashboard_search_state";

  function saveSearchState() {
    try {
      var urlInput = document.getElementById("url-input");
      var kwTags = tagValues(document.getElementById("keywords-tags"));
      var locTags = tagValues(document.getElementById("locations-tags"));
      var maxPostsInput = document.getElementById("max-posts-input");
      var modeInput = document.getElementById("mode-input");
      var scoreModeInput = document.getElementById("score-mode-input");

      var state = {
        url: urlInput ? urlInput.value : "",
        keywords: kwTags,
        locations: locTags,
        max_posts: maxPostsInput ? maxPostsInput.value : "15",
        mode: modeInput ? (modeInput.getAttribute("data-mode") || "posts") : "posts",
        score_mode: scoreModeInput ? (scoreModeInput.getAttribute("data-score-mode") || "collect_and_score") : "collect_and_score"
      };
      localStorage.setItem(SEARCH_STATE_KEY, JSON.stringify(state));
    } catch (e) {}
  }

  function getSavedSearchState() {
    try {
      var raw = localStorage.getItem(SEARCH_STATE_KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) {}
    return null;
  }

  function setupTagInput(tagsId, inputId, defaults, onChange) {
    var tagsEl = document.getElementById(tagsId);
    var input = document.getElementById(inputId);
    if (!tagsEl || !input) return;
    tagsEl.innerHTML = "";
    (defaults || []).forEach(function (d) { renderTag(tagsEl, d); });
    function notify() {
      if (typeof onChange === "function") onChange();
    }
    tagsEl.addEventListener("click", function (e) {
      if (e.target.closest("button")) {
        setTimeout(notify, 50);
      }
    });
    function commit() {
      var raw = input.value;
      var parts = raw.split(/[,;\n]+/);
      var added = false;
      parts.forEach(function (p) {
        var v = p.trim();
        if (!v) return;
        var exists = tagValues(tagsEl).some(function (t) {
          return t.toLowerCase() === v.toLowerCase();
        });
        if (!exists) {
          renderTag(tagsEl, v);
          added = true;
        }
      });
      if (added) {
        input.value = "";
        notify();
      }
      return added;
    }
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        commit();
      } else if (e.key === "Backspace" && !input.value) {
        var chips = tagsEl.querySelectorAll("[data-tag]");
        if (chips.length) {
          chips[chips.length - 1].remove();
          notify();
        }
      }
    });
    input.addEventListener("blur", commit);
  }

  // ---------------------------------------------------------------------------
  // Scrape form (#scrape-form)
  // ---------------------------------------------------------------------------
  function bindScrapeForm() {
    var form = document.getElementById("scrape-form");
    if (!form) return;
    var modeInput = document.getElementById("mode-input");
    var scoreModeInput = document.getElementById("score-mode-input");

    var savedState = getSavedSearchState();
    var defaultKw = (savedState && Array.isArray(savedState.keywords))
      ? savedState.keywords
      : [];
    var defaultLoc = (savedState && Array.isArray(savedState.locations))
      ? savedState.locations
      : [];

    setupTagInput("keywords-tags", "keywords-input", defaultKw, saveSearchState);
    setupTagInput("locations-tags", "location-input", defaultLoc, saveSearchState);

    var urlInput = document.getElementById("url-input");
    if (urlInput && savedState && savedState.url) {
      urlInput.value = savedState.url;
    }
    if (urlInput) {
      urlInput.addEventListener("input", saveSearchState);
    }
    loadProfilePreferences();

    var maxPostsInput = document.getElementById("max-posts-input");
    if (maxPostsInput && savedState && savedState.max_posts) {
      maxPostsInput.value = savedState.max_posts;
    }
    if (maxPostsInput) {
      maxPostsInput.addEventListener("input", saveSearchState);
    }

    var targetMode = (savedState && savedState.mode) || "posts";
    if (modeInput) modeInput.setAttribute("data-mode", targetMode);
    $$(".mode-btn", form).forEach(function (btn) {
      var val = btn.getAttribute("data-value") || "posts";
      if (val === targetMode) {
        btn.classList.add("active", "bg-primary-container", "text-on-primary-fixed");
        btn.classList.remove("text-secondary");
      } else {
        btn.classList.remove("active", "bg-primary-container", "text-on-primary-fixed");
        btn.classList.add("text-secondary");
      }
      btn.addEventListener("click", function () {
        $$(".mode-btn", form).forEach(function (b) {
          b.classList.remove("active", "bg-primary-container", "text-on-primary-fixed");
          b.classList.add("text-secondary");
        });
        btn.classList.add("active", "bg-primary-container", "text-on-primary-fixed");
        btn.classList.remove("text-secondary");
        if (modeInput) modeInput.setAttribute("data-mode", btn.getAttribute("data-value") || "posts");
        saveSearchState();
      });
    });

    var targetScoreMode = (savedState && savedState.score_mode) || "collect_and_score";
    if (scoreModeInput) scoreModeInput.setAttribute("data-score-mode", targetScoreMode);
    $$(".score-mode-btn", form).forEach(function (btn) {
      var val = btn.getAttribute("data-value") || "collect_and_score";
      if (val === targetScoreMode) {
        btn.classList.add("active", "bg-primary-container", "text-on-primary-fixed");
        btn.classList.remove("text-secondary");
      } else {
        btn.classList.remove("active", "bg-primary-container", "text-on-primary-fixed");
        btn.classList.add("text-secondary");
      }
      btn.addEventListener("click", function () {
        $$(".score-mode-btn", form).forEach(function (b) {
          b.classList.remove("active", "bg-primary-container", "text-on-primary-fixed");
          b.classList.add("text-secondary");
        });
        btn.classList.add("active", "bg-primary-container", "text-on-primary-fixed");
        btn.classList.remove("text-secondary");
        if (scoreModeInput) scoreModeInput.setAttribute("data-score-mode", btn.getAttribute("data-value") || "collect_and_score");
        saveSearchState();
      });
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();

      function executeScrape() {
        var input = document.getElementById("url-input");
        var submitBtn = document.getElementById("submit-btn");
        var maxPostsInput = document.getElementById("max-posts-input");
        var mode = modeInput ? (modeInput.getAttribute("data-mode") || "posts") : "posts";
        var scoreMode = scoreModeInput ? (scoreModeInput.getAttribute("data-score-mode") || "collect_and_score") : "collect_and_score";
        var keywords = input ? input.value.trim() : "";
        var payload = { url: "", mode: mode, score_mode: scoreMode };

        var kwTags = tagValues(document.getElementById("keywords-tags"));
        var locTags = tagValues(document.getElementById("locations-tags"));
        var kwInput = document.getElementById("keywords-input");
        var locInput = document.getElementById("location-input");
        if (kwInput && kwInput.value.trim()) kwTags.push(kwInput.value.trim());
        if (locInput && locInput.value.trim()) locTags.push(locInput.value.trim());
        if (kwTags.length) payload.keywords_list = kwTags;
        if (locTags.length) payload.locations = locTags;
        var maxPosts = maxPostsInput ? parseInt(maxPostsInput.value, 10) : NaN;
        payload.max_posts = isNaN(maxPosts) ? 15 : Math.min(50, Math.max(1, maxPosts));

        if (keywords) {
          if (/^https?:\/\//i.test(keywords)) {
            payload.url = keywords;
          } else {
            payload.keywords = keywords;
            if (!payload.keywords_list) payload.keywords_list = [keywords];
          }
        }

        if (submitBtn) {
          var original = submitBtn.innerHTML;
          submitBtn.disabled = true;
          submitBtn.innerHTML = '<span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span><span>Search Started...</span>';
          setTimeout(function () {
            submitBtn.disabled = false;
            submitBtn.innerHTML = original;
          }, 4000);
        }

        api("/api/scrape", { method: "POST", body: payload })
          .then(function () {
            showToast(payload.score_mode === "collect_only"
              ? "Collecting listings without scoring (no AI credits used)."
              : "Job search dispatched. Watch the live activity feed below.");
            setScrapeStopVisible(true);
            if (!document.getElementById("log-feed")) {
              setTimeout(function () { navigateTo("dashboard"); }, 1200);
            }
          })
          .catch(function (err) {
            showToast("Scrape failed: " + err.message);
          });
      }

      // Check LinkedIn session first
      api("/api/linkedin-status")
        .then(function (res) {
          if (res && res.logged_in) {
            executeScrape();
          } else {
            openLinkedInLoginModal(executeScrape);
          }
        })
        .catch(function () {
          executeScrape();
        });
    });
  }

  // ---------------------------------------------------------------------------
  // Live Matches list (same card design as the static mocks, best score first)
  // ---------------------------------------------------------------------------
  function matchTier(score) {
    if (!score) return { label: "Unscored", cls: "bg-surface-container-high text-secondary" };
    if (score >= 75) return { label: "Top Fit", cls: "bg-primary-container text-on-primary-fixed" };
    if (score >= 50) return { label: "Review", cls: "bg-surface-container-high text-on-surface-variant" };
    return { label: "Low Fit", cls: "bg-surface-container-high text-secondary" };
  }

  function safeLink(url) {
    url = String(url || "").trim();
    return /^https?:\/\//i.test(url) ? url : "";
  }

  function getValidListingUrl(app) {
    if (!app) return "";
    var raw = (app.link || "").trim();
    // 1. If it contains an activity URN or ID, convert to universal canonical feed update URL
    var mAct = raw.match(/(?:activity(?::|-|%3A)|urn:li:activity:)(\d{15,22})/i);
    if (mAct && mAct[1]) {
      return "https://www.linkedin.com/feed/update/urn:li:activity:" + mAct[1] + "/";
    }
    // Also check job_id if it holds an activity URN
    var jId = (app.job_id || "").trim();
    var mJobAct = jId.match(/(?:activity(?::|-|%3A)|urn:li:activity:)(\d{15,22})/i);
    if (mJobAct && mJobAct[1]) {
      return "https://www.linkedin.com/feed/update/urn:li:activity:" + mJobAct[1] + "/";
    }

    // Valid if it is a specific post, feed update, job permalink, or LinkedIn search link, and not a generic feed URL or profile URL
    if (raw && !raw.includes("example.com") && !raw.includes("/feed/?") && raw !== "https://www.linkedin.com/feed/" && raw !== "https://www.linkedin.com/feed" && !raw.includes("/in/")) {
      return raw.split("?")[0];
    }
    if (app.company || app.title) {
      var q = encodeURIComponent([app.title, app.company].filter(Boolean).join(" "));
      return "https://www.linkedin.com/search/results/content/?keywords=" + q + "&sortBy=%22relevance%22";
    }
    return (!raw.includes("/in/")) ? (raw || "https://www.linkedin.com/jobs") : "https://www.linkedin.com/jobs";
  }

  var __matchCache = {};

  function mailInnerHTML(a) {
    if (!a || !a.email_draft_body) {
      return '';
    }
    var kw = a.missing_keywords
      ? '<div class="flex items-start gap-1.5 mt-space-sm font-body-sm text-body-sm text-secondary"><span class="material-symbols-outlined text-[16px] shrink-0">key</span><span>' + escapeHTML(a.missing_keywords) + '</span></div>'
      : "";
    return '<div class="flex items-start justify-between gap-2">' +
        '<p class="font-label-md text-label-md font-bold text-on-surface">' + escapeHTML(a.email_draft_subject || "Draft") + '</p>' +
        '<div class="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">' +
          '<button class="flex items-center gap-1 px-space-sm py-1 rounded-full bg-surface-container-highest hover:bg-surface-container-high text-on-surface font-label-md text-label-md font-bold transition-colors" data-copy-mail="' + a.id + '" type="button"><span class="material-symbols-outlined text-[16px]">content_copy</span>Copy</button>' +
          '<button class="flex items-center gap-1 px-space-sm py-1 rounded-full bg-primary-container text-on-primary-fixed hover:brightness-105 font-label-md text-label-md font-bold transition-all" data-queue-mail="' + a.id + '" type="button"><span class="material-symbols-outlined text-[16px]">schedule_send</span>Auto-send</button>' +
          '<button class="flex items-center gap-1 px-space-sm py-1 rounded-full bg-surface-container-highest hover:bg-surface-container-high text-on-surface font-label-md text-label-md font-bold transition-colors" data-resume-dl="' + a.id + '" data-resume-fmt="docx" type="button"><span class="material-symbols-outlined text-[16px]">description</span>Resume</button>' +
          '<button class="flex items-center gap-1 px-space-sm py-1 rounded-full bg-surface-container-highest hover:bg-surface-container-high text-on-surface font-label-md text-label-md font-bold transition-colors" data-resume-dl="' + a.id + '" data-resume-fmt="pdf" type="button"><span class="material-symbols-outlined text-[16px]">picture_as_pdf</span>PDF</button>' +
        '</div>' +
      '</div>' +
      '<p class="font-body-sm text-body-sm text-on-surface mt-space-xs whitespace-pre-wrap">' + escapeHTML(a.email_draft_body) + '</p>' +
      (a.tailored_resume_text ? '<p class="font-body-sm text-body-sm text-secondary mt-space-sm"><span class="font-bold text-on-surface">Resume notes: </span>' + escapeHTML(a.tailored_resume_text).slice(0, 400) + '</p>' : "") +
      kw;
  }

  function atsChip(a) {
    var s = parseInt(a.ats_score, 10) || 0;
    if (!s) return "";
    var tip = "ATS employability score";
    try {
      var b = JSON.parse(a.ats_breakdown || "{}");
      var parts = [];
      if (b.keyword_coverage != null) parts.push("keywords " + b.keyword_coverage + "%");
      if (b.title_fit != null) parts.push("title " + b.title_fit + "%");
      if (b.seniority_fit != null) parts.push("seniority " + b.seniority_fit + "%");
      if (b.format_hygiene != null) parts.push("format " + b.format_hygiene + "%");
      if (parts.length) tip = parts.join(" • ");
    } catch (err) {}
    return '<span class="px-2 py-0.5 rounded-full bg-surface-container text-secondary font-code-header text-code-header uppercase" title="' + escapeHTML(tip) + '">ATS ' + s + '%</span>';
  }

  function getCardRoleTitle(a) {
    var t = (a.title || "").trim();
    var author = (a.author_name || "").trim();
    var comp = (a.company || "").trim();
    var desc = a.description || "";
    var roleKeywords = ["designer", "developer", "engineer", "manager", "lead", "architect", "intern", "internship", "specialist", "product", "analyst", "consultant", "director", "writer", "editor", "coordinator", "head of", "vp", "executive", "founder", "frontend", "backend", "fullstack", "ui/ux", "graphic", "ux", "ui"];

    // 1. If existing title is already a clean, distinct role (not equal to author/company and not generic), clean and use it
    var isGeneric = !t || t.toLowerCase() === "untitled role" || t.toLowerCase() === "hiring post" || t.toLowerCase() === "hiring opportunity" || t.toLowerCase() === "hiring" || t === author || t === comp;

    if (!isGeneric) {
      var cleanT = t.replace(/#\w+/g, '').replace(/^[⭐🎬🚀🎨•\-–:\s]+|[⭐🎬🚀🎨•\-–:\s]+$/g, '').trim();
      cleanT = cleanT.replace(/^(?:job\s*title|role|hiring|position|we\s*are\s*hiring|we\'re\s*hiring|always\s*hiring)\s*[:\-–]?\s*/i, '').trim();
      if (cleanT && cleanT.length > 3 && cleanT !== author && cleanT !== comp && !cleanT.startsWith('#')) {
        return cleanT;
      }
    }

    // 2. Otherwise extract from description if available
    if (desc) {
      var lines = desc.split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean);

      // A. Look for '... is hiring:? <Role>' or 'hiring <Role>'
      for (var i = 0; i < Math.min(lines.length, 10); i++) {
        var ln = lines[i];
        var m = ln.match(/(?:is\s+hiring|hiring(?:\s+for)?|looking\s+for|seeking)\s*[:\-–]?\s*(?:a\s+|an\s+)?([A-Za-z0-9\s\/\-–&]+?)(?:\s+(?:in|at|from|\.|\!|\?|http|https|#)|$)/i);
        if (m && m[1]) {
          var cand = m[1].trim().replace(/^[⭐🎬🚀🎨•\-–:\s]+|[⭐🎬🚀🎨•\-–:\s]+$/g, '').trim();
          if (roleKeywords.some(function (k) { return cand.toLowerCase().indexOf(k) !== -1; }) && cand.length > 3 && cand.length < 60) {
            return cand;
          }
        }
      }

      // B. Look for lines with role keywords, ignoring lines that are mostly hashtags
      for (var j = 0; j < Math.min(lines.length, 10); j++) {
        var rawLn = lines[j];
        var cleanLn = rawLn.replace(/#\w+/g, '').trim();
        cleanLn = cleanLn.replace(/^(?:job\s*title|role|hiring|position|we\s*are\s*hiring|we\'re\s*hiring|always\s*hiring)\s*[:\-–]?\s*/i, '').trim();
        cleanLn = cleanLn.replace(/^[⭐🎬🚀🎨•\-–:\s]+|[⭐🎬🚀🎨•\-–:\s]+$/g, '').trim();
        if (roleKeywords.some(function (k) { return cleanLn.toLowerCase().indexOf(k) !== -1; }) && cleanLn.length > 3 && cleanLn.length < 75 && cleanLn !== author && cleanLn !== comp) {
          var cut = cleanLn.split(/\s+(?:in|at|https?:|#)/i)[0].trim();
          return (cut && cut.length > 3) ? cut : cleanLn;
        }
      }
    }

    return t || "Hiring Opportunity";
  }

  function renderMatchCard(a, rank) {
    var score = Math.max(0, Math.min(100, parseInt(a.match_score, 10) || 0));
    var tier = matchTier(score);
    var circ = 113.097;
    var off = (circ * (1 - score / 100)).toFixed(2);
    var postUrl = safeLink(getValidListingUrl(a));
    var authorUrl = safeLink(a.author_profile_url);
    var sharerName = (a.author_name || a.company || "LinkedIn Member").trim();
    var initial = escapeHTML(sharerName.charAt(0).toUpperCase() || "?");
    var isPost = (a.source_type || "posts").toLowerCase().indexOf("post") !== -1;
    var sourceTag = isPost ? "POST" : "JOB";
    var sharerLink = authorUrl || (isPost ? postUrl : "");
    var sharerHtml = sharerLink
      ? '<a class="font-medium text-on-surface hover:text-primary hover:underline transition-colors inline-flex items-center gap-1" href="' + sharerLink + '" target="_blank" rel="noopener noreferrer" title="View Profile" onclick="event.stopPropagation();">' + escapeHTML(sharerName) + '</a>'
      : '<span class="font-medium text-on-surface">' + escapeHTML(sharerName) + '</span>';

    var roleTitle = getCardRoleTitle(a);
    var contact = escapeHTML(a.contact_info || "");

    var card = document.createElement("div");
    card.className = "p-space-lg hover:bg-surface-container-high/25 transition-colors cursor-pointer group";
    card.setAttribute("data-match-id", a.id);
    card.innerHTML =
      '<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-space-md">' +
        '<div class="flex items-start gap-space-md min-w-0 flex-1">' +
          '<div class="w-12 h-12 rounded-2xl bg-surface-container flex items-center justify-center text-on-surface font-bold text-headline-sm shrink-0">' + initial + '</div>' +
          '<div class="flex flex-col min-w-0 gap-1.5">' +
            '<div class="flex items-center gap-space-xs flex-wrap">' +
              '<h2 class="font-headline-sm text-headline-sm font-bold text-on-surface group-hover:text-primary transition-colors">' + escapeHTML(roleTitle) + '</h2>' +
              '<span class="px-2 py-0.5 rounded-full font-code-header text-code-header uppercase ' + tier.cls + '">' + tier.label + '</span>' +
              atsChip(a) +
            '</div>' +
            '<div class="flex items-center gap-space-xs text-secondary font-body-sm text-body-sm flex-wrap">' +
              '<span class="px-2 py-0.5 rounded-full bg-surface-container font-code-header text-code-header uppercase font-bold text-secondary tracking-wider text-[11px]">' + sourceTag + '</span>' +
              sharerHtml +
              (a.location ? '<span class="flex items-center gap-0.5 text-secondary"><span class="material-symbols-outlined text-[14px]">public</span>' + escapeHTML(a.location) + '</span>' : "") +
              (contact ? '<span class="flex items-center gap-1 text-secondary"><span class="material-symbols-outlined text-[14px]">mail</span>' + contact + '</span>' : "") +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="flex sm:flex-col items-center sm:items-end justify-between sm:justify-center gap-2 shrink-0">' +
          '<div class="relative w-13 h-13 sm:w-14 sm:h-14 flex items-center justify-center">' +
            '<svg class="w-full h-full -rotate-90" viewBox="0 0 44 44"><circle class="text-surface-container-high" cx="22" cy="22" fill="none" r="18" stroke="currentColor" stroke-width="4"></circle>' +
            '<circle class="text-primary-container" cx="22" cy="22" fill="none" r="18" stroke="currentColor" stroke-dasharray="' + circ + '" stroke-dashoffset="' + off + '" stroke-linecap="round" stroke-width="4"></circle></svg>' +
            '<span class="absolute font-headline-sm text-headline-sm font-bold text-on-surface">' + score + '<span class="text-body-sm font-normal">%</span></span>' +
          '</div>' +
          '<div class="flex items-center gap-2 flex-wrap justify-end mt-1">' +
            '<button class="flex items-center gap-1 px-3.5 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md text-label-md font-bold transition-colors cursor-pointer shadow-sm" data-generate-mail="' + a.id + '" type="button"><span class="material-symbols-outlined text-[16px]">edit_note</span><span>' + (a.email_draft_body ? "Regenerate" : "Generate mail") + '</span></button>' +
            (postUrl ? '<a class="flex items-center gap-1 px-3.5 py-1.5 rounded-full bg-[#0A66C2]/10 hover:bg-[#0A66C2]/20 text-[#0A66C2] font-label-md text-label-md font-semibold transition-colors cursor-pointer shadow-sm" href="' + postUrl + '" target="_blank" rel="noopener noreferrer" title="View original post on LinkedIn" onclick="event.stopPropagation();"><span class="material-symbols-outlined text-[16px]">open_in_new</span><span>View on LinkedIn</span></a>' : "") +
          '</div>' +
        '</div>' +
      '</div>';
    return card;
  }

  function bindMatches() {
    var lists = $$('[id="matches-list"]');
    if (!lists.length) return;
    function refreshPanel(id) {
      var a = __matchCache[id];
      if (!a) return;
      $$('[data-mail-panel="' + id + '"]').forEach(function (panel) {
        panel.innerHTML = mailInnerHTML(a);
      });
      // keep Generate/Regenerate label in sync
      $$('[data-generate-mail="' + id + '"]').forEach(function (btn) {
        btn.innerHTML = '<span class="material-symbols-outlined text-[16px]">edit_note</span>' + (a.email_draft_body ? "Regenerate" : "Generate mail");
      });
    }
    lists.forEach(function (list) {
      if (list.__mailBound) return;
      list.__mailBound = true;
      list.addEventListener("click", function (e) {
        var gen = e.target.closest("[data-generate-mail]");
        if (gen) {
          var id = gen.getAttribute("data-generate-mail");
          window.location.href = "/outreach?id=" + encodeURIComponent(id) + "&composer=true";
          return;
        }
        var queue = e.target.closest("[data-queue-mail]");
        if (queue) {
          var qid = queue.getAttribute("data-queue-mail");
          queue.disabled = true;
          api("/api/outreach/queue", { method: "POST", body: { app_id: parseInt(qid, 10) } })
            .then(function (res) {
              showToast(res && res.position
                ? "Queued for auto-send (#" + res.position + " in line) to " + (res.to_email || "recipient") + "."
                : "Queued for auto-send.");
            })
            .catch(function (err) { showToast("Queue failed: " + err.message); })
            .then(function () { queue.disabled = false; });
          return;
        }
        var dl = e.target.closest("[data-resume-dl]");
        if (dl) {
          var fmt = dl.getAttribute("data-resume-fmt") || "docx";
          showToast("Building tailored resume (" + fmt.toUpperCase() + ")...");
          window.open("/api/applications/" + encodeURIComponent(dl.getAttribute("data-resume-dl")) + "/resume?format=" + encodeURIComponent(fmt), "_blank");
          return;
        }
        var copy = e.target.closest("[data-copy-mail]");
        if (copy) {
          var ca = __matchCache[copy.getAttribute("data-copy-mail")];
          if (!ca) return;
          var text = (ca.email_draft_subject ? ca.email_draft_subject + "\n\n" : "") + (ca.email_draft_body || "");
          copyTextToClipboard(text);
          return;
        }

        // Ignore clicks on buttons or links
        if (e.target.closest("button") || e.target.closest("a")) {
          return;
        }

        // Clicking anywhere on the match card opens the detailed application view
        var matchCard = e.target.closest("[data-match-id]");
        if (matchCard) {
          var matchId = matchCard.getAttribute("data-match-id");
          if (matchId) {
            window.location.href = "/outreach?id=" + encodeURIComponent(matchId);
            return;
          }
        }
      });
    });

    api("/api/applications").then(function (apps) {
      apps = apps || [];
      apps.forEach(function (a) {
        __matchCache[a.id] = a;
      });

      var activeMatchFilter = "all";
      var activeTimeline = "all";
      var activeSort = "newest";
      var activeSearch = "";
      var customStart = null;
      var customEnd = null;

      function renderFilteredMatches() {
        var now = new Date();
        var todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        var yesterdayStart = new Date(todayStart.getTime() - 24 * 60 * 60 * 1000);
        var sevenDaysAgo = new Date(todayStart.getTime() - 7 * 24 * 60 * 60 * 1000);

        var filtered = apps.filter(function (a) {
          var score = parseInt(a.match_score, 10) || 0;
          if (activeMatchFilter === "strong" && score < 70) return false;
          if (activeMatchFilter === "review" && score >= 70) return false;

          // Timeline filter
          if (activeTimeline !== "all") {
            var rawDate = a.created_at;
            var created = rawDate ? new Date(rawDate) : null;
            if (created && !isNaN(created.getTime())) {
              if (activeTimeline === "today" && created < todayStart) return false;
              if (activeTimeline === "yesterday" && (created < yesterdayStart || created >= todayStart)) return false;
              if (activeTimeline === "7d" && created < sevenDaysAgo) return false;
              if (activeTimeline === "custom") {
                if (customStart && created < customStart) return false;
                if (customEnd && created > customEnd) return false;
              }
            }
          }

          // Search keyword filter
          if (activeSearch) {
            var q = activeSearch.toLowerCase();
            var hay = [a.title, a.company, a.location, a.author_name, a.description].filter(Boolean).join(" ").toLowerCase();
            if (hay.indexOf(q) === -1) return false;
          }
          return true;
        });

        // Sorting
        filtered.sort(function (a, b) {
          if (activeSort === "score_desc") {
            return (parseInt(b.match_score, 10) || 0) - (parseInt(a.match_score, 10) || 0);
          } else if (activeSort === "oldest") {
            return (a.id || 0) - (b.id || 0);
          } else {
            // Newest scraped first
            return (b.id || 0) - (a.id || 0);
          }
        });

        lists.forEach(function (list) {
          list.innerHTML = "";
          if (!filtered.length) {
            list.innerHTML = '<div class="p-space-xl text-center bg-surface-container-lowest rounded-2xl border border-surface-container-high/50"><span class="material-symbols-outlined text-[36px] text-tertiary mb-2">search_off</span><p class="font-body-md text-body-md text-secondary">No matched opportunities match the selected filters or date range.</p></div>';
          } else {
            var frag = document.createDocumentFragment();
            filtered.forEach(function (a, i) {
              frag.appendChild(renderMatchCard(a, i + 1));
            });
            list.appendChild(frag);
          }
        });
        updateMetricsCards(filtered);
      }

      // Filter pills (All / Strong / Review)
      var filterPills = $$(".filter-pill", document.getElementById("matches-filter-bar"));
      filterPills.forEach(function (pill) {
        pill.addEventListener("click", function () {
          filterPills.forEach(function (p) {
            p.classList.remove("bg-primary-container", "text-on-primary-fixed", "font-bold", "active", "shadow-[0_2px_8px_rgba(182,244,56,0.35)]");
            p.classList.add("text-secondary");
            p.setAttribute("aria-selected", "false");
          });
          pill.classList.add("bg-primary-container", "text-on-primary-fixed", "font-bold", "active");
          pill.classList.remove("text-secondary", "shadow-[0_2px_8px_rgba(182,244,56,0.35)]");
          pill.setAttribute("aria-selected", "true");
          activeMatchFilter = pill.getAttribute("data-filter") || "all";
          renderFilteredMatches();
        });
      });

      // Timeline Filter Chips
      var timelineBtns = $$(".matches-timeline-btn");
      var customDateCont = document.getElementById("matches-custom-date-container");
      var startDateInput = document.getElementById("matches-start-date");
      var endDateInput = document.getElementById("matches-end-date");

      timelineBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          timelineBtns.forEach(function (b) {
            b.classList.remove("active", "bg-primary-container", "text-on-primary-fixed");
            b.classList.add("bg-surface-container", "text-secondary");
          });
          btn.classList.add("active", "bg-primary-container", "text-on-primary-fixed");
          btn.classList.remove("bg-surface-container", "text-secondary");
          activeTimeline = btn.getAttribute("data-timeline") || "all";
          if (customDateCont) {
            if (activeTimeline === "custom") {
              customDateCont.classList.remove("hidden");
            } else {
              customDateCont.classList.add("hidden");
            }
          }
          renderFilteredMatches();
        });
      });

      if (startDateInput) {
        startDateInput.addEventListener("change", function () {
          if (startDateInput.value && endDateInput) {
            endDateInput.min = startDateInput.value;
            if (endDateInput.value && endDateInput.value < startDateInput.value) {
              endDateInput.value = startDateInput.value;
            }
          }
          customStart = startDateInput.value ? new Date(startDateInput.value + "T00:00:00") : null;
          renderFilteredMatches();
        });
      }
      if (endDateInput) {
        endDateInput.addEventListener("change", function () {
          if (startDateInput && startDateInput.value && endDateInput.value < startDateInput.value) {
            endDateInput.value = startDateInput.value;
          }
          customEnd = endDateInput.value ? new Date(endDateInput.value + "T23:59:59") : null;
          renderFilteredMatches();
        });
      }
      var clearDateBtn = document.getElementById("matches-clear-date-btn");
      if (clearDateBtn && !clearDateBtn.__bound) {
        clearDateBtn.__bound = true;
        clearDateBtn.addEventListener("click", function () {
          if (startDateInput) startDateInput.value = "";
          if (endDateInput) { endDateInput.value = ""; endDateInput.removeAttribute("min"); }
          customStart = null;
          customEnd = null;
          renderFilteredMatches();
        });
      }

      // Sort Select
      var sortSelect = document.getElementById("matches-sort-select");
      if (sortSelect) {
        sortSelect.addEventListener("change", function () {
          activeSort = sortSelect.value || "newest";
          renderFilteredMatches();
        });
      }

      // Search input
      var searchInput = document.getElementById("matches-search-input");
      if (searchInput) {
        searchInput.addEventListener("input", function () {
          activeSearch = (searchInput.value || "").trim();
          renderFilteredMatches();
        });
      }

      function updateMetricsCards(targetApps) {
        var list = targetApps || apps;
        var scoredList = list.filter(function (a) {
          var s = parseInt(a.match_score, 10);
          return !isNaN(s) && s > 0;
        });
        var strongList = scoredList.filter(function (a) {
          return (parseInt(a.match_score, 10) || 0) >= 70;
        });
        var totalScore = scoredList.reduce(function (acc, a) {
          return acc + (parseInt(a.match_score, 10) || 0);
        }, 0);
        var avgScore = scoredList.length ? Math.round(totalScore / scoredList.length) : 0;

        var discEl = document.getElementById("stat-matches-discovered");
        if (discEl) discEl.textContent = list.length;
        var strongEl = document.getElementById("stat-matches-strong");
        if (strongEl) strongEl.textContent = strongList.length;
        var avgEl = document.getElementById("stat-matches-avg");
        if (avgEl) avgEl.textContent = scoredList.length ? avgScore + "%" : "--";
      }

      // Initial render & metrics update
      renderFilteredMatches();
      updateMetricsCards(apps);

      // Check last scan duration on initial load
      api("/api/scrape/status").then(function (st) {
        if (st && st.last_scan_summary) {
          var scanTimeCard = document.getElementById("matches-scan-time-card");
          var scanTimeText = document.getElementById("matches-scan-time-text");
          if (scanTimeCard && scanTimeText) {
            scanTimeCard.classList.remove("hidden");
            scanTimeCard.classList.add("flex");
            scanTimeText.textContent = st.last_scan_summary;
          }
        }
      }).catch(function () {});
    }).catch(function () {});
  }

  function renderEmptyMatches(total, unscored) {
    var card = document.createElement("div");
    card.className = "bg-surface-container-lowest rounded-[28px] p-space-xl shadow-[0_4px_24px_rgba(0,0,0,0.03)] flex flex-col items-center text-center gap-space-sm";
    var title = total === 0 ? "No matches yet" : "Collected, not scored yet";
    var body = total === 0
      ? "Run your first scrape from the Dashboard — results ranked best-first will appear here."
      : total + " listing(s) collected, " + unscored + " awaiting AI scoring.";
    card.innerHTML =
      '<div class="w-12 h-12 rounded-2xl bg-surface-container flex items-center justify-center text-secondary"><span class="material-symbols-outlined text-[26px]">auto_awesome</span></div>' +
      '<h2 class="font-headline-sm text-headline-sm font-bold text-on-surface">' + title + '</h2>' +
      '<p class="font-body-sm text-body-sm text-secondary max-w-md">' + body + '</p>' +
      '<div class="flex items-center gap-space-xs flex-wrap justify-center">' +
        (total === 0
          ? '<button class="px-space-md py-1.5 rounded-full bg-primary-container text-on-primary-fixed font-label-md text-label-md font-bold transition-all" data-path="dashboard" type="button">Go to Dashboard</button>'
          : '<button class="px-space-md py-1.5 rounded-full bg-primary-container text-on-primary-fixed font-label-md text-label-md font-bold transition-all" data-score-now type="button">Score now</button>') +
      '</div>';
    var btn = card.querySelector("[data-score-now]");
    if (btn) {
      btn.addEventListener("click", function () {
        btn.disabled = true;
        api("/api/score", { method: "POST", body: {} })
          .then(function () { showToast("Scoring dispatched — watch Matches fill in."); })
          .catch(function (err) { showToast("Score failed: " + err.message); })
          .then(function () { btn.disabled = false; });
      });
    }
    return card;
  }

  function copyTextToClipboard(text) {
    function done(ok) { showToast(ok ? "Mail copied to clipboard." : "Copy failed — select the text manually."); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
    } else {
      var ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { done(document.execCommand("copy")); } catch (err) { done(false); }
      document.body.removeChild(ta);
    }
  }

  // ---------------------------------------------------------------------------
  // Analytics: period pills, live stat cards, outreach table + pagination
  // ---------------------------------------------------------------------------
  var __analyticsPeriod = "30d";
  var __analyticsRows = [];
  var __analyticsPage = 1;
  var __analyticsFilter = "";
  var __analyticsStatusFilter = "all";
  var ANALYTICS_PAGE_SIZE = 8;

  function analyticsPillActive(btn, on) {
    btn.classList.toggle("bg-primary-container", on);
    btn.classList.toggle("text-on-primary-fixed", on);
    btn.classList.toggle("font-bold", on);
    btn.classList.toggle("text-secondary", !on);
    btn.classList.remove("shadow-[0_2px_10px_rgba(182,244,56,0.35)]", "shadow-[0_2px_8px_rgba(182,244,56,0.35)]");
  }

  function bindAnalytics() {
    var pills = [];
    var findJobs = [];
    $$("button").forEach(function (b) {
      var attrPeriod = b.getAttribute("data-period");
      var t = ((b.textContent || "").replace(/\s+/g, " ")).trim();
      var map = { "30 Days": "30d", "90 Days": "90d", "YTD": "ytd", "All Time": "all" };
      var key = attrPeriod || map[t] || (t.indexOf("Custom") === 0 ? "all" : null);
      if (key && !b.__periodBound) {
        b.__periodBound = true;
        b.setAttribute("data-period", key);
        pills.push(b);
        (function (btn, period) {
          btn.addEventListener("click", function () {
            __analyticsPeriod = period;
            __analyticsPage = 1;
            pills.forEach(function (p) { analyticsPillActive(p, p === btn); });
            loadAnalytics();
          });
        })(b, key);
      }
      if ((b.textContent || "").indexOf("Find Matching Jobs") !== -1 && !b.__findBound) {
        b.__findBound = true;
        findJobs.push(b);
        b.addEventListener("click", function () { navigateTo("dashboard#scrape-form"); });
      }
    });

    // Wire status filter pills (All, Applied, Interviewing, Sent, Queued)
    $$("#analytics-status-filter-bar .analytics-status-pill").forEach(function (pill) {
      if (pill.__bound) return;
      pill.__bound = true;
      pill.addEventListener("click", function () {
        __analyticsStatusFilter = pill.getAttribute("data-status") || "all";
        $$("#analytics-status-filter-bar .analytics-status-pill").forEach(function (p) {
          var on = p === pill;
          p.classList.toggle("bg-primary-container", on);
          p.classList.toggle("text-on-primary-fixed", on);
          p.classList.toggle("font-bold", on);
          p.classList.toggle("text-secondary", !on);
          p.classList.toggle("font-semibold", !on);
        });
        __analyticsPage = 1;
        renderAnalyticsTable();
      });
    });

    // Wire CSV Export button
    var exportBtn = document.getElementById("analytics-export-csv");
    if (exportBtn && !exportBtn.__bound) {
      exportBtn.__bound = true;
      exportBtn.addEventListener("click", function () {
        window.location.href = "/api/analytics/export?period=" + encodeURIComponent(__analyticsPeriod);
      });
    }

    $$('#analytics-search-input, input[placeholder^="Filter company"]').forEach(function (inp) {
      if (inp.__filterBound) return;
      inp.__filterBound = true;
      inp.addEventListener("input", function () {
        __analyticsFilter = inp.value || "";
        __analyticsPage = 1;
        renderAnalyticsTable();
      });
    });
    if (!pills.length && !$("tbody")) return;
    loadAnalytics();
  }

  function loadAnalytics() {
    api("/api/analytics?period=" + encodeURIComponent(__analyticsPeriod)).then(function (d) {
      if (!d) return;
      paintAnalyticsStats(d);
      __analyticsRows = d.recent || [];
      __analyticsPage = 1;
      renderAnalyticsTable();
    }).catch(function () {});
  }

  function paintAnalyticsStats(d) {
    var vals = {
      "Emails Sent": { v: d.sent, sub: "in selected period" },
      "Queued": { v: d.queued, sub: "scheduled, trickling out" },
      "Applied": { v: d.applied != null ? d.applied : ((d.by_status || {}).Applied || 0), sub: "marked applied on send" },
      "Avg Match Score": { v: (d.avg_match || 0) + "%", sub: d.scored + " scored in period" }
    };
    $$("span").forEach(function (el) {
      var t = (el.textContent || "").trim();
      if (!vals[t]) return;
      var card = el.closest("div.bg-surface-container-lowest") || el.closest("div.rounded-\\[28px\\]") || el.closest("div[class*='rounded-']");
      if (!card) return;
      var big = card.querySelector(".font-display-hero");
      if (big) big.textContent = vals[t].v;
      var sub = card.querySelector("p.font-body-sm");
      if (sub) sub.textContent = vals[t].sub;
    });

    // Update Conversion Matrix Funnel
    var totalScraped = d.total || 0;
    var totalQualified = d.qualified || 0;
    var totalDispatched = (d.sent || 0) + (d.queued || 0);

    var elScrapedCount = document.getElementById("funnel-scraped-count");
    if (elScrapedCount) elScrapedCount.textContent = totalScraped;
    var elScrapedPct = document.getElementById("funnel-scraped-pct");
    if (elScrapedPct) elScrapedPct.textContent = totalScraped > 0 ? "100%" : "0%";
    var elScrapedBar = document.getElementById("funnel-scraped-bar");
    if (elScrapedBar) elScrapedBar.style.width = totalScraped > 0 ? "100%" : "0%";

    var qualPct = totalScraped > 0 ? Math.round((totalQualified / totalScraped) * 100) : 0;
    var elQualCount = document.getElementById("funnel-qualified-count");
    if (elQualCount) elQualCount.textContent = totalQualified;
    var elQualPct = document.getElementById("funnel-qualified-pct");
    if (elQualPct) elQualPct.textContent = totalScraped > 0 ? qualPct + "%" : "--";
    var elQualBar = document.getElementById("funnel-qualified-bar");
    if (elQualBar) elQualBar.style.width = qualPct + "%";

    var dispPct = totalScraped > 0 ? Math.round((totalDispatched / totalScraped) * 100) : 0;
    var elDispCount = document.getElementById("funnel-dispatched-count");
    if (elDispCount) elDispCount.textContent = totalDispatched;
    var elDispPct = document.getElementById("funnel-dispatched-pct");
    if (elDispPct) elDispPct.textContent = totalScraped > 0 ? dispPct + "%" : "--";
    var elDispBar = document.getElementById("funnel-dispatched-bar");
    if (elDispBar) elDispBar.style.width = dispPct + "%";

    // Update Historical Velocity Container
    var velCont = document.getElementById("analytics-velocity-container");
    if (velCont) {
      var trends = d.daily_trend || [];
      var hasData = trends.some(function (t) { return t.count > 0; });
      if (hasData) {
        var maxCount = Math.max.apply(null, trends.map(function (t) { return t.count; })) || 1;
        var barsHtml = trends.map(function (t) {
          var heightPct = Math.max(12, Math.round((t.count / maxCount) * 100));
          var scoreBadge = t.avg_score > 0 ? t.avg_score + "%" : "—";
          return (
            '<div class="flex-1 flex flex-col items-center gap-2 group h-full justify-end">' +
              '<div class="text-[11px] font-code-terminal font-bold text-on-surface opacity-0 group-hover:opacity-100 transition-opacity">' + t.count + '</div>' +
              '<div class="w-full max-w-[28px] bg-surface-container rounded-t-lg relative flex flex-col justify-end overflow-hidden" style="height: 110px;">' +
                '<div class="w-full bg-primary-container rounded-t-lg transition-all duration-500 group-hover:brightness-110" style="height: ' + heightPct + '%;"></div>' +
              '</div>' +
              '<div class="text-center">' +
                '<span class="font-code-header text-[11px] uppercase font-bold text-secondary block">' + escapeHTML(t.label) + '</span>' +
                '<span class="font-label-md text-[10px] text-tertiary block">' + scoreBadge + '</span>' +
              '</div>' +
            '</div>'
          );
        }).join("");

        velCont.innerHTML =
          '<div class="w-full flex flex-col justify-between h-full pt-2 pb-1">' +
            '<div class="flex items-end justify-between gap-2 h-40 px-2">' + barsHtml + '</div>' +
            '<div class="flex items-center justify-between pt-3 border-t border-surface-container-high/60 mt-2 text-xs font-code-terminal text-secondary">' +
              '<span>' + escapeHTML(d.trend_label || "Historical Velocity") + '</span>' +
              '<span class="text-on-surface font-semibold">' + totalScraped + ' total scraped • ' + (d.avg_match || 0) + '% avg match</span>' +
            '</div>' +
          '</div>';
      }
    }
  }

  function analyticsFilteredRows() {
    var q = (__analyticsFilter || "").toLowerCase().trim();
    var rows = __analyticsRows;
    if (__analyticsStatusFilter && __analyticsStatusFilter !== "all") {
      rows = rows.filter(function (r) {
        return (r.status || "").toLowerCase() === __analyticsStatusFilter.toLowerCase();
      });
    }
    if (!q) return rows;
    return rows.filter(function (r) {
      return ((r.to_email || "") + " " + (r.company || "") + " " + (r.title || "")).toLowerCase().indexOf(q) !== -1;
    });
  }

  function analyticsStatusPill(status, appId) {
    var s = String(status || "").toLowerCase();
    var badgeClass = "bg-surface-container text-secondary";
    var icon = "";
    if (s === "applied") {
      badgeClass = "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 font-semibold";
      icon = '<span class="material-symbols-outlined text-[14px]">check_circle_3</span>';
    } else if (s === "interviewing") {
      badgeClass = "bg-blue-500/15 text-blue-700 dark:text-blue-400 font-semibold";
      icon = '<span class="material-symbols-outlined text-[14px]">chat_dots</span>';
    } else if (s === "offer") {
      badgeClass = "bg-primary-container text-on-primary-fixed font-bold shadow-xs";
      icon = '<span class="material-symbols-outlined text-[14px]">auto_awesome</span>';
    } else if (s === "rejected") {
      badgeClass = "bg-rose-500/15 text-rose-700 dark:text-rose-400 font-semibold";
      icon = '<span class="material-symbols-outlined text-[14px]">close</span>';
    } else if (s === "sent") {
      badgeClass = "bg-primary-container/30 text-on-primary-fixed";
      icon = '<span class="material-symbols-outlined text-[14px]">chat_check</span>';
    } else if (s === "queued") {
      badgeClass = "bg-surface-container-high text-secondary";
      icon = '<span class="material-symbols-outlined text-[14px]">timer</span>';
    } else if (s === "failed") {
      badgeClass = "bg-error-container text-error";
      icon = '<span class="material-symbols-outlined text-[14px]">octagon_warning</span>';
    }
    var label = (status ? status.charAt(0).toUpperCase() + status.slice(1) : "—");
    if (!appId) {
      return '<span class="px-2.5 py-0.5 rounded-full text-xs font-mono ' + badgeClass + ' w-fit inline-flex items-center gap-1">' + icon + escapeHTML(label) + '</span>';
    }
    return '<button type="button" class="analytics-status-toggle px-2.5 py-0.5 rounded-full text-xs font-mono ' + badgeClass + ' w-fit inline-flex items-center gap-1 cursor-pointer hover:brightness-110 active:scale-95 transition-all select-none" data-app-id="' + escapeHTML(appId) + '" data-status="' + escapeHTML(status || "") + '" title="Click to cycle status (Applied &rarr; Interviewing &rarr; Offer &rarr; Rejected &rarr; Archived)">' + icon + '<span>' + escapeHTML(label) + '</span><span class="material-symbols-outlined text-[12px] opacity-60">unfold_more</span></button>';
  }

  function renderAnalyticsTable() {
    var rows = analyticsFilteredRows();
    var pages = Math.max(1, Math.ceil(rows.length / ANALYTICS_PAGE_SIZE));
    if (__analyticsPage > pages) __analyticsPage = pages;
    var start = (__analyticsPage - 1) * ANALYTICS_PAGE_SIZE;
    var slice = rows.slice(start, start + ANALYTICS_PAGE_SIZE);
    $$("tbody").forEach(function (tb) {
      tb.innerHTML = "";
      if (!slice.length) {
        var tr = document.createElement("tr");
        tr.innerHTML = '<td colspan="6" class="py-space-md px-space-md text-center font-body-sm text-body-sm text-secondary">No application activity recorded yet.</td>';
        tb.appendChild(tr);
      } else {
        slice.forEach(function (r) {
          var contactStr = String(r.to_email || r.company || "?").trim();
          var initial = escapeHTML(contactStr.charAt(0).toUpperCase() || "?");
          var actionHtml = r.link
            ? '<a href="' + escapeHTML(r.link) + '" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-primary hover:underline font-medium text-xs"><span class="material-symbols-outlined text-[14px]">open_in_new</span><span>View</span></a>'
            : (r.app_id
              ? '<a href="/outreach?id=' + encodeURIComponent(r.app_id) + '" class="inline-flex items-center gap-1 text-primary hover:underline font-medium text-xs"><span class="material-symbols-outlined text-[14px]">visibility</span><span>Open</span></a>'
              : '—');
          var tr = document.createElement("tr");
          tr.className = "hover:bg-surface-container-low/40 transition-colors group";
          tr.innerHTML =
            '<td class="py-space-md px-space-md"><div class="flex items-center gap-3">' +
              '<div class="w-8 h-8 rounded-full bg-surface-container-highest text-secondary font-bold flex items-center justify-center font-code-terminal">' + initial + '</div>' +
              '<div><span class="font-label-md text-label-md font-bold text-on-surface block">' + escapeHTML(r.to_email || "—") + '</span>' +
              '<span class="font-body-sm text-body-sm text-secondary">' + escapeHTML(r.company || "") + '</span></div>' +
            '</div></td>' +
            '<td class="py-space-md px-space-md text-on-surface font-medium">' + escapeHTML(r.title || "—") + '</td>' +
            '<td class="py-space-md px-space-md"><span class="font-code-terminal text-code-terminal font-bold text-on-surface">' + (r.match_score || 0) + '%</span></td>' +
            '<td class="py-space-md px-space-md">' + analyticsStatusPill(r.status, r.app_id) + '</td>' +
            '<td class="py-space-md px-space-md font-code-terminal text-code-terminal text-secondary">' + escapeHTML(r.sent_at || "—") + '</td>' +
            '<td class="py-space-md px-space-md text-right font-body-sm text-body-sm">' + actionHtml + '</td>';
          tb.appendChild(tr);
        });
      }

      if (!tb.__statusCycleBound) {
        tb.__statusCycleBound = true;
        tb.addEventListener("click", function (evt) {
          var btn = evt.target.closest(".analytics-status-toggle");
          if (!btn) return;
          var appId = btn.getAttribute("data-app-id");
          var curStatus = (btn.getAttribute("data-status") || "").toLowerCase();
          var cycleMap = {
            "applied": "Interviewing",
            "interviewing": "Offer",
            "offer": "Rejected",
            "rejected": "Archived",
            "archived": "Applied",
            "sent": "Interviewing",
            "queued": "Applied"
          };
          var nextStatus = cycleMap[curStatus] || "Applied";
          btn.disabled = true;
          api("/api/applications/" + encodeURIComponent(appId) + "/status", {
            method: "PATCH",
            body: { status: nextStatus }
          }).then(function () {
            // Update in-memory row
            __analyticsRows.forEach(function (row) {
              if (row.app_id === appId) row.status = nextStatus;
            });
            showToast("Application stage updated to " + nextStatus);
            renderAnalyticsTable();
          }).catch(function (err) {
            showToast("Failed to update status: " + (err.message || err));
          }).finally(function () {
            btn.disabled = false;
          });
        });
      }
    });
    // "Showing X of Y" labels
    $$("span").forEach(function (el) {
      if ((el.textContent || "").indexOf("Showing") === 0) {
        el.textContent = rows.length
          ? "Showing " + (start + 1) + "-" + Math.min(start + ANALYTICS_PAGE_SIZE, rows.length) + " of " + rows.length + " applications"
          : "Showing 0 of 0 applications";
        var controls = el.parentElement ? el.parentElement.querySelector("div:last-child") : null;
        if (controls && controls !== el) renderAnalyticsPager(controls, pages);
      }
    });
  }

  function renderAnalyticsPager(box, pages) {
    box.innerHTML = "";
    function btn(label, page, opts) {
      opts = opts || {};
      var b = document.createElement("button");
      b.type = "button";
      b.className = opts.active
        ? "w-8 h-8 rounded-full bg-primary-container text-on-primary-fixed font-bold font-code-terminal text-[12px] flex items-center justify-center shadow-sm"
        : "w-8 h-8 rounded-full hover:bg-surface-container-highest text-on-surface font-code-terminal text-[12px] flex items-center justify-center transition-colors";
      b.textContent = label;
      if (opts.disabled) { b.disabled = true; b.classList.add("opacity-40"); }
      else b.addEventListener("click", function () { __analyticsPage = page; renderAnalyticsTable(); });
      return b;
    }
    var prev = document.createElement("button");
    prev.type = "button";
    prev.className = "px-3 py-1.5 rounded-full bg-surface-container text-on-surface hover:bg-surface-container-highest transition-colors font-label-md text-label-md flex items-center gap-1";
    prev.innerHTML = '<span class="material-symbols-outlined text-[16px]">chevron_left</span><span>Previous</span>';
    if (__analyticsPage <= 1) { prev.disabled = true; prev.classList.add("opacity-40"); }
    else prev.addEventListener("click", function () { __analyticsPage -= 1; renderAnalyticsTable(); });
    box.appendChild(prev);
    var from = Math.max(1, Math.min(__analyticsPage - 2, pages - 4));
    var to = Math.min(pages, from + 4);
    for (var p = from; p <= to; p++) {
      (function (pg) { box.appendChild(btn(String(pg), pg, { active: pg === __analyticsPage })); })(p);
    }
    var next = document.createElement("button");
    next.type = "button";
    next.className = "px-3 py-1.5 rounded-full bg-surface-container text-on-surface hover:bg-surface-container-highest transition-colors font-label-md text-label-md flex items-center gap-1";
    next.innerHTML = '<span>Next</span><span class="material-symbols-outlined text-[16px]">chevron_right</span>';
    if (__analyticsPage >= pages) { next.disabled = true; next.classList.add("opacity-40"); }
    else next.addEventListener("click", function () { __analyticsPage += 1; renderAnalyticsTable(); });
    box.appendChild(next);
  }
  var __wasScrapingRunning = false;
  function setScrapeStopVisible(visible, st) {
    $$('[id="scrape-stop-btn"]').forEach(function (btn) {
      btn.classList.toggle("hidden", !visible);
      btn.classList.toggle("flex", !!visible);
    });

    var banner = document.getElementById("dashboard-crawler-banner");
    if (banner) {
      banner.classList.toggle("hidden", !visible);
      banner.classList.toggle("flex", !!visible);
    }

    var submitBtn = document.getElementById("submit-btn");
    if (submitBtn) {
      if (visible) {
        if (!submitBtn.__crawling) {
          submitBtn.__crawling = true;
          submitBtn.__prevHTML = submitBtn.innerHTML;
          submitBtn.disabled = true;
          submitBtn.innerHTML = '<span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span><span>Searching in Chrome...</span>';
        }
      } else if (submitBtn.__crawling) {
        submitBtn.__crawling = false;
        submitBtn.disabled = false;
        if (submitBtn.__prevHTML) submitBtn.innerHTML = submitBtn.__prevHTML;
      }
    }

    if (visible && st) {
      var msgEl = document.getElementById("dashboard-crawler-status-msg");
      if (msgEl) {
        var msg = "Chrome active: Searching LinkedIn";
        if (st.target) msg += " for '" + st.target + "'";
        if (st.collected) msg += " • " + st.collected + " leads found";
        msgEl.textContent = msg + "...";
      }
    }

    // Update scan duration card on Matches screen if available
    var scanTimeCard = document.getElementById("matches-scan-time-card");
    var scanTimeText = document.getElementById("matches-scan-time-text");
    if (scanTimeCard && scanTimeText && st) {
      if (st.last_scan_summary) {
        scanTimeCard.classList.remove("hidden");
        scanTimeCard.classList.add("flex");
        scanTimeText.textContent = st.last_scan_summary;
      }
    }

    if (__wasScrapingRunning && !visible) {
      __wasScrapingRunning = false;
      var totalFound = (st && (st.last_collected != null ? st.last_collected : st.collected)) || 0;
      var timeInfo = (st && st.last_scan_summary) ? " (" + st.last_scan_summary + ")" : "";
      showToast("Search finished: " + totalFound + " leads collected." + timeInfo);
      if (typeof bindDashboard === "function") bindDashboard();
      if (typeof bindMatches === "function") bindMatches();
    }
    if (visible) {
      __wasScrapingRunning = true;
    }
  }
  window.setScrapeStopVisible = setScrapeStopVisible;

  var __scrapeApiWarned = false;
  function refreshScrapeStatus() {
    api("/api/scrape/status").then(function (st) {
      __scrapeApiWarned = false;
      setScrapeStopVisible(!!(st && st.running), st);
    }).catch(function (err) {
      var msg = String((err && err.message) || "");
      if (msg.indexOf("404") !== -1 && !__scrapeApiWarned) {
        __scrapeApiWarned = true;
        showToast("Server is outdated — restart it (launch.bat) to enable the Stop button.");
      }
    });
  }

  function bindScrapeStop() {
    var btns = $$('[id="scrape-stop-btn"], [id="dashboard-crawler-stop-btn"]');
    if (!btns.length) return;
    btns.forEach(function (btn) {
      if (btn.__stopBound) return;
      btn.__stopBound = true;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        btn.disabled = true;
        api("/api/scrape/stop", { method: "POST", body: {} })
          .then(function (res) {
            showToast((res && res.message) || "Stop requested.");
            setScrapeStopVisible(false);
          })
          .catch(function (err) {
            showToast("Stop failed: " + err.message);
            refreshScrapeStatus();
          })
          .then(function () { btn.disabled = false; });
      });
    });
    refreshScrapeStatus();
    setInterval(refreshScrapeStatus, 3000);
  }

  // ---------------------------------------------------------------------------
  // Resume upload / delete (Profile)
  // ---------------------------------------------------------------------------
  function bindResumeUpload() {
    var input = document.getElementById("resume-file-input");
    if (!input) return;
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;

      var dropzone = document.getElementById("dropzone");
      var scanningState = document.getElementById("resume-scanning-state");
      var scanStage = document.getElementById("resume-scanning-stage");
      var scanBar = document.getElementById("resume-scanning-progress-bar");
      var scanSub = document.getElementById("resume-scanning-subtext");

      if (dropzone && scanningState) {
        dropzone.classList.add("hidden");
        scanningState.classList.remove("hidden");
        if (scanBar) scanBar.style.width = "25%";
        if (scanStage) scanStage.textContent = "Uploading & reading document structure...";
      } else {
        showToast("Uploading " + file.name + " ...");
      }

      var stageTimer1 = setTimeout(function () {
        if (scanBar) scanBar.style.width = "60%";
        if (scanStage) scanStage.textContent = "Extracting competencies, target role & work timeline...";
        if (scanSub) scanSub.textContent = "Calculating years of experience & seniority bracket...";
      }, 1000);

      var stageTimer2 = setTimeout(function () {
        if (scanBar) scanBar.style.width = "85%";
        if (scanStage) scanStage.textContent = "Calibrating ChromaDB semantic embedding model...";
        if (scanSub) scanSub.textContent = "Generating 384-dimensional vector representation...";
      }, 2300);

      var fd = new FormData();
      fd.append("file", file);
      fetch("/api/upload-resume", { method: "POST", body: fd })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          clearTimeout(stageTimer1);
          clearTimeout(stageTimer2);
          if (data && data.status === "success") {
            if (scanBar) scanBar.style.width = "100%";
            if (scanStage) scanStage.textContent = "Resume parsed & vectorized successfully!";
            showToast("Resume parsed and indexed.");
            setTimeout(function () {
              navigateTo("profile");
            }, 850);
          } else {
            if (dropzone && scanningState) {
              scanningState.classList.add("hidden");
              dropzone.classList.remove("hidden");
            }
            showToast("Upload failed: " + ((data && data.detail) || "unknown error"));
          }
        })
        .catch(function (err) {
          clearTimeout(stageTimer1);
          clearTimeout(stageTimer2);
          if (dropzone && scanningState) {
            scanningState.classList.add("hidden");
            dropzone.classList.remove("hidden");
          }
          showToast("Upload failed: " + err.message);
        });
    });
  }

  function bindDeleteResume() {
    var btn = document.getElementById("delete-resume-btn");
    if (!btn) return;
    btn.addEventListener("click", function () {
      api("/api/resume-meta")
        .then(function (meta) {
          var filename = meta && meta.resume && meta.resume.filename;
          if (!filename) return;
          return api("/api/resume/" + encodeURIComponent(filename), { method: "DELETE" });
        })
        .then(function () {
          showToast("Resume removed.");
          var pill = document.getElementById("attached-file-pill");
          if (pill) pill.classList.add("hidden");
          var dropzone = document.getElementById("dropzone");
          if (dropzone) dropzone.classList.remove("hidden");
          var fileInput = document.getElementById("resume-file-input");
          if (fileInput) fileInput.value = "";
          setTimeout(function () {
            navigateTo("profile");
          }, 800);
        })
        .catch(function (err) {
          showToast("Delete failed: " + err.message);
        });
    });
  }

  function bindGmailButtons() {
    // "Authorize Gmail" / "Connect Gmail" buttons jump to the Email card.
    $$('[id="connect-gmail-btn"]').forEach(function (btn) {
      if (btn.__gmailBound) return;
      btn.__gmailBound = true;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        navigateTo("settings#email-card");
      });
    });
    // Honor #section hashes after full-page navigation.
    try {
      if (window.location.hash && window.location.hash.length > 1) {
        scrollToSection(window.location.hash.slice(1));
      }
    } catch (err) {}
  }

  function bindProfileUI() {
    // Download active resume button
    var dlBtn = document.getElementById("download-resume-btn");
    if (dlBtn && !dlBtn.__bound) {
      dlBtn.__bound = true;
      dlBtn.addEventListener("click", function () {
        api("/api/resume-meta").then(function (meta) {
          var fn = meta && meta.resume && meta.resume.filename;
          if (fn) {
            showToast("Downloading " + fn + "...");
            window.location.href = "/api/resume/" + encodeURIComponent(fn);
          } else {
            showToast("No resume file available to download.");
          }
        }).catch(function () {
          showToast("Download failed.");
        });
      });
    }

    // Manual skill addition form
    var addSkillBtn = document.getElementById("add-skill-btn");
    var manualForm = document.getElementById("manual-skill-form");
    var skillInput = document.getElementById("manual-skill-input");
    var saveSkillBtn = document.getElementById("save-skill-btn");
    var cancelSkillBtn = document.getElementById("cancel-skill-btn");
    var chipsContainer = document.getElementById("profile-skill-chips");

    if (addSkillBtn && manualForm) {
      addSkillBtn.addEventListener("click", function () {
        manualForm.classList.toggle("hidden");
        if (!manualForm.classList.contains("hidden") && skillInput) {
          skillInput.focus();
        }
      });
    }

    if (cancelSkillBtn && manualForm) {
      cancelSkillBtn.addEventListener("click", function () {
        manualForm.classList.add("hidden");
        if (skillInput) skillInput.value = "";
      });
    }

    function syncProfileCustomSkills() {
      var chipsEl = document.getElementById("profile-skill-chips");
      if (!chipsEl) return;
      var currentSkills = Array.from(chipsEl.querySelectorAll("span:nth-child(2)")).map(function (span) {
        return span.textContent.trim();
      }).filter(Boolean);
      api("/api/profile/preferences", {
        method: "POST",
        body: { custom_skills: currentSkills }
      }).catch(function () {});
    }

    function addManualSkill() {
      if (!skillInput) return;
      var text = (skillInput.value || "").trim();
      if (!text) {
        showToast("Please enter a skill name.");
        skillInput.classList.add("ring-2", "ring-error");
        setTimeout(function () { skillInput.classList.remove("ring-2", "ring-error"); }, 1800);
        return;
      }
      var existing = Array.from(chipsContainer ? chipsContainer.querySelectorAll("span:nth-child(2)") : []).map(function (s) { return s.textContent.trim().toLowerCase(); });
      if (existing.indexOf(text.toLowerCase()) !== -1) {
        showToast("Skill '" + text + "' is already in your profile list.");
        skillInput.classList.add("ring-2", "ring-error");
        setTimeout(function () { skillInput.classList.remove("ring-2", "ring-error"); }, 1800);
        return;
      }

      var chip = document.createElement("span");
      chip.className = "px-space-md py-1.5 bg-surface-container-high text-on-surface font-label-md text-label-md rounded-full flex items-center gap-1.5 transition-all";
      chip.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-primary"></span><span>' + escapeHTML(text) + '</span><span class="material-symbols-outlined text-[14px] text-tertiary hover:text-error cursor-pointer ml-1 remove-skill-icon">close</span>';
      chip.querySelector(".remove-skill-icon").addEventListener("click", function () {
        chip.remove();
        showToast("Removed " + text);
        syncProfileCustomSkills();
      });
      if (chipsContainer) chipsContainer.appendChild(chip);
      skillInput.value = "";
      manualForm.classList.add("hidden");
      showToast("Added " + text + " to profile skills");
      syncProfileCustomSkills();
    }

    if (saveSkillBtn) {
      saveSkillBtn.addEventListener("click", addManualSkill);
    }
    if (skillInput) {
      skillInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          addManualSkill();
        }
      });
    }

    // Eye toggle - delegated for all states (guarded against duplicate listeners)
    if (!document.__pwdEyeBound) {
      document.__pwdEyeBound = true;
      document.addEventListener("click", function(e){
        var btn = e.target.closest('#toggle-pwd-btn, #toggle-ai-key-btn, .toggle-pwd-btn');
        if(!btn) return;
        e.preventDefault();
        var wrapper = btn.closest(".flex") || btn.parentElement;
        var input = wrapper ? wrapper.querySelector("input") : null;
        if(!input) input = document.getElementById("ai-api-key") || document.getElementById("smtp-password") || document.getElementById("passkey-input");
        if(!input) return;
        var isPwd = input.type === "password";
        input.type = isPwd ? "text" : "password";
        var icon = btn.querySelector(".material-symbols-outlined");
        if(icon){ var vg = isPwd ? "visibility_off" : "visibility"; if (window.setXIcon) window.setXIcon(icon, vg); else icon.textContent = vg; }
      });
    }
    // Save profile / settings credentials - per-card validation
    var saveBtns = $$('[id="save-settings-btn"], [id="save-credentials-btn"]');
    saveBtns.forEach(function(btn){
      btn.addEventListener("click", function(){
        var card = btn.closest(".bg-surface-container-lowest");
        var emailInput = card ? (card.querySelector('#sender-email') || card.querySelector('input[type="email"]')) : (document.getElementById("sender-email") || document.getElementById("profile-email"));
        var pwdInput = card ? (card.querySelector('#smtp-password') || card.querySelector('input[type="password"]')) : (document.getElementById("smtp-password") || document.getElementById("passkey-input"));
        clearCardError("email-card");
        clearCardError("profile-card");

        var payload = {};
        if (emailInput && emailInput.value.trim()) {
          payload.SENDER_EMAIL = emailInput.value.trim();
          payload.SMTP_USER = emailInput.value.trim();
        }
        if (pwdInput && pwdInput.value.trim()) {
          payload.SMTP_PASSWORD = pwdInput.value.trim().replace(/\s+/g, "");
          pwdInput.value = payload.SMTP_PASSWORD;
        }

        var nameInput = document.getElementById("sender-name");
        if (nameInput && nameInput.value.trim()) payload.SENDER_NAME = nameInput.value.trim();
        var hostInput = document.getElementById("smtp-host");
        if (hostInput && hostInput.value.trim()) payload.SMTP_HOST = hostInput.value.trim();
        var portInput = document.getElementById("smtp-port");
        if (portInput && portInput.value.trim()) payload.SMTP_PORT = portInput.value.trim();
        var userInput = document.getElementById("smtp-user");
        if (userInput && userInput.value.trim()) payload.SMTP_USER = userInput.value.trim();
        var capInput = document.getElementById("send-daily-cap");
        if (capInput && capInput.value.trim()) payload.AI_SEND_DAILY_CAP = capInput.value.trim();
        var intInput = document.getElementById("send-interval-sec");
        if (intInput && intInput.value.trim()) payload.AI_SEND_INTERVAL_SEC = intInput.value.trim();

        if (Object.keys(payload).length > 0) {
          api("/api/settings", { method: "POST", body: payload })
            .then(function () {
              showToast("Email credentials saved securely.");
              updateEmailStatusPill("active", "Configured");
            })
            .catch(function () {
              showToast("Credentials saved locally.");
            });
        } else {
          showToast("Please provide your email address and App Password.");
        }
      });
    });
    // Ensure profile card has id for per-card error
    var firstCard = document.querySelector(".bg-surface-container-lowest");
    if(firstCard && !document.getElementById("profile-card")){
      // Find the Account & Credentials card
      var cards = $$(".bg-surface-container-lowest");
      for(var i=0;i<cards.length;i++){
        if(cards[i].textContent.indexOf("Account & Credentials")!==-1){
          cards[i].id = "profile-card";
          break;
        }
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Profile success screen — render the scanned resume's extracted data
  // ---------------------------------------------------------------------------
  function initialsFor(name) {
    var parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  // ---------------------------------------------------------------------------
  // Resume upload / delete / multi-resume management (Profile)
  // ---------------------------------------------------------------------------
  function bindResumeUpload() {
    var input = document.getElementById("resume-file-input");
    if (!input) return;
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;

      var scanningState = document.getElementById("resume-scanning-state");
      var scanStage = document.getElementById("resume-scanning-stage");
      var scanBar = document.getElementById("resume-scanning-progress-bar");
      var scanSub = document.getElementById("resume-scanning-subtext");
      var dropzoneWrapper = document.getElementById("dropzone-wrapper");

      var roleTagInput = document.getElementById("resume-role-tag-input");
      var roleTagValue = (roleTagInput && roleTagInput.value.trim()) || "";

      if (dropzoneWrapper && scanningState) {
        dropzoneWrapper.classList.add("hidden");
        scanningState.classList.remove("hidden");
        if (scanBar) scanBar.style.width = "25%";
        if (scanStage) scanStage.textContent = "Uploading & reading document structure...";
      } else {
        showToast("Uploading " + file.name + " ...");
      }

      var stageTimer1 = setTimeout(function () {
        if (scanBar) scanBar.style.width = "60%";
        if (scanStage) scanStage.textContent = "Extracting competencies, target role & work timeline...";
        if (scanSub) scanSub.textContent = "Calculating years of experience & seniority bracket...";
      }, 1000);

      var stageTimer2 = setTimeout(function () {
        if (scanBar) scanBar.style.width = "85%";
        if (scanStage) scanStage.textContent = "Calibrating ChromaDB semantic embedding model...";
        if (scanSub) scanSub.textContent = "Generating 384-dimensional vector representation...";
      }, 2300);

      var fd = new FormData();
      fd.append("file", file);
      if (roleTagValue) {
        fd.append("role_tag", roleTagValue);
      }
      fetch("/api/upload-resume", { method: "POST", body: fd })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          clearTimeout(stageTimer1);
          clearTimeout(stageTimer2);
          if (data && data.status === "success") {
            if (scanBar) scanBar.style.width = "100%";
            if (scanStage) scanStage.textContent = "Resume parsed & vectorized successfully!";
            showToast("Resume parsed and indexed.");
            if (roleTagInput) roleTagInput.value = "";
            setTimeout(function () {
              navigateTo("profile");
            }, 850);
          } else {
            if (dropzoneWrapper && scanningState) {
              scanningState.classList.add("hidden");
              dropzoneWrapper.classList.remove("hidden");
            }
            showToast("Upload failed: " + ((data && data.detail) || "unknown error"));
          }
        })
        .catch(function (err) {
          clearTimeout(stageTimer1);
          clearTimeout(stageTimer2);
          if (dropzoneWrapper && scanningState) {
            scanningState.classList.add("hidden");
            dropzoneWrapper.classList.remove("hidden");
          }
          showToast("Upload failed: " + err.message);
        });
    });
  }

  function bindDeleteResume() {
    // Retained for backward compatibility
  }

  function bindGmailButtons() {
    // "Authorize Gmail" / "Connect Gmail" buttons jump to the Email card.
    $$('[id="connect-gmail-btn"]').forEach(function (btn) {
      if (btn.__gmailBound) return;
      btn.__gmailBound = true;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        navigateTo("settings#email-card");
      });
    });
    // Honor #section hashes after full-page navigation.
    try {
      if (window.location.hash && window.location.hash.length > 1) {
        scrollToSection(window.location.hash.slice(1));
      }
    } catch (err) {}
  }

  function renderResumeModelDetails(r) {
    if (!r) return;
    var setText = function (id, text) {
      var el = getEl(id);
      if (el && text !== undefined && text !== null) {
        if (el.tagName === 'INPUT') { el.value = text; }
        else { el.textContent = text; }
      }
    };

    setText("profile-resume-filename", r.filename || "Resume");
    var dlA = getEl("download-resume-btn");
    if (dlA && dlA.tagName === "A" && r.filename) {
      dlA.setAttribute("href", "/api/resume/" + encodeURIComponent(r.filename));
    }

    var stats = [];
    if (r.size_label) stats.push(r.size_label);
    if (r.words) stats.push(r.words + " words");
    if (r.pages) stats.push(r.pages + (r.pages === 1 ? " page" : " pages"));
    if (typeof r.skill_count === "number") {
      stats.push(r.skill_count + " skills");
    }
    if (stats.length) setText("resume-stats-line", stats.join(" \u2022 "));

    setText("profile-card-sub", "Parsed competencies, seniority qualification, and primary skills");

    if (r.name) {
      setText("profile-name", r.name);
      var avEl = getEl("profile-avatar");
      if (avEl) {
        avEl.textContent = initialsFor(r.name);
        avEl.className = "w-16 h-16 rounded-2xl bg-primary-container text-on-primary-fixed flex items-center justify-center font-headline-lg font-bold shadow-md shrink-0";
      }
    } else {
      setText("profile-name", r.filename || "Candidate Profile");
      var avEl = getEl("profile-avatar");
      if (avEl) {
        avEl.innerHTML = '<span class="material-symbols-outlined text-[32px]">person</span>';
        avEl.className = "w-16 h-16 rounded-2xl bg-primary-container text-on-primary-fixed flex items-center justify-center font-headline-lg font-bold shadow-md shrink-0";
      }
    }
    if (r.headline) {
      setText("profile-headline", r.headline);
      setText("profile-target-roles", "Targeting: " + r.headline);
    } else {
      setText("profile-headline", (r.skill_count ? r.skill_count + " verified skills" : "Parsed resume") + (r.words ? " \u2022 " + r.words + " words extracted" : ""));
    }

    var emailEl = getEl("profile-email");
    if (emailEl && r.email) emailEl.value = r.email;

    setText("profile-yoe", r.yoe || "Active");
    setText("profile-yoe-sub", r.yoe_sub || "Mid-Level Professional");
    var roleLabel = r.role_tag || r.target_role || "Target Role";
    var extraCount = (r.target_roles && r.target_roles.length > 1) ? " (+" + (r.target_roles.length - 1) + ")" : "";
    var roleEl = getEl("profile-salary");
    if (roleEl) {
      roleEl.innerHTML = escapeHTML(roleLabel) + (extraCount ? ' <span class="font-normal text-body-sm text-secondary tracking-normal">' + extraCount + '</span>' : '');
    }
    setText("profile-salary-sub", r.target_roles && r.target_roles.length > 1 ? r.target_roles.slice(0, 3).join(", ") : (r.target_role ? "Configured Target Role" : (r.headline || "Ingested Profile")));
    setText("profile-match-vector", r.vector_status || "Calibrated");
    setText("profile-match-vector-sub", r.vector_description || "Vector embeddings indexed in ChromaDB for high-precision semantic matching.");

    var chips = getEl("profile-skill-chips");
    if (r.skills && r.skills.length) {
      if (chips) {
        chips.innerHTML = "";
        r.skills.forEach(function (s) {
          var chip = document.createElement("span");
          chip.className = "px-space-md py-1.5 bg-surface-container-high text-on-surface font-label-md text-label-md rounded-full flex items-center gap-1.5 transition-all";
          chip.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-primary"></span><span>' + escapeHTML(s) + '</span><span class="material-symbols-outlined text-[14px] text-tertiary hover:text-error cursor-pointer ml-1 remove-skill-icon">close</span>';
          chip.querySelector(".remove-skill-icon").addEventListener("click", function () {
            chip.remove();
            showToast("Removed " + s);
            syncProfileCustomSkills();
          });
          chips.appendChild(chip);
        });
      }
    }
  }

  function bindProfile() {
    var listContainer = getEl("resumes-list-container");
    var countBadge = getEl("resumes-count-badge");
    var emptyState = getEl("resumes-empty-state");
    var statusBadge = getEl("resume-status-badge");
    var statusText = getEl("resume-status-text");

    // Fetch full multi-resume list from backend
    api("/api/resumes")
      .then(function (res) {
        var resumes = (res && res.resumes) || [];
        if (countBadge) {
          countBadge.textContent = resumes.length + (resumes.length === 1 ? " resume" : " resumes");
        }

        if (resumes.length === 0) {
          if (listContainer) listContainer.innerHTML = "";
          if (emptyState) emptyState.classList.remove("hidden");
          if (statusBadge) {
            statusBadge.className = "status-pill status-pill-inactive";
            if (statusText) statusText.textContent = "No Resume";
          }
          var subEl0 = getEl("profile-card-sub");
          if (subEl0) subEl0.textContent = "Upload resume to view all information";

          setText("profile-name", "No Resume Uploaded");
          setText("profile-headline", "Upload your resume to view all information and calibrate AI matching");
          setText("profile-target-roles", "Targeting: Configure your target roles below");

          var avEl0 = getEl("profile-avatar");
          if (avEl0) {
            avEl0.innerHTML = '<span class="material-symbols-outlined text-[32px]">person</span>';
            avEl0.className = "w-16 h-16 rounded-2xl bg-surface-container-high text-secondary flex items-center justify-center font-headline-lg font-bold shrink-0";
          }

          var chips0 = getEl("profile-skill-chips");
          if (chips0) {
            chips0.innerHTML = '<div class="p-space-md w-full rounded-xl bg-surface-container/40 border border-dashed border-surface-container-high text-center text-body-sm text-secondary">Upload resume to view all information and extracted competencies, or click <strong class="text-on-surface">Add Keyword Manually</strong> above.</div>';
          }

          var compText0 = getEl("profile-completeness-text");
          if (compText0) compText0.textContent = "0% • Awaiting Resume";
          var bar0 = getEl("profile-completeness-bar");
          if (bar0) bar0.style.width = "0%";
          var vecBadge0 = getEl("profile-match-vector-badge");
          if (vecBadge0) {
            vecBadge0.className = "status-pill status-pill-inactive";
            vecBadge0.innerHTML = '<span class="status-pill-dot"></span><span class="status-pill-text">Standby</span>';
          }
          return;
        }

        if (emptyState) emptyState.classList.add("hidden");
        if (statusBadge) {
          statusBadge.className = "status-pill status-pill-active";
          if (statusText) statusText.textContent = "Repository Ready";
        }
        var compText = getEl("profile-completeness-text");
        if (compText) compText.innerHTML = '<span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>100% Calibrated';
        var compBar = getEl("profile-completeness-bar");
        if (compBar) compBar.style.width = "100%";
        var vecBadge = getEl("profile-match-vector-badge");
        if (vecBadge) {
          vecBadge.className = "status-pill status-pill-active";
          vecBadge.innerHTML = '<span class="status-pill-dot"></span><span class="status-pill-text">Calibrated</span>';
        }

        // Identify primary resume or default to first
        var primaryResume = resumes.find(function (r) { return r.is_primary; }) || resumes[0];
        renderResumeModelDetails(primaryResume);

        if (listContainer) {
          listContainer.innerHTML = "";
          resumes.forEach(function (r) {
            var card = document.createElement("div");
            card.className = "flex flex-col sm:flex-row items-start sm:items-center justify-between p- space-md p-4 bg-surface-container-low hover:bg-surface-container transition-all rounded-2xl gap-3 border " + (r.is_primary ? "border-primary/50 shadow-xs" : "border-surface-container-high/60");

            var ext = (r.filename || "").split(".").pop().toUpperCase();
            var iconName = ext === "PDF" ? "picture_as_pdf" : (ext === "DOCX" ? "article" : "description");

            var roleTagHtml = r.role_tag
              ? '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-primary-container text-on-primary-fixed font-label-sm text-[12px] font-bold"><span class="material-symbols-outlined text-[13px]">workspace_premium</span>' + escapeHTML(r.role_tag) + '</span>'
              : '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-surface-container text-secondary font-label-sm text-[12px] font-medium"><span class="material-symbols-outlined text-[13px]">label</span>General Role</span>';

            var primaryBadgeHtml = r.is_primary
              ? '<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary text-on-primary font-code-terminal text-[11px] font-bold shadow-xs"><span class="material-symbols-outlined text-[12px]">star</span>PRIMARY DEFAULT</span>'
              : '';

            var statsLine = [
              r.size_label || "",
              r.words ? r.words + " words" : "",
              r.pages ? r.pages + (r.pages === 1 ? " pg" : " pgs") : "",
              r.skill_count ? r.skill_count + " skills" : ""
            ].filter(Boolean).join(" • ");

            card.innerHTML = [
              '<div class="flex items-start gap-3 min-w-0 flex-1">',
              '  <div class="w-11 h-11 rounded-xl bg-surface-container flex items-center justify-center text-primary shrink-0 border border-surface-container-high/60">',
              '    <span class="material-symbols-outlined text-[22px]">' + iconName + '</span>',
              '  </div>',
              '  <div class="flex flex-col min-w-0 flex-1">',
              '    <div class="flex items-center gap-2 flex-wrap">',
              '      <span class="font-label-md text-label-md font-bold text-on-surface truncate" title="' + escapeHTML(r.filename) + '">' + escapeHTML(r.filename) + '</span>',
              '      ' + primaryBadgeHtml,
              '      ' + roleTagHtml,
              '    </div>',
              '    <span class="font-body-sm text-[12px] text-secondary truncate mt-0.5">' + (statsLine || "Vectorized resume document") + '</span>',
              '  </div>',
              '</div>',
              '<div class="flex items-center gap-1.5 shrink-0 self-end sm:self-auto flex-wrap">',
              (r.is_primary
                ? ''
                : '  <button type="button" class="btn-make-primary inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-highest text-on-surface font-label-md text-label-md font-semibold transition-all cursor-pointer" title="Set as primary default resume"><span class="material-symbols-outlined text-[15px]">grade</span><span>Set Primary</span></button>'),
              '  <button type="button" class="btn-preview-model inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-highest text-on-surface font-label-md text-label-md font-semibold transition-all cursor-pointer" title="Preview candidate profile and skills"><span class="material-symbols-outlined text-[15px]">visibility</span><span>Inspect</span></button>',
              '  <button type="button" class="btn-edit-tag inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-highest text-on-surface font-label-md text-label-md font-semibold transition-all cursor-pointer" title="Edit role specialization"><span class="material-symbols-outlined text-[15px]">edit</span><span>Tag</span></button>',
              '  <a href="/api/resume/' + encodeURIComponent(r.filename) + '" target="_blank" class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-highest text-on-surface font-label-md text-label-md font-semibold transition-all shadow-xs"><span class="material-symbols-outlined text-[15px]">download</span></a>',
              '  <button type="button" class="btn-delete-resume inline-flex items-center justify-center w-8 h-8 rounded-full text-error hover:bg-error-container/40 transition-all cursor-pointer" title="Delete this resume"><span class="material-symbols-outlined text-[16px]">delete</span></button>',
              '</div>'
            ].join("");

            // Wire Make Primary
            var makePrimaryBtn = card.querySelector(".btn-make-primary");
            if (makePrimaryBtn) {
              makePrimaryBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                api("/api/resumes/primary", {
                  method: "POST",
                  body: { filename: r.filename }
                }).then(function () {
                  showToast("Set " + r.filename + " as primary resume.");
                  bindProfile();
                }).catch(function (err) {
                  showToast("Error: " + err.message);
                });
              });
            }

            // Wire Preview Model
            var previewBtn = card.querySelector(".btn-preview-model");
            if (previewBtn) {
              previewBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                renderResumeModelDetails(r);
                showToast("Viewing profile for " + (r.role_tag || r.filename));
              });
            }

            // Wire Edit Tag
            var editTagBtn = card.querySelector(".btn-edit-tag");
            if (editTagBtn) {
              editTagBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                var newTag = window.prompt("Enter role specialization tag (e.g. UX Designer, Product Lead):", r.role_tag || "");
                if (newTag !== null) {
                  api("/api/resumes/tag", {
                    method: "POST",
                    body: { filename: r.filename, role_tag: newTag.trim() }
                  }).then(function () {
                    showToast("Updated role tag.");
                    bindProfile();
                  }).catch(function (err) {
                    showToast("Error: " + err.message);
                  });
                }
              });
            }

            // Wire Delete
            var delBtn = card.querySelector(".btn-delete-resume");
            if (delBtn) {
              delBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                if (!window.confirm("Are you sure you want to remove " + r.filename + "?")) return;
                api("/api/resume/" + encodeURIComponent(r.filename), { method: "DELETE" })
                  .then(function () {
                    showToast("Resume removed.");
                    bindProfile();
                  })
                  .catch(function (err) {
                    showToast("Delete failed: " + err.message);
                  });
              });
            }

            listContainer.appendChild(card);
          });
        }

        // Load and populate Target Role & Seniority Preferences
        loadProfilePreferences();
        setupProfilePreferencesEvents();
      })
      .catch(function (err) {
        showToast("Could not load resumes: " + err.message);
      });
  }

  function loadProfilePreferences() {
    api("/api/profile/preferences").then(function (res) {
      if (!res || !res.preferences) return;
      var p = res.preferences;

      if (Array.isArray(p.custom_skills) && p.custom_skills.length) {
        var chipsContainer = getEl("profile-skill-chips");
        if (chipsContainer) {
          var existing = Array.from(chipsContainer.querySelectorAll("span:nth-child(2)")).map(function (s) { return s.textContent.trim().toLowerCase(); });
          p.custom_skills.forEach(function (s) {
            if (existing.indexOf(s.toLowerCase()) === -1) {
              var chip = document.createElement("span");
              chip.className = "px-space-md py-1.5 bg-surface-container-high text-on-surface font-label-md text-label-md rounded-full flex items-center gap-1.5 transition-all";
              chip.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-primary"></span><span>' + escapeHTML(s) + '</span><span class="material-symbols-outlined text-[14px] text-tertiary hover:text-error cursor-pointer ml-1 remove-skill-icon">close</span>';
              chip.querySelector(".remove-skill-icon").addEventListener("click", function () {
                chip.remove();
                showToast("Removed " + s);
                syncProfileCustomSkills();
              });
              chipsContainer.appendChild(chip);
              existing.push(s.toLowerCase());
            }
          });
        }
      }

      var roleInput = getEl("pref-target-role");
      if (roleInput) {
        if (Array.isArray(p.target_roles) && p.target_roles.length) {
          roleInput.value = p.target_roles.join(", ");
        } else if (p.target_role) {
          roleInput.value = p.target_role;
        }
      }
      var locInput = getEl("pref-target-locations");
      if (locInput) {
        if (Array.isArray(p.target_locations) && p.target_locations.length) {
          locInput.value = p.target_locations.join(", ");
        } else if (p.target_locations) {
          locInput.value = p.target_locations;
        }
      }
      var senSelect = getEl("pref-target-seniority");
      if (senSelect && p.target_seniority) {
        senSelect.value = p.target_seniority;
        senSelect.dispatchEvent(new Event("change"));
      }
      var maxInput = getEl("pref-max-yoe");
      if (maxInput && p.max_yoe !== undefined) maxInput.value = p.max_yoe;
      var domInput = getEl("pref-domain-keywords");
      if (domInput && p.domain_keywords) {
        domInput.value = Array.isArray(p.domain_keywords) ? p.domain_keywords.join(", ") : p.domain_keywords;
      }
      var excInput = getEl("pref-exclude-keywords");
      if (excInput && p.exclude_keywords) {
        excInput.value = Array.isArray(p.exclude_keywords) ? p.exclude_keywords.join(", ") : p.exclude_keywords;
      }

      // Update dashboard active criteria preview badge if present
      var dashPreview = getEl("dashboard-criteria-text");
      if (dashPreview) {
        var hasRoles = Array.isArray(p.target_roles) && p.target_roles.length > 0;
        var hasRole = Boolean(p.target_role && p.target_role.trim());
        var isConfigured = Boolean(p.has_profile || hasRoles || hasRole || (p.max_yoe != null && p.max_yoe > 0));

        if (!isConfigured) {
          dashPreview.textContent = "No resume uploaded • Add resume on Profile to customize";
        } else {
          var roleDesc = hasRoles ? p.target_roles[0] : (p.target_role || "Any Role");
          var locDesc = (p.target_locations && p.target_locations.length) ? p.target_locations[0] : "Remote";
          var yoeDesc = (p.max_yoe != null && p.max_yoe > 0) ? " • Max " + p.max_yoe + " YOE" : "";
          dashPreview.textContent = roleDesc + " • " + locDesc + yoeDesc;
        }
      }
    }).catch(function () {});
  }

  function setupProfilePreferencesEvents() {
    var saveBtn = getEl("save-profile-prefs-btn");
    if (!saveBtn || saveBtn._hasListener) return;
    saveBtn._hasListener = true;
    saveBtn.addEventListener("click", function () {
      var roleInput = getEl("pref-target-role");
      var locInput = getEl("pref-target-locations");
      var senSelect = getEl("pref-target-seniority");
      var maxInput = getEl("pref-max-yoe");
      var domInput = getEl("pref-domain-keywords");
      var excInput = getEl("pref-exclude-keywords");

      var rawRoles = roleInput && roleInput.value ? roleInput.value.split(",").map(function(s){return s.trim();}).filter(Boolean) : [];
      var rawLocs = locInput && locInput.value ? locInput.value.split(",").map(function(s){return s.trim();}).filter(Boolean) : [];
      var skillChips = Array.from(document.querySelectorAll("#profile-skill-chips span:nth-child(2)")).map(function(s){return s.textContent.trim();}).filter(Boolean);

      var payload = {
        target_role: rawRoles.length ? rawRoles[0] : "",
        target_roles: rawRoles,
        target_locations: rawLocs,
        target_seniority: senSelect ? senSelect.value : "",
        max_yoe: maxInput ? parseInt(maxInput.value, 10) || 3 : 3,
        domain_keywords: domInput && domInput.value ? domInput.value.split(",").map(function(s){return s.trim();}).filter(Boolean) : [],
        exclude_keywords: excInput && excInput.value ? excInput.value.split(",").map(function(s){return s.trim();}).filter(Boolean) : [],
        custom_skills: skillChips
      };

      saveBtn.disabled = true;
      saveBtn.innerHTML = '<span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span><span>Saving...</span>';

      api("/api/profile/preferences", {
        method: "POST",
        body: payload
      }).then(function (resp) {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<span>Save Target Criteria</span>';
        var toast = getEl("pref-save-toast");
        if (toast) {
          toast.classList.remove("hidden");
          setTimeout(function () { toast.classList.add("hidden"); }, 3500);
        }
        showToast("Target criteria saved successfully!");
        bindProfile();
      }).catch(function (err) {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<span>Save Target Criteria</span>';
        showToast("Error saving preferences: " + (err.message || err));
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Settings (load + save) — id mapped onto the supported ENV keys
  // ---------------------------------------------------------------------------
  var ENV_INPUT_IDS = {
    "profile-email": "SENDER_EMAIL",
    "passkey-input": "SMTP_PASSWORD",
    "sender-email": "SENDER_EMAIL",
    "sender-name": "SENDER_NAME",
    "smtp-host": "SMTP_HOST",
    "smtp-port": "SMTP_PORT",
    "smtp-user": "SMTP_USER",
    "smtp-password": "SMTP_PASSWORD",
    "send-daily-cap": "AI_SEND_DAILY_CAP",
    "send-interval-sec": "AI_SEND_INTERVAL_SEC",
    "ai-provider": "AI_PROVIDER",
    "ai-base-url": "AI_BASE_URL",
    "ai-api-key": "AI_API_KEY",
    "ai-model": "AI_MODEL",
    "ai-model-scoring": "AI_MODEL_SCORING",
    "ai-model-drafts": "AI_MODEL_DRAFTS",
    "prompt-extraction": "SYSTEM_PROMPT_EXTRACTION",
    "prompt-scoring": "SYSTEM_PROMPT_SCORING",
    "prompt-email": "SYSTEM_PROMPT_EMAIL"
  };

  // Legacy keys still read for display; saves always write canonical AI_*.
  var LEGACY_ENV_IDS = {
    "ai-base-url": "OMNIROUTE_BASE_URL",
    "ai-api-key": "OMNIROUTE_API_KEY",
    "ai-model": "CLAUDE_MODEL"
  };

  var AI_PRESETS = {
    openrouter: { base: "https://openrouter.ai/api/v1", model: "", requiresKey: true },
    omniroute: { base: "http://localhost:8000/v1", model: "", requiresKey: true },
    openai: { base: "https://api.openai.com/v1", model: "", requiresKey: true },
    ollama: { base: "http://localhost:11434/v1", model: "", requiresKey: false },
    custom: { base: "", model: "", requiresKey: false },
  };

  function setGatewayStatus(state, text) {
    var pill = document.getElementById("ai-gateway-status");
    if (!pill) return;
    var ok = state === "connected";
    var isErr = state === "error";
    var isWarn = state === "testing" || text === "TESTING...";
    var label = ok ? "Connected" : isErr ? (text === "MISSING_FIELDS" ? "Missing Key" : "Error") : isWarn ? "Testing..." : "Not Connected";

    pill.className = "status-pill " + (ok ? "status-pill-active" : isErr ? "status-pill-error" : isWarn ? "status-pill-warning" : "status-pill-inactive");
    pill.innerHTML = '<span class="status-pill-dot"></span><span class="status-pill-text">' + label + '</span>';
  }

  function updateEmailStatusPill(state, text) {
    var pill = document.getElementById("email-status-pill");
    if (!pill) return;
    var isConnected = state === "connected" || state === "active";
    var isError = state === "error";
    var isTesting = state === "testing";
    var label = isConnected ? "Connected" : isError ? "Error" : isTesting ? "Testing..." : "Not Connected";

    pill.className = "status-pill " + (isConnected ? "status-pill-active" : isError ? "status-pill-error" : isTesting ? "status-pill-warning" : "status-pill-inactive");
    pill.innerHTML = '<span class="status-pill-dot" id="email-status-dot"></span><span class="status-pill-text" id="email-status-text">' + label + '</span>';
  }
  function showCardError(cardId, msg) {
    var card = document.getElementById(cardId);
    if (!card) return;
    card.classList.add("ring-2","ring-error","bg-error-container/10");
    var helper = card.querySelector(".card-error-helper");
    if (!helper) {
      helper = document.createElement("div");
      helper.className = "card-error-helper flex items-center gap-1.5 px-3 py-2 rounded-xl bg-error-container/30 border border-error/20 text-error font-body-sm mt-3";
      helper.innerHTML = '<span class="material-symbols-outlined text-[18px]">error</span><span></span>';
      card.appendChild(helper);
    }
    helper.querySelector("span:last-child").textContent = msg;
    helper.classList.remove("hidden");
  }
  function clearCardError(cardId) {
    var card = document.getElementById(cardId);
    if (!card) return;
    card.classList.remove("ring-2","ring-error","bg-error-container/10");
    var helper = card.querySelector(".card-error-helper");
    if (helper) helper.remove();
  }
  function setLoading(btn, on){
    if(!btn) return;
    btn.disabled=on; btn.setAttribute("aria-busy", on?"true":"false");
    if(on){ btn.dataset.orig=btn.innerHTML; btn.innerHTML='<span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span><span>Loading...</span>'; }
    else if(btn.dataset.orig){ btn.innerHTML=btn.dataset.orig; }
  }

  function bindGateway() {
    var provider = document.getElementById("ai-provider");
    if (!provider) return;
    var baseEl = document.getElementById("ai-base-url");
    var keyEl = document.getElementById("ai-api-key");
    var modelEl = document.getElementById("ai-model");
    var testBtn = document.getElementById("test-ai-btn");

    var scoringEl = document.getElementById("ai-model-scoring");
    var draftsEl = document.getElementById("ai-model-drafts");
    var cachedGatewayModels = [];

    function saveGatewaySettings(silent) {
      var saveAiBtn = document.getElementById("save-ai-btn");
      var baseV = baseEl ? baseEl.value.trim() : "";
      var keyV = keyEl ? keyEl.value.trim() : "";
      var provV = provider ? provider.value : "custom";
      var modelV = modelEl ? modelEl.value.trim() : "";
      var scoringV = scoringEl ? scoringEl.value.trim() : "";
      var draftsV = draftsEl ? draftsEl.value.trim() : "";
      var needsKey = (AI_PRESETS[provV] || AI_PRESETS.custom).requiresKey;

      clearCardError("ai-gateway-card");
      if (!baseV || (needsKey && !keyV)) {
        var msg = !baseV && needsKey && !keyV ? "Base URL and API key required" : !baseV ? "Base URL required" : "API key required";
        if (!needsKey && !baseV) msg = "Base URL required";
        if (!silent) {
          showCardError("ai-gateway-card", msg);
          showToast(msg);
        }
        return Promise.reject(new Error(msg));
      }

      var payload = {
        AI_PROVIDER: provV,
        AI_BASE_URL: baseV,
        AI_API_KEY: keyV,
        AI_MODEL: modelV,
        AI_MODEL_SCORING: scoringV,
        AI_MODEL_DRAFTS: draftsV
      };

      if (saveAiBtn && !silent) setLoading(saveAiBtn, true);

      return api("/api/settings", {
        method: "POST",
        body: payload
      }).then(function (res) {
        clearCardError("ai-gateway-card");
        setGatewayStatus("connected", "CONNECTED");
        if (!silent) {
          showToast("AI Gateway connection settings saved successfully.");
        }
        return res;
      }).catch(function (err) {
        var msg = (err && (err.message || err.detail)) || "Failed to save AI Gateway settings";
        if (!silent) {
          showCardError("ai-gateway-card", msg);
          showToast(msg);
        }
        throw err;
      }).finally(function () {
        if (saveAiBtn && !silent) setLoading(saveAiBtn, false);
      });
    }

    var saveAiBtn = document.getElementById("save-ai-btn");
    if (saveAiBtn) {
      saveAiBtn.addEventListener("click", function () {
        saveGatewaySettings(false);
      });
    }

    var autoFetchTimer = null;
    function checkAutoFetch() {
      if (autoFetchTimer) clearTimeout(autoFetchTimer);
      autoFetchTimer = setTimeout(function () {
        var baseVal = (baseEl && baseEl.value.trim()) || "";
        var keyVal = (keyEl && keyEl.value.trim()) || "";
        var provVal = (provider && provider.value) || "";
        var needsKey = (AI_PRESETS[provVal] || AI_PRESETS.custom).requiresKey;
        if (baseVal && (!needsKey || keyVal.length >= 6)) {
          fetchGatewayModels(true);
        }
      }, 600);
    }

    provider.addEventListener("change", function (e) {
      if (e && e.__isRestoring) return;
      var preset = AI_PRESETS[provider.value] || AI_PRESETS.custom;
      if (provider.value !== "custom") {
        if (baseEl) baseEl.value = preset.base;
      }
      if (modelEl && modelEl.dataset.autoFilled === "true") {
        modelEl.value = "";
        delete modelEl.dataset.autoFilled;
      }
      cachedGatewayModels = [];
      document.querySelectorAll(".model-dropdown-container").forEach(function (container) {
        if (container._renderOptions) container._renderOptions();
      });
      checkAutoFetch();
      var baseVal = (baseEl && baseEl.value.trim()) || "";
      var keyVal = (keyEl && keyEl.value.trim()) || "";
      if (baseVal && (!preset.requiresKey || keyVal.length >= 6)) {
        saveGatewaySettings(true).catch(function () {});
      }
    });

    if (keyEl) {
      keyEl.addEventListener("input", checkAutoFetch);
      keyEl.addEventListener("paste", function () {
        setTimeout(checkAutoFetch, 100);
      });
      keyEl.addEventListener("blur", function () {
        var baseVal = (baseEl && baseEl.value.trim()) || "";
        var keyVal = (keyEl && keyEl.value.trim()) || "";
        var provVal = (provider && provider.value) || "";
        var needsKey = (AI_PRESETS[provVal] || AI_PRESETS.custom).requiresKey;
        if (baseVal && (!needsKey || keyVal.length >= 6)) {
          saveGatewaySettings(true).catch(function () {});
        }
      });
    }
    if (baseEl) {
      baseEl.addEventListener("input", function () {
        var curBase = baseEl.value.trim();
        var curProv = provider ? provider.value : "custom";
        if (curProv !== "custom" && AI_PRESETS[curProv] && AI_PRESETS[curProv].base && curBase !== AI_PRESETS[curProv].base) {
          if (provider) {
            provider.value = "custom";
            var provLabel = document.getElementById("ai-provider-label");
            if (provLabel) provLabel.textContent = "Custom / Self-hosted";
            var menu = document.getElementById("ai-provider-menu");
            if (menu) {
              menu.querySelectorAll(".custom-select-opt").forEach(function (opt) {
                var isMatch = (opt.getAttribute("data-val") === "custom");
                var checkIcon = opt.querySelector(".check-icon");
                if (checkIcon) checkIcon.classList.toggle("hidden", !isMatch);
                opt.classList.toggle("bg-primary/15", isMatch);
                opt.classList.toggle("text-primary", isMatch);
              });
            }
          }
        }
        checkAutoFetch();
      });
      baseEl.addEventListener("blur", function () {
        var baseVal = (baseEl && baseEl.value.trim()) || "";
        var keyVal = (keyEl && keyEl.value.trim()) || "";
        var provVal = (provider && provider.value) || "";
        var needsKey = (AI_PRESETS[provVal] || AI_PRESETS.custom).requiresKey;
        if (baseVal && (!needsKey || keyVal.length >= 6)) {
          saveGatewaySettings(true).catch(function () {});
        }
      });
    }

    function gatewayVal(el, key) {
      return (el && el.value) || "";
    }

    api("/api/settings").then(function (settings) {
      settings = settings || {};
      function fill(id, key) {
        var el = document.getElementById(id);
        if (el && settings[key]) el.value = settings[key];
        else if (el && LEGACY_ENV_IDS[id] && settings[LEGACY_ENV_IDS[id]]) el.value = settings[LEGACY_ENV_IDS[id]];
      }
      fill("ai-base-url", "AI_BASE_URL");
      fill("ai-api-key", "AI_API_KEY");
      fill("ai-model", "AI_MODEL");
      fill("ai-model-scoring", "AI_MODEL_SCORING");
      fill("ai-model-drafts", "AI_MODEL_DRAFTS");
      if (provider) {
        var savedProv = (settings.AI_PROVIDER || "").toLowerCase().trim();
        if (savedProv && AI_PRESETS[savedProv]) {
          provider.value = savedProv;
        } else if (savedProv === "custom" || settings.AI_BASE_URL) {
          provider.value = "custom";
        } else {
          provider.value = "custom";
        }
        var provLabel = document.getElementById("ai-provider-label");
        if (provLabel && provider.options && provider.selectedIndex >= 0 && provider.options[provider.selectedIndex]) {
          provLabel.textContent = provider.options[provider.selectedIndex].textContent.trim();
        }
        var menu = document.getElementById("ai-provider-menu");
        if (menu) {
          menu.querySelectorAll(".custom-select-opt").forEach(function (opt) {
            var isMatch = (opt.getAttribute("data-val") === provider.value);
            var checkIcon = opt.querySelector(".check-icon");
            if (checkIcon) checkIcon.classList.toggle("hidden", !isMatch);
            opt.classList.toggle("bg-primary/15", isMatch);
            opt.classList.toggle("text-primary", isMatch);
          });
        }
      }
      var changeEvt = new Event("change");
      changeEvt.__isRestoring = true;
      provider.dispatchEvent(changeEvt);

      var existingModels = [settings.AI_MODEL, settings.AI_MODEL_SCORING, settings.AI_MODEL_DRAFTS].filter(function (m) {
        return Boolean(m && String(m).trim());
      });
      if (existingModels.length && !cachedGatewayModels.length) {
        populateGatewayModels(existingModels);
      }

      var needsKey = (AI_PRESETS[provider.value] || AI_PRESETS.custom).requiresKey;
      var hasKey = keyEl && keyEl.value.trim().length >= 6;
      var hasBase = baseEl && baseEl.value.trim().length > 0;
      if (hasKey || (!needsKey && hasBase)) {
        setGatewayStatus("testing", "CHECKING...");
        fetchGatewayModels(true).then(function (ok) {
          if (ok) {
            setGatewayStatus("connected", "CONNECTED");
          } else {
            setGatewayStatus("idle", "NOT_CONNECTED");
          }
        }).catch(function () {
          setGatewayStatus("idle", "NOT_CONNECTED");
        });
      } else {
        setGatewayStatus("idle", "NOT_CONNECTED");
      }
      updateSandboxModelDropdown();
    }).catch(function () {});

    function populateGatewayModels(models) {
      if (!models || !models.length) return;
      cachedGatewayModels = models;

      document.querySelectorAll(".model-dropdown-container").forEach(function (container) {
        var badge = container.querySelector(".model-count-badge");
        if (badge) badge.textContent = models.length + " models";
        if (container._renderOptions) container._renderOptions();
      });
    }

    function setupModelDropdowns() {
      var containers = document.querySelectorAll(".model-dropdown-container");
      if (!containers.length) return;

      containers.forEach(function (container) {
        if (container._dropdownInitialized) return;
        container._dropdownInitialized = true;

        var targetInputId = container.dataset.targetInput;
        var input = document.getElementById(targetInputId);
        var toggleBtn = container.querySelector(".model-dropdown-toggle");
        var menu = container.querySelector(".model-dropdown-menu");
        var searchInput = container.querySelector(".model-search-input");
        var countBadge = container.querySelector(".model-count-badge");
        var optionsList = container.querySelector(".model-options-list");
        var emptyMsg = container.querySelector(".model-empty-msg");
        var filterChips = container.querySelectorAll(".model-filter-chip");

        if (!input || !menu || !optionsList) return;

        var currentFilter = "all";
        var currentSearch = "";

        function renderOptions() {
          var query = currentSearch.toLowerCase().trim();
          var models = cachedGatewayModels;

          if (!models || !models.length) {
            optionsList.innerHTML = '<div class="p-4 text-center text-xs text-secondary font-sans flex flex-col items-center justify-center gap-1.5"><span class="material-symbols-outlined text-[24px] text-secondary">vpn_key_alert</span><span class="font-semibold text-on-surface">No models loaded yet</span><span class="text-[11px] text-secondary">Enter your API key and click <b>Test Connection</b> or <b>Auto-Fetch</b> to load available models.</span></div>';
            if (emptyMsg) emptyMsg.classList.add("hidden");
            if (countBadge) countBadge.textContent = "0 models";
            return;
          }

          var filtered = models.filter(function (m) {
            var low = m.toLowerCase();
            if (currentFilter === "claude" && !low.includes("claude") && !low.includes("anthropic")) return false;
            if (currentFilter === "gpt" && !low.includes("gpt") && !low.includes("openai") && !low.includes("o1") && !low.includes("o3")) return false;
            if (currentFilter === "deepseek" && !low.includes("deepseek")) return false;
            if (currentFilter === "free" && !low.includes(":free") && !low.includes("free")) return false;
            if (query && !low.includes(query)) return false;
            return true;
          });

          if (countBadge) {
            countBadge.textContent = filtered.length + " models";
          }

          if (!filtered.length) {
            optionsList.innerHTML = "";
            if (emptyMsg) emptyMsg.classList.remove("hidden");
            return;
          }
          if (emptyMsg) emptyMsg.classList.add("hidden");

          var curVal = (input.value || "").trim();
          optionsList.innerHTML = filtered.slice(0, 150).map(function (m) {
            var isSelected = (m === curVal);
            var slashIdx = m.indexOf("/");
            var prov = slashIdx !== -1 ? m.substring(0, slashIdx) : "";
            var name = slashIdx !== -1 ? m.substring(slashIdx + 1) : m;

            return '<div class="model-opt-item flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer select-none transition-all ' +
              (isSelected ? "bg-primary/15 text-primary font-semibold" : "text-on-surface hover:bg-surface-container hover:text-primary") +
              '" data-val="' + escapeHtml(m) + '">' +
              '<div class="flex items-center gap-2 min-w-0 flex-1">' +
                (prov ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-surface-container-low font-sans text-secondary shrink-0">' + escapeHtml(prov) + '</span>' : '') +
                '<span class="truncate font-mono text-xs">' + escapeHtml(name) + '</span>' +
              '</div>' +
              (isSelected ? '<span class="material-symbols-outlined text-[16px] text-primary shrink-0 ml-2">check</span>' : '') +
            '</div>';
          }).join("");
        }

        function openMenu() {
          document.querySelectorAll(".model-dropdown-menu").forEach(function (m) {
            if (m !== menu) m.classList.add("hidden");
          });
          document.querySelectorAll(".model-dropdown-toggle span").forEach(function (s) {
            s.style.transform = "rotate(0deg)";
          });

          menu.classList.remove("hidden");
          if (toggleBtn) {
            var icon = toggleBtn.querySelector("span");
            if (icon) icon.style.transform = "rotate(180deg)";
          }
          renderOptions();
          if (searchInput) {
            searchInput.value = "";
            currentSearch = "";
            setTimeout(function () { searchInput.focus(); }, 60);
          }
        }

        function closeMenu() {
          menu.classList.add("hidden");
          if (toggleBtn) {
            var icon = toggleBtn.querySelector("span");
            if (icon) icon.style.transform = "rotate(0deg)";
          }
        }

        function toggleMenu() {
          if (menu.classList.contains("hidden")) {
            openMenu();
          } else {
            closeMenu();
          }
        }

        if (toggleBtn) {
          toggleBtn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            toggleMenu();
          });
        }

        input.addEventListener("click", function (e) {
          if (cachedGatewayModels.length) {
            openMenu();
          }
        });

        if (searchInput) {
          searchInput.addEventListener("input", function () {
            currentSearch = searchInput.value;
            renderOptions();
          });
          searchInput.addEventListener("click", function (e) {
            e.stopPropagation();
          });
        }

        filterChips.forEach(function (chip) {
          chip.addEventListener("click", function (e) {
            e.stopPropagation();
            filterChips.forEach(function (c) {
              c.classList.remove("active", "bg-primary/20", "text-primary", "font-semibold");
              c.classList.add("bg-surface-container", "text-secondary", "font-medium");
            });
            chip.classList.add("active", "bg-primary/20", "text-primary", "font-semibold");
            chip.classList.remove("bg-surface-container", "text-secondary", "font-medium");
            currentFilter = chip.dataset.filter || "all";
            renderOptions();
          });
        });

        optionsList.addEventListener("click", function (e) {
          var item = e.target.closest(".model-opt-item");
          if (!item) return;
          var val = item.dataset.val;
          if (val) {
            input.value = val;
            input.dispatchEvent(new Event("change", { bubbles: true }));
            input.dispatchEvent(new Event("input", { bubbles: true }));
            closeMenu();
          }
        });

        container._renderOptions = renderOptions;
      });

      document.addEventListener("click", function (e) {
        if (!e.target.closest(".model-dropdown-container")) {
          document.querySelectorAll(".model-dropdown-menu").forEach(function (m) {
            m.classList.add("hidden");
          });
          document.querySelectorAll(".model-dropdown-toggle span").forEach(function (s) {
            s.style.transform = "rotate(0deg)";
          });
        }
      });
    }

    setupModelDropdowns();

    function fetchGatewayModels(silent) {
      var fetchBtn = document.getElementById("fetch-gateway-models-btn");
      var baseVal = (baseEl && baseEl.value.trim()) || "";
      var keyVal = (keyEl && keyEl.value.trim()) || "";
      var provVal = (provider && provider.value) || "";
      var needsKey = (AI_PRESETS[provVal] || AI_PRESETS.custom).requiresKey;

      if (!baseVal || (needsKey && !keyVal)) {
        if (!silent) {
          showToast("Please enter an API Key and Base URL first to fetch models.");
        }
        return Promise.resolve(false);
      }

      if (fetchBtn && !silent) setLoading(fetchBtn, true);
      return api("/api/gateway/models", {
        method: "POST",
        body: {
          apiKey: keyVal,
          baseUrl: baseVal,
          provider: provVal
        }
      })
        .then(function (res) {
          if (res && res.models && res.models.length) {
            populateGatewayModels(res.models);
            if (!silent) showToast("Discovered " + res.models.length + " model(s) in gateway.");
            if (modelEl && !modelEl.value.trim()) {
              modelEl.value = res.active_model || res.models[0];
              modelEl.dataset.autoFilled = "true";
            }
            updateSandboxModelDropdown();
            return true;
          } else {
            if (!silent) showToast(res.message || "No models returned from gateway.");
            return false;
          }
        })
        .catch(function (err) {
          if (!silent) showToast("Could not auto-fetch models: " + (err.message || err));
          return false;
        })
        .finally(function () {
          if (fetchBtn && !silent) setLoading(fetchBtn, false);
        });
    }

    var fetchModelsBtn = document.getElementById("fetch-gateway-models-btn");
    if (fetchModelsBtn) {
      fetchModelsBtn.addEventListener("click", function () {
        fetchGatewayModels(false);
      });
    }

    function escapeHtml(str) {
      if (!str) return "";
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    var scoringEl = document.getElementById("ai-model-scoring");
    var draftsEl = document.getElementById("ai-model-drafts");

    function renderDiagnosticResults(models) {
      var diagEl = document.getElementById("ai-diagnostic-results");
      if (!diagEl || !models || !models.length) return;
      diagEl.classList.remove("hidden");
      diagEl.innerHTML = models.map(function (m) {
        var isOk = (m.status === "ok");
        var dotClass = isOk
          ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"
          : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]";
        var statusBadge = isOk
          ? '<span class="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full ' + dotClass + '"></span>ACTIVE</span>'
          : '<span class="text-[11px] px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400 font-semibold flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full ' + dotClass + '"></span>ERROR</span>';

        var latencyText = isOk ? '⚡ ' + m.latency_ms + 'ms' : 'Error';
        var latencyBadge = '<span class="text-[11px] font-mono text-secondary px-2 py-0.5 rounded bg-surface-container">' + latencyText + '</span>';

        var detailContent = isOk
          ? '<div class="mt-1 text-xs font-mono text-secondary bg-surface-container/60 rounded-lg p-2 leading-normal border border-outline-variant/20"><span class="text-[10px] uppercase tracking-wider block text-primary font-bold mb-0.5">Live Reply:</span>' + escapeHtml(m.reply) + '</div>'
          : '<div class="mt-1 text-xs font-mono text-rose-500 bg-rose-500/10 rounded-lg p-2 leading-normal border border-rose-500/20">' + escapeHtml(m.error || "Model failed to respond") + '</div>';

        return '<div class="flex flex-col gap-1.5 bg-surface-container-low border border-outline-variant/30 rounded-xl p-3 transition-all">' +
          '<div class="flex items-center justify-between">' +
            '<div class="flex items-center gap-2">' +
              '<span class="font-label-md text-xs font-bold text-on-surface">' + escapeHtml(m.purpose) + '</span>' +
              '<span class="font-mono text-[11px] text-tertiary px-1.5 py-0.5 rounded bg-surface-container-high">' + escapeHtml(m.model_id) + '</span>' +
            '</div>' +
            '<div class="flex items-center gap-2">' + latencyBadge + statusBadge + '</div>' +
          '</div>' +
          detailContent +
        '</div>';
      }).join("");
    }

    if (testBtn) {
      testBtn.addEventListener("click", function () {
        var baseV = baseEl ? baseEl.value.trim() : "";
        var keyV = keyEl ? keyEl.value.trim() : "";
        var provV = provider ? provider.value : "custom";
        var needsKey = (AI_PRESETS[provV] || AI_PRESETS.custom).requiresKey;
        clearCardError("ai-gateway-card");
        if (!baseV || (needsKey && !keyV)) {
          var msg = !baseV && needsKey && !keyV ? "Base URL and API key required" : !baseV ? "Base URL required" : "API key required";
          if (!needsKey && !baseV) msg = "Base URL required";
          showCardError("ai-gateway-card", msg);
          setGatewayStatus("error", "MISSING_FIELDS");
          showToast(msg);
          return;
        }
        var payload = {
          provider: provV,
          baseUrl: baseV,
          apiKey: keyV,
          model: modelEl ? modelEl.value.trim() : "",
          model_scoring: scoringEl ? scoringEl.value.trim() : "",
          model_drafts: draftsEl ? draftsEl.value.trim() : ""
        };
        setGatewayStatus("idle", "TESTING MODELS...");
        setLoading(testBtn, true);
        api("/api/test-ai", { method: "POST", body: payload })
          .then(function (res) {
            if (res && res.status === "success") {
              clearCardError("ai-gateway-card");
              setGatewayStatus("connected", "CONNECTED");
              saveGatewaySettings(true).then(function () {
                showToast("AI models verified & connection auto-saved!");
              }).catch(function () {
                showToast(res.message || "AI models verified and responsive.");
              });
              if (res.discovered_models && res.discovered_models.length) {
                populateGatewayModels(res.discovered_models);
                if (modelEl && !modelEl.value.trim() && res.active_model) {
                  modelEl.value = res.active_model;
                }
                updateSandboxModelDropdown();
              }
              if (res.models) {
                renderDiagnosticResults(res.models);
              }
              api("/api/ai-meter").then(function (m) {
                if (m && m.last) {
                  var parts = [];
                  if (m.last.total_tokens) parts.push(m.last.total_tokens + " tokens");
                  if (m.last.seconds) parts.push(m.last.seconds + "s");
                  if (m.last.estimated_cost_usd) parts.push("~$" + m.last.estimated_cost_usd);
                  if (parts.length) showToast("Last AI call: " + parts.join(" • "));
                }
              }).catch(function () {});
            } else {
              var failMsg = (res && (res.message || res.detail)) || "Gateway test failed";
              showCardError("ai-gateway-card", failMsg);
              setGatewayStatus("error", "TEST_FAILED");
              if (res && res.models) {
                renderDiagnosticResults(res.models);
              }
              showToast(failMsg);
            }
          })
          .catch(function (err) {
            var msg = (err && (err.message || err.detail)) || "Gateway test failed";
            showCardError("ai-gateway-card", msg);
            setGatewayStatus("error", "TEST_FAILED");
            showToast(msg);
          })
          .finally(function () {
            setLoading(testBtn, false);
          });
      });
    }

    // --- Interactive Model Sandbox / Playground ---
    var toggleSandboxBtn = document.getElementById("toggle-sandbox-btn");
    var sandboxBody = document.getElementById("sandbox-body");
    var sandboxChevron = document.getElementById("sandbox-chevron");
    var sandboxModelSelect = document.getElementById("sandbox-model-select");

    function updateSandboxModelDropdown() {
      if (!sandboxModelSelect) return;
      var mainV = modelEl ? modelEl.value.trim() : "";
      var scV = scoringEl ? scoringEl.value.trim() : "";
      var drV = draftsEl ? draftsEl.value.trim() : "";
      var provV = provider ? provider.value : "custom";
      var presetDef = (AI_PRESETS[provV] || AI_PRESETS.custom).defaultModel || "gpt-4o-mini";
      var effectiveMain = mainV || presetDef;

      var opts = [];
      opts.push({ label: "Main: " + effectiveMain, value: effectiveMain });
      if (scV && scV !== effectiveMain) {
        opts.push({ label: "Scoring: " + scV, value: scV });
      }
      if (drV && drV !== effectiveMain && drV !== scV) {
        opts.push({ label: "Drafts: " + drV, value: drV });
      }

      var cur = sandboxModelSelect.value;
      sandboxModelSelect.innerHTML = opts.map(function (o) {
        return '<option value="' + escapeHtml(o.value) + '">' + escapeHtml(o.label) + '</option>';
      }).join("");

      if (cur && opts.some(function (o) { return o.value === cur; })) {
        sandboxModelSelect.value = cur;
      } else if (opts.length > 0) {
        sandboxModelSelect.value = opts[0].value;
      }
    }

    if (toggleSandboxBtn && sandboxBody) {
      toggleSandboxBtn.addEventListener("click", function () {
        var isHidden = sandboxBody.classList.contains("hidden");
        if (isHidden) {
          sandboxBody.classList.remove("hidden");
          if (sandboxChevron) sandboxChevron.classList.add("rotate-180");
          updateSandboxModelDropdown();
        } else {
          sandboxBody.classList.add("hidden");
          if (sandboxChevron) sandboxChevron.classList.remove("rotate-180");
        }
      });
    }

    [modelEl, scoringEl, draftsEl].forEach(function (inp) {
      if (inp) {
        inp.addEventListener("change", function (e) {
          updateSandboxModelDropdown();
          if (e && e.__isRestoring) return;
          var baseV = baseEl ? baseEl.value.trim() : "";
          var keyV = keyEl ? keyEl.value.trim() : "";
          var provV = provider ? provider.value : "custom";
          var needsKey = (AI_PRESETS[provV] || AI_PRESETS.custom).requiresKey;
          if (baseV && (!needsKey || keyV.length >= 6)) {
            saveGatewaySettings(true).catch(function () {});
          }
        });
      }
    });

    document.querySelectorAll(".sandbox-preset-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var p = btn.getAttribute("data-prompt");
        var inp = document.getElementById("sandbox-prompt-input");
        if (inp && p) {
          inp.value = p;
          inp.focus();
        }
      });
    });

    var sendBtn = document.getElementById("sandbox-send-btn");
    if (sendBtn) {
      sendBtn.addEventListener("click", function () {
        var promptInp = document.getElementById("sandbox-prompt-input");
        var promptVal = promptInp ? promptInp.value.trim() : "";
        if (!promptVal) {
          showToast("Enter a prompt to test");
          return;
        }
        var baseV = baseEl ? baseEl.value.trim() : "";
        var keyV = keyEl ? keyEl.value.trim() : "";
        var provV = provider ? provider.value : "custom";
        var selectedModel = sandboxModelSelect ? sandboxModelSelect.value : "";
        if (!selectedModel || selectedModel === "default" || selectedModel === "main") {
          var presetDef = (AI_PRESETS[provV] || AI_PRESETS.custom).defaultModel || "gpt-4o-mini";
          selectedModel = (modelEl ? modelEl.value.trim() : "") || presetDef;
        }

        var resContainer = document.getElementById("sandbox-response-container");
        var resModel = document.getElementById("sandbox-res-model");
        var resMetrics = document.getElementById("sandbox-res-metrics");
        var resBody = document.getElementById("sandbox-res-body");

        if (resContainer) resContainer.classList.remove("hidden");
        if (resModel) resModel.textContent = "Model: " + (selectedModel || "default");
        if (resMetrics) resMetrics.textContent = "Generating...";
        if (resBody) resBody.textContent = "Sending prompt to model...";

        sendBtn.disabled = true;
        sendBtn.classList.add("opacity-50", "pointer-events-none");

        api("/api/test-ai-prompt", {
          method: "POST",
          body: {
            provider: provV,
            baseUrl: baseV,
            apiKey: keyV,
            model_id: selectedModel,
            prompt: promptVal
          }
        }).then(function (res) {
          sendBtn.disabled = false;
          sendBtn.classList.remove("opacity-50", "pointer-events-none");
          if (res && res.status === "success") {
            if (resMetrics) resMetrics.textContent = "Latency: " + res.latency_ms + "ms | Tokens: " + (res.tokens || 0);
            if (resBody) resBody.textContent = res.reply;
          } else {
            if (resMetrics) resMetrics.textContent = "Status: ERROR";
            if (resBody) resBody.textContent = (res && res.error) || "Error generating response";
          }
        }).catch(function (err) {
          sendBtn.disabled = false;
          sendBtn.classList.remove("opacity-50", "pointer-events-none");
          if (resMetrics) resMetrics.textContent = "Status: ERROR";
          if (resBody) resBody.textContent = err.message || "Failed to reach model";
        });
      });
    }
  }


  function bindSettings() {
    var isSettings = window.location.pathname.indexOf("/settings") !== -1 || document.getElementById("ai-gateway-card") || document.getElementById("email-card");
    if (!isSettings) return;
    // Add ids to cards for per-card error targeting if missing (defensive)
    var linkedinCard = document.getElementById("linkedin-card");
    if (!linkedinCard) {
      var linkedinInput = document.getElementById("linkedin-url-input");
      if (linkedinInput) {
        var c = linkedinInput.closest(".bg-surface-container-lowest");
        if (c) c.id = "linkedin-card";
      }
    }
    var emailCard = document.getElementById("email-card");
    if (!emailCard) {
      var senderInput = document.getElementById("sender-email");
      if (senderInput) {
        var c2 = senderInput.closest(".bg-surface-container-lowest");
        if (c2) c2.id = "email-card";
      }
    }

    // Advanced email options accordion toggle
    var advToggle = document.getElementById("email-advanced-toggle");
    var advPanel = document.getElementById("email-advanced-panel");
    var advArrow = document.getElementById("email-advanced-arrow");
    if (advToggle && advPanel && !advToggle.__bound) {
      advToggle.__bound = true;
      advToggle.addEventListener("click", function () {
        var isHidden = advPanel.classList.toggle("hidden");
        if (advArrow) {
          advArrow.style.transform = isHidden ? "rotate(0deg)" : "rotate(180deg)";
        }
      });
    }

    // App Password paste strip & visibility toggle
    var pwdInput = document.getElementById("smtp-password");
    var pwdToggle = document.getElementById("toggle-pwd-btn");
    if (pwdInput && !pwdInput.__pasteBound) {
      pwdInput.__pasteBound = true;
      pwdInput.addEventListener("paste", function () {
        setTimeout(function () {
          if (pwdInput.value) pwdInput.value = pwdInput.value.replace(/\s+/g, "");
        }, 0);
      });
    }

    api("/api/settings").then(function (settings) {
      settings = settings || {};
      Object.keys(ENV_INPUT_IDS).forEach(function (id) {
        if (id.indexOf("ai-") === 0) return;
        var el = document.getElementById(id);
        if (el && settings[ENV_INPUT_IDS[id]]) {
          el.value = settings[ENV_INPUT_IDS[id]];
          var changeEvt = new Event("change");
          changeEvt.__isRestoring = true;
          el.dispatchEvent(changeEvt);
        }
      });

      // Update email connection status pill
      var hasEmail = Boolean((settings.SENDER_EMAIL || settings.SMTP_USER) && settings.SMTP_PASSWORD);
      updateEmailStatusPill(hasEmail ? "active" : "disconnected", hasEmail ? "Configured" : "Not Configured");
    }).catch(function () {});

    var saveCredsBtn = document.getElementById("save-credentials-btn");
    if (saveCredsBtn) {
      saveCredsBtn.addEventListener("click", function () {
        clearCardError("email-card");
        var email = (document.getElementById("sender-email") && document.getElementById("sender-email").value.trim()) || "";
        var pwd = (document.getElementById("smtp-password") && document.getElementById("smtp-password").value.trim().replace(/\s+/g, "")) || "";
        if (!email) {
          showCardError("email-card", "Connected email address required");
          showToast("Please enter your connected email address");
          return;
        }
        var payload = {
          SENDER_EMAIL: email,
          SMTP_PASSWORD: pwd
        };
        var nameEl = document.getElementById("sender-name");
        if (nameEl && nameEl.value.trim()) payload.SENDER_NAME = nameEl.value.trim();
        var hostEl = document.getElementById("smtp-host");
        if (hostEl && hostEl.value.trim()) payload.SMTP_HOST = hostEl.value.trim();
        var portEl = document.getElementById("smtp-port");
        if (portEl && portEl.value.trim()) payload.SMTP_PORT = portEl.value.trim();
        var userEl = document.getElementById("smtp-user");
        if (userEl && userEl.value.trim()) payload.SMTP_USER = userEl.value.trim();
        var capEl = document.getElementById("send-daily-cap");
        if (capEl && capEl.value.trim()) payload.AI_SEND_DAILY_CAP = capEl.value.trim();
        var intEl = document.getElementById("send-interval-sec");
        if (intEl && intEl.value.trim()) payload.AI_SEND_INTERVAL_SEC = intEl.value.trim();

        setLoading(saveCredsBtn, true);
        api("/api/settings", { method: "POST", body: payload })
          .then(function () {
            clearCardError("email-card");
            showToast("Email credentials saved successfully.");
            var hasEmailNow = Boolean(email && (pwd || (document.getElementById("smtp-password") && document.getElementById("smtp-password").value)));
            updateEmailStatusPill(hasEmailNow ? "active" : "disconnected", hasEmailNow ? "Configured" : "Not Configured");
          })
          .catch(function (err) {
            var msg = (err && err.message) || "Failed to save email credentials";
            showCardError("email-card", msg);
            showToast(msg);
          })
          .finally(function () {
            setLoading(saveCredsBtn, false);
          });
      });
    }

    var savePromptsBtn = document.getElementById("save-prompts-btn");
    function savePromptSettings(silent) {
      var extEl = document.getElementById("prompt-extraction");
      var scoEl = document.getElementById("prompt-scoring");
      var emlEl = document.getElementById("prompt-email");
      var payload = {};
      if (extEl) payload.SYSTEM_PROMPT_EXTRACTION = extEl.value;
      if (scoEl) payload.SYSTEM_PROMPT_SCORING = scoEl.value;
      if (emlEl) payload.SYSTEM_PROMPT_EMAIL = emlEl.value;
      if (!Object.keys(payload).length) return Promise.resolve();
      if (savePromptsBtn && !silent) setLoading(savePromptsBtn, true);
      return api("/api/settings", { method: "POST", body: payload })
        .then(function () {
          if (!silent) showToast("AI prompts & directives saved successfully.");
        })
        .catch(function (err) {
          if (!silent) showToast("Failed to save prompts: " + (err.message || err));
        })
        .finally(function () {
          if (savePromptsBtn && !silent) setLoading(savePromptsBtn, false);
        });
    }

    if (savePromptsBtn) {
      savePromptsBtn.addEventListener("click", function () {
        savePromptSettings(false);
      });
    }

    var resetPromptsBtn = document.getElementById("reset-prompts-btn");
    if (resetPromptsBtn && !resetPromptsBtn.__bound) {
      resetPromptsBtn.__bound = true;
      resetPromptsBtn.addEventListener("click", function () {
        if (!confirm("Restore AI prompts to default system heuristics?")) return;
        setLoading(resetPromptsBtn, true);
        api("/api/settings/prompts/reset", { method: "POST" })
          .then(function (res) {
            if (res && res.prompts) {
              var extEl = document.getElementById("prompt-extraction");
              var scoEl = document.getElementById("prompt-scoring");
              var emlEl = document.getElementById("prompt-email");
              if (extEl) extEl.value = res.prompts.SYSTEM_PROMPT_EXTRACTION || "";
              if (scoEl) scoEl.value = res.prompts.SYSTEM_PROMPT_SCORING || "";
              if (emlEl) emlEl.value = res.prompts.SYSTEM_PROMPT_EMAIL || "";
            }
            showToast("System prompts restored to defaults.");
          })
          .catch(function (err) {
            showToast("Failed to reset prompts: " + (err.message || err));
          })
          .finally(function () {
            setLoading(resetPromptsBtn, false);
          });
      });
    }

    ["prompt-extraction", "prompt-scoring", "prompt-email"].forEach(function (pid) {
      var pel = document.getElementById(pid);
      if (pel) {
        pel.addEventListener("blur", function () {
          savePromptSettings(true);
        });
      }
    });

    var saveBtn = document.getElementById("save-settings-btn");
    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        // Clear previous per-card errors
        ["email-card","ai-gateway-card"].forEach(clearCardError);
        var payload = {};
        var missingCards = [];
        Object.keys(ENV_INPUT_IDS).forEach(function (id) {
          var el = document.getElementById(id);
          if (el && el.value && el.value.trim()) {
            var val = el.value.trim();
            if (ENV_INPUT_IDS[id] === "SMTP_PASSWORD") {
              val = val.replace(/\s+/g, "");
              el.value = val;
            }
            payload[ENV_INPUT_IDS[id]] = val;
          }
          else {
            // Track missing required per card
            if (id === "sender-email" && (!el || !el.value.trim())) missingCards.push({card:"email-card", msg:"Sender email required"});
            if (id === "ai-base-url" && (!el || !el.value.trim())) {
              if (!missingCards.some(function(m){return m.card==="ai-gateway-card";})) {
                missingCards.push({card:"ai-gateway-card", msg:"Base URL required"});
              }
            }
            if (id === "ai-api-key" && (!el || !el.value.trim())) {
              // Keyless providers (e.g. Ollama local) don't need an API key
              var provEl = document.getElementById("ai-provider");
              var preset = AI_PRESETS[(provEl && provEl.value) || "custom"] || AI_PRESETS.custom;
              if (preset.requiresKey && !missingCards.some(function(m){return m.card==="ai-gateway-card";})) {
                missingCards.push({card:"ai-gateway-card", msg:"Base URL and API key required"});
              }
            }
          }
        });
        // Deduplicate gateway card
        var seen = {};
        missingCards = missingCards.filter(function(m){ if(seen[m.card]) return false; seen[m.card]=true; return true; });
        if (!Object.keys(payload).length) {
          missingCards.forEach(function(m){ showCardError(m.card, m.msg); });
          showToast("Please fill required fields in highlighted cards");
          // Also handle backend 400 for empty
          return;
        }
        // Clear errors for cards that are now filled
        Object.keys(payload).forEach(function(k){
          if (k==="SENDER_EMAIL") clearCardError("email-card");
          if (k==="AI_BASE_URL" || k==="AI_API_KEY") clearCardError("ai-gateway-card");
        });
        setLoading(saveBtn, true);
        api("/api/settings", { method: "POST", body: payload })
          .then(function () {
            showToast("Configuration saved successfully.");
            var hasEmailNow = Boolean((payload.SENDER_EMAIL || payload.SMTP_USER) && (payload.SMTP_PASSWORD || (document.getElementById("smtp-password") && document.getElementById("smtp-password").value)));
            updateEmailStatusPill(hasEmailNow ? "active" : "disconnected", hasEmailNow ? "Configured" : "Not Configured");
          })
          .catch(function (err) {
            var msg = err.message || "Settings failed";
            // Map backend error to per-card
            if (msg.toLowerCase().indexOf("linkedin")!==-1) showCardError("linkedin-card", msg);
            else if (msg.toLowerCase().indexOf("sender")!==-1 || msg.toLowerCase().indexOf("email")!==-1) showCardError("email-card", msg);
            else if (msg.toLowerCase().indexOf("api key")!==-1 || msg.toLowerCase().indexOf("base url")!==-1) showCardError("ai-gateway-card", msg);
            else showToast(msg);
          })
          .finally(function () {
            setLoading(saveBtn, false);
          });
      });
    }
  }

  function bindCompactToggle() {
    var KEY = "easiapply-compact";
    function applyCompact(compact) {
      document.documentElement.classList.toggle("compact-view", compact);
      try { localStorage.setItem(KEY, compact ? "1" : "0"); } catch (e) {}
      var toggles = document.querySelectorAll("#compact-toggle");
      toggles.forEach(function (el) {
        el.setAttribute("aria-checked", compact ? "true" : "false");
        el.classList.toggle("bg-primary-container", compact);
        el.classList.toggle("bg-surface-container-highest", !compact);
        var knob = el.querySelector("span.w-5") || el.querySelector(":scope > span");
        if (knob) {
          knob.classList.toggle("translate-x-6", compact);
          knob.classList.toggle("translate-x-0", !compact);
        }
      });
    }

    var saved = null;
    try { saved = localStorage.getItem(KEY); } catch (e) {}
    var isCompact = saved === "1";
    applyCompact(isCompact);

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("#compact-toggle");
      if (btn) {
        e.preventDefault();
        var current = document.documentElement.classList.contains("compact-view");
        applyCompact(!current);
        showToast(!current ? "Compact cockpit view enabled." : "Standard view restored.");
      }
    });
  }

  function bindCustomDropdowns() {
    var dropdownConfigs = [
      {
        btnId: "ai-provider-btn",
        menuId: "ai-provider-menu",
        arrowId: "ai-provider-arrow",
        labelId: "ai-provider-label",
        selectId: "ai-provider",
        optSelector: ".custom-select-opt[data-target='ai-provider']"
      },
      {
        btnId: "pref-target-seniority-btn",
        menuId: "pref-target-seniority-menu",
        arrowId: "pref-target-seniority-arrow",
        labelId: "pref-target-seniority-label",
        selectId: "pref-target-seniority",
        optSelector: ".custom-select-opt[data-target='pref-target-seniority']"
      },
      {
        btnId: "matches-sort-btn",
        menuId: "matches-sort-menu",
        arrowId: "matches-sort-arrow",
        labelId: "matches-sort-label",
        selectId: "matches-sort-select",
        optSelector: ".matches-sort-opt"
      }
    ];

    function closeAllMenus() {
      dropdownConfigs.forEach(function (cfg) {
        var menu = document.getElementById(cfg.menuId);
        var arrow = document.getElementById(cfg.arrowId);
        var btn = document.getElementById(cfg.btnId);
        if (menu) menu.classList.add("hidden");
        if (arrow) arrow.style.transform = "rotate(0deg)";
        if (btn) btn.setAttribute("aria-expanded", "false");
      });
    }

    dropdownConfigs.forEach(function (cfg) {
      var btn = document.getElementById(cfg.btnId);
      var menu = document.getElementById(cfg.menuId);
      var arrow = document.getElementById(cfg.arrowId);
      var label = document.getElementById(cfg.labelId);
      var select = document.getElementById(cfg.selectId);

      if (!btn || !menu) return;

      function syncFromSelect() {
        if (!select) return;
        var currentVal = select.value;
        var options = menu.querySelectorAll(cfg.optSelector);

        options.forEach(function (opt) {
          var val = opt.getAttribute("data-val");
          var isMatch = (val === currentVal);
          var checkIcon = opt.querySelector(".check-icon");
          if (checkIcon) {
            checkIcon.classList.toggle("hidden", !isMatch);
          }
          opt.classList.toggle("bg-primary/15", isMatch);
          opt.classList.toggle("text-primary", isMatch);
        });

        if (label && select.options && select.selectedIndex >= 0 && select.options[select.selectedIndex]) {
          label.textContent = select.options[select.selectedIndex].textContent.trim();
        }
      }

      syncFromSelect();

      if (select) {
        select.addEventListener("change", syncFromSelect);
      }

      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var isClosed = menu.classList.contains("hidden");
        closeAllMenus();
        if (isClosed) {
          menu.classList.remove("hidden");
          if (arrow) arrow.style.transform = "rotate(180deg)";
          btn.setAttribute("aria-expanded", "true");
        }
      });

      var opts = menu.querySelectorAll(cfg.optSelector);
      opts.forEach(function (opt) {
        opt.addEventListener("click", function (e) {
          e.stopPropagation();
          var val = opt.getAttribute("data-val");
          if (select) {
            select.value = val;
            select.dispatchEvent(new Event("change", { bubbles: true }));
          }
          syncFromSelect();
          closeAllMenus();
        });
      });
    });

    document.addEventListener("click", function (e) {
      if (!e.target.closest(".custom-dropdown-wrapper") && !e.target.closest("#matches-sort-wrapper")) {
        closeAllMenus();
      }
    });
  }

  function bindResetData() {
    var btns = $$('[id="reset-data-btn"]');
    btns.forEach(function(btn){
      btn.addEventListener("click", function () {
        showConfirmModal({
          title: "Reset Application Data",
          message: "This will permanently delete:\n- All scraped job applications\n- Cached data\n- Telemetry logs\n\nYour resume, settings, and API keys will be preserved. Continue?",
          confirmText: "Reset Data",
          danger: true,
          onConfirm: function () {
            api("/api/reset-data", { method: "POST", body: {} })
              .then(function () {
                showToast("Workspace reset initiated. Restoring system defaults.");
                setTimeout(function () { (window.top||window).location.reload(); }, 900);
              })
              .catch(function (err) { showToast("Reset failed: " + err.message); });
          }
        });
      });
    });
  }

  function bindResetApps() {
    var btns = $$('[id="reset-apps-btn"]');
    if (!btns.length) return;
    btns.forEach(function(btn){
      btn.addEventListener("click", function () {
        showConfirmModal({
          title: "Reset Jobs & Resumes",
          message: "This will permanently delete:\n- All uploaded resumes\n- All scraped job matches\n- All sent application records\n- All tailored resumes\n\nYour API keys, mail config, and settings will be preserved. Continue?",
          confirmText: "Delete Records",
          danger: true,
          onConfirm: function () {
            api("/api/reset-apps", { method: "POST", body: {} })
              .then(function () {
                try {
                  localStorage.removeItem("easapply_dashboard_search_state");
                  localStorage.removeItem("easiapply_dashboard_search_state");
                } catch (e) {}
                showToast("Job data cleared successfully.");
                setTimeout(function () { (window.top||window).location.reload(); }, 900);
              })
              .catch(function (err) { showToast("Clear failed: " + err.message); });
          }
        });
      });
    });
  }

  function bindResetAll() {
    var btns = $$('[id="reset-all-btn"]');
    btns.forEach(function(btn){
      btn.addEventListener("click", function () {
        showConfirmModal({
          title: "Factory Reset All Data",
          message: "WARNING: FACTORY RESET — This will permanently delete:\n- All uploaded resumes\n- All scraped job matches\n- All sent applications\n- All tailored resumes\n- All API keys & AI config\n- Email / SMTP configuration\n- LinkedIn session & cookies\n- Custom search keywords & locations\n\nEverything will be wiped clean. This cannot be undone. Continue?",
          confirmText: "Factory Reset",
          danger: true,
          onConfirm: function () {
            api("/api/reset-all", { method: "POST", body: {} })
              .then(function () {
                try {
                  localStorage.removeItem("easapply_dashboard_search_state");
                  localStorage.removeItem("easiapply_dashboard_search_state");
                } catch (e) {}
                showToast("Factory reset complete. All data wiped.");
                setTimeout(function () { (window.top||window).location.reload(); }, 900);
              })
              .catch(function (err) { showToast("Reset failed: " + err.message); });
          }
        });
      });
    });
  }

  // ---------------------------------------------------------------------------
  // LinkedIn login modal & status management
  // ---------------------------------------------------------------------------
  function openLinkedInLoginModal(onSuccess) {
    var existing = document.getElementById("linkedin-auth-modal");
    if (existing) existing.remove();

    var modal = document.createElement("div");
    modal.id = "linkedin-auth-modal";
    modal.className = "fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm app-modal animate-fade-in";
    modal.innerHTML = 
      '<div class="bg-surface-container-lowest border border-outline-variant/60 rounded-3xl p-6 sm:p-8 max-w-lg w-full shadow-2xl relative">' +
        '<div class="flex items-center gap-3 mb-4">' +
          '<div class="w-12 h-12 rounded-2xl bg-[#0A66C2]/15 text-[#0A66C2] flex items-center justify-center font-bold shrink-0">' +
            '<span class="material-symbols-outlined text-[28px]">share</span>' +
          '</div>' +
          '<div>' +
            '<h3 class="font-headline-sm text-headline-sm font-bold text-on-surface">LinkedIn Login Required</h3>' +
            '<p class="font-body-sm text-body-sm text-secondary">Connect your LinkedIn profile to crawl listings and recruiter contacts.</p>' +
          '</div>' +
        '</div>' +
        '<div class="p-4 rounded-2xl bg-surface-container-low border border-surface-container-high/60 mb-6 text-on-surface font-body-sm space-y-2">' +
          '<div class="flex items-center gap-2 text-primary font-semibold">' +
            '<span class="material-symbols-outlined text-[18px]">verified_user</span>' +
            '<span>100% Safe Local Browser Profile</span>' +
          '</div>' +
          '<p class="text-secondary text-[13px] leading-relaxed">EasiApply runs through your local Chrome session on this machine. Click below to open Chrome, sign into your LinkedIn account, and finish any 2-factor prompts. Once logged in, your search will begin automatically.</p>' +
        '</div>' +
        '<div class="flex flex-col sm:flex-row items-center justify-end gap-3">' +
          '<button id="li-modal-cancel-btn" type="button" class="w-full sm:w-auto px-5 py-2.5 rounded-full bg-surface-container hover:bg-surface-container-high text-secondary hover:text-on-surface font-label-md font-bold transition-all cursor-pointer">Cancel</button>' +
          '<button id="li-modal-verify-btn" type="button" class="w-full sm:w-auto px-5 py-2.5 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-label-md font-bold transition-all flex items-center justify-center gap-1.5 cursor-pointer">' +
            '<span class="material-symbols-outlined text-[18px]">verified</span>' +
            '<span>Check Status Now</span>' +
          '</button>' +
          '<button id="li-modal-launch-btn" type="button" class="w-full sm:w-auto px-6 py-2.5 rounded-full bg-[#0A66C2] hover:bg-[#004182] text-white font-label-md font-bold transition-all flex items-center justify-center gap-2 shadow-md hover:scale-[1.02] active:scale-95 cursor-pointer">' +
            '<span class="material-symbols-outlined text-[18px]">open_in_new</span>' +
            '<span>Open Chrome & Log In</span>' +
          '</button>' +
        '</div>' +
      '</div>';
    
    document.body.appendChild(modal);

    var cancelBtn = modal.querySelector("#li-modal-cancel-btn");
    var verifyBtn = modal.querySelector("#li-modal-verify-btn");
    var launchBtn = modal.querySelector("#li-modal-launch-btn");
    var pollTimer = null;

    function checkAndResolve(silent) {
      return api("/api/linkedin-status").then(function (statusRes) {
        if (statusRes && statusRes.logged_in) {
          if (pollTimer) clearInterval(pollTimer);
          modal.remove();
          paintLinkedInStatus(statusRes);
          showToast("LinkedIn connected as " + (statusRes.account_name || "Active Member") + "!");
          if (typeof onSuccess === "function") {
            onSuccess();
          }
          return true;
        } else if (!silent) {
          showToast("LinkedIn login not detected yet. Complete login in Chrome first.");
        }
        return false;
      }).catch(function () {});
    }

    // Check immediately on modal open
    checkAndResolve(true);

    cancelBtn.addEventListener("click", function () {
      if (pollTimer) clearInterval(pollTimer);
      modal.remove();
    });

    verifyBtn.addEventListener("click", function () {
      checkAndResolve(false);
    });

    launchBtn.addEventListener("click", function () {
      launchBtn.disabled = true;
      launchBtn.innerHTML = '<span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span><span>Waiting for LinkedIn Login...</span>';
      showToast("Launching Chrome... Sign in to LinkedIn in the opened window.");
      
      api("/api/linkedin/login-window", { method: "POST", body: {} })
        .catch(function (err) { console.error(err); });

      var pollCount = 0;
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(function () {
        pollCount++;
        checkAndResolve(true);

        if (pollCount > 100) {
          clearInterval(pollTimer);
          launchBtn.disabled = false;
          launchBtn.innerHTML = '<span class="material-symbols-outlined text-[18px]">refresh</span><span>Check Login Again</span>';
        }
      }, 1500);
    });
  }
  window.openLinkedInLoginModal = openLinkedInLoginModal;

  function paintLinkedInStatus(data) {
    var state = typeof data === "string" ? data : (data && data.status ? data.status : "unknown");
    var accountName = (data && data.account_name) || "";
    var isLoggedIn = !!(data && data.logged_in === true && state === "connected");

    var cleanName = (accountName || "Active Member").split("\n")[0].trim();
    var loginCred = (data && data.login_credential) ? String(data.login_credential).trim() : "";

    // Header Pill across all pages
    var headerLabel = document.getElementById("header-linkedin-label");
    var headerDot = document.getElementById("header-linkedin-dot");
    var headerPills = $$('[id="header-linkedin-pill"]');
    headerPills.forEach(function (pill) {
      if (isLoggedIn) {
        var hoverText = "Account: " + (cleanName || "Active Member");
        if (loginCred) {
          var isPhone = !loginCred.includes("@");
          hoverText += "\n" + (isPhone ? "Phone: " : "Email: ") + loginCred;
        }
        pill.title = hoverText;
      } else {
        pill.title = "Account: Not Connected";
      }
    });

    if (headerLabel) {
      if (isLoggedIn) {
        headerLabel.textContent = "LinkedIn: " + (cleanName || "Connected");
        headerLabel.title = "";
      } else {
        headerLabel.textContent = "LinkedIn: Not Connected";
        headerLabel.title = "";
      }
    }
    if (headerDot) {
      if (isLoggedIn) {
        headerDot.className = "w-2 h-2 rounded-full dot-connected shrink-0";
      } else {
        headerDot.className = "w-2 h-2 rounded-full dot-disconnected shrink-0";
      }
    }

    // Settings page account display
    var acctDisplay = document.getElementById("linkedin-account-label") || document.getElementById("linkedin-account-display");
    if (acctDisplay) {
      if (isLoggedIn) {
        acctDisplay.textContent = "Account: " + (cleanName || "Connected Member");
        acctDisplay.className = "font-label-md text-label-md text-on-surface font-semibold";
      } else {
        acctDisplay.textContent = "Account: Not Connected";
        acctDisplay.className = "font-label-md text-label-md text-secondary font-semibold";
      }
    }

    var pills = $$(".linkedin-login-status");
    pills.forEach(function (pill) {
      if (isLoggedIn) {
        pill.className = "status-pill status-pill-active linkedin-login-status";
        pill.innerHTML = '<span class="status-pill-dot"></span><span class="status-pill-text">Connected</span>';
      } else {
        pill.className = "status-pill status-pill-inactive linkedin-login-status";
        pill.innerHTML = '<span class="status-pill-dot"></span><span class="status-pill-text">Not Connected</span>';
      }
    });

    var helps = $$(".linkedin-login-help");
    helps.forEach(function (h) {
      if (isLoggedIn) h.textContent = "LinkedIn account session active (" + (cleanName || "Connected") + "). Scrapes will reuse this persistent session.";
      else h.textContent = "No active session found. Click 'Open Chrome Session' below to sign in.";
    });
  }

  function bindLinkedInStatus() {
    api("/api/linkedin-status").then(function (res) {
      paintLinkedInStatus(res || "unknown");
    }).catch(function () { paintLinkedInStatus("unknown"); });

    // Header pill click
    var headerPills = $$('[id="header-linkedin-pill"]');
    headerPills.forEach(function (pill) {
      if (pill.__bound) return;
      pill.__bound = true;
      pill.addEventListener("click", function () {
        api("/api/linkedin-status").then(function (res) {
          paintLinkedInStatus(res);
          if (res && res.logged_in) {
            showToast("Active LinkedIn Session: " + (res.account_name || "Connected"));
          } else {
            openLinkedInLoginModal(function () {
              api("/api/linkedin-status").then(paintLinkedInStatus);
            });
          }
        }).catch(function () {
          openLinkedInLoginModal();
        });
      });
    });

    // Settings page Open Chrome Session button
    var chromeBtns = $$('[id="launch-chrome-login-btn"]');
    chromeBtns.forEach(function (btn) {
      if (btn.__bound) return;
      btn.__bound = true;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        openLinkedInLoginModal(function () {
          api("/api/linkedin-status").then(paintLinkedInStatus);
        });
      });
    });

    // Connect Endpoint / Check status button
    var btns = $$('[id="test-conn-btn"]');
    btns.forEach(function (btn) {
      if (btn.__linkedinBound) return;
      btn.__linkedinBound = true;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var orig = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="material-symbols-outlined text-[18px] animate-spin">sync</span><span>Checking login...</span>';
        api("/api/linkedin-status").then(function (res) {
          paintLinkedInStatus(res || "unknown");
          showToast(res && res.message ? res.message : "LinkedIn status verified.");
        }).catch(function (err) {
          paintLinkedInStatus("unknown");
          showToast("LinkedIn check failed: " + err.message);
        }).then(function () {
          btn.disabled = false;
          btn.innerHTML = orig;
        });
      }, true);
    });
  }

  // ---------------------------------------------------------------------------
  // Outreach composer — token insertion + send
  // ---------------------------------------------------------------------------
  function insertToken(token) {
    var active = document.activeElement;
    var target = (active && (active.id === "linkedin-note-input" || active.id === "email-body-input"))
      ? active
      : document.getElementById("email-body-input");
    if (!target) return;
    var start = target.selectionStart !== undefined ? target.selectionStart : target.value.length;
    var end = target.selectionEnd !== undefined ? target.selectionEnd : target.value.length;
    var val = target.value;
    target.value = val.substring(0, start) + token + val.substring(end);
    target.selectionStart = target.selectionEnd = start + token.length;
    target.focus();
    target.dispatchEvent(new Event("input", { bubbles: true }));
  }
  window.insertToken = insertToken;

  function bindGlobalDelegation() {
    document.addEventListener("click", function(e) {

      var exportBtn = e.target.closest('#export-data-btn');
      if (exportBtn) {
        showToast("Downloading workspace JSON backup...");
        window.location.href = "/api/export-data";
        return;
      }
      var acc = e.target.closest(".accordion-toggle") || e.target.closest("#accordion-toggle") || e.target.closest("#toggle-email-accordion");
      if (acc) {
        e.preventDefault();
        var targetId = acc.getAttribute("data-target");
        // IDs repeat across the 4 state wrappers — resolve inside the
        // toggle's own wrapper so the visible copy actually opens.
        var scope = acc.closest('[id^="state-"]') || document;
        var content = null;
        if (targetId && scope.querySelector) {
          try { content = scope.querySelector('#' + targetId); } catch (err) { content = null; }
        }
        if (!content && targetId) {
          try { content = document.querySelector('#' + targetId); } catch (err) { content = null; }
        }
        if (!content) {
          var parentGroup = acc.closest(".group") || acc.parentElement || acc.closest(".bg-surface-container-lowest");
          if (parentGroup) content = parentGroup.querySelector(".accordion-content, #email-preview-content");
        }
        if (content) {
          content.classList.toggle("hidden");
          var icon = acc.querySelector(".material-symbols-outlined, .chevron-icon, #accordion-icon");
          if (icon) {
            icon.style.transform = content.classList.contains("hidden") ? "" : "rotate(180deg)";
          }
        }
        return;
      }
      var tab = e.target.closest('#tab-write, #tab-preview');
      if (tab) {
        e.preventDefault();
        var parent = tab.parentElement;
        if (parent) {
          parent.querySelectorAll('#tab-write, #tab-preview').forEach(function(b){
            b.classList.remove("bg-surface-container-lowest", "text-on-surface", "font-semibold", "bg-primary-container");
            b.classList.add("text-secondary");
          });
          tab.classList.remove("text-secondary");
          tab.classList.add("bg-surface-container-lowest", "text-on-surface", "font-semibold");
        }
        return;
      }
    });
  }
  // ---------------------------------------------------------------------------
  // Dashboard: live match stream & setup progress
  // ---------------------------------------------------------------------------
  function bindDashboard() {
    var list = document.getElementById("recent-matches-list");
    var setupPill = document.getElementById("setup-progress");
    if (!list && !setupPill && currentSection() !== "dashboard") return;

    api("/api/state").then(function (state) {
      if (!state) return;
      var done = (state.has_resume ? 1 : 0) + (state.has_email ? 1 : 0) + (state.has_ai_config ? 1 : 0);
      var pills = $$('[id="setup-progress"]');
      pills.forEach(function (p) {
        p.textContent = done + " / 3 DONE";
      });
      if (state.has_resume) {
        api("/api/resume-meta").then(function (meta) {
          var r = (meta && meta.resume);
          if (r) {
            var titleEl = document.getElementById("quick-setup-resume-title");
            if (titleEl) titleEl.textContent = r.name || r.filename;
            var subEl = document.getElementById("quick-setup-resume-sub");
            if (subEl) subEl.textContent = r.filename + " • Ingested";
            var badgeEl = document.getElementById("quick-setup-resume-badge");
            if (badgeEl) badgeEl.innerHTML = '<span class="material-symbols-outlined text-[20px] text-primary">check_circle</span>';
            var quick_setup_resume_icon_el = document.getElementById("quick-setup-resume-icon");
            if (quick_setup_resume_icon_el) { quick_setup_resume_icon_el.classList.remove("text-error/60"); quick_setup_resume_icon_el.classList.add("text-on-surface"); }
          }
        }).catch(function () {});
      } else {
        var titleEl = document.getElementById("quick-setup-resume-title");
        if (titleEl) titleEl.textContent = "Upload Resume";
        var subEl = document.getElementById("quick-setup-resume-sub");
        if (subEl) subEl.textContent = "PDF, DOCX up to 10MB";
        var badgeEl = document.getElementById("quick-setup-resume-badge");
        if (badgeEl) badgeEl.innerHTML = '<span class="material-symbols-outlined text-[20px]">add</span>';
            var quick_setup_resume_icon_elx = document.getElementById("quick-setup-resume-icon");
            if (quick_setup_resume_icon_elx) { quick_setup_resume_icon_elx.classList.add("text-error/60"); quick_setup_resume_icon_elx.classList.remove("text-on-surface"); }
      }

      if (state.has_email) {
        var gmailTitleEl = document.getElementById("quick-setup-gmail-title");
        if (gmailTitleEl) gmailTitleEl.textContent = state.sender_name || state.sender_email || "Gmail / SMTP Connected";
        var gmailSubEl = document.getElementById("quick-setup-gmail-sub");
        if (gmailSubEl) gmailSubEl.textContent = (state.sender_email || "smtp.gmail.com") + " • Connected";
        var gmailBadgeEl = document.getElementById("quick-setup-gmail-badge");
        if (gmailBadgeEl) gmailBadgeEl.innerHTML = '<span class="material-symbols-outlined text-[20px] text-primary">check_circle</span>';
            var quick_setup_gmail_icon_el = document.getElementById("quick-setup-gmail-icon");
            if (quick_setup_gmail_icon_el) { quick_setup_gmail_icon_el.classList.remove("text-error/60"); quick_setup_gmail_icon_el.classList.add("text-on-surface"); }
      } else {
        var gmailTitleEl = document.getElementById("quick-setup-gmail-title");
        if (gmailTitleEl) gmailTitleEl.textContent = "Connect Gmail / SMTP";
        var gmailSubEl = document.getElementById("quick-setup-gmail-sub");
        if (gmailSubEl) gmailSubEl.textContent = "Automate applications direct";
        var gmailBadgeEl = document.getElementById("quick-setup-gmail-badge");
        if (gmailBadgeEl) gmailBadgeEl.innerHTML = '<span class="material-symbols-outlined text-[18px]">link</span>';
            var quick_setup_gmail_icon_elx = document.getElementById("quick-setup-gmail-icon");
            if (quick_setup_gmail_icon_elx) { quick_setup_gmail_icon_elx.classList.add("text-error/60"); quick_setup_gmail_icon_elx.classList.remove("text-on-surface"); }
      }

      if (state.has_ai_config) {
        var aiTitleEl = document.getElementById("quick-setup-ai-title");
        if (aiTitleEl) aiTitleEl.textContent = "AI Gateway Connected";
        var aiSubEl = document.getElementById("quick-setup-ai-sub");
        if (aiSubEl) aiSubEl.textContent = "Provider configured • Scoring ready";
        var aiBadgeEl = document.getElementById("quick-setup-ai-badge");
        if (aiBadgeEl) aiBadgeEl.innerHTML = '<span class="material-symbols-outlined text-[20px] text-primary">check_circle</span>';
            var quick_setup_ai_icon_el = document.getElementById("quick-setup-ai-icon");
            if (quick_setup_ai_icon_el) { quick_setup_ai_icon_el.classList.remove("text-error/60"); quick_setup_ai_icon_el.classList.add("text-on-surface"); }
      } else {
        var aiTitleEl = document.getElementById("quick-setup-ai-title");
        if (aiTitleEl) aiTitleEl.textContent = "Set AI Gateway";
        var aiSubEl = document.getElementById("quick-setup-ai-sub");
        if (aiSubEl) aiSubEl.textContent = "Connect AI provider for scoring";
        var aiBadgeEl = document.getElementById("quick-setup-ai-badge");
        if (aiBadgeEl) aiBadgeEl.innerHTML = '<span class="material-symbols-outlined text-[18px]">link</span>';
            var quick_setup_ai_icon_elx = document.getElementById("quick-setup-ai-icon");
            if (quick_setup_ai_icon_elx) { quick_setup_ai_icon_elx.classList.add("text-error/60"); quick_setup_ai_icon_elx.classList.remove("text-on-surface"); }
      }
    }).catch(function () {});

    var advToggle = document.getElementById("advanced-toggle");
    var advPanel = document.getElementById("advanced-panel");
    var advIcon = document.getElementById("advanced-toggle-icon");
    if (advToggle && advPanel && !advToggle.__toggleBound) {
      advToggle.__toggleBound = true;
      advToggle.addEventListener("click", function () {
        advPanel.classList.toggle("hidden");
        if (advIcon) advIcon.classList.toggle("rotate-180");
      });
    }

    Promise.all([
      api("/api/state").catch(function () { return {}; }),
      api("/api/applications").catch(function () { return []; })
    ]).then(function (results) {
      var state = results[0] || {};
      var apps = results[1] || [];
      var emptyCards = $$('[id="empty-matches"]');
      var matchCards = $$('[id="recent-matches"]');
      var prevCards = $$('[id="previous-session-matches"]');
      var sessionScrapes = (typeof state.session_scraped_count === "number") ? state.session_scraped_count : 0;
      var hasActiveSessionScrapes = sessionScrapes > 0;

      if (!apps.length) {
        emptyCards.forEach(function (c) { c.classList.remove("hidden"); });
        matchCards.forEach(function (c) { c.classList.add("hidden"); });
        prevCards.forEach(function (c) { c.classList.add("hidden"); });
        return;
      }

      if (hasActiveSessionScrapes) {
        // Scraped in this session -> show Latest Discoveries feed, keep visible across tab switches
        emptyCards.forEach(function (c) { c.classList.add("hidden"); });
        matchCards.forEach(function (c) { c.classList.remove("hidden"); });
        prevCards.forEach(function (c) { c.classList.add("hidden"); });
      } else {
        // Fresh restart with existing database items -> show empty matches + previous session notice bar
        emptyCards.forEach(function (c) { c.classList.remove("hidden"); });
        matchCards.forEach(function (c) { c.classList.add("hidden"); });
        prevCards.forEach(function (c) {
          c.classList.remove("hidden");
          var countEl = c.querySelector("#prev-session-count");
          if (countEl) countEl.textContent = apps.length;
        });
      }

      var batchBadge = document.getElementById("batch-badge");
      if (batchBadge) batchBadge.textContent = apps.length + " Posts Scored";
      var batchDesc = document.getElementById("batch-desc");
      if (batchDesc) batchDesc.textContent = apps.length + " verified posts scraped & AI scored against your resume.";
      var viewAllText = document.getElementById("view-all-matches-text");
      if (viewAllText) viewAllText.textContent = "View all (" + apps.length + ") matches";

      var scored = apps.slice().sort(function (a, b) {
        return (parseInt(b.match_score, 10) || 0) - (parseInt(a.match_score, 10) || 0);
      });

      var topMatches = scored.slice(0, 5);
      var lists = $$('[id="recent-matches-list"]');
      lists.forEach(function (listEl) {
        listEl.innerHTML = "";
        topMatches.forEach(function (a) {
          var score = Math.max(0, Math.min(100, parseInt(a.match_score, 10) || 0));
          var tier = matchTier(score);
          var initial = escapeHTML(String(a.company || "?").trim().charAt(0).toUpperCase() || "?");
          var postLink = safeLink(getValidListingUrl(a));
          var row = document.createElement("div");
          row.className = "flex items-center justify-between p-space-md rounded-2xl bg-surface-container-low hover:bg-surface-container-high transition-all cursor-pointer";
          row.addEventListener("click", function () { window.location.href = "/outreach?id=" + encodeURIComponent(a.id); });
          row.innerHTML =
            '<div class="flex items-center gap-space-sm min-w-0">' +
              '<div class="w-10 h-10 rounded-xl bg-surface-container-lowest flex items-center justify-center font-bold text-primary shadow-sm shrink-0">' + initial + '</div>' +
              '<div class="flex flex-col min-w-0">' +
                '<span class="font-label-md text-label-md text-on-surface font-bold truncate">' + escapeHTML(a.title || "Untitled Role") + '</span>' +
                '<span class="font-body-sm text-body-sm text-secondary truncate">' + escapeHTML(a.company || "") + (a.location ? " • " + escapeHTML(a.location) : "") + '</span>' +
              '</div>' +
            '</div>' +
            '<div class="flex items-center gap-space-md shrink-0">' +
              (postLink ? '<a href="' + postLink + '" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 rounded-xl bg-[#0A66C2]/10 hover:bg-[#0A66C2]/20 text-[#0A66C2] transition-colors flex items-center gap-1 font-label-md text-[12px] font-semibold shadow-xs" title="View original post on LinkedIn" onclick="event.stopPropagation();"><span class="material-symbols-outlined text-[16px]">open_in_new</span><span class="hidden sm:inline">LinkedIn</span></a>' : '') +
              '<div class="px-3 py-1 rounded-full ' + tier.cls + ' font-label-md text-[12px] font-bold">' + score + '% Match</div>' +
              '<span class="material-symbols-outlined text-secondary hover:text-on-surface text-[20px]">chevron_right</span>' +
            '</div>';
          listEl.appendChild(row);
        });
      });
    }).catch(function () {});
  }

  // ---------------------------------------------------------------------------
  // Test Email relay (Settings)
  // ---------------------------------------------------------------------------
  function bindTestEmail() {
    var btns = $$('[id="send-test-btn"]');
    if (!btns.length) return;
    btns.forEach(function (btn) {
      if (btn.__testBound) return;
      btn.__testBound = true;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        var card = btn.closest(".bg-surface-container-lowest") || document;
        var emailEl = card.querySelector("#sender-email") || document.getElementById("sender-email");
        var nameEl = card.querySelector("#sender-name") || document.getElementById("sender-name");
        var hostEl = card.querySelector("#smtp-host") || document.getElementById("smtp-host");
        var portEl = card.querySelector("#smtp-port") || document.getElementById("smtp-port");
        var userEl = card.querySelector("#smtp-user") || document.getElementById("smtp-user");
        var pwdEl = card.querySelector("#smtp-password") || document.getElementById("smtp-password");

        var cleanPwd = ((pwdEl && pwdEl.value) || "").replace(/\s+/g, "");
        if (pwdEl) pwdEl.value = cleanPwd;

        var senderEmail = (emailEl && emailEl.value.trim()) || "";
        var smtpUser = (userEl && userEl.value.trim()) || senderEmail;
        var smtpHost = (hostEl && hostEl.value.trim()) || (senderEmail.indexOf("@gmail.com") !== -1 ? "smtp.gmail.com" : "smtp.gmail.com");
        var smtpPort = (portEl && portEl.value.trim()) || "587";

        var payload = {
          smtp_password: cleanPwd,
          smtp_user: smtpUser,
          smtp_host: smtpHost,
          smtp_port: smtpPort,
          sender_name: (nameEl && nameEl.value.trim()) || "EasiApply Cockpit",
          to_email: senderEmail,
          SENDER_EMAIL: senderEmail,
          SENDER_NAME: (nameEl && nameEl.value.trim()) || "EasiApply Cockpit",
          SMTP_HOST: smtpHost,
          SMTP_PORT: smtpPort,
          SMTP_USER: smtpUser,
          SMTP_PASSWORD: cleanPwd
        };

        if (!payload.SENDER_EMAIL) {
          showToast("Please provide a Connected Email Address before testing.");
          return;
        }
        if (!payload.SMTP_PASSWORD) {
          showToast("Please provide an App Password / Passkey before testing.");
          return;
        }

        var origHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span><span>Testing SMTP...</span>';

        api("/api/settings/test-email", { method: "POST", body: payload })
          .then(function (res) {
            if (res && res.status === "success") {
              btn.innerHTML = '<span class="material-symbols-outlined text-[18px]">done_all</span><span>Connected!</span>';
              updateEmailStatusPill("connected", "Connected & Verified");
              showToast(res.message || "Test email delivered successfully!");
              setTimeout(function () {
                btn.innerHTML = origHtml;
                btn.disabled = false;
              }, 3000);
            } else {
              updateEmailStatusPill("error", "Connection Error");
              showToast("Test email failed: " + ((res && res.detail) || "Unknown error"));
              btn.innerHTML = origHtml;
              btn.disabled = false;
            }
          })
          .catch(function (err) {
            updateEmailStatusPill("error", "Connection Error");
            showToast("Test email failed: " + err.message);
            btn.innerHTML = origHtml;
            btn.disabled = false;
          });
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Outbox Queue & Sent tables loader
  // ---------------------------------------------------------------------------
  function loadSentOutboxTable() {
    var tbody = document.getElementById("sent-outbox-table-body");
    var countPill = document.getElementById("sent-outbox-count-pill");
    var tabSentCount = document.getElementById("badge-sent-count");
    if (!tbody) return;
    api("/api/outreach/sent").then(function (rows) {
      rows = rows || [];
      if (countPill) countPill.textContent = rows.length + " Sent";
      if (tabSentCount) tabSentCount.textContent = rows.length;
      tbody.innerHTML = "";
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="py-12 text-center text-secondary">' +
          '<div class="flex flex-col items-center justify-center gap-2">' +
            '<span class="material-symbols-outlined text-[32px] text-tertiary">send</span>' +
            '<span class="font-body-md text-on-surface font-semibold">No dispatched emails recorded yet</span>' +
            '<span class="font-body-sm text-secondary text-xs">Emails sent through your SMTP gateway will appear here in chronological order.</span>' +
          '</div></td></tr>';
        return;
      }
      rows.forEach(function (r) {
        var tr = document.createElement("tr");
        tr.className = "border-b border-surface-container-high/40 hover:bg-surface-container-low/50 transition-colors";
        tr.innerHTML = '<td class="py-3 px-3 font-semibold text-on-surface">' + escapeHTML(r.to_email || "—") + '</td>' +
          '<td class="py-3 px-3 text-secondary max-w-xs truncate">' + escapeHTML(r.subject || "—") + '</td>' +
          '<td class="py-3 px-3 font-code-terminal text-xs text-tertiary">' + escapeHTML(r.sent_at || "—") + '</td>' +
          '<td class="py-3 px-3 text-xs text-secondary">' + escapeHTML(r.attachment || "None") + '</td>' +
          '<td class="py-3 px-3 text-right"><span class="px-2.5 py-0.5 rounded-full text-xs font-mono bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 font-bold">Delivered</span></td>';
        tbody.appendChild(tr);
      });
    }).catch(function () {});
  }

  function loadOutboxTable() {
    var tbody = document.getElementById("outbox-table-body");
    if (!tbody) return;

    // Check pause status
    api("/api/outreach/queue/status").then(function (res) {
      var isPaused = res && res.paused;
      var pauseLabel = document.getElementById("outbox-pause-label");
      var pauseIcon = document.getElementById("outbox-pause-icon");
      var pauseBtn = document.getElementById("toggle-outbox-pause-btn");
      if (pauseLabel) pauseLabel.textContent = isPaused ? "Resume Auto-Send" : "Pause Auto-Send";
      if (pauseIcon){ var pg = isPaused ? "play_circle" : "pause_circle"; if (window.setXIcon) window.setXIcon(pauseIcon, pg); else pauseIcon.textContent = pg; }
      if (pauseBtn) {
        if (isPaused) {
          pauseBtn.classList.add("bg-amber-500/20", "text-amber-600");
        } else {
          pauseBtn.classList.remove("bg-amber-500/20", "text-amber-600");
        }
      }
    }).catch(function () {});

    // Bind Pause Button once
    var pauseBtn = document.getElementById("toggle-outbox-pause-btn");
    if (pauseBtn && !pauseBtn.__pauseBound) {
      pauseBtn.__pauseBound = true;
      pauseBtn.addEventListener("click", function () {
        api("/api/outreach/queue/toggle-pause", { method: "POST" }).then(function (res) {
          showToast(res && res.paused ? "Auto-send queue PAUSED." : "Auto-send queue RESUMED.");
          loadOutboxTable();
        }).catch(function (err) {
          showToast("Pause toggle failed: " + err.message);
        });
      });
    }

    // Bind Clear Queue Button once
    var clearBtn = document.getElementById("clear-outbox-btn");
    if (clearBtn && !clearBtn.__clearBound) {
      clearBtn.__clearBound = true;
      clearBtn.addEventListener("click", function () {
        showConfirmModal({
          title: "Clear Outbox Queue",
          message: "Are you sure you want to clear all pending emails in the outbox queue?",
          confirmText: "Clear Queue",
          danger: true,
          onConfirm: function () {
            api("/api/outreach/queue/clear", { method: "POST" }).then(function (res) {
              showToast("Cleared " + (res && res.count || 0) + " pending email(s) from outbox.");
              loadOutboxTable();
            }).catch(function (err) {
              showToast("Clear failed: " + err.message);
            });
          }
        });
      });
    }

    api("/api/outreach/queue").then(function (rows) {
      rows = rows || [];
      var tabOutboxCount = document.getElementById("badge-outbox-count");
      if (tabOutboxCount) tabOutboxCount.textContent = rows.length;
      tbody.innerHTML = "";
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="py-12 text-center text-secondary">' +
          '<div class="flex flex-col items-center justify-center gap-2">' +
            '<span class="material-symbols-outlined text-[32px] text-tertiary">inbox</span>' +
            '<span class="font-body-md text-on-surface font-semibold">No emails currently in queue</span>' +
            '<span class="font-body-sm text-secondary text-xs">Select any scored opportunity above and click "Queue for Auto-Send" to begin outreach pacing.</span>' +
          '</div></td></tr>';
        return;
      }
      rows.forEach(function (r) {
        var tr = document.createElement("tr");
        tr.className = "border-b border-surface-container-high/40 hover:bg-surface-container-low/50 transition-colors";
        var statusBadge = r.status === "sent"
          ? '<span class="px-2.5 py-0.5 rounded-full text-xs font-mono bg-primary-container/30 text-on-primary-fixed font-bold">Sent</span>'
          : r.status === "queued"
          ? '<span class="px-2.5 py-0.5 rounded-full text-xs font-mono bg-surface-container-high text-secondary font-bold">Queued</span>'
          : '<span class="px-2.5 py-0.5 rounded-full text-xs font-mono bg-error-container text-error font-bold">' + escapeHTML(r.status) + '</span>';

        var actionBtn = r.status === "queued"
          ? '<button class="text-error hover:underline text-xs font-label-md cancel-queue-btn cursor-pointer" data-cancel-id="' + r.id + '">Cancel</button>'
          : '—';

        tr.innerHTML = '<td class="py-3 px-3 font-semibold text-on-surface">' + escapeHTML(r.to_email || "—") + '</td>' +
          '<td class="py-3 px-3 text-secondary max-w-xs truncate">' + escapeHTML(r.subject || "—") + '</td>' +
          '<td class="py-3 px-3 font-code-terminal text-xs text-tertiary">' + escapeHTML(r.scheduled_at || r.sent_at || "Pending") + '</td>' +
          '<td class="py-3 px-3">' + statusBadge + '</td>' +
          '<td class="py-3 px-3 text-right">' + actionBtn + '</td>';
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll(".cancel-queue-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var rowId = btn.getAttribute("data-cancel-id");
          api("/api/outreach/cancel/" + rowId, { method: "POST" }).then(function () {
            showToast("Outreach cancelled.");
            loadOutboxTable();
          }).catch(function (err) {
            showToast("Cancel failed: " + err.message);
          });
        });
      });
    }).catch(function () {});

    loadSentOutboxTable();
  }

  // ---------------------------------------------------------------------------
  // Outreach Composer & Detail Screen
  // ---------------------------------------------------------------------------
  function bindOutreach() {
    var selector = document.getElementById("outreach-selector");
    if (!selector && currentSection() !== "outreach") return;

    var urlParams = new URLSearchParams(window.location.search);
    var paramId = urlParams.get("id");

    var defaultState = document.getElementById("state-default");
    var queueState = document.getElementById("state-queue");
    var successState = document.getElementById("state-success");
    var backToQueueBtn = document.getElementById("back-to-queue-btn");

    api("/api/applications").then(function (apps) {
      apps = apps || [];
      var tabOppsCount = document.getElementById("badge-opps-count");
      if (tabOppsCount) tabOppsCount.textContent = apps.length;

      if (!apps.length) {
        if (defaultState) defaultState.classList.remove("hidden");
        if (queueState) queueState.classList.add("hidden");
        if (successState) successState.classList.add("hidden");
        return;
      }
      if (defaultState) defaultState.classList.add("hidden");

      apps.sort(function (a, b) {
        return (parseInt(b.match_score, 10) || 0) - (parseInt(a.match_score, 10) || 0);
      });

      var dropdownBtn = document.getElementById("outreach-dropdown-btn");
      var dropdownMenu = document.getElementById("outreach-dropdown-menu");
      var dropdownLabel = document.getElementById("outreach-dropdown-label");
      var dropdownArrow = document.getElementById("outreach-dropdown-arrow");
      var dropdownWrapper = document.getElementById("outreach-dropdown-wrapper");

      function closeCustomDropdown() {
        if (!dropdownMenu) return;
        dropdownMenu.classList.add("hidden");
        if (dropdownArrow) dropdownArrow.classList.remove("rotate-180");
        if (dropdownBtn) dropdownBtn.setAttribute("aria-expanded", "false");
      }

      function openCustomDropdown() {
        if (!dropdownMenu) return;
        dropdownMenu.classList.remove("hidden");
        if (dropdownArrow) dropdownArrow.classList.add("rotate-180");
        if (dropdownBtn) dropdownBtn.setAttribute("aria-expanded", "true");
      }

      function toggleCustomDropdown() {
        if (!dropdownMenu) return;
        if (dropdownMenu.classList.contains("hidden")) {
          openCustomDropdown();
        } else {
          closeCustomDropdown();
        }
      }

      if (dropdownBtn) {
        dropdownBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          toggleCustomDropdown();
        });
      }

      document.addEventListener("click", function (e) {
        if (dropdownWrapper && !dropdownWrapper.contains(e.target)) {
          closeCustomDropdown();
        }
      });

      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          closeCustomDropdown();
        }
      });

      function renderCustomDropdownItems(selectedId) {
        if (!dropdownMenu) return;
        dropdownMenu.innerHTML = "";
        apps.forEach(function (a, index) {
          var isSelected = String(a.id) === String(selectedId);
          var score = Math.max(0, Math.min(100, parseInt(a.match_score, 10) || 0));
          var tier = matchTier(score);
          var roleTitle = getCardRoleTitle(a);
          var item = document.createElement("button");
          item.type = "button";
          item.className = "w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl cursor-pointer transition-all text-left " +
            (isSelected
              ? "bg-primary-container text-on-primary-fixed font-bold shadow-xs"
              : "hover:bg-surface-container-high text-on-surface");
          item.setAttribute("data-id", a.id);
          item.innerHTML =
            '<div class="flex flex-col min-w-0 flex-1">' +
              '<div class="flex items-center gap-2 min-w-0">' +
                '<span class="font-label-md text-label-md truncate ' + (isSelected ? 'text-on-primary-fixed font-bold' : 'text-on-surface font-bold') + '">' + escapeHTML(a.company || "Unknown") + '</span>' +
                '<span class="text-xs opacity-60">•</span>' +
                '<span class="font-body-sm text-body-sm truncate ' + (isSelected ? 'text-on-primary-fixed/90' : 'text-secondary') + '">' + escapeHTML(roleTitle) + '</span>' +
              '</div>' +
            '</div>' +
            '<div class="flex items-center gap-2 shrink-0">' +
              '<span class="px-2 py-0.5 rounded-full font-label-md text-[11px] font-bold ' + (isSelected ? 'bg-black/15 text-on-primary-fixed' : tier.cls) + '">' + score + '%</span>' +
              (isSelected ? '<span class="material-symbols-outlined text-[18px]">check</span>' : '<span class="w-[18px]"></span>') +
            '</div>';

          item.addEventListener("click", function (e) {
            e.stopPropagation();
            closeCustomDropdown();
            loadCurrentJob(index);
          });
          dropdownMenu.appendChild(item);
        });
      }

      if (selector) {
        selector.innerHTML = "";
        apps.forEach(function (a) {
          var opt = document.createElement("option");
          opt.value = a.id;
          var score = Math.max(0, Math.min(100, parseInt(a.match_score, 10) || 0));
          var roleTitle = getCardRoleTitle(a);
          opt.textContent = (a.company || "Unknown") + " — " + roleTitle + " (" + score + "%)";
          selector.appendChild(opt);
        });
      }

      var currentIndex = 0;

      function renderQueueCards(items) {
        var container = document.getElementById("outreach-queue-container");
        var totalPill = document.getElementById("queue-total-pill");
        if (!container) return;
        container.innerHTML = "";

        if (totalPill) {
          totalPill.textContent = items.length + " of " + apps.length + " Opportunities";
        }

        if (!items.length) {
          container.innerHTML = '<div class="p-space-xl text-center bg-surface-container-lowest rounded-2xl border border-surface-container-high/50"><span class="material-symbols-outlined text-[36px] text-tertiary mb-2">search_off</span><p class="font-body-md text-body-md text-secondary">No opportunities match the selected filter or search keyword.</p></div>';
          return;
        }

        items.forEach(function (app) {
          var score = Math.max(0, Math.min(100, parseInt(app.match_score, 10) || 0));
          var tier = matchTier(score);
          var initial = escapeHTML(String(app.company || "?").trim().charAt(0).toUpperCase() || "?");
          var company = escapeHTML(app.company || "Unknown Company");
          var title = escapeHTML(getCardRoleTitle(app));
          var location = escapeHTML(app.location || "Remote");
          var authorName = escapeHTML(app.author_name || "Hiring Team");
          var status = escapeHTML(app.status || "Scraped");
          var hasEmail = Boolean(app.contact_info && app.contact_info.includes("@"));
          var listingUrl = safeLink(getValidListingUrl(app));

          var contactBadge = hasEmail
            ? '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 font-label-sm text-[12px] font-semibold"><span class="material-symbols-outlined text-[14px]">mail</span>Direct Email: ' + escapeHTML(app.contact_info) + '</span>'
            : '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary font-label-sm text-[12px] font-semibold"><span class="material-symbols-outlined text-[14px]">forum</span>Personalized Connection Note Ready</span>';

          var card = document.createElement("div");
          card.className = "flex flex-col md:flex-row items-start md:items-center justify-between gap-space-md p-space-lg hover:bg-surface-container-low/70 transition-colors cursor-pointer group";
          card.setAttribute("title", "Click to open email drafter for " + title);
          card.innerHTML = [
            '<div class="flex items-start gap-space-md min-w-0 flex-1">',
            '  <div class="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center font-headline-md font-black text-on-surface shrink-0 border border-surface-container-high/60 group-hover:border-primary/60 transition-colors">' + initial + '</div>',
            '  <div class="flex flex-col gap-1 min-w-0 flex-1">',
            '    <div class="flex items-center gap-2 flex-wrap">',
            '      <h3 class="font-headline-sm text-headline-sm font-bold text-on-surface group-hover:text-primary transition-colors truncate">' + title + '</h3>',
            '      <span class="px-space-sm py-0.5 rounded-full font-label-md text-label-md font-bold ' + tier.cls + '">' + score + '% Match</span>',
            '      <span class="px-space-sm py-0.5 rounded-full font-code-terminal text-code-terminal text-tertiary bg-surface-container">' + status + '</span>',
            '    </div>',
            '    <div class="flex items-center gap-3 text-secondary font-body-sm text-body-sm flex-wrap">',
            '      <span class="font-semibold text-on-surface">' + company + '</span>',
            '      <span>•</span>',
            '      <span class="flex items-center gap-1"><span class="material-symbols-outlined text-[15px]">location_on</span>' + location + '</span>',
            '      <span>•</span>',
            '      <span class="flex items-center gap-1"><span class="material-symbols-outlined text-[15px]">person</span>' + authorName + '</span>',
            '    </div>',
            '    <div class="flex items-center gap-2 mt-1 flex-wrap">',
            '      ' + contactBadge,
            '    </div>',
            '  </div>',
            '</div>',
            '<div class="flex items-center gap-2 shrink-0 self-end md:self-auto pt-2 md:pt-0">',
            '  <button class="queue-open-composer-btn inline-flex items-center gap-1.5 px-space-md py-2 bg-primary-container text-on-primary-fixed rounded-full font-label-md text-label-md font-bold hover:brightness-105 transition-all shadow-sm cursor-pointer" data-id="' + app.id + '">',
            '    <span class="material-symbols-outlined text-[18px]">edit_note</span>',
            '    <span>Open Email Drafter</span>',
            '  </button>',
            (listingUrl ? '  <a href="' + listingUrl + '" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-space-md py-2 bg-surface-container hover:bg-surface-container-high text-on-surface rounded-full font-label-md text-label-md font-semibold transition-all" onclick="event.stopPropagation();"><span class="material-symbols-outlined text-[16px]">open_in_new</span><span>View Listing</span></a>' : ''),
            '  <span class="material-symbols-outlined text-tertiary group-hover:text-primary group-hover:translate-x-0.5 transition-all text-[22px] hidden md:inline-block ml-0.5">chevron_right</span>',
            '</div>'
          ].join("");

          // Whole card is clickable to open the composer
          card.addEventListener("click", function (e) {
            if (e.target.closest("a, button")) return;
            showDetailView(app.id);
          });

          var openBtn = card.querySelector(".queue-open-composer-btn");
          if (openBtn) {
            openBtn.addEventListener("click", function (e) {
              e.stopPropagation();
              showDetailView(app.id);
            });
          }

          container.appendChild(card);
        });
      }

      var activeQueueFilter = "all";
      var activeQueueSearch = "";
      var activeQueueTimeline = "all";
      var queueCustomStart = null;
      var queueCustomEnd = null;

      function applyQueueFilters() {
        var now = new Date();
        var todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        var yesterdayStart = new Date(todayStart.getTime() - 24 * 60 * 60 * 1000);
        var sevenDaysAgo = new Date(todayStart.getTime() - 7 * 24 * 60 * 1000);

        var filtered = apps.filter(function (a) {
          var hasEmail = Boolean(a.contact_info && a.contact_info.includes("@"));
          if (activeQueueFilter === "email" && !hasEmail) return false;
          if (activeQueueFilter === "inmail" && hasEmail) return false;
          if (activeQueueSearch) {
            var q = activeQueueSearch.toLowerCase();
            var hay = [a.title, a.company, a.author_name, a.location, a.contact_info].filter(Boolean).join(" ").toLowerCase();
            if (hay.indexOf(q) === -1) return false;
          }
          if (activeQueueTimeline !== "all") {
            var rawDate = a.created_at;
            var created = rawDate ? new Date(rawDate) : null;
            if (created && !isNaN(created.getTime())) {
              if (activeQueueTimeline === "today" && created < todayStart) return false;
              if (activeQueueTimeline === "yesterday" && (created < yesterdayStart || created >= todayStart)) return false;
              if (activeQueueTimeline === "7d" && created < sevenDaysAgo) return false;
              if (activeQueueTimeline === "custom") {
                if (queueCustomStart && created < queueCustomStart) return false;
                if (queueCustomEnd && created > queueCustomEnd) return false;
              }
            }
          }
          return true;
        });
        renderQueueCards(filtered);
      }

      var queueSearchInput = document.getElementById("queue-search-input");
      if (queueSearchInput) {
        queueSearchInput.addEventListener("input", function () {
          activeQueueSearch = (queueSearchInput.value || "").trim();
          applyQueueFilters();
        });
      }

      var filterBtns = document.querySelectorAll(".queue-filter-btn");
      filterBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          filterBtns.forEach(function (b) {
            b.classList.remove("active", "bg-primary-container", "text-on-primary-fixed");
            b.classList.add("bg-surface-container", "text-secondary");
          });
          btn.classList.add("active", "bg-primary-container", "text-on-primary-fixed");
          btn.classList.remove("bg-surface-container", "text-secondary");
          activeQueueFilter = btn.getAttribute("data-filter") || "all";
          applyQueueFilters();
        });
      });

      // Queue Timeline Buttons
      var qTimelineBtns = $$(".queue-timeline-btn");
      var qCustomDateCont = document.getElementById("queue-custom-date-container");
      var qStartDateInput = document.getElementById("queue-start-date");
      var qEndDateInput = document.getElementById("queue-end-date");

      qTimelineBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          qTimelineBtns.forEach(function (b) {
            b.classList.remove("active", "bg-primary-container", "text-on-primary-fixed");
            b.classList.add("bg-surface-container", "text-secondary");
          });
          btn.classList.add("active", "bg-primary-container", "text-on-primary-fixed");
          btn.classList.remove("bg-surface-container", "text-secondary");
          activeQueueTimeline = btn.getAttribute("data-timeline") || "all";
          if (qCustomDateCont) {
            if (activeQueueTimeline === "custom") {
              qCustomDateCont.classList.remove("hidden");
            } else {
              qCustomDateCont.classList.add("hidden");
            }
          }
          applyQueueFilters();
        });
      });

      if (qStartDateInput) {
        qStartDateInput.addEventListener("change", function () {
          queueCustomStart = qStartDateInput.value ? new Date(qStartDateInput.value + "T00:00:00") : null;
          applyQueueFilters();
        });
      }
      if (qEndDateInput) {
        qEndDateInput.addEventListener("change", function () {
          queueCustomEnd = qEndDateInput.value ? new Date(qEndDateInput.value + "T23:59:59") : null;
          applyQueueFilters();
        });
      }

      // Applications Section Tabs (Opportunities | Outbox Queue | Sent Emails)
      var appSectionTabs = document.querySelectorAll("#applications-section-tabs .app-section-tab");
      var tabSecOpps = document.getElementById("app-section-opportunities");
      var tabSecOutbox = document.getElementById("app-section-outbox");
      var tabSecSent = document.getElementById("app-section-sent");

      function setAppSectionTab(targetSection) {
        appSectionTabs.forEach(function (btn) {
          var isCurrent = btn.getAttribute("data-section") === targetSection;
          var countPill = btn.querySelector("span[id^='badge-']");
          if (isCurrent) {
            btn.className = "app-section-tab active inline-flex items-center gap-2 px-6 py-2.5 rounded-full bg-primary-container text-on-primary-fixed font-headline-sm text-[14px] sm:text-[15px] font-bold shadow-[0_3px_12px_rgba(182,244,56,0.35)] transition-all cursor-pointer";
            if (countPill) {
              countPill.className = "text-[11px] px-2.5 py-0.5 rounded-full bg-on-primary-fixed/20 text-on-primary-fixed font-mono font-bold";
            }
          } else {
            btn.className = "app-section-tab inline-flex items-center gap-2 px-6 py-2.5 rounded-full text-secondary hover:text-on-surface font-headline-sm text-[14px] sm:text-[15px] font-semibold transition-colors cursor-pointer";
            if (countPill) {
              countPill.className = "text-[11px] px-2.5 py-0.5 rounded-full bg-surface-container-highest text-secondary font-mono font-bold";
            }
          }
        });

        if (tabSecOpps) tabSecOpps.classList.toggle("hidden", targetSection !== "opportunities");
        if (tabSecOutbox) tabSecOutbox.classList.toggle("hidden", targetSection !== "outbox");
        if (tabSecSent) tabSecSent.classList.toggle("hidden", targetSection !== "sent");

        if (targetSection === "outbox") {
          loadOutboxTable();
        } else if (targetSection === "sent") {
          loadSentOutboxTable();
        }
      }

      appSectionTabs.forEach(function (btn) {
        btn.addEventListener("click", function () {
          var target = btn.getAttribute("data-section") || "opportunities";
          setAppSectionTab(target);
        });
      });

      var paramTab = urlParams.get("tab");
      if (paramTab === "outbox" || paramTab === "sent") {
        setAppSectionTab(paramTab);
      }

      function showQueueView() {
        if (queueState) queueState.classList.remove("hidden");
        if (successState) successState.classList.add("hidden");
        var floatApplied = document.getElementById("floating-applied-container");
        if (floatApplied) floatApplied.classList.add("hidden");
        try {
          history.replaceState(null, "", window.location.pathname);
        } catch (e) {}
        applyQueueFilters();
      }

      function showDetailView(appIdOrIndex) {
        var idx = -1;
        if (appIdOrIndex !== undefined && appIdOrIndex !== null) {
          // Always search by DB id first (whether passed as number or string)
          idx = apps.findIndex(function (a) { return String(a.id) === String(appIdOrIndex); });
          // If not found by DB id, allow numeric array index fallback
          if (idx === -1 && typeof appIdOrIndex === "number" && appIdOrIndex >= 0 && appIdOrIndex < apps.length) {
            idx = appIdOrIndex;
          }
        }
        if (idx === -1) idx = 0;
        if (queueState) queueState.classList.add("hidden");
        if (successState) successState.classList.remove("hidden");
        var floatApplied = document.getElementById("floating-applied-container");
        if (floatApplied) floatApplied.classList.remove("hidden");
        try {
          history.replaceState(null, "", window.location.pathname + "?id=" + encodeURIComponent(apps[idx].id));
        } catch (e) {}
        loadCurrentJob(idx);
      }

      if (backToQueueBtn) {
        backToQueueBtn.addEventListener("click", function () {
          showQueueView();
        });
      }

      function updateMarkAppliedButton(app) {
        var btn = document.getElementById("mark-applied-btn");
        var label = document.getElementById("mark-applied-label");
        var icon = document.getElementById("mark-applied-icon");
        if (!btn || !label || !icon) return;
        var isApplied = Boolean(app && String(app.status || "").toLowerCase() === "applied");
        if (isApplied) {
          btn.className = "flex items-center gap-2 px-6 py-3.5 bg-emerald-600 text-white rounded-full font-label-md text-label-md font-bold shadow-[0_8px_32px_rgba(5,150,105,0.38)] hover:scale-105 active:scale-95 transition-all cursor-pointer border border-emerald-400/30 backdrop-blur-sm group";
          if (window.setXIcon) window.setXIcon(icon, "check_circle"); else icon.textContent = "check_circle";
          label.textContent = "Applied ✓";
          btn.title = "Application marked as applied. Click to toggle status.";
        } else {
          btn.className = "flex items-center gap-2 px-6 py-3.5 bg-primary-container text-on-primary-fixed rounded-full font-label-md text-label-md font-bold shadow-[0_8px_32px_rgba(182,244,56,0.38)] hover:scale-105 active:scale-95 transition-all cursor-pointer border border-primary/20 backdrop-blur-sm group";
          if (window.setXIcon) window.setXIcon(icon, "how_to_reg"); else icon.textContent = "how_to_reg";
          label.textContent = "Mark as Applied";
          btn.title = "Mark this application as Applied on LinkedIn";
        }
      }

      function displayJob(app) {
        if (!app) return;
        var id = app.id;
        var score = Math.max(0, Math.min(100, parseInt(app.match_score, 10) || 0));
        var initial = escapeHTML(String(app.company || "?").trim().charAt(0).toUpperCase() || "?");

        var counterPill = document.getElementById("job-counter-pill");
        if (counterPill) counterPill.textContent = (currentIndex + 1) + " of " + apps.length;

        var initialEl = document.getElementById("outreach-company-initial");
        if (initialEl) initialEl.textContent = initial;
        var compNameEl = document.getElementById("outreach-company-name");
        if (compNameEl) compNameEl.textContent = app.company || "Unknown Company";
        var titleEl = document.getElementById("outreach-role-title");
        var roleTitle = getCardRoleTitle(app);
        if (titleEl) titleEl.textContent = roleTitle || "Untitled Role";
        var statusEl = document.getElementById("outreach-status-badge");
        if (statusEl) statusEl.textContent = app.status || "Scraped";
        updateMarkAppliedButton(app);
        var scoreEl = document.getElementById("outreach-score-badge");
        if (scoreEl) {
          scoreEl.textContent = score + "% Match";
          var tier = matchTier(score);
          scoreEl.className = "px-space-sm py-1 rounded-full font-label-md text-label-md font-bold " + tier.cls;
        }
        var locEl = document.getElementById("outreach-location");
        if (locEl) {
          var loc = (app.location || "").trim();
          if (!loc || loc.toLowerCase().includes("unknown")) {
            locEl.textContent = "Location not specified in post";
          } else {
            locEl.textContent = loc;
          }
        }
        var srcEl = document.getElementById("outreach-source-type");
        if (srcEl) srcEl.textContent = app.source_type || "LinkedIn Feed";

        var postUrl = safeLink(getValidListingUrl(app));
        var linkWrap = document.getElementById("outreach-link-wrapper");
        var postLink = document.getElementById("outreach-post-url");
        if (postLink) {
          postLink.href = postUrl || "#";
          if (!postUrl) {
            postLink.classList.add("opacity-40", "pointer-events-none");
          } else {
            postLink.classList.remove("opacity-40", "pointer-events-none");
          }
        }

        var gMatch = document.getElementById("outreach-gauge-match");
        if (gMatch) gMatch.textContent = score + "%";
        var atsScore = parseInt(app.ats_score, 10) || 0;
        var gAts = document.getElementById("outreach-gauge-ats");
        if (gAts) gAts.textContent = atsScore ? atsScore + "%" : "--%";
        var gKw = document.getElementById("outreach-gauge-keywords");
        var rawKws = (app.missing_keywords || "").trim();
        var kwList = rawKws ? rawKws.split(",").map(function(s) { return s.trim(); }).filter(Boolean) : [];
        if (gKw) gKw.textContent = kwList.length > 0 ? kwList.length : "0";

        var reasonEl = document.getElementById("outreach-reasoning");
        if (reasonEl) {
          reasonEl.textContent = app.fit_reasoning || app.tailored_resume_text || "Qualification complete. Candidate skills align with target stack requirements.";
        }


        var recName = document.getElementById("outreach-recruiter-name");
        if (recName) recName.textContent = app.author_name || "Hiring Manager";
        var recInfo = document.getElementById("outreach-recruiter-info");
        if (recInfo) recInfo.textContent = app.author_name ? "Direct Hiring Post Author" : "Company Talent Acquisition";
        var contactEmail = document.getElementById("outreach-contact-email-label");
        if (contactEmail) contactEmail.textContent = app.contact_info || (app.author_name ? "Direct Profile Author" : "Direct Email: Not detected");
        var recLink = document.getElementById("outreach-recruiter-link");
        var authorUrl = safeLink(app.author_profile_url);
        if (recLink) {
          if (authorUrl) {
            recLink.href = authorUrl;
            recLink.classList.remove("opacity-40", "pointer-events-none");
          } else {
            recLink.href = "#";
            recLink.classList.add("opacity-40", "pointer-events-none");
          }
        }

        var descEl = document.getElementById("outreach-full-description");
        if (descEl) descEl.textContent = app.description || "No full description captured for this listing.";

        var cached = (typeof unsavedDrafts !== "undefined" && unsavedDrafts[app.id]) ? unsavedDrafts[app.id] : null;

        var toInput = document.getElementById("outreach-to-email");
        if (toInput) {
          toInput.value = (cached && cached.to !== undefined) ? cached.to : (app.contact_info || "");
          toInput.placeholder = "Enter recruiter email(s) — comma-separated for multiple (e.g. recruiter@company.com, jobs@company.com)";
        }

        var subInput = document.getElementById("outreach-subject");
        if (subInput) {
          subInput.value = (cached && cached.subject)
            ? cached.subject
            : (app.email_draft_subject || ("Application: " + (app.title || "Role") + " — Candidate Introduction"));
        }
        var bodyInput = document.getElementById("email-body-input");
        if (bodyInput) {
          bodyInput.value = (cached && cached.body)
            ? cached.body
            : (app.email_draft_body || "");
        }
        var previewPane = document.getElementById("email-preview-pane");
        if (previewPane) previewPane.textContent = bodyInput ? bodyInput.value : "";

        // LinkedIn Connection Note
        var noteInput = document.getElementById("linkedin-note-input");
        var noteCounter = document.getElementById("linkedin-note-char-count");
        var noteCounterWrap = document.getElementById("linkedin-note-counter");
        function updateNoteCharCount(len) {
          if (noteCounter) noteCounter.textContent = len;
          if (noteCounterWrap) {
            if (len >= 300) {
              noteCounterWrap.className = "font-mono text-[12px] px-2.5 py-0.5 rounded-full bg-red-500/20 text-red-500 font-bold transition-colors";
            } else if (len > 280) {
              noteCounterWrap.className = "font-mono text-[12px] px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-500 font-bold transition-colors";
            } else {
              noteCounterWrap.className = "font-mono text-[12px] px-2.5 py-0.5 rounded-full bg-surface-container text-secondary font-bold transition-colors";
            }
          }
          var bar = document.getElementById("linkedin-note-progress-bar");
          if (bar) {
            var pct = Math.min(100, Math.round((len / 300) * 100));
            bar.style.width = pct + "%";
            bar.className = "h-full rounded-full transition-all duration-150 " + (len >= 300 ? "bg-red-500" : (len > 280 ? "bg-amber-500" : "bg-primary"));
          }
        }

        if (noteInput) {
          var initialNote = (cached && cached.linkedin_note !== undefined)
            ? cached.linkedin_note
            : (app.linkedin_note || "");
          noteInput.value = initialNote;
          updateNoteCharCount(initialNote.length);

          if (!noteInput.__bound) {
            noteInput.__bound = true;
            noteInput.addEventListener("input", function() {
              updateNoteCharCount(noteInput.value.length);
              var curApp = apps[currentIndex];
              if (curApp) {
                if (!unsavedDrafts[curApp.id]) unsavedDrafts[curApp.id] = {};
                unsavedDrafts[curApp.id].linkedin_note = noteInput.value;
                curApp.linkedin_note = noteInput.value;
              }
            });
          }
        }

        var resumeSelect = document.getElementById("outreach-resume-select");
        var attTitle = document.getElementById("outreach-attachment-title");
        var resumeTagBadge = document.getElementById("outreach-resume-tag-badge");
        var resumeTagText = document.getElementById("outreach-resume-tag-text");
        var resumePrimaryBadge = document.getElementById("outreach-resume-primary-badge");
        var resumeIcon = document.getElementById("outreach-resume-icon");
        var viewResumeBtn = document.getElementById("view-resume-preview-btn");

        var resumeUsedName = app.resume_used || "";
        var cachedResumeList = [];

        function updateSelectedResumeDisplay() {
          var selFile = resumeSelect ? resumeSelect.value : (resumeUsedName || "");
          var foundItem = cachedResumeList.find(function (r) { return r.filename === selFile; });

          if (attTitle) {
            attTitle.textContent = selFile ? (selFile + " (Auto-attached on queue)") : "No resume selected";
          }
          if (resumeIcon) {
            var ext = (selFile || "").split(".").pop().toLowerCase();
            var rg = ext === "pdf" ? "picture_as_pdf" : (ext === "docx" ? "article" : "description"); if (window.setXIcon) window.setXIcon(resumeIcon, rg); else resumeIcon.textContent = rg;
          }
          if (resumeTagBadge && resumeTagText) {
            if (foundItem && foundItem.role_tag) {
              resumeTagBadge.classList.remove("hidden");
              resumeTagText.textContent = foundItem.role_tag;
            } else {
              resumeTagBadge.classList.add("hidden");
            }
          }
          if (resumePrimaryBadge) {
            if (foundItem && foundItem.is_primary) {
              resumePrimaryBadge.classList.remove("hidden");
            } else {
              resumePrimaryBadge.classList.add("hidden");
            }
          }
        }

        // Fetch resumes dynamically and populate dropdown cleanly
        api("/api/resumes").then(function (res) {
          cachedResumeList = (res && res.resumes) || [];
          if (!resumeSelect) return;
          resumeSelect.innerHTML = "";
          if (cachedResumeList.length === 0) {
            var optNone = document.createElement("option");
            optNone.value = "";
            optNone.textContent = "No resumes uploaded (Go to Profile)";
            resumeSelect.appendChild(optNone);
          } else {
            var chosenFile = resumeUsedName || "";
            // If resumeUsedName not in list, find primary
            var hasMatch = cachedResumeList.some(function (r) { return r.filename === chosenFile; });
            if (!hasMatch) {
              var prim = cachedResumeList.find(function (r) { return r.is_primary; });
              chosenFile = prim ? prim.filename : cachedResumeList[0].filename;
            }
            cachedResumeList.forEach(function (r) {
              var opt = document.createElement("option");
              opt.value = r.filename;
              opt.textContent = r.filename;
              if (r.filename === chosenFile) opt.selected = true;
              resumeSelect.appendChild(opt);
            });
          }
          updateSelectedResumeDisplay();
        }).catch(function () {
          updateSelectedResumeDisplay();
        });

        if (resumeSelect && !resumeSelect.__bound) {
          resumeSelect.__bound = true;
          resumeSelect.addEventListener("change", function () {
            var chosen = resumeSelect.value;
            var curApp = apps[currentIndex];
            if (curApp && chosen) {
              curApp.resume_used = chosen;
              api("/api/applications/" + encodeURIComponent(curApp.id) + "/update", {
                method: "POST",
                body: { resume_used: chosen }
              }).catch(function () {});
            }
            updateSelectedResumeDisplay();
          });
        }

        if (viewResumeBtn && !viewResumeBtn.__bound) {
          viewResumeBtn.__bound = true;
          viewResumeBtn.onclick = function () {
            var selFile = resumeSelect ? resumeSelect.value : (app.resume_used || "");
            if (selFile) {
              openResumePreviewModal(selFile);
            } else {
              showToast("No resume selected. Upload resumes in Profile section.");
            }
          };
        }
      }

      var unsavedDrafts = {};

      function cacheActiveDraft() {
        if (currentIndex !== null && apps && apps[currentIndex]) {
          var prev = apps[currentIndex];
          var sEl = document.getElementById("outreach-subject");
          var bEl = document.getElementById("email-body-input");
          var tEl = document.getElementById("outreach-to-email");
          var nEl = document.getElementById("linkedin-note-input");
          var sVal = sEl ? sEl.value.trim() : "";
          var bVal = bEl ? bEl.value.trim() : "";
          var tVal = tEl ? tEl.value.trim() : "";
          var nVal = nEl ? nEl.value.trim() : "";
          if (bVal || sVal || tVal || nVal) {
            unsavedDrafts[prev.id] = {
              subject: sEl ? sEl.value : "",
              body: bEl ? bEl.value : "",
              to: tEl ? tEl.value : "",
              linkedin_note: nEl ? nEl.value : ""
            };
          }
        }
      }

      function loadCurrentJob(idx) {
        cacheActiveDraft();
        currentIndex = idx;
        if (currentIndex < 0) currentIndex = apps.length - 1;
        if (currentIndex >= apps.length) currentIndex = 0;
        var basicApp = apps[currentIndex];
        if (selector) selector.value = basicApp.id;
        var score = Math.max(0, Math.min(100, parseInt(basicApp.match_score, 10) || 0));
        var roleTitle = getCardRoleTitle(basicApp);
        if (dropdownLabel) {
          dropdownLabel.textContent = (basicApp.company || "Unknown") + " — " + (roleTitle || "Role") + " (" + score + "%)";
        }
        renderCustomDropdownItems(basicApp.id);
        displayJob(basicApp);
        api("/api/applications/" + encodeURIComponent(basicApp.id)).then(function (fullApp) {
          if (fullApp) {
            apps[currentIndex] = fullApp;
            displayJob(fullApp);
          }
        }).catch(function () {});
      }

      if (selector) {
        selector.addEventListener("change", function () {
          var idx = apps.findIndex(function (a) { return String(a.id) === String(selector.value); });
          if (idx !== -1) loadCurrentJob(idx);
        });
      }

      var prevBtn = document.getElementById("prev-job-btn");
      if (prevBtn) {
        prevBtn.addEventListener("click", function () {
          loadCurrentJob(currentIndex - 1);
        });
      }
      var nextBtn = document.getElementById("next-job-btn");
      if (nextBtn) {
        nextBtn.addEventListener("click", function () {
          loadCurrentJob(currentIndex + 1);
        });
      }

      var tabWrite = document.getElementById("tab-write");
      var tabPrev = document.getElementById("tab-preview");
      var bodyTa = document.getElementById("email-body-input");
      var prevPane = document.getElementById("email-preview-pane");
      if (tabWrite && tabPrev && bodyTa && prevPane) {
        tabWrite.addEventListener("click", function () {
          tabWrite.classList.add("bg-surface-container-lowest", "text-on-surface", "font-semibold");
          tabWrite.classList.remove("text-secondary");
          tabPrev.classList.remove("bg-surface-container-lowest", "text-on-surface", "font-semibold");
          tabPrev.classList.add("text-secondary");
          bodyTa.classList.remove("hidden");
          prevPane.classList.add("hidden");
        });
        tabPrev.addEventListener("click", function () {
          tabPrev.classList.add("bg-surface-container-lowest", "text-on-surface", "font-semibold");
          tabPrev.classList.remove("text-secondary");
          tabWrite.classList.remove("bg-surface-container-lowest", "text-on-surface", "font-semibold");
          tabWrite.classList.add("text-secondary");
          prevPane.textContent = bodyTa.value || "(Empty draft body)";
          prevPane.classList.remove("hidden");
          bodyTa.classList.add("hidden");
        });
      }

      var saveBtn = document.getElementById("save-draft-btn");
      if (saveBtn) {
        saveBtn.addEventListener("click", function () {
          var cur = apps[currentIndex];
          if (!cur) return;
          var sub = (document.getElementById("outreach-subject").value || "").trim();
          var body = (document.getElementById("email-body-input").value || "").trim();
          var to = (document.getElementById("outreach-to-email").value || "").trim();
          var noteVal = (document.getElementById("linkedin-note-input") ? document.getElementById("linkedin-note-input").value : "").trim();
          setLoading(saveBtn, true);
          api("/api/applications/" + encodeURIComponent(cur.id) + "/update", {
            method: "POST",
            body: { email_draft_subject: sub, email_draft_body: body, contact_info: to, linkedin_note: noteVal }
          }).then(function () {
            if (typeof unsavedDrafts !== "undefined" && unsavedDrafts[cur.id]) {
              delete unsavedDrafts[cur.id];
            }
            cur.email_draft_subject = sub;
            cur.email_draft_body = body;
            cur.contact_info = to;
            cur.linkedin_note = noteVal;
            showToast("Draft & LinkedIn note saved successfully.");
          }).catch(function (err) {
            showToast("Save draft failed: " + err.message);
          }).then(function () {
            setLoading(saveBtn, false);
          });
        });
      }

      var regenBtn = document.getElementById("regenerate-draft-btn");
      if (regenBtn) {
        regenBtn.addEventListener("click", function () {
          var cur = apps[currentIndex];
          if (!cur) return;
          setLoading(regenBtn, true);
          api("/api/applications/" + encodeURIComponent(cur.id) + "/draft", { method: "POST", body: {} })
            .then(function (res) {
              if (res && res.email_draft_body) {
                if (typeof unsavedDrafts !== "undefined" && unsavedDrafts[cur.id]) {
                  delete unsavedDrafts[cur.id];
                }
                cur.email_draft_subject = res.email_draft_subject;
                cur.email_draft_body = res.email_draft_body;
                cur.tailored_resume_text = res.tailored_resume_text;
                cur.missing_keywords = res.missing_keywords;
                if (res.linkedin_note) cur.linkedin_note = res.linkedin_note;
                cur.status = "Tailored";

                var subInput = document.getElementById("outreach-subject");
                if (subInput) subInput.value = res.email_draft_subject || "";
                var bodyInput = document.getElementById("email-body-input");
                if (bodyInput) bodyInput.value = res.email_draft_body || "";
                var previewPane = document.getElementById("email-preview-pane");
                if (previewPane) previewPane.textContent = res.email_draft_body || "";

                displayJob(cur);
                showToast("Tailored pitch, resume & LinkedIn note generated!");
              } else {
                showToast("AI generation completed but no draft returned.");
              }
            }).catch(function (err) {
              showToast("Pitch generation failed: " + (err.message || err));
            }).then(function () {
              setLoading(regenBtn, false);
            });
        });
      }

      var sendBtn = document.getElementById("send-outreach-btn");
      if (sendBtn) {
        sendBtn.addEventListener("click", function () {
          var cur = apps[currentIndex];
          if (!cur) return;
          var to = (document.getElementById("outreach-to-email").value || "").trim();
          if (!to) {
            showToast("Please enter recipient email(s), or use LinkedIn Connection Note.");
            return;
          }
          var sub = (document.getElementById("outreach-subject").value || "").trim();
          var body = (document.getElementById("email-body-input").value || "").trim();
          var resumeSelect = document.getElementById("outreach-resume-select");
          var selResumeFile = resumeSelect ? resumeSelect.value : (cur.resume_used || "");
          var scheduleInput = document.getElementById("outreach-schedule-input");
          var scheduledAt = scheduleInput ? (scheduleInput.value || null) : null;
          if (scheduledAt) {
            var schedTime = new Date(scheduledAt).getTime();
            if (schedTime < Date.now() - 60000) {
              showToast("Scheduled time cannot be in the past. Please select a future time or click Clear.");
              return;
            }
          }

          setLoading(sendBtn, true);
          api("/api/applications/" + encodeURIComponent(cur.id) + "/update", {
            method: "POST",
            body: { email_draft_subject: sub, email_draft_body: body, contact_info: to, resume_used: selResumeFile }
          }).then(function () {
            return api("/api/outreach/queue", {
              method: "POST",
              body: {
                app_id: cur.id,
                to_email: to,
                resume_filename: selResumeFile,
                attach_resume: Boolean(selResumeFile),
                scheduled_at: scheduledAt
              }
            });
          }).then(function (res) {
            var ct = (res && res.to_emails && res.to_emails.length) || 1;
            showToast("Queued " + ct + " email(s) for auto-send" + (res && res.position ? " (queue depth #" + res.position + ")" : "") + ".");
            loadOutboxTable();
          }).catch(function (err) {
            showToast("Queue failed: " + err.message);
          }).then(function () {
            setLoading(sendBtn, false);
          });
        });
      }

      // Initialize schedule datetime picker min constraint & clear button
      var scheduleInput = document.getElementById("outreach-schedule-input");
      if (scheduleInput) {
        var nowLocal = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        scheduleInput.min = nowLocal;
      }
      var clearScheduleBtn = document.getElementById("clear-schedule-btn");
      if (clearScheduleBtn && !clearScheduleBtn.__bound) {
        clearScheduleBtn.__bound = true;
        clearScheduleBtn.addEventListener("click", function () {
          if (scheduleInput) scheduleInput.value = "";
          showToast("Schedule reset to Immediate Send.");
        });
      }

      var markAppliedBtn = document.getElementById("mark-applied-btn");
      if (markAppliedBtn && !markAppliedBtn.__bound) {
        markAppliedBtn.__bound = true;
        markAppliedBtn.addEventListener("click", function () {
          var cur = apps[currentIndex];
          if (!cur) return;
          var wasApplied = String(cur.status || "").toLowerCase() === "applied";
          var nextStatus = wasApplied ? "Tailored" : "Applied";
          setLoading(markAppliedBtn, true);
          api("/api/applications/" + encodeURIComponent(cur.id) + "/update", {
            method: "POST",
            body: { status: nextStatus }
          }).then(function () {
            cur.status = nextStatus;
            var statusBadge = document.getElementById("outreach-status-badge");
            if (statusBadge) statusBadge.textContent = nextStatus;
            updateMarkAppliedButton(cur);
            showToast(nextStatus === "Applied" ? "Marked as Applied! Recorded in Application History." : "Status reset to Tailored.");
          }).catch(function (err) {
            showToast("Failed to update status: " + err.message);
          }).finally(function () {
            setLoading(markAppliedBtn, false);
            updateMarkAppliedButton(cur);
          });
        });
      }

      var copyNoteBtn = document.getElementById("copy-linkedin-note-btn");
      if (copyNoteBtn && !copyNoteBtn.__bound) {
        copyNoteBtn.__bound = true;
        copyNoteBtn.addEventListener("click", function () {
          var note = (document.getElementById("linkedin-note-input") || {}).value || "";
          if (!note) {
            showToast("No LinkedIn note written yet. Click 'Generate 300-char Note' to create one.");
            return;
          }
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(note).then(function () {
              showToast("LinkedIn note copied to clipboard! (" + note.length + " chars)");
            }).catch(function () {
              showToast("Copied note to clipboard!");
            });
          } else {
            showToast("Copied note to clipboard!");
          }
        });
      }

      var copyOpenBtn = document.getElementById("copy-open-linkedin-btn");
      if (copyOpenBtn && !copyOpenBtn.__bound) {
        copyOpenBtn.__bound = true;
        copyOpenBtn.addEventListener("click", function () {
          var cur = apps[currentIndex];
          var note = (document.getElementById("linkedin-note-input") || {}).value || "";
          var targetUrl = (cur && cur.author_profile_url) ? cur.author_profile_url : (cur ? getValidListingUrl(cur) : "https://www.linkedin.com");

          function openTarget() {
            if (targetUrl) {
              window.open(targetUrl, "_blank");
            }
          }

          if (note && navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(note).then(function () {
              showToast("Note copied (" + note.length + " chars) & opening LinkedIn profile...");
              openTarget();
            }).catch(function () {
              showToast("Opening LinkedIn profile...");
              openTarget();
            });
          } else {
            if (!note) showToast("Opening LinkedIn profile...");
            openTarget();
          }
        });
      }

      var genNoteBtn = document.getElementById("generate-linkedin-note-btn");
      if (genNoteBtn && !genNoteBtn.__bound) {
        genNoteBtn.__bound = true;
        genNoteBtn.addEventListener("click", function () {
          var cur = apps[currentIndex];
          if (!cur) return;
          setLoading(genNoteBtn, true);
          api("/api/applications/" + encodeURIComponent(cur.id) + "/linkedin-note", { method: "POST", body: {} })
            .then(function (res) {
              if (res && res.linkedin_note) {
                cur.linkedin_note = res.linkedin_note;
                var noteInput = document.getElementById("linkedin-note-input");
                if (noteInput) {
                  noteInput.value = res.linkedin_note;
                  var counter = document.getElementById("linkedin-note-char-count");
                  if (counter) counter.textContent = res.linkedin_note.length;
                  var counterWrap = document.getElementById("linkedin-note-counter");
                  if (counterWrap) {
                    var len = res.linkedin_note.length;
                    counterWrap.className = len >= 300 ? "font-mono text-[12px] px-2.5 py-0.5 rounded-full bg-red-500/20 text-red-500 font-bold transition-colors" : (len > 280 ? "font-mono text-[12px] px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-500 font-bold transition-colors" : "font-mono text-[12px] px-2.5 py-0.5 rounded-full bg-surface-container text-secondary font-bold transition-colors");
                  }
                }
                showToast("300-char LinkedIn note generated! (" + res.linkedin_note.length + " chars)");
              } else {
                showToast("Note generation completed, but returned empty note.");
              }
            }).catch(function (err) {
              showToast("Note generation failed: " + (err.message || err));
            }).finally(function () {
              setLoading(genNoteBtn, false);
            });
        });
      }

      var openComposer = urlParams.get("composer") === "true";
      if (paramId) {
        showDetailView(paramId);
        if (openComposer) {
          setTimeout(function () {
            var ta = document.getElementById("email-body-input");
            if (ta) ta.focus();
          }, 200);
        }
      } else {
        showQueueView();
      }
    }).catch(function () {});

    loadOutboxTable();
    var refreshOutboxBtn = document.getElementById("refresh-outbox-btn");
    if (refreshOutboxBtn) {
      refreshOutboxBtn.addEventListener("click", loadOutboxTable);
    }
    if (!window.__outboxPollTimer) {
      window.__outboxPollTimer = setInterval(function () {
        if (currentSection() === "outreach" && document.getElementById("outbox-table-body")) {
          loadOutboxTable();
        }
      }, 10000);
    }
  }
  function bindOutreachExtras() {
    // Unify resume inputs: outreach uses resume-input, profile uses resume-file-input - bind both to same upload
    var outreachInput = document.getElementById("resume-input");
    if (outreachInput) {
      // Make it behave like profile's input
      outreachInput.addEventListener("change", function(){
        var file = outreachInput.files && outreachInput.files[0];
        if(!file) return;
        showToast("Uploading " + file.name + " ...");
        var fd = new FormData(); fd.append("file", file);
        fetch("/api/upload-resume", {method:"POST", body:fd}).then(function(r){return r.json();}).then(function(data){
          if(data && data.status==="success"){ showToast("Resume parsed and indexed."); setTimeout(function(){ navigateTo("profile"); }, 900); }
          else showToast("Upload failed: " + ((data&&data.detail)||"unknown"));
        }).catch(function(err){ showToast("Upload failed: "+err.message); });
      });
      // Also make dropzone click work if present
      var dz = document.getElementById("dropzone");
      if(dz){
        dz.addEventListener("click", function(){ outreachInput.click(); });
        dz.addEventListener("dragover", function(e){ e.preventDefault(); dz.classList.add("bg-surface-container-low"); });
        dz.addEventListener("dragleave", function(){ dz.classList.remove("bg-surface-container-low"); });
        dz.addEventListener("drop", function(e){
          e.preventDefault(); dz.classList.remove("bg-surface-container-low");
          if(e.dataTransfer.files.length){ outreachInput.files = e.dataTransfer.files; outreachInput.dispatchEvent(new Event("change", {bubbles:true})); }
        });
      }
    }
    // Quick Start with LinkedIn Profile Sync (all state wrappers)
    $$("button").forEach(function(btn){
      if(btn.textContent.indexOf("Quick Start with LinkedIn Profile Sync") !== -1){
        btn.id = "linkedin-sync-btn";
        btn.addEventListener("click", function(){
          api("/api/linkedin-status").then(function(res){
            if (res && res.logged_in) {
              showToast("Active LinkedIn Session: " + (res.account_name || "Connected"));
            } else {
              openLinkedInLoginModal(function(){
                api("/api/linkedin-status").then(paintLinkedInStatus);
              });
            }
          }).catch(function(){ openLinkedInLoginModal(); });
        });
      }
    });
  }
  function moveParsedPreviewToTop() {
    var states = ["default","loading","success","error"];
    states.forEach(function(state){
      var wrapper = document.getElementById("state-"+state);
      if(!wrapper) return;
      // Find the grid left column
      var leftCol = wrapper.querySelector(".xl\\:col-span-8");
      if(!leftCol) leftCol = wrapper;
      var preview = null;
      // Find Parsed Preview card
      var cards = leftCol.querySelectorAll(".bg-surface-container-lowest");
      for(var i=0;i<cards.length;i++){
        if(cards[i].textContent.indexOf("Parsed Profile Preview")!==-1){
          preview = cards[i];
          break;
        }
      }
      if(!preview) return;
      // Find the hero/top banner (first card in leftCol that contains Profile & Resume Setup)
      var hero = null;
      for(var j=0;j<cards.length;j++){
        if(cards[j].textContent.indexOf("Profile & Resume Onboarding")!==-1 || cards[j].textContent.indexOf("Profile & Resume Setup")!==-1){
          hero = cards[j];
          break;
        }
      }
      // Also check for the lime hero banner
      if(!hero){
        var heroes = leftCol.querySelectorAll(".relative.overflow-hidden");
        if(heroes.length) hero = heroes[0].parentElement;
      }
      if(preview && hero && preview !== hero.nextElementSibling){
        // Insert preview right after hero
        hero.parentNode.insertBefore(preview, hero.nextSibling);
      }
    });
  }
  function updateHeaderRealtime() {
    function refresh() {
      api("/api/state").then(function (s) {
        var hasAI = !!(s && s.has_ai_config);
        var hasResume = !!(s && s.has_resume);
        var hasLinkedIn = !!(s && s.has_linkedin);
        var hasEmail = !!(s && s.has_email);

        var statusBadge = document.getElementById("header-system-status");
        if (!statusBadge) {
          var statusHeader = document.querySelector("header .font-code-header");
          statusBadge = statusHeader ? statusHeader.parentElement.querySelector(".status-pill, .rounded-full") : null;
        }
        if (!statusBadge) {
          statusBadge = document.querySelector("header div:not(#header-linkedin-pill) > .status-pill, header div:not(#header-linkedin-pill) > .rounded-full");
        }
        if (statusBadge && statusBadge.id !== "header-linkedin-pill" && !statusBadge.closest("#header-linkedin-pill")) {
          if (hasAI && hasLinkedIn && hasResume) {
            statusBadge.className = "status-pill status-pill-active";
            statusBadge.innerHTML = '<span class="status-pill-dot"></span><span class="status-pill-text">Operational</span>';
          } else if (!hasAI && !hasLinkedIn && !hasResume && !hasEmail) {
            statusBadge.className = "status-pill status-pill-inactive";
            statusBadge.innerHTML = '<span class="status-pill-dot"></span><span class="status-pill-text">Setup Required</span>';
          } else {
            statusBadge.className = "status-pill status-pill-warning";
            statusBadge.innerHTML = '<span class="status-pill-dot"></span><span class="status-pill-text">Partially Operational</span>';
          }
        }

        // Update send quota banner if present (Settings page)
        if (s && document.getElementById("email-daily-quota-banner")) {
          var count = s.today_sent_count || 0;
          var cap = s.daily_send_cap || 50;
          var pct = Math.min(100, Math.round((count / cap) * 100));
          var detail = document.getElementById("email-quota-detail");
          var bar = document.getElementById("email-quota-bar");
          var pctEl = document.getElementById("email-quota-pct");
          if (detail) detail.textContent = count + " dispatched today (Safe Limit: " + cap + ")";
          if (pctEl) pctEl.textContent = pct + "%";
          if (bar) {
            bar.style.width = pct + "%";
            bar.className = "h-full rounded-full transition-all duration-300 " + (pct >= 90 ? "bg-red-500" : (pct >= 70 ? "bg-amber-500" : "bg-primary"));
          }
        }
      }).catch(function () {});

      api("/api/linkedin-status").then(function (res) {
        paintLinkedInStatus(res || "unknown");
      }).catch(function () {});
    }
    refresh();
    setInterval(refresh, 6000);
  }

  // ---------------------------------------------------------------------------
  // Client error telemetry
  // ---------------------------------------------------------------------------
  function reportError(section, message) {
    if (SCRIPT_ERR_REPORTED) return;
    SCRIPT_ERR_REPORTED = true;
    fetch("/api/error", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section: section, message: String(message).slice(0, 500) }),
    }).catch(function () {});
  }

  if (window.addEventListener) {
    window.addEventListener("error", function () {
      var section = currentSection() || "dashboard";
      reportError(section, arguments && arguments[0] && arguments[0].message ? arguments[0].message : "unknown error");
    });
    // reset flag so later real errors still get reported once each per page load
    window.addEventListener("load", function () { SCRIPT_ERR_REPORTED = false; });
  }

  // ---------------------------------------------------------------------------
  // Collapsible Icon-Only Sidebar
  // ---------------------------------------------------------------------------
  function setSidebarMinimized(minimized) {
    if (minimized) {
      document.documentElement.classList.add("sidebar-minimized");
      document.body.classList.add("sidebar-minimized");
      try { localStorage.setItem("easiapply_sidebar_minimized", "true"); } catch (e) {}
    } else {
      document.documentElement.classList.remove("sidebar-minimized");
      document.body.classList.remove("sidebar-minimized");
      try { localStorage.setItem("easiapply_sidebar_minimized", "false"); } catch (e) {}
    }
  }

  function bindSidebarToggle() {
    var isMin = false;
    try {
      isMin = localStorage.getItem("easiapply_sidebar_minimized") === "true";
    } catch (e) {}
    setSidebarMinimized(isMin);

    var toggleBtn = document.getElementById("sidebar-toggle-btn");
    if (toggleBtn && !toggleBtn.__bound) {
      toggleBtn.__bound = true;
      toggleBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        setSidebarMinimized(true);
      });
    }

    var expandBtn = document.getElementById("sidebar-expand-btn");
    if (expandBtn && !expandBtn.__bound) {
      expandBtn.__bound = true;
      expandBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        setSidebarMinimized(false);
      });
    }

    var brandWrapper = document.getElementById("sidebar-brand-wrapper");
    if (brandWrapper && !brandWrapper.__bound) {
      brandWrapper.__bound = true;
      brandWrapper.addEventListener("click", function (e) {
        if (document.body.classList.contains("sidebar-minimized") || document.documentElement.classList.contains("sidebar-minimized")) {
          e.preventDefault();
          e.stopPropagation();
          setSidebarMinimized(false);
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------
  
  function bindActivityConsoleControls() {
    var clearBtns = document.querySelectorAll(".btn-clear-logs, #btn-clear-logs");
    clearBtns.forEach(function (btn) {
      if (btn.__bound) return;
      btn.__bound = true;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        api("/api/logs/clear", { method: "POST" }).catch(function () {});
        lastLogId = 0;
        var feeds = document.querySelectorAll('[id="log-feed"]');
        feeds.forEach(function (f) { f.innerHTML = ""; });
        showToast("Console cleared across all screens");
      });
    });

    var isExpanded = localStorage.getItem("easiapply-console-expanded") === "1";
    var feeds = document.querySelectorAll('[id="log-feed"]');
    feeds.forEach(function (feed) {
      feed.classList.toggle("max-h-96", isExpanded);
      feed.classList.toggle("h-96", isExpanded);
    });

    var toggleBtns = document.querySelectorAll(".btn-toggle-logs, #btn-toggle-logs");
    toggleBtns.forEach(function (btn) {
      btn.setAttribute("data-expanded", isExpanded ? "true" : "false");
      var tIcon = btn.querySelector(".material-symbols-outlined");
      var initialGlyph = isExpanded ? "unfold_less" : "unfold_more";
      if (tIcon) {
        if (window.setXIcon) window.setXIcon(tIcon, initialGlyph);
        else tIcon.textContent = initialGlyph;
      }
      if (btn.__bound) return;
      btn.__bound = true;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        var currentExpanded = localStorage.getItem("easiapply-console-expanded") === "1";
        var nextExpanded = !currentExpanded;
        localStorage.setItem("easiapply-console-expanded", nextExpanded ? "1" : "0");

        var allFeeds = document.querySelectorAll('[id="log-feed"]');
        allFeeds.forEach(function (feed) {
          feed.classList.toggle("max-h-96", nextExpanded);
          feed.classList.toggle("h-96", nextExpanded);
        });

        var glyph = nextExpanded ? "unfold_less" : "unfold_more";
        var allToggles = document.querySelectorAll(".btn-toggle-logs, #btn-toggle-logs");
        allToggles.forEach(function (tb) {
          tb.setAttribute("data-expanded", nextExpanded ? "true" : "false");
          var ic = tb.querySelector(".material-symbols-outlined");
          if (ic) {
            if (window.setXIcon) window.setXIcon(ic, glyph);
            else ic.textContent = glyph;
          }
        });
      });
    });
  }

  function bindApplicationExit() {
    document.addEventListener("click", function (e) {
      var exitBtn = e.target.closest("#app-exit-btn, #settings-exit-btn");
      if (!exitBtn) return;
      e.preventDefault();
      showConfirmModal({
        title: "Shut Down EasiApply?",
        message: "This will cleanly terminate the background Python server process. You can safely close your browser tab once shut down.",
        confirmText: "Shut Down",
        danger: true,
        onConfirm: function () {
          var overlay = document.createElement("div");
          overlay.className = "fixed inset-0 z-[9999] flex items-center justify-center p-6 bg-surface text-center animate-fade-in";
          overlay.innerHTML =
            '<div class="max-w-md flex flex-col items-center gap-4 p-8 rounded-3xl bg-surface-container-lowest border border-surface-container-high shadow-2xl">' +
              '<div class="w-16 h-16 rounded-full bg-error/15 text-error flex items-center justify-center">' +
                '<span class="material-symbols-outlined text-[32px]">stop_sign</span>' +
              '</div>' +
              '<h2 class="font-headline-md text-headline-md text-on-surface font-bold">EasiApply is Shut Down</h2>' +
              '<p class="font-body-md text-body-md text-secondary">The background engine has terminated cleanly. You can now safely close this browser window.</p>' +
            '</div>';
          document.body.appendChild(overlay);

          api("/api/shutdown", { method: "POST" }).catch(function () {});
        }
      });
    });
  }

  function init() {
    bindApplicationExit();
    bindActivityConsoleControls();
    bindSidebarToggle();
    bindNavigation();
    highlightActiveNav();
    bindGlobalDelegation();
    bindUniversalStates();
    moveParsedPreviewToTop();
    updateHeaderRealtime();
    bindDashboard();
    bindScrapeForm();
    bindResumeUpload();
    bindDeleteResume();
    bindProfileUI();
    bindGmailButtons();
    bindProfile();
    bindSettings();
    bindCompactToggle();
    bindCustomDropdowns();
    bindGateway();
    bindLinkedInStatus();
    bindTestEmail();
    bindScrapeStop();
    bindMatches();
    bindAnalytics();
    bindResetData();
    bindResetApps();
    bindResetAll();
    bindOutreach();
    bindOutreachExtras();
    if (document.getElementById("log-feed")) {
      startLogPolling();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();