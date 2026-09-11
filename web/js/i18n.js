/* Translations.
   The page is served from file://, where fetch() is blocked, so the strings
   come across the pywebview bridge rather than being loaded by the page. */

const I18n = {
  bundles: {},
  language: "de",
  fallback: "en",

  async load() {
    try {
      this.bundles = (await window.pywebview.api.get_translations()) || {};
    } catch (e) {
      console.error("Could not load translations", e);
      this.bundles = {};
    }
  },

  setLanguage(language) {
    this.language = this.bundles[language] ? language : this.fallback;
    document.documentElement.lang = this.language;
    this.apply();
  },

  t(key, vars) {
    const bundle = this.bundles[this.language] || {};
    const fallback = this.bundles[this.fallback] || {};
    let value = bundle[key] ?? fallback[key];
    // A missing key should be obvious during development, not silently blank.
    if (value === undefined) return key;
    if (vars) {
      for (const [name, replacement] of Object.entries(vars)) {
        value = value.split("{" + name + "}").join(replacement);
      }
    }
    return value;
  },

  apply(root) {
    (root || document).querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = this.t(el.dataset.i18n);
    });
    (root || document).querySelectorAll("[data-i18n-ph]").forEach((el) => {
      el.placeholder = this.t(el.dataset.i18nPh);
    });
    (root || document).querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.title = this.t(el.dataset.i18nTitle);
    });
  },
};
