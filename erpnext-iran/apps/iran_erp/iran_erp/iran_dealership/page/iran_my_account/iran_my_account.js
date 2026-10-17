// «حساب من»: an investor's contracts, the profit earned to date and the payments to come.
// An investor sees only their own account; staff choose the investor.

frappe.pages["iran-my-account"].on_page_load = function (wrapper) {
	const trade = frappe.boot.iran_trade_name;
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: trade ? `${__("My Account")} — ${trade}` : __("My Account"),
		single_column: true,
	});
	const state = { investor: (frappe.route_options && frappe.route_options.investor) || null };
	frappe.route_options = null;
	const $body = $(`<div class="iran-investor" dir="rtl"></div>`).appendTo(page.main);
	const esc = frappe.utils.escape_html;
	const money = (v) => iran_erp.money.format(v);
	const date = (v) => frappe.format(v, { fieldtype: "Date" });
	const STATUS = {
		Active: ["فعال", "blue"],
		Matured: ["سررسید شده", "orange"],
		Settled: ["تسویه شده", "green"],
		Pending: ["در انتظار", "gray"],
		Paid: ["پرداخت شده", "green"],
		Reinvested: ["سرمایه‌گذاری مجدد", "purple"],
	};
	const pill = (status) => {
		const [label, color] = STATUS[status] || [__(status), "gray"];
		return `<span class="indicator-pill ${color}">${label}</span>`;
	};

	const load = async () => {
		$body.html(`<div class="text-muted">${__("Loading…")}</div>`);
		let data;
		try {
			data = await frappe.xcall("iran_erp.business.investor_portal.get_my_account", { investor: state.investor });
		} catch (e) {
			$body.html(`<div class="iran-investor-empty">${__("No investor account is linked to your login. Ask the office to link it.")}</div>`);
			return;
		}
		if (data.staff && !page.investor_field) {
			page.investor_field = page.add_field({
				fieldtype: "Link",
				options: "Iran Investor",
				label: __("Investor"),
				fieldname: "investor",
				change() {
					state.investor = this.get_value() || null;
					load();
				},
			});
		}
		render(data.investors[0]);
	};

	const render = (investor) => {
		if (!investor) {
			$body.html(`<div class="iran-investor-empty">هنوز سرمایه‌گذاری ثبت نشده است.</div>`);
			return;
		}
		const t = investor.totals;
		let html = `
			<div class="iran-investor-hello">${esc(investor.full_name)}</div>
			<div class="iran-investor-cards">
				<div class="iran-investor-card"><div class="label">سرمایه‌ی فعال</div><div class="value">${money(t.invested)}</div></div>
				<div class="iran-investor-card accent"><div class="label">سود تا امروز (روزشمار)</div><div class="value">${money(t.earned)}</div></div>
				<div class="iran-investor-card"><div class="label">دریافت شده</div><div class="value">${money(t.paid)}</div></div>
				<div class="iran-investor-card"><div class="label">پرداخت‌های آینده</div><div class="value">${money(t.upcoming)}</div></div>
			</div>`;
		if (!investor.contracts.length) html += `<div class="iran-investor-empty">قراردادی ثبت نشده است.</div>`;
		for (const c of investor.contracts) {
			const kind = c.type === "Car Remittance" ? "خرید حواله خودرو" : "مشارکت";
			const terms =
				c.type === "Car Remittance"
					? `${c.vehicle ? esc(c.vehicle) + " — " : ""}${c.settlement_amount ? "سهم شما از فروش: " + money(c.settlement_amount) : "در انتظار فروش"}`
					: `${c.months} ماه، سود ماهانه ${c.monthly_rate}٪ — کل سود ${money(c.total_profit)}`;
			html += `
				<div class="iran-investor-contract">
					<div class="head">
						<div><b>${kind}</b> ${pill(c.status)} <span class="text-muted">${esc(c.name)}</span>
							${c.parent_contract ? `<span class="text-muted">— ادامه‌ی ${esc(c.parent_contract)}</span>` : ""}</div>
						<div class="amount">${money(c.amount)}</div>
					</div>
					<div class="text-muted small">${date(c.start_date)} تا ${date(c.end_date)} — ${terms}</div>
					${c.type === "Partnership" ? `<div class="earned">سود تا امروز: <b>${money(c.accrued_profit)}</b></div>` : ""}
					<table class="table table-sm iran-investor-table">
						<thead><tr><th>سررسید</th><th>نوع</th><th>مبلغ</th><th>چک</th><th>وضعیت</th></tr></thead>
						<tbody>${c.payments
							.map(
								(p) => `<tr>
									<td>${date(p.due_date)}</td>
									<td>${p.kind === "Profit" ? "سود" : "اصل سرمایه"}</td>
									<td>${money(p.amount)}</td>
									<td>${p.cheque_number ? esc(p.cheque_number) + " " + `<span class="text-muted">(${__(p.cheque_status)})</span>` : "—"}</td>
									<td>${pill(p.status)}</td>
								</tr>`
							)
							.join("")}</tbody>
					</table>
				</div>`;
		}
		$body.html(html);
	};

	page.set_secondary_action(__("Refresh"), load, "refresh-cw");
	load();
	// Opened again from another investor's form
	$(wrapper).on("show", () => {
		const chosen = frappe.route_options && frappe.route_options.investor;
		if (chosen && chosen !== state.investor) {
			state.investor = chosen;
			frappe.route_options = null;
			if (page.investor_field) page.investor_field.set_value(chosen);
			load();
		}
	});
};
