# Parallax interface

This is a refinement of the existing dark research desk, retaining its palette, single-question entry, model selection, conversation drawer, and four research views. Dark mode is the user's default; light mode remains available.

## Visual system

- Canvas `#141619`; panel `#1d2025`; separators `#30353e`.
- Primary text `#eceef2`; secondary text `#a1a9b6`; action accent `#b7c6ff`.
- Manrope Variable is self-hosted, used for both the interface and headings. Headings use weight 550 with restrained negative tracking; the wordmark uses 650. Body answers retain a 70ch measure.
- A 760px question panel is the visual anchor. Text entry, options, send action, and model choices belong to one bounded surface. Extra configuration stays behind Options and Settings.
- The two offset viewing planes form the Parallax mark. It is geometry, used in the wordmark and favicon, rather than an illustration or background motif.
- Selected researchers have a tinted fill, border, and pressed semantics. Provider colors identify models, not answer quality. Success and warning colors retain their existing meanings.
- Results use readable prose, horizontal tabs, source trails, and expandable original answers. Research activity opens during a new run and keeps the user's disclosure choice during streamed updates.

## Composition and interaction

```
History   Parallax / New                      Mode   Theme   Settings

                 What would you like to know?
            ┌────────────────────────────────────┐
            │ Question                           │
            │ Options                  Enter  Send│
            ├────────────────────────────────────┤
            │ GPT  Claude  Grok  Gemini  Manage   │
            └────────────────────────────────────┘
                         Demo / provider notice
```

The familiar chat composition is intentional: the task is asking and comparing. Distinction comes from the viewing-plane mark, type, and precise control grouping rather than adding a landing page, decorative gradients, or cards unrelated to research.

On narrow screens the heading wraps, keyboard guidance recedes, model controls wrap, and the new-conversation action remains in the history drawer. Research views retain horizontal tab scrolling. Keep visible focus, semantic control names, reduced-motion support, and at least 16px mobile form input text.


## Chat-first behavior (3 November 2026)

The user's primary action is sending a message. Preserve the dark palette, Manrope typography and Parallax mark. Show a continuous thread with compact right-aligned user messages and unboxed assistant prose. Everyday chat has no research tabs, budgets or sample banners. Small badges below the composer show the selected models and mark the one used for everyday chat. Use **Models** beside the badges to open the searchable picker and change the research team. Research replies use the same message layout, with original answers, sources and disagreements behind a single disclosure. Never automatically substitute demo data for user messages.
