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
    desktop: "(min-width: 768px) and (min-height: 640px) and (pointer: fine)",
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
      const gutters = step.querySelectorAll(".catch-gutter");
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
      let started = false;
      if (scramble.getChildren().length) timeline.call(() => {
        if (started) return;
        started = true;
        scramble.restart();
      }, null, 0.01);

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
      counts.add(summary, node, parse(beforeCell.textContent), 0.8, at, "power1.out", animatedCopy);
      summary.set(cell, { backgroundColor: "var(--coral)", color: "var(--stage)" }, at + 0.8);
      summary.set(cell, { clearProps: "backgroundColor,color" }, at + 1);
    });

    cleanups.push(counts.finishWhenHidden(summary));
    const finishSummary = () => summary.progress(1, false);
    const animations = steps.map(stepAnimation);
    const flaps = steps.map(step => gsap.from(step.querySelector(".catch-position b"), {
      rotationX: -50, duration: 0.2, ease: "power2.out", paused: true, immediateRender: false
    }));
    if (conditions.desktop) {
      section.classList.add("catch-pinned");
      let current = -1;
      let ends = [];
      let summaryStarted = false;
      function measure() {
        let distance = 0;
        ends = steps.map(step => {
          distance += step.offsetHeight;
          return distance;
        });
        return distance;
      }
      function render(self) {
        const offset = self.progress * ends[ends.length - 1];
        const i = ends.findIndex(end => offset <= end);
        if (i < 0) return;
        if (current !== i) {
          if (current === steps.length - 1) finishSummary();
          if (current !== -1) flaps[i].restart();
          steps[current]?.classList.remove("is-current");
          steps[i].classList.add("is-current");
          current = i;
        }
        const start = ends[i - 1] || 0;
        animations[i].progress((offset - start) / (ends[i] - start), false);
        if (i === steps.length - 1 && !summaryStarted) {
          summaryStarted = true;
          summary.play();
        }
      }
      ScrollTrigger.create({
        trigger: stage, pin: true, start: "top top", refreshPriority: 1,
        end: () => "+=" + measure(), onUpdate: render, onRefresh: render, onLeave: finishSummary
      });
      cleanups.push(() => {
        section.classList.remove("catch-pinned");
        steps.forEach(step => step.classList.remove("is-current"));
      });
    } else {
      steps.forEach((step, i) => {
        ScrollTrigger.create({
          trigger: step, start: "top 85%", once: true,
          onEnter: () => {
            if (i > 0) flaps[i].play();
            animations[i].play();
            if (i === steps.length - 1) summary.play();
          },
          onLeave: i === steps.length - 1 ? finishSummary : undefined,
          onLeaveBack: () => { if (summary.isActive()) finishSummary(); }
        });
      });
    }
    return () => { cleanups.forEach(cleanup => cleanup()); };
  });
})();
