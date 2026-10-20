// Copyright (c) 2026, Majid Ehtesham and contributors
// For license information, please see license.txt

const IRAN_EXAMPLE = "iran_erp.iran_erp.doctype.iran_intent_example.iran_intent_example";

frappe.ui.form.on("Iran Intent Example", {
	refresh(frm) {
		if (frm.is_new()) return;
		const set = (status) =>
			frappe.xcall(`${IRAN_EXAMPLE}.set_status`, { names: frm.doc.name, status }).then(() => frm.reload_doc());
		if (frm.doc.status !== "Approved") frm.add_custom_button(__("Approve"), () => set("Approved"));
		if (frm.doc.status !== "Rejected") frm.add_custom_button(__("Reject"), () => set("Rejected"));
		frm.add_custom_button(__("Check Again"), () =>
			frm.save().then(() => frappe.xcall(`${IRAN_EXAMPLE}.check`, { names: frm.doc.name }).then(() => frm.reload_doc()))
		);
	},
});
