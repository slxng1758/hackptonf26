import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import { App } from "./App";
import { Infodemic } from "./Infodemic";
import { Village } from "./Village";
import { Petri } from "./Petri";
import { Paper } from "./Paper";
import { Lab } from "./Lab";
import { B2A } from "./B2A";

const VIEWS = [
  { hash: "#/", label: "B2A", el: <B2A /> },
  { hash: "#/lab", label: "Message lab", el: <Lab /> },
  { hash: "#/network", label: "Network", el: <Infodemic /> },
  { hash: "#/village", label: "Village", el: <Village /> },
  { hash: "#/petri", label: "Petri dish", el: <Petri /> },
  { hash: "#/paper", label: "Newspaper", el: <Paper /> },
  { hash: "#/generations", label: "Generations", el: <App /> },
];

function Root() {
  const [hash, setHash] = useState(location.hash || "#/");
  useEffect(() => {
    const f = () => setHash(location.hash || "#/");
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);
  const path = hash.split("?")[0];
  const view = VIEWS.find((v) => v.hash === path) ?? VIEWS[0];
  return (
    <>
      <div key={hash}>{view.el}</div>
      <nav className="fixed left-1/2 top-3 z-50 flex -translate-x-1/2 gap-1 rounded-full border border-white/15 bg-black/60 p-1 backdrop-blur">
        {VIEWS.map((v) => (
          <a key={v.hash} href={v.hash} className={`rounded-full px-3 py-1 font-mono text-[11px] uppercase tracking-widest ${v.hash === view.hash ? "bg-white text-black" : "text-white/60 hover:text-white"}`}>{v.label}</a>
        ))}
      </nav>
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Root /></React.StrictMode>);
