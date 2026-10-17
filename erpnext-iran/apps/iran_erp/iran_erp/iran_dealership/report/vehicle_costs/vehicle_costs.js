frappe.query_reports["Vehicle Costs"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: [
				{ value: "Service", label: __("Service") },
				{ value: "Car", label: __("Car") },
			],
			default: "Service",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Select",
			options: ["", "Preparation", "Repair", "Paperwork", "Other"].map((v) => ({ value: v, label: __(v) })),
		},
		{ fieldname: "service", label: __("Service"), fieldtype: "Link", options: "Iran Vehicle Service" },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
	],
};
