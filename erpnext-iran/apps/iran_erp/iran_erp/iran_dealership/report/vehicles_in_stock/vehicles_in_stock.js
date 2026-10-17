frappe.query_reports["Vehicles in Stock"] = {
	filters: [
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "parking", label: __("Parking"), fieldtype: "Link", options: "Iran Parking" },
		{
			fieldname: "status",
			label: __("Status in the Lot"),
			fieldtype: "Select",
			options: ["", "Awaiting Delivery", "In Preparation", "Ready for Sale", "Reserved"].map((v) => ({ value: v, label: __(v) })),
		},
		{
			fieldname: "ownership",
			label: __("Owned By"),
			fieldtype: "Select",
			options: ["", "Business", "Investor", "Customer"].map((v) => ({ value: v, label: __(v) })),
		},
		{ fieldname: "car_model", label: __("Model"), fieldtype: "Link", options: "Iran Car Model" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days" && data && data.days > 60) value = `<span class="text-danger">${value}</span>`;
		if (column.fieldname === "name" && data && data.name) {
			value = `<a href="/desk/iran-vehicle/${encodeURIComponent(data.name)}">${value}</a>`;
		}
		return value;
	},
};
