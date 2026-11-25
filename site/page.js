(() => {
  const { gsap, ScrollTrigger, SplitText, ScrambleTextPlugin, DrawSVGPlugin, Flip, Draggable, InertiaPlugin, Lenis } = window;
  const motion = "(prefers-reduced-motion: no-preference)";
  const reduce = "(prefers-reduced-motion: reduce)";

  const root = document.documentElement;
  const toggle = document.querySelector(".theme-toggle");
  function switchTheme() {
    const light = root.dataset.theme !== "light";
    root.dataset.theme = light ? "light" : "dark";
    toggle.setAttribute("aria-pressed", String(light));
    try { localStorage.setItem("diffscope-theme", root.dataset.theme); } catch {}
  }
  toggle.hidden = false;
  toggle.setAttribute("aria-pressed", String(root.dataset.theme === "light"));
  let dragged = false;
  toggle.addEventListener("pointerdown", () => { dragged = false; });
  toggle.addEventListener("click", event => {
    if (event.detail === 0 || !dragged) switchTheme();
  });

  document.querySelectorAll(".instructions pre").forEach(pre => {
    const code = pre.querySelector("code");
    if (!code) return;
    const command = code.textContent;
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
        await navigator.clipboard.writeText(command);
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
        code.textContent = command;
        range.selectNodeContents(code);
        selection.removeAllRanges();
        selection.addRange(range);
        button.textContent = "Use system copy";
        status.textContent = "Code selected. Use your system copy command.";
        reset = setTimeout(() => { button.textContent = "Copy"; }, 2500);
      }
    });
  });

  if (!gsap) return;
  gsap.registerPlugin(...[ScrollTrigger, SplitText, ScrambleTextPlugin, DrawSVGPlugin, Flip,
    Draggable, InertiaPlugin].filter(Boolean));
  const media = gsap.matchMedia();

  if (Draggable && InertiaPlugin) {
    const cord = toggle.querySelector(".cord");
    media.add({ motion, reduce }, ({ conditions }) => {
      let recoil;
      InertiaPlugin.track(cord, "y");
      const [drag] = Draggable.create(cord, {
        trigger: toggle, type: "y", bounds: { minY: 0, maxY: 32 },
        dragClickables: true, minimumMovement: 4, allowNativeTouchScrolling: false,
        onDragStart() {
          dragged = true;
          recoil?.kill();
        },
        onDragEnd() {
          if (this.y >= 16) switchTheme();
          if (conditions.reduce) {
            gsap.set(cord, { y: 0 });
          } else {
            const velocity = InertiaPlugin.getVelocity(cord, "y");
            recoil = gsap.timeline()
              .to(cord, { inertia: { y: { velocity, min: 0, max: 34 }, duration: 0.07 } })
              .to(cord, { y: 0, duration: 0.22, ease: "back.out(1.7)" });
          }
        }
      });
      return () => {
        recoil?.kill();
        drag.kill();
        InertiaPlugin.untrack(cord, "y");
        gsap.set(cord, { clearProps: "transform" });
      };
    });
  }
  if (!ScrollTrigger) return;
  media.add("(min-width: 768px) and (pointer: fine) and (prefers-reduced-motion: no-preference)", () => {
    if (!Lenis || navigator.maxTouchPoints > 0) return;
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

    function onView(element, hasCounts = false) {
      const trigger = { trigger: element, start: "top 94%", once: true };
      if (hasCounts) {
        trigger.end = "bottom top";
        trigger.onLeave = self => self.animation.progress(1, false);
        trigger.onLeaveBack = self => {
          if (self.animation.isActive()) self.animation.progress(1, false);
        };
      }
      const timeline = gsap.timeline({ scrollTrigger: trigger });
      if (hasCounts) restore.push(counts.finishWhenHidden(timeline));
      return timeline;
    }
    const comment = document.querySelector("#comment .evidence");
    onView(comment).from(comment, { y: 36, duration: 0.45, ease: "power3.out" });
    document.querySelectorAll(".numeric-shifts").forEach(table => {
      const timeline = onView(table, true);
      table.querySelectorAll("tbody tr").forEach((row, i) => {
        const [, before, after] = row.cells;
        const at = i * 0.1;
        counts.add(timeline, after, Number(before.textContent.replaceAll(",", "")), 0.8, at, "power2.out", overlay);
        timeline.set(after, { backgroundColor: "var(--coral)", color: "var(--stage)" }, at + 0.8)
          .set(after, { clearProps: "backgroundColor,color" }, at + 1);
      });
    });
    const limits = document.querySelector("#limits");
    onView(limits).from(limits.querySelector(".limits-rule"), {
      scaleX: 0, duration: 0.3, ease: "power2.out"
    });
    if (DrawSVGPlugin) {
      const diagram = document.querySelector(".method-flow");
      onView(diagram).from(diagram.querySelectorAll(".flow-lines path"), {
        drawSVG: "0%", duration: 0.3, stagger: 0.19, ease: "power2.out"
      });
    }

    function type(timeline, element, duration, at) {
      const text = element.textContent;
      const display = overlay(element);
      const cursor = { chars: 0 };
      timeline.to(cursor, {
        chars: text.length, duration, ease: "none", snap: "chars",
        onUpdate: () => { display.textContent = text.slice(0, cursor.chars); },
        onComplete: () => { element.textContent = text; }
      }, at);
    }
    const terminal = document.querySelector(".instructions");
    const transcript = onView(terminal);
    terminal.querySelectorAll("pre code").forEach((code, i) => {
      type(transcript, code, 0.3, i * 0.22);
    });

    const timings = document.querySelector(".timings");
    if (timings) {
      const timeline = onView(timings, true);
      timings.querySelectorAll("tbody tr").forEach(row => {
        const label = row.querySelector(".timing-value");
        const bar = row.querySelector(".timing-track rect");
        if (!label || !bar) return;
        const duration = Number(label.textContent) * 3;
        counts.add(timeline, label, 0, duration, 0, "none", overlay);
        timeline.from(bar, { scaleX: 0, duration, ease: "none" }, 0);
      });
    }

    const scenarios = document.querySelector(".scenarios");
    if (scenarios) {
      const log = onView(scenarios);
      const rows = Array.from(scenarios.querySelectorAll("tbody tr"));
      const startTime = gsap.utils.distribute({ amount: 0.84, ease: "power1.out" });
      rows.forEach((row, i) => {
        const name = row.querySelector(".log-name");
        const result = row.querySelector(".log-result");
        const known = row.querySelector(".known");
        if (!name || !result || !known) return;
        const start = Number(startTime(i, row, rows));
        type(log, name, 0.18, start);
        type(log, result, 0.34, start + 0.18);
        log.from(known, { opacity: 0, duration: 0.12 }, start + 0.52);
      });
    }

    return () => {
      restore.forEach(reset => reset());
    };
  });
})();
