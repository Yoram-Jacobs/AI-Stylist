/**
 * Tailwind config for the extension.
 *
 * Mirrors the main DressApp design tokens enough to make the popup
 * feel native, but stays small (no plugins, no animation kit) — the
 * extension popup must load instantly on click.
 */
export default {
  content: ['./src/**/*.{js,jsx,html}'],
  theme: {
    extend: {
      colors: {
        // Match dressapp.co's neutral primary; tweak via .env at
        // build-time later if we want a different brand accent here.
        primary:    { DEFAULT: '#0f172a', foreground: '#ffffff' },
        muted:      { DEFAULT: '#f1f5f9', foreground: '#64748b' },
        border:     '#e2e8f0',
        background: '#ffffff',
        foreground: '#0f172a',
        accent:     { DEFAULT: '#0ea5e9', foreground: '#ffffff' },
      },
      fontFamily: {
        sans: ['Figtree', 'system-ui', 'sans-serif'],
      },
      borderRadius: { xl: '0.875rem', '2xl': '1.125rem' },
    },
  },
  plugins: [],
};
