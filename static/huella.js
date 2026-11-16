/* La huella: a guilloche rosette drawn from a file's SHA-256 fingerprint.
   Like the engraving on a banknote: change one cell of the file and the
   drawing changes. Used by the app and by the technical file.

   balanzaHuella(fingerprint, { iris, draw, weight })
     iris    print it in the two brand inks, blended like banknote iris printing
             (the inks are the CSS variables --iris-a and --iris-b of wherever it sits)
     draw    let it draw itself, ring by ring, when it appears
     weight  line weight of the rings, in drawing units (the drawing is 480 wide) */
(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const SIZE = 480;
  let serial = 0;

  const STYLE = `
.huella-svg { display: block; overflow: visible; }
.huella-svg.draw { animation: huella-turn 3.4s cubic-bezier(.16, .84, .24, 1) both; }
.huella-svg.draw .rings path { stroke-dasharray: var(--len); animation: huella-draw 2.5s cubic-bezier(.62, 0, .24, 1) both;
  animation-delay: calc(150ms + var(--layer) * 380ms + var(--ring) * 45ms); }
.huella-svg.draw .ticks { animation: huella-show 1.4s ease-out .1s both; }
@keyframes huella-draw { from { stroke-dashoffset: var(--len); } to { stroke-dashoffset: 0; } }
@keyframes huella-turn { from { transform: rotate(-22deg); } to { transform: rotate(0); } }
@keyframes huella-show { from { opacity: 0; } to { opacity: 1; } }
@media (prefers-reduced-motion: reduce), print { .huella-svg.draw, .huella-svg.draw .rings path, .huella-svg.draw .ticks { animation: none; } }`;

  function make(tag, attrs) {
    const element = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) element.setAttribute(key, value);
    return element;
  }

  function huella(fingerprint, options) {
    const { iris = false, draw = false, weight = 0.8 } = typeof options === "object" && options ? options : {};
    if (!document.getElementById("huella-style")) {
      const style = document.createElement("style");
      style.id = "huella-style";
      style.textContent = STYLE;
      document.head.append(style);
    }

    const bytes = (String(fingerprint).match(/[0-9a-f]{2}/gi) || []).map((pair) => parseInt(pair, 16));
    const svg = make("svg", { viewBox: `0 0 ${SIZE} ${SIZE}`, role: "img", class: "huella-svg" + (draw ? " draw" : ""),
      "aria-label": `Engraved pattern drawn from the file fingerprint ${String(fingerprint).slice(0, 12)}` });
    if (bytes.length < 12) return svg;

    let ink = "currentColor";
    if (iris) {
      const id = `huella-iris-${++serial}`;
      const gradient = make("linearGradient", { id, gradientUnits: "userSpaceOnUse", x1: 40, y1: 60, x2: 440, y2: 420 });
      gradient.append(make("stop", { offset: 0, style: "stop-color: var(--iris-a, #22d8f0)" }), make("stop", { offset: 1, style: "stop-color: var(--iris-b, #2f6bff)" }));
      const defs = make("defs");
      defs.append(gradient);
      svg.append(defs);
      ink = `url(#${id})`;
    }

    const centre = SIZE / 2, radius = SIZE / 2 - 22;
    const rings = make("g", { class: "rings", fill: "none", stroke: ink, "stroke-width": weight, "stroke-linecap": "round" });
    for (let layer = 0; layer < 3; layer++) {
      const [b0, b1, b2, b3] = bytes.slice(layer * 4, layer * 4 + 4);
      const petals = 6 + (b0 % 13), second = 2 + (b1 % 4);
      const base = radius * (0.27 + 0.235 * layer), swing = radius * (0.075 + (b2 / 255) * 0.045), beta = (b3 / 255) * 2 * Math.PI;
      for (let ring = 0; ring < 12; ring++) {
        const phase = (2 * Math.PI * ring) / 12;
        let d = "", length = 0, before = null;
        for (let step = 0; step <= 360; step++) {
          const theta = (2 * Math.PI * step) / 360;
          const r = base + swing * Math.sin(petals * theta + phase) * (0.7 + 0.3 * Math.cos(second * theta + beta));
          const x = centre + r * Math.cos(theta), y = centre + r * Math.sin(theta);
          d += (step ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
          if (before) length += Math.hypot(x - before[0], y - before[1]);
          before = [x, y];
        }
        // --len lets the ring draw itself: a dash as long as the ring, slid into place.
        rings.append(make("path", { d: d + "Z", style: `--len: ${Math.ceil(length) + 4}; --layer: ${layer}; --ring: ${ring}` }));
      }
    }
    let ticks = "";
    for (let i = 0; i < 120; i++) {
      const angle = (2 * Math.PI * i) / 120, inner = radius + (i % 10 === 0 ? 6 : i % 5 === 0 ? 11 : 13.5);
      ticks += `M${(centre + inner * Math.cos(angle)).toFixed(1)} ${(centre + inner * Math.sin(angle)).toFixed(1)}L${(centre + (radius + 17) * Math.cos(angle)).toFixed(1)} ${(centre + (radius + 17) * Math.sin(angle)).toFixed(1)}`;
    }
    svg.append(rings, make("path", { class: "ticks", d: ticks, fill: "none", stroke: ink, "stroke-width": weight * 1.6, "stroke-linecap": "round" }));
    return svg;
  }

  // Draw it again from the start (the app does this when a model is weighed again).
  huella.redraw = (svg) => {
    if (!svg || !svg.classList.contains("draw")) return;
    svg.classList.remove("draw");
    svg.getBoundingClientRect(); // lets the browser notice the class is gone, so the animation restarts
    svg.classList.add("draw");
  };

  window.balanzaHuella = huella;
  // Any element with data-huella="<sha256>" gets its drawing (used by the technical file).
  // Add data-iris for the two brand inks and data-draw to let it draw itself.
  document.addEventListener("DOMContentLoaded", () => {
    for (const holder of document.querySelectorAll("[data-huella]")) {
      holder.prepend(huella(holder.dataset.huella, { iris: "iris" in holder.dataset, draw: "draw" in holder.dataset, weight: Number(holder.dataset.weight) || 0.8 }));
    }
  });
})();
