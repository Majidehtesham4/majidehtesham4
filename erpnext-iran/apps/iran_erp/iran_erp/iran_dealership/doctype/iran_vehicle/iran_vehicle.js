// Copyright (c) 2026, Majid Ehtesham and contributors

// The car's body seen from above, front at the top: each part a shape that can be clicked
const IRAN_CAR_PARTS = [
	["front_bumper", "rect", { x: 70, y: 8, width: 160, height: 26, rx: 13 }],
	["hood", "rect", { x: 72, y: 40, width: 156, height: 92, rx: 12 }],
	["front_left_fender", "rect", { x: 22, y: 44, width: 44, height: 92, rx: 12 }],
	["front_right_fender", "rect", { x: 234, y: 44, width: 44, height: 92, rx: 12 }],
	["windshield", "path", { d: "M80 138 H220 L208 172 H92 Z" }],
	["front_left_door", "rect", { x: 22, y: 142, width: 44, height: 94, rx: 6 }],
	["front_right_door", "rect", { x: 234, y: 142, width: 44, height: 94, rx: 6 }],
	["roof", "rect", { x: 92, y: 178, width: 116, height: 150, rx: 10 }],
	["rear_left_door", "rect", { x: 22, y: 240, width: 44, height: 94, rx: 6 }],
	["rear_right_door", "rect", { x: 234, y: 240, width: 44, height: 94, rx: 6 }],
	["left_sill", "rect", { x: 6, y: 142, width: 12, height: 192, rx: 5 }],
	["right_sill", "rect", { x: 282, y: 142, width: 12, height: 192, rx: 5 }],
	["rear_glass", "path", { d: "M92 334 H208 L220 364 H80 Z" }],
	["rear_left_fender", "rect", { x: 22, y: 340, width: 44, height: 92, rx: 12 }],
	["rear_right_fender", "rect", { x: 234, y: 340, width: 44, height: 92, rx: 12 }],
	["trunk", "rect", { x: 72, y: 370, width: 156, height: 72, rx: 12 }],
	["rear_bumper", "rect", { x: 70, y: 448, width: 160, height: 26, rx: 13 }],
];

// Iranian cars carry a Jalali model year, imported ones a Gregorian year
function iran_vehicle_year_hint(frm) {
	const imported = frm.doc.made_in === "Imported Car";
	frm.set_df_property(
		"year",
		"description",
		imported ? __("Gregorian year of an imported car, for example 2024") : __("Jalali year of a car made in Iran, for example 1403")
	);
}

// The model's technical specifications, kept in the list of car models, shown under the model
function iran_vehicle_specs(frm) {
	// Kept as the field's content: the form redraws HTML fields from it on every refresh
	const show = (html) => {
		frm.set_df_property("specs_html", "options", html);
		frm.refresh_field("specs_html");
	};
	if (!frm.doc.car_model) {
		show("");
		return;
	}
	frappe
		.xcall("iran_erp.iran_dealership.doctype.iran_car_model.iran_car_model.get_specs", { model: frm.doc.car_model })
		.then(({ rows, features }) => {
			const esc = frappe.utils.escape_html;
			if (!rows.length && !features.length) {
				show(
					`<div class="iran-specs empty">${__("No specifications are written for this model yet.")}
					<a href="/desk/iran-car-model/${encodeURIComponent(frm.doc.car_model)}">${__("Write them once for the model")}</a></div>`
				);
				return;
			}
			show(`<div class="iran-specs">
				<div class="iran-specs-title">${__("Technical Specifications")}</div>
				<div class="iran-specs-grid">${rows
					.map((r) => `<div><span>${esc(r.label)}</span><b>${esc(r.value)}</b></div>`)
					.join("")}</div>
				${features.length ? `<div class="iran-specs-features">${features.map((f) => `<span>${esc(f)}</span>`).join("")}</div>` : ""}
			</div>`);
		});
}

frappe.ui.form.on("Iran Vehicle", {
	car_model(frm) {
		iran_vehicle_specs(frm);
	},

	// Fetched from the car model when one is chosen
	made_in(frm) {
		iran_vehicle_year_hint(frm);
	},

	setup(frm) {
		const cash = () => ({ filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] } });
		frm.set_query("paid_from", cash);
		frm.set_query("paid_from", "costs", cash);
		frm.set_query("car_model", () => ({ filters: { disabled: 0 } }));
		frm.set_query("color", () => ({ filters: { disabled: 0 } }));
		frm.set_query("parking", () => ({ filters: { disabled: 0, ...(frm.doc.branch ? { branch: ["in", [frm.doc.branch, ""]] } : {}) } }));
		frm.set_query("service", "costs", () => ({ filters: { disabled: 0 } }));
		frm.set_query("investment_contract", () => ({ filters: { investor: frm.doc.investor, docstatus: 1 } }));
	},

	onload(frm) {
		if (!frm.is_new()) return;
		if (!frm.doc.company) frm.set_value("company", frappe.defaults.get_user_default("Company"));
		// The branch of whoever registers the car
		frappe.db.get_value("User", frappe.session.user, "iran_branch").then(({ message }) => {
			if (message && message.iran_branch && !frm.doc.branch) frm.set_value("branch", message.iran_branch);
		});
		if (!(frm.doc.inspection || []).length) {
			frappe.xcall("iran_erp.iran_dealership.doctype.iran_vehicle.iran_vehicle.get_inspection_items").then((items) => {
				items.forEach((item) => frm.add_child("inspection", { item: item.name, section: item.section, measure: item.measure }));
				frm.refresh_field("inspection");
			});
		}
	},

	refresh(frm) {
		const admin = frappe.user.has_role("System Manager");
		frm.set_df_property("branch", "read_only", admin ? 0 : 1);
		iran_vehicle_year_hint(frm);
		iran_vehicle_specs(frm);
		iran_erp.plate.editor(frm);
		iran_vehicle_body.render(frm);
		if (frm.is_new()) return;

		// Prices, costs, owners and sales are for those who may see the books (not reception)
		const books = Boolean(frm.perm[1] && frm.perm[1].read);
		if (frm.doc.show_on_website && ["In Preparation", "Ready for Sale", "Reserved"].includes(frm.doc.status)) {
			frm.add_custom_button(__("See on the Website"), () => window.open(`/cars/${frm.doc.name}`, "_blank"));
		}
		if (!books) {
			const days = frappe.datetime.get_day_diff(frappe.datetime.get_today(), frm.doc.entry_date);
			if (frm.doc.entry_date) frm.set_intro(__("{0} days in the lot", [days]), "blue");
			return;
		}

		const intro = [];
		if (frm.doc.total_cost) intro.push(__("Total cost of the car: {0}", [iran_erp.money.format(frm.doc.total_cost)]));
		if (frm.doc.profit) intro.push(__("Profit on the car: {0}", [iran_erp.money.format(frm.doc.profit)]));
		const days = frappe.datetime.get_day_diff(frm.doc.exit_date || frappe.datetime.get_today(), frm.doc.entry_date);
		if (frm.doc.entry_date) intro.push(__("{0} days in the lot", [days]));
		if (intro.length) frm.set_intro(intro.join(" — "), "blue");

		if (["In Preparation", "Ready for Sale", "Reserved"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Sell in Instalments"), () =>
				frappe.new_doc("Iran Instalment Sale", {
					vehicle: frm.doc.name,
					company: frm.doc.company,
					branch: frm.doc.branch,
					sale_price: frm.doc.asking_price,
				})
			);
		}
		if (["In Preparation", "Ready for Sale"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Reserve"), () => {
				frappe.prompt(
					[
						{ fieldname: "customer", fieldtype: "Link", options: "Customer", label: __("Customer") },
						{ fieldname: "note", fieldtype: "Data", label: __("Note") },
					],
					(v) => frm.call("reserve", v).then(() => frm.reload_doc()),
					__("Reserve"),
					__("Reserve")
				);
			});
		}
		if (frm.doc.status === "Reserved") {
			frm.add_custom_button(__("Cancel Reservation"), () => frm.call("unreserve").then(() => frm.reload_doc()));
		}
		if (frm.doc.status === "Sold") {
			frm.add_custom_button(__("Car Leaves the Lot"), () => {
				frappe.prompt(
					[
						{ fieldname: "date", fieldtype: "Date", label: __("Exit Date"), default: frappe.datetime.get_today(), reqd: 1 },
						{ fieldname: "delivered_to", fieldtype: "Data", label: __("Delivered To") },
					],
					(v) => frm.call("record_exit", v).then(() => frm.reload_doc()),
					__("Car Leaves the Lot"),
					__("Save")
				);
			});
		}
		frm.add_custom_button(__("Add Service or Cost"), () => {
			frm.scroll_to_field("costs");
			const row = frm.add_child("costs", { date: frappe.datetime.get_today(), status: "Done" });
			frm.refresh_field("costs");
			frm.fields_dict.costs.grid.get_row(row.name).toggle_view(true);
		});
	},

	ownership(frm) {
		iran_vehicle_body.render(frm);
	},

	owner_customer(frm) {
		if (!frm.doc.owner_customer) return;
		frappe.db.get_value("Customer", frm.doc.owner_customer, ["mobile_no", "iran_national_id"]).then(({ message }) => {
			if (message.mobile_no && !frm.doc.owner_mobile) frm.set_value("owner_mobile", message.mobile_no);
			if (message.iran_national_id && !frm.doc.owner_national_id) frm.set_value("owner_national_id", message.iran_national_id);
		});
	},

	investor(frm) {
		frm.set_value("investment_contract", null);
	},
});

frappe.ui.form.on("Iran Vehicle Cost", {
	service(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.service) return;
		frappe.db.get_value("Iran Vehicle Service", row.service, ["category", "default_amount", "asks_scope"]).then(({ message }) => {
			frappe.model.set_value(cdt, cdn, "category", message.category);
			if (message.default_amount && !row.amount) frappe.model.set_value(cdt, cdn, "amount", message.default_amount);
			if (!message.asks_scope) frappe.model.set_value(cdt, cdn, "scope", "Whole Car");
		});
	},
});

// The body diagram: parts coloured by what was found on them; a click opens the part
const iran_vehicle_body = {
	options: null,

	async load() {
		if (!this.options) {
			this.options = await frappe.xcall("iran_erp.iran_dealership.doctype.iran_vehicle.iran_vehicle.get_body_options");
		}
		return this.options;
	},

	async render(frm) {
		const field = frm.fields_dict.body_diagram;
		if (!field) return;
		const { parts, conditions } = await this.load();
		const esc = frappe.utils.escape_html;
		const by_key = Object.fromEntries(parts.filter((p) => p.diagram_key).map((p) => [p.diagram_key, p.name]));
		const colors = Object.fromEntries(conditions.map((c) => [c.name, c.color_code || "#7c3aed"]));
		const marks = {};
		(frm.doc.body_marks || []).forEach((m) => (marks[m.body_part] = marks[m.body_part] || []).push(m));

		const shapes = IRAN_CAR_PARTS.map(([key, tag, attrs]) => {
			const part = by_key[key];
			if (!part) return "";
			const found = marks[part] || [];
			const fill = found.length ? colors[found[0].condition] : "var(--control-bg, #f3f4f6)";
			const attr = Object.entries(attrs).map(([k, v]) => `${k}="${v}"`).join(" ");
			const title = esc(part + (found.length ? ": " + found.map((m) => m.condition).join("، ") : ""));
			return `<${tag} ${attr} class="iran-body-part ${found.length ? "marked" : ""}" data-part="${esc(part)}" fill="${fill}"><title>${title}</title></${tag}>`;
		}).join("");
		const labels = IRAN_CAR_PARTS.map(([key, , attrs]) => {
			const part = by_key[key];
			const found = part && marks[part];
			if (!found || !found.length) return "";
			const x = attrs.x !== undefined ? attrs.x + attrs.width / 2 : 150;
			const y = attrs.y !== undefined ? attrs.y + attrs.height / 2 : key === "windshield" ? 156 : 350;
			return `<text x="${x}" y="${y + 4}" class="iran-body-count">${found.length}</text>`;
		}).join("");
		const extra = parts
			.filter((p) => !p.diagram_key)
			.map((p) => {
				const found = marks[p.name] || [];
				const style = found.length ? `style="background:${colors[found[0].condition]};color:#fff"` : "";
				return `<button type="button" class="btn btn-xs btn-default iran-body-chip" data-part="${esc(p.name)}" ${style}>${esc(p.name)}${found.length ? " (" + found.length + ")" : ""}</button>`;
			})
			.join(" ");
		const legend = conditions
			.map((c) => `<span class="iran-body-legend"><i style="background:${c.color_code || "#7c3aed"}"></i>${esc(c.name)}</span>`)
			.join("");
		const list = (frm.doc.body_marks || [])
			.map((m) => `<li><b>${esc(m.body_part)}</b>: ${esc(m.condition)}${m.description ? " — " + esc(m.description) : ""}</li>`)
			.join("");

		field.$wrapper.html(`
			<div class="iran-body" dir="rtl">
				<div class="iran-body-figure">
					<div class="text-muted small text-center">${__("Front")}</div>
					<svg viewBox="0 0 300 482" class="iran-body-svg">${shapes}${labels}</svg>
					<div class="text-muted small text-center">${__("Rear")}</div>
				</div>
				<div class="iran-body-side">
					<p class="text-muted">${__("Click a part of the car to record what was found on it.")}</p>
					<div class="iran-body-legends">${legend}</div>
					<div class="iran-body-extra">${extra}</div>
					${list ? `<ul class="iran-body-list">${list}</ul>` : `<p class="text-success">${__("Body without marks")}</p>`}
				</div>
			</div>`);
		field.$wrapper.find("[data-part]").on("click", (e) => this.edit(frm, e.currentTarget.dataset.part));
	},

	clear(frm, part) {
		(frm.doc.body_marks || [])
			.filter((m) => m.body_part === part)
			.forEach((m) => frappe.model.clear_doc(m.doctype, m.name));
		(frm.doc.body_marks || []).forEach((m, i) => (m.idx = i + 1));
	},

	edit(frm, part) {
		if (frm.doc.docstatus === 2) return;
		const { conditions } = this.options;
		const existing = (frm.doc.body_marks || []).filter((m) => m.body_part === part);
		const notes = existing.map((m) => m.description).filter(Boolean).join("، ");
		const d = new frappe.ui.Dialog({
			title: part,
			fields: [
				{
					fieldname: "conditions",
					fieldtype: "MultiCheck",
					label: __("What was found"),
					columns: 2,
					options: conditions.map((c) => ({
						label: c.name,
						value: c.name,
						checked: existing.some((m) => m.condition === c.name),
					})),
				},
				{ fieldname: "description", fieldtype: "Small Text", label: __("Description"), default: notes },
			],
			primary_action_label: __("Save"),
			primary_action: (values) => {
				this.clear(frm, part);
				(values.conditions || []).forEach((condition) =>
					frm.add_child("body_marks", { body_part: part, condition, description: values.description || "" })
				);
				frm.refresh_field("body_marks");
				frm.dirty();
				d.hide();
				this.render(frm);
			},
			secondary_action_label: existing.length ? __("Part Is Sound") : undefined,
			secondary_action: existing.length
				? () => {
						this.clear(frm, part);
						frm.refresh_field("body_marks");
						frm.dirty();
						d.hide();
						this.render(frm);
					}
				: undefined,
		});
		d.show();
	},
};

frappe.ui.form.on("Iran Vehicle Body Mark", {
	body_marks_remove: (frm) => iran_vehicle_body.render(frm),
	condition: (frm) => iran_vehicle_body.render(frm),
});
