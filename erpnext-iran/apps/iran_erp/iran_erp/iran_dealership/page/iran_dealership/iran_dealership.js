// The dealership's home: the lot, the money of the coming days and the latest events.

frappe.pages["iran-dealership"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Car Dealership"), single_column: true });
	const $body = $(`<div class="iran-dash" dir="rtl"></div>`).appendTo(page.main);
	const esc = frappe.utils.escape_html;
	const money = (v) => iran_erp.money.format(v);
	const num = (v) => frappe.format(v || 0, { fieldtype: "Int" });
	const state = { branch: null };

	page.set_primary_action(__("New Car"), () => frappe.new_doc("Iran Vehicle"), "plus");
	page.add_inner_button(__("New Instalment Sale"), () => frappe.new_doc("Iran Instalment Sale"));
	page.add_inner_button(__("New Investment Contract"), () => frappe.new_doc("Iran Investment Contract"));

	const card = (label, value, sub, route, tone = "") => `
		<a class="iran-dash-card ${tone}" ${route ? `data-route='${esc(JSON.stringify(route))}'` : ""}>
			<div class="label">${label}</div>
			<div class="value">${value}</div>
			${sub ? `<div class="sub">${sub}</div>` : ""}
		</a>`;

	const load = async () => {
		const d = await frappe.xcall("iran_erp.iran_dealership.dashboard.get_dashboard", { branch: state.branch });
		if (d.is_admin && !page.branch_field) {
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
		const c = d.counts;
		const lot = ["List", "Iran Vehicle"];
		let html = `<div class="iran-dash-cards">
			${card(__("Cars in the Lot"), num(d.in_lot), __("Value of own cars: {0}", [money(d.stock_value)]), lot, "accent")}
			${card(__("Ready for Sale"), num(c["Ready for Sale"]), "", lot)}
			${card(__("In Preparation"), num(c["In Preparation"]), "", lot)}
			${card(__("Reserved"), num(c["Reserved"]), "", lot)}
			${card(__("Awaiting Delivery"), num(c["Awaiting Delivery"]), "", lot)}
			${card(__("Sold This Month"), num(d.sold_month), "", ["List", "Iran Instalment Sale"])}
		</div>
		<div class="iran-dash-cards">
			${card(__("Cheques to Receive This Week"), money(d.cheques_in.amount), __("{0} cheques", [num(d.cheques_in.count)]), ["List", "Iran Cheque"], "good")}
			${card(__("Cheques to Pay This Week"), money(d.cheques_out.amount), __("{0} cheques", [num(d.cheques_out.count)]), ["List", "Iran Cheque"], "warn")}
			${card(__("Overdue Instalments"), money(d.overdue.amount), __("{0} instalments", [num(d.overdue.count)]), ["query-report", "Overdue Instalments"], d.overdue.count ? "bad" : "")}
			${card(__("Due to Investors This Month"), money(d.investors_month), "", ["query-report", "Instalments and Investors Cash Forecast"])}
		</div>
		<div class="iran-dash-row">
			<div class="iran-dash-box">
				<div class="iran-dash-title">${__("Longest in the Lot")}</div>
				${d.oldest.length ? d.oldest.map((r) => `
					<a class="iran-dash-line" data-route='${esc(JSON.stringify(["Form", "Iran Vehicle", r.name]))}'>
						<span>${esc(r.title || r.name)}</span>
						<span class="text-muted">${__(r.status)} — ${__("{0} days", [num(r.days)])}</span>
					</a>`).join("") : `<div class="text-muted">${__("No cars in the lot")}</div>`}
			</div>
			<div class="iran-dash-box">
				<div class="iran-dash-title">${__("Cars by Parking")}</div>
				${d.parkings.length ? d.parkings.map((r) => `
					<div class="iran-dash-line"><span>${esc(r.parking || __("No parking set"))}</span><b>${num(r.count)}</b></div>`).join("") : `<div class="text-muted">—</div>`}
			</div>
			<div class="iran-dash-box wide">
				<div class="iran-dash-title">${__("Latest Events")}</div>
				${d.events.length ? d.events.map((e) => `
					<a class="iran-dash-line" data-route='${esc(JSON.stringify(["Form", "Iran Vehicle", e.parent]))}'>
						<span><b>${esc(e.event)}</b> — ${esc(e.title || e.parent)}</span>
						<span class="text-muted">${frappe.datetime.comment_when(e.date)}</span>
					</a>`).join("") : `<div class="text-muted">—</div>`}
			</div>
		</div>`;
		$body.html(html);
	};
	$body.on("click", "[data-route]", (e) => frappe.set_route(...JSON.parse(e.currentTarget.dataset.route)));
	page.set_secondary_action(__("Refresh"), load, "refresh-cw");
	load();
	$(wrapper).on("show", load);
};
