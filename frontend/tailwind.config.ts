import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg:         '#0a0a0f',
        surface:    '#13131a',
        's2':       '#1a1a24',
        's3':       '#21212e',
        accent:     '#4f7fff',
        'accent-d': '#2d4fb0',
        success:    '#22c97a',
        warn:       '#f5a623',
        danger:     '#ff4d4d',
        border:     '#1e1e2e',
        muted:      '#6b7280',
        dim:        '#94a3b8',
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-dm-mono)', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        glow:       '0 0 20px rgba(79,127,255,0.15)',
        'glow-sm':  '0 0 10px rgba(79,127,255,0.1)',
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease',
        'slide-in': 'slideIn 0.2s ease',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4,0,0.6,1) infinite',
      },
      keyframes: {
        fadeIn:  { from: { opacity: '0' }, to: { opacity: '1' } },
        slideIn: { from: { opacity: '0', transform: 'translateY(8px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
      },
    },
  },
  plugins: [],
}
export default config
