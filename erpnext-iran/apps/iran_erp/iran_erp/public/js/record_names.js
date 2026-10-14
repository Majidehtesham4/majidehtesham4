// Standard master records (territories, customer groups, units, modes of payment, ...) are stored
// under English names such as "Rest Of The World" or "Demo Customer Group". Frappe translates them
// in link fields and tree nodes once their DocType is marked "translated"
// (iran_erp.install.mark_translated_doctypes), but not as the title of their own list rows.

frappe.provide("iran_erp.names");

iran_erp.names.is_translated = (doctype) => (frappe.boot.translated_doctypes || []).includes(doctype);

$(document).on("app_ready", () => {
	const list = frappe.views.ListView && frappe.views.ListView.prototype;
	if (list && !list.iran_names) {
		list.iran_names = true;
		const subject_text = list.get_subject_text;
		list.get_subject_text = function (doc, title) {
			const text = subject_text.call(this, doc, title);
			return iran_erp.names.is_translated(this.doctype) && typeof text === "string" ? __(text) : text;
		};
		// The name repeated in a plain text column ("نام منطقه") as well
		const column_html = list.get_column_html;
		list.get_column_html = function (col, doc, show_in_mobile) {
			const fieldname = col.df && col.df.fieldname;
			if (fieldname && col.type !== "Subject" && iran_erp.names.is_translated(this.doctype)) {
				const value = doc[fieldname];
				if (typeof value === "string" && value === doc.name) {
					doc = Object.assign({}, doc, { [fieldname]: __(value) });
				}
			}
			return column_html.call(this, col, doc, show_in_mobile);
		};
	}

});
