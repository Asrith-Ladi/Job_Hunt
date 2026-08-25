# Company category filters

Date: 2026-08-20
Queue item: Q-039
Status: implemented

## Request

The official-employer selector showed all registry companies in one long list. Make the
existing Excel workbook categories available as UI choices so a focused group is easier to
browse.

## Decision

Use the category already returned with every registry company. The React selector now offers
counted views in the workbook's canonical order:

1. All
2. MNC
3. Product Companies
4. Startups
5. Mid-Sized Companies
6. Other Companies
7. Selected

The category and text search filters are combined. Switching views never clears selected
companies, including selections made in another group, and the existing maximum of ten
companies remains authoritative. The Selected view provides a quick way to review or remove
the current batch before running it.

## Boundaries

- The categories are registry data, not a second hard-coded company catalog.
- No backend contract, Excel workbook, source adapter, run behavior, or Drive artifact changed.
- Unexpected future registry categories are still displayed after the five canonical groups.
- The controls expose pressed state for assistive technology and become horizontally scrollable
  on narrow screens.

## Verification

The React TypeScript production build passes after the selector and responsive styles were
updated. The nine registry/source contract tests also pass. Browser click-through could not
be performed in the implementation session because no browser surface was connected.
