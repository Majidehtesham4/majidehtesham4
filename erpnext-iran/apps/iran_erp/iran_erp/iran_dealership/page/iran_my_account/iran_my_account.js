// «حساب من»: an investor's own account — what they put in, the profit earned to date and to come,
// month by month on a chart, their cheques, the cars bought with their money and their statement.
// An investor sees only their own account; staff choose the investor.

frappe.pages["iran-my-account"].on_page_load = function (wrapper) {
	const trade = frappe.boot.iran_trade_name;
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: trade ? `${__("My Account")} — ${trade}` : __("My Account"),
		single_column: true,
	});
	const state = { investor: (frappe.route_options && frappe.route_options.investor) || null, tab: "contracts" };
	frappe.route_options = null;
	const $body = $(`<div class="iran-investor" dir="rtl"></div>`).appendTo(page.main);
	const esc = frappe.utils.escape_html;
	const fa = (v) => iran_erp.to_persian_digits(String(v ?? ""));
	const money = (v) => iran_erp.money.format(v || 0);
	const date = (v) => (v ? iran_erp.to_jalali(v) : "—");
	const STATUS = {
		Active: ["فعال", "blue"],
		Matured: ["سررسید شده", "orange"],
		Settled: ["تسویه شده", "green"],
		Pending: ["در انتظار", "gray"],
		Paid: ["پرداخت شده", "green"],
		Reinvested: ["سرمایه‌گذاری مجدد", "purple"],
		Issued: ["صادر شده", "blue"],
		Cleared: ["پاس شده", "green"],
		Returned: ["برگشتی", "red"],
		Bounced: ["برگشت خورده", "red"],
		Cancelled: ["باطل شده", "gray"],
	};
	const KIND = { Profit: "سود", Principal: "اصل سرمایه", "Profit and Principal": "سود و بخشی از اصل" };
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

	const card = (label, value, sub = "", tone = "") =>
		`<div class="iran-investor-card ${tone}"><div class="label">${label}</div><div class="value">${value}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;

	const render = (investor) => {
		if (!investor) {
			$body.html(`<div class="iran-investor-empty">هنوز سرمایه‌گذاری ثبت نشده است.</div>`);
			return;
		}
		state.data = investor;
		const t = investor.totals;
		const next = investor.next_payment;
		const today = iran_erp.to_jalali(frappe.datetime.nowdate());
		$body.html(`
			<div class="iran-investor-hero">
				<div>
					<div class="name">${esc(investor.full_name)}</div>
					<div class="sub">${esc(trade || "")} — ${today}</div>
				</div>
				<div class="owed">
					<span>باقی‌مانده‌ی طلب شما (سود و اصل)</span>
					<b>${money(t.remaining)}</b>
				</div>
			</div>
			<div class="iran-investor-cards">
				${card("سرمایه‌ی فعال", money(t.invested), t.annual_rate ? `سود سالانه حدود ${fa(t.annual_rate)}٪` : "")}
				${card("سود تا امروز (روزشمار)", money(t.earned), `از ${money(t.profit_promised)} سود قراردادها`, "accent")}
				${card("دریافت شده تا امروز", money(t.paid), `سود دریافتی: ${money(t.profit_received)}`)}
				${card("پرداخت‌های آینده", money(t.upcoming))}
			</div>
			${next ? `<div class="iran-investor-next">
				<span>پرداخت بعدی:</span> <b>${date(next.due_date)}</b> — <b>${money(next.amount)}</b>
				(${KIND[next.kind] || ""})${next.cheque_number ? ` — چک شماره‌ی <b>${fa(esc(next.cheque_number))}</b>` : ""}
			</div>` : ""}
			<div class="iran-investor-box">
				<div class="title">سود و پرداخت‌ها، ماه به ماه</div>
				<div class="iran-investor-chart"></div>
			</div>
			<div class="iran-investor-tabs">
				${[
					["contracts", `قراردادها (${fa(investor.contracts.length)})`],
					["cheques", `چک‌ها (${fa(investor.cheques.length)})`],
					["cars", `خودروها (${fa(investor.cars.length)})`],
					["statement", "گردش حساب"],
				].map(([key, label]) => `<button data-tab="${key}" class="${state.tab === key ? "on" : ""}">${label}</button>`).join("")}
			</div>
			<div class="iran-investor-tab"></div>`);
		draw_chart(investor.chart);
		render_tab();
	};

	const draw_chart = (chart) => {
		const $chart = $body.find(".iran-investor-chart");
		if (!chart.labels.length) {
			$chart.html(`<div class="text-muted">—</div>`);
			return;
		}
		new frappe.Chart($chart[0], {
			type: "bar",
			height: 260,
			data: {
				labels: chart.labels.map(fa),
				datasets: [
					{ name: "سود به‌دست‌آمده در ماه", values: chart.earned },
					{ name: "دریافت شده", values: chart.paid },
					{ name: "در راه (پرداخت‌های آینده)", values: chart.pending },
				],
			},
			colors: ["#e87ba4", "#1baf7a", "#2a78d6"],
			barOptions: { spaceRatio: 0.35 },
			axisOptions: { xIsSeries: 1, shortenYAxisNumbers: 1 },
			tooltipOptions: { formatTooltipY: (v) => money(v) },
		});
	};

	const render_tab = () => {
		const investor = state.data;
		const $tab = $body.find(".iran-investor-tab");
		$body.find("[data-tab]").removeClass("on").filter(`[data-tab=${state.tab}]`).addClass("on");
		if (state.tab === "contracts") $tab.html(contracts_html(investor.contracts));
		if (state.tab === "cheques") $tab.html(cheques_html(investor.cheques));
		if (state.tab === "cars") $tab.html(cars_html(investor.cars));
		if (state.tab === "statement") $tab.html(statement_html(investor.statement));
	};

	const contracts_html = (contracts) => {
		if (!contracts.length) return `<div class="iran-investor-empty">قراردادی ثبت نشده است.</div>`;
		return contracts.map((c) => {
			const kind = c.type === "Car Remittance" ? "خرید حواله خودرو" : "مشارکت";
			const terms =
				c.type === "Car Remittance"
					? `${c.vehicle ? esc(c.vehicle) + " — " : ""}${c.settlement_amount ? "سهم شما از فروش: " + money(c.settlement_amount) : "در انتظار فروش"}`
					: `${fa(c.months)} ماه، سود ماهانه ${fa(c.monthly_rate)}٪ — کل سود ${money(c.total_profit)}`;
			const done = c.payments.filter((p) => p.status !== "Pending").length;
			const progress = c.payments.length ? Math.round((done / c.payments.length) * 100) : 0;
			return `<div class="iran-investor-contract">
				<div class="head">
					<div><b>${kind}</b> ${pill(c.status)} <span class="text-muted">${esc(c.name)}</span>
						${c.parent_contract ? `<span class="text-muted">— ادامه‌ی ${esc(c.parent_contract)}</span>` : ""}</div>
					<div class="amount">${money(c.amount)}</div>
				</div>
				<div class="text-muted small">${date(c.start_date)} تا ${date(c.end_date)} — ${terms}</div>
				${c.type === "Partnership" ? `<div class="earned">سود تا امروز: <b>${money(c.accrued_profit)}</b></div>` : ""}
				<div class="iran-investor-progress" title="${fa(done)} از ${fa(c.payments.length)} پرداخت"><i style="width:${progress}%"></i></div>
				<table class="table table-sm iran-investor-table">
					<thead><tr><th>سررسید</th><th>نوع</th><th>مبلغ</th><th>چک</th><th>وضعیت</th></tr></thead>
					<tbody>${c.payments.map((p) => `<tr>
						<td>${date(p.due_date)}</td>
						<td>${KIND[p.kind] || ""}</td>
						<td>${money(p.amount)}</td>
						<td>${p.cheque_number ? fa(esc(p.cheque_number)) + ` <span class="text-muted">(${STATUS[p.cheque_status] ? STATUS[p.cheque_status][0] : __(p.cheque_status)})</span>` : "—"}</td>
						<td>${pill(p.status)}</td>
					</tr>`).join("")}</tbody>
				</table>
			</div>`;
		}).join("");
	};

	const cheques_html = (cheques) => {
		if (!cheques.length) return `<div class="iran-investor-empty">چکی برای شما صادر نشده است.</div>`;
		const total = (status) => cheques.filter((c) => c.status === status).reduce((s, c) => s + c.amount, 0);
		return `<div class="iran-investor-box">
			<div class="text-muted small">پاس شده: ${money(total("Cleared"))} — در دست شما (سررسید نشده یا پاس نشده): ${money(total("Issued"))}</div>
			<table class="table table-sm iran-investor-table">
				<thead><tr><th>شماره چک</th><th>شناسه صیادی</th><th>بانک</th><th>سررسید</th><th>مبلغ</th><th>بابت</th><th>وضعیت</th></tr></thead>
				<tbody>${cheques.map((c) => `<tr>
					<td>${fa(esc(c.cheque_number || ""))}</td>
					<td>${fa(esc(c.sayad_id || "—"))}</td>
					<td>${esc(c.bank || "")}</td>
					<td>${date(c.due_date)}</td>
					<td>${money(c.amount)}</td>
					<td>${KIND[c.kind] || ""}</td>
					<td>${pill(c.status)}</td>
				</tr>`).join("")}</tbody>
			</table></div>`;
	};

	const cars_html = (cars) => {
		if (!cars.length) return `<div class="iran-investor-empty">خودرویی با سرمایه‌ی شما خرید و فروش نشده است.</div>`;
		return `<div class="iran-investor-box"><table class="table table-sm iran-investor-table">
			<thead><tr><th>خودرو</th><th>پلاک</th><th>ورود</th><th>وضعیت</th><th>قیمت خرید</th><th>قیمت فروش</th><th>سود</th><th>روز در نمایشگاه</th></tr></thead>
			<tbody>${cars.map((c) => `<tr>
				<td>${esc(c.car_model || c.title)} <span class="text-muted">${fa(esc(c.year || ""))}</span></td>
				<td>${c.plate ? iran_erp.plate.html(c.plate) : ""}</td>
				<td>${date(c.entry_date)}</td>
				<td>${__(c.status)}${c.exit_date ? `<div class="text-muted small">${date(c.exit_date)}</div>` : ""}</td>
				<td>${money(c.purchase_price || c.total_cost)}</td>
				<td>${c.sold_price ? money(c.sold_price) : `<span class="text-muted">${money(c.asking_price)} (قیمت پیشنهادی)</span>`}</td>
				<td>${c.sold_price ? money(c.profit) : "—"}</td>
				<td>${fa(c.days)}</td>
			</tr>`).join("")}</tbody>
		</table></div>`;
	};

	const statement_html = (statement) => {
		if (!statement.rows.length) return `<div class="iran-investor-empty">گردشی ثبت نشده است.</div>`;
		return `<div class="iran-investor-box">
			<div class="text-muted small">چکی که به شما داده شده، همان روز صدورش «پرداخت به شما» ثبت می‌شود؛ چک‌های پاس‌نشده در زبانه‌ی «چک‌ها» هستند.</div>
			<table class="table table-sm iran-investor-table">
			<thead><tr><th>تاریخ</th><th>شرح</th><th>به نفع شما (واریز و سود)</th><th>پرداخت به شما (نقد یا چک)</th><th>مانده</th></tr></thead>
			<tbody>${statement.rows.map((r) => `<tr>
				<td>${date(r.date)}</td>
				<td>${fa(esc(r.description))}</td>
				<td>${r.in ? money(r.in) : ""}</td>
				<td>${r.out ? money(r.out) : ""}</td>
				<td><b>${money(r.balance)}</b></td>
			</tr>`).join("")}</tbody>
		</table></div>`;
	};

	$body.on("click", "[data-tab]", (e) => {
		state.tab = e.currentTarget.getAttribute("data-tab");
		render_tab();
	});
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
