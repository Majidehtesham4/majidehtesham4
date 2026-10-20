// «سیستم مشتری‌ها»: every business environment on this server, from the main site. Shows which ones
// have the last update and runs it for one business or all of them.

frappe.pages["iran-owner-panel"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Customer Systems"), single_column: true });
	wrapper.owner_panel = new IranOwnerPanel(page);
};

frappe.pages["iran-owner-panel"].on_page_show = function (wrapper) {
	wrapper.owner_panel && wrapper.owner_panel.load();
};

class IranOwnerPanel {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="iran-owner"></div>').appendTo(page.body);
		page.set_primary_action(__("Update All"), () => this.update());
		page.set_secondary_action(__("Refresh"), () => this.load());
	}

	digits(text) {
		return iran_erp.to_persian_digits ? iran_erp.to_persian_digits(text) : text;
	}

	load() {
		frappe.call("iran_erp.owner.get_panel").then((r) => {
			this.data = r.message;
			this.render();
			this.watch();
		});
	}

	render() {
		const { sites, main, update } = this.data;
		const cmd = (text) => `<code dir="ltr">${text}</code>`;
		const behind = sites.filter((s) => !s.error && !s.up_to_date).length + (main.up_to_date ? 0 : 1);
		const rows = sites
			.map((s) => {
				const name = frappe.utils.escape_html(s.title || s.site);
				const kind = s.business_type ? __(s.business_type) : __("Not set up yet");
				const state = s.error
					? `<span class="indicator-pill red">${__("Not reachable")}</span>`
					: s.up_to_date
						? `<span class="indicator-pill green">${__("Up to date")}</span>`
						: `<span class="indicator-pill orange">${__("Needs update")}</span>`;
				const active = s.last_active ? iran_erp.to_jalali(s.last_active) : "—";
				const url = frappe.utils.escape_html(s.url);
				return `<tr>
					<td><b>${name}</b><div class="text-muted small" dir="ltr">${frappe.utils.escape_html(s.site)}</div></td>
					<td>${kind}</td>
					<td>${this.digits(s.users || 0)}</td>
					<td>${active}</td>
					<td>${state}</td>
					<td class="iran-owner-actions">
						<a class="btn btn-xs btn-default" href="${url}/login" target="_blank" rel="noopener">${__("Open")}</a>
						${s.error ? "" : `<button class="btn btn-xs btn-default" data-update="${frappe.utils.escape_html(s.site)}">${__("Update")}</button>`}
					</td>
				</tr>`;
			})
			.join("");
		this.$body.html(`
			<div class="iran-owner-summary">
				<div><small>${__("Businesses")}</small><strong>${this.digits(sites.length)}</strong></div>
				<div class="${behind ? "warn" : ""}"><small>${__("Need the last update")}</small><strong>${this.digits(behind)}</strong></div>
				<div><small>${__("This main site")}</small><strong>${main.up_to_date ? __("Up to date") : __("Needs update")}</strong></div>
			</div>
			<div class="iran-owner-status">${this.status_html(update)}</div>
			${
				sites.length
					? `<table class="table table-bordered iran-owner-table">
						<thead><tr><th>${__("Business Environment")}</th><th>${__("Kind of business")}</th><th>${__("Users")}</th>
						<th>${__("Last activity")}</th><th>${__("Version")}</th><th></th></tr></thead>
						<tbody>${rows}</tbody></table>`
					: `<p class="text-muted">${__("No business environments yet.")}</p>`
			}
			<div class="iran-owner-help">
				<p>${__("Make a new business: on the server, in the deploy folder: {0}", [cmd(".\\business.ps1 new name")])}</p>
				<p>${__("Log in to a business as its Administrator without its password: {0}", [cmd(".\\business.ps1 open name")])}</p>
				<p>${__("A new version: {0} on the server gets it, rebuilds and updates every business. «Update All» here only repeats the last step.", [cmd(".\\update.ps1")])}</p>
			</div>
		`);
		this.$body.find("[data-update]").on("click", (e) => this.update($(e.currentTarget).attr("data-update")));
	}

	status_html(update) {
		if (!update) return "";
		const done = (update.done || []).length;
		const failed = Object.keys(update.failed || {});
		if (update.running) {
			return `<div class="alert alert-info">${__("Updating {0} of {1}: {2}", [
				this.digits(done + failed.length + 1),
				this.digits(update.sites.length),
				frappe.utils.escape_html(update.current || ""),
			])}</div>`;
		}
		let html = `<div class="alert ${failed.length ? "alert-danger" : "alert-success"}">${__("Last update: {0} done", [
			this.digits(done),
		])}`;
		if (failed.length) {
			html += ` — ${__("failed")}: ${failed.map((s) => frappe.utils.escape_html(s)).join("، ")}`;
			html += failed
				.map((s) => `<pre class="small" dir="ltr">${frappe.utils.escape_html(update.failed[s])}</pre>`)
				.join("");
		}
		return html + "</div>";
	}

	update(site) {
		const message = site
			? __("Update {0} now? Its users may see errors for a few minutes.", [site])
			: __("Update every business and this main site now? Their users may see errors for a few minutes.");
		frappe.confirm(message, () => {
			frappe.call("iran_erp.owner.start_update", { site: site || null }).then((r) => {
				this.data.update = r.message;
				this.render();
				this.watch();
			});
		});
	}

	watch() {
		clearTimeout(this.timer);
		if (!(this.data.update && this.data.update.running)) return;
		this.timer = setTimeout(() => {
			frappe.call("iran_erp.owner.update_status").then((r) => {
				const was_running = this.data.update && this.data.update.running;
				this.data.update = r.message;
				if (was_running && !(r.message && r.message.running)) return this.load();
				this.$body.find(".iran-owner-status").html(this.status_html(r.message));
				this.watch();
			});
		}, 4000);
	}
}
