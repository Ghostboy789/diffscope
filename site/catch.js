(() => {
  const { gsap, ScrollTrigger, ScrambleTextPlugin, DrawSVGPlugin } = window;
  const section = document.getElementById("catch");
  if (!section || !gsap || !ScrollTrigger || !ScrambleTextPlugin || !DrawSVGPlugin) return;

  const stage = section.querySelector(".catch-stage");
  const steps = Array.from(section.querySelectorAll(".catch-step"));
  if (!stage || steps.length !== 5) return;

  // page.js registers the plugins before this deferred script runs.
  const media = gsap.matchMedia();
  media.add({
    desktop: "(min-width: 768px)",
    motion: "(prefers-reduced-motion: no-preference)",
    reduced: "(prefers-reduced-motion: reduce)"
  }, ({ conditions }) => {
    if (conditions.reduced || !conditions.motion) return;

    const cleanups = [];
    const parse = text => Number(text.replaceAll(",", ""));
    const integer = new Intl.NumberFormat("en-US");

    // Keep a stable reading for assistive technology while the visible digits change.
    function animatedCopy(node) {
      const text = node.textContent;
      const accessible = document.createElement("span");
      accessible.className = "catch-accessible";
      accessible.textContent = text;
      const visible = document.createElement("span");
      visible.setAttribute("aria-hidden", "true");
      visible.textContent = text;
      node.replaceChildren(accessible, visible);
      cleanups.push(() => node.replaceChildren(text));
      return visible;
    }

    function count(timeline, node, before, at) {
      const original = node.textContent;
      const digits = original.split(".")[1]?.length || 0;
      const format = new Intl.NumberFormat("en-US", {
        minimumFractionDigits: digits, maximumFractionDigits: digits
      });
      const visible = animatedCopy(node);
      const state = { value: before };
      timeline.fromTo(state, { value: before }, {
        value: parse(original), duration: 0.8, ease: "power1.out",
        onUpdate: () => { visible.textContent = format.format(state.value); }
      }, at);
    }

    // Tick labels keep two significant figures so a paused scrub never shows fractional cents.
    const roundTick = x => { const m = 10 ** (Math.floor(Math.log10(x)) - 1); return Math.round(x / m) * m; };

    function orderZoom(figure, timeline) {
      const axis = figure.querySelector(".catch-axis");
      const rule = figure.querySelector(".catch-axis-rule");
      const mid = figure.querySelector(".catch-axis-mid");
      const end = figure.querySelector(".catch-axis-end");
      const before = figure.querySelector(".catch-order-before");
      const after = figure.querySelector(".catch-order-after");
      if (!axis || !rule || !mid || !end || !before || !after) return;

      const state = { progress: 0 };
      let width = axis.clientWidth;
      function render() {
        if (!width) return;
        const p = state.progress;
        // The first 760 cents occupy 40px. Both rows always share one cents/px scale.
        const limit = 1000 * Math.pow(80, p);
        const startWidth = 40 * 1000 / 760;
        const axisWidth = startWidth * Math.pow(width / startWidth, p);
        const pixelsPerCent = axisWidth / limit;
        const revealed = 760 + (76000 - 760) * (1 - (1 - p) ** 2);
        before.style.transform = `scaleX(${760 * pixelsPerCent / (width * 0.0095)})`;
        after.style.transform = `scaleX(${revealed * pixelsPerCent / (width * 0.95)})`;
        rule.style.transform = `scaleX(${axisWidth / width})`;
        mid.style.transform = `translateX(${(axisWidth - width) / 2}px)`;
        end.style.transform = `translateX(${axisWidth - width}px)`;
        mid.style.opacity = String(Math.max(0, Math.min(1, (axisWidth - 260) / 40)));
        mid.textContent = integer.format(roundTick(limit / 2));
        end.textContent = integer.format(roundTick(limit));
      }
      const resize = () => { width = axis.clientWidth; render(); };
      ScrollTrigger.addEventListener("refresh", resize);
      cleanups.push(() => {
        ScrollTrigger.removeEventListener("refresh", resize);
        for (const node of [before, after, rule, mid, end]) node.style.removeProperty("transform");
        mid.style.removeProperty("opacity");
        mid.textContent = "40,000";
        end.textContent = "80,000";
      });
      render();
      timeline.to(state, { progress: 1, duration: 1.5, ease: "none", onUpdate: render }, 0);
    }

    function customerFlow(figure, timeline) {
      const path = figure.querySelector(".catch-lineage path");
      const bar = figure.querySelector(".catch-customer-after");
      if (!path || !bar) return;
      timeline.fromTo(path, { drawSVG: "0%" }, { drawSVG: "100%", duration: 0.8 }, 0);
      timeline.fromTo(bar, { scaleX: 1250 / 76490 }, {
        scaleX: 1, duration: 0.8, ease: "power1.out"
      }, 0.8);
      // No scrubbed counter here: a paused scroll must never show a value that is not in the comment.
    }

    function stepAnimation(step) {
      const timeline = gsap.timeline({ paused: true });
      const flap = step.querySelector(".catch-position b");
      const gutters = step.querySelectorAll(".catch-gutter");
      if (flap) timeline.fromTo(flap, { rotationX: -88 }, { rotationX: 0, duration: 0.35 }, 0);
      if (gutters.length) timeline.fromTo(gutters, { scaleX: 0 }, {
        scaleX: 1, duration: 0.35, stagger: 0.08
      }, 0.1);
      // The scramble runs in real time, so a paused scroll always rests on the true value.
      const scramble = gsap.timeline({ paused: true });
      step.querySelectorAll("[data-catch-scramble]").forEach((node, i) => {
        const visible = animatedCopy(node);
        scramble.to(visible, {
          scrambleText: { text: visible.textContent, chars: "+-/", speed: 0.65 },
          duration: 0.55
        }, i * 0.08);
      });
      if (scramble.getChildren().length) timeline.call(() => scramble.restart(), null, 0.01);

      const zoom = step.querySelector("[data-catch-zoom]");
      const customer = step.querySelector("[data-catch-customer]");
      if (zoom) orderZoom(zoom, timeline);
      if (customer) customerFlow(customer, timeline);
      return timeline;
    }

    // The summary runs once in real time, even while the desktop scroll is stopped.
    const summary = gsap.timeline({ paused: true });
    steps[4].querySelectorAll("td [data-catch-count]").forEach((node, i) => {
      const cell = node.closest("td");
      const beforeCell = cell?.previousElementSibling;
      if (!cell || !beforeCell) return;
      const at = i * 0.1;
      count(summary, node, parse(beforeCell.textContent), at);
      summary.set(cell, { backgroundColor: "var(--coral)", color: "var(--stage)" }, at + 0.8);
      summary.set(cell, { clearProps: "backgroundColor,color" }, at + 1);
    });

    const animations = steps.map(stepAnimation);
    if (conditions.desktop) {
      section.classList.add("catch-pinned");
      gsap.set(steps.slice(1), { opacity: 0, pointerEvents: "none" });
      const story = gsap.timeline({ paused: true });
      // Times are viewport heights, with 1.5 of the 3.5 reserved for the axis zoom.
      const starts = [0, 0.48, 0.96, 2.46, 3.05, 3.5];
      steps.forEach((step, i) => {
        if (i > 0) {
          story.set(steps[i - 1], { opacity: 0, pointerEvents: "none" }, starts[i]);
          story.set(step, { opacity: 1, pointerEvents: "auto" }, starts[i]);
        }
        const duration = (starts[i + 1] - starts[i]) * (i === 2 ? 0.96 : 0.8);
        story.add(animations[i].duration(duration).paused(false), starts[i]);
      });
      story.to({}, { duration: starts[5] - story.duration() });
      let summaryStarted = false;
      ScrollTrigger.create({
        trigger: stage, animation: story, pin: true, scrub: true,
        start: () => stage.offsetHeight <= window.innerHeight ? "center center" : "top top",
        end: () => "+=" + window.innerHeight * starts[5],
        onUpdate: self => {
          if (!summaryStarted && self.progress >= starts[4] / starts[5]) {
            summaryStarted = true;
            summary.play();
          }
        }
      });
      cleanups.push(() => section.classList.remove("catch-pinned"));
    } else {
      steps.forEach((step, i) => {
        ScrollTrigger.create({
          trigger: step, start: "top 85%", once: true,
          onEnter: () => {
            animations[i].play();
            if (i === steps.length - 1) summary.play();
          }
        });
      });
    }
    return () => { cleanups.forEach(cleanup => cleanup()); };
  });
})();
