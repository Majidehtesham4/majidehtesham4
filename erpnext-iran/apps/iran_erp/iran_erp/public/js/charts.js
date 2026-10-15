// Charts with Persian month labels («فروردین ۱۴۰۵») cut every label to «فروردین ...»: the chart
// library allows 7px a letter and keeps only 60% of each label's share of the width. Here the year
// is dropped when all labels are in one year (two digits otherwise), a little more room is allowed,
// and labels that still do not fit are skipped instead of cut. The tooltip keeps the full label.

frappe.provide("iran_erp.charts");

iran_erp.charts.PERSIAN = /[؀-ۿ]/;
// «فروردین ۱۴۰۵», or «فروردین ۱۴۰۵ (مبلغ)» from the trends reports
iran_erp.charts.MONTH_YEAR = /^(\S+)\s+([۰-۹0-9]{4})(\s*\(.*\))?$/;

// Shorter labels for a chart's data; full[short] is the original label, for the tooltip
iran_erp.charts.shorten = function (data, full) {
	const labels = data && data.labels;
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
	return options;
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
		// Dashboards draw an empty chart first and put the real data in later
		if (chart && typeof chart.update === "function") {
			const update = chart.update.bind(chart);
			chart.update = (data, ...rest) => {
				const result = update(iran_erp.charts.shorten(data, full), ...rest);
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
