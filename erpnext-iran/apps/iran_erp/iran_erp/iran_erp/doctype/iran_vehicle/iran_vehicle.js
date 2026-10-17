// Copyright (c) 2026, Majid Ehtesham and contributors

frappe.ui.form.on("Iran Vehicle", {
	setup(frm) {
		const cash = () => ({ filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] } });
		frm.set_query("paid_from", cash);
		frm.set_query("paid_from", "costs", cash);
	},
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.ownership === "Business" && !frm.doc.purchase_entry && frm.doc.purchase_price) {
			frm.add_custom_button(__("Record Purchase in the Books"), () =>
				frm.call("record_purchase").then(() => frm.reload_doc())
			);
		}
		if (frm.doc.status !== "Sold") {
			frm.add_custom_button(__("Sell in Instalments"), () =>
				frappe.new_doc("Iran Instalment Sale", {
					vehicle: frm.doc.name,
					company: frm.doc.company,
					branch: frm.doc.branch,
					sale_price: frm.doc.asking_price,
				})
			);
		}
		if (frm.doc.total_cost) {
			frm.set_intro(
				__("Total cost of the car: {0}", [iran_erp.money.format(frm.doc.total_cost)]) +
					(frm.doc.profit ? " — " + __("Profit on the car: {0}", [iran_erp.money.format(frm.doc.profit)]) : ""),
				"blue"
			);
		}
	},
});
