// Run from any directory with: node tests/check-site-counts.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const read = file => fs.readFileSync(path.join(__dirname, "../site", file), "utf8");
const html = read("index.html");
const document = new EventTarget();
const counts = vm.runInNewContext(read("counts.js") + "\ncounts", { document });

const pinned = html.split('<section id="catch"')[1].split("</section>")[0];
const summary = [...pinned.matchAll(/<span data-catch-count([^>]*)>([^<]*)<\/span>/g)];
assert.deepEqual(summary.map(match => match[2]), ["80,765.0", "10,095.62", "49,802.5"]);
assert.equal([...html.matchAll(/\bdata-catch-count\b/g)].length, summary.length);

const comment = html.split('id="comment"')[1].split('id="method"')[0];
const quoted = [...comment.matchAll(/<td class="bug">([^<]*)<\/td>/g)].map(match => match[1]);
assert.deepEqual(quoted, [
  "10,095.62", "49,802.5", "80,765.0", "76,000",
  "20,191.25", "2,137.5", "65,354.0", "80,765.0", "76,490"
]);
assert.doesNotMatch(comment, /data-final/);
assert.match(html, /<span class="hero-value">76,000<\/span>/);
for (const script of ["page.js", "hero.js", "scope-scene.mjs"]) {
  assert.doesNotMatch(read(script), /\bcounts\.(?:add|land)\(/);
}

const benchmark = fs.readFileSync(path.join(__dirname, "../bench/results.md"), "utf8");
const observations = [...benchmark.matchAll(/^\| ([\d,]+) \| ([\d,]+) \| (\d+\.\d+) \|$/gm)];
const timings = [...html.matchAll(/<tr class="benchmark-row">\s*<th scope="row">([\d,]+)[\s\S]*?<\/th><td>([\d,]+)<\/td>\s*<td><span class="timing-value" data-final="([^"]+)">([^<]+)<\/span><svg class="timing-track" viewBox="0 0 (\d+) 8"[^>]*><rect width="(\d+)" height="8"\/><\/svg><span class="timing-rate">≈([\d,]+) rows\/s<\/span>/g)];
assert.equal(timings.length, 3);
assert.equal(observations.length, timings.length);
const toNumber = text => Number(text.replaceAll(",", ""));
const longest = Math.max(...observations.map(match => Math.round(Number(match[3]) * 1000)));
for (const [i, [, rows, changed, final, time, maxWidth, width, rate]] of timings.entries()) {
  assert.deepEqual([rows, changed, time], observations[i].slice(1));
  assert.equal(final, time);
  assert.equal(Number(width), Math.round(Number(time) * 1000));
  assert.equal(Number(maxWidth), longest);
  assert.equal(toNumber(rate), Math.round(toNumber(rows) / Number(time)));
}
assert.equal([...html.matchAll(/\bdata-final="/g)].length, summary.length + timings.length);

for (const [tag, attributes, staticText] of summary) {
  const final = attributes.match(/\bdata-final="([^"]+)"/)?.[1];
  assert.equal(final, staticText, tag);
  const display = { textContent: "" };
  let text = staticText;
  const element = {
    dataset: { final },
    get textContent() { return text + display.textContent; },
    set textContent(value) { text = value; display.textContent = ""; }
  };
  // Exercise the pinned story's count formatting and completion without a browser clock.
  const timeline = {
    to(state, tween) {
      tween.onStart();
      state.n = tween.n / 2;
      tween.onUpdate();
      assert.notEqual(element.textContent, staticText);
      state.n = tween.n;
      tween.onUpdate();
      tween.onComplete();
    }
  };
  counts.add(timeline, element, 0, .8, 0, "none", () => display);
  assert.equal(element.textContent, staticText);
}
assert.throws(() => counts.land({ dataset: { final: "80,765.0" } }, "80,765"), /Expected/);
let finishes = 0;
const unlisten = counts.finishWhenHidden({
  isActive: () => true,
  progress(value, suppressEvents) {
    assert.equal(value, 1);
    assert.equal(suppressEvents, false);
    finishes++;
  }
});
document.hidden = false;
document.dispatchEvent(new Event("visibilitychange"));
assert.equal(finishes, 0);
document.hidden = true;
document.dispatchEvent(new Event("visibilitychange"));
unlisten();
document.dispatchEvent(new Event("visibilitychange"));
assert.equal(finishes, 1);
console.log("Passed: pinned counter endpoints, static PR values, and benchmark times, widths and rates.");
