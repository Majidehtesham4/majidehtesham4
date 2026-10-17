// Everyday tasks as short forms («فرم ساده»): only the details a task needs, in plain words.
// The form runs the same built-in command the chat runs for that task.

frappe.provide("iran_erp.start");

iran_erp.start.wizard = function (intent) {
	frappe.xcall("iran_erp.start.get_wizard", { intent }).then((wizard) => {
		const fields = wizard.fields.map((field) => {
			const df = { ...field };
			if (df.filters) {
				const filters = df.filters;
				df.get_query = () => ({ filters });
				delete df.filters;
			}
			if (df.fieldtype === "Select" && wizard.payment_modes && df.fieldname === "payment_mode") {
				df.fieldtype = "Select";
				df.options = Object.entries(wizard.payment_modes).map(([value, label]) => ({ value, label }));
			}
			if (df.fieldtype === "Table") {
				// One empty row to start with, so the first item can be typed straight away
				df.data = [{ qty: 1 }];
				df.cannot_add_rows = false;
				df.in_place_edit = true;
			}
			return df;
		});
		const dialog = new frappe.ui.Dialog({
			title: wizard.title,
			fields,
			size: fields.some((f) => f.fieldtype === "Table") ? "large" : "small",
			primary_action_label: __("Save"),
			primary_action: (values) => {
				dialog.disable_primary_action();
				frappe
					.xcall("iran_erp.start.run_wizard", { intent, values })
					.then((result) => {
						dialog.hide();
						iran_erp.start.show_result(wizard.title, result);
					})
					.finally(() => dialog.enable_primary_action());
			},
		});
		dialog.$wrapper.find(".modal-content").attr("dir", "rtl");
		dialog.show();
	});
};

iran_erp.start.show_result = function (title, result) {
	const html = frappe.markdown(frappe.utils.escape_html(result.answer || ""));
	const $body = $(`<div class="iran-start-result" dir="rtl"></div>`).html(html);
	const dialog = new frappe.ui.Dialog({ title });
	dialog.$body.append($body);
	(result.actions || []).forEach((action) => {
		if (!action.url) return;
		const label = action.label || `${__("Open")} ${__(action.created || "")} ${action.name || ""}`;
		$(`<button class="btn btn-primary btn-sm iran-start-result-open"></button>`)
			.text(label)
			.on("click", () => {
				dialog.hide();
				frappe.set_route(action.url.replace(/^https?:\/\/[^/]+/, ""));
			})
			.appendTo($body);
	});
	if (!result.incomplete && (result.actions || []).length) {
		$body.append(
			$(`<p class="iran-start-result-note"></p>`).text(
				__("It was saved as a draft. Open it, check it, then press «Submit» to make it final.")
			)
		);
	}
	dialog.show();
};

// An investor's login always opens on their own account
$(document).on("startup", () => {
	if (!frappe.boot.iran_investor_only) return;
	const home = () => /^\/(desk|app)(\/(desktop|build\/desktop))?\/?$/.test(window.location.pathname);
	const go = () => home() && frappe.set_route("iran-my-account");
	// The desk may move to its home page after a slow first load; look again a few times
	[300, 1500, 4000].forEach((wait) => setTimeout(go, wait));
	frappe.router.on("change", () => setTimeout(go, 100));
});

// Newcomers land on the Start page once per sign-in, instead of the grid of app icons
$(document).on("startup", () => {
	if (!frappe.boot.iran_open_start_page) return;
	const key = `iran_start_shown_${frappe.boot.user.name}`;
	try {
		if (sessionStorage.getItem(key)) return;
		sessionStorage.setItem(key, "1");
	} catch (e) {
		return;
	}
	// Only when the desk opens on its home page, and once the desk has finished setting up
	if (!/^\/(desk|app)\/?$/.test(window.location.pathname)) return;
	setTimeout(() => {
		if (/^\/(desk|app)\/?$/.test(window.location.pathname)) frappe.set_route("iran-start");
	}, 300);
});
