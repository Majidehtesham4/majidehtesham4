// The dealership's home: the state of the lot and the money in one look, month-by-month profit
// and costs on a chart whose series are ticked on and off, and the latest events.

// The chart's series in a fixed order: each keeps its colour whatever else is ticked
const IRAN_DASH_SERIES = [
	["sales", "Car Sales"],
	["car_profit", "Profit on Cars Sold"],
	["interest", "Instalment Profit"],
	["service_costs", "Service Costs"],
	["investor_profit", "Investors' Profit"],
	["net", "Net Profit"],
	["purchases", "Car Purchases"],
	["collected", "Instalments Collected"],
];
const IRAN_DASH_DEFAULT = ["car_profit", "interest", "investor_profit", "net"];
// Validated categorical palette, light and dark steps of the same eight hues
const IRAN_DASH_COLORS = {
	light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
	dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
};
const IRAN_DASH_LOT = [
	["Awaiting Delivery", "#6250d6", "#9085e9"],
	["In Preparation", "#eda100", "#c98500"],
	["Ready for Sale", "#1baf7a", "#199e70"],
	["Reserved", "#2a78d6", "#3987e5"],
];

const IRAN_DASH_ICONS = {
	car: '<path d="M5 17h14M6 17v2M18 17v2M3 13l2-6a2 2 0 0 1 2-1h10a2 2 0 0 1 2 1l2 6v4H3z"/><circle cx="7.5" cy="13.5" r="1"/><circle cx="16.5" cy="13.5" r="1"/>',
	sales: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
	profit: '<circle cx="12" cy="12" r="9"/><path d="M15 9.5c-.5-1-1.6-1.5-3-1.5-1.7 0-3 .9-3 2s1 1.7 3 2 3 .9 3 2-1.3 2-3 2c-1.4 0-2.5-.5-3-1.5M12 6v2M12 16v2"/>',
	cash: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
	alert: '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17h.01"/>',
	users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.5-3.5 3.2-5.5 6.5-5.5s6 2 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c2 .7 3.2 2.5 3.5 5.2"/>',
	cheque: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 10h7M6 14h4M15 14h3"/>',
	up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
	down: '<path d="M12 5v14M5 12l7 7 7-7"/>',
	clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};

frappe.pages["iran-dealership"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Car Dealership"), single_column: true });
	const $body = $(`<div class="iran-dash" dir="rtl"></div>`).appendTo(page.main);
	const esc = frappe.utils.escape_html;
	const money = (v) => iran_erp.money.format(v || 0);
	const digits = (v) => (iran_erp.to_persian_digits ? iran_erp.to_persian_digits(String(v)) : String(v));
	// Plain text, not frappe.format: that wraps the number in a block and breaks the line around it
	const num = (v) => digits(Math.round(v || 0).toLocaleString("en-US"));
	const icon = (name, cls = "") =>
		`<svg class="iran-dash-icon ${cls}" viewBox="0 0 24 24" aria-hidden="true">${IRAN_DASH_ICONS[name]}</svg>`;
	const store = {
		get(key, fallback) {
			try {
				const v = localStorage.getItem(`iran_dash_${key}`);
				return v ? JSON.parse(v) : fallback;
			} catch (e) {
				return fallback;
			}
		},
		set(key, value) {
			try {
				localStorage.setItem(`iran_dash_${key}`, JSON.stringify(value));
			} catch (e) {
				// private window: the choice lasts until the page is left
			}
		},
	};
	const state = {
		branch: null,
		months: store.get("months", 12),
		shown: store.get("series", IRAN_DASH_DEFAULT),
		kind: store.get("kind", "bar"),
		table: false,
		data: null,
	};

	page.set_primary_action(__("New Car"), () => frappe.new_doc("Iran Vehicle"), "plus");
	page.add_inner_button(__("New Instalment Sale"), () => frappe.new_doc("Iran Instalment Sale"));
	page.add_inner_button(__("New Investment Contract"), () => frappe.new_doc("Iran Investment Contract"));
	if (frappe.user.has_role("System Manager")) {
		page.add_inner_button(__("New Reception Staff"), () =>
			frappe.prompt(
				[
					{
						fieldtype: "HTML",
						options: `<p class="text-muted">${__(
							"Reception registers cars, their body condition, inspection and photos, and puts them on the website. They do not see purchase prices, costs, owners or the books."
						)}</p>`,
					},
					{ fieldname: "full_name", fieldtype: "Data", label: __("Full Name"), reqd: 1 },
					{ fieldname: "email", fieldtype: "Data", options: "Email", label: __("Email (their username)"), reqd: 1 },
					{ fieldname: "password", fieldtype: "Password", label: __("Password"), reqd: 1 },
					{ fieldname: "branch", fieldtype: "Link", options: "Branch", label: __("Branch") },
				],
				(values) =>
					frappe
						.xcall("iran_erp.business.add_reception_user", values)
						.then((user) => frappe.show_alert({ message: __("{0} can now log in.", [user]), indicator: "green" }, 10)),
				__("New Reception Staff"),
				__("Create")
			)
		);
	}
	page.add_field({
		fieldtype: "Select",
		fieldname: "months",
		label: __("Period"),
		options: [
			{ value: "6", label: __("Last 6 Months") },
			{ value: "12", label: __("Last 12 Months") },
			{ value: "24", label: __("Last 24 Months") },
		],
		default: String(state.months),
		change() {
			state.months = +this.get_value() || 12;
			store.set("months", state.months);
			load();
		},
	});

	const dark = () => document.documentElement.getAttribute("data-theme") === "dark";
	const color = (key) => IRAN_DASH_COLORS[dark() ? "dark" : "light"][IRAN_DASH_SERIES.findIndex(([k]) => k === key)];

	// «۱٫۲ میلیارد», «۳۵۰ میلیون»: axis and tooltip-friendly short amounts
	const short = (v) => {
		const a = Math.abs(v);
		const sign = v < 0 ? "-" : "";
		const fmt = (n) => digits((Math.round(n * 10) / 10).toString().replace(".", "٫"));
		if (a >= 1e9) return `${sign}${fmt(a / 1e9)} ${__("billion")}`;
		if (a >= 1e6) return `${sign}${fmt(a / 1e6)} ${__("million")}`;
		if (a >= 1e3) return `${sign}${fmt(a / 1e3)} ${__("thousand")}`;
		return sign + digits(a);
	};

	const delta = (now, before, good_when_up = true) => {
		if (!before && !now) return "";
		const up = now >= before;
		const pct = before ? Math.round((Math.abs(now - before) / Math.abs(before)) * 100) : null;
		const tone = up === good_when_up ? "good" : "bad";
		const text = pct === null ? __("new") : `${digits(pct)}٪`;
		return `<span class="iran-dash-delta ${tone}" title="${esc(__("Compared with last month"))}">${icon(up ? "up" : "down")}${text}</span>`;
	};

	const tile = ({ label, value, sub = "", route, icon_name, tone = "", extra = "" }) => `
		<a class="iran-dash-tile ${tone}" ${route ? `data-route='${esc(JSON.stringify(route))}'` : ""}>
			<div class="iran-dash-tile-head">${icon(icon_name)}<span>${label}</span>${extra}</div>
			<div class="iran-dash-tile-value">${value}</div>
			${sub ? `<div class="iran-dash-tile-sub">${sub}</div>` : ""}
		</a>`;

	// Whose the cars are: the business's own at cost, customers' cars left for sale and the
	// investors' cars; each opens the list of those cars
	const OWNERS = [
		["Business", "The business's own cars", "cost"],
		["Customer", "Cars left for sale (consignment)", "asking"],
		["Investor", "Investors' cars", "cost"],
	];
	// No branch key: every branch; "" : the cars with no branch set
	const cars_link = (args) => {
		if (args.branch === null || args.branch === undefined) delete args.branch;
		return `data-cars='${esc(JSON.stringify(args))}'`;
	};
	const holdings_html = (d) => {
		if (!d.holdings) return "";
		return `<div class="iran-dash-holdings">${OWNERS.map(([owner, label, value]) => {
			const h = d.holdings[owner];
			return `<a class="iran-dash-hero-stat" ${cars_link({ ownership: owner, branch: d.branch || null })}>
				<span>${__(label)}</span>
				<b>${money(h[value])}</b>
				<small>${__("{0} cars", [num(h.count)])}</small>
			</a>`;
		}).join("")}</div>`;
	};

	// The general manager: every branch beside the others. A branch's manager: the cars of the
	// other branches, which they may sell too
	const branches_html = (d) => {
		if (d.branches && d.branches.length) {
			const total = (key) => d.branches.reduce((sum, r) => sum + (r[key] || 0), 0);
			const cell = (r, owner, count_key, value_key) =>
				`<td><a ${cars_link({ branch: r.branch, ownership: owner })}>${money(r[value_key])}<small>${__("{0} cars", [num(r[count_key])])}</small></a></td>`;
			const rows = d.branches.map((r) => `<tr>
				<th><a ${cars_link({ branch: r.branch })}>${esc(r.branch || __("No branch set"))}</a></th>
				<td><a ${cars_link({ branch: r.branch })}>${num(r.cars)}<small>${__("{0} ready for sale", [num(r.ready)])}</small></a></td>
				${cell(r, "Business", "business", "business_value")}
				${cell(r, "Customer", "customer", "customer_value")}
				${cell(r, "Investor", "investor", "investor_value")}
				<td>${money(r.sales)}<small>${__("{0} cars", [num(r.sold)])}</small></td>
				<td class="${r.profit < 0 ? "bad" : ""}">${money(r.profit)}</td>
			</tr>`).join("");
			return `<div class="iran-dash-box iran-dash-branches">
				<div class="iran-dash-title">${__("Branches")}</div>
				<div class="iran-dash-table-wrap"><table class="iran-dash-table">
					<thead><tr><th>${__("Branch")}</th><th>${__("Cars in the Lot")}</th><th>${__("The business's own cars")}</th>
					<th>${__("Cars left for sale (consignment)")}</th><th>${__("Investors' cars")}</th>
					<th>${__("Sales This Month")}</th><th>${__("Profit This Month")}</th></tr></thead>
					<tbody>${rows}</tbody>
					<tfoot><tr><th><a ${cars_link({})}>${__("Total")}</a></th><td>${num(total("cars"))}</td>
					<td>${money(total("business_value"))}</td><td>${money(total("customer_value"))}</td>
					<td>${money(total("investor_value"))}</td><td>${money(total("sales"))}</td><td>${money(total("profit"))}</td></tr></tfoot>
				</table></div>
			</div>`;
		}
		if (d.other_branches && d.other_branches.length) {
			return `<div class="iran-dash-box iran-dash-branches">
				<div class="iran-dash-title">${__("Cars of the Other Branches")}</div>
				<div class="text-muted small">${__("You may sell these cars too.")}</div>
				${d.other_branches.map((r) => `<a class="iran-dash-line" ${d.books ? cars_link({ branch: r.branch || "" }) : `data-route='${esc(JSON.stringify(["List", "Iran Vehicle", { branch: r.branch }]))}'`}>
					<span class="grow">${esc(r.branch || __("No branch set"))}</span><b>${__("{0} cars", [num(r.count)])}</b></a>`).join("")}
			</div>`;
		}
		return "";
	};

	// The cars behind a figure: price, owner and description of each
	const show_cars = async (args) => {
		const cars = await frappe.xcall("iran_erp.iran_dealership.dashboard.get_lot_cars", args);
		const costs = cars.some((c) => c.total_cost !== null);
		const sum = (key) => cars.reduce((t, c) => t + (c[key] || 0), 0);
		const title = [
			args.branch === undefined ? __("All branches") : args.branch || __("No branch set"),
			args.ownership ? __({ Business: "The business's own cars", Customer: "Cars left for sale (consignment)", Investor: "Investors' cars" }[args.ownership]) : "",
		].filter(Boolean).join(" — ");
		const rows = cars.map((c) => `<tr>
			<td><a href="/app/iran-vehicle/${encodeURIComponent(c.name)}">${esc(c.car_model || c.title)}</a>
				<small>${esc(digits(c.year || ""))} ${c.year ? (c.made_in === "Imported Car" ? __("Gregorian") : __("Jalali")) : ""} · ${esc(c.color || "")} · ${c.mileage ? __("{0} km", [num(c.mileage)]) : __("New")}</small></td>
			<td>${c.plate ? iran_erp.plate.html(c.plate) : ""}</td>
			<td>${esc(c.branch || "")}</td>
			<td>${__(c.status)}<small>${__("{0} days", [num(c.days)])}</small></td>
			<td>${__(c.ownership)}${c.owner_name ? `<small>${esc(c.owner_name)}</small>` : ""}</td>
			${costs ? `<td>${c.total_cost === null ? "—" : money(c.total_cost)}</td>` : ""}
			<td>${money(c.asking_price)}</td>
		</tr>`).join("");
		const dialog = new frappe.ui.Dialog({ title, size: "extra-large" });
		dialog.$body.html(`<div class="iran-dash-table-wrap"><table class="iran-dash-table iran-dash-cars">
			<thead><tr><th>${__("Car")}</th><th>${__("Plate")}</th><th>${__("Branch")}</th><th>${__("Status in the Lot")}</th>
			<th>${__("Owned By")}</th>${costs ? `<th>${__("Total Cost")}</th>` : ""}<th>${__("Asking Price")}</th></tr></thead>
			<tbody>${rows || `<tr><td colspan="7" class="text-muted">${__("No cars in the lot")}</td></tr>`}</tbody>
			<tfoot><tr><th colspan="5">${__("{0} cars", [num(cars.length)])}</th>${costs ? `<td>${money(sum("total_cost"))}</td>` : ""}<td>${money(sum("asking_price"))}</td></tr></tfoot>
		</table></div>`);
		dialog.show();
	};

	const render = (d) => {
		const c = d.counts;
		const tm = d.this_month;
		const lm = d.last_month;
		const net_cash = d.cheques_in.amount - d.cheques_out.amount;
		const total_lot = d.in_lot || 0;
		const lot_bar = IRAN_DASH_LOT.map(([status, light, dk]) => {
			const n = c[status] || 0;
			if (!n) return "";
			return `<a class="seg" style="flex:${n};background:${dark() ? dk : light}" title="${esc(__(status))}: ${num(n)}"
				data-route='${esc(JSON.stringify(["List", "Iran Vehicle", { status }]))}'></a>`;
		}).join("");
		const lot_legend = IRAN_DASH_LOT.map(([status, light, dk]) => `
			<a class="iran-dash-key" data-route='${esc(JSON.stringify(["List", "Iran Vehicle", { status }]))}'>
				<i style="background:${dark() ? dk : light}"></i><span>${__(status)}</span><b>${num(c[status] || 0)}</b>
			</a>`).join("");
		const max_age = Math.max(1, ...d.ages.map((a) => a.count));
		const ages = d.ages.map((a) => {
			const label = a.to === null ? __("More than {0} days", [digits(a.from - 1)]) : __("{0} to {1} days", [digits(a.from), digits(a.to)]);
			return `<div class="iran-dash-age ${a.from > 90 ? "old" : ""}">
				<span class="name">${label}</span>
				<span class="bar"><i style="width:${(a.count / max_age) * 100}%"></i></span>
				<b>${num(a.count)}</b>
			</div>`;
		}).join("");

		$body.html(`
			<div class="iran-dash-hero">
				<div>
					<div class="iran-dash-hero-name">${esc(d.trade_name || __("Car Dealership"))}</div>
					<div class="iran-dash-hero-sub">${esc(digits(d.today))}${d.branch ? ` — ${esc(d.branch)}` : ""}</div>
					${frappe.boot.iran_build ? `<div class="iran-dash-hero-sub iran-build">${esc(__("Version"))} ${esc(frappe.boot.iran_build)}</div>` : ""}
				</div>
				${holdings_html(d)}
			</div>

			<div class="iran-dash-tiles">
				${tile({ label: __("Cars in the Lot"), value: num(total_lot), icon_name: "car", route: ["List", "Iran Vehicle"],
					sub: __("{0} ready for sale", [num(c["Ready for Sale"])]) })}
				${tile({ label: __("Sales This Month"), value: money(tm.sales), icon_name: "sales", route: ["List", "Iran Instalment Sale"],
					sub: __("{0} cars — last month {1}", [num(d.sold_month), money(lm.sales)]), extra: delta(tm.sales, lm.sales) })}
				${tile({ label: __("Net Profit This Month"), value: money(tm.net), icon_name: "profit", tone: tm.net < 0 ? "bad" : "",
					sub: __("Last month {0}", [money(lm.net)]), extra: delta(tm.net, lm.net) })}
				${tile({ label: __("Cash in the Next 7 Days"), value: money(net_cash), icon_name: "cash", route: ["List", "Iran Cheque"],
					tone: net_cash < 0 ? "bad" : "",
					sub: __("To receive {0} — to pay {1}", [money(d.cheques_in.amount), money(d.cheques_out.amount)]) })}
			</div>

			<div class="iran-dash-alerts">
				${tile({ label: __("Overdue Instalments"), value: money(d.overdue.amount), icon_name: "alert", tone: d.overdue.count ? "critical" : "calm",
					route: ["query-report", "Overdue Instalments"], sub: __("{0} instalments", [num(d.overdue.count)]) })}
				${tile({ label: __("Due to Investors This Month"), value: money(d.investors_month), icon_name: "users", tone: d.investors_month ? "warning" : "calm",
					route: ["query-report", "Instalments and Investors Cash Forecast"] })}
				${tile({ label: __("New Customer Requests"), value: num(d.requests), icon_name: "users", tone: d.requests ? "warning" : "calm",
					route: ["List", "Iran Car Inquiry", { status: "New" }], sub: __("From the website and by phone") })}
				${tile({ label: __("Cheques This Week"), value: `${num(d.cheques_in.count + d.cheques_out.count)}`, icon_name: "cheque", tone: "calm",
					route: ["List", "Iran Cheque"], sub: __("{0} to receive, {1} to pay", [num(d.cheques_in.count), num(d.cheques_out.count)]) })}
			</div>

			${branches_html(d)}

			<div class="iran-dash-row">
				<div class="iran-dash-box">
					<div class="iran-dash-title">${__("The Lot")}</div>
					<div class="iran-dash-stack">${lot_bar || `<span class="empty"></span>`}</div>
					<div class="iran-dash-keys">${lot_legend}</div>
					<div class="iran-dash-title small">${__("Days in the Lot")}</div>
					${ages}
				</div>
				<div class="iran-dash-box wide iran-dash-money">
					<div class="iran-dash-money-head">
						<div class="iran-dash-title">${__("Profit, Costs and Sales by Month")}</div>
						<div class="iran-dash-switch">
							<button data-kind="bar" class="${state.kind === "bar" ? "on" : ""}">${__("Bars")}</button>
							<button data-kind="line" class="${state.kind === "line" ? "on" : ""}">${__("Lines")}</button>
							<button data-table="1" class="${state.table ? "on" : ""}">${__("Table")}</button>
						</div>
					</div>
					<div class="iran-dash-series">
						${IRAN_DASH_SERIES.map(([key, label]) => `
							<label class="iran-dash-chip ${state.shown.includes(key) ? "on" : ""}">
								<input type="checkbox" data-series="${key}" ${state.shown.includes(key) ? "checked" : ""}>
								<i style="--c:${color(key)}"></i><span>${__(label)}</span>
							</label>`).join("")}
					</div>
					<div class="iran-dash-chart"></div>
					<div class="iran-dash-tooltip" hidden></div>
				</div>
			</div>

			<div class="iran-dash-row three">
				<div class="iran-dash-box">
					<div class="iran-dash-title">${icon("clock")}${__("Longest in the Lot")}</div>
					${d.oldest.length ? d.oldest.map((r) => `
						<a class="iran-dash-line" data-route='${esc(JSON.stringify(["Form", "Iran Vehicle", r.name]))}'>
							<span class="grow">${esc(r.title || r.name)}<small>${__(r.status)}</small></span>
							<span class="iran-dash-days ${r.days > 90 ? "critical" : r.days > 60 ? "warning" : ""}">
								${r.days > 60 ? icon("alert") : ""}${__("{0} days", [num(r.days)])}</span>
						</a>`).join("") : `<div class="text-muted">${__("No cars in the lot")}</div>`}
				</div>
				<div class="iran-dash-box">
					<div class="iran-dash-title">${__("Cars by Parking")}</div>
					${d.parkings.length ? d.parkings.map((r) => {
						const full = r.capacity ? Math.min(100, (r.count / r.capacity) * 100) : 0;
						return `<a class="iran-dash-park" data-route='${esc(JSON.stringify(["List", "Iran Vehicle", { parking: r.parking || "" }]))}'>
							<div class="top"><span>${esc(r.parking || __("No parking set"))}</span>
							<b>${r.capacity ? __("{0} of {1}", [num(r.count), num(r.capacity)]) : num(r.count)}</b></div>
							${r.capacity ? `<span class="bar ${full >= 90 ? "full" : ""}"><i style="width:${full}%"></i></span>` : ""}
						</a>`;
					}).join("") : `<div class="text-muted">—</div>`}
				</div>
				<div class="iran-dash-box">
					<div class="iran-dash-title">${__("Latest Events")}</div>
					<div class="iran-dash-timeline">
					${d.events.length ? d.events.map((e) => `
						<a class="iran-dash-event" data-route='${esc(JSON.stringify(["Form", "Iran Vehicle", e.parent]))}'>
							<b>${esc(e.event)}</b>
							<span>${esc(e.title || e.parent)}</span>
							<small>${frappe.datetime.comment_when(e.date)}</small>
						</a>`).join("") : `<div class="text-muted">—</div>`}
					</div>
				</div>
			</div>`);
		draw();
	};

	// ------------------------------------------------------------ the money chart

	const draw = () => {
		const d = state.data;
		const $chart = $body.find(".iran-dash-chart");
		if (!d || !$chart.length) return;
		const keys = IRAN_DASH_SERIES.map(([k]) => k).filter((k) => state.shown.includes(k));
		const labels = d.months.labels;
		const label_of = (key) => __(IRAN_DASH_SERIES.find(([k]) => k === key)[1]);
		if (!keys.length) {
			$chart.html(`<div class="iran-dash-empty">${__("Tick at least one item to see it on the chart.")}</div>`);
			return;
		}
		if (state.table) {
			$chart.html(`<div class="iran-dash-table"><table>
				<thead><tr><th>${__("Month")}</th>${keys.map((k) => `<th>${esc(label_of(k))}</th>`).join("")}</tr></thead>
				<tbody>${labels.map((l, i) => `<tr><td>${esc(digits(l))}</td>${keys
					.map((k) => `<td>${money(d.months.series[k][i])}</td>`).join("")}</tr>`).reverse().join("")}</tbody>
			</table></div>`);
			return;
		}
		const width = Math.max(320, $chart.width());
		const height = 300;
		const pad = { top: 16, right: state.kind === "line" && keys.length <= 4 ? 96 : 16, bottom: 34, left: 76 };
		const plot_w = width - pad.left - pad.right;
		const plot_h = height - pad.top - pad.bottom;
		const values = keys.flatMap((k) => d.months.series[k]);
		let lo = Math.min(0, ...values);
		let hi = Math.max(0, ...values);
		if (lo === hi) hi = lo + 1;
		const raw = (hi - lo) / 4;
		const mag = Math.pow(10, Math.floor(Math.log10(raw)));
		const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
		lo = Math.floor(lo / step) * step;
		hi = Math.ceil(hi / step) * step;
		const y = (v) => pad.top + plot_h - ((v - lo) / (hi - lo)) * plot_h;
		const band = plot_w / labels.length;
		const x = (i) => pad.left + band * i + band / 2;
		const svg = [];
		for (let v = lo; v <= hi + step / 2; v += step) {
			svg.push(`<line class="${Math.abs(v) < step / 1e6 ? "zero" : "grid"}" x1="${pad.left}" x2="${width - pad.right}" y1="${y(v)}" y2="${y(v)}"/>`);
			svg.push(`<text class="axis" x="${pad.left - 8}" y="${y(v) + 4}" text-anchor="end">${esc(short(v))}</text>`);
		}
		// The hovered month, drawn under the marks so they keep their colour
		svg.push(`<rect class="band" x="0" y="${pad.top}" width="${band}" height="${plot_h}" visibility="hidden"/>`);
		const every = Math.ceil(labels.length / Math.max(1, Math.floor(plot_w / 70)));
		labels.forEach((l, i) => {
			if ((labels.length - 1 - i) % every) return;
			svg.push(`<text class="axis" x="${x(i)}" y="${height - 10}" text-anchor="middle">${esc(digits(l.split(" ")[0]))}</text>`);
		});
		if (state.kind === "bar") {
			const group = Math.min(band * 0.72, keys.length * 26);
			const bar_w = Math.max(2, (group - (keys.length - 1) * 2) / keys.length);
			labels.forEach((_l, i) => {
				keys.forEach((k, j) => {
					const v = d.months.series[k][i];
					if (!v) return;
					const left = x(i) - group / 2 + j * (bar_w + 2);
					const top = Math.min(y(v), y(0));
					const h = Math.max(1, Math.abs(y(v) - y(0)));
					const r = Math.min(4, bar_w / 2, h);
					// Rounded only at the data end, square on the baseline
					const path = v >= 0
						? `M${left},${top + h} V${top + r} Q${left},${top} ${left + r},${top} H${left + bar_w - r} Q${left + bar_w},${top} ${left + bar_w},${top + r} V${top + h} Z`
						: `M${left},${top} V${top + h - r} Q${left},${top + h} ${left + r},${top + h} H${left + bar_w - r} Q${left + bar_w},${top + h} ${left + bar_w},${top + h - r} V${top} Z`;
					svg.push(`<path class="mark" d="${path}" fill="${color(k)}"/>`);
				});
			});
		} else {
			keys.forEach((k) => {
				const pts = d.months.series[k].map((v, i) => `${x(i)},${y(v)}`);
				svg.push(`<polyline class="line" points="${pts.join(" ")}" stroke="${color(k)}"/>`);
				d.months.series[k].forEach((v, i) => svg.push(`<circle class="dot" cx="${x(i)}" cy="${y(v)}" r="4" fill="${color(k)}"/>`));
			});
			if (keys.length <= 4) {
				// Direct labels at the line ends, nudged apart so they do not overlap
				const ends = keys.map((k) => ({ k, y: y(d.months.series[k][labels.length - 1]) })).sort((a, b) => a.y - b.y);
				ends.forEach((e, i) => { if (i && e.y - ends[i - 1].y < 14) e.y = ends[i - 1].y + 14; });
				ends.forEach((e) => svg.push(`<text class="end" x="${x(labels.length - 1) + 10}" y="${e.y + 4}">${esc(label_of(e.k))}</text>`));
			}
		}
		svg.push(`<line class="cross" x1="0" x2="0" y1="${pad.top}" y2="${pad.top + plot_h}" visibility="hidden"/>`);
		labels.forEach((_l, i) => svg.push(`<rect class="hit" data-i="${i}" x="${pad.left + band * i}" y="${pad.top}" width="${band}" height="${plot_h}" tabindex="0"/>`));
		$chart.html(`<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(__("Profit, Costs and Sales by Month"))}">${svg.join("")}</svg>`);

		const $tip = $body.find(".iran-dash-tooltip");
		const show = (target) => {
			const i = +target.dataset.i;
			$chart.find(".cross").attr({ x1: x(i), x2: x(i), visibility: "visible" });
			$chart.find(".band").attr({ x: pad.left + band * i, visibility: "visible" });
			const tip = $tip[0];
			tip.textContent = "";
			const head = document.createElement("div");
			head.className = "head";
			head.textContent = digits(labels[i]);
			tip.appendChild(head);
			keys.forEach((k) => {
				const row = document.createElement("div");
				row.className = "row";
				const key = document.createElement("i");
				key.style.background = color(k);
				const value = document.createElement("b");
				value.innerHTML = money(d.months.series[k][i]);
				const name = document.createElement("span");
				name.textContent = label_of(k);
				row.append(key, value, name);
				tip.appendChild(row);
			});
			tip.hidden = false;
			const box = $chart[0].getBoundingClientRect();
			const host = $body.find(".iran-dash-money")[0].getBoundingClientRect();
			const left = box.left - host.left + x(i) + 14;
			tip.style.top = `${box.top - host.top + pad.top}px`;
			tip.style.left = `${left + tip.offsetWidth > host.width ? left - tip.offsetWidth - 28 : left}px`;
		};
		const hide = () => {
			$tip[0].hidden = true;
			$chart.find(".cross, .band").attr("visibility", "hidden");
		};
		$chart.find(".hit").on("pointermove focus", (e) => show(e.currentTarget)).on("pointerleave blur", hide);
	};

	$body.on("change", "[data-series]", (e) => {
		const key = e.currentTarget.dataset.series;
		state.shown = e.currentTarget.checked ? [...state.shown, key] : state.shown.filter((k) => k !== key);
		store.set("series", state.shown);
		$(e.currentTarget).closest(".iran-dash-chip").toggleClass("on", e.currentTarget.checked);
		draw();
	});
	$body.on("click", "[data-kind]", (e) => {
		state.kind = e.currentTarget.dataset.kind;
		state.table = false;
		store.set("kind", state.kind);
		$body.find(".iran-dash-switch button").removeClass("on");
		$(e.currentTarget).addClass("on");
		draw();
	});
	$body.on("click", "[data-table]", (e) => {
		state.table = !state.table;
		$(e.currentTarget).toggleClass("on", state.table);
		draw();
	});
	$body.on("click", "[data-cars]", (e) => {
		e.preventDefault();
		show_cars(JSON.parse(e.currentTarget.getAttribute("data-cars")));
	});
	$body.on("click", "[data-route]", (e) => {
		e.preventDefault();
		const route = JSON.parse(e.currentTarget.dataset.route);
		if (route[0] === "List" && route[2]) {
			frappe.route_options = route[2];
			frappe.set_route("List", route[1]);
		} else {
			frappe.set_route(...route);
		}
	});

	const load = async () => {
		$body.addClass("loading");
		const d = await frappe.xcall("iran_erp.iran_dealership.dashboard.get_dashboard", {
			branch: state.branch,
			months: state.months,
		});
		$body.removeClass("loading");
		state.data = d;
		if (d.is_general && !page.branch_field) {
			page.branch_field = page.add_field({
				fieldtype: "Link",
				options: "Branch",
				label: __("Branch"),
				fieldname: "branch",
				change() {
					state.branch = this.get_value() || null;
					load();
				},
			});
		}
		page.set_title(d.trade_name || __("Car Dealership"));
		render(d);
	};
	page.set_secondary_action(__("Refresh"), load, "refresh-cw");
	let resize;
	$(window).on("resize", () => {
		clearTimeout(resize);
		resize = setTimeout(draw, 150);
	});
	load();
	$(wrapper).on("show", () => state.data && load());
};
