(() => {
  const scope = document.querySelector(".scope");
  const { gsap } = window;
  if (!gsap || !scope || !("IntersectionObserver" in window) || !("ResizeObserver" in window)) return;

  const motion = matchMedia("(prefers-reduced-motion: no-preference)");
  let inView = false;
  let afterPaint = false;
  let loading = false;
  let failed = false;
  let dispose;

  async function sync() {
    if (!motion.matches) {
      dispose?.();
      dispose = undefined;
    }
    if (!afterPaint || !inView || document.hidden || !motion.matches || loading || failed || dispose) return;
    loading = true;
    try {
      const { createScope } = await import("./scope-scene.mjs");
      if (inView && !document.hidden && motion.matches) {
        dispose = createScope(scope, gsap, () => { failed = true; });
      }
    } catch {
      failed = true;
    } finally {
      loading = false;
    }
  }

  new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    sync();
  }).observe(scope.querySelector(".scope-window"));
  motion.addEventListener("change", sync);
  document.addEventListener("visibilitychange", sync);

  function afterLoad() {
    const ready = () => {
      afterPaint = true;
      sync();
    };
    if ("requestIdleCallback" in window) requestIdleCallback(ready, { timeout: 500 });
    else setTimeout(ready, 80);
  }
  if (document.readyState === "complete") afterLoad();
  else window.addEventListener("load", afterLoad, { once: true });
})();
