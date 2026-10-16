// Report tables (frappe DataTable) sized to what they hold.
//
// The table sizes a column from its header and its first row only, and keeps any width the report
// sets; values further down were cut («246,200,293,...») while other tables were wider than needed
// and scrolled sideways for nothing. Here every column gets the width of its longest header or
// value among the first rows (indented tree rows included), within limits; when the columns
// together are narrower than the page they are widened to fill it, so the table scrolls sideways
// only when its content really is wider than the page.

frappe.provide("iran_erp.tables");

iran_erp.tables.SAMPLE_ROWS = 300;
iran_erp.tables.MIN_WIDTH = 70;
iran_erp.tables.MAX_WIDTH = 420;
iran_erp.tables.PADDING = 34;
// Canvas measures come out a little narrower than the table draws the same text
iran_erp.tables.SCALE = 1.08;
iran_erp.tables.INDENT = 20;

iran_erp.tables.measure = (function () {
	let context = null;
	return function (text, bold) {
		if (!context) context = document.createElement("canvas").getContext("2d");
		const style = getComputedStyle(document.body);
		context.font = `${bold ? 600 : 400} 13px ${style.fontFamily}`;
		const value = String(text);
		// Digits are drawn as Persian digits, which are a little wider than the ones measured here
		const digits = document.documentElement.dir === "rtl" ? (value.match(/\d/g) || []).length : 0;
		return context.measureText(value).width + digits * 1.9;
	};
})();

iran_erp.tables.text = function (html) {
	if (html === null || html === undefined) return "";
	const value = String(html);
	if (!value.includes("<")) return value;
	const div = document.createElement("div");
	div.innerHTML = value;
	return div.textContent || "";
};

// The text a cell will show: through the column's own formatter when it has one
iran_erp.tables.cell_text = function (column, value, row) {
	if (value === null || value === undefined || value === "") return "";
	try {
		if (typeof column.format === "function") {
			return iran_erp.tables.text(column.format(value, row, column, row));
		}
		if (column.docfield || column.fieldtype) {
			const df = column.docfield || { fieldtype: column.fieldtype, options: column.options };
			return iran_erp.tables.text(frappe.format(value, df, { always_show_decimals: false }, row));
		}
	} catch (e) {
		// Formatters written for the full row may fail on the raw values; the value itself is close
	}
	return typeof value === "object" ? iran_erp.tables.text(value.content ?? "") : String(value);
};

// Amount columns are headed with the currency's code («بدهکار (IRR)»); the rial is named in Persian
iran_erp.tables.currency_label = function (column) {
	const fixed = { ...column };
	["name", "label", "content"].forEach((key) => {
		if (typeof fixed[key] === "string") fixed[key] = fixed[key].replace(/\(IRR\)/g, "(ریال)");
	});
	return fixed;
};

iran_erp.tables.fit = function (wrapper, options) {
	const columns = options && options.columns;
	const data = (options && options.data) || [];
	if (!Array.isArray(columns) || !columns.length || options.layout === "ratio") return options;
	const T = iran_erp.tables;
	const rows = data.slice(0, T.SAMPLE_ROWS);
	const widths = columns.map((column, index) => {
		if (typeof column !== "object" || column === null) return null;
		if (column.iran_fixed_width) return column.width;
		let width = T.measure(__(column.name || column.label || column.content || ""), true);
		const key = column.id || column.fieldname;
		rows.forEach((row) => {
			let value;
			if (Array.isArray(row)) value = row[index];
			else if (row && typeof row === "object") value = row[key];
			const text = T.cell_text(column, value, row);
			let cell = T.measure(text, row && (row.bold || row.is_total_row));
			// Tree reports indent the first column by the row's level
			if (index === 0 && row && !Array.isArray(row) && row.indent) cell += row.indent * T.INDENT + 16;
			if (cell > width) width = cell;
		});
		// Link cells draw a little more than their text
		const fieldtype = column.fieldtype || (column.docfield && column.docfield.fieldtype);
		const extra = ["Link", "Dynamic Link"].includes(fieldtype) ? 18 : 0;
		return Math.round(Math.min(T.MAX_WIDTH, Math.max(T.MIN_WIDTH, width * T.SCALE + T.PADDING + extra)));
	});

	// Room on the page for the columns: the table's width less the row number and checkbox columns
	const available = (wrapper && wrapper.clientWidth ? wrapper.clientWidth : 0) - 90;
	const total = widths.reduce((sum, w) => sum + (w || 0), 0);
	const scale = available > 0 && total > 0 && total < available ? available / total : 1;

	options.columns = columns.map((column, i) => {
		if (widths[i] === null) return column;
		return { ...T.currency_label(column), width: Math.floor(widths[i] * scale) };
	});
	return options;
};

iran_erp.tables.wrap = function (Base) {
	if (!Base || !Base.prototype || Base.prototype.iran_fitted) return Base;
	const proto = Base.prototype;

	// Every table is drawn through refresh: the constructor calls it with no arguments, lists in
	// report view call it again with the rows they load
	const refresh = proto.refresh;
	proto.refresh = function (data, columns) {
		const rows = data || this.options.data;
		const source = columns || this.options.columns;
		if (Array.isArray(rows) && rows.length && Array.isArray(source)) {
			const fitted = iran_erp.tables.fit(this.wrapper, {
				data: rows,
				columns: source,
				layout: this.options.layout,
			}).columns;
			if (columns) columns = fitted;
			else this.options.columns = fitted;
		}
		return refresh.call(this, data, columns);
	};
	proto.iran_fitted = true;

	// The row-number column is measured in the default font; Persian digits are a little wider,
	// so «10» showed as «0...»
	const holder = document.createElement("div");
	holder.style.cssText = "position:absolute;left:-9999px;top:0;width:200px;";
	try {
		document.body.appendChild(holder);
		const probe = new Base(holder, { columns: ["x"], data: [] });
		const Style = Object.getPrototypeOf(probe.style);
		if (!Style.iran_row_index) {
			const row_index_width = Style.getRowIndexColumnWidth;
			Style.getRowIndexColumnWidth = function () {
				return row_index_width.call(this) + 16;
			};
			Style.iran_row_index = true;
		}
		// Columns without an alignment are set to the left, where a Persian page starts on the right:
		// text there began at the far side of its column
		if (!Style.iran_rtl_align) {
			const set_column_style = Style.setColumnStyle;
			Style.setColumnStyle = function () {
				if (document.documentElement.dir === "rtl") {
					this.datamanager.getColumns().forEach((column) => {
						if (!column.align || column.align === "left") column.align = "right";
					});
				}
				return set_column_style.call(this);
			};
			Style.iran_rtl_align = true;
		}
		probe.destroy && probe.destroy();
	} catch (e) {
		// The row numbers keep the table's own width
	} finally {
		holder.remove();
	}
	return Base;
};

// The table class arrives with the report bundle, which loads only when a report is opened
(function () {
	for (const [owner, key] of [
		[window, "DataTable"],
		[frappe, "DataTable"],
	]) {
		let current = iran_erp.tables.wrap(owner[key]);
		Object.defineProperty(owner, key, {
			configurable: true,
			get: () => current,
			set: (value) => (current = iran_erp.tables.wrap(value)),
		});
	}
})();

// Lists (/desk/<doctype>) are not tables: each row is a line of boxes, most of them sharing the width
// equally, so a short date had room to spare while the name and the ID beside it were cut. Each
// column is measured at the width of its widest box and the room left on the page is shared out
// in proportion; the list scrolls sideways only when its content really is wider than the page. A
// width the user set by dragging a column's edge is kept.
iran_erp.tables.LIST_MAX_WIDTH = 460;

iran_erp.tables.LIST_MIN_CAP = 160;

// The widest a column may be for all of them to fit in the room there is, no narrower than
// LIST_MIN_CAP: columns wider than that give up the difference
iran_erp.tables.list_cap = function (widths, available) {
	const sorted = [...widths].sort((a, b) => b - a);
	let rest = widths.reduce((sum, w) => sum + w, 0);
	for (let i = 0; i < sorted.length; i++) {
		rest -= sorted[i];
		// The first i+1 columns at the same cap, the rest as they are
		const cap = (available - rest) / (i + 1);
		if (cap >= (sorted[i + 1] || 0)) return Math.max(iran_erp.tables.LIST_MIN_CAP, Math.floor(cap));
	}
	return iran_erp.tables.LIST_MIN_CAP;
};

iran_erp.tables.fit_list = function (listview) {
	const result = listview.$result && listview.$result[0];
	if (!result || !result.offsetParent || frappe.is_mobile()) return;
	const manual = new Set(
		(listview.columns || [])
			.filter((col) => col.df && cint(col.df.width))
			.map((col) => (col.type === "Status" ? "status_field" : col.df.fieldname))
	);
	const cells = [...result.querySelectorAll(".level-left .list-row-col[data-fieldname]")].filter(
		(el) => el.dataset.fieldname && el.dataset.fieldname !== "undefined" && !manual.has(el.dataset.fieldname)
	);
	if (!cells.length) return;

	// Every box at the width of its content, measured in one pass
	result.classList.add("iran-list-measure");
	const widths = {};
	cells.forEach((el) => {
		const name = el.dataset.fieldname;
		widths[name] = Math.max(widths[name] || 0, Math.ceil(el.getBoundingClientRect().width) + 4);
	});
	result.classList.remove("iran-list-measure");

	const head = result.querySelector(".list-row-head");
	const left = head && head.querySelector(".level-left");
	const right = head && head.querySelector(".level-right");
	if (!head || !left) return;
	const style = getComputedStyle(head);
	const first = left.querySelector(".list-row-col");
	const gap = first ? parseFloat(getComputedStyle(first).marginLeft) + parseFloat(getComputedStyle(first).marginRight) : 15;
	// Columns the measure leaves alone keep their room: a user's own widths in full, the others
	// (the button and tag columns, which take what is left over) only their spacing
	let fixed = 0;
	left.querySelectorAll(":scope > .list-row-col").forEach((el) => {
		const name = el.dataset.fieldname;
		if (name in widths || !el.offsetWidth) return;
		fixed += (manual.has(name) ? el.getBoundingClientRect().width : 0) + gap;
	});
	// The list grows past the page to fit wide columns, so the page is the box it scrolls in
	const page = result.closest(".result-container") || result;
	const available =
		page.clientWidth -
		parseFloat(style.paddingLeft) -
		parseFloat(style.paddingRight) -
		(right ? right.getBoundingClientRect().width : 0) -
		fixed -
		Object.keys(widths).length * gap -
		8;
	const total = Object.values(widths).reduce((sum, w) => sum + w, 0);
	let cap = iran_erp.tables.LIST_MAX_WIDTH;
	if (available > 0 && total > available) {
		// A little too wide: the longest columns (long account names) give up the difference, so the
		// short ones beside them (the ID) stay in sight; much too wide and the list scrolls
		cap = iran_erp.tables.list_cap(Object.values(widths), available);
	}
	const capped = Object.values(widths).reduce((sum, w) => sum + Math.min(w, cap), 0);
	const scale = available > 0 && capped > 0 && capped < available ? available / capped : 1;
	Object.entries(widths).forEach(([name, width]) => {
		listview.column_max_widths[name] = Math.floor(Math.min(width, cap) * scale);
	});
};

$(document).on("app_ready", () => {
	const list = frappe.views.ListView && frappe.views.ListView.prototype;
	if (!list || list.iran_fitted) return;
	list.iran_fitted = true;
	const apply_column_widths = list.apply_column_widths;
	list.apply_column_widths = function () {
		if (!this.list_view_settings?.disable_scrolling) {
			try {
				iran_erp.tables.fit_list(this);
			} catch (e) {
				// The list keeps its own widths
			}
		}
		apply_column_widths.call(this);
		// Measured before the Persian font arrived, the text was wider than it will be drawn
		if (document.fonts && document.fonts.status !== "loaded" && !this.iran_fonts_wait) {
			this.iran_fonts_wait = true;
			document.fonts.ready.then(() => this.apply_column_widths());
		}
		// The list's own limit is narrower than a long name may need
		if (this.list_view_settings?.disable_scrolling) return;
		Object.entries(this.column_max_widths).forEach(([name, width]) => {
			if (width <= 400) return;
			this.$result.find(`.level-left .list-row-col[data-fieldname="${name}"]`).css({
				width,
				flex: `0 0 ${width}px`,
			});
		});
	};
});
