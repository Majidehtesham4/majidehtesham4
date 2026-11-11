/** The bar of an app shows the app's icon before its name */
import { NavBar } from "@web/webclient/navbar/navbar";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

patch(NavBar.prototype, {
	veronAppIcon(app) {
		const icon = app?.webIcon;
		if (icon && icon.split(",").length === 2) {
			const path = icon.replace(",", "/");
			return path.startsWith("/") ? path : "/" + path;
		}
		const data = app?.webIconData;
		if (data) {
			if (data.startsWith("data:") || data.startsWith("/")) {
				return data;
			}
			return (data.startsWith("P") ? "data:image/svg+xml;base64," : "data:image/png;base64,") + data;
		}
		return "/veron_theme/static/src/img/veron-mark.svg";
	},
});

// The theme is chosen in the user menu (dark or light); the colors of the app menu are the theme's
const systray = registry.category("systray");
if (systray.contains("AppMenuTheme")) {
	systray.remove("AppMenuTheme");
}
