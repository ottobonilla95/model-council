# Validation — 3 November 2026

- Python behavioral tests: 18 passing. Includes the actual Deep Agents loop with deterministic model doubles, parallel ordering, message and filesystem isolation, structured comparison, partial failures, work limits, cancellation, persistence, export, event replay, source chunks and credential handling.
- Ruff: passing.
- uv lockfile: consistent with project dependencies.
- Vite production build: passing.
- Browser: demo panel completes; combined answer, comparison, originals and source views work; saved conversation reloads and accepts a follow-up; Settings lists editable models and key inputs.
- Responsive check: desktop and 390 × 844 viewport; temporary viewport override reset afterward.
- Browser console: no captured warnings or errors during verification.
- Public source reader smoke test: successfully fetched and extracted a real LangChain documentation page, with bounded chunks. This used no API credentials.
- Simplified UI: question input and inline model selection; model changes preserve drafts and persist across reloads; selecting fewer than two models is prevented. A demo round with GPT, Claude and Gemini completed using the selected IDs. History drawer, comparison tabs and expandable activity verified. Desktop 1280 × 900 and mobile 390 × 844 checked; viewport reset. Production build and Impeccable detector pass; no browser warnings or errors captured.
- Preview: `preview.jpg` shows the simplified question box and model selector.
- Impeccable visual pass: dark and light semantic colors cover the composer, model choices, history, result views and settings. Theme preference persists across reloads; switching themes preserves the current draft. Desktop results and settings, plus the 390 × 844 mobile layout, checked. No horizontal overflow on mobile. Measured dark-theme contrast: body 10.78:1, placeholder 6.90:1, selected model 7.95:1, send button 9.47:1. Production build and JavaScript syntax checks pass. `dark-preview.jpg` records the finished default dark screen.

Live OpenRouter model calls and Tavily search were not executed. No API keys were supplied. Paid endpoint compatibility, answer quality, real token costs and comparative usefulness remain to be evaluated with live credentials.

## Parallax rename

- Renamed application branding, Python and frontend packages, environment options, exports, project folder, and public GitHub repository to Parallax.
- Preserved the existing two local conversations and credentials; renamed the SQLite database and migrated browser theme/model preferences.
- All 18 Python behavioral tests, Ruff, the locked dependency sync, JavaScript syntax checks, and the production frontend build pass.
- Restarted the local app from its renamed folder. Browser title and header show Parallax; dark theme and the three selected models persist. Refreshed both preview images.

## Interface refinement — Frontend Design and Impeccable

- Preserved the existing dark palette and simple chat flow. Added a viewing-plane wordmark/favicon and self-hosted Manrope typography; the font license ships with the public assets.
- Grouped question entry and model selection into a single panel, with a compact follow-up form on result screens. Increased small UI text, input and control sizing; removed the misleading dropdown arrow on the mode toggle.
- Empty questions disable the send action. Submission has a visible pending state. Research activity opens during new runs and preserves the user's disclosure state during streamed updates.
- Production build and JavaScript syntax checks pass. Impeccable's requested detector reported zero findings; no suppressions were added.
- Verified the complete demo flow, saved conversation reopening, question preservation when toggling models, all four result views, settings, and both themes. No paid model/search calls were made. Browser captured no warnings or errors.
- Desktop 1280 × 900 and mobile 390 × 844 verified, with no page overflow. Light-theme contrast ratios: body 7.43:1, placeholder 5.24:1, selected models 5.65:1. Dark theme: body 10.78:1, placeholder 6.90:1, selected models 7.95:1.
- The compact form's Options menu opens toward the inside of the page. Temporary browser viewport overrides were reset. Preview images cover the home screen and sample results on desktop and mobile.
