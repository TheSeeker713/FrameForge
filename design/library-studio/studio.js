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

const EMBED = new URLSearchParams(location.search).get("embed") === "1";
const LOCKED = {
  shelf: "coverflow",
  material: "glass",
  pointer: "magnetic",
  player: "expand",
  anamorphic: true,
  reflection: true,
  grain: false,
  vignette: true,
};
if (EMBED) {
  Object.assign(choice, LOCKED);
  document.documentElement.classList.add("embed");
  document.body.classList.add("embed");
}

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
scene.fog = new THREE.Fog(0x100e0c, 9, 22);
const camera = new THREE.PerspectiveCamera(32, window.innerWidth / window.innerHeight, 0.1, 40);
camera.position.set(0, 1.22, 7.4);
camera.lookAt(0, 0.95, 0);

const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.35;

scene.add(new THREE.AmbientLight(0xfff1e0, 0.22));
const key = new THREE.SpotLight(0xffe2b0, 6, 20, 0.55, 0.45, 1);
key.position.set(2.4, 4.8, 3.2);
scene.add(key);
const rim = new THREE.DirectionalLight(0x8ea4ff, 0.7);
rim.position.set(-4, 2.4, -1);
scene.add(rim);
const sweepLight = new THREE.PointLight(0xfff1cc, 0, 6);
sweepLight.position.set(0, 1.5, 2.2);
scene.add(sweepLight);

function canvasTex(canvas, color) {
  const tex = new THREE.CanvasTexture(canvas);
  if (color) tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  return tex;
}

function paintWall() {
  const board = document.createElement("canvas");
  board.width = 1024;
  board.height = 512;
  const g = board.getContext("2d");
  g.fillStyle = "#140e0c";
  g.fillRect(0, 0, 1024, 512);
  for (let x = 0; x < 1024; x += 1) {
    const fold = Math.sin(x * 0.045) * 0.5 + Math.sin(x * 0.11) * 0.25;
    const light = 42 + fold * 36;
    g.fillStyle = `rgb(${light + 28}, ${light * 0.42}, ${light * 0.32})`;
    g.fillRect(x, 0, 1, 512);
  }
  for (let i = 0; i < 6000; i += 1) {
    g.fillStyle = `rgba(255, 220, 180, ${Math.random() * 0.05})`;
    g.fillRect(Math.random() * 1024, Math.random() * 512, 1, 2 + Math.random() * 8);
  }
  const pool = g.createRadialGradient(512, 280, 30, 512, 300, 420);
  pool.addColorStop(0, "rgba(180, 110, 60, 0.28)");
  pool.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = pool;
  g.fillRect(0, 0, 1024, 512);
  g.fillStyle = "rgba(0,0,0,0.45)";
  g.fillRect(0, 0, 1024, 36);
  return canvasTex(board, true);
}

function paintWood() {
  const board = document.createElement("canvas");
  board.width = 512;
  board.height = 512;
  const g = board.getContext("2d");
  for (let y = 0; y < 8; y += 1) {
    const tone = 42 + (y % 3) * 10;
    g.fillStyle = `rgb(${tone + 28}, ${tone + 12}, ${tone})`;
    g.fillRect(0, y * 64, 512, 64);
    g.strokeStyle = "rgba(0,0,0,0.35)";
    g.beginPath();
    g.moveTo(0, y * 64);
    g.lineTo(512, y * 64);
    g.stroke();
    for (let i = 0; i < 18; i += 1) {
      g.strokeStyle = `rgba(90, 60, 30, ${0.15 + Math.random() * 0.25})`;
      g.beginPath();
      const yy = y * 64 + 8 + Math.random() * 48;
      g.moveTo(0, yy);
      g.bezierCurveTo(160, yy + 4, 320, yy - 4, 512, yy + 2);
      g.stroke();
    }
  }
  return canvasTex(board, true);
}

function paintBrush() {
  const board = document.createElement("canvas");
  board.width = 256;
  board.height = 256;
  const g = board.getContext("2d");
  const img = g.createImageData(256, 256);
  for (let y = 0; y < 256; y += 1) {
    const streak = 90 + (y % 3) * 18;
    for (let x = 0; x < 256; x += 1) {
      const n = streak + Math.sin(x * 0.7 + y) * 20 + Math.random() * 12;
      const i = (y * 256 + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = n;
      img.data[i + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  const tex = canvasTex(board, false);
  tex.repeat.set(3, 3);
  return tex;
}

function paintFiber() {
  const board = document.createElement("canvas");
  board.width = 256;
  board.height = 256;
  const g = board.getContext("2d");
  g.fillStyle = "#c8b496";
  g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2500; i += 1) {
    g.strokeStyle = `rgba(90, 60, 30, ${0.15 + Math.random() * 0.35})`;
    g.beginPath();
    const x = Math.random() * 256;
    const y = Math.random() * 256;
    g.moveTo(x, y);
    g.lineTo(x + 8 + Math.random() * 18, y + (Math.random() - 0.5) * 4);
    g.stroke();
  }
  const tex = canvasTex(board, false);
  tex.repeat.set(2, 2);
  return tex;
}

const wall = new THREE.Mesh(
  new THREE.PlaneGeometry(18, 9),
  new THREE.MeshStandardMaterial({ map: paintWall(), roughness: 0.96, metalness: 0 }),
);
wall.position.set(0, 2.1, -4.2);
scene.add(wall);

const wood = new THREE.Mesh(
  new THREE.CircleGeometry(8, 64),
  new THREE.MeshStandardMaterial({ map: paintWood(), roughness: 0.62, metalness: 0.04 }),
);
wood.rotation.x = -Math.PI / 2;
wood.position.y = -0.04;
scene.add(wood);

for (const [x, y, z, color] of [
  [-3.6, 2.6, -2.6, 0xffb06a],
  [3.5, 2.3, -2.4, 0xffd8a8],
]) {
  const bulb = new THREE.Mesh(
    new THREE.SphereGeometry(0.07, 16, 12),
    new THREE.MeshBasicMaterial({ color }),
  );
  bulb.position.set(x, y, z);
  scene.add(bulb);
  const glow = new THREE.PointLight(color, 4, 7, 2);
  glow.position.set(x, y, z);
  scene.add(glow);
}

const floor = new Reflector(new THREE.CircleGeometry(5.2, 48), {
  clipBias: 0.003,
  textureWidth: 512,
  textureHeight: 512,
  color: 0x3a2e24,
});
floor.rotation.x = -Math.PI / 2;
floor.position.y = -0.02;
scene.add(floor);

const brushMap = paintBrush();
const fiberMap = paintFiber();

const rig = new THREE.Group();
scene.add(rig);

function paintScene(g, id, w, h) {
  const sky = g.createLinearGradient(0, 0, 0, h);
  if (id === "lecture") {
    sky.addColorStop(0, "#1c2430");
    sky.addColorStop(1, "#0c1016");
    g.fillStyle = sky;
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#d7e4f2";
    g.beginPath();
    g.arc(720, 110, 64, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "#141a22";
    for (let row = 0; row < 6; row += 1) g.fillRect(70, 240 + row * 40, w - 140, 14);
  } else if (id === "news") {
    sky.addColorStop(0, "#102033");
    sky.addColorStop(1, "#070b12");
    g.fillStyle = sky;
    g.fillRect(0, 0, w, h);
    for (let i = 0; i < 26; i += 1) {
      g.fillStyle = `rgba(255, 214, 150, ${0.18 + (i % 4) * 0.08})`;
      g.beginPath();
      g.arc(70 + ((i * 97) % w), 36 + ((i * 47) % 240), 7 + (i % 4) * 5, 0, Math.PI * 2);
      g.fill();
    }
    g.fillStyle = "#1b2836";
    g.fillRect(0, 330, w, 210);
    g.fillStyle = "#c4554a";
    g.fillRect(48, 292, 200, 16);
  } else if (id === "demo") {
    sky.addColorStop(0, "#f3eadf");
    sky.addColorStop(1, "#8d735c");
    g.fillStyle = sky;
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#2a241e";
    g.beginPath();
    g.ellipse(480, 360, 210, 36, 0, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "#f7f1e8";
    g.fillRect(390, 170, 180, 160);
    g.fillStyle = "#1a140c";
    g.fillRect(418, 198, 124, 72);
  } else if (id === "field") {
    sky.addColorStop(0, "#f2c7a0");
    sky.addColorStop(0.42, "#d97848");
    sky.addColorStop(1, "#234232");
    g.fillStyle = sky;
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#f6e2b8";
    g.beginPath();
    g.arc(760, 140, 46, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "#1e3a28";
    g.beginPath();
    g.moveTo(0, 310);
    g.lineTo(260, 240);
    g.lineTo(520, 330);
    g.lineTo(w, 210);
    g.lineTo(w, h);
    g.lineTo(0, h);
    g.fill();
  } else if (id === "recital") {
    sky.addColorStop(0, "#3a1020");
    sky.addColorStop(1, "#14080e");
    g.fillStyle = sky;
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#6e2438";
    g.fillRect(0, 0, 130, h);
    g.fillRect(w - 130, 0, 130, h);
    g.fillStyle = "rgba(255, 214, 160, 0.9)";
    g.beginPath();
    g.moveTo(470, 0);
    g.lineTo(560, 0);
    g.lineTo(515, 400);
    g.fill();
    g.fillStyle = "#1a120e";
    g.fillRect(280, 350, 400, 190);
  } else if (id === "trailer") {
    sky.addColorStop(0, "#07070c");
    sky.addColorStop(1, "#101820");
    g.fillStyle = sky;
    g.fillRect(0, 0, w, h);
    g.strokeStyle = "#ff4d6a";
    g.lineWidth = 10;
    g.beginPath();
    g.moveTo(60, 400);
    g.bezierCurveTo(220, 70, 500, 450, 900, 130);
    g.stroke();
    g.strokeStyle = "#7ecbff";
    g.lineWidth = 4;
    g.beginPath();
    g.moveTo(30, 190);
    g.lineTo(930, 250);
    g.stroke();
  } else {
    sky.addColorStop(0, "#3a2a22");
    sky.addColorStop(0.5, "#8a5a3a");
    sky.addColorStop(1, "#1c1410");
    g.fillStyle = sky;
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#f0c48a";
    g.fillRect(640, 30, 250, 360);
    g.fillStyle = "rgba(255, 220, 170, 0.28)";
    g.fillRect(662, 50, 88, 320);
    g.fillStyle = "#1a120e";
    g.beginPath();
    g.ellipse(400, 220, 62, 78, 0, 0, Math.PI * 2);
    g.fill();
    g.fillRect(330, 290, 150, 250);
  }
}

function makeBack(clip) {
  const board = document.createElement("canvas");
  board.width = 640;
  board.height = 360;
  const g = board.getContext("2d");
  g.fillStyle = "#2a2118";
  g.fillRect(0, 0, 640, 360);
  for (let i = 0; i < 1800; i += 1) {
    g.strokeStyle = `rgba(80, 56, 32, ${0.2 + Math.random() * 0.35})`;
    g.beginPath();
    const x = Math.random() * 640;
    const y = Math.random() * 360;
    g.moveTo(x, y);
    g.lineTo(x + 10 + Math.random() * 16, y + (Math.random() - 0.5) * 3);
    g.stroke();
  }
  g.strokeStyle = "rgba(231, 194, 122, 0.7)";
  g.lineWidth = 3;
  g.strokeRect(28, 28, 584, 304);
  g.fillStyle = "#f4efe6";
  g.font = "560 36px Fraunces, serif";
  g.fillText(clip.title, 52, 180);
  g.fillStyle = "rgba(244,239,230,0.7)";
  g.font = "500 18px Outfit, sans-serif";
  g.fillText(clip.meta, 52, 214);
  const tex = new THREE.CanvasTexture(board);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeStill(clip) {
  const w = 960;
  const h = 540;
  const board = document.createElement("canvas");
  board.width = w;
  board.height = h;
  const g = board.getContext("2d");
  paintScene(g, clip.id, w, h);
  const grain = g.getImageData(0, 0, w, h);
  for (let i = 0; i < grain.data.length; i += 16) {
    const n = (Math.random() - 0.5) * 22;
    grain.data[i] = Math.max(0, Math.min(255, grain.data[i] + n));
    grain.data[i + 1] = Math.max(0, Math.min(255, grain.data[i + 1] + n));
    grain.data[i + 2] = Math.max(0, Math.min(255, grain.data[i + 2] + n));
  }
  g.putImageData(grain, 0, 0);
  g.fillStyle = "rgba(8, 6, 4, 0.66)";
  g.fillRect(0, h - 100, w, 100);
  g.fillStyle = "rgba(244, 239, 230, 0.78)";
  g.font = "500 20px Outfit, sans-serif";
  g.fillText(clip.meta, 36, h - 64);
  g.fillStyle = "#f4efe6";
  g.font = "560 42px Fraunces, serif";
  g.fillText(clip.title, 36, h - 26);
  g.fillStyle = "rgba(244, 239, 230, 0.94)";
  g.beginPath();
  g.arc(w / 2, 220, 34, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "#1a140c";
  g.beginPath();
  g.moveTo(w / 2 - 8, 204);
  g.lineTo(w / 2 + 16, 220);
  g.lineTo(w / 2 - 8, 236);
  g.closePath();
  g.fill();
  const tex = new THREE.CanvasTexture(board);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  if (clip.thumb) {
    const img = new Image();
    img.onload = () => {
      g.drawImage(img, 0, 0, w, h);
      g.fillStyle = "rgba(8, 6, 4, 0.62)";
      g.fillRect(0, h - 96, w, 96);
      g.fillStyle = "#f4efe6";
      g.font = "560 40px Fraunces, serif";
      g.fillText(clip.title || "", 36, h - 32);
      tex.needsUpdate = true;
    };
    img.src = clip.thumb;
  }
  return tex;
}

function buildCard(clip, index) {
  const tex = makeStill(clip);
  const bodyMat = new THREE.MeshPhysicalMaterial({
    color: "#1c1916",
    roughness: 0.35,
    metalness: 0.15,
    clearcoat: 1,
    clearcoatRoughness: 0.2,
  });
  const screenMat = new THREE.MeshBasicMaterial({ map: tex });
  const body = new THREE.Mesh(new RoundedBoxGeometry(1.78, 1.04, 0.07, 5, 0.045), bodyMat);
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.62, 0.91), screenMat);
  screen.position.z = 0.05;
  const matte = new THREE.Mesh(
    new THREE.PlaneGeometry(1.68, 0.97),
    new THREE.MeshBasicMaterial({ color: "#1a140e" }),
  );
  matte.position.z = 0.04;
  const backMat = new THREE.MeshBasicMaterial({ map: makeBack(clip) });
  const back = new THREE.Mesh(new THREE.PlaneGeometry(1.62, 0.91), backMat);
  back.position.z = -0.05;
  back.rotation.y = Math.PI;
  back.userData.role = "back";
  const group = new THREE.Group();
  group.add(body);
  group.add(matte);
  group.add(screen);
  group.add(back);
  group.userData.index = index;
  group.userData.id = clip.id;
  rig.add(group);
  return { clip, group, body, bodyMat, screenMat, tex };
}

let cards = [];

function mountCards(list) {
  for (const card of cards) {
    rig.remove(card.group);
    card.tex.dispose();
    card.bodyMat.dispose();
    card.screenMat.dispose();
    const back = card.group.children.find((child) => child.userData.role === "back");
    if (back && back.material) {
      if (back.material.map) back.material.map.dispose();
      back.material.dispose();
    }
  }
  cards = list.map((clip, index) => buildCard(clip, index));
  state.order = list.map((clip) => clip.id);
  focus = 0;
  focusTo = 0;
  open = false;
  applyBodyMaterial();
  const empty = document.getElementById("emptyShelf");
  const none = list.length === 0;
  document.body.classList.toggle("empty", none);
  document.documentElement.classList.toggle("empty", none);
  if (empty) empty.hidden = !none;
}

function applyBodyMaterial() {
  for (const card of cards) {
    const mat = card.bodyMat;
    mat.transmission = 0;
    mat.thickness = 0;
    mat.roughnessMap = null;
    mat.iridescence = 0;
    mat.sheen = 0;
    if (choice.material === "metal") {
      mat.color.set("#8d8478");
      mat.metalness = 1;
      mat.roughness = 0.42;
      mat.roughnessMap = brushMap;
      mat.clearcoat = 0.45;
      mat.clearcoatRoughness = 0.22;
    } else if (choice.material === "paper") {
      mat.color.set("#e4d0b4");
      mat.metalness = 0;
      mat.roughness = 0.92;
      mat.roughnessMap = fiberMap;
      mat.clearcoat = 0;
      mat.sheen = 0.65;
      mat.sheenColor = new THREE.Color("#fff4e4");
      mat.sheenRoughness = 0.7;
    } else {
      mat.color.set("#d7dee8");
      mat.metalness = 0;
      mat.roughness = 0.05;
      mat.clearcoat = 1;
      mat.clearcoatRoughness = 0.04;
      mat.transmission = 0.9;
      mat.thickness = 0.55;
      mat.ior = 1.5;
      mat.iridescence = 0.55;
      mat.iridescenceIOR = 1.25;
      if ("dispersion" in mat) mat.dispersion = 0.1;
    }
    mat.needsUpdate = true;
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
  return [...cards].sort((a, b) => (rank.get(a.clip.id) ?? 0) - (rank.get(b.clip.id) ?? 0));
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
      const ang = rel * 0.46;
      x = Math.sin(ang) * 2.05;
      z = (Math.cos(ang) - 1) * 1.35;
      rot = -ang * 0.82;
      scale = 1.02 - Math.min(Math.abs(rel), 2.2) * 0.1;
    } else if (choice.shelf === "rail" || choice.shelf === "manual") {
      x = (index - (n - 1) / 2) * 1.9;
      rot = rel * -0.05;
      scale = index === Math.round(dtFocus) ? 1.04 : 0.96;
    } else {
      x = rel * 1.42;
      z = -Math.abs(rel) * 0.92;
      rot = THREE.MathUtils.clamp(rel * -0.46, -0.9, 0.9);
      scale = 1.14 - Math.min(Math.abs(rel), 2.2) * 0.1;
    }
    const front = Math.abs(rel) < 0.5;
    const tucked = choice.shelf === "orbit" && Math.abs(rel) > 2.35;
    if (tucked) scale = 0.02;
    if (front && choice.player === "expand") {
      z += openAmt * 1.35;
      scale += openAmt * 0.7;
      rot *= 1 - openAmt;
    }
    card.group.position.x += (x - card.group.position.x) * 0.18;
    card.group.position.y = 0.95;
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
  if (!list.length) return null;
  const index = THREE.MathUtils.clamp(Math.round(focus), 0, list.length - 1);
  return list[index];
}

function showPlayer(card) {
  open = true;
  sweep = 0;
  playerTitle.textContent = card.clip.title;
  playerSub.textContent = EMBED
    ? `${card.clip.meta} · The file stays where it is.`
    : `${card.clip.meta} · path stays on disk · sample still, not your file`;
  if (!EMBED && card.tex && card.tex.image) {
    playerStill.src = card.tex.image.toDataURL("image/jpeg", 0.86);
  }
  playerStill.alt = card.clip.title;
  playerEl.classList.add("open");
  playerEl.classList.toggle("theater", choice.player === "theater");
  playerEl.classList.toggle("caption", choice.player === "expand");
  if (EMBED) {
    fetch("/api/shelf/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "open", id: card.clip.id }),
    }).catch(() => {});
    return;
  }
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
    focusTo = THREE.MathUtils.clamp(focusTo + (dx > 0 ? -1 : 1), 0, Math.max(orderedCards().length - 1, 0));
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
    focusTo = THREE.MathUtils.clamp(focusTo + Math.sign(event.deltaY), 0, Math.max(orderedCards().length - 1, 0));
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
  if (EMBED) return;
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
  grade.uniforms.grain.value = choice.grain ? 0.025 : 0;
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

function applySaved(data) {
  const saved = data.choices || {};
  for (const group of GROUPS) {
    const value = saved[group.key];
    const id = value && value.id;
    if (id && group.options.some((option) => option[0] === id)) choice[group.key] = id;
  }
  for (const [key] of LAYERS) {
    const value = saved[key];
    if (value && (value.id === "on" || value.id === "off")) choice[key] = value.id === "on";
  }
  if (Array.isArray(data.order) && data.order.length) {
    const byTitle = new Map(CLIPS.map((clip) => [clip.title, clip.id]));
    const ids = data.order
      .map((item) => byTitle.get(item) || item)
      .filter((id) => CLIPS.some((clip) => clip.id === id));
    if (ids.length === CLIPS.length) state.order = ids;
  }
  state.events = Array.isArray(data.events) ? data.events.slice(-400) : [];
  state.kept = Array.isArray(data.kept) ? data.kept : [];
  state.discarded = Array.isArray(data.discarded) ? data.discarded : [];
  state.notes = data.notes || "";
  state.status = data.status === "complete" ? "complete" : "in progress";
  notesEl.value = state.notes;
  const done = document.getElementById("done");
  if (done) done.textContent = state.status === "complete" ? "Reopen feedback" : "Mark feedback complete";
}

async function resumeSession() {
  try {
    const response = await fetch("/api/feedback", { cache: "no-store" });
    if (response.status === 200) applySaved(await response.json());
  } catch {
    /* first visit has nothing to restore */
  }
  applyBodyMaterial();
  paintControls();
  record("open", "Studio reopened");
}

function repaintStills() {
  for (const card of cards) {
    const next = makeStill(card.clip);
    card.screenMat.map = next;
    card.screenMat.needsUpdate = true;
    card.tex.dispose();
    card.tex = next;
    const back = card.group.children.find((child) => child.userData.role === "back");
    if (back && back.material.map) {
      const printed = makeBack(card.clip);
      back.material.map.dispose();
      back.material.map = printed;
      back.material.needsUpdate = true;
    }
  }
}

async function loadShelf() {
  try {
    const response = await fetch("/api/shelf", { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    if (data.look) Object.assign(choice, LOCKED, data.look);
    mountCards(Array.isArray(data.clips) ? data.clips : []);
    document.fonts.ready.then(repaintStills);
  } catch {
    banner.style.display = "block";
    banner.textContent = "Library shelf could not load.";
    mountCards([]);
  }
}

document.fonts.ready.then(repaintStills);
if (EMBED) {
  loadShelf();
} else {
  mountCards(CLIPS);
  resumeSession();
}
requestAnimationFrame(animate);
