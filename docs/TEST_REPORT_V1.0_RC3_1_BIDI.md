# CORVAX v1.0 RC3.1 — Bidirectional Layout Test Report

## Build

- TypeScript compilation: PASSED
- Vite production build: PASSED

## Desktop browser measurements (1536 px viewport)

### Arabic / RTL

- Sidebar x-position: 1281 px
- Sidebar width: 240 px
- Content x-position: 0 px
- Computed grid: `1281px 240px`
- Result: sidebar physically on the right — PASSED

### English / LTR

- Sidebar x-position: 0 px
- Sidebar width: 240 px
- Content x-position: 240 px
- Computed grid: `240px 1281px`
- Result: sidebar physically on the left — PASSED

## Mobile rules

- Arabic drawer anchored to right and enters from right.
- English drawer anchored to left and enters from left.
- Navigation chevrons mirror by language direction.
