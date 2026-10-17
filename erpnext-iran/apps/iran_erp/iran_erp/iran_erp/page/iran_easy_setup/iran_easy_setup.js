// «راه‌اندازی آسان»: setting the system up in plain questions, one step at a time. Each step says
// what it is for, shows an example and links to the guide of the part it fills. See iran_erp/onboarding.py.

frappe.pages["iran-easy-setup"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Easy Setup"), single_column: true });
	wrapper.iran_setup = new IranSetupPage(page);
};

frappe.pages["iran-easy-setup"].on_page_show = function (wrapper) {
	wrapper.iran_setup && wrapper.iran_setup.load();
};

// Header words that name each column when a list is pasted from Excel
const PASTE_HEADERS = {
	name: ["نام", "name", "مشتری", "تامین", "تأمین", "طرف"],
	item_name: ["نام", "کالا", "خدمت", "item", "شرح"],
	bank: ["بانک", "bank"],
	account_name: ["عنوان", "نوع حساب", "account name"],
	account_number: ["شماره", "شبا", "number", "iban"],
	mobile: ["موبایل", "همراه", "تلفن", "mobile", "phone"],
	national_id: ["ملی", "شناسه", "national"],
	balance: ["مانده", "بدهی", "طلب", "بدهکار", "بستانکار", "مبلغ", "balance", "موجودی"],
	selling_price: ["فروش", "sell"],
	cost_price: ["خرید", "بهای", "cost"],
	qty: ["تعداد", "مقدار", "qty", "موجودی"],
	warehouse: ["انبار", "warehouse"],
	warehouse_name: ["انبار", "نام", "warehouse"],
	party: ["مشتری", "تامین", "تأمین", "طرف", "نام"],
	amount: ["مبلغ", "amount"],
	due_date: ["سررسید", "تاریخ", "due"],
	number: ["شماره", "صیادی", "number"],
	direction: ["نوع", "دریافتی", "پرداختی"],
};

class IranSetupPage {
	constructor(page) {
		this.page = page;
		this.$body = $(`
			<div class="iran-setup" dir="rtl">
				<div class="iran-setup-nav"></div>
				<div class="iran-setup-main"></div>
			</div>`).appendTo(page.main);
		this.$nav = this.$body.find(".iran-setup-nav");
		this.$main = this.$body.find(".iran-setup-main");
		this.current = null;
	}

	load() {
		return frappe.xcall("iran_erp.onboarding.get_state").then((state) => {
			this.state = state;
			const first_open = state.steps.find((s) => !s.done) || state.steps[state.steps.length - 1];
			const keep = this.current && state.steps.find((s) => s.key === this.current);
			this.show(keep ? this.current : first_open.key);
		});
	}

	render_nav() {
		const steps = this.state.steps;
		const done = steps.filter((s) => s.done).length;
		this.$nav.html(`
			<div class="iran-setup-progress">
				<div class="iran-setup-progress-text">${__("{0} of {1} steps done", [String(done), String(steps.length)])}</div>
				<div class="iran-setup-progress-bar"><span style="width:${Math.round((100 * done) / steps.length)}%"></span></div>
			</div>`);
		steps.forEach((step, i) => {
			$(`<button class="iran-setup-nav-item"></button>`)
				.toggleClass("active", step.key === this.current)
				.toggleClass("done", !!step.done)
				.append($(`<span class="iran-setup-nav-mark"></span>`).text(step.done ? "✓" : i + 1))
				.append($(`<span></span>`).text(step.title))
				.on("click", () => this.leave(() => this.show(step.key)))
				.appendTo(this.$nav);
		});
	}

	// Rows typed into a step are lost unless saved; ask before going elsewhere
	leave(go) {
		const changed =
			this.form && this.saved_values !== undefined && JSON.stringify(this.form.get_values(true)) !== this.saved_values;
		if (!changed) return go();
		frappe.confirm("آنچه در این قدم نوشته‌اید ذخیره نشده است. بدون ذخیره می‌روید؟", go);
	}

	step(key) {
		return this.state.steps.find((s) => s.key === key);
	}

	show(key) {
		this.current = key;
		this.render_nav();
		const step = this.step(key);
		const index = this.state.steps.indexOf(step);
		this.$main.empty();
		const $card = $(`
			<div class="iran-setup-card">
				<div class="iran-setup-step-number"></div>
				<h3 class="iran-setup-title"></h3>
				<p class="iran-setup-intro"></p>
				<div class="iran-setup-example"><b>مثال:</b> <span></span></div>
				<button class="btn btn-xs btn-default iran-setup-learn"></button>
				<div class="iran-setup-form"></div>
				<div class="iran-setup-actions"></div>
			</div>`).appendTo(this.$main);
		$card.find(".iran-setup-step-number").text(__("Step {0} of {1}", [String(index + 1), String(this.state.steps.length)]));
		$card.find(".iran-setup-title").text(step.title);
		$card.find(".iran-setup-intro").text(step.intro);
		$card.find(".iran-setup-example span").text(step.example);
		$card
			.find(".iran-setup-learn")
			.html(`${frappe.utils.icon("book-open", "xs")} <span></span>`)
			.on("click", () => iran_erp.help.show({ kind: "list", doctype: step.learn }))
			.find("span")
			.text(__("Learn more: {0}", [__(step.learn)]));
		this.$form = $card.find(".iran-setup-form");
		this.$actions = $card.find(".iran-setup-actions");
		this.form = null;
		this.saved_values = undefined;
		if (key === "review") return this.render_review(index);
		this.render_form(step);
		this.render_actions(index);
	}

	fields_for(step) {
		const answers = this.state.answers;
		const data = this.state.data || {};
		const options = (map) => Object.entries(map).map(([value, label]) => ({ value, label }));
		if (step.key === "business") {
			return [
				{
					fieldname: "trade_name",
					fieldtype: "Data",
					label: "نام کسب‌وکار شما",
					default: answers.trade_name || "",
					description: "نامی که مشتری‌ها می‌شناسند، مثلاً «نمایشگاه خودرو ورون». روی داشبورد، چاپ‌ها و صفحه‌ی سرمایه‌گذاران نوشته می‌شود.",
				},
				{
					fieldname: "trade_phone",
					fieldtype: "Data",
					label: "تلفن",
					default: answers.trade_phone || "",
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "business_type",
					fieldtype: "Select",
					label: "کار شما چیست؟",
					options: options(this.state.business_types),
					default: answers.business_type || "Shop",
					reqd: 1,
				},
				...Object.entries(this.state.business_features || {}).map(([type, spec]) => ({
					fieldname: spec.field,
					fieldtype: "MultiCheck",
					label: "کدام‌ها را دارید؟ (هر وقت خواستید می‌توانید عوضشان کنید)",
					columns: 1,
					depends_on: `eval:doc.business_type=='${type}'`,
					options: spec.choices.map(([value, label, description]) => ({
						value,
						label: `${label} — ${description}`,
						checked: answers.business_features ? answers.business_features.includes(value) : 1,
					})),
				})),
				{
					fieldname: "parkings",
					fieldtype: "Small Text",
					label: "پارکینگ‌ها (نام هر پارکینگ در یک خط)",
					default: answers.parkings || "",
					depends_on: "eval:doc.business_type=='Car Dealership'",
					description: "مثلاً «پارکینگ اصلی» و «پارکینگ طبقه منفی یک». جای هر خودرو در پرونده‌اش ثبت می‌شود.",
				},
				{
					fieldname: "sells",
					fieldtype: "Select",
					label: "چه می‌فروشید؟",
					depends_on: "eval:doc.business_type!='Car Dealership'",
					options: options(this.state.sells),
					default: answers.sells || "Goods",
					reqd: 1,
				},
				{
					fieldname: "has_warehouse",
					fieldtype: "Check",
					label: "کالا در انبار نگه می‌دارم",
					default: answers.has_warehouse ?? 1,
					depends_on: "eval:doc.sells != 'Services' && doc.business_type!='Car Dealership'",
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "vat_registered",
					fieldtype: "Check",
					label: "مشمول مالیات بر ارزش افزوده هستم",
					default: answers.vat_registered ?? 1,
					description: "اگر تیک نخورد، فاکتورها بدون ارزش افزوده صادر می‌شوند.",
				},
				{
					fieldname: "uses_cheques",
					fieldtype: "Check",
					label: "چک می‌گیرم یا چک می‌دهم",
					default: answers.uses_cheques ?? 1,
				},
				{
					fieldname: "opening_date",
					fieldtype: "Date",
					label: "از چه تاریخی با سیستم کار می‌کنید؟",
					default: answers.opening_date || frappe.datetime.get_today(),
					reqd: 1,
					description: "موجودی‌ها و مانده‌هایی که در قدم‌های بعد می‌نویسید مال همین روز است.",
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "branches",
					fieldtype: "Small Text",
					label: "شعبه‌ها (اگر چند شعبه دارید، نام هر شعبه در یک خط)",
					default: answers.branches || "",
					description:
						"مثلاً «شعبه مرکزی» و «شعبه کرج». هر سند می‌تواند شعبه داشته باشد و گزارش‌ها برای هر شعبه جدا گرفته می‌شوند. اگر یک شعبه دارید خالی بگذارید.",
				},
			];
		}
		const table = (key, label) => ({
			fieldname: key,
			fieldtype: "Table",
			label,
			fields: this.state.tables[key].map((f, i) => ({ ...f, in_list_view: i < 6 ? 1 : 0 })),
			data: (data[key] || []).map((r) => ({ ...r })),
			cannot_add_rows: false,
			in_place_edit: true,
		});
		if (step.key === "banks") {
			return [
				{
					fieldname: "cash_balance",
					fieldtype: "Currency",
					label: "پول نقد در صندوق (ریال)",
					default: data.cash_balance || 0,
				},
				table("banks", "حساب‌های بانکی"),
			];
		}
		if (step.key === "warehouses") {
			const existing = (this.state.warehouses || []).join("، ");
			return [
				{
					fieldtype: "HTML",
					options: existing
						? `<p class="text-muted">${__("Warehouses you already have: {0}", [frappe.utils.escape_html(existing)])}</p>`
						: "",
				},
				table("warehouses", "انبارهای تازه"),
			];
		}
		const labels = {
			customers: "مشتری‌ها",
			suppliers: "تأمین‌کننده‌ها",
			items: "کالاها و خدمات",
			cheques: "چک‌ها",
		};
		return [table(step.key, labels[step.key])];
	}

	render_form(step) {
		this.form = new frappe.ui.FieldGroup({ fields: this.fields_for(step), body: this.$form[0] });
		this.form.make();
		setTimeout(() => (this.saved_values = JSON.stringify(this.form.get_values(true))), 300);
		const table_key = (this.state.tables[step.key] && step.key) || null;
		if (table_key) {
			const grid = this.form.fields_dict[table_key].grid;
			if (!grid.get_data().length) {
				grid.add_new_row();
			}
			$(`<button class="btn btn-xs btn-default iran-setup-paste"></button>`)
				.text("چسباندن از اکسل")
				.attr("title", "ردیف‌ها را در اکسل انتخاب و کپی کنید، اینجا بچسبانید")
				.on("click", () => this.paste(table_key))
				.insertAfter(this.form.fields_dict[table_key].$wrapper.find(".grid-footer, .form-grid").last());
		}
	}

	render_actions(index) {
		const step = this.state.steps[index];
		if (index > 0) {
			$(`<button class="btn btn-default"></button>`)
				.text(__("Previous"))
				.on("click", () => this.leave(() => this.show(this.state.steps[index - 1].key)))
				.appendTo(this.$actions);
		}
		$(`<button class="btn btn-primary"></button>`)
			.text(__("Save and continue"))
			.on("click", (e) => this.save(step, index, $(e.currentTarget)))
			.appendTo(this.$actions);
		if (step.key !== "business") {
			$(`<button class="btn btn-link"></button>`)
				.text(__("Skip this step"))
				.on("click", () =>
					this.leave(() => this.show(this.state.steps[Math.min(index + 1, this.state.steps.length - 1)].key))
				)
				.appendTo(this.$actions);
		}
	}

	save(step, index, $button) {
		const values = this.form.get_values(true);
		if (step.key === "business" && !values.opening_date) {
			frappe.msgprint(__("Choose the start date."));
			return;
		}
		$button.prop("disabled", true);
		frappe
			.xcall("iran_erp.onboarding.save_step", { step: step.key, values })
			.then((state) => {
				this.state = state;
				frappe.show_alert({ message: __("Saved"), indicator: "green" });
				const position = state.steps.findIndex((s) => s.key === step.key);
				const next = state.steps[Math.min(position + 1, state.steps.length - 1)];
				this.show(next.key);
			})
			.finally(() => $button.prop("disabled", false));
	}

	// ---------------------------------------------------------------- paste from Excel

	paste(table_key) {
		const dialog = new frappe.ui.Dialog({
			title: "چسباندن از اکسل",
			fields: [
				{
					fieldtype: "HTML",
					options: `<p class="text-muted">ستون‌ها را در اکسل انتخاب کنید (اگر سطر عنوان دارد، آن را هم)، کپی کنید و اینجا بچسبانید. ستون‌ها از روی عنوان یا محتوا شناخته می‌شوند.</p>`,
				},
				{ fieldname: "text", fieldtype: "Long Text", label: "متن کپی‌شده", reqd: 1 },
			],
			primary_action_label: "افزودن به جدول",
			primary_action: ({ text }) => {
				const rows = this.parse_paste(table_key, text);
				if (!rows.length) {
					frappe.msgprint("ردیفی پیدا نشد.");
					return;
				}
				const grid = this.form.fields_dict[table_key].grid;
				const kept = grid.get_data().filter((r) => Object.keys(r).some((k) => !["idx", "name", "doctype", "__islocal"].includes(k) && r[k]));
				this.form.fields_dict[table_key].df.data = [...kept, ...rows];
				grid.refresh();
				dialog.hide();
				frappe.show_alert({ message: `${rows.length} ردیف اضافه شد`, indicator: "green" });
			},
		});
		dialog.show();
	}

	parse_paste(table_key, text) {
		const columns = this.state.tables[table_key];
		const number = (v) => {
			const latin = iran_erp.to_latin_digits ? iran_erp.to_latin_digits(v) : v;
			const cleaned = String(latin).replace(/[٬,،\s]/g, "").replace(/^−/, "-");
			return /^-?\d+(\.\d+)?$/.test(cleaned) ? Number(cleaned) : null;
		};
		const lines = String(text)
			.split(/\r?\n/)
			.map((l) => l.split(/\t|;|\|/).map((c) => c.trim()))
			.filter((cells) => cells.some(Boolean));
		if (!lines.length) return [];

		// A first row of words that name the columns is a header
		let mapping = null;
		const header = lines[0];
		if (header.every((c) => number(c) === null)) {
			const found = header.map((cell) => {
				const lower = cell.toLowerCase();
				const column = columns.find((col) => (PASTE_HEADERS[col.fieldname] || []).some((w) => lower.includes(w)));
				return column ? column.fieldname : null;
			});
			if (found.filter(Boolean).length >= Math.min(2, header.length)) {
				mapping = found;
				lines.shift();
			}
		}
		const numeric = columns.filter((c) => ["Currency", "Float"].includes(c.fieldtype)).map((c) => c.fieldname);
		const texts = columns.filter((c) => c.fieldtype === "Data").map((c) => c.fieldname);
		return lines.map((cells) => {
			const row = {};
			if (mapping) {
				cells.forEach((cell, i) => {
					const field = mapping[i];
					if (!field || !cell) return;
					const column = columns.find((c) => c.fieldname === field);
					row[field] = ["Currency", "Float"].includes(column.fieldtype) ? number(cell) ?? 0 : cell;
				});
				return row;
			}
			// Without a header: mobile numbers and IDs by their shape, then numbers and words in order
			let n = 0;
			let t = 0;
			cells.forEach((cell) => {
				if (!cell) return;
				const digits = iran_erp.to_latin_digits ? iran_erp.to_latin_digits(cell).replace(/\D/g, "") : cell;
				if (texts.includes("mobile") && /^09\d{9}$/.test(digits)) row.mobile = digits;
				else if (texts.includes("national_id") && /^\d{10,11}$/.test(digits) && !digits.startsWith("09"))
					row.national_id = digits;
				else if (number(cell) !== null && n < numeric.length) row[numeric[n++]] = number(cell);
				else if (t < texts.length) {
					while (texts[t] && ["mobile", "national_id"].includes(texts[t])) t++;
					if (texts[t]) row[texts[t++]] = cell;
				}
			});
			return row;
		});
	}

	// ---------------------------------------------------------------- review

	render_review(index) {
		this.$form.html(`<div class="text-muted">${__("Loading…")}</div>`);
		frappe.xcall("iran_erp.onboarding.get_review").then((review) => {
			const money = (v) => format_currency(v, frappe.boot.sysdefaults.currency, 0);
			const esc = frappe.utils.escape_html;
			let html = `<table class="table iran-setup-summary"><tbody>`;
			review.lines.forEach((line) => {
				html += `<tr><td>${esc(line.label)}</td><td class="text-${line.sign > 0 ? "success" : "danger"}">${
					line.sign > 0 ? "+" : "−"
				} ${money(line.amount)}</td></tr>`;
			});
			html += `<tr class="iran-setup-capital"><td>سرمایه (دارایی‌ها منهای بدهی‌ها)</td><td>${money(review.capital)}</td></tr>`;
			html += `</tbody></table>`;
			if (review.issues.length) {
				html += `<div class="iran-setup-issues">`;
				review.issues.forEach((issue) => {
					const icon = { error: "⛔", warning: "⚠️", info: "ℹ️" }[issue.level];
					const link = issue.route ? ` <a href="${esc(issue.route)}">${__("Open")}</a>` : "";
					html += `<div class="iran-setup-issue iran-setup-issue-${issue.level}">${icon} ${esc(issue.text)}${link}</div>`;
				});
				html += `</div>`;
			} else {
				html += `<div class="iran-setup-issue iran-setup-issue-ok">✅ همه‌چیز آماده است.</div>`;
			}
			if (review.opening_posted) {
				html += `<h5>سندهایی که ساخته شد</h5><ul>`;
				review.opening_documents.forEach((d) => {
					html += `<li><a href="/desk/${frappe.router.slug(d.doctype)}/${encodeURIComponent(d.name)}">${esc(
						__(d.doctype)
					)} ${esc(d.name)}</a></li>`;
				});
				html += `</ul><p>راه‌اندازی تمام شد. از صفحه‌ی «شروع کار» کار روزانه را شروع کنید.</p>`;
			}
			this.$form.html(html);
			this.$actions.empty();
			if (index > 0) {
				$(`<button class="btn btn-default"></button>`)
					.text(__("Previous"))
					.on("click", () => this.show(this.state.steps[index - 1].key))
					.appendTo(this.$actions);
			}
			if (review.opening_posted) {
				$(`<button class="btn btn-primary"></button>`)
					.text(__("Start Page"))
					.on("click", () => frappe.set_route("iran-start"))
					.appendTo(this.$actions);
				return;
			}
			$(`<button class="btn btn-primary"></button>`)
				.text("ثبت مانده‌های اول دوره")
				.prop("disabled", !review.can_post)
				.on("click", (e) => {
					frappe.confirm(
						"همه‌ی مانده‌ها با تاریخ شروع ثبت می‌شوند و بعد از آن از این صفحه قابل تغییر نیستند. ادامه می‌دهید؟",
						() => {
							$(e.currentTarget).prop("disabled", true);
							frappe
								.xcall("iran_erp.onboarding.post_opening")
								.then(() => this.load())
								.catch(() => $(e.currentTarget).prop("disabled", false));
						}
					);
				})
				.appendTo(this.$actions);
		});
	}
}
