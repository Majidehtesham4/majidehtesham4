// ERPNext's Banking page (/banking) is a separate app that does not load the desk's scripts. It
// writes dates in the Gregorian calendar and a few labels without translating them. This script
// watches what the page draws and puts Jalali dates and the Persian labels in their place.

(function () {
	const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
	const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
	const MONTHS_FA = [
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
	const persian = (text) => String(text).replace(/\d/g, (d) => PERSIAN_DIGITS[d]);
	const pad2 = (n) => String(n).padStart(2, "0");

	function jalali(gy, gm, gd) {
		if (!(gy > 1900 && gm >= 1 && gm <= 12 && gd >= 1 && gd <= 31)) return null;
		const j = iran_erp.jalaali.to_jalali(gy, gm, gd);
		return persian(`${j.jy}/${pad2(j.jm)}/${pad2(j.jd)}`);
	}

	// The order of day, month and year in the user's date format («dd-mm-yyyy»)
	function date_order() {
		const boot = (window.frappe && frappe.boot) || {};
		const format = (
			(boot.user && boot.user.defaults && boot.user.defaults.date_format) ||
			(boot.sysdefaults && boot.sysdefaults.date_format) ||
			"dd-mm-yyyy"
		).toLowerCase();
		return format
			.split(/[^dmy]+/)
			.filter(Boolean)
			.map((part) => part[0]);
	}

	const NUMERIC = /\b(\d{1,4})([-/.])(\d{1,2})\2(\d{1,4})\b/g;
	// «1st Oct '26», «Oct 1, 2026», «1 Oct 2026»
	const DAY_MONTH = /\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s+'?(\d{2,4})\b/g;
	const MONTH_DAY = /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+'?(\d{2,4})\b/g;
	const full_year = (y) => (String(y).length === 2 ? 2000 + Number(y) : Number(y));

	function convert_dates(text) {
		const order = date_order();
		text = text.replace(NUMERIC, (match, a, _sep, b, c) => {
			const parts = { [order[0]]: Number(a), [order[1]]: Number(b), [order[2]]: Number(c) };
			if (String(a).length === 4) Object.assign(parts, { y: Number(a), m: Number(b), d: Number(c) });
			return jalali(parts.y, parts.m, parts.d) || match;
		});
		text = text.replace(DAY_MONTH, (match, d, mon, y) => {
			return jalali(full_year(y), MONTHS_EN.indexOf(mon) + 1, Number(d)) || match;
		});
		text = text.replace(MONTH_DAY, (match, mon, d, y) => {
			return jalali(full_year(y), MONTHS_EN.indexOf(mon) + 1, Number(d)) || match;
		});
		return text;
	}

	// The calendar of the date picker is Gregorian; its English day and month names get Persian ones
	const CALENDAR_WORDS = {
		Su: "ی",
		Mo: "د",
		Tu: "س",
		We: "چ",
		Th: "پ",
		Fr: "ج",
		Sa: "ش",
		Jan: "ژانویه",
		Feb: "فوریه",
		Mar: "مارس",
		Apr: "آوریل",
		May: "مه",
		Jun: "ژوئن",
		Jul: "ژوئیه",
		Aug: "اوت",
		Sep: "سپتامبر",
		Oct: "اکتبر",
		Nov: "نوامبر",
		Dec: "دسامبر",
	};

	function translate(text) {
		const word = text.trim();
		if (CALENDAR_WORDS[word]) return text.replace(word, CALENDAR_WORDS[word]);
		const messages = (window.frappe && frappe._messages) || {};
		const key = text.trim();
		return key && messages[key] && messages[key] !== key ? text.replace(key, messages[key]) : text;
	}

	function fix(node) {
		const value = node.nodeValue;
		if (!value || !/[A-Za-z0-9]/.test(value)) return;
		const fixed = convert_dates(translate(value));
		if (fixed !== value) node.nodeValue = fixed;
	}

	function walk(root) {
		if (root.nodeType === Node.TEXT_NODE) return fix(root);
		if (root.nodeType !== Node.ELEMENT_NODE || root.closest("input, textarea, script, style")) return;
		const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
		let node;
		while ((node = walker.nextNode())) fix(node);
		root.querySelectorAll("[placeholder]").forEach((el) => {
			const placeholder = el.getAttribute("placeholder");
			const fixed = translate(placeholder);
			if (fixed !== placeholder) el.setAttribute("placeholder", fixed);
		});
	}

	// Periods of the Jalali calendar. The page's own periods («این ماه») are Gregorian months; these
	// set the page's stored date range and reload it.
	function jalali_range(kind) {
		const today = new Date();
		const j = iran_erp.jalaali.to_jalali(today.getFullYear(), today.getMonth() + 1, today.getDate());
		let from, to;
		if (kind === "month" || kind === "last_month") {
			let { jy, jm } = j;
			if (kind === "last_month") [jy, jm] = jm === 1 ? [jy - 1, 12] : [jy, jm - 1];
			from = [jy, jm, 1];
			to = [jy, jm, iran_erp.jalaali.month_length(jy, jm)];
		} else if (kind === "quarter") {
			const first = Math.floor((j.jm - 1) / 3) * 3 + 1;
			from = [j.jy, first, 1];
			to = [j.jy, first + 2, iran_erp.jalaali.month_length(j.jy, first + 2)];
		} else {
			from = [j.jy, 1, 1];
			to = [j.jy, 12, iran_erp.jalaali.month_length(j.jy, 12)];
		}
		const iso = ([jy, jm, jd]) => {
			const g = iran_erp.jalaali.to_gregorian(jy, jm, jd);
			return `${g.gy}-${pad2(g.gm)}-${pad2(g.gd)}`;
		};
		return { fromDate: iso(from), toDate: iso(to) };
	}

	function add_jalali_periods() {
		const bar = document.createElement("div");
		bar.className = "iran-banking-periods";
		bar.setAttribute("dir", "rtl");
		bar.innerHTML = `<span>${translate("Jalali period")}:</span>`;
		[
			["month", "این ماه"],
			["last_month", "ماه قبل"],
			["quarter", "این فصل"],
			["year", "امسال"],
		].forEach(([kind, label]) => {
			const button = document.createElement("button");
			button.type = "button";
			button.textContent = label;
			button.addEventListener("click", () => {
				try {
					localStorage.setItem("bank-rec-date", JSON.stringify(jalali_range(kind)));
				} catch (e) {
					return;
				}
				window.location.reload();
			});
			bar.appendChild(button);
		});
		const style = document.createElement("style");
		style.textContent = `
			.iran-banking-periods { position: fixed; bottom: 16px; left: 16px; z-index: 50; display: flex;
				gap: 6px; align-items: center; padding: 6px 10px; border-radius: 999px; font-size: 13px;
				background: #fff; border: 1px solid #e2e2e2; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
			.iran-banking-periods button { border: 1px solid #e2e2e2; border-radius: 999px; padding: 2px 10px;
				background: #f8f8f8; cursor: pointer; font: inherit; }
			.iran-banking-periods button:hover { background: #ededed; }
			@media (prefers-color-scheme: dark) {
				.iran-banking-periods { background: #1f1f1f; border-color: #383838; color: #ededed; }
				.iran-banking-periods button { background: #2a2a2a; border-color: #383838; color: inherit; }
			}`;
		document.head.appendChild(style);
		document.body.appendChild(bar);
	}

	function start() {
		if (!(window.iran_erp && iran_erp.jalaali)) return;
		walk(document.body);
		new MutationObserver((mutations) => {
			for (const mutation of mutations) {
				if (mutation.type === "characterData") fix(mutation.target);
				mutation.addedNodes.forEach(walk);
			}
		}).observe(document.body, { childList: true, subtree: true, characterData: true });
		// The page's translations arrive after it first draws; go over it again once they are in
		Promise.resolve(window.frappe && frappe._translations_loaded).then(() => {
			walk(document.body);
			add_jalali_periods();
			document.title = translate("Banking") + " | " + (document.title.split("|")[1] || "").trim();
		});
	}

	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
	else start();
})();
