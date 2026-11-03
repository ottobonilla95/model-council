// Apply the saved theme before the app paints. This stays external for the CSP.
(() => {
  let theme = 'dark';
  try {
    // Keep existing browser preferences when upgrading to Parallax.
    for (const suffix of ['theme', 'preferences']) {
      const previousKey = `council-${suffix}`;
      const key = `parallax-${suffix}`;
      const previous = localStorage.getItem(previousKey);
      if (previous !== null) {
        if (localStorage.getItem(key) === null) localStorage.setItem(key, previous);
        localStorage.removeItem(previousKey);
      }
    }
    if (localStorage.getItem('parallax-theme') === 'light') theme = 'light';
  } catch { /* The default also works when browser storage is unavailable. */ }
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#141619' : '#f7f8fa');
})();
