// "My Tasks": approvals, drafts to submit, assigned tasks and due items in one list, like Odoo's
// activities. Shown in the sidebar under Notifications and next to the bell on the home page.

frappe.provide("iran_erp.inbox");

const SECTION_LABELS = () => ({
	approvals: __("Waiting for your approval"),
	drafts: __("Drafts to review and submit"),
	tasks: __("Assigned to you"),
	alerts: __("Needs attention"),
});
const REFRESH_MS = 2 * 60 * 1000;

Object.assign(iran_erp.inbox, {
	data: { items: [], total: 0 },
	loaded_at: 0,

	load(force) {
		if (!force && Date.now() - this.loaded_at < 30 * 1000) return;
		this.loaded_at = Date.now();
		frappe.xcall("iran_erp.inbox.get_inbox").then((data) => {
			this.data = data;
			this.render_badges();
			if (this.$panel?.is(":visible")) this.render_panel();
		});
	},

	render_badges() {
		const total = this.data.total || 0;
		$(".iran-inbox-count")
			.text(total > 99 ? "99+" : total)
			.toggleClass("hidden", !total);
	},

	// The sidebar is rebuilt on navigation, so the item is put back whenever it goes missing
	ensure_entries() {
		$(".standard-items-band").each((_, band) => {
			if ($(band).find(".iran-inbox-item").length) return;
			$(`
				<div class="iran-inbox-item">
					<div class="standard-sidebar-item">
						<a class="item-anchor">
							<span class="sidebar-item-icon">${frappe.utils.icon("list-checks", "sm")}</span>
							<span class="sidebar-item-label">${__("My Tasks")}</span>
							<span class="sidebar-item-suffix"><span class="notification-count iran-inbox-count hidden"></span></span>
						</a>
					</div>
				</div>`)
				.insertAfter($(band).find(".sidebar-notification").first())
				.on("click", (e) => this.toggle(e.currentTarget));
		});
		$(".desktop-notifications").each((_, bell) => {
			if ($(bell).prev(".iran-inbox-desktop").length) return;
			$(`
				<div class="iran-inbox-desktop">
					<button class="btn-reset nav-link text-muted" title="${__("My Tasks")}">
						${frappe.utils.icon("list-checks", "md")}
						<span class="notification-count iran-inbox-count hidden"></span>
					</button>
				</div>`)
				.insertBefore(bell)
				.on("click", (e) => this.toggle(e.currentTarget));
		});
		this.render_badges();
	},

	toggle(anchor) {
		if (!this.$panel) {
			this.$panel = $(`<div class="iran-inbox-panel" dir="rtl"></div>`).appendTo(document.body).hide();
			this.$panel.on("click", ".iran-inbox-row", (e) => {
				const item = this.data.items[Number($(e.currentTarget).data("index"))];
				this.$panel.hide();
				frappe.set_route("List", item.doctype, item.filters);
			});
			$(document).on("mousedown", (e) => {
				if (
					this.$panel.is(":visible") &&
					!$(e.target).closest(".iran-inbox-panel, .iran-inbox-item, .iran-inbox-desktop").length
				) {
					this.$panel.hide();
				}
			});
		}
		if (this.$panel.is(":visible")) {
			this.$panel.hide();
			return;
		}
		this.render_panel();
		const rect = anchor.getBoundingClientRect();
		const width = 340;
		const left = Math.min(Math.max(8, rect.left), window.innerWidth - width - 8);
		this.$panel.css({ top: rect.bottom + 6, left, width }).show();
		this.load(true);
	},

	render_panel() {
		const labels = SECTION_LABELS();
		const items = this.data.items || [];
		let html = `<div class="iran-inbox-title">${__("My Tasks")}</div>`;
		if (!items.length) {
			html += `<div class="iran-inbox-empty">${__("Nothing is waiting for you.")}</div>`;
		}
		let section = null;
		items.forEach((item, index) => {
			if (item.section !== section) {
				section = item.section;
				html += `<div class="iran-inbox-section">${labels[section] || ""}</div>`;
			}
			html += `
				<div class="iran-inbox-row" data-index="${index}">
					<span>${frappe.utils.escape_html(item.label)}</span>
					<span class="iran-inbox-row-count">${item.count}</span>
				</div>`;
		});
		this.$panel.html(html);
	},
});

$(document).on("app_ready", () => {
	iran_erp.inbox.ensure_entries();
	iran_erp.inbox.load(true);
	setInterval(() => iran_erp.inbox.load(true), REFRESH_MS);
	frappe.router.on("change", () => {
		setTimeout(() => iran_erp.inbox.ensure_entries(), 300);
		iran_erp.inbox.load();
	});
	// Catch sidebar re-renders that do not come with a route change
	let pending = null;
	new MutationObserver(() => {
		clearTimeout(pending);
		pending = setTimeout(() => iran_erp.inbox.ensure_entries(), 400);
	}).observe(document.body, { childList: true, subtree: true });
});

// Frappe opens every "External" home-screen icon in a new tab, including this app's icons,
// which only lead to pages of this same desk
$(document).on("click", "a.desktop-icon[target=_blank]", function () {
	if ((this.getAttribute("href") || "").startsWith(`${window.location.origin}/desk/`)) {
		this.removeAttribute("target");
	}
});
