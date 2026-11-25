import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const MAX_CENTS = 80000;
const AXIS_HEIGHT = 7.2;
const WALL_Z = -3.05;
const ELEVATION = THREE.MathUtils.degToRad(24);
const TURN = THREE.MathUtils.degToRad(30);
const DRIFT = THREE.MathUtils.degToRad(5);
const GROW_AT = .7;
const GROW_SECONDS = .9;

export function createScope(scope, gsap, onFailure) {
  const plot = scope.querySelector(".scope-window");
  const canvas = plot.querySelector("canvas");
  const playback = scope.querySelector(".scope-playback");
  const context = canvas.getContext("webgl2", { antialias: false, powerPreference: "low-power" });
  if (!context || !context.getExtension("EXT_color_buffer_float")) throw new Error("WebGL buffers unavailable");

  const phone = matchMedia("(max-width: 760px), (pointer: coarse) and (max-width: 950px)");
  const fine = matchMedia("(hover: hover) and (pointer: fine)");
  const dark = matchMedia("(prefers-color-scheme: dark)");
  const cleanup = new AbortController();
  const { signal } = cleanup;
  const renderer = new THREE.WebGLRenderer({ canvas, context });
  renderer.toneMapping = THREE.NeutralToneMapping;
  const scene = new THREE.Scene();
  const backdrop = new THREE.Color();
  scene.background = backdrop;

  const labels = new CSS2DRenderer({ element: plot.querySelector(".scope-labels") });
  const camera = new THREE.PerspectiveCamera(36, 1, .1, 80);
  const key = new THREE.DirectionalLight("white", 2.0);
  key.position.set(-3.5, 7, 5);
  scene.add(key);

  const ground = new THREE.PlaneGeometry(60, 60);
  const surfaces = [new THREE.Vector3(.1, 0, 0), new THREE.Vector3(.4, 2, WALL_Z)]
    .map((center, index) => {
      const material = new THREE.ShaderMaterial({
        uniforms: {
          field: { value: backdrop },
          tint: { value: new THREE.Color() },
          center: { value: center },
          falloff: { value: index === 0 ? new THREE.Vector3(.13, 0, .19) : new THREE.Vector3(.13, .17, 0) }
        },
        vertexShader: `
          varying vec3 worldPoint;
          void main() {
            vec4 world = modelMatrix * vec4(position, 1.0);
            worldPoint = world.xyz;
            gl_Position = projectionMatrix * viewMatrix * world;
          }
        `,
        fragmentShader: `
          uniform vec3 field, tint, center, falloff;
          varying vec3 worldPoint;
          void main() {
            vec3 d = (worldPoint - center) * falloff;
            gl_FragColor = vec4(mix(field, tint, exp(-2.0 * dot(d, d))), 1.0);
          }
        `
      });
      const plane = new THREE.Mesh(ground, material);
      if (index === 0) plane.rotation.x = -Math.PI / 2;
      else plane.position.set(0, 30, WALL_Z);
      scene.add(plane);
      return material;
    });

  const rulePoints = [];
  const guideMaterial = new THREE.LineBasicMaterial({ transparent: true, opacity: .54 });
  function tag(text, className, x, y, z) {
    const element = document.createElement("div");
    element.className = className;
    element.append(text);
    const object = new CSS2DObject(element);
    object.position.set(x, y, z);
    scene.add(object);
    labels.domElement.append(element);
    return object;
  }
  const ticks = [0, MAX_CENTS / 2, MAX_CENTS].map(cents => {
    const y = cents * AXIS_HEIGHT / MAX_CENTS;
    rulePoints.push(new THREE.Vector3(-3.8, y, WALL_Z + .01), new THREE.Vector3(3.42, y, WALL_Z + .01));
    const label = tag(cents.toLocaleString("en-US"), "scope-axis-tick", -3.9, y, WALL_Z + .01);
    label.center.x = 1;
    return label;
  });
  const guides = new THREE.BufferGeometry().setFromPoints(rulePoints);
  scene.add(new THREE.LineSegments(guides, guideMaterial));

  const normal = new THREE.MeshPhysicalMaterial({ roughness: .35, metalness: .13, clearcoat: .75, clearcoatRoughness: .19 });
  const alarm = normal.clone();
  const slab = new RoundedBoxGeometry(.86, 1, .92, 2, .069);
  const rows = [...scope.querySelectorAll("[data-order]")];
  const shadeFootprint = new THREE.PlaneGeometry(1.65, 1.75);
  shadeFootprint.rotateX(-Math.PI / 2);
  const penumbra = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: { ink: { value: new THREE.Color() } },
    vertexShader: `
      varying vec2 footprint;
      void main() {
        footprint = uv * 2.0 - 1.0;
        gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 ink;
      varying vec2 footprint;
      void main() {
        vec2 d = footprint * vec2(1.05, 1.15);
        float shade = max(0.0, exp(-4.5 * dot(d, d)) - 0.02);
        gl_FragColor = vec4(ink, 0.48 * shade);
      }
    `
  });
  const shadows = new THREE.InstancedMesh(shadeFootprint, penumbra, rows.length);
  const translation = new THREE.Matrix4();
  scene.add(shadows);
  const orders = rows.map((row, index) => {
    const rear = index < 4;
    const x = (rear ? -2.55 : -2.8) + index % 4 * 1.7;
    const z = rear ? -1.45 : 1.48;
    const isBug = row.classList.contains("bug");
    const mesh = new THREE.Mesh(slab, isBug ? alarm : normal);
    mesh.position.set(x, 0, z);
    scene.add(mesh);
    shadows.setMatrixAt(index, translation.makeTranslation(x + .11, .009, z));
    const badge = document.createElement("div");
    badge.className = isBug ? "scope-tag bug" : "scope-tag";
    badge.append(row.querySelector("b").cloneNode(true), " ", row.querySelector(".order-diff").textContent);
    const leader = document.createElement("span");
    leader.className = "scope-tag-leader";
    const label = tag(leader, "scope-tag-anchor", x, 0, z);
    label.element.append(badge);
    label.center.set(0, 0);
    return { before: Number(row.dataset.before), cents: 0, mesh, label, badge, leader, rear, isBug };
  });
  shadows.instanceMatrix.needsUpdate = true;

  const bug = orders.find(order => order.isBug);
  const finalAmount = Number(scope.closest(".opening").querySelector(".hero-value").textContent.replaceAll(",", ""));
  const orbit = { spread: 0 };
  const intro = gsap.timeline({ paused: true })
    .to(orders, { cents: index => orders[index].before, duration: .32, stagger: .04, ease: "power2.out" }, .04)
    .to(bug, { cents: finalAmount, duration: GROW_SECONDS, ease: "power2.inOut" }, GROW_AT)
    .to(orbit, { spread: 1, duration: GROW_SECONDS, ease: "power2.inOut" }, GROW_AT);

  // The optic refracts the opaque scene. The unlit rim supplies a separate grazing highlight.
  const lensShape = new THREE.SphereGeometry(1, 40, 24);
  const glass = new THREE.MeshPhysicalMaterial({
    roughness: .043, transmission: 1, thickness: .78, ior: 1.45,
    clearcoat: .45, clearcoatRoughness: .15, envMapIntensity: .72
  });
  const optic = new THREE.Mesh(lensShape, glass);
  optic.scale.set(1, 1, .27);
  const rimShape = new THREE.TorusGeometry(.989, .019, 8, 64);
  const rimMaterial = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: { tint: { value: new THREE.Color() } },
    vertexShader: `
      varying vec3 surfaceNormal;
      void main() {
        surfaceNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 tint;
      varying vec3 surfaceNormal;
      void main() {
        vec3 n = normalize(surfaceNormal);
        float shine = pow(max(0.0, dot(n, normalize(vec3(-0.5, 0.8, 0.7)))), 3.0);
        gl_FragColor = vec4(tint, 0.28 + 0.57 * shine);
      }
    `
  });
  const lens = new THREE.Group();
  lens.add(optic, new THREE.Mesh(rimShape, rimMaterial));
  scene.add(lens);

  const glowScene = new THREE.Scene();
  glowScene.background = new THREE.Color(0);
  const glowMaterial = new THREE.MeshBasicMaterial({ toneMapped: false });
  const glow = new THREE.Mesh(slab, glowMaterial);
  glowScene.add(glow);
  const bloomSource = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType });
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), .23, .4, .015);
  const combine = new ShaderPass({
    uniforms: {
      tDiffuse: { value: null },
      // In the pinned pass, the first horizontal target holds only the blurred composite.
      halo: { value: null }
    },
    vertexShader: `
      varying vec2 samplePoint;
      void main() {
        samplePoint = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform sampler2D tDiffuse, halo;
      varying vec2 samplePoint;
      void main() {
        vec4 base = texture2D(tDiffuse, samplePoint);
        gl_FragColor = vec4(base.rgb + texture2D(halo, samplePoint).rgb, base.a);
      }
    `
  });
  // Attach the pinned pass’s blurred composite without cloning its render texture.
  combine.uniforms.halo.value = bloom.renderTargetsHorizontal[0].texture;
  const composer = new EffectComposer(renderer);
  const output = new OutputPass();
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(combine);
  composer.addPass(output);

  const floor = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const raycaster = new THREE.Raycaster();
  const pointerNdc = new THREE.Vector2();
  const target = new THREE.Vector3();
  const clamp = gsap.utils.clamp;
  const projected = new THREE.Vector3();
  let width, height;
  let pointer;
  let touch = !fine.matches;
  let inView = false;
  let ticking = false;
  let ready = false;
  let disposed = false;
  let needsSize = true;
  let needsTheme = true;
  let movingLens = true;
  let paused = false;
  let lastTime;
  let time = 0;
  let environment;

  function size() {
    width = plot.clientWidth;
    height = plot.clientHeight;
    if (!width || !height) return false;
    for (const order of orders) {
      order.labelWidth = order.badge.offsetWidth;
      order.labelHeight = order.badge.offsetHeight;
    }
    for (const tick of ticks) {
      tick.labelWidth = tick.element.offsetWidth;
      tick.labelHeight = tick.element.offsetHeight;
    }
    const dpr = Math.min(devicePixelRatio || 1, phone.matches ? 1.125 : 1.25);
    if (renderer.getPixelRatio() !== dpr) {
      renderer.setPixelRatio(dpr);
      composer.setPixelRatio(dpr);
    }
    renderer.setSize(width, height, false);
    composer.setSize(width, height);
    labels.setSize(width, height);
    const scale = dpr * (phone.matches ? .75 : 1);
    const glowWidth = Math.max(48, Math.round(width * scale));
    const glowHeight = Math.max(48, Math.round(height * scale));
    bloomSource.setSize(glowWidth, glowHeight);
    bloom.setSize(glowWidth, glowHeight);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    return true;
  }

  function theme() {
    const style = getComputedStyle(scope);
    const token = name => style.getPropertyValue("--" + name).trim();
    const night = style.colorScheme === "dark";
    backdrop.set(token("field-light"));
    surfaces[0].uniforms.tint.value.set(token("platform"));
    surfaces[1].uniforms.tint.value.set(token("wall"));
    normal.color.set(token("bar"));
    alarm.color.set(token("alarm-mesh"));
    alarm.emissive.copy(alarm.color);
    alarm.emissiveIntensity = night ? .23 : .095;
    glowMaterial.color.copy(alarm.color).multiplyScalar(night ? .95 : .6);
    guideMaterial.color.set(token("control"));
    penumbra.uniforms.ink.value.set(token("contact"));
    rimMaterial.uniforms.tint.value.set(token("rim"));
    scene.environmentIntensity = night ? .7 : 1;
    renderer.toneMappingExposure = night ? .88 : 1;
  }

  function bakeEnvironment() {
    const room = new RoomEnvironment();
    const generator = new THREE.PMREMGenerator(renderer);
    environment = generator.fromScene(room, .04);
    scene.environment = environment.texture;
    room.dispose();
    generator.dispose();
  }

  function placeCamera() {
    const drift = Math.max(0, time - intro.duration());
    const azimuth = TURN + DRIFT * Math.sin(drift * Math.PI / 6);
    const y = 1.75 + 1.45 * orbit.spread;
    const distance = (14 + 5.7 * orbit.spread) * Math.max(1, .96 / camera.aspect);
    const groundDistance = distance * Math.cos(ELEVATION);
    camera.position.set(
      Math.sin(azimuth) * groundDistance,
      y + distance * Math.sin(ELEVATION),
      Math.cos(azimuth) * groundDistance
    );
    camera.lookAt(0, y, 0);
    camera.updateMatrixWorld();
  }

  function poseBars() {
    orders.forEach(({ mesh, label, cents }) => {
      const height = cents * AXIS_HEIGHT / MAX_CENTS;
      mesh.visible = height > 0;
      mesh.scale.y = Math.max(height, .001);
      mesh.position.y = height / 2;
      label.position.y = height;
    });
    glow.position.copy(bug.mesh.position);
    glow.scale.copy(bug.mesh.scale);
    glow.visible = bug.mesh.visible;
  }

  function screenPoint(label) {
    projected.copy(label.position).project(camera);
    return { x: (1 + projected.x) * width / 2, y: (1 - projected.y) * height / 2 };
  }

  function placeLabels() {
    const gap = 2;
    const inset = 4;
    const lead = 8;
    const anchors = orders.map(({ label }) => screenPoint(label));
    const labelBoxes = ticks.map(tick => {
      const { x, y } = screenPoint(tick);
      return { left: x - tick.labelWidth, right: x, top: y - tick.labelHeight / 2, bottom: y + tick.labelHeight / 2 };
    });
    const occupied = [...labelBoxes, ...anchors.map(({ x, y }) => ({
      left: x - gap, right: x + gap, top: y - gap, bottom: y + gap
    }))];
    orders.forEach(({ badge, leader, rear, labelWidth: w, labelHeight: h }, index) => {
      const { x, y } = anchors[index];
      const centered = x - w / 2;
      const fitX = left => clamp(inset, Math.max(inset, width - w - inset), left);
      let left = fitX(centered);
      let top = clamp(inset, Math.max(inset, height - h - inset), rear ? y - h - lead : y + lead);
      let best = Infinity;
      // Try the nearest rows first, then use the edges of any blockers to find a horizontal nudge.
      for (let step = lead; step < best && step < height; step += 2) {
        for (const above of [rear, !rear]) {
          const row = above ? y - h - step : y + step;
          if (row < inset || row + h > height - inset) continue;
          const blockers = occupied.filter(box => row < box.bottom + gap && row + h > box.top - gap);
          const candidates = [fitX(centered), ...blockers.flatMap(box => [fitX(box.left - w - gap), fitX(box.right + gap)])];
          for (const column of candidates) {
            if (blockers.some(box => column < box.right + gap && column + w > box.left - gap)) continue;
            const dx = clamp(column, column + w, x) - x;
            const score = Math.hypot(dx, step) + .1 * Math.abs(column - centered) + (above === rear ? 0 : gap);
            if (score >= best) continue;
            const dy = above ? -step : step;
            const crossesLabel = labelBoxes.some(box => {
              if (box.top >= Math.max(y, y + dy) || box.bottom <= Math.min(y, y + dy)) return false;
              const start = x + dx * clamp(0, 1, (box.top - y) / dy);
              const end = x + dx * clamp(0, 1, (box.bottom - y) / dy);
              return Math.min(start, end) < box.right && Math.max(start, end) > box.left;
            });
            if (crossesLabel) continue;
            best = score;
            left = column;
            top = row;
          }
        }
      }
      const box = { left, right: left + w, top, bottom: top + h };
      labelBoxes.push(box);
      occupied.push(box);
      badge.style.transform = `translate(${left - x}px, ${top - y}px)`;
      const dx = clamp(left, left + w, x) - x;
      const dy = clamp(top, top + h, y) - y;
      leader.style.transform = `rotate(${Math.atan2(dy, dx)}rad) scaleX(${Math.hypot(dx, dy)})`;
    });
  }

  function placeLens(delta) {
    const parked = bug.mesh.position;
    target.set(parked.x + .53, 1.05, parked.z + 1.05);
    if (!touch && !paused) target.x += Math.sin(time * Math.PI / 6) * .19;
    if (pointer && !touch) {
      const rect = plot.getBoundingClientRect();
      pointerNdc.set(2 * (pointer.x - rect.left) / rect.width - 1, 1 - 2 * (pointer.y - rect.top) / rect.height);
      raycaster.setFromCamera(pointerNdc, camera);
      if (raycaster.ray.intersectPlane(floor, target)) {
        target.x = clamp(-3.45, 3.45, target.x);
        target.z = clamp(-1.1, 3.5, target.z);
        target.y = 1.05;
      }
    }
    lens.position.lerp(target, ready && !paused ? 1 - Math.exp(-delta * 12) : 1);
    lens.quaternion.copy(camera.quaternion);
    lens.scale.setScalar(phone.matches ? .9 : 1);
    movingLens = lens.position.distanceToSquared(target) > .0001;
  }

  function stop() {
    if (ticking) gsap.ticker.remove(frame);
    ticking = false;
    lastTime = undefined;
  }

  function wake() {
    if (disposed || ticking || !inView || document.hidden) return;
    ticking = true;
    gsap.ticker.add(frame);
  }

  function frame(seconds) {
    if (!inView || document.hidden || disposed) { stop(); return; }
    const idle = !paused && ready && time >= intro.duration() && !pointer && !movingLens && !needsSize && !needsTheme;
    if (idle && lastTime !== undefined && seconds - lastTime < 1 / 30) return;
    const delta = lastTime === undefined ? 1 / 60 : Math.min(seconds - lastTime, .1);
    lastTime = seconds;
    const resized = needsSize;
    try {
      if (resized) {
        if (!size()) { stop(); return; }
        needsSize = false;
      }
      if (needsTheme) {
        theme();
        needsTheme = false;
      }
      if (!environment) bakeEnvironment();

      if (paused) time = Math.max(time, intro.duration());
      else if (ready) time += delta;
      if (resized || intro.time() < intro.duration()) {
        intro.time(Math.min(time, intro.duration()));
        poseBars();
      }
      placeCamera();
      placeLens(delta);
      renderer.setRenderTarget(bloomSource);
      renderer.render(glowScene, camera);
      bloom.render(renderer, null, bloomSource);
      renderer.setRenderTarget(null);
      composer.render();
      placeLabels();
      labels.render(scene, camera);
      if (!ready) {
        ready = true;
        scope.classList.add("has-scene");
      }
      if (paused) stop();
    } catch {
      fail();
    }
  }

  function visibility() {
    if (inView && !document.hidden) wake();
    else stop();
  }
  function resize() { needsSize = true; wake(); }
  function recolor() { needsTheme = true; wake(); }
  function point(event) {
    if (paused) return;
    if (event.pointerType === "touch" || !fine.matches) {
      touch = true;
      pointer = undefined;
    } else {
      touch = false;
      pointer = { x: event.clientX, y: event.clientY };
    }
    wake();
  }
  function clearPointer() {
    pointer = undefined;
    if (!paused) wake();
  }
  function togglePlayback() {
    paused = !paused;
    pointer = undefined;
    playback.textContent = paused ? "Play scene" : "Pause scene";
    wake();
  }

  const viewport = new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    visibility();
  });
  const observer = new ResizeObserver(resize);
  function dispose() {
    if (disposed) return;
    disposed = true;
    stop();
    cleanup.abort();
    viewport.disconnect();
    observer.disconnect();
    scope.classList.remove("has-scene");
    labels.domElement.replaceChildren();
    playback.textContent = "Pause scene";
    intro.kill();
    [ground, ...surfaces, slab, guides, shadeFootprint, shadows, penumbra, normal, alarm,
      guideMaterial, lensShape, glass, rimShape, rimMaterial, glowMaterial, bloomSource,
      environment, bloom, combine, output, composer, renderer]
      .forEach(resource => resource?.dispose());
  }

  function fail() {
    dispose();
    onFailure();
  }

  viewport.observe(plot);
  observer.observe(plot);
  for (const { badge } of orders) observer.observe(badge);
  for (const { element } of ticks) observer.observe(element);
  canvas.addEventListener("webglcontextlost", fail, { signal });
  document.addEventListener("visibilitychange", visibility, { signal });
  window.addEventListener("diffscope:theme", recolor, { signal });
  dark.addEventListener("change", recolor, { signal });
  fine.addEventListener("change", clearPointer, { signal });
  phone.addEventListener("change", resize, { signal });
  window.addEventListener("resize", resize, { signal });
  playback.addEventListener("click", togglePlayback, { signal });
  plot.addEventListener("pointermove", point, { signal, passive: true });
  plot.addEventListener("pointerdown", point, { signal, passive: true });
  plot.addEventListener("pointerleave", clearPointer, { signal });
  return dispose;
}
