// Charts with Persian month labels («فروردین ۱۴۰۵») cut every label to «فروردین ...»: the chart
// library allows 7px a letter and keeps only 60% of each label's share of the width. Here the year
// is dropped when all labels are in one year (two digits otherwise), a little more room is allowed,
// and labels that still do not fit are skipped instead of cut. The tooltip keeps the full label.

frappe.provide("iran_erp.charts");

iran_erp.charts.PERSIAN = /[؀-ۿ]/;
// «فروردین ۱۴۰۵», or «فروردین ۱۴۰۵ (مبلغ)» from the trends reports
iran_erp.charts.MONTH_YEAR = /^(\S+)\s+([۰-۹0-9]{4})(\s*\(.*\))?$/;

// Shorter labels for a chart's data; full[short] is the original label, for the tooltip
// Gregorian dates as labels («31-10-2025», «31-10-25»), in the order of the user's date format
iran_erp.charts.NUMERIC_DATE = /^(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})$/;

iran_erp.charts.jalali_dates = function (labels) {
	if (!iran_erp.jalaali) return null;
	const format = (
		(frappe.boot.user && frappe.boot.user.defaults && frappe.boot.user.defaults.date_format) ||
		(frappe.boot.sysdefaults && frappe.boot.sysdefaults.date_format) ||
		"dd-mm-yyyy"
	).toLowerCase();
	const order = format.split(/[^dmy]+/).filter(Boolean).map((part) => part[0]);
	const converted = labels.map((label) => {
		const match = iran_erp.charts.NUMERIC_DATE.exec(String(label).trim());
		if (!match) return null;
		let parts = { [order[0]]: +match[1], [order[1]]: +match[2], [order[2]]: +match[3] };
		if (match[1].length === 4) parts = { y: +match[1], m: +match[2], d: +match[3] };
		if (parts.y < 100) parts.y += 2000;
		if (!(parts.m >= 1 && parts.m <= 12 && parts.d >= 1 && parts.d <= 31)) return null;
		const j = iran_erp.jalaali.to_jalali(parts.y, parts.m, parts.d);
		return { j, text: `${j.jy}/${String(j.jm).padStart(2, "0")}/${String(j.jd).padStart(2, "0")}` };
	});
	if (!converted.every(Boolean)) return null;
	const one_year = new Set(converted.map((c) => c.j.jy)).size === 1;
	const digits = (text) => (iran_erp.to_persian_digits ? iran_erp.to_persian_digits(text) : text);
	return converted.map((c) => digits(one_year ? c.text.slice(5) : c.text));
};

iran_erp.charts.shorten = function (data, full) {
	const labels = data && data.labels;
	if (Array.isArray(labels) && labels.length && !labels.some((l) => iran_erp.charts.PERSIAN.test(String(l)))) {
		const dates = iran_erp.charts.jalali_dates(labels);
		if (!dates) return data;
		dates.forEach((d, i) => (full[d] = labels[i]));
		return { ...data, labels: dates };
	}
	if (!Array.isArray(labels) || !labels.some((l) => iran_erp.charts.PERSIAN.test(String(l)))) {
		return data;
	}
	const parts = labels.map((l) => iran_erp.charts.MONTH_YEAR.exec(String(l).trim()));
	if (!parts.every(Boolean)) return data;
	const one_year = new Set(parts.map((p) => p[2])).size === 1;
	// A suffix every label has («(مبلغ)») says nothing on the axis; a differing one is kept
	const one_suffix = new Set(parts.map((p) => p[3] || "")).size === 1;
	const short = parts.map(
		(p) =>
			(one_year ? p[1] : `${p[1]} ${p[2].slice(-2)}`) + (one_suffix ? "" : ` ${(p[3] || "").trim()}`)
	);
	short.forEach((s, i) => (full[s] = labels[i]));
	return { ...data, labels: short };
};

iran_erp.charts.adjust = function (options, full) {
	options.data = iran_erp.charts.shorten(options.data, full);
	const tooltip = { ...(options.tooltipOptions || {}) };
	const format = tooltip.formatTooltipX;
	tooltip.formatTooltipX = (label) => {
		const original = full[label] || label;
		return format ? format(original) : original;
	};
	options.tooltipOptions = tooltip;
	options.axisOptions = {
		xIsSeries: 1,
		seriesLabelSpaceRatio: 0.95,
		...(options.axisOptions || {}),
	};
	// Pie and donut legends show raw values («48850000000») unless given a formatter
	if (iran_erp.charts.CIRCULAR.includes(String(options.type || "").toLowerCase()) && !tooltip.formatTooltipY) {
		tooltip.formatTooltipY = (value) => format_number(value, null, 0);
	}
	// The library gives each legend entry 150px and cuts longer names («...جریان نقدی ناش»);
	// those charts get a legend of their own that wraps instead
	if (iran_erp.charts.legend_names(options).some((name) => String(name || "").length > 16)) {
		options.showLegend = 0;
		options.iran_html_legend = true;
	}
	return options;
};

iran_erp.charts.CIRCULAR = ["pie", "donut", "percentage"];

// Values in a chart's own legend («48850000000») get thousands separators, however the chart was made
iran_erp.charts.watch_legend_values = function (parent) {
	const root = typeof parent === "string" ? document.querySelector(parent) : parent;
	if (!root || root.iran_legend_watch) return;
	const format = () =>
		root.querySelectorAll(".legend-dataset-value").forEach((text) => {
			const value = text.textContent.trim();
			if (/^-?\d{4,}(\.\d+)?$/.test(value)) text.textContent = format_number(value, null, 0);
		});
	root.iran_legend_watch = new MutationObserver(format);
	root.iran_legend_watch.observe(root, { childList: true, subtree: true });
	format();
};

iran_erp.charts.legend_names = function (options) {
	const data = options.data || {};
	if (iran_erp.charts.CIRCULAR.includes(String(options.type || "").toLowerCase())) return data.labels || [];
	return (data.datasets || []).map((d) => d.name);
};

iran_erp.charts.html_legend = function (parent, chart, options) {
	const root = typeof parent === "string" ? document.querySelector(parent) : parent;
	if (!root) return;
	// Beside the chart's element, not in it: the chart redraws its own children
	let $legend = $(root).next(".iran-chart-legend");
	if (!$legend.length) $legend = $(`<div class="iran-chart-legend" dir="auto"></div>`).insertAfter(root);
	$legend.empty();
	const colors = chart.colors || options.colors || [];
	iran_erp.charts.legend_names(options).forEach((name, i) => {
		$(`<span class="iran-chart-legend-item"><i></i><span></span></span>`)
			.find("i")
			.css("background", colors[i % colors.length] || "var(--gray-500)")
			.end()
			.find("span")
			.text(__(name || ""))
			.end()
			.appendTo($legend);
	});
};

// The activity heatmap names Gregorian months in English («Oct 2025»). Each label marks the column
// where a Gregorian month starts; it is replaced by the Jalali month that covers most of that month.
iran_erp.charts.GREGORIAN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
iran_erp.charts.JALALI_MONTHS = [
	"فروردین",
	"اردیبهشت",
	"خرداد",
	"تیر",
	"مرداد",
	"شهریور",
	"مهر",
	"آبان",
	"آذر",
	"دی",
	"بهمن",
	"اسفند",
];

iran_erp.charts.jalali_heatmap_labels = function (parent) {
	const root = typeof parent === "string" ? document.querySelector(parent) : parent;
	if (!root || !iran_erp.jaalali_ready()) return;
	root.querySelectorAll("svg text").forEach((text) => {
		const match = /^([A-Z][a-z]{2})(?:\s+(\d{4}))?$/.exec(text.textContent.trim());
		if (!match) return;
		const month = iran_erp.charts.GREGORIAN_MONTHS.indexOf(match[1]);
		if (month < 0) return;
		const year = Number(match[2]) || new Date().getFullYear();
		const j = iran_erp.jalaali.to_jalali(year, month + 1, 15);
		text.textContent = match[2]
			? `${iran_erp.charts.JALALI_MONTHS[j.jm - 1]} ${iran_erp.to_persian_digits(j.jy)}`
			: iran_erp.charts.JALALI_MONTHS[j.jm - 1];
	});
};

iran_erp.jaalali_ready = () => !!(iran_erp.jalaali && iran_erp.to_persian_digits);

(function () {
	const Base = frappe.Chart;
	if (!Base || Base.iran_adjusted) return;
	const Adjusted = function (parent, options) {
		const full = {};
		const chart = new Base(parent, iran_erp.charts.adjust(options || {}, full));
		if ((options || {}).type === "heatmap") {
			setTimeout(() => iran_erp.charts.jalali_heatmap_labels(parent), 0);
		}
		if (options && options.iran_html_legend) iran_erp.charts.html_legend(parent, chart, options);
		iran_erp.charts.watch_legend_values(parent);
		// Dashboards draw an empty chart first and put the real data in later
		if (chart && typeof chart.update === "function") {
			const update = chart.update.bind(chart);
			chart.update = (data, ...rest) => {
				const result = update(iran_erp.charts.shorten(data, full), ...rest);
				if (options && options.iran_html_legend && data) {
					iran_erp.charts.html_legend(parent, chart, { ...options, data });
				}
				if ((options || {}).type === "heatmap") {
					setTimeout(() => iran_erp.charts.jalali_heatmap_labels(parent), 0);
				}
				return result;
			};
		}
		return chart;
	};
	Adjusted.prototype = Base.prototype;
	Adjusted.iran_adjusted = true;
	frappe.Chart = Adjusted;
})();

// Reports show every number with decimals («3,038,000,000.00»); amounts in rials never have any, and
// the extra characters push long numbers out of their column. Whole numbers are shown without them.
(function () {
	const formatters = frappe.form && frappe.form.formatters;
	if (!formatters || formatters.Float.iran_whole) return;
	const Float = formatters.Float;
	formatters.Float = function (value, docfield, options, doc) {
		if (options && options.always_show_decimals && value !== null && value !== "" && flt(value) % 1 === 0) {
			options = { ...options, always_show_decimals: false };
		}
		return Float.call(this, value, docfield, options, doc);
	};
	formatters.Float.iran_whole = true;
})();

// Dashboard pages put the dashboard's name in the breadcrumb as it is stored («Selling»)
(function () {
	const Page = frappe.ui && frappe.ui.Page;
	if (!Page || Page.prototype.iran_breadcrumbs) return;
	const set_breadcrumbs = Page.prototype.set_breadcrumbs;
	Page.prototype.set_breadcrumbs = function (items, ...rest) {
		if (Array.isArray(items) && frappe.get_route().includes("dashboard-view")) {
			items = items.map((item) => (item && item.label ? { ...item, label: __(item.label) } : item));
		}
		return set_breadcrumbs.call(this, items, ...rest);
	};
	Page.prototype.iran_breadcrumbs = true;
})();

// The dock (the column of app icons beside the sidebar) shows module names as stored: «Buying»
(function () {
	const Dock = frappe.ui && frappe.ui.Dock;
	if (!Dock || Dock.prototype.iran_translated) return;
	const { make_dock_item, name_tile, module_logo } = Dock.prototype;
	Dock.prototype.make_dock_item = function (entry) {
		const $item = make_dock_item.call(this, entry);
		if ($item && entry && entry.label) {
			const label = __(entry.label);
			$item.attr("aria-label", label);
			$item.find(".dock-item-label").text(label);
		}
		return $item;
	};
	Dock.prototype.name_tile = function ($el, label) {
		return name_tile.call(this, $el, __(label));
	};
	Dock.prototype.module_logo = function () {
		const logo = module_logo.call(this);
		return { ...logo, title: __(logo.title) };
	};
	Dock.prototype.iran_translated = true;
})();

// Shortened amounts on dashboards and chart axes («3 B», «30 M») in Persian words: «۳ میلیارد»
(function () {
	if (!frappe.utils.get_number_system || !String(frappe.boot.lang || "").startsWith("fa")) return;
	// No plain spaces in a word: number cards split «3 میلیارد» on the space to put the currency between
	const words = { 1e12: "هزار\u00a0میلیارد", 1e9: "میلیارد", 1e6: "میلیون", 1e3: "هزار" };
	(frappe.utils.get_number_system("Iran") || []).forEach((step) => {
		if (words[step.divisor]) step.symbol = words[step.divisor];
	});
})();

// Number cards put the currency between the number and its size («ریال ۳ میلیارد»); in Persian the
// amount reads «۳ میلیارد ریال»
(function () {
	const Card = frappe.widget && frappe.widget.widget_factory && frappe.widget.widget_factory.number_card;
	if (!Card || Card.prototype.iran_order) return;
	const set_formatted_number = Card.prototype.set_formatted_number;
	const SIZE = /^(.*?)(-?[\d.,٬]+)(.*?)\s+(هزار\u00a0میلیارد|میلیارد|میلیون|هزار)$/;
	Card.prototype.set_formatted_number = function (...args) {
		set_formatted_number.apply(this, args);
		const text = String(this.formatted_number || "").trim();
		// An amount in a currency written after the number (money.js): «۳ میلیارد ریال» as one
		const sized = /^(.*)\s+(هزار\u00a0میلیارد|میلیارد|میلیون|هزار)$/.exec(text);
		const amount = sized && iran_erp.money && iran_erp.money.parts(sized[1]);
		if (amount) {
			this.formatted_number = iran_erp.money.isolate(amount.number, `${sized[2]} ${amount.words}`);
			return;
		}
		const match = SIZE.exec(text);
		if (match) {
			const currency = `${match[1]} ${match[3]}`.trim();
			this.formatted_number = `${match[2]} ${match[4]}${currency ? " " + currency : ""}`;
		}
	};
	Card.prototype.iran_order = true;
})();

// The System Health Report fills its fields with English status words («finished», «Process Not Found»)
(function () {
	const formatters = frappe.form && frappe.form.formatters;
	if (!formatters || formatters.Data.iran_health) return;
	const Data = formatters.Data;
	formatters.Data = function (value, docfield, options, doc) {
		if (doc && doc.doctype === "System Health Report" && typeof value === "string" && value) {
			value = __(value);
		}
		return Data.call(this, value, docfield, options, doc);
	};
	formatters.Data.iran_health = true;
})();
