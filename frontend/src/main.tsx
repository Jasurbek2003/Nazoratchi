import { StrictMode, useMemo } from "react";
import { createRoot } from "react-dom/client";
import { App, createQueryClient } from "./app/App";
import { applyTheme, getThemePref } from "./lib/theme";
import "./styles/index.css";

applyTheme(getThemePref());

function Root() {
  const client = useMemo(createQueryClient, []);
  return <App client={client} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
