// Copyright (c) 2026, Majid Ehtesham and contributors

frappe.ui.form.on("Iran Instalment Sale", {
	setup(frm) {
		frm.set_query("down_payment_account", () => ({
			filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] },
		}));
		frm.set_query("vehicle", () => ({ filters: { status: ["in", ["In Preparation", "Ready for Sale", "Reserved"]] } }));
	},
	vehicle(frm) {
		if (!frm.doc.vehicle) return;
		frappe.db.get_value("Iran Vehicle", frm.doc.vehicle, ["asking_price", "title", "branch"]).then(({ message }) => {
			if (message.asking_price && !frm.doc.sale_price) frm.set_value("sale_price", message.asking_price);
			frm.set_value("description", message.title);
			if (message.branch) frm.set_value("branch", message.branch);
		});
	},
	sale_price: (frm) => frm.events.calculate(frm),
	down_payment: (frm) => frm.events.calculate(frm),
	other_costs: (frm) => frm.events.calculate(frm),
	monthly_rate: (frm) => frm.events.calculate(frm),
	months: (frm) => frm.events.calculate(frm),
	interval_months: (frm) => frm.events.calculate(frm),
	posting_date(frm) {
		if (!frm.doc.first_due_date && frm.doc.posting_date) {
			frm.set_value("first_due_date", frappe.datetime.add_months(frm.doc.posting_date, 1));
		}
	},
	// The totals while typing; saving makes the instalments
	calculate(frm) {
		const d = frm.doc;
		const months = cint(d.months);
		if (!months) return;
		const financed = flt(d.sale_price) - flt(d.down_payment) + flt(d.other_costs);
		const interest = Math.round(financed * flt(d.monthly_rate) / 100 * months * (cint(d.interval_months) || 1));
		const total = financed + interest;
		frm.set_value({
			financed_amount: financed,
			total_interest: interest,
			total_payable: total,
			instalment_amount: Math.floor(total / months / 1000) * 1000,
		});
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frm.call("get_summary").then(({ message: s }) => {
			let intro = __("Paid {0} of {1}; outstanding {2}.", [
				iran_erp.money.format(frm.doc.paid_total),
				iran_erp.money.format(frm.doc.total_payable),
				iran_erp.money.format(frm.doc.outstanding),
			]);
			if (s.overdue) intro += " " + __("{0} instalments are overdue.", [s.overdue]);
			if (s.late_fee_to_charge) intro += " " + __("Late fee not yet charged: {0}", [iran_erp.money.format(s.late_fee_to_charge)]);
			frm.set_intro(intro, s.overdue ? "red" : "blue");
			frm.iran_summary = s;
		});
		if (["Settled", "Cancelled"].includes(frm.doc.status)) return;
		const group = __("Instalments");
		if (frm.doc.schedule.some((r) => !r.cheque && ["Unpaid", "Overdue"].includes(r.status))) {
			frm.add_custom_button(__("Make Instalment Cheques"), () => make_cheques(frm), group);
		}
		frm.add_custom_button(__("Instalment Paid in Cash"), () => pay_row(frm), group);
		frm.add_custom_button(__("Charge Late Fee"), () =>
			frm.call("charge_late_fees").then(({ message }) => {
				frappe.show_alert({ message: __("Late fee charged: {0}", [iran_erp.money.format(message)]), indicator: "green" });
				frm.reload_doc();
			}), group);
		frm.add_custom_button(__("Early Settlement"), () => settle(frm), group);
		frm.add_custom_button(__("Overdue Instalments"), () =>
			frappe.set_route("query-report", "Overdue Instalments", { customer: frm.doc.customer })
		);
	},
});

function make_cheques(frm) {
	const open = frm.doc.schedule.filter((r) => !r.cheque && ["Unpaid", "Overdue"].includes(r.status));
	const d = new frappe.ui.Dialog({
		title: __("Make Instalment Cheques"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__("{0} cheques are made, one per instalment, with their amounts and due dates; the numbers go on from the first one.", [open.length])}</p>`,
			},
			{ fieldname: "bank", fieldtype: "Data", label: __("Bank"), reqd: 1 },
			{ fieldname: "branch_name", fieldtype: "Data", label: __("Branch of the Bank") },
			{ fieldname: "first_number", fieldtype: "Data", label: __("Number of the First Cheque"), reqd: 1 },
			{
				fieldname: "sayad_ids",
				fieldtype: "Small Text",
				label: __("Sayad IDs (optional, one per line in order)"),
			},
		],
		primary_action_label: __("Make Cheques"),
		primary_action(values) {
			frm.call("make_cheques", values).then(({ message }) => {
				d.hide();
				frappe.show_alert({ message: __("{0} cheques made", [message.length]), indicator: "green" });
				frm.reload_doc();
			});
		},
	});
	d.show();
}

function pay_row(frm) {
	const open = frm.doc.schedule.filter((r) => !r.cheque && ["Unpaid", "Overdue"].includes(r.status));
	if (!open.length) {
		frappe.msgprint(__("Every open instalment has a cheque; clear the cheque when it is paid."));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: __("Instalment Paid in Cash"),
		fields: [
			{
				fieldname: "row",
				fieldtype: "Select",
				label: __("Instalment"),
				reqd: 1,
				options: open.map((r) => ({
					value: String(r.idx),
					label: `${r.idx} — ${frappe.format(r.due_date, { fieldtype: "Date" })} — ${iran_erp.money.format(r.amount)}`,
				})),
			},
			{
				fieldname: "paid_to",
				fieldtype: "Link",
				options: "Account",
				label: __("Received In"),
				reqd: 1,
				get_query: () => ({ filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] } }),
			},
			{ fieldname: "date", fieldtype: "Date", label: __("Date"), default: frappe.datetime.get_today() },
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			frm.call("mark_paid", values).then(() => {
				d.hide();
				frm.reload_doc();
			});
		},
	});
	d.show();
}

function settle(frm) {
	const q = frm.iran_summary && frm.iran_summary.settlement;
	if (!q) return;
	frappe.confirm(
		__("To settle today the customer pays {0}: principal {1} and profit earned so far {2}. The profit of the days not reached, {3}, is taken off. The open cheques are to be given back. Continue?", [
			iran_erp.money.format(q.payable),
			iran_erp.money.format(q.principal),
			iran_erp.money.format(q.earned_interest),
			iran_erp.money.format(q.discount),
		]),
		() => frm.call("settle_early").then(() => frm.reload_doc())
	);
}
