// Copyright (c) 2026, Majid Ehtesham and contributors
// For license information, please see license.txt

frappe.ui.form.on("Iran ERP Settings", {
	refresh(frm) {
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
