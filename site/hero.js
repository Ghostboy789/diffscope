(() => {
  const { gsap, SplitText } = window;
  const hero = document.querySelector(".opening");
  if (!hero) return;

  const motion = "(prefers-reduced-motion: no-preference)";
  const reduce = "(prefers-reduced-motion: reduce)";

  // The static SVG holds the finished field, including when scripts are disabled.
  const field = hero.querySelector(".data-field");
  const stamp = hero.querySelector(".stamp");
  const thermal = field.querySelector("#thermal");
  const pattern = field.querySelector("#hot-row");
  let fieldLeft, fieldTop;
  const updateField = () => {
    const box = field.getBoundingClientRect();
    fieldLeft = box.left + window.scrollX;
    fieldTop = box.top + window.scrollY;
    const mark = stamp.getBoundingClientRect();
    const x = mark.left + mark.width / 2 - box.left;
    const y = mark.top + mark.height / 2 - box.top;
    thermal.setAttribute("cx", x);
    thermal.setAttribute("cy", y);
    // Keep the changed row just above the stamp, including on narrow screens.
    const rowX = Math.max(0, Math.min(box.width - 210, x - 80));
    const rowY = y - mark.height / 2 - 10;
    const shift = `translate(${rowX} ${rowY - 66})`;
    pattern.setAttribute("patternTransform", shift);
    field.querySelector("#order-field").setAttribute("patternTransform", shift);
  };
  const size = new ResizeObserver(updateField);
  size.observe(hero);
  size.observe(hero.querySelector(".score"));
  updateField();

  if (!gsap) return;
  const media = gsap.matchMedia();

  function wheels(element) {
    const finalText = element.textContent;
    const original = document.createElement("span");
    original.textContent = finalText;
    original.className = "score-original";
    const reels = document.createElement("span");
    reels.className = "reels";
    reels.setAttribute("aria-hidden", "true");
    const strips = [];
    const startText = "760".padStart(finalText.length);
    let comma;
    Array.from(finalText).forEach((last, index) => {
      if (last === ",") {
        comma = document.createElement("span");
        comma.textContent = last;
        reels.append(comma);
        return;
      }
      const first = startText[index];
      const reel = document.createElement("span");
      reel.className = "reel";
      // Reserve this digit's finished advance even while a different glyph rolls past.
      const width = document.createElement("span");
      width.className = "reel-width";
      width.textContent = last;
      const strip = document.createElement("span");
      strip.className = "reel-strip";
      const distance = (Number(last) - Number(first) + 10) % 10 || 10;
      for (let i = 0; i <= distance; i++) {
        const digit = document.createElement("span");
        digit.textContent = i === 0 ? first : String((Number(first) + i) % 10);
        strip.append(digit);
      }
      reel.append(width, strip);
      reels.append(reel);
      strips.push(strip);
    });
    element.replaceChildren(original, reels);
    return {
      strips, comma,
      restore() {
        counts.land(element, finalText);
        element.style.removeProperty("color");
      }
    };
  }

  media.add({ motion, reduce }, context => {
    if (context.conditions.reduce) return;
    const score = hero.querySelector(".odometer");
    const heat = hero.querySelector(".thermal-cells");
    counts.check(score);
    const display = wheels(score);
    const timeline = gsap.timeline();
    timeline.set([stamp, heat, display.comma], { opacity: 0 })
      .set(score, { color: "var(--ink)" })
      .to(display.strips, {
        yPercent: (_, strip) => -100 * (strip.childElementCount - 1) / strip.childElementCount,
        duration: 1.6, ease: "expo.out", onComplete: display.restore
      }, 0)
      .set(display.comma, { opacity: 1 }, 0.06)
      .set(score, { color: "var(--coral)" }, 0.12)
      .addLabel("impact", 1.6)
      .fromTo(stamp, { scale: 1.25, rotation: -15 }, {
        scale: 1, rotation: -9, opacity: 1, duration: 0.35, ease: "power3.out"
      }, "impact")
      .to(heat, { opacity: 1, duration: 0.18, ease: "power2.out" }, "impact")
      .fromTo(stamp.querySelector(".stamp-flash"), { opacity: 1 }, {
        opacity: 0, duration: 0.24, ease: "power2.out"
      }, "impact");
    if (SplitText) {
      const subline = SplitText.create(".hero-subline", { type: "words", mask: "words", tag: "span" });
      timeline.from(subline.words, { yPercent: 100, duration: 0.32,
        stagger: 0.035, ease: "power3.out" }, 0.45);
    }
    if (window.ScrollTrigger) window.ScrollTrigger.create({
      trigger: hero, start: "top top", end: "bottom top", once: true,
      onLeave: () => timeline.progress(1, false)
    });
    const unlisten = counts.finishWhenHidden(timeline);
    return () => { unlisten(); display.restore(); };
  });

  media.add("(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)", () => {
    const remove = [];
    const spot = field.querySelector(".develop");
    let frame = 0;
    let pointer;
    const paint = () => {
      frame = 0;
      spot.setAttribute("transform", `translate(${pointer.pageX - fieldLeft} ${pointer.pageY - fieldTop})`);
      spot.setAttribute("visibility", "visible");
    };
    const moveSpot = event => {
      if (event.pointerType === "touch") return;
      pointer = event;
      if (!frame) frame = requestAnimationFrame(paint);
    };
    const hideSpot = () => {
      cancelAnimationFrame(frame);
      frame = 0;
      spot.setAttribute("visibility", "hidden");
    };
    hero.addEventListener("pointermove", moveSpot);
    hero.addEventListener("pointerleave", hideSpot);
    remove.push(() => {
      hideSpot();
      hero.removeEventListener("pointermove", moveSpot);
      hero.removeEventListener("pointerleave", hideSpot);
    });
    hero.querySelectorAll(".primary").forEach(link => {
      const xTo = gsap.quickTo(link, "x", { duration: 0.2 });
      const yTo = gsap.quickTo(link, "y", { duration: 0.2 });
      const move = event => {
        const box = link.getBoundingClientRect();
        const dx = (event.clientX - box.left - box.width / 2) * 0.1;
        const dy = (event.clientY - box.top - box.height / 2) * 0.16;
        const clamp = Math.min(1, 6 / (Math.hypot(dx, dy) || 1));
        xTo(dx * clamp);
        yTo(dy * clamp);
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
