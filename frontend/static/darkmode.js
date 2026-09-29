(function(){
  // Kinetic Neo-Tech theme switch. Standard: data-theme="light"|"dark" on
  // <html> (see theme.css + root DESIGN.md). Legacy ".dark" class is removed
  // on every apply so the two mechanisms can never fight.
  const KEY="easiapply-theme";
  function isDark(){ return document.documentElement.getAttribute("data-theme") === "dark"; }
  function switchToggles(){
    // Support both the data attribute and legacy duplicate id="darkmode-toggle"
    // (settings.html renders 4 state copies with the same id).
    const byAttr = Array.prototype.slice.call(document.querySelectorAll('[data-darkmode-toggle][role="switch"]'));
    const byId = Array.prototype.slice.call(document.querySelectorAll('[id="darkmode-toggle"]'));
    const seen = new Set();
    return byAttr.concat(byId).filter(function(el){ if(seen.has(el)) return false; seen.add(el); return true; });
  }
  function apply(dark){
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    document.documentElement.classList.remove("dark");
    try {
      localStorage.setItem(KEY, dark ? "dark" : "light");
      localStorage.removeItem("easiapply-theme-class");
    } catch(e){}
    // Sliding switches: move knob + recolor track.
    switchToggles().forEach(function(el){
      el.setAttribute("aria-checked", dark?"true":"false");
      el.classList.toggle("bg-primary-container", dark);
      el.classList.toggle("bg-surface-container-highest", !dark);
      // Knob is the inner dot (w-5), NOT an icon span — pick it explicitly
      // so we never translate a material icon.
      var knob = el.querySelector("span.w-5") || el.querySelector(":scope > span");
      if(knob && knob.classList.contains("material-symbols-outlined") === false){
        knob.classList.toggle("translate-x-6", dark);
        knob.classList.toggle("translate-x-0", !dark);
      }
    });
    // Header icon button: only swap the glyph, never move or recolor it.
    document.querySelectorAll("#darkmode-toggle-header .material-symbols-outlined").forEach(function(icon){
      icon.classList.remove("translate-x-6", "translate-x-0");
      var glyph = dark ? "mode_-__light" : "mode_-__dark";
      if (window.setXIcon) window.setXIcon(icon, glyph); else icon.textContent = glyph;
    });
  }
  window.toggleDarkMode=function(){ apply(!isDark()); };
  window.__darkModeApply = apply;
  window.__isDarkMode = isDark;
  function init(){
    let saved=null;
    try { saved=localStorage.getItem(KEY); } catch(e){}
    // One-time migration from the legacy .dark-class mechanism.
    if (!saved && document.documentElement.classList.contains("dark")) saved = "dark";
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    apply(saved ? saved==="dark" : !!prefersDark);
    document.addEventListener("click", function(e){
      const t=e.target && e.target.closest ? e.target.closest('[data-darkmode-toggle], [id="darkmode-toggle"], #darkmode-toggle-header') : null;
      if(t){ e.preventDefault(); window.toggleDarkMode(); }
    });
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
