// Copyright (c) 2026, Majid Ehtesham and contributors

frappe.ui.form.on("Iran Investor", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Investor's Account"), () => {
			frappe.route_options = { investor: frm.doc.name };
			frappe.set_route("iran-my-account");
		});
		frm.add_custom_button(__("New Investment Contract"), () =>
			frappe.new_doc("Iran Investment Contract", { investor: frm.doc.name })
		);
		if (!frm.doc.user) {
			frm.add_custom_button(__("Create Login"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Create Login"),
					fields: [
						{
							fieldtype: "HTML",
							options: `<p class="text-muted">${__("The investor signs in with this email and password and sees only their own account.")}</p>`,
						},
						{ fieldname: "email", fieldtype: "Data", options: "Email", label: __("Email"), reqd: 1 },
						{ fieldname: "password", fieldtype: "Password", label: __("Password"), reqd: 1 },
					],
					primary_action_label: __("Create"),
					primary_action(values) {
						frm.call("create_login", values).then(() => {
							d.hide();
							frm.reload_doc();
						});
					},
				});
				d.show();
			});
		}
	},
});
