// Copyright (c) 2026, Majid Ehtesham and contributors
// For license information, please see license.txt

const CHEQUE_STATUS_COLORS = {
	Draft: "gray",
	"In Hand": "blue",
	Deposited: "purple",
	Issued: "orange",
	Cleared: "green",
	Bounced: "red",
	Returned: "gray",
	Endorsed: "cyan",
	Cancelled: "red",
};

frappe.listview_settings["Iran Cheque"] = {
	add_fields: ["status", "due_date"],
	get_indicator(doc) {
		let color = CHEQUE_STATUS_COLORS[doc.status] || "gray";
		// Open cheques past their due date stand out
		const open = ["In Hand", "Deposited", "Issued"].includes(doc.status);
		if (open && doc.due_date && doc.due_date < frappe.datetime.nowdate()) color = "yellow";
		return [__(doc.status), color, `status,=,${doc.status}`];
	},
};
