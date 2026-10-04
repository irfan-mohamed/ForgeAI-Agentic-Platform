/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // ── Primary violet palette — matches the reference design ───────────
        forge: {
          50:  '#f5f3ff',
          100: '#ede9fe',
          200: '#ddd6fe',
          300: '#c4b5fd',
          400: '#a78bfa',
          500: '#8b5cf6',
          600: '#7c3aed',  // main interactive / CTA
          700: '#6d28d9',  // hover deep
          800: '#5b21b6',
          900: '#4c1d95',
          950: '#2e1065',
        },
        // ── Dark palette — used exclusively for the sidebar ─────────────────
        surface: {
          50:  '#f8f7ff',
          100: '#f0eeff',
          200: '#e0dafc',
          300: '#b8b0e0',
          400: '#8880b8',
          500: '#5d5690',
          600: '#423d70',
          700: '#302c57',
          800: '#1e1b4b',  // sidebar background
          900: '#141230',
          950: '#0c0b1e',
        },
        // ── Canvas — light lavender for content-area backgrounds ────────────
        canvas: {
          50:  '#fdfcff',
          100: '#f8f5ff',
          200: '#f1ecff',
          300: '#e7dffe',
        },
      },
      animation: {
        'fade-in':    'fadeIn 0.3s ease-in-out',
        'slide-up':   'slideUp 0.4s ease-out',
        'pulse-slow': 'pulse 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
