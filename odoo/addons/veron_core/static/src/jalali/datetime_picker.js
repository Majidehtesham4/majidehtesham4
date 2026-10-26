/** The date picker in Shamsi months and years, with Gregorian dates underneath. */
import { _t } from "@web/core/l10n/translation";
import { DateTimePicker } from "@web/core/datetime/datetime_picker";
import { isInRange, today } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import * as jalali from "./jalali";

const { Info } = luxon;

const startOfWeek = (date) => {
    const { weekStart } = localization;
    return date.set({ weekday: date.weekday < weekStart ? weekStart - 7 : weekStart });
};

const item = ({ range, label, isOutOfRange = false, isValid = true, extraClass = "" }) => ({
    id: range[0].toISODate(),
    includesToday: isInRange(today(), range),
    isOutOfRange,
    isValid,
    label: String(label),
    range,
    extraClass,
});

const yearOf = (date) => jalali.toJalali(date).year;
const yearRange = (year, like) => [
    jalali.fromJalali(year, 1, 1, like),
    jalali.fromJalali(year + 1, 1, 1, like).minus({ millisecond: 1 }),
];

const LEVELS = new Map()
    .set("days", {
        mainTitle: _t("Select month"),
        nextTitle: _t("Next month"),
        prevTitle: _t("Previous month"),
        move: (date, n) => jalali.addMonths(jalali.startOfMonth(date), n),
        getTitle: (date) => jalali.monthTitle(date),
        getItems: (date, { maxDate, minDate, showWeekNumbers, isDateValid, dayCellClass }) => {
            const monthRange = [jalali.startOfMonth(date), jalali.endOfMonth(date)];
            const weeks = [];
            let start = startOfWeek(monthRange[0]);
            for (let w = 0; w < 6; w++) {
                const days = [];
                for (let d = 0; d < 7; d++) {
                    const day = start.plus({ day: d });
                    const range = [day, day.endOf("day")];
                    days.push(
                        item({
                            range,
                            label: jalali.toJalali(day).day,
                            isOutOfRange: !isInRange(day, monthRange),
                            isValid: isInRange(range, [minDate, maxDate]) && (isDateValid?.(day) ?? true),
                            extraClass: dayCellClass?.(day) || "",
                        })
                    );
                }
                weeks.push({ number: days[3].range[0].weekNumber, days });
                start = start.plus({ day: 7 });
            }
            const daysOfWeek = weeks[0].days.map((d) => [
                d.range[0].weekdayShort,
                d.range[0].weekdayLong,
                Info.weekdays("narrow", { locale: d.range[0].locale })[d.range[0].weekday - 1],
            ]);
            if (showWeekNumbers) {
                daysOfWeek.unshift(["", _t("Week numbers"), ""]);
            }
            return [{ id: "__month__0", number: jalali.toJalali(monthRange[0]).month, daysOfWeek, weeks }];
        },
    })
    .set("months", {
        mainTitle: _t("Select year"),
        nextTitle: _t("Next year"),
        prevTitle: _t("Previous year"),
        move: (date, n) => jalali.addMonths(jalali.startOfMonth(date), 12 * n),
        getTitle: (date) => String(yearOf(date)),
        getItems: (date, { maxDate, minDate }) => {
            const year = yearOf(date);
            return jalali.MONTHS.map((name, i) => {
                const start = jalali.fromJalali(year, i + 1, 1, date);
                const range = [start, jalali.endOfMonth(start)];
                return item({ range, label: name, isValid: isInRange(range, [minDate, maxDate]) });
            });
        },
    })
    .set("years", {
        mainTitle: _t("Select decade"),
        nextTitle: _t("Next decade"),
        prevTitle: _t("Previous decade"),
        move: (date, n) => jalali.addMonths(jalali.startOfMonth(date), 120 * n),
        getTitle: (date) => {
            const decade = Math.floor(yearOf(date) / 10) * 10;
            return `${decade - 1} - ${decade + 10}`;
        },
        getItems: (date, { maxDate, minDate }) => {
            const decade = Math.floor(yearOf(date) / 10) * 10;
            return [...Array(12)].map((_, i) => {
                const range = yearRange(decade + i - 1, date);
                return item({
                    range,
                    label: decade + i - 1,
                    isOutOfRange: i === 0 || i === 11,
                    isValid: isInRange(range, [minDate, maxDate]),
                });
            });
        },
    })
    .set("decades", {
        mainTitle: _t("Select century"),
        nextTitle: _t("Next century"),
        prevTitle: _t("Previous century"),
        move: (date, n) => jalali.addMonths(jalali.startOfMonth(date), 1200 * n),
        getTitle: (date) => {
            const century = Math.floor(yearOf(date) / 100) * 100;
            return `${century - 10} - ${century + 100}`;
        },
        getItems: (date, { maxDate, minDate }) => {
            const century = Math.floor(yearOf(date) / 100) * 100;
            return [...Array(12)].map((_, i) => {
                const first = century + (i - 1) * 10;
                const range = [yearRange(first, date)[0], yearRange(first + 9, date)[1]];
                return item({
                    range,
                    label: first,
                    isOutOfRange: i === 0 || i === 11,
                    isValid: isInRange(range, [minDate, maxDate]),
                });
            });
        },
    });

patch(DateTimePicker.prototype, {
    get activePrecisionLevel() {
        return jalali.isActive() ? LEVELS.get(this.state.precision) : super.activePrecisionLevel;
    },

    adjustFocus(values, focusedDateIndex) {
        if (!jalali.isActive()) {
            return super.adjustFocus(values, focusedDateIndex);
        }
        if (!this.shouldAdjustFocusDate && this.state.focusDate) {
            return;
        }
        const date = values[focusedDateIndex] || values[focusedDateIndex === 1 ? 0 : 1] || today();
        this.shouldAdjustFocusDate = false;
        this.state.focusDate = this.clamp(jalali.startOfMonth(date));
    },

    next(ev) {
        if (!jalali.isActive()) {
            return super.next(ev);
        }
        ev.preventDefault();
        this.state.focusDate = this.clamp(this.activePrecisionLevel.move(this.state.focusDate, 1));
    },

    previous(ev) {
        if (!jalali.isActive()) {
            return super.previous(ev);
        }
        ev.preventDefault();
        this.state.focusDate = this.clamp(this.activePrecisionLevel.move(this.state.focusDate, -1));
    },
});

// Week numbers are Gregorian ones: not shown beside Shamsi months
registry.category("services").add("veron_jalali_picker", {
    dependencies: ["veron_jalali"],
    start() {
        if (jalali.isActive()) {
            DateTimePicker.defaultProps = { ...DateTimePicker.defaultProps, showWeekNumbers: false };
        }
    },
});
