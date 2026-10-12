// Copyright (c) 2026, Majid Ehtesham and contributors
// For license information, please see license.txt

frappe.ui.form.on("Iran AI Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method: "iran_erp.ai.api.test_connection",
				freeze: true,
				freeze_message: __("Contacting the AI service…"),
				callback: (r) => frappe.msgprint(r.message),
			});
		});
	},
});
