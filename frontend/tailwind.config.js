/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        chatBg: "#0f172a",
        chatSidebar: "#090d16",
        chatCard: "#1e293b",
        chatBorder: "#334155",
        brandPrimary: "#3b82f6",
        brandHover: "#2563eb",
      }
    },
  },
  plugins: [],
}
