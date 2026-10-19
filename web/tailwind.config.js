/**
 * Tailwind config for the ai-bunker site.
 *
 * A real, self-hosted, content-scanned build rather than the Play CDN — the
 * same choice the dashboard makes, for the same reason: a project whose claim
 * is that nothing leaves the network should not serve a page that fetches a
 * stylesheet from a third party on load.
 *
 * Build, from web/:
 *   npx tailwindcss@3 -i css/tailwind-input.css -o css/app.css --minify
 */
module.exports = {
  content: ['./**/*.html'],
  // The toggle sets data-color-scheme="dark" on <html> (js/theme.js).
  darkMode: ['class', '[data-color-scheme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Roboto', 'system-ui', 'sans-serif'],
        serif: ['Roboto Serif', 'serif'],
        mono: ['Roboto Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        brand: {
          blue: 'rgb(var(--brand-blue-rgb) / <alpha-value>)',
          bluedark: 'rgb(var(--brand-bluedark-rgb) / <alpha-value>)',
          bluelight: 'rgb(var(--brand-bluelight-rgb) / <alpha-value>)',
          navy: 'rgb(var(--brand-navy-rgb) / <alpha-value>)',
          linktext: 'rgb(var(--brand-linktext-rgb) / <alpha-value>)',
          green: 'rgb(var(--brand-green-rgb) / <alpha-value>)',
          red: 'rgb(var(--brand-red-rgb) / <alpha-value>)',
          orange: 'rgb(var(--brand-orange-rgb) / <alpha-value>)',
        },
      },
    },
  },
};
