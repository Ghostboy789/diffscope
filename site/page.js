(() => {
  const { gsap, ScrollTrigger, SplitText, ScrambleTextPlugin, DrawSVGPlugin, Flip, Lenis } = window;
  const motion = "(prefers-reduced-motion: no-preference)";
  const reduce = "(prefers-reduced-motion: reduce)";

  document.querySelectorAll(".instructions pre").forEach(pre => {
    const code = pre.querySelector("code");
    if (!code) return;
    const row = document.createElement("div");
    row.className = "copy-row";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copy-button";
    button.textContent = "Copy";
    const status = document.createElement("span");
    status.className = "sr-only";
    status.setAttribute("role", "status");
    row.append(button, status);
    pre.before(row);
    let reset;
    button.addEventListener("click", async () => {
      clearTimeout(reset);
      try {
        await navigator.clipboard.writeText(code.textContent);
        button.textContent = "Copied";
        button.dataset.copied = "";
        status.textContent = "Code copied.";
        reset = setTimeout(() => {
          button.textContent = "Copy";
          delete button.dataset.copied;
          status.textContent = "";
        }, 200);
      } catch {
        const selection = window.getSelection();
        if (!selection) return;
        const range = document.createRange();
        range.selectNodeContents(code);
        selection.removeAllRanges();
        selection.addRange(range);
        button.textContent = "Use system copy";
        status.textContent = "Code selected. Use your system copy command.";
        reset = setTimeout(() => { button.textContent = "Copy"; }, 2500);
      }
    });
  });

  if (!gsap || !ScrollTrigger || !SplitText || !ScrambleTextPlugin || !DrawSVGPlugin || !Flip) return;
  gsap.registerPlugin(ScrollTrigger, SplitText, ScrambleTextPlugin, DrawSVGPlugin, Flip);
  const media = gsap.matchMedia();

  media.add("(min-width: 768px) and (pointer: fine) and (prefers-reduced-motion: no-preference)", () => {
    if (!Lenis) return;
    const lenis = new Lenis({ autoRaf: false, anchors: true });
    const tick = seconds => lenis.raf(seconds * 1000);
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(tick);
      lenis.destroy();
    };
  });

  media.add({ motion, reduce }, context => {
    // The HTML is the finished view. Reverting a media query restores it.
    if (context.conditions.reduce) return;
    const restore = [];

    // The original reserves the final space and remains the accessible value.
    function overlay(element) {
      const original = document.createElement("span");
      original.className = "original";
      original.textContent = element.textContent;
      const visible = document.createElement("span");
      visible.setAttribute("aria-hidden", "true");
      const pair = document.createElement("span");
      pair.className = "animated-text";
      pair.append(original, visible);
      element.replaceChildren(pair);
      restore.push(() => element.replaceChildren(original.textContent));
      return visible;
    }

    function count(timeline, cell, start, duration, position, ease) {
      const endText = cell.textContent.trim();
      const end = Number(endText.replaceAll(",", ""));
      const digits = endText.split(".")[1]?.length || 0;
      const format = new Intl.NumberFormat("en-US", {
        minimumFractionDigits: digits, maximumFractionDigits: digits
      });
      const display = overlay(cell);
      const value = { n: start };
      display.textContent = format.format(start);
      timeline.to(value, {
        n: end, duration, ease,
        onUpdate: () => { display.textContent = format.format(value.n); },
        onComplete: () => { display.textContent = endText; }
      }, position);
    }

    function onView(element) {
      return gsap.timeline({ scrollTrigger: { trigger: element, start: "top 94%", once: true } });
    }
    document.querySelectorAll(".numeric-shifts").forEach(table => {
      const timeline = onView(table);
      table.querySelectorAll("tbody tr").forEach((row, i) => {
        const [, before, after] = row.cells;
        if (!before || !after) return;
        count(timeline, after, Number(before.textContent.replaceAll(",", "")), 0.8, i * 0.1, "power2.out");
        timeline.fromTo(after, { backgroundColor: "var(--coral)", color: "var(--stage)" }, {
          backgroundColor: "var(--panel)", color: "var(--coral)", duration: 0.24,
          immediateRender: false, clearProps: "backgroundColor,color"
        }, 0.8 + i * 0.1);
      });
    });

    const timings = document.querySelector(".timings");
    if (timings) {
      const timeline = onView(timings);
      timings.querySelectorAll("tbody tr").forEach(row => {
        const label = row.querySelector(".timing-value");
        const bar = row.querySelector(".timing-track rect");
        if (!label || !bar) return;
        const duration = Number(label.textContent) * 3;
        count(timeline, label, 0, duration, 0, "none");
        timeline.from(bar, { scaleX: 0, duration, ease: "none" }, 0);
      });
    }

    const scenarios = document.querySelector(".scenarios");
    if (scenarios) {
      const log = onView(scenarios);
      scenarios.querySelectorAll("tbody tr").forEach((row, i) => {
        const name = row.querySelector(".log-name");
        const result = row.querySelector(".log-result");
        const known = row.querySelector(".known");
        if (!name || !result || !known) return;
        const start = i * 0.12;
        [name, result].forEach((element, part) => {
          const text = element.textContent;
          const display = overlay(element);
          const cursor = { chars: 0 };
          log.to(cursor, {
            chars: text.length, duration: part ? 0.34 : 0.18, ease: "none", snap: "chars",
            onUpdate: () => { display.textContent = text.slice(0, cursor.chars); }
          }, start + part * 0.18);
        });
        log.from(known, { opacity: 0, duration: 0.12 }, start + 0.52);
      });
    }

    document.documentElement.classList.add("nav-motion");
    return () => {
      restore.forEach(reset => reset());
      document.documentElement.classList.remove("nav-motion");
    };
  });
})();
