// «آموزش»: a button on every page that explains the page and each of its parts.
// Forms list their fields, lists their statuses, reports their filters and columns; a click on
// an entry scrolls to it and highlights it. Text comes from the Persian guides in
// iran_erp/help/guides.py, then from the field's own description, then from its type.

frappe.provide("iran_erp.help");

iran_erp.help = {
	guides: {},
	field_types: null,

	context() {
		const route = frappe.get_route() || [];
		const view = (route[0] || "").toLowerCase();
		if (view === "form" && route[1]) return { kind: "form", doctype: route[1] };
		if (["list", "report", "kanban", "calendar", "gantt", "dashboard-view", "image"].includes(view) && route[1])
			return { kind: "list", doctype: route[1] };
		if (view === "tree" && route[1]) return { kind: "list", doctype: route[1] };
		if (view === "query-report" && route[1]) return { kind: "report", report: route[1] };
		if (view === "workspaces" && route[1]) return { kind: "workspace", workspace: route[1] };
		return { kind: "page", page: route[0] || "desk" };
	},

	add_button() {
		const page = frappe.container && frappe.container.page && frappe.container.page.page;
		if (!page || !page.icon_group || page.iran_help_button) return;
		page.iran_help_button = $(
			`<button class="btn btn-default btn-sm iran-help-button" title="${__("Explain this page")}">
				${frappe.utils.icon("book-open", "sm")}<span>${__("Help")}</span>
			</button>`
		)
			.appendTo(page.icon_group.removeClass("hide"))
			.on("click", () => this.toggle());
	},

	async toggle() {
		if (this.$panel && this.$panel.is(":visible")) {
			this.$panel.hide();
			return;
		}
		if (!this.$panel) {
			this.$panel = $(`
				<div class="iran-help-panel" dir="rtl">
					<div class="iran-help-header">
						<div class="iran-help-title"></div>
						<button class="btn btn-xs btn-default iran-help-close">${frappe.utils.icon("x", "sm")}</button>
					</div>
					<div class="iran-help-body"></div>
				</div>`).appendTo(document.body);
			this.$panel.find(".iran-help-close").on("click", () => this.$panel.hide());
			this.$panel.on("click", ".iran-help-item[data-target]", (e) => this.point_to($(e.currentTarget)));
			this.$panel.on("click", ".iran-help-generate", () => this.generate());
			frappe.router.on("change", () => this.$panel && this.$panel.hide());
		}
		this.$panel.show();
		this.$panel.find(".iran-help-body").html(`<div class="text-muted">${__("Loading…")}</div>`);
		if (!this.field_types) {
			this.field_types = await frappe.xcall("iran_erp.help.get_field_types");
		}
		const context = this.context();
		this.current = context;
		const html = await this.render(context);
		this.$panel.find(".iran-help-body").html(html);
	},

	async guide(kind, name) {
		const key = `${kind}:${name}`;
		if (!(key in this.guides)) {
			this.guides[key] = await frappe.xcall("iran_erp.help.get_guide", { kind, name });
		}
		return this.guides[key] || {};
	},

	async render(context) {
		const esc = frappe.utils.escape_html;
		let title = "";
		let parts = [];
		if (context.kind === "form" || context.kind === "list") {
			const doctype = context.doctype;
			await frappe.model.with_doctype(doctype);
			const guide = await this.guide("doctype", doctype);
			title = __(doctype);
			parts.push(this.about(guide.about || __("This page holds {0} records.", [__(doctype)])));
			parts.push(this.saved_section({ kind: "doctype", name: doctype }, guide));
			if (guide.module_about) parts.push(this.section(__("Part of the system"), `<p>${esc(guide.module_about)}</p>`));
			if (guide.steps && guide.steps.length) parts.push(this.steps(guide.steps));
			if (context.kind === "form") {
				parts.push(this.form_fields(doctype, guide.fields || {}));
				if (guide.is_submittable) parts.push(this.section(__("Document states"), this.docstatus_help()));
			} else {
				parts.push(this.list_help(doctype));
			}
		} else if (context.kind === "report") {
			const guide = await this.guide("report", context.report);
			title = __(context.report);
			parts.push(this.about(guide.about || __("A report.")));
			parts.push(this.saved_section({ kind: "report", name: context.report }, guide));
			parts.push(this.report_parts(guide.fields || {}));
		} else if (context.kind === "workspace") {
			const guide = await this.guide("workspace", context.workspace);
			title = __(context.workspace);
			parts.push(
				this.about(
					guide.about ||
						__("This workspace gathers the pages of one part of the system. Use the side menu to open them.")
				)
			);
			parts.push(this.saved_section({ kind: "workspace", name: context.workspace }, guide));
			parts.push(this.section(__("How to move around"), this.navigation_help()));
		} else {
			title = __("Help");
			parts.push(this.section(__("How to move around"), this.navigation_help()));
		}
		this.$panel.find(".iran-help-title").html(`${frappe.utils.icon("book-open", "sm")} ${esc(title)}`);
		return parts.filter(Boolean).join("");
	},

	about(text) {
		return `<p class="iran-help-about">${frappe.utils.escape_html(text)}</p>`;
	},

	section(title, html) {
		return `<div class="iran-help-section"><div class="iran-help-section-title">${frappe.utils.escape_html(
			title
		)}</div>${html}</div>`;
	},

	steps(steps) {
		const items = steps.map((s) => `<li>${frappe.utils.escape_html(s)}</li>`).join("");
		return this.section(__("Steps"), `<ol class="iran-help-steps">${items}</ol>`);
	},

	type_text(df) {
		let text = this.field_types[df.fieldtype] || __(df.fieldtype);
		return text.replace("{options}", __(df.options || ""));
	},

	item(label, text, meta, target) {
		const esc = frappe.utils.escape_html;
		return `<div class="iran-help-item" ${target ? `data-target="${esc(target)}"` : ""}>
			<div class="iran-help-item-label">${esc(label)}${meta ? ` <span class="iran-help-item-meta">${esc(meta)}</span>` : ""}</div>
			${text ? `<div class="iran-help-item-text">${esc(text)}</div>` : ""}
		</div>`;
	},

	form_fields(doctype, explanations) {
		const meta = frappe.get_meta(doctype);
		const skip = ["Column Break", "Fold", "HTML", "Button", "Image", "Heading"];
		let html = "";
		let group = "";
		let count = 0;
		for (const df of meta.fields) {
			if (df.fieldtype === "Section Break" || df.fieldtype === "Tab Break") {
				group = df.label ? __(df.label) : group;
				if (df.label) html += `<div class="iran-help-group">${frappe.utils.escape_html(__(df.label))}</div>`;
				continue;
			}
			if (skip.includes(df.fieldtype) || df.hidden || !df.label) continue;
			// On an open form, only the fields it shows now (others depend on choices made in it)
			const field = cur_frm && cur_frm.doctype === doctype && cur_frm.fields_dict[df.fieldname];
			if (field && field.disp_status === "None") continue;
			const text =
				explanations[df.fieldname] || (df.description ? __(df.description) : "") || this.type_text(df);
			const flags = [this.type_text(df)];
			if (df.reqd) flags.push(__("required"));
			if (df.read_only) flags.push(__("filled by the system"));
			html += this.item(__(df.label), text === flags[0] ? "" : text, flags.join("، "), `field:${df.fieldname}`);
			count++;
		}
		const hint = cur_frm ? `<p class="text-muted small">${__("Click a field to find it on the form.")}</p>` : "";
		return this.section(__("Fields ({0})", [count]), hint + html);
	},

	docstatus_help() {
		return `<ul class="iran-help-steps">
			<li>${__("Draft: can be edited freely; it has no effect on accounts or stock yet.")}</li>
			<li>${__("Submitted: final; accounts and stock are updated. It can no longer be edited.")}</li>
			<li>${__("Cancelled: a submitted document is reversed with Cancel; use Amend to make a corrected copy.")}</li>
		</ul>`;
	},

	list_help(doctype) {
		const meta = frappe.get_meta(doctype);
		let html = `<ul class="iran-help-steps">
			<li>${__("Click a row to open it; «+ Add» makes a new one.")}</li>
			<li>${__("Filter by the boxes above the list, or with «Filter»; sort with the sort button.")}</li>
			<li>${__("Tick rows to edit, print, export or delete several at once from «Actions».")}</li>
			<li>${__("Switch between list, report, kanban and other views from the view menu.")}</li>
		</ul>`;
		const status = meta.fields.find((df) => df.fieldname === "status" && df.fieldtype === "Select");
		if (status && status.options) {
			const states = status.options
				.split("\n")
				.filter(Boolean)
				.map((s) => `<span class="iran-help-chip">${frappe.utils.escape_html(__(s))}</span>`)
				.join(" ");
			html += `<div class="iran-help-group">${__("Statuses")}</div><div>${states}</div>`;
		}
		return this.section(__("Working with the list"), html);
	},

	report_parts(explanations) {
		const report = frappe.query_report;
		if (!report) return "";
		let html = "";
		const filters = (report.filters || []).filter((f) => f.df && f.df.label && !f.df.hidden);
		if (filters.length) {
			html += `<div class="iran-help-group">${__("Filters")}</div>`;
			for (const f of filters) {
				const df = f.df;
				const text = explanations[df.fieldname] || (df.description ? __(df.description) : "") || "";
				html += this.item(__(df.label), text, this.type_text(df), `filter:${df.fieldname}`);
			}
		}
		const columns = (report.columns || []).filter((c) => c.label);
		if (columns.length) {
			html += `<div class="iran-help-group">${__("Columns")}</div><div>${columns
				.map((c) => `<span class="iran-help-chip">${frappe.utils.escape_html(__(c.label))}</span>`)
				.join(" ")}</div>`;
		}
		html += `<p class="text-muted small">${__(
			"Change the filters and the report refreshes. Export to Excel or print from the menu."
		)}</p>`;
		return this.section(__("Parts of the report"), html);
	},

	navigation_help() {
		return `<ul class="iran-help-steps">
			<li>${__("The home screen icons open each part of the system; the side menu lists its pages.")}</li>
			<li>${__("Search (Ctrl+K) finds any page, report or record by name.")}</li>
			<li>${__("«My Tasks» next to the bell lists what waits for you.")}</li>
			<li>${__("The assistant at the bottom of the screen answers questions and creates drafts in Persian.")}</li>
		</ul>`;
	},

	point_to($item) {
		const [kind, name] = ($item.attr("data-target") || "").split(":");
		let $target = null;
		if (kind === "field" && cur_frm) {
			cur_frm.scroll_to_field(name, false);
			const field = cur_frm.get_field(name);
			$target = field && field.$wrapper;
		} else if (kind === "filter" && frappe.query_report) {
			const filter = frappe.query_report.get_filter(name);
			$target = filter && filter.$wrapper;
		}
		if ($target && $target.length) {
			$target[0].scrollIntoView({ block: "center", behavior: "smooth" });
			$target.addClass("iran-help-highlight");
			setTimeout(() => $target.removeClass("iran-help-highlight"), 2500);
		}
	},

	// The full guide the AI model writes once; everyone sees the saved text afterwards
	saved_section(page, guide) {
		this.page = page;
		const saved = guide.saved;
		const ai_on = frappe.boot.iran_ai_model_enabled;
		const button = (label) =>
			`<button class="btn btn-sm btn-default iran-help-generate">${frappe.utils.icon("sparkles", "sm")} ${label}</button>`;
		let html = "";
		if (saved && saved.status === "Ready" && saved.content) {
			html = `<div class="iran-help-saved">${frappe.markdown(frappe.utils.escape_html(saved.content))}</div>`;
			html += `<div class="iran-help-saved-note">${
				saved.source === "Manual" ? __("Written by your administrator") : __("Written by the AI model and saved")
			}</div>`;
			if (guide.can_regenerate && ai_on && saved.source !== "Manual") {
				html += button(__("Write it again"));
			}
		} else if (saved && saved.status === "Generating") {
			html = `<div class="text-muted">${__("The full guide is being written; it takes a minute or two…")}</div>`;
			this.wait_for(page);
		} else if (ai_on) {
			if (saved && saved.status === "Failed") {
				html += `<div class="text-danger small">${frappe.utils.escape_html(saved.error || "")}</div>`;
			}
			html += `<p class="text-muted small">${__(
				"A step-by-step guide for beginners, written once by the AI model and saved for everyone."
			)}</p>`;
			html += button(__("Write the full guide"));
		}
		return html ? this.section(__("Complete guide"), html) : "";
	},

	async generate() {
		const page = this.page;
		if (!page) return;
		this.$panel.find(".iran-help-generate").prop("disabled", true);
		await frappe.xcall("iran_erp.help.generate", { kind: page.kind, name: page.name }, "POST");
		this.wait_for(page, true);
	},

	wait_for(page, refresh_now) {
		const key = `${page.kind}:${page.name}`;
		clearTimeout(this.waiting);
		const check = async () => {
			delete this.guides[key];
			const guide = await this.guide(page.kind, page.name);
			const status = guide.saved && guide.saved.status;
			const same_page = this.page && `${this.page.kind}:${this.page.name}` === key;
			if (!same_page || !this.$panel.is(":visible")) return;
			if (status === "Generating") {
				if (refresh_now) {
					refresh_now = false;
					this.$panel.find(".iran-help-body").html(await this.render(this.current));
				}
				this.waiting = setTimeout(check, 4000);
				return;
			}
			this.$panel.find(".iran-help-body").html(await this.render(this.current));
		};
		this.waiting = setTimeout(check, refresh_now ? 0 : 4000);
	},

};

$(document).on("app_ready", () => {
	const add = () => setTimeout(() => iran_erp.help.add_button(), 400);
	add();
	frappe.router.on("change", add);
	// Pages that render after the route change (forms, reports) get the button once they exist
	let pending = null;
	new MutationObserver(() => {
		clearTimeout(pending);
		pending = setTimeout(() => iran_erp.help.add_button(), 500);
	}).observe(document.body, { childList: true, subtree: true });
});
