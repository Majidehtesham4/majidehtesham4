// Moadian (سامانه مؤدیان): give a submitted invoice its tax number and show the electronic invoice data.

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frm.add_custom_button(
			frm.doc.iran_tax_id ? __("Moadian Invoice") : __("Prepare for Moadian"),
			() =>
				frappe
					.xcall("iran_erp.moadian.invoice.prepare", { sales_invoice: frm.doc.name })
					.then((r) => {
						show_moadian_invoice(r);
						if (r.tax_id && r.tax_id !== frm.doc.iran_tax_id) frm.reload_doc();
					}),
			__("Moadian")
		);
	},
});

function show_moadian_invoice(r) {
	const json = JSON.stringify(r.payload, null, 2);
	const problems = (r.problems || [])
		.map((p) => `<li>${frappe.utils.escape_html(p)}</li>`)
		.join("");
	const dialog = new frappe.ui.Dialog({
		title: __("Moadian Invoice"),
		size: "large",
		fields: [
			{
				fieldname: "details",
				fieldtype: "HTML",
				options: `
					<p><b>${__("Tax Number")}:</b> <code dir="ltr">${frappe.utils.escape_html(
						r.tax_id || __("Not assigned yet")
					)}</code></p>
					${
						problems
							? `<div class="alert alert-warning"><b>${__(
									"Fix these before sending:"
							  )}</b><ul>${problems}</ul></div>`
							: ""
					}
					<p class="text-muted small">${__(
						"Signing and sending to the tax organization is not built in yet; this data has not been tested against the live service."
					)}</p>
					<pre dir="ltr" style="max-height:360px;overflow:auto;text-align:left"></pre>`,
			},
		],
		primary_action_label: __("Download JSON"),
		primary_action() {
			const blob = new Blob([json], { type: "application/json" });
			const a = document.createElement("a");
			a.href = URL.createObjectURL(blob);
			a.download = `${r.tax_id || "moadian-invoice"}.json`;
			a.click();
		},
	});
	// Set as text so the JSON keeps its line breaks
	dialog.fields_dict.details.$wrapper.find("pre").text(json);
	dialog.show();
}
