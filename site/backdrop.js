(() => {
  'use strict';

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  canvas.className = 'diff-stream';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);

  const status = { prefix: 'order_id 101  status  complete', after: 'completed', mark: '+', color: 'lime' };
  const amount = { prefix: 'order_id 103  amount_cents  760', after: '76,000', mark: '−', color: 'coral' };
  const layers = [
    { size: 10, alpha: 0.07, speed: 3, spacing: 70, entries: [
      'baseline.orders', 'FULL OUTER JOIN', 'candidate.orders', 'IS NOT DISTINCT FROM',
      'meta.diffscope_keys', 'GROUP BY', 'COUNT(*)', 'quantile_cont', 'IS DISTINCT FROM',
      'order_id', 'status', 'amount_cents', 'customer_id', 'total_amount_cents'
    ] },
    { size: 12, alpha: 0.10, speed: 6, spacing: 100, entries: [
      'rows 8 → 8', 'customer_id 2  total_amount_cents  1,250 → 76,490', 'changed 2',
      'sum(amount_cents)  5,525.0 → 80,765.0', 'unchanged 6', '+1,361.8%'
    ] },
    { size: 14, alpha: 0.14, speed: 10, spacing: 150, entries: [amount, status] }
  ];

  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const light = matchMedia('(prefers-color-scheme: light)');
  const desktopPointer = matchMedia('(min-width: 768px) and (hover: hover) and (pointer: fine)');
  const frameMs = 1000 / 30;
  let rows = [];
  let width, height, mono, colors;
  let pointer = null;
  let frame, lastTick, lastPaint;
  let elapsed = 0;
  let nextDiff = diffDelay();

  function diffDelay() {
    return 2500 + Math.random() * 1500;
  }

  function readTokens() {
    const style = getComputedStyle(canvas);
    const token = name => style.getPropertyValue('--' + name).trim();
    mono = token('mono');
    colors = { ink: token('ink'), lime: token('lime'), coral: token('coral') };
  }

  function layout() {
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    rows = [];
    layers.forEach((layer, depth) => {
      const font = layer.size + 'px ' + mono;
      ctx.font = font;
      const entries = layer.entries.map(entry => {
        const edit = typeof entry === 'string' ? null : entry;
        const prefix = edit ? edit.prefix + ' → ' : entry;
        const text = edit ? prefix + edit.after : prefix;
        return { edit, prefix, text, width: ctx.measureText(text).width, offset: ctx.measureText(prefix).width };
      });
      const density = width < 768 ? 0.5 : 1;
      const count = Math.max(1, Math.min(32, Math.ceil(height / layer.spacing * density)));
      const span = height + layer.size;
      for (let i = 0; i < count; i++) {
        const column = (i + depth) % 3;
        const row = { layer, font, entries, index: i % entries.length, column,
          y: (i + (depth + 1) / 4) * span / count, span };
        setEntry(row);
        rows.push(row);
      }
    });
    updateDimmer();
    restart();
  }

  function setEntry(row) {
    const entry = row.entries[row.index];
    row.entry = entry;
    const margin = Math.min(40, width * 0.05);
    row.x = margin + row.column / 2 * Math.max(0, width - entry.width - 2 * margin);
    row.start = null;
    row.settled = reduced.matches;
  }

  function updateDimmer() {
    canvas.style.opacity = 0.5 + 0.5 * Math.min(1, Math.max(0, window.scrollY) / (height || 1));
  }

  function startDiff() {
    const visible = rows.filter(row => row.entry.edit && row.y > row.layer.size + 20 && row.y < height);
    const fresh = visible.filter(row => !row.settled);
    const choices = fresh.length ? fresh : visible;
    if (choices.length) choices[Math.floor(Math.random() * choices.length)].start = elapsed;
    nextDiff = elapsed + diffDelay();
  }

  // Reveal real glyphs from left to right without inventing intermediate values.
  function scramble(after, age) {
    const tick = Math.floor(age / 60);
    const revealed = Math.floor(after.length * age / 400);
    return after.slice(0, revealed) + Array.from(after.slice(revealed),
      (_, i) => '/_·'[(tick + i) % 3]).join('');
  }

  function paint(delta) {
    ctx.clearRect(0, 0, width, height);
    if (!reduced.matches && elapsed >= nextDiff) startDiff();
    for (const row of rows) {
      const { layer } = row;
      row.y -= layer.speed * delta / 1000;
      if (row.y < 0) {
        row.y += row.span;
        row.index = (row.index + 1) % row.entries.length;
        setEntry(row);
      }
      const { edit, text, prefix, offset } = row.entry;
      let alpha = layer.alpha;
      if (pointer) {
        const dx = Math.max(row.x - pointer.x, pointer.x - row.x - row.entry.width, 0);
        const distance = Math.hypot(dx, pointer.y - row.y + layer.size / 2);
        alpha += 0.05 * Math.max(0, 1 - distance / 140) ** 2;
      }
      const age = row.start === null ? Infinity : elapsed - row.start;
      if (age >= 400 && row.start !== null) row.settled = true;
      const glow = Math.min(1, Math.max(0, 1 - (age - 400) / 1500));
      ctx.font = row.font;
      ctx.fillStyle = colors.ink;
      const brightness = alpha + (0.30 - alpha) * glow;
      ctx.globalAlpha = brightness;
      if (glow > 0) {
        ctx.fillText(prefix, row.x, row.y);
        const value = age < 400 ? scramble(edit.after, age) : edit.after;
        ctx.globalAlpha = brightness * (1 - glow);
        if (glow < 1) ctx.fillText(value, row.x + offset, row.y);
        ctx.fillStyle = colors[edit.color];
        ctx.globalAlpha = 0.30 * glow;
        ctx.fillText(edit.mark, row.x - layer.size, row.y);
        ctx.fillText(value, row.x + offset, row.y);
      } else {
        ctx.fillText(edit && !row.settled ? edit.prefix : text, row.x, row.y);
      }
    }
  }

  function tick(now) {
    if (now - lastTick >= frameMs - 0.2) {
      const delta = Math.min(now - lastPaint, 100);
      elapsed += delta;
      paint(delta);
      lastPaint = now;
      lastTick += frameMs;
      if (now - lastTick >= frameMs) lastTick = now;
    }
    frame = requestAnimationFrame(tick);
  }

  function restart() {
    cancelAnimationFrame(frame);
    if (document.hidden) return;
    paint(0);
    if (reduced.matches) return;
    lastPaint = lastTick = performance.now();
    frame = requestAnimationFrame(tick);
  }

  function trackPointer(event) {
    if (event.pointerType !== 'touch') pointer = { x: event.clientX, y: event.clientY };
  }

  function clearPointer() { pointer = null; }
  function configurePointer() {
    clearPointer();
    window.removeEventListener('pointermove', trackPointer);
    if (desktopPointer.matches && !reduced.matches) {
      window.addEventListener('pointermove', trackPointer, { passive: true });
    }
  }

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(layout, 120);
  });
  window.addEventListener('scroll', updateDimmer, { passive: true });
  document.addEventListener('visibilitychange', restart);
  document.documentElement.addEventListener('pointerleave', clearPointer);
  window.addEventListener('blur', clearPointer);
  desktopPointer.addEventListener('change', configurePointer);
  reduced.addEventListener('change', () => { configurePointer(); layout(); });
  light.addEventListener('change', () => { readTokens(); restart(); });
  readTokens();
  configurePointer();
  layout();
  if (document.fonts.status === 'loading') document.fonts.ready.then(layout);
})();
