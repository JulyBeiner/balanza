/* Balanza page. Plain JavaScript, no libraries, works offline.
   Text from the server is always added as text (never as HTML). */
(() => {
  "use strict";

  const view = document.getElementById("view");
  const tip = document.getElementById("tip");
  const WORDS = {
    pass: "Pass", warn: "Warning", fail: "Fail", na: "Not measured", missing: "Missing",
    ready: "Evidence ready", attention: "Needs attention", gap: "Gap", none: "None yet",
  };
  const OVERALL = { pass: "All checks pass", warn: "Passes with warnings", fail: "Does not pass" };
  const CATEGORIES = [
    ["data", "Data quality", "Art. 10"],
    ["performance", "Accuracy", "Art. 15"],
    ["calibration", "Calibration", "Art. 15"],
    ["stability", "Stability", "Art. 15"],
    ["fairness", "Bias", "Art. 9 and 10"],
  ];
  const ACTIONS = {
    "model.registered": "Model registered", "validation.run": "Validation run",
    "monitoring.recorded": "Monitoring recorded", "docs.updated": "Answers updated", "evidence.sealed": "Evidence sealed",
  };
  const INK = "#0d1117", COBALT = "#0f52ff", LEAD = "#667080", GRID = "#e8ebef", DASH = "5 4";
  let meta = null;
  let viewRun = 0; // each page that starts loading takes a number; one that finishes late, after a newer page, does not draw
  let scaleAngle = { id: null, angle: 0 };

  // ---------------------------------------------------------------- small helpers

  function build(element, attrs, children) {
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key.startsWith("on")) element.addEventListener(key.slice(2), value);
      else element.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      element.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return element;
  }
  const h = (tag, attrs, ...children) => build(document.createElement(tag), attrs, children);
  const s = (tag, attrs, ...children) => build(document.createElementNS("http://www.w3.org/2000/svg", tag), attrs, children);
  const mark = (status, word) => h("span", { class: `mark ${status}` }, word || WORDS[status] || status);
  const pct = (value, digits = 1) => (100 * value).toFixed(digits) + "%";
  const count = (n, one, many) => `${n.toLocaleString("en-GB")} ${n === 1 ? one : many}`;
  const tally = (c) => `${c.pass} pass, ${count(c.warn, "warning", "warnings")}, ${c.fail} failed`;
  const when = (iso) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  const day = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const still = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const paper = (...children) => h("section", { class: "paper" }, h("div", { class: "wrap" }, ...children));

  // Numbers that count up to their value while a model is weighed.
  let counters = [], countRun = 0;
  function counting(value, format) {
    const node = h("span", null, format(value));
    counters.push({ node, value, format });
    return node;
  }
  function runCounters() {
    if (still()) return;
    const run = ++countRun, mine = counters, start = performance.now();
    const step = (now) => {
      if (run !== countRun) return; // a newer weighing took over
      const t = Math.min((now - start) / 2000, 1), eased = 1 - Math.pow(1 - t, 3);
      for (const item of mine) item.node.textContent = item.format(item.value * eased);
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    const isJson = (response.headers.get("content-type") || "").includes("json");
    const body = isJson ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = body && body.detail;
      throw new Error(typeof detail === "string" ? detail : "The request could not be completed. Check the fields and try again.");
    }
    return body;
  }

  let toastTimer;
  function toast(message) {
    const box = document.getElementById("toast");
    box.textContent = message;
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { box.hidden = true; }, 5000);
  }

  document.addEventListener("mousemove", (event) => {
    const target = event.target.closest ? event.target.closest("[data-tip]") : null;
    if (!target) { tip.hidden = true; return; }
    tip.textContent = target.dataset.tip;
    tip.hidden = false;
    const box = tip.getBoundingClientRect();
    tip.style.left = Math.min(event.clientX + 14, window.innerWidth - box.width - 8) + "px";
    tip.style.top = Math.max(8, event.clientY - box.height - 12) + "px";
  });

  function uploadButton(label, onFile, quiet, accept = ".csv,text/csv") {
    const input = h("input", { type: "file", accept, hidden: true });
    const button = h("button", { type: "button", class: quiet ? "quiet" : null, onclick: () => input.click() }, label);
    input.addEventListener("change", async () => {
      if (!input.files.length) return;
      button.disabled = true;
      try { await onFile(input.files[0]); } catch (error) { toast(error.message); }
      button.disabled = false;
      input.value = "";
    });
    return h("span", null, button, input);
  }

  // ---------------------------------------------------------------- routing

  async function route() {
    const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
    try {
      if (!meta) {
        meta = await api("/api/meta");
        meta.deadline_text = new Date(meta.deadline + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
        document.getElementById("deadline").append(h("b", null, count(meta.days_left, "day", "days")), " until the high-risk rules apply, ", h("span", { style: "white-space:nowrap" }, meta.deadline_text));
      }
      const model = parts[0] === "models" && parts[1], verify = parts[0] === "verify";
      document.body.dataset.view = model ? "model" : verify ? "verify" : "inventory";
      if (model) await showModel(Number(parts[1]), parts[2] || "requirements", parts[3]);
      else if (verify) showVerify();
      else await showInventory();
    } catch (error) {
      document.body.dataset.view = "error";
      view.replaceChildren(paper(h("div", { class: "empty" }, h("h2", null, "This page could not be loaded"), h("p", null, error.message), h("a", { class: "button", href: "#/" }, "Back to all models"))));
    }
  }
  window.addEventListener("hashchange", () => { window.scrollTo(0, 0); route(); });

  // ---------------------------------------------------------------- inventory

  async function showInventory() {
    const run = ++viewRun;
    const models = await api("/api/models");
    if (run !== viewRun) return;
    const form = registerForm();
    form.hidden = true;
    const toggle = h("button", { type: "button", onclick: () => {
      form.hidden = !form.hidden;
      if (form.hidden) return;
      form.scrollIntoView({ block: "center", behavior: still() ? "auto" : "smooth" });
      form.querySelector("input").focus({ preventScroll: true });
    } }, "Register a model");

    const rows = models.map((m) => {
      const open = () => { location.hash = `#/models/${m.id}`; };
      return h("tr", { onclick: open },
        h("td", null, h("a", { class: "name", href: `#/models/${m.id}` }, m.name), h("div", { class: "muted small" }, m.owner)),
        h("td", null, m.use_case_label),
        h("td", null, m.risk_label),
        h("td", null, m.validation ? mark(m.validation) : mark("none")),
        h("td", null, m.monitoring ? mark(m.monitoring, `${WORDS[m.monitoring]}, ${m.monitoring_period}`) : mark("none")),
        h("td", { class: "r num" }, h("span", { class: "meter" }, h("i", null, h("b", { style: `width:${m.readiness}%` })), `${m.readiness}%`)));
    });

    view.replaceChildren(
      h("section", { class: "hero inventory ink" }, h("div", { class: "wrap" },
        h("div", { class: "hero-text" },
          h("h1", null, "Models"),
          h("p", { class: "lede" }, "Every AI model in use, how the EU AI Act classes it, and how much evidence is on record for it."),
          h("div", { class: "actions" }, toggle, h("a", { class: "button quiet", href: "#/verify" }, "Verify a sealed pack"))),
        h("div", { class: "countdown" },
          h("p", { class: "reading" }, meta.days_left.toLocaleString("en-GB")),
          h("p", { class: "reading-what" }, `${meta.days_left === 1 ? "day" : "days"} until the high-risk rules apply, `, h("span", { style: "white-space:nowrap" }, meta.deadline_text))))),
      paper(form,
        models.length
          ? h("table", { class: "inventory" },
              h("thead", null, h("tr", null, ...["Model", "Use", "Classification", "Last validation", "Monitoring"].map((t) => h("th", null, t)), h("th", { class: "r" }, "Evidence ready"))),
              h("tbody", null, rows))
          : h("div", { class: "empty" }, h("h2", null, "No models registered"), h("p", null, "Register the first model to see how the AI Act classes it and what evidence it needs."))));
  }

  function registerForm() {
    const field = (label, name, attrs = {}, hint) =>
      h("label", { class: attrs.wide ? "wide" : null }, label, hint && h("span", { class: "hint" }, hint), h("input", { type: "text", name, ...attrs, wide: null }));
    const basis = h("span", { class: "hint" });
    const select = h("select", { name: "use_case", onchange: showBasis },
      ...Object.entries(meta.use_cases).map(([key, value]) => h("option", { value: key }, value.label)));
    function showBasis() {
      const chosen = meta.use_cases[select.value];
      basis.textContent = `${chosen.risk_label}. ${chosen.basis}`;
    }
    showBasis();
    const error = h("p", { class: "error wide", hidden: true });

    return h("form", { class: "panel form", onsubmit: async (event) => {
        event.preventDefault();
        const body = Object.fromEntries(new FormData(event.target));
        try {
          const created = await api("/api/models", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
          location.hash = `#/models/${created.id}`;
          toast(`${created.name} registered as "${created.risk_label}".`);
        } catch (failure) { error.textContent = failure.message; error.hidden = false; }
      } },
      field("Name of the model", "name", { required: true, minlength: 2, maxlength: 120 }),
      field("Team that owns it", "owner", { required: true, minlength: 2, maxlength: 120 }),
      h("label", { class: "wide" }, "What it is used for", select, basis),
      field("Purpose in one sentence", "purpose", { maxlength: 400, wide: true }),
      field("Type of model", "model_type", { maxlength: 120 }, "For example: logistic regression"),
      field("Version", "version", { maxlength: 40 }, "For example: 1.0"),
      error,
      h("div", { class: "wide" }, h("button", { type: "submit" }, "Register model")));
  }

  // ---------------------------------------------------------------- model page

  async function showModel(id, tab, focus) {
    const run = ++viewRun;
    const data = await api(`/api/models/${id}`);
    if (run !== viewRun) return;
    const m = data.model, v = data.validation;
    const reload = async (message) => { await showModel(id, tab); if (message) toast(message); };
    const tabs = [["requirements", "Requirements"], ["validation", "Validation"], ["monitoring", "Monitoring"], ["documentation", "Documentation"], ["history", "History"]];
    const render = { requirements: tabRequirements, validation: tabValidation, monitoring: tabMonitoring, documentation: tabDocumentation, history: tabHistory }[tab] || tabRequirements;
    const overview = render === tabRequirements; // the first tab opens with the instrument; the others with the title only
    counters = [];

    const sentence = (text) => (text ? text.replace(/[.\s]+$/, "") + "." : null);
    const about = [sentence(m.purpose), sentence(m.owner), sentence([m.model_type, m.version && `version ${m.version}`].filter(Boolean).join(", "))].filter(Boolean).join(" ");
    // Two documents leave Balanza: one page for the person who decides, and the full file for the person who inspects.
    const file = h("div", { class: "actions" },
      h("a", { class: overview ? "button" : "button quiet", href: `/models/${id}/verdict`, target: "_blank", rel: "noopener" }, "Open the one-page verdict"),
      h("a", { class: "button quiet", href: `/models/${id}/technical-file`, target: "_blank", rel: "noopener" }, "Open the technical file"));
    const { ready, attention, gap } = data.evidence.counts;
    const tool = overview ? instrument(m.id, data.evidence, v) : null;

    view.replaceChildren(...[
      h("nav", { class: "tabs ink", "aria-label": "Sections of this model" }, h("div", { class: "wrap" },
        ...tabs.map(([key, label]) => h("a", { href: `#/models/${id}/${key}`, "aria-current": key === tab || (overview && key === "requirements") ? "page" : null }, label)))),
      h("section", { class: overview ? "hero ink" : "hero compact ink" }, h("div", { class: "wrap" },
        h("div", { class: "hero-text" },
          h("a", { class: "back", href: "#/" }, "All models"),
          h("h1", null, m.name),
          h("p", { class: "class" }, h("b", null, m.risk_label), `. ${m.risk_basis}`),
          about && h("p", { class: "about" }, about),
          overview && [
            h("p", { class: "reading" }, counting(data.evidence.readiness, (n) => String(Math.round(n))), "%"),
            h("p", { class: "reading-what" }, m.risk_class === "high"
              ? "of the evidence for the high-risk requirements is ready"
              : "of the evidence is ready. Not mandatory for this use: kept as good practice."),
            h("ul", { class: "tally" },
              h("li", null, mark("ready", count(ready, "requirement", "requirements") + " with evidence ready")),
              attention > 0 && h("li", null, mark("attention", count(attention, "requirement needs", "requirements need") + " attention")),
              h("li", null, mark("gap", count(gap, "requirement", "requirements") + " with a gap"))),
            file]),
        overview ? tool.element : file)),
      overview && v && band(v),
      ...[render(data, reload, focus)].flat().map((part) => (part.matches("section") ? part : paper(part)))].filter(Boolean));
    if (tool) tool.weigh(false);
    // Opened at one place in the page (a step of the route leads there): bring it into view.
    const place = focus && document.getElementById(`at-${focus}`);
    if (place) place.scrollIntoView({ block: "center" });
  }

  // The band of readings under the instrument: the numbers of the last validation.
  function band(v) {
    const shown = (id, key) => {
      const check = v.checks.find((c) => c.id === id && c.value !== null);
      if (!check) return null;
      const written = new RegExp(key + " ([0-9.]+)").exec(check.display); // the number exactly as the check reports it
      return written ? Number(written[1]) : check.value;
    };
    const three = (n) => n.toFixed(3);
    const readings = [
      [shown("performance.auc", "AUC"), "AUC. Tells good and bad payers apart."],
      [shown("performance.ks", "KS"), "KS. Separation between payers."],
      [shown("stability.score", "PSI"), "PSI. Scores behave the same on unseen loans."],
    ].filter(([value]) => value !== null).map(([value, label]) =>
      h("div", null, h("p", { class: "value" }, counting(value, three)), h("p", { class: "label" }, label)));
    return h("section", { class: "band" }, h("div", { class: "wrap" },
      h("div", { class: "band-head" },
        h("p", null, h("b", null, `Last validation, ${day(v.created_at)}`)),
        h("p", null, `${v.dataset_name}, ${count(v.n_rows, "loan", "loans")}. The engraving above is drawn from its fingerprint, `,
          h("span", { class: "hash" }, v.dataset_sha256.slice(0, 12) + "…"))),
      h("div", { class: "readings" }, ...readings,
        h("div", null,
          h("p", { class: "value" }, counting(v.counts.pass, (n) => String(Math.round(n))), `/${v.checks.length}`),
          h("p", { class: "label" }, `checks pass. ${count(v.counts.warn, "warning", "warnings")}, ${v.counts.fail} failed.`)))));
  }

  // ---- requirements

  function tabRequirements(data) {
    const evidence = data.evidence;
    return h("div", null,
      data.model.risk_class !== "high" && h("p", { class: "lede", style: "margin:0 0 40px" },
        "This use is not classed as high-risk, so the requirements below are not mandatory for it. They are kept here as good practice."),
      theRoute(data.model.id, data.route),
      h("h2", { class: "register-title" }, "The requirements, one by one"),
      h("ul", { class: "register" }, ...evidence.requirements.map((r) => {
        const [, number, extra] = /^Art\. (\d+)(.*)$/.exec(r.article) || [null, r.article, ""];
        return h("li", null,
          h("p", { class: "article" }, h("span", { class: "art" }, "Art."), number, extra.trim() && h("span", { class: "plus" }, extra.trim())),
          h("div", { class: "what" }, h("h3", null, r.title), h("p", null, r.plain),
            h("ul", { class: "evidence" }, ...r.items.map((item) =>
              h("li", null, mark(item.status), h("span", null, item.label), h("span", null, item.detail))))),
          h("span", { class: "state" }, mark(r.state)));
      })),
      h("p", { class: "note" }, "\"Evidence ready\" means the tests pass and the written answers exist. It is not a statement that the model complies with the AI Act."));
  }

  // The route: what to do next, in order, until the evidence is ready. The first step is the
  // one to take today; each says how far it moves the reading.
  function theRoute(modelId, plan) {
    if (!plan.steps.length) {
      return h("div", { class: "route done" }, h("h2", null, "Nothing left to do"),
        h("p", { class: "lede" }, "The evidence for every requirement is ready. Keep recording a month of production loans every month."));
    }
    const list = (items) => items.length > 1 ? items.slice(0, -1).join(", ") + " and " + items.at(-1) : items[0];
    let reading = plan.readiness;
    const steps = plan.steps.map((step) => {
      const after = step.readiness_after;
      let effect;
      if (after === null) effect = `Needed for ${list(step.articles)}. The reading moves once this is done.`;
      else if (after > reading) effect = `${step.hypothetical ? "Once solved, evidence" : "Evidence"} ready goes from ${reading}% to ${after}%.` + (step.closes.length ? ` Closes ${list(step.closes)}.` : "");
      else effect = `Needed for ${list(step.articles)}. The reading moves when the other steps for ${step.articles.length > 1 ? "them" : "it"} are done.`;
      if (after !== null) reading = after;
      const place = step.kind === "write" ? `/${step.field}` : step.id === "act.fairness" ? "/what-if" : "";
      return h("li", { class: step.number === 1 ? "first" : null },
        h("span", { class: "n" }, step.number),
        h("div", { class: "what" }, h("h3", null, step.title), h("p", null, step.what), h("p", { class: "effect" }, effect)),
        h("a", { class: step.number === 1 ? "button" : "button quiet", href: `#/models/${modelId}/${step.tab}${place}` }, step.action));
    });
    return h("div", { class: "route" },
      h("h2", null, "What to do next"),
      h("p", { class: "lede" }, `${count(plan.steps.length, "step", "steps")} until the evidence for every requirement is ready. Start with the first.`),
      h("ol", { class: "steps" }, ...steps));
  }

  // A balance with weights on its pans. load() puts the weights on, swing() lets it move to
  // where they take it, until it settles.
  function balance(leftLabel, rightLabel) {
    const cx = 220, cy = 104, arm = 150, drop = 62, needle = 76;
    const stroke = (cls, width, d) => s("path", { class: cls, d, fill: "none", "stroke-width": width, "stroke-linecap": "round" });
    let arc = "";
    for (let i = -9; i <= 9; i++) {
      const a = (i * 3 * Math.PI) / 180, inner = needle + (i === 0 ? 8 : i % 3 === 0 ? 13 : 16);
      arc += `M${(cx + inner * Math.sin(a)).toFixed(1)} ${(cy - inner * Math.cos(a)).toFixed(1)}L${(cx + (needle + 22) * Math.sin(a)).toFixed(1)} ${(cy - (needle + 22) * Math.cos(a)).toFixed(1)}`;
    }
    const weights = (items) => items.map((kind, index) => {
      const x = -42 + (index % 4) * 28, y = -15 - Math.floor(index / 4) * 21;
      if (kind === "ready") return s("circle", { class: "weight ready", cx: x, cy: y, r: 7 });
      if (kind === "attention") return s("path", { class: "weight attention", d: `M${x} ${y - 8}L${x + 8} ${y + 7}H${x - 8}Z` });
      return s("rect", { class: "weight gap", x: x - 7, y: y - 7, width: 14, height: 14 });
    });
    const strings = `M0 0L-56 ${drop}M0 0L56 ${drop}`, plate = `M-62 ${drop}H62`;
    const pan = () => {
      const load = s("g", { transform: `translate(0 ${drop})` });
      const group = s("g", null, stroke("cut", 5, strings), stroke("cut", 6.5, plate), stroke("line", 1.2, strings), stroke("line", 1.9, plate), load);
      return { group, load };
    };
    const stand = `M${cx} ${cy}V214M${cx - 52} 214H${cx + 52}`;
    const beamCut = stroke("cut", 6.5, ""), beam = stroke("line", 1.9, ""), fielCut = stroke("cut", 7, ""), fiel = stroke("fiel", 2.2, "");
    const left = pan(), right = pan();
    const picture = s("svg", { class: "balance", viewBox: "0 0 440 248", role: "img" },
      stroke("cut", 6.5, stand), stroke("cut", 4.5, arc), stroke("line", 1, arc), stroke("line", 1.9, stand),
      beamCut, fielCut, beam, fiel, left.group, right.group,
      s("circle", { class: "pivot", cx, cy, r: 4.6 }),
      s("text", { x: cx - arm, y: 240 }, leftLabel), s("text", { x: cx + arm, y: 240 }, rightLabel));

    let at = 0, target = 0, run = 0;
    function draw(angle) {
      at = angle;
      const rad = (angle * Math.PI) / 180, dx = arm * Math.cos(rad), dy = arm * Math.sin(rad);
      const across = `M${cx - dx} ${cy - dy}L${cx + dx} ${cy + dy}`, up = `M${cx} ${cy}L${cx + needle * Math.sin(rad)} ${cy - needle * Math.cos(rad)}`;
      beamCut.setAttribute("d", across); beam.setAttribute("d", across);
      fielCut.setAttribute("d", up); fiel.setAttribute("d", up);
      left.group.setAttribute("transform", `translate(${cx - dx} ${cy - dy})`);
      right.group.setAttribute("transform", `translate(${cx + dx} ${cy + dy})`);
    }
    // Weights on: the good ones on the left pan, the open ones on the right. Returns where it will rest.
    function load({ ready, attention, gap }) {
      const open = attention + gap;
      left.load.replaceChildren(...weights(Array(ready).fill("ready")));
      right.load.replaceChildren(...weights([...Array(gap).fill("gap"), ...Array(attention).fill("attention")]));
      picture.setAttribute("aria-label", `A balance. ${ready} on the pan "${leftLabel}", ${open} on the pan "${rightLabel}".`);
      target = ((open - ready) / Math.max(ready + open, 1)) * 12; // degrees
      return target;
    }
    function swing(from = at) {
      const mine = ++run, to = target;
      if (still() || from === to) { draw(to); return; }
      draw(from);
      const start = performance.now();
      const step = (now) => {
        if (mine !== run) return;
        const t = (now - start) / 1000;
        draw(to + (from - to) * Math.exp(-1.25 * t) * Math.cos(4.4 * t)); // swings, then rests
        if (t < 3.8) requestAnimationFrame(step); else draw(to);
      };
      requestAnimationFrame(step);
    }
    draw(0);
    return { picture, load, swing, draw };
  }

  // The instrument. La huella of the validated file, and in front of it the balance: evidence on
  // the left pan, open work on the right. The heavier side goes down and the needle (el fiel)
  // shows by how much on its graduated arc. Weighing draws the engraving, swings the balance
  // until it settles, and counts the numbers up.
  function instrument(modelId, evidence, validation) {
    const scale = balance("Evidence ready", "Still open");
    const target = scale.load(evidence.counts);
    scale.draw(target);
    function swing(again) {
      // It starts where the balance last rested for this model, or tipped as if just loaded.
      let from = again ? target - 9 : scaleAngle.id === modelId ? scaleAngle.angle : target - 13;
      if (Math.abs(from - target) < 0.5) from = target - 7;
      scaleAngle = { id: modelId, angle: target };
      scale.swing(from);
    }

    const seal = validation && window.balanzaHuella(validation.dataset_sha256, { iris: true, draw: true, weight: 0.5 });
    function weigh(again) {
      if (again && seal) window.balanzaHuella.redraw(seal);
      swing(again);
      runCounters();
    }
    const element = seal
      ? h("button", { type: "button", class: "instrument", "aria-label": "Weigh again: replay the drawing and the balance", onclick: () => weigh(true) }, seal, scale.picture)
      : h("div", { class: "instrument bare" }, scale.picture);
    return { element, weigh };
  }

  // ---- validation

  function tabValidation(data, reload) {
    const id = data.model.id, v = data.validation;
    const outcome = (r) => `Validation recorded: ${tally(r.counts)}.`;
    const actions = h("div", { class: "actions" },
      uploadButton("Validate a scored file", async (file) => {
        const body = new FormData(); body.append("file", file);
        await reload(outcome(await api(`/api/models/${id}/validations`, { method: "POST", body })));
      }),
      h("button", { type: "button", class: "quiet", onclick: async (event) => {
        event.target.disabled = true;
        try { await reload(outcome(await api(`/api/models/${id}/validations/demo`, { method: "POST" }))); } catch (error) { toast(error.message); event.target.disabled = false; }
      } }, "Validate with the demo data"),
      h("a", { class: "button quiet", href: "/api/demo/dataset.csv", download: "" }, "Download the demo file"));
    const format = h("p", { class: "muted small", style: "margin-top:10px;max-width:78ch" },
      "A scored file is a CSV with one loan per row. It needs a column \"score\" (probability of default, 0 to 1) and a column \"default\" (1 = not repaid, 0 = repaid). Add \"approved\", \"sample\", \"gender\" and \"age\" to unlock the stability and bias checks.");

    if (!v) {
      return h("div", { class: "empty" }, h("h2", null, "No validation on record"),
        h("p", null, "Upload the model's scored loans, or use the invented demo data to see how an inspection looks."), actions, format);
    }

    const groups = CATEGORIES.map(([key, title, article]) => {
      const checks = v.checks.filter((c) => c.category === key);
      if (!checks.length) return null;
      return [
        h("h3", null, title, h("span", null, `Evidence for ${article}`)),
        ...checks.map((c) => h("details", { class: `check ${c.status}`, open: c.status === "fail" },
          h("summary", null, mark(c.status), h("span", null, c.name), h("span", { class: "value" }, c.display)),
          h("div", { class: "why" }, h("p", null, c.meaning), h("p", { class: "muted" }, `Rule: ${c.rule}.`)))),
      ];
    });

    return [h("div", null,
      h("div", { class: "head" },
        h("div", null,
          h("div", { class: "summary" }, mark(v.overall, OVERALL[v.overall]),
            h("span", { class: "num" }, tally(v.counts))),
          h("p", { class: "muted small", style: "margin-top:8px" },
            `${v.dataset_name}, ${count(v.n_rows, "loan", "loans")}` + (v.has_samples ? ` (${v.n_evaluated.toLocaleString("en-GB")} kept aside to measure)` : "") + `, run ${when(v.created_at)}`),
          h("p", { class: "muted small" }, "File fingerprint ", h("span", { class: "hash" }, v.dataset_sha256.slice(0, 24) + "…"))),
        actions),
      format,
      h("div", { class: "checks" }, groups)),
      whatIf(v),
      h("div", null,
      h("div", { class: "charts", style: "margin-top:0" },
        calibrationChart(v.charts.calibration),
        scoresChart(v.charts.scores, v.threshold),
        ...Object.entries(v.charts.fairness).map(([attribute, rows]) => groupChart(attribute, rows))),
      h("p", { class: "note" }, "The limits used here are common industry conventions, set as defaults. They are not legal thresholds; each lender should review and justify its own."))];
  }

  // What if the cut-off moved? Arithmetic on the validated file, as if every loan scored below
  // the cut-off were approved. The slider moves the cut-off; the numbers, the bias checks and the
  // balance follow. It shows consequences and recommends nothing.
  function whatIf(v) {
    const rows = v.what_if;
    if (!rows || !rows.length) {
      return h("section", { class: "whatif ink", id: "at-what-if" }, h("div", { class: "wrap" },
        h("h2", null, "What if the cut-off moved?"),
        h("p", { class: "lede" }, "This validation was recorded before Balanza could move the cut-off. Validate the file again to try other cut-offs.")));
    }
    const inUse = Math.round(100 * v.threshold);
    const at = (percent) => rows.find((row) => Math.round(100 * row.cut_off) === percent) || rows[0];
    const cutOff = h("output", { class: "reading", for: "cut-off" });
    const facts = [["approval_rate", "of the loans would be approved"], ["default_rate", "of the approved loans did not repay"], ["good_rejected", "of the people who repaid would be turned away"]]
      .map(([key, label]) => ({ key, node: h("p", { class: "value" }), label }));
    const bias = h("ul", { class: "whatif-bias" });
    const scale = rows[0].bias.length ? balance("Pass", "Warning or fail") : null;
    const back = h("button", { type: "button", class: "quiet", onclick: () => { slider.value = inUse; show(true); } }, `Back to ${inUse}%, the cut-off in use`);
    const slider = h("input", { type: "range", id: "cut-off", min: Math.round(100 * rows[0].cut_off), max: Math.round(100 * rows.at(-1).cut_off), step: 1, value: inUse,
      "aria-label": "Approve loans scored below this probability of default", oninput: () => show(true) });

    function show(moving) {
      const percent = Number(slider.value), row = at(percent);
      cutOff.textContent = `${percent}%`;
      slider.style.setProperty("--fill", `${(100 * (percent - slider.min)) / (slider.max - slider.min)}%`);
      for (const fact of facts) fact.node.textContent = row[fact.key] === null ? "–" : pct(row[fact.key]);
      bias.replaceChildren(...row.bias.map((measure) => h("li", null, mark(measure.status), h("span", null, measure.name), h("span", { class: "value" }, measure.display))));
      back.style.visibility = percent === inUse ? "hidden" : "visible";
      if (!scale) return;
      scale.load({
        ready: row.bias.filter((measure) => measure.status === "pass").length,
        attention: row.bias.filter((measure) => measure.status === "warn").length,
        gap: row.bias.filter((measure) => measure.status === "fail").length,
      });
      if (moving) scale.swing(); else scale.swing(0);
    }
    show(false);

    return h("section", { class: "whatif ink", id: "at-what-if" }, h("div", { class: "wrap" },
      h("div", { class: "whatif-text" },
        h("h2", null, "What if the cut-off moved?"),
        h("p", { class: "lede" }, `Today loans scored below ${inUse}% are approved. Move the cut-off to see what would change, on the same ${v.n_evaluated.toLocaleString("en-GB")} loans.`),
        h("p", { class: "whatif-label" }, "Approve loans scored below"),
        cutOff, slider, back,
        h("div", { class: "readings" }, ...facts.map((fact) => h("div", null, fact.node, h("p", { class: "label" }, fact.label))))),
      h("div", { class: "whatif-scale" },
        scale && scale.picture,
        bias),
      h("p", { class: "whatif-note" }, "This is arithmetic on the validated file, as if every loan scored below the cut-off were approved. It shows what would change. It does not recommend a cut-off: moving it changes who gets credit and how much risk the lender takes, and that decision is the lender's. The limits are the same as in the bias checks above.")));
  }

  // ---- charts (one axis each, thin marks, a table behind every picture)

  const scaleLinear = (d0, d1, r0, r1) => (value) => r0 + ((value - d0) / (d1 - d0 || 1)) * (r1 - r0);
  const linePath = (points) => points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  function niceTop(value) { return [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1].find((step) => step >= value) || 1; }
  function gridLines(svg, x0, x1, y, values, format) {
    for (const value of values) {
      svg.append(s("line", { x1: x0, x2: x1, y1: y(value), y2: y(value), stroke: GRID }),
        s("text", { x: x0 - 8, y: y(value) + 4, "text-anchor": "end" }, format(value)));
    }
  }
  function endLabels(svg, x, labels) { // labels: [{y, text}] ; keep them at least 14px apart
    labels.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < 14) labels[i].y = labels[i - 1].y + 14;
    for (const label of labels) svg.append(s("text", { x, y: label.y + 4, class: "strong" }, label.text));
  }
  const dots = (points, colour) => points.map(([x, y]) => s("circle", { cx: x, cy: y, r: 3.5, fill: colour, stroke: "#fff", "stroke-width": 2 }));
  const legend = (...items) => h("div", { class: "legend" }, ...items.map(([colour, label, dashed]) => h("span", null, h("i", { class: dashed ? "dashed" : null, style: `border-color:${colour}` }), label)));

  function calibrationChart(rows) {
    const W = 460, H = 220, x0 = 44, x1 = W - 72, y0 = H - 34, y1 = 12;
    const top = niceTop(Math.max(...rows.map((r) => Math.max(r.predicted, r.observed))));
    const x = scaleLinear(1, rows.length, x0 + 10, x1 - 10), y = scaleLinear(0, top, y0, y1);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Predicted and real default rate in ten groups of loans, from safest to riskiest." });
    gridLines(svg, x0, x1, y, [0, top / 2, top], (value) => pct(value, 0));
    const predicted = rows.map((r) => [x(r.bin), y(r.predicted)]), real = rows.map((r) => [x(r.bin), y(r.observed)]);
    svg.append(
      s("path", { d: linePath(predicted), fill: "none", stroke: LEAD, "stroke-width": 1.5, "stroke-dasharray": DASH }),
      s("path", { d: linePath(real), fill: "none", stroke: COBALT, "stroke-width": 1.75 }),
      ...dots(real, COBALT),
      s("text", { x: x0 + 10, y: H - 10 }, "Safest loans"), s("text", { x: x1 - 10, y: H - 10, "text-anchor": "end" }, "Riskiest loans"));
    endLabels(svg, x1 + 2, [{ y: predicted.at(-1)[1], text: "Predicted" }, { y: real.at(-1)[1], text: "Real" }]);
    const band = (x1 - x0 - 20) / (rows.length - 1);
    for (const r of rows) svg.append(s("rect", { x: x(r.bin) - band / 2, y: y1, width: band, height: y0 - y1, fill: "transparent",
      "data-tip": `Group ${r.bin} of ${rows.length}\nPredicted ${pct(r.predicted)}\nReal ${pct(r.observed)}\n${count(r.n, "loan", "loans")}` }));
    return h("figure", { class: "chart" },
      h("h3", null, "Does it predict the right number of defaults?"),
      h("p", null, "Loans split in ten groups by score. The two lines should travel together."),
      svg, legend([COBALT, "Real default rate"], [LEAD, "Predicted default rate", true]),
      h("details", null, h("summary", null, "Show the numbers"),
        h("table", null, h("thead", null, h("tr", null, ...["Group", "Loans", "Predicted", "Real"].map((t) => h("th", null, t)))),
          h("tbody", null, ...rows.map((r) => h("tr", null, h("td", null, r.bin), h("td", { class: "num" }, r.n), h("td", { class: "num" }, pct(r.predicted)), h("td", { class: "num" }, pct(r.observed))))))));
  }

  function scoresChart(hist, threshold) {
    const W = 460, H = 236, x0 = 44, x1 = W - 16, y0 = H - 50, y1 = 12;
    const edges = hist.edges, last = edges.at(-1);
    const top = niceTop(Math.max(...hist.repaid, ...hist.default));
    const x = scaleLinear(0, last, x0, x1), y = scaleLinear(0, top, y0, y1);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Share of repaid and unpaid loans at each score." });
    gridLines(svg, x0, x1, y, [0, top / 2, top], (value) => pct(value, 0));
    const steps = (values) => values.map((value, i) => `${i ? "L" : "M"}${x(edges[i]).toFixed(1)} ${y(value).toFixed(1)} H${x(edges[i + 1]).toFixed(1)}`).join(" ");
    svg.append(
      s("path", { d: steps(hist.repaid), fill: "none", stroke: COBALT, "stroke-width": 1.75, "stroke-linejoin": "round" }),
      s("path", { d: steps(hist.default), fill: "none", stroke: LEAD, "stroke-width": 1.5, "stroke-linejoin": "round", "stroke-dasharray": DASH }));
    if (threshold < last) svg.append(
      s("line", { x1: x(threshold), x2: x(threshold), y1: y1, y2: y0, stroke: INK, "stroke-width": 1 }),
      s("text", { x: x(threshold) + 6, y: y1 + 10, class: "strong" }, `Approved below ${pct(threshold, 0)}`));
    const tick = last > 0.5 ? 0.2 : 0.1;
    for (let value = 0; value <= last + 1e-9; value += tick) svg.append(s("text", { x: x(value), y: y0 + 18, "text-anchor": value === 0 ? "start" : "middle" }, pct(value, 0)));
    svg.append(s("text", { x: (x0 + x1) / 2, y: H - 6, "text-anchor": "middle" }, "Score (probability of default)"));
    hist.repaid.forEach((value, i) => svg.append(s("rect", { x: x(edges[i]), y: y1, width: x(edges[i + 1]) - x(edges[i]), height: y0 - y1, fill: "transparent",
      "data-tip": `Score ${pct(edges[i], 0)} to ${pct(edges[i + 1], 0)}\n${pct(value)} of repaid loans\n${pct(hist.default[i])} of unpaid loans` })));
    return h("figure", { class: "chart" },
      h("h3", null, "Does it separate good and bad payers?"),
      h("p", null, "Where each kind of loan sits on the score. The further apart the two shapes, the better."),
      svg, legend([COBALT, "Loans that were repaid"], [LEAD, "Loans that were not repaid", true]));
  }

  function groupChart(attribute, rows) {
    const label = attribute.replace(/_/g, " ");
    const W = 460, rowH = 30, x0 = 76, x1 = W - 120, H = rows.length * rowH + 30;
    const x = scaleLinear(0, 1, x0, x1);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Approval rate by ${label}.` });
    for (const value of [0, 0.5, 1]) svg.append(
      s("line", { x1: x(value), x2: x(value), y1: 4, y2: H - 24, stroke: GRID }),
      s("text", { x: x(value), y: H - 8, "text-anchor": "middle" }, pct(value, 0)));
    rows.forEach((r, i) => {
      const y = 10 + i * rowH;
      svg.append(
        s("text", { x: x0 - 10, y: y + 9, "text-anchor": "end", class: "strong" }, r.group),
        s("rect", { x: x0, y: y + 2, width: Math.max(x(r.approval_rate) - x0, 2), height: 6, rx: 3, fill: COBALT }),
        s("rect", { x: x0, y: y + 2, width: 4, height: 6, fill: COBALT }), // square at the baseline, round at the data end
        s("text", { x: x(r.approval_rate) + 8, y: y + 9, class: "strong" }, pct(r.approval_rate)),
        s("text", { x: x(r.approval_rate) + 52, y: y + 9 }, count(r.n, "loan", "loans")),
        s("rect", { x: 0, y: y - 8, width: W, height: rowH, fill: "transparent",
          "data-tip": `${label} ${r.group}\nApproved ${pct(r.approval_rate)}\nGood payers approved ${r.good_approval_rate === null ? "–" : pct(r.good_approval_rate)}\nDefault rate ${pct(r.default_rate)}` }));
    });
    return h("figure", { class: "chart" },
      h("h3", null, `Approval rate by ${label}`),
      h("p", null, "Share of applicants in each group that the model approves."),
      svg,
      h("details", null, h("summary", null, "Show the numbers"),
        h("table", null, h("thead", null, h("tr", null, ...["Group", "Loans", "Approved", "Good payers approved", "Defaults", "AUC"].map((t) => h("th", null, t)))),
          h("tbody", null, ...rows.map((r) => h("tr", null, h("td", null, r.group), h("td", { class: "num" }, r.n.toLocaleString("en-GB")), h("td", { class: "num" }, pct(r.approval_rate)),
            h("td", { class: "num" }, r.good_approval_rate === null ? "–" : pct(r.good_approval_rate)), h("td", { class: "num" }, pct(r.default_rate)), h("td", { class: "num" }, r.auc === null ? "–" : r.auc.toFixed(3))))))));
  }

  function trendChart({ title, sub, rows, series, refs = [], format, floor, top, step = 0.05 }) {
    const W = 760, H = 176, x0 = 48, x1 = W - 128, y0 = H - 28, y1 = 12;
    const values = rows.flatMap((r) => series.map((item) => item.get(r))).concat(refs.map((ref) => ref.value));
    const low = floor === undefined ? Math.floor((Math.min(...values) - 0.01) / step) * step : floor;
    const high = Math.max(top || 0, Math.ceil((Math.max(...values) * (top === undefined ? 1 : 1.04) + (top === undefined ? 0.01 : 0)) / step) * step);
    const x = scaleLinear(0, Math.max(rows.length - 1, 1), x0 + 14, x1 - 14), y = scaleLinear(low, high, y0, y1);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${title}, by month.` });
    gridLines(svg, x0, x1, y, [low, (low + high) / 2, high], format);
    const labels = [];
    for (const ref of refs) {
      svg.append(s("line", { x1: x0, x2: x1, y1: y(ref.value), y2: y(ref.value), stroke: LEAD, "stroke-dasharray": "2 4" }));
      labels.push({ y: y(ref.value), text: ref.label, quiet: true });
    }
    for (const item of series) {
      const points = rows.map((r, i) => [x(i), y(item.get(r))]);
      svg.append(s("path", { d: linePath(points), fill: "none", stroke: item.colour, "stroke-width": item.dashed ? 1.5 : 1.75, "stroke-dasharray": item.dashed ? DASH : null }), ...(item.dashed ? [] : dots(points, item.colour)));
      labels.push({ y: points.at(-1)[1], text: item.label });
    }
    labels.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < 14) labels[i].y = labels[i - 1].y + 14;
    for (const label of labels) svg.append(s("text", { x: x1 + 4, y: label.y + 4, class: label.quiet ? null : "strong" }, label.text));
    const band = rows.length > 1 ? x(1) - x(0) : x1 - x0;
    rows.forEach((r, i) => {
      const [year, month] = r.period.split("-");
      const name = new Date(Number(year), Number(month) - 1, 1).toLocaleDateString("en-GB", { month: "short" });
      svg.append(s("text", { x: x(i), y: H - 8, "text-anchor": "middle" }, month === "01" || i === 0 ? `${name} ${year}` : name),
        s("rect", { x: x(i) - band / 2, y: y1, width: band, height: y0 - y1, fill: "transparent",
          "data-tip": `${r.period}\n` + series.map((item) => `${item.label} ${format(item.get(r))}`).join("\n") }));
    });
    return h("figure", { class: "chart" }, h("h3", null, title), h("p", null, sub), svg,
      series.length > 1 && legend(...series.map((item) => [item.colour, item.label, item.dashed])));
  }

  // ---- monitoring

  function tabMonitoring(data, reload) {
    const id = data.model.id, rows = data.monitoring, v = data.validation;
    const error = h("p", { class: "error", hidden: true });
    const now = new Date();
    const form = h("form", { class: "panel", style: "margin-top:0", onsubmit: async (event) => {
        event.preventDefault();
        const submit = event.target.querySelector("button");
        submit.disabled = true; error.hidden = true;
        try {
          const result = await api(`/api/models/${id}/monitoring`, { method: "POST", body: new FormData(event.target) });
          await reload(`${result.period} recorded: ${WORDS[result.overall].toLowerCase()}.`);
        } catch (failure) { error.textContent = failure.message; error.hidden = false; submit.disabled = false; }
      } },
      h("h2", null, "Record a month"),
      h("p", { class: "muted small", style: "margin:4px 0 16px" }, "Upload that month's scored loans, with the outcome known. Balanza compares them with the validated model."),
      h("label", null, "Month", h("input", { type: "month", name: "period", required: true, value: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}` })),
      h("label", { style: "margin-top:14px" }, "Scored file (CSV)", h("input", { type: "file", name: "file", accept: ".csv,text/csv", required: true })),
      error,
      h("div", { class: "actions", style: "margin-top:16px" }, h("button", { type: "submit" }, "Record this month"),
        h("a", { class: "small", href: "/api/demo/monitoring.csv", download: "" }, "Download a demo month")));

    if (!v) return h("div", { class: "empty" }, h("h2", null, "Validate the model first"),
      h("p", null, "Monitoring compares new loans with the validated model, so it needs a validation on record."),
      h("a", { class: "button", href: `#/models/${id}/validation` }, "Go to validation"));
    if (!rows.length) return h("div", { class: "split", style: "margin-top:0" },
      h("div", { class: "empty" }, h("h2", null, "No months recorded"), h("p", { style: "margin-bottom:0" }, "Record the first month of production loans to start watching for drift.")), form);

    const lastRow = rows.at(-1);
    return h("div", null,
      h("div", { class: "summary", style: "margin-bottom:20px" }, mark(lastRow.overall, `${lastRow.period}: ${WORDS[lastRow.overall]}`),
        h("span", { class: "muted" }, lastRow.signals.filter((signal) => signal.status !== "pass").map((signal) => signal.name).join("; ") || "All three signals are inside their limits.")),
      h("div", { class: "stack" },
        trendChart({ title: "Have the applicants changed?", sub: "Population Stability Index of the scores, against the loans the model was built with.", rows,
          series: [{ label: "PSI", colour: COBALT, get: (r) => r.psi }], refs: [{ value: 0.10, label: "Watch above 0.10" }, { value: 0.25, label: "Act above 0.25" }],
          format: (value) => value.toFixed(2), floor: 0, top: 0.3, step: 0.1 }),
        trendChart({ title: "Does it still predict the right number of defaults?", sub: "Default rate the model expected each month, against what really happened.", rows,
          series: [{ label: "Real", colour: COBALT, get: (r) => r.default_rate }, { label: "Predicted", colour: LEAD, dashed: true, get: (r) => r.predicted_rate }],
          format: (value) => pct(value, 0), floor: 0, top: 0.2, step: 0.1 }),
        trendChart({ title: "Is it still accurate?", sub: "AUC each month. One month has few loans, so small moves are chance; only clear drops raise an alarm.", rows,
          series: [{ label: "AUC", colour: COBALT, get: (r) => r.auc }], refs: [{ value: v.auc, label: `Validation ${v.auc.toFixed(3)}` }],
          format: (value) => value.toFixed(2) })),
      h("div", { class: "split" },
        h("table", null,
          h("thead", null, h("tr", null, ...["Month", "Loans", "PSI", "AUC", "Predicted", "Real"].map((t) => h("th", null, t)), h("th", null, "Result"))),
          h("tbody", null, ...[...rows].reverse().map((r) => h("tr", null, h("td", null, r.period), h("td", { class: "num" }, r.n_rows.toLocaleString("en-GB")),
            h("td", { class: "num" }, r.psi.toFixed(3)), h("td", { class: "num" }, r.auc.toFixed(3)), h("td", { class: "num" }, pct(r.predicted_rate)), h("td", { class: "num" }, pct(r.default_rate)), h("td", null, mark(r.overall)))))),
        form));
  }

  // ---- documentation

  function tabDocumentation(data, reload, focus) {
    const id = data.model.id, docs = data.model.docs || {}, drafts = data.drafts || {};
    const usedFor = {};
    for (const r of data.evidence.requirements) for (const item of r.items) (usedFor[item.label] = usedFor[item.label] || []).push(r.article.split(" and ")[0]);
    const error = h("p", { class: "error", hidden: true });
    const open = (text) => text.includes(meta.to_complete);
    const fields = Object.entries(meta.doc_fields).map(([key, field]) => {
      const text = docs[key] || "";
      const box = h("textarea", { id: `doc-${key}`, name: key, maxlength: 6000 }, text);
      const drafted = h("p", { class: "drafted", hidden: true },
        "Balanza wrote this from your test results. Complete the parts in [brackets] and check every sentence: you sign it, not Balanza. Nothing is saved until you press \"Save answers\".");
      const useDraft = () => {
        box.value = drafts[key];
        requestAnimationFrame(() => { box.style.height = "auto"; box.style.height = `${box.scrollHeight + 4}px`; });
        drafted.hidden = false; offer.hidden = true;
      };
      const offer = h("button", { type: "button", class: "quiet", hidden: !(drafts[key] && !text.trim()), onclick: useDraft }, "Draft it from the evidence");
      if (focus === key && drafts[key] && !text.trim()) useDraft(); // arriving from a step of the route
      const state = text.trim().length >= 40 && !open(text) ? mark("pass", "Written") : open(text) ? mark("missing", "Parts still to complete") : mark("missing", "Not written yet");
      return h("div", { class: "field", id: `at-${key}` },
        h("label", { for: `doc-${key}` }, field.label, h("span", { class: "hint" }, field.help)),
        box, drafted,
        h("p", { class: "needs" }, state, usedFor[field.label] ? `   Evidence for ${usedFor[field.label].join(", ")}` : ""),
        offer);
    });
    return h("form", { class: "doc", onsubmit: async (event) => {
        event.preventDefault();
        const changes = {};
        for (const [key, value] of new FormData(event.target)) if ((docs[key] || "") !== value.trim()) changes[key] = value;
        if (!Object.keys(changes).length) { toast("Nothing has changed."); return; }
        const unfinished = Object.values(changes).filter(open).length;
        try {
          await api(`/api/models/${id}/docs`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes) });
          await reload(unfinished
            ? `Answers saved. ${count(unfinished, "answer still has", "answers still have")} parts to complete in [brackets], so ${unfinished === 1 ? "it does" : "they do"} not count yet.`
            : "Answers saved. The evidence has been updated.");
        } catch (failure) { error.textContent = failure.message; error.hidden = false; }
      } },
      h("p", { class: "lede", style: "margin:0" }, "The answers only the lender can give. They go into the technical file, next to the test results. Write in plain language; an answer needs at least a couple of sentences to count."),
      fields, error,
      h("div", { class: "actions" }, h("button", { type: "submit" }, "Save answers"),
        h("a", { href: `/models/${id}/technical-file`, target: "_blank", rel: "noopener" }, "Open the technical file")));
  }

  // ---- history

  function tabHistory(data, reload) {
    return h("div", null,
      theSeal(data, reload),
      verifyFile(data),
      h("p", { class: "lede", style: "margin:0 0 20px" }, "Every validation, monitoring month and change, with the fingerprint of the file that was used."),
      h("ul", { class: "trail" }, ...data.audit.map((entry) =>
        h("li", null, h("span", { class: "num muted" }, when(entry.at)), h("b", null, ACTIONS[entry.action] || entry.action), h("span", null, entry.detail)))));
  }

  // Is this the file that was weighed? The file's fingerprint is compared with the ones on
  // record, and the two engravings are shown side by side: the same file draws the same huella.
  function verifyFile(data) {
    const id = data.model.id;
    const result = h("div", { class: "verify-result", hidden: true, "aria-live": "polite" });
    const seal = (sha, caption) => h("figure", { class: "seal" }, window.balanzaHuella(sha, { iris: true, draw: true, weight: 1.6 }),
      h("figcaption", null, h("b", null, sha.slice(0, 12) + "…"), caption));
    const used = (match) => match.kind === "validation"
      ? `It is ${match.dataset_name}, the file validated on ${when(match.created_at)}. Result of that validation: ${WORDS[match.overall].toLowerCase()}.`
      : `It is the file of the month ${match.period}, recorded on ${when(match.created_at)}. Result of that month: ${WORDS[match.overall].toLowerCase()}.`;

    // A file validated several times is named once, with its latest validation.
    const sameFile = (matches) => {
      const validations = matches.filter((match) => match.kind === "validation"), months = matches.filter((match) => match.kind !== "validation");
      return [
        validations.length && used(validations[0]) + (validations.length > 1 ? ` It has been validated ${validations.length} times with this same file.` : ""),
        ...months.map(used),
      ].filter(Boolean).join(" ");
    };

    const choose = uploadButton("Choose a file to verify", async (file) => {
      const body = new FormData(); body.append("file", file);
      const answer = await api(`/api/models/${id}/verify`, { method: "POST", body });
      const same = answer.matches.length > 0;
      const elsewhere = answer.other_models.length ? ` A file with this fingerprint was used for: ${answer.other_models.join(", ")}.` : "";
      result.replaceChildren(
        h("div", { class: "seals" },
          seal(answer.sha256, `This file: ${answer.file_name}`),
          answer.validated && seal(answer.validated.dataset_sha256, `Validated: ${answer.validated.dataset_name}`)),
        h("div", { class: "verdict" },
          h("p", { class: "summary" }, same ? mark("pass", "Same file") : mark("fail", "Not the same file")),
          h("p", null, same ? sameFile(answer.matches)
            : (data.validation ? "No validation or monitoring month of this model used this file. One changed cell is enough to change the fingerprint, and the drawing with it." : "This model has no validation on record to compare with.") + elsewhere),
          h("p", { class: "hash" }, answer.sha256)));
      result.hidden = false;
    }, true);

    return h("div", { class: "panel verify" },
      h("div", { class: "verify-ask" },
        h("div", null, h("h2", null, "Verify a file"),
          h("p", { class: "muted small" }, "Choose a file to see whether it is one that was weighed for this model. Balanza reads it, takes its fingerprint and keeps nothing.")),
        choose),
      result);
  }

  // ---- the seal

  // The evidence of the model closed into one file, under a seal: its state, its engraving and the pack to hand over.
  function theSeal(data, reload) {
    const id = data.model.id, seal = data.seal;
    const packUrl = (mark) => `/api/models/${id}/seals/${mark}`;
    const sealNow = h("button", { type: "button", onclick: async () => {
      sealNow.disabled = true;
      try {
        const made = await api(`/api/models/${id}/seals`, { method: "POST" });
        // The pack is downloaded exactly as the server stored it: the page never rewrites a sealed file.
        const link = h("a", { href: packUrl(made.seal), download: made.file_name, hidden: true });
        document.body.append(link); link.click(); link.remove();
        await reload("Evidence sealed. The pack has been downloaded: keep it together with its seal.");
      } catch (failure) { toast(failure.message); sealNow.disabled = false; }
    } }, seal.state === "changed" ? "Seal the evidence again" : "Seal the evidence");
    const [state, meaning] = {
      none: [mark("missing", "Not sealed yet"), "Sealing closes everything on record for this model (the written answers, the validation, the monitoring months and this history) into one file, under a seal. Change one number afterwards and the seal no longer matches."],
      sealed: [mark("pass", "Under seal, unchanged"), `Sealed on ${when(seal.sealed_at)}. Nothing on record for this model has changed since.`],
      changed: [mark("warn", "Changed since the last seal"), `What is on record is no longer what was sealed on ${when(seal.sealed_at)}. Seal it again to cover the changes. The new seal keeps the old one inside, so the chain can be followed.`],
    }[seal.state];
    const earlier = data.seals.slice(1);

    return h("div", { class: "panel verify sealing" },
      h("div", { class: seal.seal ? "now" : "now bare" },
        seal.seal && h("figure", { class: "seal" }, window.balanzaHuella(seal.seal, { iris: true, draw: true, weight: 1.6 }),
          h("figcaption", null, h("b", null, seal.seal.slice(0, 12) + "…"), "The engraving of this seal")),
        h("div", { class: "verdict" },
          h("h2", null, "The seal"),
          h("p", { class: "summary" }, state),
          h("p", null, meaning),
          seal.seal && h("p", { class: "hash" }, seal.seal),
          h("div", { class: "actions" },
            seal.state !== "sealed" && sealNow,
            seal.state === "sealed" && h("a", { class: "button", href: packUrl(seal.seal), download: "" }, "Download the sealed pack"),
            h("a", { class: "button quiet", href: "#/verify" }, "Verify a sealed pack")),
          h("p", { class: "muted small" }, "A pack holds results and fingerprints. It never holds the loans."))),
      earlier.length > 0 && h("details", { class: "earlier" },
        h("summary", null, count(earlier.length, "earlier seal", "earlier seals")),
        h("ul", null, ...earlier.map((item) => h("li", null,
          h("span", { class: "num muted" }, when(item.sealed_at)), h("span", { class: "hash" }, item.seal.slice(0, 16) + "…"),
          h("a", { href: packUrl(item.seal), download: "" }, "Download"))))));
  }

  // ---------------------------------------------------------------- verify a sealed pack

  // Whoever receives a pack checks it here: is the seal intact, what does it hold, and does the
  // data file weigh the same again. The pack and the file are read, checked and dropped.
  function showVerify() {
    viewRun += 1;
    let packFile = null;
    const result = h("div", { class: "pack-result", hidden: true, "aria-live": "polite" });
    const engraving = (sha, caption) => h("figure", { class: "seal" }, window.balanzaHuella(sha, { iris: true, draw: true, weight: 1.6 }),
      h("figcaption", null, h("b", null, sha.slice(0, 12) + "…"), caption));
    const line = (label, ...value) => h("li", null, h("span", { class: "muted" }, label), h("span", null, ...value));
    const check = async (dataFile) => {
      const body = new FormData();
      body.append("pack", packFile);
      if (dataFile) body.append("data", dataFile);
      show(await api("/api/packs/verify", { method: "POST", body }));
    };

    function weighedAgain(a) {
      const r = a.reweigh;
      if (!r) return null;
      if (!r.same_file) return h("div", { class: "verdict" },
        h("p", { class: "summary" }, mark("fail", "Not the file that was weighed")),
        h("p", null, r.month ? `It is the file of the monitoring month ${r.month}, not the file that was validated.`
          : "Its fingerprint is not the one sealed in the pack. One changed cell is enough to change it."),
        h("p", { class: "hash" }, r.sha256));
      if (r.same === r.checks) return h("div", { class: "verdict" },
        h("p", { class: "summary" }, mark("pass", "Same file, same result")),
        h("p", null, `It is the file that was validated, and ${r.checks} of its ${r.checks} checks give the same result as in the pack.`));
      return h("div", { class: "verdict" },
        h("p", { class: "summary" }, mark("warn", `${r.same} of ${r.checks} checks give the same result`)),
        h("p", null, `It is the file that was validated, but this Balanza (version ${a.this_version}) does not measure everything as the one that sealed the pack (version ${a.made_with}).`),
        h("ul", { class: "holds" }, ...r.differences.map((d) => line(d.name, `sealed: ${d.sealed}. Now: ${d.now}.`))));
    }

    function show(a) {
      if (!a.intact) {
        result.replaceChildren(h("div", { class: "now" },
          h("div", { class: "seals" }, engraving(a.seal, "The seal the pack carries"), engraving(a.computed, "The seal its content gives")),
          h("div", { class: "verdict" },
            h("p", { class: "summary" }, mark("fail", "Seal broken")),
            h("p", null, "What this pack holds does not give the seal it carries. Something in it was changed after it was sealed, so nothing it says can be relied on."),
            h("p", { class: "hash" }, `Carries ${a.seal}`), h("p", { class: "hash" }, `Gives ${a.computed}`))));
        result.hidden = false;
        return;
      }
      const inside = a.inside, v = inside.validation, last = inside.months[inside.months.length - 1];
      result.replaceChildren(
        h("div", { class: "now" },
          h("div", { class: "seals" }, engraving(a.seal, a.file_name)),
          h("div", { class: "verdict" },
            h("p", { class: "summary" }, mark("pass", "Seal intact")),
            h("p", null, `Nothing in this pack has changed since it was sealed on ${when(a.sealed_at)}, with Balanza ${a.made_with}.`),
            h("p", null, a.sealed_here ? `It was sealed on this computer, for ${a.sealed_here.model_name}.`
              : "It was not sealed on this computer. To know it is the pack you were promised, compare the seal below with the one you were given when it was sealed: it is printed on the verdict page."),
            h("p", { class: "hash" }, a.seal))),
        h("h3", { class: "holds-title" }, "What the pack holds"),
        h("ul", { class: "holds" },
          line("Model", `${inside.model.name}. ${inside.model.owner}. ${inside.risk_label}.`),
          line("Read today", `${inside.statement} ${inside.readiness}% of the evidence is ready, read by this Balanza from the sealed evidence.`),
          line("Written answers", `${inside.answers} of ${inside.answers_total}.`),
          line("Validated file", v ? [`${v.dataset_name}, ${count(v.n_rows, "loan", "loans")}, validated ${day(v.created_at)}: ${tally(v.counts)}. `, h("span", { class: "hash" }, v.dataset_sha256)] : "None."),
          line("Monitoring", last ? `${count(inside.months.length, "month", "months")} on record. Latest, ${last.period}: ${WORDS[last.overall].toLowerCase()}.` : "No month on record."),
          line("History", `${count(inside.history, "entry", "entries")}.`),
          line("Seal before this one", a.previous_seal ? h("span", { class: "hash" }, a.previous_seal) : "None: it is the first seal of this model.")),
        v && h("div", { class: "reweigh" },
          h("div", { class: "verify-ask" },
            h("div", null, h("h3", null, "Weigh it again"),
              h("p", { class: "muted small" }, "Choose the file that was validated. Balanza checks that it is the same file and runs every test again.")),
            uploadButton("Choose the data file", check, true)),
          weighedAgain(a)));
      result.hidden = false;
    }

    const choose = uploadButton("Choose a sealed pack", async (file) => { packFile = file; await check(null); }, false, ".json,application/json");
    view.replaceChildren(
      h("section", { class: "hero compact ink" }, h("div", { class: "wrap" },
        h("div", { class: "hero-text" },
          h("a", { class: "back", href: "#/" }, "All models"),
          h("h1", null, "Verify a sealed pack"),
          h("p", { class: "class" }, "Choose a pack that Balanza sealed. It is read here, checked and dropped: nothing is stored.")))),
      paper(
        h("div", { class: "panel verify" },
          h("div", { class: "verify-ask" },
            h("div", null, h("h2", null, "Is the seal intact?"),
              h("p", { class: "muted small" }, "A sealed pack is a file whose name begins with balanza-seal. Whoever sealed the evidence hands it over together with its seal.")),
            choose),
          result),
        h("p", { class: "note" }, "An intact seal shows that nothing changed after sealing. It does not show that the data was true to begin with, or who sealed it.")));
  }

  route();
})();
