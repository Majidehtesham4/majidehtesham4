/**
 * Spreadsheets and dashboards in Persian: list dates in Shamsi, «50,000 ریال» with its space, and the
 * date filter's month, season and year are Shamsi ones.
 */
import { CurrencyPlugin } from "@spreadsheet/currency/plugins/currency";
import { DateFilterDropdown } from "@spreadsheet/global_filters/components/date_filter_dropdown/date_filter_dropdown";
import { DateFilterValue } from "@spreadsheet/global_filters/components/date_filter_value/date_filter_value";
import {
    dateFilterValueToString,
    getDateDomain,
    getDateRange,
    getNextDateFilterValue,
    getPreviousDateFilterValue,
    getRelativeDateFromTo,
} from "@spreadsheet/global_filters/helpers";
import { GlobalFiltersCoreViewPlugin } from "@spreadsheet/global_filters/plugins/global_filters_core_view_plugin";
import { DashboardDateFilter } from "@spreadsheet_dashboard/bundle/dashboard_action/dashboard_date_filter/dashboard_date_filter";
import { DashboardSearchBar } from "@spreadsheet_dashboard/bundle/dashboard_action/dashboard_search_bar/dashboard_search_bar";
import { serializeDate } from "@web/core/l10n/dates";
import { helpers } from "@odoo/o-spreadsheet";
import { ListDataSource } from "@spreadsheet/list/list_data_source";
import { deserializeDate, deserializeDateTime, formatDate, formatDateTime } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";
import * as jalali from "@veron_core/jalali/jalali";
import { SEASONS } from "@veron_core/jalali/search_dates";

const { DateTime } = luxon;
const { toNumber } = helpers;

patch(ListDataSource.prototype, {
    // The spreadsheet turns a date into a number it then shows in Gregorian: the date as text instead
    _parseServerValue(field, value) {
        if (jalali.isActive() && value && field.type === "date") {
            return formatDate(deserializeDate(value));
        }
        if (jalali.isActive() && value && field.type === "datetime") {
            return formatDateTime(deserializeDateTime(value));
        }
        return super._parseServerValue(field, value);
    },
});

patch(CurrencyPlugin.prototype, {
    // The spreadsheet's format puts a symbol written after the amount right against it
    computeFormatFromCurrency(currency) {
        if (currency?.position !== "after") {
            return super.computeFormatFromCurrency(currency);
        }
        const decimals = currency.decimalPlaces ?? 2;
        return `#,##0${decimals ? "." + "0".repeat(decimals) : ""}[$ ${currency.symbol.trim()}]`;
    },
});

// Large numbers: «150 میلیون» rather than 150m, read by o_spreadsheet.js as models/assets.py adjusts it.
// Up to ten million in full, then millions, then billions: at least two digits, as rial amounts are told.
if (jalali.isActive()) {
    globalThis.veronLargeNumbers = (value) => {
        if (value < 1e7) {
            return { magnitude: 0, postFix: "" };
        }
        return value < 1e10 ? { magnitude: 2, postFix: " میلیون" } : { magnitude: 3, postFix: " میلیارد" };
    };
}

// ---- The date filter. Its month, quarter and year values {type, year, month | quarter} are Shamsi ones;
// a year above 1700 is a Gregorian value saved before, read as Odoo does.

const isShamsi = (value) =>
    jalali.isActive() && ["month", "quarter", "year"].includes(value?.type) && value.year < 1700;
const usesShamsi = (value) => isShamsi(value) || (jalali.isActive() && value?.type === "relative");

/** The current Shamsi month, season and year */
function current(type, monthOffset = 0) {
    const { year, month } = jalali.toJalali(jalali.addMonths(DateTime.local(), monthOffset));
    if (type === "month") {
        return { type, year, month };
    }
    return type === "quarter" ? { type, year, quarter: Math.ceil(month / 3) } : { type, year };
}

const span = (start, months) => ({
    from: start,
    to: jalali.addMonths(start, months).minus({ days: 1 }).endOf("day"),
});

function toString(value) {
    if (!isShamsi(value)) {
        return dateFilterValueToString(value);
    }
    if (value.type === "month") {
        return `${jalali.MONTHS[value.month - 1]} ${value.year}`;
    }
    return value.type === "quarter" ? `${SEASONS[value.quarter - 1]} ${value.year}` : String(value.year);
}

/** {from, to} of a value, offset periods later, as getDateRange */
function dateRange(value, offset = 0) {
    if (isShamsi(value)) {
        if (value.type === "month") {
            return span(jalali.addMonths(jalali.fromJalali(value.year, value.month, 1), offset), 1);
        }
        if (value.type === "quarter") {
            const start = jalali.fromJalali(value.year, value.quarter * 3 - 2, 1);
            return span(jalali.addMonths(start, 3 * offset), 3);
        }
        return span(jalali.fromJalali(value.year + offset, 1, 1), 12);
    }
    if (jalali.isActive() && value?.type === "relative") {
        const now = DateTime.local();
        const today = now.endOf("day");
        switch (value.period) {
            case "month_to_date":
                return { from: jalali.startOfMonth(jalali.addMonths(now, offset)), to: jalali.addMonths(today, offset) };
            case "last_month":
                return span(jalali.startOfMonth(jalali.addMonths(now, offset - 1)), 1);
            case "year_to_date":
                return {
                    from: jalali.startOfYear(jalali.addMonths(now, 12 * offset)),
                    to: jalali.addMonths(today, 12 * offset),
                };
            case "last_12_months":
                return span(jalali.startOfMonth(jalali.addMonths(now, 12 * offset - 12)), 12);
        }
        return getRelativeDateFromTo(now, offset, value.period);
    }
    return getDateRange(value, offset);
}

/** The value of the period after (step 1) or before (step -1), as getNextDateFilterValue */
function step(value, direction) {
    const odoo = direction > 0 ? getNextDateFilterValue : getPreviousDateFilterValue;
    if (!jalali.isActive() || value?.type !== "relative") {
        return odoo(value);
    }
    switch (value.period) {
        case "last_month":
            return current("month", direction > 0 ? 0 : -2);
        case "month_to_date":
            return current("month", direction);
        case "year_to_date":
            return current("year", 12 * direction);
        case "last_12_months": {
            const { from, to } = dateRange(value, direction);
            return { type: "range", from: from.toISODate(), to: to.toISODate() };
        }
    }
    return odoo(value);
}

patch(GlobalFiltersCoreViewPlugin.prototype, {
    _getDateValueFromDefaultValue(defaultValue) {
        const types = { this_year: "year", this_quarter: "quarter", this_month: "month" };
        if (jalali.isActive() && defaultValue in types) {
            return current(types[defaultValue]);
        }
        return super._getDateValueFromDefaultValue(...arguments);
    },

    _getDateFilterDisplayValue(filter) {
        const value = this.getGlobalFilterValue(filter.id);
        if (!usesShamsi(value)) {
            return super._getDateFilterDisplayValue(...arguments);
        }
        const { from, to } = dateRange(value);
        const locale = this.getters.getLocale();
        const cell = (date) => ({
            value: date ? toNumber(serializeDate(date), locale) : "",
            format: locale.dateFormat,
        });
        return [[cell(from)], [cell(to)]];
    },

    _getDateDomain(filter, fieldMatching) {
        const value = this.getGlobalFilterValue(filter.id);
        if (!fieldMatching.chain || !usesShamsi(value)) {
            return super._getDateDomain(...arguments);
        }
        const { from, to } = dateRange(value, fieldMatching.offset || 0);
        return getDateDomain(from, to, fieldMatching.chain, fieldMatching.type);
    },
});

patch(DateFilterDropdown.prototype, {
    _computeDefaultSelectedValues() {
        super._computeDefaultSelectedValues();
        if (jalali.isActive()) {
            Object.assign(this.selectedValues, {
                month: current("month"),
                quarter: current("quarter"),
                year: current("year"),
            });
        }
    },

    _setRangeToCurrentValue(value) {
        super._setRangeToCurrentValue(value);
        if (usesShamsi(value)) {
            const { from, to } = dateRange(value);
            this.selectedValues.range = { type: "range", from: from.toISODate(), to: to.toISODate() };
        } else if (jalali.isActive() && !value) {
            const { from, to } = dateRange(current("month"));
            this.selectedValues.range = { type: "range", from: from.toISODate(), to: to.toISODate() };
        }
    },

    getDescription(type) {
        return toString(this.selectedValues[type]);
    },

    selectPrevious(type) {
        this.selectedValues[type] = step(this.selectedValues[type], -1);
    },

    selectNext(type) {
        this.selectedValues[type] = step(this.selectedValues[type], 1);
    },
});

patch(DateFilterValue.prototype, {
    get inputValue() {
        return toString(this.props.value);
    },
});

patch(DashboardDateFilter.prototype, {
    get inputValue() {
        return toString(this.props.value);
    },

    selectPrevious() {
        if (!jalali.isActive() || this.props.value?.type !== "relative") {
            return super.selectPrevious();
        }
        this.props.update(step(this.props.value, -1));
    },

    selectNext() {
        if (!jalali.isActive() || this.props.value?.type !== "relative") {
            return super.selectNext();
        }
        this.props.update(step(this.props.value, 1));
    },
});

patch(DashboardSearchBar.prototype, {
    async getFacetFor(filter) {
        const facet = await super.getFacetFor(...arguments);
        if (filter.type === "date" && jalali.isActive()) {
            facet.values = [toString(this.props.model.getters.getGlobalFilterValue(filter.id))];
        }
        return facet;
    },
});
