import type { Config } from 'tailwindcss'

// Token families copied verbatim from brandkit v2 §2
// (brandkit/brandkit/frontend-brandkit-v2.md, reconciled into
// docs/frontend-brandkit.md). Use the class names (bg-primary, text-danger) in
// markup — never a raw hex. Two hexes the spec references without a token name
// are minted here: surface.zebra (#F9FBFB, ResultsTable zebra rows) and
// ink.foreground (#C7DBE0, mono text on the ink KYC/code surface).
const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#0E7569', // brand accent: buttons, links, active step
          hover: '#0A5B51', // button/link hover
          soft: '#E2F3EF', // selected rows, soft badges, hero pill
          strong: '#0A5B51', // accessible teal text on the soft fill
        },
        signal: {
          DEFAULT: '#3BD1B5', // bright accent — dark surfaces only
        },
        ink: {
          DEFAULT: '#0B1D26', // dark surfaces: KYC code block, footer
          foreground: '#C7DBE0', // minted: mono text on the ink surface (7.9:1)
        },
        surface: {
          DEFAULT: '#FFFFFF', // card / panel background
          muted: '#F5F8F8', // page + inset backgrounds
          border: '#DCE6E9', // hairlines, dividers (decorative only)
          foreground: '#0C1E28', // primary text
          subtle: '#4E6B78', // secondary text, labels; form-control borders
          zebra: '#F9FBFB', // minted: ResultsTable zebra rows
        },
        success: {
          DEFAULT: '#177E4D', // footprint = yes, score ≥ 60%
          soft: '#DDF3E4',
          strong: '#116038', // "Yes" badge text, done check
        },
        warning: {
          DEFAULT: '#B45309', // score 30–59%
          soft: '#FCEFD8',
          strong: '#8A4B08', // warning badge text
        },
        danger: {
          DEFAULT: '#C4403A', // footprint = no, failed job, score 0–29%
          soft: '#FBE5E3',
          strong: '#9E332E', // "No" badge text, failure heading
        },
      },
      fontFamily: {
        // Wired to --font-sans / --font-mono in app/globals.css (@fontsource).
        // Fallback stacks match brandkit v2 §3.
        sans: [
          'var(--font-sans)',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          '"Segoe UI"',
          'sans-serif',
        ],
        mono: [
          'var(--font-mono)',
          'ui-monospace',
          '"SF Mono"',
          'Menlo',
          'Consolas',
          'monospace',
        ],
      },
      keyframes: {
        // Soft pulse ring for the active StepProgress dot (brandkit v2 §5).
        // Applied via motion-safe: so prefers-reduced-motion disables it.
        'pulse-ring': {
          '0%': { boxShadow: '0 0 0 0 rgba(14, 117, 105, 0.45)' },
          '70%': { boxShadow: '0 0 0 6px rgba(14, 117, 105, 0)' },
          '100%': { boxShadow: '0 0 0 0 rgba(14, 117, 105, 0)' },
        },
      },
      animation: {
        'pulse-ring': 'pulse-ring 1.8s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}

export default config
