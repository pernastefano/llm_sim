/* ═══════════════════════════════════════════════════════════════════════
   i18n.js — Internationalisation engine

   Translations are loaded from /lang/{code}.json at runtime.

   Usage in HTML:
     data-i18n="key"             → sets element.textContent
     data-i18n-html="key"        → sets element.innerHTML
     data-i18n-placeholder="key" → sets element.placeholder attribute
     data-i18n-title="key"       → sets element.title / document.title

   Language is persisted in localStorage under "llmsim_lang".
   Default: "en".
═══════════════════════════════════════════════════════════════════════ */

const SUPPORTED    = ["en", "it"];
const DEFAULT_LANG = "en";
const STORAGE_KEY  = "llmsim_lang";

let _currentLang = DEFAULT_LANG;
const _cache = {};   // { langCode: translationsObject }

/* ── Loader ──────────────────────────────────────────────────────────── */

function _loadLang(lang) {
  if (_cache[lang]) return Promise.resolve(_cache[lang]);
  return fetch(`/lang/${lang}.json`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status} loading ${lang}.json`);
      return res.json();
    })
    .then(data => {
      _cache[lang] = data;
      return data;
    });
}

/* ── Core helpers ────────────────────────────────────────────────────── */

/**
 * Return the translation for *key* in the active language,
 * falling back to English when the key is missing.
 */
function t(key) {
  return (_cache[_currentLang] || {})[key]
      || (_cache[DEFAULT_LANG]  || {})[key]
      || key;
}

/** Apply all data-i18n* attributes to the document. */
function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-html]").forEach(el => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    el.title = t(el.dataset.i18nTitle);
  });
  document.documentElement.lang = _currentLang;
  const titleKey = document.documentElement.dataset.i18nTitle;
  if (titleKey) document.title = t(titleKey);
  document.querySelectorAll(".lang-switcher button[data-lang]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.lang === _currentLang);
  });
}

/* ── Public API ──────────────────────────────────────────────────────── */

/**
 * Switch to *lang*, fetch its JSON if not already cached, then
 * re-apply translations.  Exposed globally for onclick handlers.
 */
function setLang(lang) {
  if (!SUPPORTED.includes(lang)) return;
  _loadLang(lang).then(() => {
    _currentLang = lang;
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (_) {}
    applyTranslations();
    document.dispatchEvent(new CustomEvent("langchange", { detail: { lang } }));
  });
}

/* ── Init ────────────────────────────────────────────────────────────── */

(function init() {
  let stored = DEFAULT_LANG;
  try { stored = localStorage.getItem(STORAGE_KEY) || DEFAULT_LANG; } catch (_) {}
  _currentLang = SUPPORTED.includes(stored) ? stored : DEFAULT_LANG;

  // Pre-load default + active language, then display
  const toLoad = _currentLang === DEFAULT_LANG
    ? [_loadLang(DEFAULT_LANG)]
    : [_loadLang(DEFAULT_LANG), _loadLang(_currentLang)];

  Promise.all(toLoad).then(() => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", applyTranslations);
    } else {
      applyTranslations();
    }

    // Wire up lang-switcher buttons without inline handlers (CSP compliance)
    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-lang]");
      if (btn) setLang(btn.dataset.lang);
    });
    // Pre-fetch remaining languages in the background for instant switching
    SUPPORTED.forEach(l => _loadLang(l).catch(() => {}));
  });
})();
