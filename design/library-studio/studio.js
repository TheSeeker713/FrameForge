import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { Reflector } from "three/addons/objects/Reflector.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const CLIPS = [
  { id: "interview", title: "Interview clip", meta: "youtube · 1080p · 12:04", hue: 28 },
  { id: "lecture", title: "Lecture excerpt", meta: "vimeo · 720p · 48:11", hue: 200 },
  { id: "news", title: "News segment", meta: "youtube · 1080p · 3:22", hue: 12 },
  { id: "demo", title: "Demo recording", meta: "local · 1440p · 8:40", hue: 150 },
  { id: "field", title: "Field note", meta: "local · 1080p · 6:18", hue: 92 },
  { id: "recital", title: "Recital", meta: "vimeo · 1080p · 21:05", hue: 262 },
  { id: "trailer", title: "Trailer cut", meta: "youtube · 4K · 2:11", hue: 340 },
];

const GROUPS = [
  {
    key: "shelf",
    label: "Shelf",
    options: [
      ["coverflow", "Cover flow"],
      ["rail", "Flat rail"],
      ["orbit", "Orbit"],
      ["manual", "Manual order"],
    ],
  },
  {
    key: "material",
    label: "Card",
    options: [
      ["glass", "Optical glass"],
      ["metal", "Graphite"],
      ["paper", "Matte paper"],
    ],
  },
  {
    key: "pointer",
    label: "Pointer",
    options: [
      ["tilt", "Specular tilt"],
      ["magnetic", "Magnetic pull"],
      ["still", "Still"],
    ],
  },
  {
    key: "player",
    label: "Open",
    options: [
      ["expand", "Card comes forward"],
      ["theater", "Theater frame"],
    ],
  },
];

const LAYERS = [
  ["anamorphic", "Anamorphic streak"],
  ["reflection", "Floor mirror"],
  ["grain", "Film grain"],
  ["vignette", "Vignette"],
];

const PRESETS = {
  screening: {
    label: "Screening room",
    shelf: "coverflow",
    material: "glass",
    pointer: "tilt",
    player: "expand",
    anamorphic: true,
    reflection: true,
    grain: true,
    vignette: true,
  },
  archive: {
    label: "Archive rail",
    shelf: "rail",
    material: "paper",
    pointer: "still",
    player: "theater",
    anamorphic: false,
    reflection: false,
    grain: true,
    vignette: true,
  },
  graphite: {
    label: "Graphite orbit",
    shelf: "orbit",
    material: "metal",
    pointer: "magnetic",
    player: "expand",
    anamorphic: true,
    reflection: true,
    grain: false,
    vignette: true,
  },
};

const state = {
  status: "in progress",
  updated: null,
  notes: "",
  fps: null,
  backend: "WebGL2",
  choices: {},
  order: CLIPS.map((clip) => clip.id),
  kept: [],
  discarded: [],
  events: [],
};

const choice = {
  shelf: "coverflow",
  material: "glass",
  pointer: "tilt",
  player: "expand",
  anamorphic: true,
  reflection: true,
  grain: true,
  vignette: true,
};

const canvas = document.getElementById("stage");
const groupsEl = document.getElementById("groups");
const notesEl = document.getElementById("notes");
const saveEl = document.getElementById("save");
const fpsEl = document.getElementById("fps");
const banner = document.getElementById("banner");
const playerEl = document.getElementById("player");
const playerTitle = document.getElementById("playerTitle");
const playerSub = document.getElementById("playerSub");
const playerStill = playerEl.querySelector(".still");

let focus = 2;
let focusTo = 2;
let open = false;
let openAmt = 0;
let sweep = 1;
let pointerX = 0;
let pointerY = 0;
let scrubbing = false;
let scrubLast = 0;
let dragId = null;
let dragX = 0;
let saveTimer = 0;
let fpsNoted = false;
let frames = 0;
let fpsStamp = performance.now();

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  alpha: false,
  powerPreference: "high-performance",
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(0x0c0b0a, 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
state.backend = `WebGL2 · Three r0.186.1 · ${renderer.capabilities.isWebGL2 ? "WebGL2" : "WebGL1"}`;

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x0c0b0a, 8, 16);
const camera = new THREE.PerspectiveCamera(30, window.innerWidth / window.innerHeight, 0.1, 40);
camera.position.set(0, 1.05, 6.6);
camera.lookAt(0, 0.72, 0);

const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.9;

scene.add(new THREE.AmbientLight(0xfff4e4, 0.25));
const key = new THREE.SpotLight(0xffe2b0, 3.2, 18, 0.7, 0.8, 1);
key.position.set(3.2, 5.5, 4);
scene.add(key);
const rim = new THREE.DirectionalLight(0x9eb6ff, 1.4);
rim.position.set(-4, 2.2, -2);
scene.add(rim);
const sweepLight = new THREE.PointLight(0xfff1cc, 0, 6);
sweepLight.position.set(0, 1.4, 2.2);
scene.add(sweepLight);

const floor = new Reflector(new THREE.CircleGeometry(8, 48), {
  clipBias: 0.003,
  textureWidth: 512,
  textureHeight: 512,
  color: 0x8899aa,
});
floor.rotation.x = -Math.PI / 2;
floor.position.y = -0.02;
scene.add(floor);

const rig = new THREE.Group();
scene.add(rig);

function makeStill(clip) {
  const board = document.createElement("canvas");
  board.width = 640;
  board.height = 360;
  const g = board.getContext("2d");
  const wash = g.createLinearGradient(0, 0, 640, 360);
  wash.addColorStop(0, `hsl(${clip.hue} 42% 46%)`);
  wash.addColorStop(0.45, `hsl(${(clip.hue + 18) % 360} 36% 28%)`);
  wash.addColorStop(1, `hsl(${clip.hue} 30% 12%)`);
  g.fillStyle = wash;
  g.fillRect(0, 0, 640, 360);
  g.fillStyle = "rgba(244,239,230,0.9)";
  g.beginPath();
  g.arc(84, 168, 28, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "#1a140c";
  g.beginPath();
  g.moveTo(76, 154);
  g.lineTo(100, 168);
  g.lineTo(76, 182);
  g.closePath();
  g.fill();
  g.fillStyle = "#f4efe6";
  g.font = "500 18px Outfit, sans-serif";
  g.fillText(clip.meta, 40, 64);
  g.font = "560 28px Fraunces, serif";
  g.fillText(clip.title, 40, 250);
  const tex = new THREE.CanvasTexture(board);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

const cards = CLIPS.map((clip, index) => {
  const tex = makeStill(clip);
  const bodyMat = new THREE.MeshPhysicalMaterial({
    color: "#1c1916",
    roughness: 0.35,
    metalness: 0.15,
    clearcoat: 1,
    clearcoatRoughness: 0.2,
  });
  const screenMat = new THREE.MeshBasicMaterial({ map: tex });
  const body = new THREE.Mesh(new RoundedBoxGeometry(1.46, 0.84, 0.06, 4, 0.05), bodyMat);
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.28, 0.72), screenMat);
  screen.position.z = 0.045;
  const group = new THREE.Group();
  group.add(body);
  group.add(screen);
  group.userData.index = index;
  group.userData.id = clip.id;
  rig.add(group);
  return { clip, group, body, bodyMat, screenMat, tex };
});

function applyBodyMaterial() {
  for (const card of cards) {
    const mat = card.bodyMat;
    mat.transmission = 0;
    mat.thickness = 0;
    if (choice.material === "metal") {
      mat.color.set("#3a3632");
      mat.metalness = 1;
      mat.roughness = 0.28;
      mat.clearcoat = 1;
      mat.clearcoatRoughness = 0.12;
      mat.iridescence = 0;
      mat.sheen = 0;
    } else if (choice.material === "paper") {
      mat.color.set("#efe6d6");
      mat.metalness = 0;
      mat.roughness = 0.95;
      mat.clearcoat = 0;
      mat.sheen = 1;
      mat.sheenColor = new THREE.Color("#fff6e8");
      mat.sheenRoughness = 0.6;
      mat.iridescence = 0;
    } else {
      mat.color.set("#d5dbe6");
      mat.metalness = 0;
      mat.roughness = 0.06;
      mat.clearcoat = 1;
      mat.transmission = 0.86;
      mat.thickness = 0.45;
      mat.ior = 1.45;
      mat.iridescence = 1;
      mat.iridescenceIOR = 1.3;
      if ("dispersion" in mat) mat.dispersion = 0.12;
    }
  }
}

const AnamorphicShader = {
  uniforms: {
    tDiffuse: { value: null },
    strength: { value: 1 },
    grain: { value: 0.045 },
    vignette: { value: 0.85 },
    time: { value: 0 },
  },
  vertexShader: `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    uniform sampler2D tDiffuse;
    uniform float strength;
    uniform float grain;
    uniform float vignette;
    uniform float time;
    varying vec2 vUv;
    float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
    void main() {
      vec4 base = texture2D(tDiffuse, vUv);
      vec3 glow = vec3(0.0);
      for (int i = 0; i < 17; i++) {
        float fi = float(i) - 8.0;
        vec2 offset = vec2(fi * 0.0048, 0.0);
        vec3 sampleColor = texture2D(tDiffuse, vUv + offset).rgb;
        float weight = exp(-abs(fi) * 0.26);
        float hot = smoothstep(0.88, 1.2, luma(sampleColor));
        glow += sampleColor * hot * weight;
      }
      vec3 color = base.rgb + glow * strength * vec3(0.72, 0.84, 1.0);
      float n = fract(sin(dot(vUv * vec2(1920.0, 1080.0) + time, vec2(12.9898, 78.233))) * 43758.5453);
      color += (n - 0.5) * grain;
      float edge = smoothstep(0.92, 0.28, length(vUv - 0.5));
      color *= mix(1.0, edge, vignette);
      gl_FragColor = vec4(color, 1.0);
    }
  `,
};

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const grade = new ShaderPass(AnamorphicShader);
composer.addPass(grade);
composer.addPass(new OutputPass());

const raycaster = new THREE.Raycaster();
const ndc = new THREE.Vector2();

function orderedCards() {
  const rank = new Map(state.order.map((id, index) => [id, index]));
  return [...cards].sort((a, b) => rank.get(a.clip.id) - rank.get(b.clip.id));
}

function layout(dtFocus) {
  const list = orderedCards();
  const n = list.length;
  list.forEach((card, index) => {
    const rel = index - dtFocus;
    let x = 0;
    let z = 0;
    let rot = 0;
    let scale = 1;
    if (choice.shelf === "orbit") {
      const ang = rel * ((Math.PI * 2) / n);
      x = Math.sin(ang) * 2.7;
      z = Math.cos(ang) * 1.6 - 1.15;
      rot = ang * 0.65;
      scale = 0.92;
    } else if (choice.shelf === "rail" || choice.shelf === "manual") {
      x = (index - (n - 1) / 2) * 1.62;
      rot = rel * -0.05;
      scale = index === Math.round(dtFocus) ? 1.04 : 0.96;
    } else {
      x = rel * 1.18;
      z = -Math.abs(rel) * 0.78;
      rot = THREE.MathUtils.clamp(rel * -0.46, -0.9, 0.9);
      scale = 1.14 - Math.min(Math.abs(rel), 2.2) * 0.1;
    }
    const front = Math.abs(rel) < 0.5;
    if (front && choice.player === "expand") {
      z += openAmt * 1.35;
      scale += openAmt * 0.7;
      rot *= 1 - openAmt;
    }
    card.group.position.x += (x - card.group.position.x) * 0.18;
    card.group.position.y = 0.78;
    card.group.position.z += (z - card.group.position.z) * 0.18;
    card.group.rotation.y += (rot - card.group.rotation.y) * 0.18;
    const s = card.group.scale.x + (scale - card.group.scale.x) * 0.18;
    card.group.scale.setScalar(s);
    const dim = open && !front ? 0.28 : 1;
    card.bodyMat.transparent = true;
    card.screenMat.transparent = true;
    card.bodyMat.opacity += (dim - card.bodyMat.opacity) * 0.15;
    card.screenMat.opacity += (dim - card.screenMat.opacity) * 0.15;
    card.group.userData.index = index;
  });
}

function hitCard(event) {
  const rect = canvas.getBoundingClientRect();
  ndc.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  ndc.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(ndc, camera);
  const hits = raycaster.intersectObjects(rig.children, true);
  if (!hits.length) return null;
  let node = hits[0].object;
  while (node && node.parent !== rig) node = node.parent;
  return node;
}

function focusedClip() {
  const list = orderedCards();
  const index = THREE.MathUtils.clamp(Math.round(focus), 0, list.length - 1);
  return list[index];
}

function showPlayer(card) {
  open = true;
  sweep = 0;
  playerTitle.textContent = card.clip.title;
  playerSub.textContent = `${card.clip.meta} · path stays on disk · sample still, not your file`;
  playerStill.src = card.tex.image.toDataURL("image/jpeg", 0.86);
  playerStill.alt = card.clip.title;
  playerEl.classList.add("open");
  playerEl.classList.toggle("theater", choice.player === "theater");
  playerEl.classList.toggle("caption", choice.player === "expand");
  record("player-open", `Opened ${card.clip.title} with ${labelOf("player", choice.player)}`);
}

function hidePlayer() {
  open = false;
  playerEl.classList.remove("open");
}

canvas.addEventListener("pointerdown", (event) => {
  const node = hitCard(event);
  if (choice.shelf === "manual" && node) {
    dragId = node.userData.id;
    dragX = event.clientX;
    canvas.setPointerCapture(event.pointerId);
    return;
  }
  scrubbing = true;
  scrubLast = event.clientX;
  canvas.setPointerCapture(event.pointerId);
});

canvas.addEventListener("pointermove", (event) => {
  const rect = canvas.getBoundingClientRect();
  pointerX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointerY = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  if (dragId) {
    const dx = event.clientX - dragX;
    if (Math.abs(dx) > 56) {
      const ids = [...state.order];
      const index = ids.indexOf(dragId);
      const next = index + (dx > 0 ? 1 : -1);
      if (index >= 0 && next >= 0 && next < ids.length) {
        const hold = ids[index];
        ids[index] = ids[next];
        ids[next] = hold;
        state.order = ids;
        dragX = event.clientX;
        focusTo = next;
        record("order", `Manual order: ${orderedCards().map((card) => card.clip.title).join(", ")}`);
      }
    }
    return;
  }
  if (!scrubbing || choice.shelf === "manual") return;
  const dx = event.clientX - scrubLast;
  if (Math.abs(dx) > 36) {
    focusTo = THREE.MathUtils.clamp(focusTo + (dx > 0 ? -1 : 1), 0, CLIPS.length - 1);
    scrubLast = event.clientX;
    if (open) hidePlayer();
  }
});

canvas.addEventListener("pointerup", (event) => {
  if (dragId) {
    dragId = null;
    return;
  }
  const moved = Math.abs(event.clientX - scrubLast) > 8 && scrubbing;
  scrubbing = false;
  if (moved && choice.shelf !== "manual") return;
  const node = hitCard(event);
  if (!node) {
    hidePlayer();
    return;
  }
  const index = node.userData.index;
  if (Math.round(focusTo) !== index) {
    focusTo = index;
    hidePlayer();
    return;
  }
  const card = orderedCards()[index];
  if (open) hidePlayer();
  else showPlayer(card);
});

canvas.addEventListener(
  "wheel",
  (event) => {
    event.preventDefault();
    focusTo = THREE.MathUtils.clamp(focusTo + Math.sign(event.deltaY), 0, CLIPS.length - 1);
    if (open) hidePlayer();
  },
  { passive: false },
);

document.getElementById("closePlayer").addEventListener("click", hidePlayer);

function labelOf(groupKey, id) {
  const group = GROUPS.find((item) => item.key === groupKey);
  const found = group && group.options.find((option) => option[0] === id);
  if (found) return found[1];
  const layer = LAYERS.find((item) => item[0] === id);
  if (layer) return layer[1];
  return String(id);
}

function snapshotChoices() {
  const shot = {};
  for (const group of GROUPS) {
    shot[group.key] = { group: group.label, id: choice[group.key], label: labelOf(group.key, choice[group.key]) };
  }
  for (const [key, label] of LAYERS) {
    shot[key] = { group: label, id: choice[key] ? "on" : "off", label: choice[key] ? "On" : "Off" };
  }
  return shot;
}

function record(key, label) {
  state.choices = snapshotChoices();
  state.updated = new Date().toISOString();
  state.events.push({ t: state.updated, key, label });
  if (state.events.length > 400) state.events.splice(0, state.events.length - 400);
  scheduleSave();
}

function scheduleSave() {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(save, 200);
}

async function save() {
  state.choices = snapshotChoices();
  state.updated = new Date().toISOString();
  const payload = {
    ...state,
    order: orderedCards().map((card) => card.clip.title),
  };
  try {
    const response = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(String(response.status));
    saveEl.innerHTML = `<strong>Saved</strong> ${new Date().toLocaleTimeString()}`;
    banner.style.display = "none";
  } catch (error) {
    saveEl.textContent = "Not recording";
    banner.style.display = "block";
    banner.textContent = "Open http://127.0.0.1:8765/ so answers write to docs/LIBRARY_DESIGN_FEEDBACK.md. A file opened from disk cannot save.";
  }
}

function paintControls() {
  groupsEl.replaceChildren();
  const presets = document.createElement("div");
  presets.className = "group";
  presets.innerHTML = "<span>Start from</span>";
  for (const [id, preset] of Object.entries(PRESETS)) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = preset.label;
    button.addEventListener("click", () => {
      Object.assign(choice, preset);
      applyBodyMaterial();
      paintControls();
      record("preset", `Preset ${preset.label}`);
    });
    presets.appendChild(button);
  }
  groupsEl.appendChild(presets);
  for (const group of GROUPS) {
    const wrap = document.createElement("div");
    wrap.className = "group";
    const title = document.createElement("span");
    title.textContent = group.label;
    wrap.appendChild(title);
    for (const [id, label] of group.options) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.setAttribute("aria-pressed", String(choice[group.key] === id));
      button.addEventListener("click", () => {
        choice[group.key] = id;
        if (group.key === "player" && open) {
          playerEl.classList.toggle("theater", id === "theater");
          playerEl.classList.toggle("caption", id === "expand");
        }
        if (group.key === "material") applyBodyMaterial();
        paintControls();
        record(group.key, `${group.label}: ${label}`);
      });
      wrap.appendChild(button);
    }
    groupsEl.appendChild(wrap);
  }
  const layers = document.createElement("div");
  layers.className = "group";
  layers.innerHTML = "<span>Layers</span>";
  for (const [key, label] of LAYERS) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.setAttribute("aria-pressed", String(Boolean(choice[key])));
    button.addEventListener("click", () => {
      choice[key] = !choice[key];
      paintControls();
      record(key, `${label}: ${choice[key] ? "on" : "off"}`);
    });
    layers.appendChild(button);
  }
  groupsEl.appendChild(layers);
}

notesEl.addEventListener("input", () => {
  state.notes = notesEl.value;
  record("notes", "Notes updated");
});

document.getElementById("keep").addEventListener("click", () => {
  state.kept.push({ t: new Date().toISOString(), choices: snapshotChoices() });
  record("keep", "Kept the current look");
});
document.getElementById("discard").addEventListener("click", () => {
  state.discarded.push({ t: new Date().toISOString(), choices: snapshotChoices() });
  record("discard", "Discarded the current look");
});
document.getElementById("done").addEventListener("click", () => {
  state.status = state.status === "complete" ? "in progress" : "complete";
  document.getElementById("done").textContent = state.status === "complete" ? "Reopen feedback" : "Mark feedback complete";
  record("status", state.status === "complete" ? "Feedback marked complete" : "Feedback reopened");
});

function resize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
}
window.addEventListener("resize", resize);

function animate(now) {
  requestAnimationFrame(animate);
  focus += (focusTo - focus) * 0.12;
  openAmt += ((open ? 1 : 0) - openAmt) * 0.1;
  if (sweep < 1) sweep += 0.012;
  sweepLight.intensity = open ? (1 - Math.abs(sweep * 2 - 1)) * 6 : 0;
  sweepLight.position.x = -2.4 + sweep * 4.8;
  const tilt = choice.pointer === "still" ? 0 : choice.pointer === "magnetic" ? 0.05 : 0.14;
  const targetY = pointerX * tilt;
  const targetX = pointerY * tilt * -0.45;
  rig.rotation.y += (targetY - rig.rotation.y) * 0.08;
  rig.rotation.x += (targetX - rig.rotation.x) * 0.08;
  floor.visible = choice.reflection;
  grade.uniforms.strength.value = choice.anamorphic ? 0.16 : 0;
  grade.uniforms.grain.value = choice.grain ? 0.05 : 0;
  grade.uniforms.vignette.value = choice.vignette ? 0.9 : 0;
  grade.uniforms.time.value = now * 0.001;
  layout(focus);
  if (choice.pointer === "magnetic") {
    const front = focusedClip();
    if (front) front.group.position.x += pointerX * 0.18;
  }
  composer.render();
  frames += 1;
  if (now - fpsStamp > 1000) {
    state.fps = Math.round((frames * 1000) / (now - fpsStamp));
    frames = 0;
    fpsStamp = now;
    fpsEl.textContent = `${state.backend} · ${state.fps} fps`;
    if (!fpsNoted && state.fps >= 20) {
      fpsNoted = true;
      scheduleSave();
    }
  }
}

applyBodyMaterial();
paintControls();
document.fonts.ready.then(() => {
  for (const card of cards) {
    const next = makeStill(card.clip);
    card.screenMat.map = next;
    card.screenMat.needsUpdate = true;
    card.tex.dispose();
    card.tex = next;
  }
});
record("open", "Studio opened on the screening-room preset");
requestAnimationFrame(animate);
