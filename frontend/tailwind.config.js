/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        slate: {
          950: "#0e1217", // page
          925: "#131820", // sidebar
          900: "#171d26", // card
          850: "#1c2330", // card hover / inputs
          800: "#252d3a", // borders
          700: "#344052",
        },
        ivory: {
          50: "#fbf8f1",
          100: "#f3ecdc", // primary text
          200: "#e4dac4",
          300: "#c9bfa9", // secondary text
          400: "#9d9483", // muted
          500: "#736c60",
        },
        cat: {
          read: "#d9a55b",
          cook: "#d97757",
          buy: "#8fae7e",
          explore: "#6fa3c7",
          build: "#a98bd4",
          uncategorized: "#8a8f99",
        },
      },
      fontFamily: {
        serif: ['"Fraunces"', "Georgia", "serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(243,236,220,0.04) inset, 0 10px 30px -12px rgba(0,0,0,0.5)",
      },
    },
  },
  plugins: [],
};
