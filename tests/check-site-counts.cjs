// Run from any directory with: node tests/check-site-counts.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const read = file => fs.readFileSync(path.join(__dirname, "../site", file), "utf8");
const html = read("index.html");
const document = new EventTarget();
const counts = vm.runInNewContext(read("counts.js") + "\ncounts", { document });

// Find the animated elements independently of data-final so a missing attribute fails.
const stats = [...html.matchAll(/<table class="data-table numeric-shifts">([\s\S]*?)<\/table>/g)]
  .flatMap(table => [...table[1].matchAll(/<td class="bug"([^>]*)>([^<]*)<\/td>/g)]);
const labels = [...html.matchAll(/<span (?:class="(?:odometer|timing-value)"|data-catch-count)([^>]*)>([^<]*)<\/span>/g)];
const elements = [...stats, ...labels];
assert.equal(elements.length, 14);
assert.equal(elements.length, [...html.matchAll(/\bdata-final="/g)].length);

for (const [tag, attributes, staticText] of elements) {
  const final = attributes.match(/\bdata-final="([^"]+)"/)?.[1];
  assert.equal(final, staticText, tag);
  const display = { textContent: "" };
  let text = staticText;
  const element = {
    dataset: { final },
    get textContent() { return text + display.textContent; },
    set textContent(value) { text = value; display.textContent = ""; }
  };
  if (tag.includes('class="odometer"')) {
    element.textContent = "760";
    counts.land(element, staticText);
  } else {
    // Exercise the page's own rendering and completion callbacks without a browser clock.
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
    counts.add(timeline, element, 0, 0.8, 0, "none", () => display);
  }
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
console.log(`Passed: all ${elements.length} counter endpoints match the HTML byte for byte.`);
