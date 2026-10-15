// Jalali <-> Gregorian date conversion, with no other dependency: used by the desk (jalali.js) and by
// pages outside it, such as ERPNext's Banking page.

window.iran_erp = window.iran_erp || {};

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
