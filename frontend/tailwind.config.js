/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // The UI uses a few half-steps (py-4.5, px-5.5) that Tailwind's default
      // scale doesn't include. Without these tokens the classes emit no CSS
      // and the affected panels lose their padding.
      spacing: {
        "4.5": "1.125rem",
        "5.5": "1.375rem",
      },
      colors: {
        navy: { DEFAULT: "#16324F", deep: "#0F2438" },
        blue: { DEFAULT: "#2C5F8A", tint: "#E4ECF2" },
        paper: "#F6F7F4",
        ink: "#16202B",
        steel: { DEFAULT: "#64748B", light: "#A6B0BC" },
        amber: { DEFAULT: "#E8871E", dark: "#C46E12" },
        green: { DEFAULT: "#2F7D5C", tint: "#E4F0EA" },
        red: { DEFAULT: "#C1443D", tint: "#F6E4E3" },
        border: "#D8DEE3",
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'IBM Plex Sans'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      borderRadius: {
        DEFAULT: "2px",
      },
    },
  },
  plugins: [],
};
