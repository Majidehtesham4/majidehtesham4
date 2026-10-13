// Copyright (c) 2026, Majid Ehtesham and contributors
// For license information, please see license.txt

frappe.ui.form.on("Iran Chat Command", {
	onload(frm) {
		frappe
			.xcall("iran_erp.iran_erp.doctype.iran_chat_command.iran_chat_command.builtin_commands")
			.then((commands) => {
				frm.set_df_property("intent", "options", [{ value: "", label: "" }, ...commands]);
				frm.refresh_field("intent");
			});
	},
});
