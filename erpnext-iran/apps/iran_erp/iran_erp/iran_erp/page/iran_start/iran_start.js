// «شروع کار»: today's figures and the everyday tasks as big buttons, for people new to the software.

frappe.pages["iran-start"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Start Page"), single_column: true });
	wrapper.iran_start = new IranStartPage(page);
};

frappe.pages["iran-start"].on_page_show = function (wrapper) {
	wrapper.iran_start && wrapper.iran_start.load_summary();
};

// wizard: a short form that runs the same command as the chat; route: a page; chat: a question for the assistant
const START_GROUPS = [
	{
		title: "فروش",
		icon: "sell",
		tiles: [
			{ label: "فاکتور فروش", hint: "فروختید؟ فاکتورش را اینجا بزنید", wizard: "create_sales_invoice" },
			{ label: "دریافت پول از مشتری", hint: "مشتری پول داد (نقد یا واریز)", wizard: "receive_payment" },
			{ label: "پیش‌فاکتور", hint: "قیمت برای مشتری بفرستید", wizard: "create_quotation" },
			{ label: "مشتری جدید", hint: "تعریف یک خریدار تازه", wizard: "create_customer" },
		],
	},
	{
		title: "خرید و هزینه",
		icon: "buying",
		tiles: [
			{ label: "فاکتور خرید", hint: "جنس یا خدمت خریدید", wizard: "create_purchase_invoice" },
			{ label: "پرداخت به تأمین‌کننده", hint: "به فروشنده پول دادید", wizard: "make_payment" },
			{ label: "تأمین‌کننده‌ی جدید", hint: "تعریف فروشنده‌ای که از او می‌خرید", wizard: "create_supplier" },
			{ label: "ثبت هزینه", hint: "اجاره، قبض، حقوق و …", route: "/desk/journal-entry/new" },
		],
	},
	{
		title: "انبار و کالا",
		icon: "stock",
		tiles: [
			{ label: "کالای جدید", hint: "تعریف کالا یا خدمت", wizard: "create_item" },
			{ label: "ورود کالا به انبار", hint: "رسید انبار", wizard: "stock_receipt" },
			{ label: "خروج کالا از انبار", hint: "حواله یا مصرف", wizard: "stock_issue" },
			{ label: "موجودی کالاها", hint: "چه داریم و چقدر", route: "/desk/query-report/Stock Balance" },
		],
	},
	{
		title: "چک",
		icon: "money-coins-1",
		tiles: [
			{ label: "چک دریافتی", hint: "مشتری چک داد", wizard: "register_received_cheque" },
			{ label: "چک پرداختی", hint: "چک کشیدید", wizard: "register_issued_cheque" },
			{ label: "چک‌های نزدیک سررسید", hint: "چه چک‌هایی در راه است", chat: "چک‌های نزدیک سررسید" },
			{ label: "همه‌ی چک‌ها", hint: "فهرست و وضعیت چک‌ها", route: "/desk/iran-cheque" },
		],
	},
	{
		title: "گزارش‌های ساده",
		icon: "chart",
		tiles: [
			{ label: "سود و زیان", hint: "امسال چقدر سود کردیم", chat: "سود و زیان امسال" },
			{ label: "بدهکاران", hint: "چه کسانی به ما بدهکارند", chat: "کل طلب ما از مشتری‌ها" },
			{ label: "پرفروش‌ترین کالاها", hint: "چه چیزی بیشتر فروش رفت", chat: "کالاهای پرفروش امسال" },
			{ label: "موجودی صندوق و بانک", hint: "چقدر پول داریم", chat: "موجودی صندوق و بانک" },
		],
	},
	{
		title: "کارهای روزانه",
		icon: "list",
		tiles: [
			{ label: "یادآوری", hint: "یادداشت یک کار برای بعد", wizard: "create_todo" },
			{ label: "کارهای منتظر من", hint: "تأییدها و پیش‌نویس‌ها", chat: "کارهای من" },
			{ label: "از دستیار بپرس", hint: "هر چیزی را به زبان ساده بنویسید", chat: "" },
			{ label: "راهنمای برنامه", hint: "هر صفحه دکمه‌ی «آموزش» دارد", chat: "راهنما" },
		],
	},
];

class IranStartPage {
	constructor(page) {
		this.page = page;
		this.$body = $(`<div class="iran-start" dir="rtl"></div>`).appendTo(page.main);
		this.$hello = $(`<div class="iran-start-hello"></div>`).appendTo(this.$body);
		this.$setup = $(`<div class="iran-start-setup" style="display:none"></div>`).appendTo(this.$body);
		this.$cards = $(`<div class="iran-start-cards"></div>`).appendTo(this.$body);
		this.$groups = $(`<div class="iran-start-groups"></div>`).appendTo(this.$body);
		this.render_groups();
	}

	// Until the easy setup is finished, a banner leads to it
	load_setup() {
		frappe.xcall("iran_erp.onboarding.get_progress").then((p) => {
			if (!p || !p.total || p.finished) return this.$setup.hide();
			this.$setup
				.html(
					`<div class="iran-start-setup-text">
						<b>راه‌اندازی آسان</b>
						<span>بانک‌ها، مشتری‌ها، کالاها و موجودی‌های اول کار را با چند سؤال ساده وارد کنید.</span>
						<div class="iran-setup-progress-bar"><span style="width:${Math.round((100 * p.done) / p.total)}%"></span></div>
						<small>${__("{0} of {1} steps done", [String(p.done), String(p.total)])}</small>
					</div>
					<button class="btn btn-primary btn-sm">${p.done ? "ادامه‌ی راه‌اندازی" : "شروع راه‌اندازی"}</button>`
				)
				.show()
				.find("button")
				.on("click", () => frappe.set_route("iran-easy-setup"));
		});
	}

	load_summary() {
		this.load_setup();
		frappe.xcall("iran_erp.start.get_summary").then((r) => {
			const name = (r.user || "").split(" ")[0];
			this.$hello.html(`
				<div class="iran-start-title">${frappe.utils.escape_html(__("Hello {0}!", [name]))}</div>
				<div class="iran-start-subtitle">${__(
					"What do you want to do today? Click a button; each one asks a few simple questions. You can also write to the assistant in plain words."
				)}</div>`);
			this.$cards.empty();
			r.cards.forEach((card) => {
				const value =
					card.kind === "money"
						? format_currency(card.value, frappe.boot.sysdefaults.currency, 0)
						: String(card.value);
				const $card = $(`
					<div class="iran-start-card" role="button" tabindex="0">
						<div class="iran-start-card-label"></div>
						<div class="iran-start-card-value"></div>
						<div class="iran-start-card-hint"></div>
					</div>`).appendTo(this.$cards);
				$card.find(".iran-start-card-label").text(card.label);
				$card.find(".iran-start-card-value").text(value);
				$card.find(".iran-start-card-hint").text(card.hint || "");
				$card.on("click", () => {
					if (card.key === "tasks") {
						this.chat("کارهای من");
					} else if (card.route) {
						frappe.set_route(card.route);
					}
				});
			});
		});
	}

	render_groups() {
		START_GROUPS.forEach((group) => {
			const $group = $(`
				<div class="iran-start-group">
					<div class="iran-start-group-title"></div>
					<div class="iran-start-tiles"></div>
				</div>`).appendTo(this.$groups);
			$group.find(".iran-start-group-title").text(group.title);
			const $tiles = $group.find(".iran-start-tiles");
			group.tiles.forEach((tile) => {
				const $tile = $(`
					<button class="iran-start-tile">
						<span class="iran-start-tile-label"></span>
						<span class="iran-start-tile-hint"></span>
					</button>`).appendTo($tiles);
				$tile.find(".iran-start-tile-label").text(tile.label);
				$tile.find(".iran-start-tile-hint").text(tile.hint);
				$tile.on("click", () => this.open(tile));
			});
		});
	}

	open(tile) {
		if (tile.wizard) return iran_erp.start.wizard(tile.wizard);
		if (tile.route) return frappe.set_route(tile.route);
		if (tile.chat !== undefined) return this.chat(tile.chat);
	}

	chat(question) {
		const panel = iran_erp.ai && iran_erp.ai.panel;
		if (!panel) {
			frappe.msgprint(__("The assistant is turned off. Ask your administrator to turn it on in Iran AI Settings."));
			return;
		}
		panel.toggle(true);
		if (question) {
			panel.add_message("user", question);
			panel.ask({ question });
		} else {
			panel.$input.focus();
		}
	}
}
