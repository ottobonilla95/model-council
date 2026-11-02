// Apply the saved theme before the app paints. This stays external for the CSP.
(() => {
  let theme = 'dark';
  try {
    if (localStorage.getItem('council-theme') === 'light') theme = 'light';
  } catch { /* The default also works when browser storage is unavailable. */ }
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#141619' : '#f7f8fa');
})();
