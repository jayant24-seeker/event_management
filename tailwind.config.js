/** Design tokens live here. Colors point at CSS variables in app/static/src/input.css. */
module.exports = {
  content: ["./app/templates/**/*.html"],
  // Badge styles are picked in Python (events.py), so Tailwind can't see them in templates.
  safelist: ["badge-hot", "badge-soldout", "badge-free", "badge-live", "badge-muted"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "rgb(var(--ink) / <alpha-value>)", soft: "rgb(var(--ink-soft) / <alpha-value>)" },
        paper: { DEFAULT: "rgb(var(--paper) / <alpha-value>)", raised: "rgb(var(--paper-raised) / <alpha-value>)" },
        line: "rgb(var(--line) / <alpha-value>)",
        rani: { DEFAULT: "rgb(var(--rani) / <alpha-value>)", dark: "rgb(var(--rani-dark) / <alpha-value>)" },
        marigold: "rgb(var(--marigold) / <alpha-value>)",
        leaf: "rgb(var(--leaf) / <alpha-value>)",
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', '"Mukta"', "system-ui", "sans-serif"],
        sans: ['"Plus Jakarta Sans"', '"Mukta"', "system-ui", "sans-serif"],
      },
      borderRadius: { card: "1.25rem" },
      boxShadow: {
        poster: "0 18px 40px -18px rgb(var(--ink) / 0.45)",
        lift: "0 28px 60px -20px rgb(var(--rani) / 0.45)",
      },
      maxWidth: { site: "80rem" },
    },
  },
  plugins: [],
};
