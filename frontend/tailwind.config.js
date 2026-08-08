/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        parchment: "#f6f2e9",
        brass: "#9b6b32",
      },
    },
  },
  plugins: [],
};
