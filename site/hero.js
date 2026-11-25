(() => {
  const { gsap, ScrollTrigger, SplitText } = window;
  if (!gsap) return;
  const hero = document.querySelector(".opening");
  if (!hero) return;
  const media = gsap.matchMedia();
  const motion = "(prefers-reduced-motion: no-preference)";
  const reduce = "(prefers-reduced-motion: reduce)";

  // Use the same eight positions for the static diagram and the canvas.
  function scopeField(moving) {
    const canvas = hero.querySelector(".scope-canvas");
    const map = hero.querySelector(".scope-points");
    const ctx = canvas?.getContext("2d");
    if (!ctx || !map || !window.ResizeObserver) return null;
    const dots = Array.from(map.querySelectorAll("circle"), dot => ({
      x: dot.cx.baseVal.value, y: dot.cy.baseVal.value, radius: dot.r.baseVal.value,
      hit: dot.classList.contains("scope-hit")
    }));
    const field = { growth: moving ? 1 : 10 };
    const pointer = { x: 0, y: 0, inside: false };
    const scheme = matchMedia("(prefers-color-scheme: light)");
    let lime, coral, ticking = false;

    function paint(time = 0) {
      ctx.clearRect(0, 0, 360, 216);
      dots.forEach((dot, i) => {
        const dx = dot.x - pointer.x;
        const dy = dot.y - pointer.y;
        const distance = Math.hypot(dx, dy);
        const push = pointer.inside ? Math.max(0, 1 - distance / 80) * 13 / Math.max(1, distance) : 0;
        ctx.fillStyle = dot.hit && field.growth > 1 ? coral : lime;
        ctx.globalAlpha = moving ? 0.89 + 0.11 * Math.cos(time * Math.PI * 2 / 3 - i * 0.4) : 1;
        ctx.beginPath();
        const radius = dot.hit ? dot.radius * field.growth / 10 : dot.radius;
        ctx.arc(dot.x + dx * push, dot.y + dy * push, radius, 0, 2 * Math.PI);
        ctx.fill();
      });
    }
    function resize() {
      const box = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(box.width * dpr));
      canvas.height = Math.max(1, Math.round(box.height * dpr));
      ctx.setTransform(canvas.width / 360, 0, 0, canvas.height / 216, 0, 0);
      const colors = getComputedStyle(hero);
      lime = colors.getPropertyValue("--lime").trim();
      coral = colors.getPropertyValue("--coral").trim();
      paint();
    }
    resize();
    map.style.visibility = "hidden";
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    scheme.addEventListener("change", resize);

    let stop = () => {};
    if (moving && ScrollTrigger) {
      const xTo = gsap.quickTo(pointer, "x", { duration: 0.18 });
      const yTo = gsap.quickTo(pointer, "y", { duration: 0.18 });
      function move(event) {
        if (event.pointerType === "touch") return;
        const box = canvas.getBoundingClientRect();
        pointer.inside = true;
        xTo((event.clientX - box.left) * 360 / box.width);
        yTo((event.clientY - box.top) * 216 / box.height);
      }
      function leave() { pointer.inside = false; }
      function toggle(active) {
        const run = active && !document.hidden;
        if (ticking === run) return;
        ticking = run;
        if (run) gsap.ticker.add(paint);
        else gsap.ticker.remove(paint);
      }
      const trigger = ScrollTrigger.create({
        trigger: hero, start: "top bottom", end: "bottom top",
        onToggle: self => toggle(self.isActive)
      });
      const visibility = () => toggle(trigger.isActive);
      visibility();
      document.addEventListener("visibilitychange", visibility);
      canvas.addEventListener("pointermove", move);
      canvas.addEventListener("pointerleave", leave);
      stop = () => {
        toggle(false);
        trigger.kill();
        document.removeEventListener("visibilitychange", visibility);
        canvas.removeEventListener("pointermove", move);
        canvas.removeEventListener("pointerleave", leave);
      };
    }
    return {
      field,
      dispose() {
        stop();
        observer.disconnect();
        scheme.removeEventListener("change", resize);
        map.style.removeProperty("visibility");
        ctx.clearRect(0, 0, 360, 216);
      }
    };
  }

  function wheels(element) {
    const finalText = element.textContent;
    const original = document.createElement("span");
    original.textContent = finalText;
    original.className = "score-original";
    const reels = document.createElement("span");
    reels.className = "reels";
    reels.setAttribute("aria-hidden", "true");
    const strips = [];
    const comma = document.createElement("span");
    comma.textContent = ",";
    for (const place of [10000, 1000, 100, 10, 1]) {
      if (place === 100) reels.append(comma);
      const reel = document.createElement("span");
      reel.className = "reel";
      const strip = document.createElement("span");
      strip.className = "reel-strip";
      for (let n = 0; n <= 10; n++) {
        const digit = document.createElement("span");
        digit.textContent = String(n % 10);
        strip.append(digit);
      }
      reel.append(strip);
      reels.append(reel);
      strips.push({ place, reel, setY: gsap.quickSetter(strip, "yPercent") });
    }
    element.replaceChildren(original, reels);
    function render(n) {
      comma.hidden = n < 1000;
      element.style.color = n < 10000 ? "var(--ink)" : "var(--coral)";
      for (const { place, reel, setY } of strips) {
        reel.hidden = n < place;
        const value = n / place;
        const whole = Math.floor(value);
        // Higher wheels carry only near the end of the lower wheel's turn.
        const fraction = place === 1 ? value - whole : Math.max(0, (value - whole - 0.9) * 10);
        setY(-(whole % 10 + fraction) * 100 / 11);
      }
    }
    return {
      render,
      restore() {
        element.textContent = finalText;
        element.style.removeProperty("color");
      }
    };
  }

  media.add({ motion, reduce }, context => {
    const headline = hero.querySelector("#headline");
    const subline = hero.querySelector(".hero-subline");
    const score = hero.querySelector(".odometer");
    const stamp = hero.querySelector(".stamp");
    const stage = hero.querySelector(".hero-main");
    const animate = !context.conditions.reduce && !!(headline && subline && score && stamp && stage && SplitText && ScrollTrigger);
    const scope = scopeField(animate);
    if (!animate) return () => scope?.dispose();

    const display = wheels(score);
    const counter = { cents: 760 };
    display.render(counter.cents);
    gsap.set(stamp, { autoAlpha: 0 });
    let active = true;
    context.add("play", () => {
      const title = SplitText.create(headline, { type: "words,chars", mask: "chars", tag: "span" });
      const sub = SplitText.create(subline, { type: "words", tag: "span" });
      const timeline = gsap.timeline();
      timeline.from(title.chars, { yPercent: 105, skewY: 5, duration: 0.9, stagger: 0.02, ease: "power3.out" })
        .from(sub.words, { opacity: 0, duration: 0.32, stagger: 0.04 }, 0.75)
        .to(counter, {
          cents: 76000, duration: 1.6, ease: "expo.out",
          onUpdate: () => display.render(counter.cents), onComplete: display.restore
        })
        .addLabel("impact")
        .fromTo(stamp, { scale: 1.6, rotation: -15 }, {
          scale: 1, rotation: -9, autoAlpha: 1, duration: 0.35, ease: "back.out(3)"
        }, "impact")
        .to(stage, { x: 4, duration: 1 / 60, ease: "none" }, "impact")
        .to(stage, { x: -4, duration: 1 / 60, ease: "none" }, "impact+=" + 1 / 60)
        .set(stage, { x: 0 }, "impact+=" + 2 / 60);
      if (scope) timeline.to(scope.field, { growth: 10, duration: 1.2, ease: "power2.out" }, "impact");
    });
    Promise.resolve(document.fonts?.ready).then(() => { if (active) context.play(); });
    return () => {
      active = false;
      display.restore();
      scope?.dispose();
    };
  });

  media.add("(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)", () => {
    const remove = [];
    hero.querySelectorAll(".action").forEach(link => {
      const xTo = gsap.quickTo(link, "x", { duration: 0.2 });
      const yTo = gsap.quickTo(link, "y", { duration: 0.2 });
      const move = event => {
        const box = link.getBoundingClientRect();
        xTo((event.clientX - box.left - box.width / 2) * 0.1);
        yTo((event.clientY - box.top - box.height / 2) * 0.16);
      };
      const leave = () => { xTo(0); yTo(0); };
      link.addEventListener("pointermove", move);
      link.addEventListener("pointerleave", leave);
      remove.push(() => {
        link.removeEventListener("pointermove", move);
        link.removeEventListener("pointerleave", leave);
      });
    });
    return () => remove.forEach(dispose => dispose());
  });
})();
