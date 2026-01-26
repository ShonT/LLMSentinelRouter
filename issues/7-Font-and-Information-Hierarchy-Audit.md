# Font & Information Hierarchy Audit

## The Issue
The dashboard currently uses a generic sans‑serif font with insufficient visual distinction between labels and values, making key metrics harder to parse at a glance.

## Why It's Critical
Readability directly impacts usability. A high‑quality variable font improves legibility and conveys professionalism. Clear typographic hierarchy (size, weight, color) helps users quickly locate the most important numbers. Monospaced fonts for numerical values and API keys enhance scanability and reduce misreading.

## Proposed Fix
1. Replace the standard sans‑serif with a high‑quality "Geist" or "Inter" variable font.
2. Increase the contrast between "Label" (e.g., Avg Judge Latency) and the "Value" (e.g., 0ms).
3. Use a mono‑spaced font (like JetBrains Mono) for all numerical values and API keys.
4. Update the logo on the main page to use the SVG at `data/vectors/vecotize.svg`.

## Implementation Details
### 1. Font Stack
- **Primary UI font**: `'Geist', 'Inter', -apple‑system, BlinkMacSystemFont, sans‑serif`
- **Code/mono font**: `'JetBrains Mono', 'Consolas', 'Monaco', monospace`

### 2. Typographic Scale
- **Labels** (metric names, section headers): `font‑weight: 500; color: slate‑600 (light) / slate‑300 (dark);`
- **Values** (numbers, counts): `font‑weight: 700; color: slate‑900 (light) / white (dark); font‑size: 1.5–2× label size;`
- **Secondary text** (descriptions, timestamps): `font‑weight: 400; color: slate‑500 (light) / slate‑400 (dark);`

### 3. Monospace Application
- Apply `.font‑mono` to:
  - All numeric displays (latency, count, cost).
  - API keys (both masked and unmasked).
  - Request IDs, model names, and other code‑like tokens.
- Ensure monospace fonts are loaded via a CDN (e.g., Google Fonts) or bundled locally.

### 4. Logo Update
- Replace the current logo with the vector graphic at `data/vectors/vecotize.svg`.
- Verify the SVG file exists; if not, create a placeholder or use an alternative.
- Make the logo theme‑aware (e.g., invert colors for dark mode).

### 5. CSS Integration
- Define CSS custom properties (variables) for fonts, sizes, and colors.
- Update the main stylesheet (or Tailwind configuration) to incorporate the new font stack and typographic rules.
- Test across different screen sizes and browsers.

## Example Before/After
**Before**
```
Avg Judge Latency: 0ms
```
**After**
```
<span class="label">Avg Judge Latency</span>
<span class="value font‑mono">0 ms</span>
```
With distinct color, weight, and spacing.

## Related Components
- `sentinelrouter/dashboard.py` (HTML templates)
- Static CSS files (e.g., `static/styles.css`)
- Tailwind config (`tailwind.config.js` if present)
- Logo asset at `data/vectors/vecotize.svg`

## Performance Considerations
- Font files should be served with proper caching and subsetting if possible.
- Use `font‑display: swap` to avoid blocking rendering.
- Consider self‑hosting fonts to avoid external dependencies.

## Priority
Medium – improves readability and polish, but does not affect core routing logic.