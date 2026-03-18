/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['DM Sans', 'system-ui', '-apple-system', 'sans-serif'],
      },
      colors: {
        primary: {
          DEFAULT: '#4A90B8',
          dark: '#3A7196',
          light: '#E8F4F8',
        },
        background: '#FAFBFC',
        surface: '#FFFFFF',
        muted: '#F0F4F7',
        border: 'rgba(26, 43, 61, 0.06)',
        success: '#5CB88A',
        danger: '#E07070',
        text: {
          primary: '#1A2B3D',
          secondary: '#6B7F8E',
        },
      },
      boxShadow: {
        soft: '0 2px 8px rgba(26, 43, 61, 0.06)',
        card: '0 4px 16px rgba(26, 43, 61, 0.08)',
        elevated: '0 8px 32px rgba(26, 43, 61, 0.12)',
      },
      borderRadius: {
        '2xl': '16px',
        'xl': '12px',
      },
    },
  },
  plugins: [],
}
