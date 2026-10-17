// Copyright (c) 2026, Majid Ehtesham and contributors
// For license information, please see license.txt

// Which actions each status allows, per cheque type
const CHEQUE_ACTIONS = {
	Received: {
		"In Hand": ["deposit", "clear", "endorse", "return", "bounce"],
		Deposited: ["clear", "bounce"],
	},
	Issued: {
		Issued: ["clear", "return", "bounce"],
	},
};

const cheque_action_labels = () => ({
	deposit: __("Deposit to Bank"),
	clear: __("Mark as Cleared"),
	bounce: __("Mark as Bounced"),
	return: __("Return to Party"),
	endorse: __("Endorse to Third Party"),
});

frappe.ui.form.on("Iran Cheque", {
	setup(frm) {
		const bank_query = () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				account_type: ["in", ["Bank", "Cash"]],
			},
		});
		frm.set_query("bank_account", bank_query);
		frm.set_query("against_invoice", () => ({
			filters: {
				company: frm.doc.company,
				docstatus: 1,
				outstanding_amount: [">", 0],
				[frm.doc.against_doctype === "Purchase Invoice" ? "supplier" : "customer"]: frm.doc.party,
			},
		}));
	},

	refresh(frm) {
		// A cheque the business writes is printed on the bank's leaf
		if (frm.doc.cheque_type === "Issued" && !frm.is_new()) {
			const open = (test) =>
				window.open(`/cheque_print?cheque=${encodeURIComponent(frm.doc.name)}${test ? "&test=1" : ""}`, "_blank");
			frm.add_custom_button(__("Print on Cheque"), () => open(false), __("Print"));
			frm.add_custom_button(__("Test Print (with grid)"), () => open(true), __("Print"));
			frm.add_custom_button(__("Cheque Print Layout"), () => frappe.set_route("List", "Iran Cheque Layout"), __("Print"));
		}
		if (frm.doc.docstatus !== 1) return;
		const actions = (CHEQUE_ACTIONS[frm.doc.cheque_type] || {})[frm.doc.status] || [];
		const labels = cheque_action_labels();
		actions.forEach((action) => {
			frm.add_custom_button(labels[action], () => show_cheque_action(frm, action), __("Actions"));
		});
	},

	cheque_type(frm) {
		frm.set_value("party_type", frm.doc.cheque_type === "Issued" ? "Supplier" : "Customer");
		frm.set_value("against_doctype", "");
	},

	party_type(frm) {
		frm.set_value("party", "");
	},

	against_doctype(frm) {
		frm.set_value("against_invoice", "");
	},

	against_invoice(frm) {
		if (!frm.doc.against_invoice || frm.doc.amount) return;
		frappe.db
			.get_value(frm.doc.against_doctype, frm.doc.against_invoice, "outstanding_amount")
			.then((r) => frm.set_value("amount", r.message.outstanding_amount));
	},
});

function show_cheque_action(frm, action) {
	const needs_bank = ["deposit", "clear"].includes(action);
	const fields = [
		{ fieldname: "date", fieldtype: "Date", label: __("Date"), reqd: 1, default: frappe.datetime.nowdate() },
	];
	if (needs_bank) {
		fields.push({
			fieldname: "bank_account",
			fieldtype: "Link",
			options: "Account",
			label: __("Bank Account"),
			reqd: 1,
			default: frm.doc.bank_account,
			get_query: () => ({
				filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] },
			}),
		});
	}
	if (action === "endorse") {
		fields.push(
			{
				fieldname: "endorsed_to_type",
				fieldtype: "Select",
				label: __("Endorsed To Type"),
				options: ["Supplier", "Customer", "Employee"],
				default: "Supplier",
				reqd: 1,
			},
			{
				fieldname: "endorsed_to",
				fieldtype: "Dynamic Link",
				options: "endorsed_to_type",
				label: __("Endorsed To"),
				reqd: 1,
			}
		);
	}
	fields.push({ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") });

	const dialog = new frappe.ui.Dialog({
		title: cheque_action_labels()[action],
		fields,
		primary_action_label: __("Save"),
		primary_action(values) {
			dialog.hide();
			frm.call({
				doc: frm.doc,
				method: "take_action",
				args: { action, ...values },
				freeze: true,
				callback: () => frm.reload_doc(),
			});
		},
	});
	dialog.show();
}
