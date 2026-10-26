/**
 * The date filters of the search bar in Shamsi: the months, the seasons and the years offered are Shamsi,
 * and so is the range of dates they search. The options keep Odoo's own ids (month-1, year, first_quarter…),
 * so saved favorites and default_period keep working.
 */
import { Domain } from "@web/core/domain";
import { serializeDate, serializeDateTime } from "@web/core/l10n/dates";
import { clamp } from "@web/core/utils/numbers";
import { patch } from "@web/core/utils/patch";
import { SearchModel } from "@web/search/search_model";
import { toGeneratorId, yearSelected } from "@web/search/utils/dates";
import * as jalali from "./jalali";

export const SEASONS = ["بهار", "تابستان", "پاییز", "زمستان"];
const QUARTER_IDS = ["first_quarter", "second_quarter", "third_quarter", "fourth_quarter"];

/** The options of a date filter, as getPeriodOptions of Odoo, in Shamsi */
export function getPeriodOptions(referenceMoment, optionsParams) {
    const { startYear, endYear, startMonth, endMonth, customOptions } = optionsParams;
    const reference = jalali.toJalali(referenceMoment);
    const yearShift = clamp(0, startYear, endYear);
    const months = [];
    for (let monthOffset = startMonth; monthOffset <= endMonth; monthOffset++) {
        const { year, month } = jalali.toJalali(
            jalali.addMonths(referenceMoment, monthOffset + 12 * yearShift)
        );
        months.push({
            id: toGeneratorId("month", monthOffset),
            defaultYearId: toGeneratorId("year", clamp(year - reference.year, startYear, endYear)),
            description: jalali.MONTHS[month - 1],
            granularity: "month",
            groupNumber: 1,
            month,
        });
    }
    const defaultYearId = toGeneratorId("year", yearShift);
    const quarters = QUARTER_IDS.map((id, i) => ({
        id,
        defaultYearId,
        description: SEASONS[i],
        granularity: "quarter",
        groupNumber: 1,
        quarter: i + 1,
    }));
    const years = [];
    for (let offset = startYear; offset <= endYear; offset++) {
        years.push({
            id: toGeneratorId("year", offset),
            description: String(reference.year + offset),
            granularity: "year",
            groupNumber: 2,
            year: reference.year + offset,
        });
    }
    const custom = customOptions.map((option) => ({
        id: option.id,
        description: option.description,
        granularity: "withDomain",
        groupNumber: 3,
        domain: option.domain,
    }));
    return [...months.reverse(), ...quarters.reverse(), ...years.reverse(), ...custom];
}

/** The domain and the description of the selected options, as constructDateDomain of Odoo, in Shamsi */
export function constructDateDomain(referenceMoment, searchItem, selectedOptionIds) {
    const options = getPeriodOptions(referenceMoment, searchItem.optionsParams);
    const selected = selectedOptionIds
        .map((id) => options.find((option) => option.id === id))
        .filter(Boolean);
    const withDomain = selected.find((option) => option.granularity === "withDomain");
    if (withDomain) {
        return {
            description: withDomain.description,
            domain: Domain.and([withDomain.domain, searchItem.domain]),
        };
    }
    const years = selected.filter((option) => option.granularity === "year");
    years.sort((a, b) => a.year - b.year);
    const parts = selected.filter((option) => ["month", "quarter"].includes(option.granularity));
    const rank = (option) => (option.granularity === "month" ? option.month : 12 + option.quarter);
    parts.sort((a, b) => rank(a) - rank(b));
    const ranges = [];
    for (const { year } of years) {
        if (!parts.length) {
            ranges.push(dateRange(searchItem, year, 1, 12, String(year)));
        }
        for (const part of parts) {
            if (part.granularity === "month") {
                ranges.push(dateRange(searchItem, year, part.month, 1, `${part.description} ${year}`));
            } else {
                const first = 3 * part.quarter - 2;
                ranges.push(dateRange(searchItem, year, first, 3, `${part.description} ${year}`));
            }
        }
    }
    const domain = Domain.and([
        Domain.combine(
            ranges.map((range) => range.domain),
            "OR"
        ),
        searchItem.domain,
    ]);
    return { domain, description: ranges.map((range) => range.description).join("/") };
}

/** count Shamsi months from the 1st of month of year */
function dateRange({ fieldName, fieldType }, year, month, count, description) {
    const start = jalali.fromJalali(year, month, 1);
    const end = jalali.addMonths(start, count).minus({ days: 1 }).endOf("day");
    const serialize = fieldType === "date" ? serializeDate : serializeDateTime;
    const domain = new Domain([
        "&",
        [fieldName, ">=", serialize(start)],
        [fieldName, "<=", serialize(end)],
    ]);
    return { domain, description };
}

patch(SearchModel.prototype, {
    toggleDateFilter(searchItemId, generatorId) {
        const searchItem = this.searchItems[searchItemId];
        if (!jalali.isActive() || searchItem.type !== "dateFilter") {
            return super.toggleDateFilter(...arguments);
        }
        // As Odoo's own, but the year added with a month or a season is its Shamsi year
        const generatorIds = generatorId ? [generatorId] : searchItem.defaultGeneratorIds;
        for (const generatorId of generatorIds) {
            const index = this.query.findIndex(
                (queryElem) =>
                    queryElem.searchItemId === searchItemId &&
                    "generatorId" in queryElem &&
                    queryElem.generatorId === generatorId
            );
            if (index >= 0) {
                this.query.splice(index, 1);
                if (!yearSelected(this._getSelectedGeneratorIds(searchItemId))) {
                    this.query = this.query.filter(
                        (queryElem) => queryElem.searchItemId !== searchItemId
                    );
                }
            } else if (generatorId.startsWith("custom")) {
                this.query = this.query.filter(
                    (queryElem) => searchItemId !== queryElem.searchItemId
                );
                this.query.push({ searchItemId, generatorId });
            } else {
                this.query = this.query.filter(
                    (queryElem) =>
                        queryElem.searchItemId !== searchItemId ||
                        !queryElem.generatorId.startsWith("custom")
                );
                this.query.push({ searchItemId, generatorId });
                if (!yearSelected(this._getSelectedGeneratorIds(searchItemId))) {
                    const { defaultYearId } = getPeriodOptions(
                        this.referenceMoment,
                        searchItem.optionsParams
                    ).find((o) => o.id === generatorId);
                    this.query.push({ searchItemId, generatorId: defaultYearId });
                }
            }
        }
        this._notify();
    },

    _enrichItem(searchItem) {
        const item = super._enrichItem(...arguments);
        if (jalali.isActive() && item.type === "dateFilter" && item.options) {
            const active = new Set(item.options.filter((o) => o.isActive).map((o) => o.id));
            item.options = getPeriodOptions(this.referenceMoment, searchItem.optionsParams).map(
                ({ description, id, groupNumber }) => ({
                    description,
                    id,
                    groupNumber,
                    isActive: active.has(id),
                })
            );
        }
        return item;
    },

    _getDateFilterDomain(dateFilter, generatorIds, key = "domain") {
        if (!jalali.isActive()) {
            return super._getDateFilterDomain(...arguments);
        }
        return constructDateDomain(this.referenceMoment, dateFilter, generatorIds)[key];
    },
});
