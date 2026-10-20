frappe.listview_settings["Iran Intent Example"] = {
	get_indicator(doc) {
		const colors = { Approved: "green", Proposed: "blue", "Needs Review": "orange", Rejected: "red" };
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
	onload(list) {
		const method = "iran_erp.iran_erp.doctype.iran_intent_example.iran_intent_example.set_status";
		for (const [label, status] of [
			[__("Approve"), "Approved"],
			[__("Reject"), "Rejected"],
		]) {
			list.page.add_actions_menu_item(label, () => {
				const names = list.get_checked_items(true);
				if (!names.length) return;
				frappe.xcall(method, { names, status }).then(() => list.refresh());
			});
		}
	},
};
