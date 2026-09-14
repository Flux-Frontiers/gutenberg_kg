import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ForestApp } from "./game/ForestApp";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ForestApp />
  </StrictMode>,
);
