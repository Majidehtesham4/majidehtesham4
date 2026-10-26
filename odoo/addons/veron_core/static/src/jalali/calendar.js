/** The calendar view in Shamsi: titles, day numbers, and the month page from the 1st of a Shamsi month. */
import { CalendarController } from "@web/views/calendar/calendar_controller";
import { CalendarModel } from "@web/views/calendar/calendar_model";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";
import { localization } from "@web/core/l10n/localization";
import { patch } from "@web/core/utils/patch";
import * as jalali from "./jalali";

const weekOf = (date) => jalali.week(date, localization.weekStart || 6);

patch(CalendarModel.prototype, {
    computeRange() {
        if (!jalali.isActive() || this.meta.scale !== "month") {
            return super.computeRange();
        }
        let start = jalali.startOfMonth(this.meta.date);
        let end = jalali.endOfMonth(this.meta.date);
        if (this.monthOverflow) {
            // Whole weeks, as Odoo's own month page
            start = start.minus({ days: (start.weekday - this.meta.firstDayOfWeek + 7) % 7 });
            end = end.plus({ days: (this.meta.firstDayOfWeek + 6 - end.weekday + 7) % 7 }).endOf("day");
        }
        return { start, end };
    },
});

patch(CalendarController.prototype, {
    async setDate(move) {
        if (!jalali.isActive() || !["month", "year"].includes(this.model.scale) || move === "today") {
            return super.setDate(move);
        }
        const months = (this.model.scale === "month" ? 1 : 12) * (move === "next" ? 1 : -1);
        await this.model.load({ date: jalali.addMonths(this.model.date, months) });
    },

    get dayHeader() {
        if (!jalali.isActive()) {
            return super.dayHeader;
        }
        const { year, month, day } = jalali.toJalali(this.date);
        return `${day} ${jalali.MONTHS[month - 1]} ${year}`;
    },

    get weekHeader() {
        if (!jalali.isActive()) {
            return super.weekHeader;
        }
        const { rangeStart, rangeEnd } = this.model;
        const [start, end] = [jalali.toJalali(rangeStart), jalali.toJalali(rangeEnd)];
        if (start.year !== end.year) {
            return `${jalali.monthTitle(rangeStart)} - ${jalali.monthTitle(rangeEnd)}`;
        }
        if (start.month !== end.month) {
            return `${jalali.MONTHS[start.month - 1]} - ${jalali.monthTitle(rangeEnd)}`;
        }
        return jalali.monthTitle(rangeStart);
    },

    get currentMonth() {
        return jalali.isActive() ? jalali.monthTitle(this.date) : super.currentMonth;
    },

    get currentYear() {
        return jalali.isActive() ? String(jalali.toJalali(this.date).year) : super.currentYear;
    },

    get currentWeek() {
        return jalali.isActive() ? weekOf(this.model.rangeStart) : super.currentWeek;
    },

    get today() {
        return jalali.isActive() ? String(jalali.toJalali(luxon.DateTime.now()).day) : super.today;
    },
});

patch(CalendarCommonRenderer.prototype, {
    get options() {
        const options = super.options;
        if (!jalali.isActive()) {
            return options;
        }
        options.weekNumberCalculation = (date) => weekOf(luxon.DateTime.fromJSDate(date));
        if (this.props.model.scale === "month") {
            options.dayCellContent = ({ date }) =>
                String(jalali.toJalali(luxon.DateTime.fromJSDate(date, { zone: "UTC" })).day);
            // Odoo's month page is a Gregorian month: the same grid over the Shamsi month's weeks
            const { rangeStart, rangeEnd } = this.props.model;
            options.views = {
                ...(options.views || {}),
                veronShamsiMonth: {
                    type: "dayGrid",
                    visibleRange: {
                        start: rangeStart.toISODate(),
                        end: rangeEnd.plus({ days: 1 }).toISODate(),
                    },
                },
            };
            options.initialView = "veronShamsiMonth";
        }
        return options;
    },

    headerTemplateProps(date) {
        const props = super.headerTemplateProps(date);
        if (jalali.isActive()) {
            const options = this.props.model.scale === "month" ? { zone: "UTC" } : {};
            props.day = jalali.toJalali(luxon.DateTime.fromJSDate(date, options).plus({ hour: 1 })).day;
        }
        return props;
    },
});
