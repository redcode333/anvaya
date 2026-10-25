import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AppProvider } from "./state";
import "./styles.css";
// Self-hosted fonts (no Google Fonts): only the subsets and weights the UI uses, font-display: swap.
import "@fontsource/noto-sans-devanagari/devanagari-400.css";
import "@fontsource/noto-sans-devanagari/devanagari-600.css";
import "@fontsource/noto-sans-telugu/telugu-400.css";
import "@fontsource/noto-sans-telugu/telugu-600.css";
import "@fontsource/inter-tight/latin-600.css";
import "@fontsource/instrument-serif/latin-400-italic.css";
import devanagariHero from "@fontsource/noto-sans-devanagari/files/noto-sans-devanagari-devanagari-600-normal.woff2?url";
import teluguHero from "@fontsource/noto-sans-telugu/files/noto-sans-telugu-telugu-600-normal.woff2?url";
import interTightHero from "@fontsource/inter-tight/files/inter-tight-latin-600-normal.woff2?url";

// Preload the hero headline weights so the first rotation to Hindi or Telugu doesn't flash a fallback font.
for (const href of [interTightHero, devanagariHero, teluguHero]) {
  const l = document.createElement("link");
  l.rel = "preload"; l.as = "font"; l.type = "font/woff2"; l.crossOrigin = "anonymous"; l.href = href;
  document.head.appendChild(l);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppProvider>
        <App />
      </AppProvider>
    </BrowserRouter>
  </React.StrictMode>,
);

if ("serviceWorker" in navigator && import.meta.env.PROD) {
  navigator.serviceWorker.register("/sw.js").catch(() => undefined);
}
