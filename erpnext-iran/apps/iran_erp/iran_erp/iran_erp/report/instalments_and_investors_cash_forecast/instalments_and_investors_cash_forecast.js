frappe.query_reports["Instalments and Investors Cash Forecast"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "months", label: __("Months"), fieldtype: "Int", default: 12 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "running" && data && data.running < 0) value = `<span class="text-danger">${value}</span>`;
		return value;
	},
};
