// «آموزش»: a button on every page that opens the complete guide of the page.
//
// The guide (iran_erp/help/content, then iran_erp/help/guides.py) says what the page is for, what
// has to exist first, the steps, what each field means, what saving changes, the common mistakes
// and tips, with a worked example. Every part of the page the guide talks about can be found:
// a click on it draws a box around that part of the page. «تور قدم‌به‌قدم» walks through the
// page's parts one by one. Fields without a written explanation are explained from their
// description or their type.

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

	// The guide of another part of the system, from a «بیشتر بدانید» link: show({ kind: "list", doctype })
	show(context) {
		return this.toggle(context);
	},

	make_panel() {
		this.$panel = $(`
			<div class="iran-help-panel" dir="rtl">
				<div class="iran-help-header">
					<div class="iran-help-title"></div>
					<button class="btn btn-xs btn-default iran-help-close" title="${__("Close")}">${frappe.utils.icon("x", "sm")}</button>
				</div>
				<div class="iran-help-toolbar">
					<button class="btn btn-sm btn-primary iran-help-tour-start">${frappe.utils.icon("play", "sm")} تور قدم‌به‌قدم این صفحه</button>
					<input type="search" class="form-control input-xs iran-help-search" placeholder="جستجو در راهنما…">
				</div>
				<div class="iran-help-body"></div>
			</div>`).appendTo(document.body);
		this.$panel.find(".iran-help-close").on("click", () => this.hide());
		this.$panel.on("click", "[data-target]", (e) => {
			e.stopPropagation();
			this.point_to($(e.currentTarget));
		});
		this.$panel.on("click", ".iran-help-related", (e) => {
			e.preventDefault();
			const doctype = $(e.currentTarget).attr("data-doctype");
			if (doctype) this.toggle({ kind: "list", doctype });
		});
		this.$panel.on("click", ".iran-help-back", (e) => {
			e.preventDefault();
			this.toggle(this.context());
		});
		this.$panel.on("click", ".iran-help-tour-start", () => this.tour.start());
		this.$panel.on("input", ".iran-help-search", (e) => this.filter(e.target.value));
		frappe.router.on("change", () => {
			this.hide();
			this.tour.stop();
		});
		// A click anywhere else, or Esc, takes the box away
		$(document).on("mousedown.iran_help", (e) => {
			if (!$(e.target).closest(".iran-help-panel, .iran-help-tour-bubble").length) this.unframe();
		});
		$(document).on("keydown.iran_help", (e) => {
			if (e.key === "Escape") this.unframe();
		});
	},

	hide() {
		if (this.$panel) this.$panel.hide();
		this.unframe();
	},

	async toggle(context) {
		if (!context && this.$panel && this.$panel.is(":visible")) {
			this.hide();
			return;
		}
		if (!this.$panel) this.make_panel();
		this.tour.stop();
		this.$panel.show();
		this.$panel.find(".iran-help-search").val("");
		this.$panel.find(".iran-help-body").html(`<div class="text-muted">${__("Loading…")}</div>`);
		if (!this.field_types) {
			this.field_types = await frappe.xcall("iran_erp.help.get_field_types");
		}
		context = context || this.context();
		this.current = context;
		const html = await this.render(context);
		this.$panel.find(".iran-help-body").html(html).scrollTop(0);
		// The tour walks through the page on screen, not another page's guide
		const own = JSON.stringify(context) === JSON.stringify(this.context());
		this.$panel.find(".iran-help-tour-start").toggle(own);
	},

	async guide(kind, name) {
		const key = `${kind}:${name}`;
		if (!(key in this.guides)) {
			this.guides[key] = await frappe.xcall("iran_erp.help.get_guide", { kind, name });
		}
		return this.guides[key] || {};
	},

	async current_guide(context) {
		context = context || this.context();
		if (context.kind === "form" || context.kind === "list") return this.guide("doctype", context.doctype);
		if (context.kind === "report") return this.guide("report", context.report);
		if (context.kind === "workspace") return this.guide("workspace", context.workspace);
		return {};
	},

	async render(context) {
		const esc = frappe.utils.escape_html;
		let title = "";
		const parts = [];
		const own = JSON.stringify(context) === JSON.stringify(this.context());
		if (!own) {
			parts.push(
				`<a href="#" class="iran-help-back">${frappe.utils.icon("arrow-right", "xs")} راهنمای همین صفحه</a>`
			);
		}
		if (context.kind === "form" || context.kind === "list") {
			const doctype = context.doctype;
			await frappe.model.with_doctype(doctype);
			const guide = await this.guide("doctype", doctype);
			title = __(doctype);
			parts.push(this.about(guide.about || __("This page holds {0} records.", [__(doctype)])));
			parts.push(this.example(guide.example));
			parts.push(this.list_section("پیش از شروع", guide.before, "iran-help-before"));
			if (guide.steps && guide.steps.length) parts.push(this.steps(guide.steps));
			if (guide.after) {
				const title_after = guide.is_submittable ? "پس از «ثبت نهایی» چه می‌شود؟" : "پس از ذخیره";
				parts.push(this.section(title_after, `<p>${esc(guide.after)}</p>`));
			}
			if (context.kind === "form" && own) {
				parts.push(this.form_fields(doctype, guide.fields || {}));
				if (guide.is_submittable) parts.push(this.section(__("Document states"), this.docstatus_help()));
			} else if (context.kind === "form" || !own) {
				parts.push(this.field_notes(doctype, guide.fields || {}));
			} else {
				parts.push(this.list_help(doctype));
			}
			parts.push(this.list_section("اشتباه‌های رایج", guide.mistakes, "iran-help-mistakes"));
			parts.push(this.list_section("نکته‌ها", guide.tips, "iran-help-tips"));
			parts.push(this.related(guide.related));
			if (guide.module_about) parts.push(this.section(__("Part of the system"), `<p>${esc(guide.module_about)}</p>`));
			parts.push(this.saved_section(guide));
		} else if (context.kind === "report") {
			const guide = await this.guide("report", context.report);
			title = __(context.report);
			parts.push(this.about(guide.about || __("A report.")));
			parts.push(this.example(guide.example));
			if (guide.steps && guide.steps.length) parts.push(this.steps(guide.steps, "چطور از این گزارش استفاده کنم؟"));
			parts.push(this.report_parts(guide.fields || {}, guide.columns || {}));
			parts.push(this.list_section("اشتباه‌های رایج", guide.mistakes, "iran-help-mistakes"));
			parts.push(this.list_section("نکته‌ها", guide.tips, "iran-help-tips"));
			parts.push(this.related(guide.related));
			parts.push(this.saved_section(guide));
		} else if (context.kind === "workspace") {
			const guide = await this.guide("workspace", context.workspace);
			title = __(context.workspace);
			parts.push(
				this.about(
					guide.about ||
						__("This workspace gathers the pages of one part of the system. Use the side menu to open them.")
				)
			);
			if (guide.steps && guide.steps.length) parts.push(this.steps(guide.steps, "از کجا شروع کنم؟"));
			parts.push(this.list_section("نکته‌ها", guide.tips, "iran-help-tips"));
			parts.push(this.related(guide.related, "صفحه‌های این بخش"));
			parts.push(this.section(__("How to move around"), this.navigation_help()));
			parts.push(this.saved_section(guide));
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

	example(text) {
		if (!text) return "";
		return `<div class="iran-help-example"><b>${__("Example")}:</b> ${frappe.utils.escape_html(text)}</div>`;
	},

	section(title, html, css_class = "") {
		return `<div class="iran-help-section ${css_class}"><div class="iran-help-section-title">${frappe.utils.escape_html(
			title
		)}</div>${html}</div>`;
	},

	list_section(title, items, css_class) {
		if (!items || !items.length) return "";
		const list = items.map((s) => `<li>${frappe.utils.escape_html(s)}</li>`).join("");
		return this.section(title, `<ul class="iran-help-list">${list}</ul>`, css_class);
	},

	steps(steps, title) {
		const items = steps.map((s) => `<li>${frappe.utils.escape_html(s)}</li>`).join("");
		return this.section(title || "قدم‌به‌قدم", `<ol class="iran-help-steps">${items}</ol>`);
	},

	related(names, title) {
		const readable = (frappe.boot.user && frappe.boot.user.can_read) || [];
		const links = (names || [])
			.filter((name) => readable.includes(name))
			.map(
				(name) =>
					`<a href="#" class="iran-help-chip iran-help-related" data-doctype="${frappe.utils.escape_html(name)}">${frappe.utils.escape_html(
						__(name)
					)}</a>`
			)
			.join(" ");
		if (!links) return "";
		return this.section(title || "صفحه‌های مرتبط", `<div>${links}</div>`);
	},

	type_text(df) {
		const text = (this.field_types && this.field_types[df.fieldtype]) || __(df.fieldtype);
		return text.replace("{options}", __(df.options || ""));
	},

	item(label, text, meta, target) {
		const esc = frappe.utils.escape_html;
		return `<div class="iran-help-item" ${target ? `data-target="${esc(target)}" data-label="${esc(label)}"` : ""}>
			<div class="iran-help-item-label">${target ? frappe.utils.icon("crosshair", "xs") + " " : ""}${esc(label)}${
				meta ? ` <span class="iran-help-item-meta">${esc(meta)}</span>` : ""
			}</div>
			${text ? `<div class="iran-help-item-text">${esc(text)}</div>` : ""}
		</div>`;
	},

	form_fields(doctype, explanations) {
		const meta = frappe.get_meta(doctype);
		const skip = ["Column Break", "Fold", "HTML", "Button", "Image", "Heading"];
		const esc = frappe.utils.escape_html;
		let html = "";
		let count = 0;
		for (const df of meta.fields) {
			if (df.fieldtype === "Section Break" || df.fieldtype === "Tab Break") {
				if (!df.label) continue;
				const target = df.fieldtype === "Tab Break" ? `tab:${df.fieldname}` : `section:${df.fieldname}`;
				html += `<div class="iran-help-group" data-target="${esc(target)}" data-label="${esc(__(df.label))}">${esc(
					__(df.label)
				)}</div>`;
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
		const hint = cur_frm
			? `<p class="text-muted small">روی هر فیلد یا بخش کلیک کنید تا جای آن در فرم با کادر نشان داده شود.</p>`
			: "";
		return this.section(__("Fields ({0})", [count]), hint + html);
	},

	// The written explanations of a document's fields, when its form is not the page on screen
	field_notes(doctype, explanations) {
		const meta = frappe.get_meta(doctype);
		const html = Object.entries(explanations)
			.map(([fieldname, text]) => {
				const df = meta.fields.find((d) => d.fieldname === fieldname);
				return df ? this.item(__(df.label), text, this.type_text(df)) : "";
			})
			.join("");
		return html ? this.section("فیلدهای مهم", html) : "";
	},

	docstatus_help() {
		return `<ul class="iran-help-list">
			<li>${__("Draft: can be edited freely; it has no effect on accounts or stock yet.")}</li>
			<li>${__("Submitted: final; accounts and stock are updated. It can no longer be edited.")}</li>
			<li>${__("Cancelled: a submitted document is reversed with Cancel; use Amend to make a corrected copy.")}</li>
		</ul>`;
	},

	// The parts of a list page, each one found on the page with a click
	LIST_PARTS: [
		["el:.standard-filter-section", "جستجوی سریع", "در این کادرها بخشی از نام، شماره یا هر ستون را بنویسید تا فهرست همان لحظه محدود شود."],
		["el:.filter-selector", "فیلتر", "شرط‌های دقیق‌تر بسازید؛ مثلاً «وضعیت = پرداخت‌نشده» و «تاریخ از ۱۴۰۵/۰۷/۰۱». چند شرط با هم جمع می‌شوند."],
		["el:.sort-selector", "مرتب‌سازی", "ترتیب ردیف‌ها را عوض کنید؛ مثلاً جدیدترین در بالا یا بر اساس مبلغ."],
		["el:.frappe-list .result", "فهرست", "روی هر ردیف کلیک کنید تا باز شود. با تیک ردیف‌ها، چند ردیف را با هم ویرایش، چاپ یا حذف کنید (از «اقدامات»)."],
		["el:.view-switcher", "نما", "نمایش را عوض کنید: فهرست، گزارش (جدول با جمع ستون‌ها)، کانبان، تقویم و ..."],
		["el:.page-actions .primary-action", "افزودن", "یک رکورد تازه بسازید."],
		["el:.list-paging-area", "تعداد ردیف‌ها", "چند ردیف در هر صفحه نمایش داده شود (۲۰، ۱۰۰، ۵۰۰، ...)."],
	],

	list_help(doctype) {
		const meta = frappe.get_meta(doctype);
		let html = this.LIST_PARTS.filter(([target]) => this.find(target))
			.map(([target, label, text]) => this.item(label, text, "", target))
			.join("");
		const status = meta.fields.find((df) => df.fieldname === "status" && df.fieldtype === "Select");
		if (status && status.options) {
			const states = status.options
				.split("\n")
				.filter(Boolean)
				.map((s) => `<span class="iran-help-chip">${frappe.utils.escape_html(__(s))}</span>`)
				.join(" ");
			html += `<div class="iran-help-group">${__("Statuses")}</div><div>${states}</div>`;
		}
		return this.section("بخش‌های این صفحه", html);
	},

	report_parts(explanations, column_notes) {
		const report = frappe.query_report;
		if (!report || this.context().kind !== "report") {
			const notes = Object.entries(explanations).map(([name, text]) => this.item(name, text)).join("");
			return notes ? this.section("فیلترها", notes) : "";
		}
		let html = "";
		const filters = (report.filters || []).filter((f) => f.df && f.df.label && !f.df.hidden);
		if (filters.length) {
			html += `<div class="iran-help-group" data-target="el:.page-form" data-label="${__("Filters")}">${__("Filters")}</div>`;
			for (const f of filters) {
				const df = f.df;
				const text = explanations[df.fieldname] || (df.description ? __(df.description) : "") || "";
				html += this.item(__(df.label), text, this.type_text(df), `filter:${df.fieldname}`);
			}
		}
		const columns = (report.columns || []).filter((c) => c.label);
		if (columns.length) {
			html += `<div class="iran-help-group" data-target="el:.report-wrapper .datatable" data-label="${__("Columns")}">${__("Columns")}</div>`;
			for (const c of columns) {
				const note = column_notes[c.fieldname] || column_notes[c.label] || "";
				const label = __(c.label).replace(/\(IRR\)/g, "(ریال)");
				html += this.item(label, note, "", `column:${c.fieldname}`);
			}
		}
		html += `<p class="text-muted small">${__(
			"Change the filters and the report refreshes. Export to Excel or print from the menu."
		)}</p>`;
		return this.section(__("Parts of the report"), html);
	},

	NAVIGATION: [
		["el:.body-sidebar", "منوی کناری", "صفحه‌های همین بخش اینجا فهرست شده‌اند؛ روی هر کدام کلیک کنید."],
		["el:.sidebar-header", "نام بخش", "با کلیک روی نام بخش، به بخش‌های دیگر (فروش، خرید، انبار، ...) بروید."],
		["el:.dock", "نوار برنامه‌ها", "میان‌بر بخش‌های اصلی سیستم و منوی کاربر (پایین نوار)."],
		["el:.iran-ai-launcher", "دستیار هوشمند", "سؤالتان را به فارسی بنویسید یا بگویید؛ مثلاً «فاکتور فروش برای آقای احمدی ۱۰ عدد کابل»."],
	],

	navigation_help() {
		let html = this.NAVIGATION.filter(([target]) => this.find(target))
			.map(([target, label, text]) => this.item(label, text, "", target))
			.join("");
		html += `<ul class="iran-help-list">
			<li>${__("Search (Ctrl+K) finds any page, report or record by name.")}</li>
			<li>${__("«My Tasks» next to the bell lists what waits for you.")}</li>
		</ul>`;
		return html;
	},

	// Text typed in the search box keeps the entries that contain it
	filter(text) {
		const query = (text || "").trim();
		const $body = this.$panel.find(".iran-help-body");
		$body.find(".iran-help-item, .iran-help-list li, .iran-help-steps li").each((_, el) => {
			$(el).toggle(!query || el.textContent.includes(query));
		});
		$body.find(".iran-help-section").each((_, el) => {
			const $el = $(el);
			const visible = !query || $el.text().includes(query);
			$el.toggle(visible);
		});
		$body.find(".iran-help-about, .iran-help-example").toggle(!query);
	},

	// The element of the page a target names: "field:customer", "filter:company", "column:account",
	// "section:items_section", "tab:payments_tab" or "el:<selector>"
	find(target) {
		const index = target.indexOf(":");
		const kind = target.slice(0, index);
		const name = target.slice(index + 1);
		const visible = (el) => el && el.isConnected && el.getClientRects().length > 0;
		if (kind === "field" && cur_frm) {
			const field = cur_frm.get_field(name);
			return field && field.$wrapper && field.$wrapper[0];
		}
		if ((kind === "section" || kind === "tab") && cur_frm) {
			const field = cur_frm.get_field(name);
			if (kind === "tab") {
				const tab = cur_frm.layout && (cur_frm.layout.tabs || []).find((t) => t.df.fieldname === name);
				return tab && tab.tab_link && tab.tab_link[0];
			}
			return field && field.wrapper && (field.wrapper[0] || field.wrapper);
		}
		if (kind === "filter" && frappe.query_report) {
			const filter = frappe.query_report.get_filter(name);
			return filter && filter.$wrapper && filter.$wrapper[0];
		}
		if (kind === "column" && frappe.query_report && frappe.query_report.datatable) {
			const columns = frappe.query_report.datatable.getColumns();
			const column = columns.find((c) => c.id === name || c.fieldname === name || c.docfield?.fieldname === name);
			if (!column) return null;
			const head = document.querySelector(`.report-wrapper .dt-cell--header.dt-cell--col-${column.colIndex}`);
			const cells = document.querySelectorAll(`.report-wrapper .dt-scrollable .dt-cell--col-${column.colIndex}`);
			return head ? [head, cells[cells.length - 1]].filter(Boolean) : null;
		}
		if (kind === "el") {
			const el = [...document.querySelectorAll(name)].find(visible);
			return el || null;
		}
		return null;
	},

	point_to($item) {
		const target = $item.attr("data-target") || "";
		const label = $item.attr("data-label") || $item.find(".iran-help-item-label").text().trim();
		this.$panel.find(".iran-help-item.active, .iran-help-group.active").removeClass("active");
		$item.addClass("active");
		const [kind, name] = [target.split(":")[0], target.slice(target.indexOf(":") + 1)];
		// A field or section on a tab that is not open: open its tab first
		if (["field", "section"].includes(kind) && cur_frm) cur_frm.scroll_to_field(name, false);
		if (kind === "tab" && cur_frm) {
			const tab = cur_frm.layout && (cur_frm.layout.tabs || []).find((t) => t.df.fieldname === name);
			if (tab) tab.set_active();
		}
		setTimeout(() => {
			const el = this.find(target);
			if (el) this.frame(el, label);
			else frappe.show_alert({ message: "این بخش الان روی صفحه دیده نمی‌شود.", indicator: "orange" }, 3);
		}, 120);
	},

	// A box drawn around a part of the page, following it while the page scrolls
	frame(target, label) {
		this.unframe();
		const elements = (Array.isArray(target) ? target : [target]).filter(Boolean);
		if (!elements.length) return;
		elements[0].scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
		const $box = $(`<div class="iran-help-frame"><span class="iran-help-frame-label"></span></div>`).appendTo(
			document.body
		);
		$box.find(".iran-help-frame-label").text(label || "").toggle(Boolean(label));
		const place = () => {
			if (!elements[0].isConnected) return this.unframe();
			const rects = elements.map((el) => el.getBoundingClientRect());
			const top = Math.min(...rects.map((r) => r.top));
			const left = Math.min(...rects.map((r) => r.left));
			const right = Math.max(...rects.map((r) => r.right));
			const bottom = Math.max(...rects.map((r) => r.bottom));
			$box.css({ top: top - 6, left: left - 6, width: right - left + 12, height: bottom - top + 12 });
			this.avoid({ top, left, right, bottom });
			this.frame_loop = requestAnimationFrame(place);
		};
		place();
		this.$frame = $box;
		return $box;
	},

	unframe() {
		cancelAnimationFrame(this.frame_loop);
		if (this.$frame) this.$frame.remove();
		this.$frame = null;
		if (this.$panel) this.$panel.removeClass("iran-help-panel-right");
	},

	// The panel moves to the other side of the screen when it covers the part being shown
	avoid(rect) {
		if (!this.$panel || !this.$panel.is(":visible")) return;
		const width = this.$panel.outerWidth() + 24;
		const under_left = rect.left < width;
		const under_right = rect.right > window.innerWidth - width;
		this.$panel.toggleClass("iran-help-panel-right", under_left && !under_right);
	},

	// A guide an administrator wrote (or the AI model wrote earlier) for this page, shown with the rest
	saved_section(guide) {
		const saved = guide.saved;
		if (!(saved && saved.status === "Ready" && saved.content)) return "";
		const html = `<div class="iran-help-saved">${frappe.markdown(frappe.utils.escape_html(saved.content))}</div>`;
		return this.section("توضیحات بیشتر", html);
	},
};

// «تور قدم‌به‌قدم»: the parts of the page one after another, each in a box with its explanation
iran_erp.help.tour = {
	steps: [],
	index: 0,

	async start() {
		const help = iran_erp.help;
		const context = help.context();
		const guide = await help.current_guide(context);
		this.steps = this.build(context, guide).filter((step) => help.find(step.target));
		if (!this.steps.length) {
			frappe.show_alert({ message: "برای این صفحه توری آماده نیست.", indicator: "orange" });
			return;
		}
		if (help.$panel) help.$panel.hide();
		this.index = 0;
		this.active = true;
		$(document).on("keydown.iran_tour", (e) => {
			if (e.key === "Escape") this.stop();
			// In a right-to-left page the next step is to the left
			if (e.key === "ArrowLeft") this.go(1);
			if (e.key === "ArrowRight") this.go(-1);
		});
		this.show();
	},

	stop() {
		if (!this.active) return;
		this.active = false;
		$(document).off("keydown.iran_tour");
		if (this.$bubble) this.$bubble.remove();
		this.$bubble = null;
		$("body").removeClass("iran-help-touring");
		iran_erp.help.unframe();
	},

	go(step) {
		const next = this.index + step;
		if (next < 0) return;
		if (next >= this.steps.length) return this.stop();
		this.index = next;
		this.show();
	},

	show() {
		const help = iran_erp.help;
		const step = this.steps[this.index];
		const [kind, name] = [step.target.split(":")[0], step.target.slice(step.target.indexOf(":") + 1)];
		if (["field", "section"].includes(kind) && cur_frm) cur_frm.scroll_to_field(name, false);
		$("body").addClass("iran-help-touring");
		setTimeout(() => {
			const el = help.find(step.target);
			if (!el) return this.go(1);
			const $box = help.frame(el, "");
			this.bubble(step, $box);
		}, 150);
	},

	bubble(step, $box) {
		const esc = frappe.utils.escape_html;
		const digits = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
		if (this.$bubble) this.$bubble.remove();
		const last = this.index === this.steps.length - 1;
		this.$bubble = $(`
			<div class="iran-help-tour-bubble" dir="rtl">
				<div class="iran-help-tour-count">${digits(this.index + 1)} از ${digits(this.steps.length)}</div>
				<div class="iran-help-tour-title">${esc(step.title)}</div>
				<div class="iran-help-tour-text">${esc(step.text)}</div>
				<div class="iran-help-tour-buttons">
					<button class="btn btn-xs btn-default iran-help-tour-end">پایان</button>
					<span>
						${this.index ? `<button class="btn btn-xs btn-default iran-help-tour-prev">قبلی</button>` : ""}
						<button class="btn btn-xs btn-primary iran-help-tour-next">${last ? "تمام" : "بعدی"}</button>
					</span>
				</div>
			</div>`).appendTo(document.body);
		this.$bubble.find(".iran-help-tour-next").on("click", () => this.go(1));
		this.$bubble.find(".iran-help-tour-prev").on("click", () => this.go(-1));
		this.$bubble.find(".iran-help-tour-end").on("click", () => this.stop());
		this.$bubble.find(".iran-help-tour-next").trigger("focus");
		const place = () => {
			if (!this.$bubble || !$box || !$box[0].isConnected) return;
			const box = $box[0].getBoundingClientRect();
			const bubble = this.$bubble[0].getBoundingClientRect();
			const room_below = window.innerHeight - box.bottom;
			let top = room_below > bubble.height + 16 ? box.bottom + 10 : box.top - bubble.height - 10;
			if (top < 8) top = Math.min(window.innerHeight - bubble.height - 8, box.top + 10);
			let left = box.right - bubble.width;
			left = Math.max(8, Math.min(left, window.innerWidth - bubble.width - 8));
			this.$bubble.css({ top, left });
			this.bubble_loop = requestAnimationFrame(place);
		};
		cancelAnimationFrame(this.bubble_loop);
		// After the smooth scroll has moved the part into view
		setTimeout(place, 50);
	},

	// The steps for the page on screen, from its guide where it has one
	build(context, guide) {
		const fields = guide.fields || {};
		const help_step = {
			target: "el:.iran-help-button",
			title: "آموزش",
			text: "هر وقت سؤالی داشتید، این دکمه راهنمای کامل همین صفحه را باز می‌کند: مراحل کار، معنی هر فیلد، اشتباه‌های رایج و یک مثال.",
		};
		if (context.kind === "form") {
			const steps = [
				{ target: "el:.page-head .title-area", title: "عنوان و وضعیت", text: "نام این سند و وضعیت آن (پیش‌نویس، ثبت‌شده، لغو شده، ...) اینجا دیده می‌شود." },
				{ target: "el:.form-tabs-list", title: "زبانه‌ها", text: "فیلدهای فرم در چند زبانه دسته‌بندی شده‌اند. اطلاعات اصلی در زبانه اول است؛ بقیه را در صورت نیاز باز کنید." },
			];
			Object.entries(fields)
				.filter(([name]) => {
					const field = cur_frm && cur_frm.fields_dict[name];
					return field && field.disp_status !== "None";
				})
				.slice(0, 7)
				.forEach(([name, text]) => {
					const df = cur_frm.fields_dict[name].df;
					steps.push({ target: `field:${name}`, title: __(df.label), text });
				});
			steps.push(
				{
					target: "el:.page-actions .primary-action",
					title: "ذخیره و ثبت نهایی",
					text: guide.is_submittable
						? "اول «ذخیره» کنید تا پیش‌نویس نگه داشته شود. وقتی همه‌چیز درست بود «ثبت نهایی» را بزنید؛ پس از آن سند در حساب‌ها اثر می‌گذارد و فقط با «لغو» برمی‌گردد."
						: "تغییرات را با «ذخیره» نگه دارید.",
				},
				{ target: "el:.form-sidebar", title: "کناره فرم", text: "پیوست فایل، واگذاری کار به همکار، برچسب‌ها و اشتراک‌گذاری این سند." },
				{ target: "el:.new-timeline", title: "فعالیت‌ها و یادداشت‌ها", text: "تاریخچه همه تغییرات این سند و یادداشت‌هایی که همکاران نوشته‌اند. برای هماهنگی، همین‌جا یادداشت بگذارید." },
				help_step
			);
			return steps;
		}
		if (context.kind === "list") {
			return [
				{ target: "el:.page-head .title-area", title: __(context.doctype), text: guide.about || "فهرست همه رکوردهای این نوع." },
				...iran_erp.help.LIST_PARTS.map(([target, title, text]) => ({ target, title, text })),
				help_step,
			];
		}
		if (context.kind === "report") {
			const steps = [
				{ target: "el:.page-head .title-area", title: __(context.report), text: guide.about || "" },
				{ target: "el:.page-form", title: "فیلترها", text: "اول شرکت و بازه تاریخ را درست کنید؛ گزارش با هر تغییر فیلتر دوباره ساخته می‌شود." },
			];
			Object.entries(fields)
				.filter(([name]) => frappe.query_report && frappe.query_report.get_filter(name))
				.slice(0, 4)
				.forEach(([name, text]) => {
					const df = frappe.query_report.get_filter(name).df;
					steps.push({ target: `filter:${name}`, title: __(df.label), text });
				});
			steps.push(
				{ target: "el:.chart-wrapper", title: "نمودار", text: "خلاصه گزارش به شکل نمودار؛ روی هر بخش نمودار بروید تا مقدار آن را ببینید." },
				{ target: "el:.report-wrapper .datatable", title: "جدول گزارش", text: "روی عنوان هر ستون کلیک کنید تا مرتب شود یا آن را فیلتر کنید. روی ردیف‌های دارای پیوند کلیک کنید تا سند اصلی باز شود." },
				{ target: "el:.page-actions .custom-actions", title: "اقدامات", text: "برون‌بُرد به اکسل، چاپ و ذخیره همین تنظیمات گزارش از این منو انجام می‌شود." },
				help_step
			);
			return steps;
		}
		return [
			...iran_erp.help.NAVIGATION.map(([target, title, text]) => ({ target, title, text })),
			{ target: "el:.iran-help-button", title: "آموزش", text: help_step.text },
		];
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
