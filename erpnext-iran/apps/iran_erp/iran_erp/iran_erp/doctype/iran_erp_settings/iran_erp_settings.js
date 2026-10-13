// Copyright (c) 2026, Majid Ehtesham and contributors
// For license information, please see license.txt

frappe.ui.form.on("Iran ERP Settings", {
	refresh(frm) {
		const wait_for_demo = () =>
			frappe.xcall("iran_erp.demo.job_status").then((r) => {
				if (r.running) {
					setTimeout(wait_for_demo, 3000);
					return;
				}
				const message = r.error
					? __("Demo data failed: {0}", [r.error])
					: r.action === "create"
					? __("Demo data was created: {0} records.", [r.count])
					: __("Demo data was deleted: {0} records.", [r.count]);
				// A toast, not msgprint: the confirm dialog shares msgprint's dialog and can blank it
				frappe.show_alert({ message, indicator: r.error ? "red" : "green" }, 30);
			});
		const demo = (action, question) =>
			frappe.confirm(question, () =>
				frappe.xcall("iran_erp.demo.start", { action }).then(() => {
					frappe.show_alert({ message: __("Please wait; this takes a minute or two."), indicator: "blue" }, 15);
					setTimeout(wait_for_demo, 3000);
				})
			);
		frm.add_custom_button(
			__("Create Demo Data"),
			() =>
				demo(
					"create",
					__(
						"Sample customers, suppliers, items, stock, production, sales and purchase invoices, CRM, projects, support tickets, employees, web pages and cheques will be added to the default company. Continue?"
					)
				),
			__("Demo Data")
		);
		frm.add_custom_button(
			__("Delete Demo Data"),
			() => demo("delete", __("All demo records will be cancelled and deleted. Continue?")),
			__("Demo Data")
		);
		frm.add_custom_button(__("Apply Iranian Chart of Accounts"), () => {
			frappe.prompt(
				[
					{
						fieldname: "company",
						fieldtype: "Link",
						options: "Company",
						label: __("Company"),
						reqd: 1,
						default: frappe.defaults.get_user_default("Company"),
					},
					{
						fieldname: "vat_rate",
						fieldtype: "Percent",
						label: __("VAT Rate"),
						default: frm.doc.vat_rate,
					},
				],
				(values) => {
					frappe.confirm(
						__(
							"All accounts and tax templates of {0} will be deleted and replaced with the Iranian chart of accounts. This only works for a company without transactions. Continue?",
							[values.company.bold()]
						),
						() =>
							frappe.call({
								method: "iran_erp.accounts.chart.apply_iran_chart",
								args: values,
								freeze: true,
								callback: (r) =>
									frappe.msgprint(
										__("The Iranian chart of accounts with {0} accounts was created.", [
											r.message.accounts,
										])
									),
							})
					);
				},
				__("Apply Iranian Chart of Accounts")
			);
		});
	},
});
