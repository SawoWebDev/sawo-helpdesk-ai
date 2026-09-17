import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sawo: {
          light: "#c19a76",
          DEFAULT: "#af8564",
          dark: "#9d745a",
          darker: "#8b6947",
          bg: "#faf8f5",
          border: "#ede3d8",
        },
        night: {
          bg: "#08090b",
          surface: "#121316",
        },
      },
      fontFamily: {
        sans: ["var(--font-montserrat)", "Montserrat", "sans-serif"],
      },
      keyframes: {
        "float-a": {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "33%": { transform: "translate(6%, -8%) scale(1.08)" },
          "66%": { transform: "translate(-5%, 5%) scale(0.94)" },
        },
        "float-b": {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "33%": { transform: "translate(-7%, 6%) scale(0.95)" },
          "66%": { transform: "translate(5%, -5%) scale(1.1)" },
        },
        "float-c": {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "50%": { transform: "translate(4%, -7%) scale(1.06)" },
        },
        // Slow, tiny wander: a few % of the orb's own size, so it's felt more than seen
        "orb-drift": {
          "0%, 100%": { transform: "translate(-50%, -50%) translate(0%, 0%) scale(1)" },
          "25%": { transform: "translate(-50%, -50%) translate(2.5%, -1.5%) scale(1.03)" },
          "50%": { transform: "translate(-50%, -50%) translate(0.5%, 2%) scale(0.985)" },
          "75%": { transform: "translate(-50%, -50%) translate(-2.5%, 0.5%) scale(1.02)" },
        },
        "orb-breathe": {
          "0%, 100%": { opacity: "0.8" },
          "50%": { opacity: "1" },
        },
        "orb-turn": {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        "streak-drift": {
          from: { backgroundPosition: "0 0" },
          to: { backgroundPosition: "240px 0" },
        },      },
      animation: {
        "float-a": "float-a 22s ease-in-out infinite",
        "float-b": "float-b 26s ease-in-out infinite",
        "float-c": "float-c 18s ease-in-out infinite",
        "orb-drift": "orb-drift 70s ease-in-out infinite",
        "orb-breathe": "orb-breathe 16s ease-in-out infinite",
        "orb-turn": "orb-turn 120s linear infinite",
        "streak-drift": "streak-drift 45s linear infinite",      },
    },
  },
  plugins: [],
};

export default config;
