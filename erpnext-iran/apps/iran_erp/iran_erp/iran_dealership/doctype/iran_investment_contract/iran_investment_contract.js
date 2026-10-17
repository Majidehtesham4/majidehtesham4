// Copyright (c) 2026, Majid Ehtesham and contributors

const iran_cash_query = (frm) => () => ({
	filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] },
});

frappe.ui.form.on("Iran Investment Contract", {
	setup(frm) {
		frm.set_query("received_to", iran_cash_query(frm));
		frm.set_query("vehicle", () =>
			frm.doc.contract_type === "Car Remittance" ? { filters: { status: "Awaiting Delivery" } } : {}
		);
	},
	amount: (frm) => frm.events.calculate(frm),
	monthly_rate: (frm) => frm.events.calculate(frm),
	months: (frm) => frm.events.calculate(frm),
	calculate(frm) {
		const monthly = Math.round(flt(frm.doc.amount) * flt(frm.doc.monthly_rate) / 100);
		frm.set_value({ monthly_profit: monthly, total_profit: monthly * cint(frm.doc.months) });
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Investor's Account"), () => {
			frappe.route_options = { investor: frm.doc.investor };
			frappe.set_route("iran-my-account");
		});
		if (frm.doc.docstatus !== 1) return;
		frm.call("get_summary").then(({ message: s }) => {
			let intro = "";
			if (frm.doc.contract_type === "Partnership") {
				intro = __("Profit earned to date: {0} ({1} a day). Paid so far: {2}.", [
					iran_erp.money.format(s.accrued_profit),
					iran_erp.money.format(s.daily_profit),
					iran_erp.money.format(s.paid_profit),
				]);
			}
			if (s.reinvest_ready) {
				intro += " " + __("Cleared payments of {0} have reached the reinvestment threshold: a new contract can be made.", [
					iran_erp.money.format(s.cleared_not_reinvested),
				]);
			}
			if (s.chain.length > 1) {
				intro += " " + __("This contract is part of a chain of {0} contracts.", [s.chain.length]);
			}
			if (intro) frm.set_intro(intro, s.reinvest_ready ? "green" : "blue");
			frm.iran_summary = s;
		});
		if (["Settled", "Cancelled"].includes(frm.doc.status)) return;
		const group = __("Payments");
		if (frm.doc.schedule.some((r) => !r.cheque && r.status === "Pending")) {
			frm.add_custom_button(__("Issue Cheques"), () => issue_cheques(frm), group);
		}
		frm.add_custom_button(__("Paid by Transfer"), () => pay(frm), group);
		frm.add_custom_button(__("Reinvest"), () => reinvest(frm), group);
	},
});

function pending_options(frm, filter) {
	return frm.doc.schedule
		.filter((r) => r.status === "Pending" && (!filter || filter(r)))
		.map((r) => ({
			value: String(r.idx),
			label: `${r.kind === "Profit" ? "سود" : "اصل سرمایه"} — ${frappe.format(r.due_date, { fieldtype: "Date" })} — ${iran_erp.money.format(r.amount)}${r.cheque ? " (" + __("cheque") + ")" : ""}`,
		}));
}

function issue_cheques(frm) {
	const count = frm.doc.schedule.filter((r) => !r.cheque && r.status === "Pending").length;
	const d = new frappe.ui.Dialog({
		title: __("Issue Cheques"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__("{0} cheques are issued to the investor, one per payment, with their amounts and due dates.", [count])}</p>`,
			},
			{
				fieldname: "bank_account",
				fieldtype: "Link",
				options: "Account",
				label: __("Bank Account the Cheques Are Drawn On"),
				reqd: 1,
				get_query: () => ({ filters: { company: frm.doc.company, is_group: 0, account_type: "Bank" } }),
			},
			{ fieldname: "first_number", fieldtype: "Data", label: __("Number of the First Cheque"), reqd: 1 },
			{ fieldname: "sayad_ids", fieldtype: "Small Text", label: __("Sayad IDs (optional, one per line in order)") },
			{ fieldname: "posting_date", fieldtype: "Date", label: __("Date Given"), default: frm.doc.start_date },
		],
		primary_action_label: __("Issue"),
		primary_action(values) {
			frm.call("issue_cheques", values).then(({ message }) => {
				d.hide();
				frappe.show_alert({ message: __("{0} cheques issued", [message.length]), indicator: "green" });
				frm.reload_doc();
			});
		},
	});
	d.show();
}

function pay(frm) {
	const options = pending_options(frm, (r) => !r.cheque);
	if (!options.length) {
		frappe.msgprint(__("Every payment has a cheque; mark the cheque cleared when it is paid."));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: __("Paid by Transfer"),
		fields: [
			{ fieldname: "row", fieldtype: "Select", label: __("Payment"), options, reqd: 1 },
			{
				fieldname: "paid_from",
				fieldtype: "Link",
				options: "Account",
				label: __("Paid From"),
				reqd: 1,
				get_query: iran_cash_query(frm),
			},
			{ fieldname: "date", fieldtype: "Date", label: __("Date"), default: frappe.datetime.get_today() },
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			frm.call("pay", values).then(() => {
				d.hide();
				frm.reload_doc();
			});
		},
	});
	d.show();
}

function reinvest(frm) {
	const s = frm.iran_summary || {};
	const d = new frappe.ui.Dialog({
		title: __("Reinvest"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__("A new contract continues this one. Payments not yet made can be put back in (their cheques come back), and money from cleared cheques can be brought back in.")}</p>`,
			},
			{
				fieldname: "rows",
				fieldtype: "MultiCheck",
				label: __("Payments Put Back In"),
				options: pending_options(frm),
				columns: 1,
			},
			{
				fieldname: "cleared_amount",
				fieldtype: "Currency",
				label: __("Money from Cleared Cheques Brought Back"),
				default: s.reinvest_ready ? s.cleared_not_reinvested : 0,
			},
			{
				fieldname: "received_to",
				fieldtype: "Link",
				options: "Account",
				label: __("Brought Back Into"),
				depends_on: "eval:doc.cleared_amount > 0",
				get_query: iran_cash_query(frm),
			},
			{ fieldtype: "Section Break" },
			{ fieldname: "months", fieldtype: "Int", label: __("Months"), default: frm.doc.months },
			{ fieldname: "monthly_rate", fieldtype: "Percent", label: __("Monthly Profit Rate (%)"), default: frm.doc.monthly_rate },
			{
				fieldname: "profit_payment",
				fieldtype: "Select",
				label: __("Profit Paid"),
				options: [
					{ value: "Monthly", label: __("Monthly") },
					{ value: "At the End", label: __("At the End") },
				],
				default: frm.doc.profit_payment,
			},
		],
		primary_action_label: __("Make New Contract"),
		primary_action(values) {
			frm.call("reinvest", { ...values, rows: JSON.stringify(values.rows || []) }).then(({ message }) => {
				d.hide();
				frappe.set_route("Form", "Iran Investment Contract", message);
			});
		},
	});
	d.show();
}
