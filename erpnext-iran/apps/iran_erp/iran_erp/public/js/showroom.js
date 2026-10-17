// The car's page on the showroom website: photos, the 3D viewer, the instalment calculator and
// the request form. No framework: the page must load fast on a phone.

(function () {
	const car = window.SR_CAR;
	const $ = (sel, root = document) => root.querySelector(sel);
	const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
	const PERSIAN = "۰۱۲۳۴۵۶۷۸۹";
	const fa = (text) => String(text).replace(/\d/g, (d) => PERSIAN[d]);
	const unit = car.toman ? 10 : 1;
	const money = (rial) => fa(Math.round(rial / unit).toLocaleString("en-US")).replace(/,/g, "٬") + (car.toman ? " تومان" : " ریال");

	async function api(method, args, post) {
		const headers = { Accept: "application/json" };
		const token = $('meta[name="csrf-token"]');
		if (token) headers["X-Frappe-CSRF-Token"] = token.content;
		let url = `/api/method/iran_erp.iran_dealership.showroom.${method}`;
		const init = { headers };
		if (post) {
			init.method = "POST";
			headers["Content-Type"] = "application/json";
			init.body = JSON.stringify(args);
		} else {
			url += "?" + new URLSearchParams(args);
		}
		const response = await fetch(url, init);
		const data = await response.json().catch(() => ({}));
		if (!response.ok) {
			let message = "خطایی پیش آمد؛ دوباره تلاش کنید.";
			try {
				message = JSON.parse(JSON.parse(data._server_messages)[0]).message || message;
			} catch (e) {
				if (response.status === 429) message = "درخواست‌های زیادی فرستاده شده؛ کمی بعد دوباره تلاش کنید.";
			}
			throw new Error(message.replace(/<[^>]+>/g, ""));
		}
		return data.message;
	}

	// ---------------------------------------------------------------- photos and 3D tabs

	$$(".sr-thumbs button").forEach((button) =>
		button.addEventListener("click", () => {
			$("#sr-main-photo").src = button.dataset.photo;
			$$(".sr-thumbs button").forEach((b) => b.classList.toggle("on", b === button));
		})
	);

	let viewer = null;
	async function open_3d() {
		if (viewer) return;
		const stage = $("#sr-stage");
		try {
			const { mount } = await import("/assets/iran_erp/js/showroom_3d.js");
			viewer = mount(stage, {
				color: car.color,
				model: car.model_3d || null,
				on_spin: (on) => $('[data-3d="spin"]').classList.toggle("on", on),
				on_ready: ({ drawn, animations }) => {
					$$(".drawn-only").forEach((b) => (b.hidden = !drawn));
					const box = $("#sr-anims");
					animations.forEach((name, i) => {
						const b = document.createElement("button");
						b.textContent = name || `حرکت ${fa(i + 1)}`;
						b.addEventListener("click", () => viewer.play(i));
						box.appendChild(b);
					});
				},
			});
		} catch (e) {
			stage.innerHTML = '<div class="sr-stage-hint">مرورگر شما نمای سه‌بعدی را نشان نمی‌دهد.</div>';
		}
	}
	$$(".sr-tabs button").forEach((tab) =>
		tab.addEventListener("click", () => {
			$$(".sr-tabs button").forEach((t) => t.classList.toggle("on", t === tab));
			$$(".sr-pane").forEach((p) => (p.hidden = p.dataset.pane !== tab.dataset.tab));
			if (tab.dataset.tab === "three") open_3d();
		})
	);
	if (!$('[data-pane="photos"]')) open_3d();
	$$("[data-3d]").forEach((b) =>
		b.addEventListener("click", () => {
			if (!viewer) return;
			const on = viewer[b.dataset["3d"]]();
			b.classList.toggle("on", on);
			if (b.dataset["3d"] === "doors") b.textContent = on ? "بستن درها" : "باز کردن درها";
			if (b.dataset["3d"] === "hood") b.textContent = on ? "بستن کاپوت" : "باز کردن کاپوت";
		})
	);
	$$("[data-view]").forEach((b) => b.addEventListener("click", () => viewer && viewer.view(b.dataset.view)));

	// ---------------------------------------------------------------- instalment calculator

	const plan = { down: 0, months: car.months.includes(12) ? 12 : car.months[0], result: null };
	const slider = $("#sr-down");
	if (slider && car.price) {
		const least = Math.ceil(car.min_down_percent);
		slider.min = least;
		slider.max = 90;
		slider.value = Math.max(least, 40);
		$("#sr-down-min").textContent = fa(least) + "٪";
		$("#sr-down-max").textContent = fa(90) + "٪";
		const months = $$("#sr-months button");
		const mark = () => months.forEach((b) => b.classList.toggle("on", +b.dataset.months === plan.months));
		months.forEach((b) =>
			b.addEventListener("click", () => {
				plan.months = +b.dataset.months;
				mark();
				run();
			})
		);
		mark();
		let timer;
		const run = () => {
			// Whole millions of tomans (ten millions of rials) for the down payment
			plan.down = Math.ceil((car.price * slider.value) / 100 / 1e7) * 1e7;
			$("#sr-down-text").textContent = `${money(plan.down)} (${fa(slider.value)}٪)`;
			clearTimeout(timer);
			timer = setTimeout(async () => {
				$("#sr-result").classList.add("busy");
				try {
					const r = await api("simulate", { vehicle: car.name, down_payment: plan.down, months: plan.months });
					plan.result = r;
					$("#sr-monthly").textContent = r.monthly ? `${money(r.monthly)} × ${fa(r.months)}` : "نقدی";
					$("#sr-r-price").textContent = money(r.price);
					$("#sr-r-down").textContent = money(r.down_payment);
					$("#sr-r-financed").textContent = money(r.financed);
					$("#sr-r-interest").textContent = money(r.interest);
					$("#sr-r-total").textContent = money(r.total);
				} catch (e) {
					$("#sr-monthly").textContent = e.message;
				}
				$("#sr-result").classList.remove("busy");
			}, 250);
		};
		slider.addEventListener("input", run);
		run();
	}

	// ---------------------------------------------------------------- requests

	const dialog = $("#sr-inquiry");
	const form = $("#sr-inquiry-form");
	const TITLES = {
		"Test Drive": "رزرو تست‌درایو",
		"Call Me Back": "با من تماس بگیرید",
		"Instalment Plan": "درخواست خرید اقساطی",
		Question: "پرسش درباره‌ی خودرو",
	};
	$$("[data-inquiry]").forEach((b) =>
		b.addEventListener("click", (e) => {
			e.preventDefault();
			const kind = b.dataset.inquiry;
			form.kind.value = kind;
			$("#sr-inquiry-title").textContent = TITLES[kind];
			$(".sr-when").hidden = kind !== "Test Drive";
			const planBox = $("#sr-inquiry-plan");
			planBox.hidden = !(kind === "Instalment Plan" && plan.result && plan.result.monthly);
			if (!planBox.hidden) {
				planBox.textContent = `پیش‌پرداخت ${money(plan.result.down_payment)} و ${fa(plan.result.months)} قسط ${money(plan.result.monthly)}`;
			}
			$("#sr-inquiry-error").hidden = true;
			form.hidden = false;
			$("#sr-sent").hidden = true;
			dialog.showModal();
		})
	);
	$$("[data-close]", dialog).forEach((b) => b.addEventListener("click", () => dialog.close()));
	form.addEventListener("submit", async (e) => {
		e.preventDefault();
		const data = Object.fromEntries(new FormData(form).entries());
		data.vehicle = car.name;
		if (data.kind === "Instalment Plan" && plan.result && plan.result.monthly) {
			data.down_payment = plan.result.down_payment;
			data.months = plan.result.months;
		}
		const button = $('button[type="submit"]', form);
		button.disabled = true;
		try {
			const r = await api("send_inquiry", data, true);
			form.hidden = true;
			$("#sr-sent-code").textContent = r.name;
			$("#sr-sent").hidden = false;
			form.reset();
		} catch (err) {
			const box = $("#sr-inquiry-error");
			box.textContent = err.message;
			box.hidden = false;
		}
		button.disabled = false;
	});
})();
