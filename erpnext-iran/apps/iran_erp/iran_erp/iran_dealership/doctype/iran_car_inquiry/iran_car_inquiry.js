// Copyright (c) 2026, Majid Ehtesham and contributors

frappe.ui.form.on("Iran Car Inquiry", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.mobile) {
			frm.add_custom_button(__("Call"), () => (window.location.href = `tel:${frm.doc.mobile}`));
			frm.add_custom_button(__("WhatsApp"), () =>
				window.open(`https://wa.me/98${frm.doc.mobile.replace(/^0/, "")}`, "_blank", "noopener")
			);
		}
		if (frm.doc.vehicle && !frm.doc.sale_contract && !["Won", "Lost"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Make Instalment Sale"), async () => {
				const sale = await frappe.xcall(
					"iran_erp.iran_dealership.doctype.iran_car_inquiry.iran_car_inquiry.make_sale",
					{ inquiry: frm.doc.name }
				);
				frappe.model.sync(sale);
				frappe.set_route("Form", sale.doctype, sale.name);
			}).addClass("btn-primary");
		}
		if (frm.doc.vehicle) {
			frm.add_custom_button(__("See on the Website"), () => window.open(`/cars/${frm.doc.vehicle}`, "_blank"));
		}
	},
});
