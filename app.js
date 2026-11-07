// Reads index.json and results/<run>.json only; console text and every
// other field from a run document is set as text, never as HTML.
"use strict";
const main = document.getElementById("main");
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v; else if (k === "href") e.href = v; else e.setAttribute(k, v);
  }
  for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(k == null ? "" : String(k)));
  return e;
}
function link(href, text) { return href ? el("a", {href}, text) : document.createTextNode(text); }
function counts(c) {
  c = c || {};
  return `${c.pass || 0} pass / ${c.fail || 0} fail / ${c.skip || 0} skip` +
    (c.justified ? ` (${c.justified} justified)` : "") + (c.flaky ? ` (${c.flaky} flaky)` : "");
}
function short(s) { return (s || "").slice(0, 12); }
function inputsTable(inputs, rootfs, suite) {
  const t = el("table", {}, el("tr", {}, el("th", {}, "component"), el("th", {}, "role"),
    el("th", {}, "repository"), el("th", {}, "ref"), el("th", {}, "commit")));
  for (const [c, v] of Object.entries(inputs)) {
    t.append(el("tr", {}, el("td", {}, c), el("td", {}, v.role), el("td", {}, v.repo), el("td", {}, v.ref || ""),
      el("td", {}, short(v.commit), v.pending ? el("span", {class: "pending"}, " not public: " + v.pending) : "")));
  }
  t.append(el("tr", {}, el("td", {}, "rootfs"), el("td", {}, "pinned"), el("td", {}, rootfs.repo || "qcom-buildroot"),
    el("td", {}, ""), el("td", {}, short(rootfs.commit),
      rootfs.upstream ? "" : el("span", {class: "pending"}, " not yet upstream" + (rootfs.note ? ": " + rootfs.note : "")))));
  for (const [name, o] of Object.entries(rootfs.overrides || {})) {
    t.append(el("tr", {}, el("td", {}, "rootfs override"), el("td", {}, "pinned"), el("td", {}, name), el("td", {}, ""),
      el("td", {}, short(o.revision), el("span", {class: "pending"}, " " + o.reason))));
  }
  t.append(el("tr", {}, el("td", {}, "suite"), el("td", {}, "pinned"), el("td", {}, "test-definitions"),
    el("td", {}, ""), el("td", {}, short(typeof suite === "string" ? suite : suite.commit))));
  return t;
}
async function front() {
  const idx = await (await fetch("index.json", {cache: "no-store"})).json();
  main.replaceChildren();
  main.append(el("h2", {}, "Latest nightly per board"));
  const ln = Object.entries(idx.latest_nightly || {});
  main.append(ln.length ? el("ul", {}, ...ln.map(([b, r]) => el("li", {}, b + ": ", link("?run=" + r, r))))
                        : el("p", {}, "No nightly yet."));
  main.append(el("h2", {}, "Recent runs"));
  const t = el("table", {}, el("tr", {}, ...["run", "title", "requester", "state", "boards"].map(h => el("th", {}, h))));
  for (const r of idx.runs) {
    t.append(el("tr", {}, el("td", {}, link("?run=" + r.id, r.id)), el("td", {}, r.title), el("td", {}, r.requester),
      el("td", {}, r.state), el("td", {}, ...r.targets.map(x => el("div", {class: x.verdict === "pass" ? "pass" :
        x.verdict === "fail" ? "fail" : ""}, `${x.board}: ${x.state} ${x.state_detail || ""} ${counts(x.counts)}`)))));
  }
  main.append(t);
}
async function run(id) {
  const d = await (await fetch("results/" + encodeURIComponent(id) + ".json", {cache: "no-store"})).json();
  main.replaceChildren(el("h2", {}, d.run.title || d.run.id), el("p", {}, `run ${d.run.id}, ${d.run.kind}, state ${d.state}, `,
    link(d.run.ci_url, "CI run"), `, requested by ${d.run.requester || "?"}, updated ${d.run.updated}`));
  main.append(inputsTable(d.inputs, d.rootfs, d.suite));
  for (const t of d.targets) {
    main.append(el("h3", {}, `${t.board} (${t.device_type || ""}): ${t.state} ${t.state_detail || ""}`));
    main.append(el("p", {}, `fingerprint ${t.fingerprint || ""}; BL2 ${t.bl2 ? t.bl2.fingerprint : ""}; gate ${t.fingerprint_gate || "not-run"}; verdict ${t.verdict || "not-run"}; `,
      t.lava ? link(t.lava.url, "LAVA " + t.lava.job_id + (t.lava.device ? " on " + t.lava.device : "")) : "",
      t.queue_position ? ` (queue position ${t.queue_position})` : "", "; ", counts(t.counts)));
    if (t.diff) {
      main.append(el("p", {}, `against ${t.diff.baseline}: new fail ${t.diff.new_fail.length}, new pass ${t.diff.new_pass.length}, ` +
        `still fail ${t.diff.still_fail.length}, missing ${t.diff.missing.length}, added ${t.diff.added.length}`));
      for (const k of ["new_fail", "new_pass", "missing", "added"]) {
        if (t.diff[k].length) main.append(el("p", {}, k + ": " + t.diff[k].join(", ")));
      }
    }
    const tb = el("table", {}, el("tr", {}, ...["suite", "case", "result", "note"].map(h => el("th", {}, h))));
    for (const c of t.cases || []) {
      const cls = c.justified ? "justified" : c.flake ? "flaky" : c.result;
      tb.append(el("tr", {class: cls}, el("td", {}, c.suite), el("td", {}, link(c.url, c.name)),
        el("td", {}, c.justified ? c.result + " (justified)" : c.result),
        el("td", {}, c.justified ? c.justified.reason : (c.note || "") + (c.flake ? " flake " + c.flake : ""))));
    }
    main.append(tb);
  }
}
const q = new URLSearchParams(location.search).get("run");
(q ? run(q) : front()).catch(e => main.replaceChildren(el("p", {}, "Cannot load: " + e)));
