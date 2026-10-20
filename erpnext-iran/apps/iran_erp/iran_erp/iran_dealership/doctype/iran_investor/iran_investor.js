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
		if (!frappe.user.has_role(["System Manager", "Accounts Manager"])) return;
		const has_login = Boolean(frm.doc.user);
		if (has_login) {
			frappe.db.get_value("User", frm.doc.user, "username").then(({ message }) => {
				const username = (message && message.username) || frm.doc.user;
				frm.set_intro(
					__("The investor logs in at {0} with the username {1} and sees their own account.", [
						`<a href="/login" target="_blank">${location.host}/login</a>`,
						`<b dir="ltr">${frappe.utils.escape_html(username)}</b>`,
					]),
					"blue"
				);
			});
		}
		frm.add_custom_button(has_login ? __("Change Username or Password") : __("Create Login"), () => {
			const d = new frappe.ui.Dialog({
				title: has_login ? __("Change Username or Password") : __("Create Login"),
				fields: [
					{
						fieldtype: "HTML",
						options: `<p class="text-muted">${__(
							"The investor logs in with this username and password and sees only their own account: contracts, profit, cheques, cars and statement."
						)}</p>`,
					},
					{
						fieldname: "username",
						fieldtype: "Data",
						label: __("Username"),
						reqd: 1,
						description: __("English letters or digits, for example: ali.rezaei"),
					},
					{ fieldname: "password", fieldtype: "Password", label: __("Password"), reqd: 1, description: __("At least 6 characters") },
					...(has_login ? [] : [{ fieldname: "email", fieldtype: "Data", options: "Email", label: __("Email (optional)") }]),
				],
				primary_action_label: has_login ? __("Save") : __("Create"),
				primary_action(values) {
					frm.call("create_login", values).then(({ message }) => {
						d.hide();
						frappe.msgprint({
							title: __("Done"),
							indicator: "green",
							message: __("The investor can now log in at {0} with the username {1} and the password you chose.", [
								`<a href="/login" target="_blank">${location.host}/login</a>`,
								`<b dir="ltr">${frappe.utils.escape_html(message.username)}</b>`,
							]),
						});
						frm.reload_doc();
					});
				},
			});
			d.show();
		});
	},
});
