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
						"Sample data of the kind of business chosen in Easy Setup will be added: for a car dealership its cars, investors, instalment sales and website; for other businesses customers, suppliers, items, stock, production, invoices, CRM, projects and cheques. Continue?"
					)
				),
			__("Demo Data")
		);
		frm.add_custom_button(
			__("Delete Demo Data"),
			() => demo("delete", __("All demo records will be cancelled and deleted. Continue?")),
			__("Demo Data")
		);
		frm.add_custom_button(
			__("Delete All Data (Start Over)"),
			() => {
				const word = "حذف همه";
				frappe.prompt(
					[
						{
							fieldtype: "HTML",
							options: `<p class="text-danger">${__(
								"Every document, customer, supplier, item, car, cheque and contract is deleted and cannot be brought back; numbering starts again from 1 and Easy Setup asks about the business again. The companies, chart of accounts, users and settings stay."
							)}</p>`,
						},
						{ fieldname: "confirm", fieldtype: "Data", label: __("To confirm, type «{0}»", [word]), reqd: 1 },
					],
					({ confirm }) =>
						frappe.xcall("iran_erp.reset_data.start", { confirm }).then(() => {
							frappe.show_alert({ message: __("Deleting; this takes a minute or two."), indicator: "blue" }, 20);
							const wait = () =>
								frappe.xcall("iran_erp.reset_data.status").then((r) => {
									if (r.running) return setTimeout(wait, 3000);
									if (r.error) {
										frappe.msgprint({ message: r.error, indicator: "red", title: __("Deleting failed") });
										return;
									}
									frappe.msgprint({
										message: __("{0} records were deleted. The system now opens on Easy Setup.", [r.count]),
										indicator: "green",
										primary_action: { label: __("Open Easy Setup"), action: () => (window.location.href = "/desk/iran-easy-setup") },
									});
								});
							setTimeout(wait, 3000);
						}),
					__("Delete All Data"),
					__("Delete")
				);
			},
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
