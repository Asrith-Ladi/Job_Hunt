# 039 - Premium UI refresh

Date: 2026-08-31
Queue item: Q-049
Status: implemented locally; production hosting decision pending

## Request

Refresh the React interface so it feels premium, calm, and easy to use for both freshers and experienced candidates. Reduce explanatory text, improve hierarchy, and keep the existing workflow intact.

## Implemented outcome

- Preserved the Search → Results → Applications lifecycle and separate Network workspace.
- Simplified navigation labels, headings, and search guidance.
- Replaced the heavy dark presentation with a brighter indigo/sky visual system.
- Increased key typography and input sizes, clarified selection and focus states, and improved card spacing.
- Rebuilt Search as a visible four-step journey: Sources, Preferences, Source details, and Search.
- Moved the primary search action to a sticky completion card at the end of configuration.
- Reframed Results as the decision stage and Applications as the progress stage.
- Changed the per-job intelligence workspace from a right-aligned drawer to a centered, focused dialog.
- Applied a consistent variable-system font stack and stronger heading/body type hierarchy.
- Promoted Gmail history and source-output menus into centered foreground popovers with a dimmed, blurred underlay and internal scrolling.
- Replaced legacy micro-text across navigation, job rows, tables, metadata, badges, and popup actions with a readable ship-mode type scale.
- Added explicit close, Escape dismissal, backdrop dismissal, scroll locking, and a sticky heading to the Gmail-history dialog.
- Replaced the legacy startup screen with an on-brand premium loading experience and added restrained page/dialog entrance motion with reduced-motion fallbacks.
- Hardened phone and tablet layouts for sticky navigation, touch targets, search steps, empty states, filters, job cards, network tables, dialogs, and narrow 420px screens.
- Kept responsive mobile behavior and reduced-motion support.
- Added no new data access, OAuth scope, persistence, automation, or external dependency.

Follow-up: Discussion 040 supersedes the decorative four-step Search journey and sticky
bottom action. Search now keeps one primary action at the top and collapses advanced filters.

## Verification

- TypeScript validation passes.
- The Vite production build passes and emits the compiled frontend bundle.

## Production gate

The application handles private Gmail, Drive, resume, and LinkedIn-export data. Deployment remains gated on the private hosting/authentication decision in Discussion 007; the UI must not be published as an unauthenticated public application.
