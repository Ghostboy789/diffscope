(() => {
  const section = document.getElementById("catch");
  const { gsap, ScrollTrigger } = window;
  if (!section || !gsap || !ScrollTrigger) return;

  gsap.matchMedia().add("(min-width: 768px) and (prefers-reduced-motion: no-preference)", () => {
    gsap.registerPlugin(ScrollTrigger);
    const stage = section.querySelector(".catch-stage");
    const position = section.querySelector(".catch-position");
    const steps = [...section.querySelectorAll(".catch-step")];
    section.classList.add("catch-enhanced");

    // Keeping the steps in one grid cell reserves space for the tallest figure.
    const reveals = steps.map(step => gsap.fromTo(step, { opacity: 0 }, {
      opacity: 1, duration: 0.25, ease: "power2.out", paused: true
    }));
    let current = 0;
    reveals[current].progress(1);
    steps[current].classList.add("catch-current");
    position.textContent = `1 / ${steps.length}`;

    function showStep({ progress }) {
      const next = Math.min(steps.length - 1, Math.floor(progress * steps.length));
      if (current === next) return;
      reveals[current].pause(0);
      steps[current].classList.remove("catch-current");
      steps[next].classList.add("catch-current");
      reveals[next].restart();
      position.textContent = `${next + 1} / ${steps.length}`;
      current = next;
    }

    const pin = ScrollTrigger.create({
      trigger: stage,
      pin: true,
      start: "center center",
      end: () => "+=" + window.innerHeight * 0.55 * steps.length,
      onUpdate: showStep,
      onRefresh: showStep
    });
    let active = true;
    document.fonts?.ready.then(() => {
      if (active) pin.refresh();
    });

    return () => {
      active = false;
      section.classList.remove("catch-enhanced");
      steps[current].classList.remove("catch-current");
      position.textContent = "";
    };
  });
})();
