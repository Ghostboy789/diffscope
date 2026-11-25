// All count-ups finish by replacing their temporary display with a single text node.
const counts = (() => {
  function check(element) {
    if (element.textContent !== element.dataset.final) {
      throw new Error(`Expected ${element.dataset.final}, got ${element.textContent}`);
    }
  }

  function land(element, text) {
    element.textContent = text;
    check(element);
  }

  function add(timeline, element, start, duration, position, ease, makeDisplay) {
    check(element);
    const target = element.dataset.final;
    const digits = target.split(".")[1]?.length || 0;
    const format = new Intl.NumberFormat("en-US", {
      minimumFractionDigits: digits, maximumFractionDigits: digits
    });
    const value = { n: start };
    let display;
    timeline.to(value, {
      n: Number(target.replaceAll(",", "")), duration, ease,
      onStart: () => { display = makeDisplay(element); },
      onUpdate: () => { if (display) display.textContent = format.format(value.n); },
      onComplete: () => land(element, format.format(value.n))
    }, position);
  }

  function finishWhenHidden(timeline) {
    const finish = () => {
      if (document.hidden && timeline.isActive()) timeline.progress(1, false);
    };
    document.addEventListener("visibilitychange", finish);
    return () => document.removeEventListener("visibilitychange", finish);
  }

  return { add, check, land, finishWhenHidden };
})();
