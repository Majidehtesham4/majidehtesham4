// ERP-VERON in place of the framework underneath: the About dialog, the support link of the user
// menu, the links to the upstream documentation in the Help menu and the advertising banners of
// the side menu.

frappe.provide("iran_erp.brand");

iran_erp.brand.NAME = "ERP-VERON";
iran_erp.brand.LOGO = "/assets/iran_erp/images/erp-veron-logo.svg";
iran_erp.brand.WEBSITE = "https://erpveron.com";
iran_erp.brand.PROGRAMMER = "مجید احتشام";

iran_erp.brand.open_website = function () {
	window.open(iran_erp.brand.WEBSITE, "_blank", "noopener");
};

// The year in the Jalali calendar, for the copyright line
iran_erp.brand.jalali_year = function () {
	const today = new Date();
	if (!(iran_erp.jalaali && iran_erp.jalaali.to_jalali)) return "";
	return iran_erp.jalaali.to_jalali(today.getFullYear(), today.getMonth() + 1, today.getDate()).jy;
};

iran_erp.brand.about = function () {
	const B = iran_erp.brand;
	if (B.about_dialog) {
		B.about_dialog.show();
		return false;
	}
	const esc = frappe.utils.escape_html;
	const version = frappe.boot.iran_version || "";
	const features = [
		"حسابداری با سرفصل‌های استاندارد ایرانی، تقویم شمسی و گزارش‌های مالی",
		"فروش، خرید، انبار و تولید در یک سامانه یکپارچه",
		"مدیریت چک‌های دریافتی و پرداختی",
		"آماده برای سامانه مودیان مالیاتی",
		"دستیار هوشمند فارسی و راهنمای کامل هر صفحه",
	];
	const dialog = new frappe.ui.Dialog({ title: `${__("About")} ${B.NAME}` });
	$(dialog.wrapper).addClass("iran-about-dialog");
	$(dialog.body).html(`
		<div class="iran-about" dir="rtl">
			<div class="iran-about-head">
				<img src="${B.LOGO}" alt="${B.NAME}" class="iran-about-logo">
				<div>
					<div class="iran-about-name">${B.NAME}</div>
					<div class="iran-about-tagline">نرم‌افزار یکپارچه مدیریت کسب‌وکار، ساخته‌شده برای شرکت‌های ایرانی</div>
					${version ? `<div class="iran-about-version">نسخه ${esc(String(version))}</div>` : ""}
				</div>
			</div>
			<ul class="iran-about-features">${features.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
			<div class="iran-about-rows">
				<div class="iran-about-row">
					<span class="iran-about-label">برنامه‌نویس</span>
					<span>${esc(B.PROGRAMMER)}</span>
				</div>
				<div class="iran-about-row">
					<span class="iran-about-label">وب‌سایت</span>
					<a href="${B.WEBSITE}" target="_blank" rel="noopener" dir="ltr">erpveron.com</a>
				</div>
				<div class="iran-about-row">
					<span class="iran-about-label">پشتیبانی</span>
					<span>برای راهنمایی و پشتیبانی به وب‌سایت مراجعه کنید.</span>
				</div>
			</div>
			<div class="iran-about-legal">
				این نرم‌افزار بر پایه نرم‌افزارهای متن‌باز ساخته شده و تحت مجوز GNU GPL نسخه ۳ منتشر می‌شود.
			</div>
			<div class="iran-about-copy">© ${B.jalali_year()} ${B.NAME} — تمامی حقوق محفوظ است.</div>
		</div>`);
	B.about_dialog = dialog;
	dialog.show();
	return false;
};

(function () {
	// Every «About» in the desk (the user menu, the Help menu) opens this dialog
	frappe.provide("frappe.ui.misc");
	frappe.provide("frappe.ui.toolbar");
	frappe.ui.misc.about = iran_erp.brand.about;
	frappe.ui.toolbar.show_about = iran_erp.brand.about;

	// The user menu's «Frappe Support» (the apps screen's avatar menu builds it with no way to take
	// it out) leads to the product's own website instead
	const Dropdown = frappe.ui.Dropdown;
	if (Dropdown && !Dropdown.iran_branded) {
		const support = __("Frappe Support");
		const rebrand = (options) => {
			if (!Array.isArray(options)) return options;
			return options.map((option) => {
				if (option && Array.isArray(option.options)) return { ...option, options: rebrand(option.options) };
				if (option && (option.label === support || option.label === "Frappe Support")) {
					return {
						...option,
						label: __("ERP-VERON Website"),
						icon: "globe",
						href: undefined,
						onclick: iran_erp.brand.open_website,
					};
				}
				return option;
			});
		};
		frappe.ui.Dropdown = class extends Dropdown {
			constructor(opts) {
				if (opts && Array.isArray(opts.options)) opts = { ...opts, options: rebrand(opts.options) };
				super(opts);
			}
		};
		frappe.ui.Dropdown.iran_branded = true;
	}

	// The side menu advertises other products of the framework's makers on the CRM and Support pages
	const Sidebar = frappe.ui.Sidebar;
	if (Sidebar && !Sidebar.prototype.iran_branded) {
		Sidebar.prototype.get_crm_banner = function () {};
		Sidebar.prototype.get_helpdesk_banner = function () {};
		Sidebar.prototype.iran_branded = true;
	}
})();

$(document).on("app_ready", () => {
	// The Help menu listed links to the upstream English documentation for many pages; the
	// «آموزش» button on every page holds the guide in Persian
	if (frappe.help && frappe.help.help_links) {
		Object.keys(frappe.help.help_links).forEach((key) => delete frappe.help.help_links[key]);
	}
});
