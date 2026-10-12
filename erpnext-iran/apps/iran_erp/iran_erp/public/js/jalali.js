// Jalali (Solar Hijri) dates for ERPNext desk.
// Dates are always stored in Gregorian. Depending on Iran ERP Settings, date fields either take
// Jalali input with a Jalali calendar, or keep the Gregorian picker and show the Jalali date under it.

frappe.provide("iran_erp");

iran_erp.jalaali = (() => {
	// Jalali <-> Gregorian conversion (algorithm of jalaali-js, MIT licence, by Behrang Noruzi Niya)
	const BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];
	const div = (a, b) => ~~(a / b);
	const mod = (a, b) => a - ~~(a / b) * b;
	function jal_cal(jy) {
		const gy = jy + 621;
		let leap_j = -14, jp = BREAKS[0], jm, jump = 0, n;
		for (let i = 1; i < BREAKS.length; i += 1) {
			jm = BREAKS[i];
			jump = jm - jp;
			if (jy < jm) break;
			leap_j = leap_j + div(jump, 33) * 8 + div(mod(jump, 33), 4);
			jp = jm;
		}
		n = jy - jp;
		leap_j = leap_j + div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
		if (mod(jump, 33) === 4 && jump - n === 4) leap_j += 1;
		const leap_g = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
		const march = 20 + leap_j - leap_g;
		if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
		let leap = mod(mod(n + 1, 33) - 1, 4);
		if (leap === -1) leap = 4;
		return { leap, gy, march };
	}
	function g2d(gy, gm, gd) {
		let d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) + div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408;
		return d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
	}
	function d2g(jdn) {
		let j = 4 * jdn + 139361631;
		j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
		const i = div(mod(j, 1461), 4) * 5 + 308;
		const gd = div(mod(i, 153), 5) + 1;
		const gm = mod(div(i, 153), 12) + 1;
		const gy = div(j, 1461) - 100100 + div(8 - gm, 6);
		return { gy, gm, gd };
	}
	function j2d(jy, jm, jd) {
		const r = jal_cal(jy);
		return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
	}
	function d2j(jdn) {
		const gy = d2g(jdn).gy;
		let jy = gy - 621;
		const r = jal_cal(jy);
		let k = jdn - g2d(gy, 3, r.march);
		if (k >= 0) {
			if (k <= 185) return { jy, jm: 1 + div(k, 31), jd: mod(k, 31) + 1 };
			k -= 186;
		} else {
			jy -= 1;
			k += 179;
			if (r.leap === 1) k += 1;
		}
		return { jy, jm: 7 + div(k, 30), jd: mod(k, 30) + 1 };
	}
	const to_jalali = (gy, gm, gd) => d2j(g2d(gy, gm, gd));
	const to_gregorian = (jy, jm, jd) => d2g(j2d(jy, jm, jd));
	const is_leap = (jy) => jal_cal(jy).leap === 0;
	const month_length = (jy, jm) => (jm <= 6 ? 31 : jm <= 11 ? 30 : is_leap(jy) ? 30 : 29);
	return { to_jalali, to_gregorian, month_length, is_leap };
})();

const JALALI_MONTHS = [
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
const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const pad2 = (n) => String(n).padStart(2, "0");

iran_erp.to_persian_digits = (text) => String(text).replace(/\d/g, (d) => PERSIAN_DIGITS[d]);
iran_erp.to_latin_digits = (text) =>
	String(text)
		.replace(/[۰-۹]/g, (d) => PERSIAN_DIGITS.indexOf(d))
		.replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d));

// "2026-10-11" (or "2026-10-11 10:00:00") -> {jy, jm, jd}
iran_erp.parse_db_date = (value) => {
	const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value || "");
	if (!match) return null;
	return iran_erp.jalaali.to_jalali(Number(match[1]), Number(match[2]), Number(match[3]));
};

iran_erp.to_jalali = (value) => {
	const j = iran_erp.parse_db_date(value);
	return j ? iran_erp.to_persian_digits(`${j.jy}/${pad2(j.jm)}/${pad2(j.jd)}`) : "";
};

// "1405/07/19" (Persian or Latin digits) -> "2026-10-11"; anything else -> null
iran_erp.jalali_to_db = (text) => {
	const match = /^\s*(\d{4})\s*[\/\-.]\s*(\d{1,2})\s*[\/\-.]\s*(\d{1,2})\s*$/.exec(
		iran_erp.to_latin_digits(text || "")
	);
	if (!match) return null;
	const [jy, jm, jd] = match.slice(1).map(Number);
	if (jy < 1200 || jy > 1600 || jm < 1 || jm > 12 || jd < 1) return null;
	if (jd > iran_erp.jalaali.month_length(jy, jm)) return null;
	const g = iran_erp.jalaali.to_gregorian(jy, jm, jd);
	return `${g.gy}-${pad2(g.gm)}-${pad2(g.gd)}`;
};

// The date picker ships no Persian locale, so it falls back to English month names and "Today".
const persian_gregorian_months = [
	"ژانویه",
	"فوریه",
	"مارس",
	"آوریل",
	"مه",
	"ژوئن",
	"ژوئیه",
	"اوت",
	"سپتامبر",
	"اکتبر",
	"نوامبر",
	"دسامبر",
];
$.fn.datepicker.language["fa"] = {
	days: ["یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه"],
	daysShort: ["یک", "دو", "سه", "چهار", "پنج", "جمعه", "شنبه"],
	daysMin: ["ی", "د", "س", "چ", "پ", "ج", "ش"],
	months: persian_gregorian_months,
	monthsShort: persian_gregorian_months,
	today: "امروز",
	clear: "پاک کردن",
	dateFormat: "dd/mm/yyyy",
	timeFormat: "hh:ii aa",
	firstDay: 6,
};

// List view, report view, read-only fields and grids show the Jalali date.
const gregorian_date_formatter = frappe.form.formatters.Date;
frappe.form.formatters.Date = function (value, ...args) {
	return iran_erp.to_jalali(value) || gregorian_date_formatter.call(this, value, ...args);
};

const jalali_input = () => frappe.boot.iran_jalali_input !== false;

// A small Jalali month calendar shown under a date input.
iran_erp.JalaliPicker = class {
	constructor(control) {
		this.control = control;
		// The "datepicker" class makes list filters treat clicks inside it as clicks in a date picker
		this.$el = $(`<div class="iran-jalali-picker datepicker" dir="rtl"></div>`)
			.appendTo(document.body)
			.hide();
		this.$el.on("mousedown", (e) => e.preventDefault());
		this.$el.on("click", "[data-action]", (e) => this.on_action($(e.currentTarget)));
		// Clicks inside the picker keep focus on the input (mousedown above), so blur means leaving it
		control.$input.on("blur", () => this.hide());
	}

	show() {
		const today = iran_erp.parse_db_date(frappe.datetime.nowdate());
		const current = iran_erp.parse_db_date(this.control.value) || today;
		this.view = { jy: current.jy, jm: current.jm };
		this.render();
		const rect = this.control.$input[0].getBoundingClientRect();
		const height = this.$el.outerHeight();
		const below = rect.bottom + 4 + height < window.innerHeight;
		this.$el.css({
			top: (below ? rect.bottom + 4 : rect.top - height - 4) + window.scrollY,
			left: Math.max(8, rect.right - this.$el.outerWidth()) + window.scrollX,
		});
		this.$el.show();
	}

	hide() {
		this.$el.hide();
	}

	render() {
		const { jy, jm } = this.view;
		const selected = iran_erp.parse_db_date(this.control.value);
		const today = iran_erp.parse_db_date(frappe.datetime.nowdate());
		const first = iran_erp.jalaali.to_gregorian(jy, jm, 1);
		// Columns run Saturday to Friday
		const offset = (new Date(first.gy, first.gm - 1, first.gd).getDay() + 1) % 7;
		const days = iran_erp.jalaali.month_length(jy, jm);
		const same = (d, day) => d && d.jy === jy && d.jm === jm && d.jd === day;

		let cells = "";
		for (let i = 0; i < offset; i++) cells += `<span></span>`;
		for (let day = 1; day <= days; day++) {
			const classes = ["iran-jalali-day"];
			if (same(selected, day)) classes.push("selected");
			if (same(today, day)) classes.push("today");
			cells += `<span class="${classes.join(" ")}" data-action="pick" data-day="${day}">${iran_erp.to_persian_digits(day)}</span>`;
		}

		this.$el.html(`
			<div class="iran-jalali-nav">
				<span data-action="prev" title="${__("Previous")}">›</span>
				<b>${JALALI_MONTHS[jm - 1]} ${iran_erp.to_persian_digits(jy)}</b>
				<span data-action="next" title="${__("Next")}">‹</span>
			</div>
			<div class="iran-jalali-grid">
				${["ش", "ی", "د", "س", "چ", "پ", "ج"].map((d) => `<span class="iran-jalali-weekday">${d}</span>`).join("")}
				${cells}
			</div>
			<div class="iran-jalali-footer">
				<span data-action="today">${__("Today")}</span>
				<span data-action="clear">${__("Clear")}</span>
			</div>`);
	}

	on_action($target) {
		const action = $target.data("action");
		if (action === "prev" || action === "next") {
			let { jy, jm } = this.view;
			jm += action === "next" ? 1 : -1;
			if (jm > 12) [jy, jm] = [jy + 1, 1];
			if (jm < 1) [jy, jm] = [jy - 1, 12];
			this.view = { jy, jm };
			this.render();
			return;
		}
		let value = "";
		if (action === "today") value = frappe.datetime.nowdate();
		if (action === "pick") {
			const g = iran_erp.jalaali.to_gregorian(this.view.jy, this.view.jm, Number($target.data("day")));
			value = `${g.gy}-${pad2(g.gm)}-${pad2(g.gd)}`;
		}
		this.hide();
		this.control.set_value(value);
		this.control.$input.trigger("change");
	}
};

// Date fields: Jalali input and calendar, or (when turned off in Iran ERP Settings) the Gregorian
// picker with the Jalali date written under the field.
frappe.ui.form.ControlDate = class ControlJalaliDate extends frappe.ui.form.ControlDate {
	make_picker() {
		if (!jalali_input()) return super.make_picker();
		this.set_t_for_today();
		this.jalali_picker = new iran_erp.JalaliPicker(this);
		this.$input.attr("placeholder", iran_erp.to_persian_digits("1405/01/01"));
		// Handlers must not return false: jQuery would cancel the keystroke
		this.$input.on("focus click", () => {
			if (!this.df.read_only) this.jalali_picker.show();
		});
		this.$input.on("keydown", (e) => {
			if (e.key === "Escape") this.jalali_picker.hide();
		});
	}

	set_formatted_input(value) {
		if (!jalali_input()) {
			super.set_formatted_input(value);
			this.set_jalali_hint(value);
			return;
		}
		if (value === "Today") value = frappe.datetime.nowdate();
		this.$input && this.$input.val(this.format_for_input(value));
	}

	format_for_input(value) {
		if (!jalali_input()) return super.format_for_input(value);
		return iran_erp.to_jalali(value) || "";
	}

	parse(value) {
		if (!jalali_input() || !value) return super.parse(value);
		const db_date = iran_erp.jalali_to_db(value);
		if (db_date) return db_date;
		// Frappe itself passes Gregorian dates in the system format; a pasted database date is fine too
		const latin = iran_erp.to_latin_digits(value).trim();
		const user_format = frappe.datetime.get_user_date_fmt().toUpperCase();
		if (moment(latin, [user_format, "YYYY-MM-DD"], true).isValid() && Number(latin.match(/\d{4}/)) > 1700) {
			return super.parse(latin);
		}
		// Anything else would be misread as a Gregorian date, so keep the old value
		frappe.show_alert({ message: __("Invalid Jalali date: {0}", [value]), indicator: "red" });
		setTimeout(() => this.set_formatted_input(this.value));
		return this.value;
	}

	set_jalali_hint(value) {
		if (!this.$wrapper) return;
		if (!this.$jalali_hint) {
			this.$jalali_hint = $(`<div class="iran-erp-jalali-hint text-muted small"></div>`);
			this.$wrapper.find(".control-input-wrapper").append(this.$jalali_hint);
		}
		const jalali = iran_erp.to_jalali(value);
		this.$jalali_hint.text(jalali ? `${__("Jalali")}: ${jalali}` : "");
	}
};
