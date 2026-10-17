// The showroom's 3D viewer: the car on a turning platform. Drag to look around, scroll or pinch to
// zoom. With a .glb file on the car model that model is shown (and its own animations, such as
// opening doors, get buttons); without one, a car is drawn in the car's colour, whose doors and
// hood open.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const LENGTH = 4.4;

function paint(color) {
	return new THREE.MeshPhysicalMaterial({
		color,
		metalness: 0.55,
		roughness: 0.32,
		clearcoat: 1,
		clearcoatRoughness: 0.08,
	});
}

function side_shape(points) {
	const shape = new THREE.Shape();
	points.forEach(([x, y], i) => (i ? shape.lineTo(x, y) : shape.moveTo(x, y)));
	shape.closePath();
	return shape;
}

function extrude(points, depth, material, bevel = 0.06) {
	const geometry = new THREE.ExtrudeGeometry(side_shape(points), {
		depth: depth - bevel * 2,
		bevelEnabled: true,
		bevelThickness: bevel,
		bevelSize: bevel,
		bevelSegments: 4,
		curveSegments: 8,
	});
	geometry.translate(0, 0, -(depth - bevel * 2) / 2);
	const mesh = new THREE.Mesh(geometry, material);
	mesh.castShadow = true;
	mesh.receiveShadow = true;
	return mesh;
}

// A sedan seen from the side: x along the car (front at +x), y up, z across
function drawn_car(color) {
	const car = new THREE.Group();
	const body_paint = paint(color);
	const glass = new THREE.MeshPhysicalMaterial({ color: 0x0d1620, metalness: 0.2, roughness: 0.05, transmission: 0.1, opacity: 0.85, transparent: true });
	const black = new THREE.MeshStandardMaterial({ color: 0x15171a, roughness: 0.8 });
	const chrome = new THREE.MeshStandardMaterial({ color: 0xd9dde2, metalness: 1, roughness: 0.18 });
	const width = 1.8;

	car.add(
		extrude(
			[[-2.2, 0.32], [2.15, 0.32], [2.25, 0.5], [2.25, 0.78], [2.0, 0.95], [0.75, 1.02], [-1.75, 1.05], [-2.2, 0.98], [-2.27, 0.7]],
			width,
			body_paint
		)
	);
	const cabin = extrude([[0.75, 1.0], [-0.05, 1.5], [-1.15, 1.52], [-1.78, 1.02]], width - 0.18, glass, 0.05);
	car.add(cabin);
	// Roof over the glass, and the black sills under the doors
	const roof = extrude([[-0.02, 1.48], [-1.13, 1.5], [-1.1, 1.54], [0.02, 1.53]], width - 0.2, body_paint, 0.03);
	car.add(roof);
	const sill = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.08, width + 0.02), black);
	sill.position.set(-0.15, 0.34, 0);
	car.add(sill);

	// Doors: each hinged at its front edge
	const doors = [];
	for (const [front, length] of [[0.72, 0.95], [-0.25, 0.95]]) {
		for (const side of [1, -1]) {
			const hinge = new THREE.Group();
			hinge.position.set(front, 0, (side * width) / 2 + side * 0.012);
			const door = new THREE.Mesh(new THREE.BoxGeometry(length, 0.6, 0.04), body_paint);
			door.position.set(-length / 2, 0.68, 0);
			door.castShadow = true;
			const pane = new THREE.Mesh(new THREE.BoxGeometry(length * 0.86, 0.36, 0.03), glass);
			pane.position.set(-length / 2 - 0.02, 1.2, -side * 0.06);
			const handle = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.03, 0.03), chrome);
			handle.position.set(-length + 0.22, 0.88, side * 0.03);
			hinge.add(door, pane, handle);
			hinge.userData.side = side;
			car.add(hinge);
			doors.push(hinge);
		}
	}

	// Hood: hinged at the windscreen, with the engine under it
	const engine = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.1, width - 0.4), new THREE.MeshStandardMaterial({ color: 0x2b2f36, metalness: 0.6, roughness: 0.5 }));
	engine.position.set(1.4, 0.93, 0);
	car.add(engine);
	const hood_hinge = new THREE.Group();
	hood_hinge.position.set(0.78, 1.0, 0);
	const hood = new THREE.Mesh(new THREE.BoxGeometry(1.32, 0.04, width - 0.12), body_paint);
	hood.position.set(0.64, 0.0, 0);
	hood.rotation.z = -0.06;
	hood.castShadow = true;
	hood_hinge.add(hood);
	car.add(hood_hinge);

	// Wheels
	const tyre = new THREE.CylinderGeometry(0.36, 0.36, 0.26, 40);
	tyre.rotateX(Math.PI / 2);
	const rim = new THREE.CylinderGeometry(0.23, 0.23, 0.27, 24);
	rim.rotateX(Math.PI / 2);
	for (const x of [1.38, -1.38]) {
		for (const z of [0.8, -0.8]) {
			const wheel = new THREE.Group();
			wheel.add(new THREE.Mesh(tyre, black), new THREE.Mesh(rim, chrome));
			wheel.position.set(x, 0.36, z);
			wheel.children.forEach((m) => (m.castShadow = true));
			car.add(wheel);
		}
	}

	// Lights
	const head = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xe8f1ff, emissiveIntensity: 0.9 });
	const tail = new THREE.MeshStandardMaterial({ color: 0x9b1111, emissive: 0xc81e1e, emissiveIntensity: 0.6 });
	for (const z of [0.62, -0.62]) {
		const h = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.1, 0.36), head);
		h.position.set(2.24, 0.78, z);
		const t = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.1, 0.4), tail);
		t.position.set(-2.25, 0.86, z);
		car.add(h, t);
	}
	const grille = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.16, 0.7), black);
	grille.position.set(2.25, 0.62, 0);
	car.add(grille);

	return { car, doors, hood: hood_hinge };
}

export function mount(element, options = {}) {
	const color = options.color || "#9aa4b2";
	const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
	renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
	renderer.shadowMap.enabled = true;
	renderer.shadowMap.type = THREE.PCFSoftShadowMap;
	renderer.toneMapping = THREE.ACESFilmicToneMapping;
	element.appendChild(renderer.domElement);

	const scene = new THREE.Scene();
	scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
	const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100);
	camera.position.set(6.2, 2.6, 6.2);

	const controls = new OrbitControls(camera, renderer.domElement);
	controls.target.set(0, 0.7, 0);
	controls.enableDamping = true;
	controls.enablePan = false;
	controls.minDistance = 3.2;
	controls.maxDistance = 14;
	controls.maxPolarAngle = Math.PI / 2 - 0.04;

	scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 0.6));
	const sun = new THREE.DirectionalLight(0xffffff, 1.6);
	sun.position.set(5, 9, 4);
	sun.castShadow = true;
	sun.shadow.mapSize.set(1024, 1024);
	Object.assign(sun.shadow.camera, { left: -5, right: 5, top: 5, bottom: -5 });
	scene.add(sun);

	// The turning platform
	const platform = new THREE.Group();
	const disc = new THREE.Mesh(
		new THREE.CylinderGeometry(3.3, 3.4, 0.14, 96),
		new THREE.MeshStandardMaterial({ color: 0x23272e, metalness: 0.7, roughness: 0.35 })
	);
	disc.position.y = -0.07;
	disc.receiveShadow = true;
	const ring = new THREE.Mesh(
		new THREE.TorusGeometry(3.32, 0.025, 8, 128),
		new THREE.MeshStandardMaterial({ color: 0x3aa0ff, emissive: 0x1a6fd0, emissiveIntensity: 1.2 })
	);
	ring.rotation.x = Math.PI / 2;
	ring.position.y = 0.005;
	platform.add(disc, ring);
	scene.add(platform);

	const state = { spin: true, doors: 0, doors_to: 0, hood: 0, hood_to: 0, parts: null, mixer: null, actions: [] };

	const fit = (object) => {
		const box = new THREE.Box3().setFromObject(object);
		const size = box.getSize(new THREE.Vector3());
		const scale = LENGTH / Math.max(size.x, size.z);
		object.scale.setScalar(scale);
		const fitted = new THREE.Box3().setFromObject(object);
		const center = fitted.getCenter(new THREE.Vector3());
		object.position.x -= center.x;
		object.position.z -= center.z;
		object.position.y -= fitted.min.y;
	};

	const use_drawn = () => {
		state.parts = drawn_car(color);
		platform.add(state.parts.car);
		options.on_ready && options.on_ready({ drawn: true, animations: [] });
	};

	if (options.model) {
		new GLTFLoader().load(
			options.model,
			(gltf) => {
				const model = gltf.scene;
				model.traverse((m) => {
					if (m.isMesh) m.castShadow = m.receiveShadow = true;
				});
				fit(model);
				platform.add(model);
				if (gltf.animations.length) {
					state.mixer = new THREE.AnimationMixer(model);
					state.actions = gltf.animations.map((clip) => {
						const action = state.mixer.clipAction(clip);
						action.clampWhenFinished = true;
						action.loop = THREE.LoopOnce;
						return action;
					});
				}
				options.on_ready && options.on_ready({ drawn: false, animations: gltf.animations.map((a) => a.name) });
			},
			undefined,
			use_drawn
		);
	} else {
		use_drawn();
	}

	const resize = () => {
		const { clientWidth: w, clientHeight: h } = element;
		renderer.setSize(w, h, false);
		camera.aspect = w / Math.max(h, 1);
		camera.updateProjectionMatrix();
	};
	new ResizeObserver(resize).observe(element);
	resize();

	// Dragging stops the turning; it comes back by the button
	controls.addEventListener("start", () => {
		state.spin = false;
		options.on_spin && options.on_spin(false);
	});

	const clock = new THREE.Clock();
	renderer.setAnimationLoop(() => {
		const dt = Math.min(clock.getDelta(), 0.05);
		if (state.spin) platform.rotation.y += dt * 0.35;
		const ease = (from, to) => from + (to - from) * Math.min(1, dt * 4);
		if (state.parts) {
			state.doors = ease(state.doors, state.doors_to);
			state.hood = ease(state.hood, state.hood_to);
			state.parts.doors.forEach((hinge) => (hinge.rotation.y = hinge.userData.side * state.doors));
			state.parts.hood.rotation.z = state.hood;
		}
		if (state.mixer) state.mixer.update(dt);
		controls.update();
		renderer.render(scene, camera);
	});

	return {
		spin(on) {
			state.spin = on ?? !state.spin;
			return state.spin;
		},
		doors() {
			state.doors_to = state.doors_to ? 0 : 1.05;
			return !!state.doors_to;
		},
		hood() {
			state.hood_to = state.hood_to ? 0 : 0.95;
			return !!state.hood_to;
		},
		play(index) {
			const action = state.actions[index];
			if (!action) return;
			if (action.isRunning() || action.time > 0) {
				action.timeScale = action.timeScale > 0 ? -1 : 1;
				action.paused = false;
				action.play();
			} else {
				action.reset().play();
			}
		},
		view(name) {
			const views = { front: [6.5, 1.6, 0.2], side: [0.1, 1.6, 7], back: [-6.5, 1.8, 0.2], top: [0.1, 9, 0.1], three: [6.2, 2.6, 6.2] };
			const [x, y, z] = views[name] || views.three;
			state.spin = false;
			options.on_spin && options.on_spin(false);
			platform.rotation.y = 0;
			camera.position.set(x, y, z);
			controls.update();
		},
	};
}
