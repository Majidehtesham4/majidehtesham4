/** The barcode screen: home, transfers, a transfer, a stock count, a product. Each scan goes to the
 * server (veron.barcode), which checks and records it; the screen shows what comes back. */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { scanBarcode } from "@web/core/barcode/barcode_dialog";
import { isBarcodeScannerSupported } from "@web/core/barcode/barcode_video_scanner";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { formatFloat } from "@web/core/utils/numbers";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";

const MODEL = "veron.barcode";

export class BarcodeApp extends Component {
    static template = "veron_barcode.BarcodeApp";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.input = useRef("input");
        this.state = useState({ screen: "home", home: null, list: [], kind: null, data: null, typed: "" });
        this.camera = isBarcodeScannerSupported();
        this.kindTitles = {
            incoming: _t("Receipts"),
            outgoing: _t("Deliveries"),
            internal: _t("Internal Transfers"),
        };
        useBus(useService("barcode").bus, "barcode_scanned", ({ detail }) => this.onScan(detail.barcode));
        onWillStart(() => this.goHome());
    }

    async call(method, ...args) {
        return this.orm.call(MODEL, method, args);
    }

    show(screen, data) {
        Object.assign(this.state, { screen, data });
        if (data?.message) {
            this.notification.add(data.message, { type: data.level === "danger" ? "danger" : data.level || "info" });
            if (data.level === "danger") {
                this.beep();
            }
        }
    }

    beep() {
        try {
            new Audio("/barcodes/static/src/audio/error.mp3").play();
        } catch {
            // No sound on this device
        }
    }

    // --- screens

    async goHome() {
        this.state.home = await this.call("home");
        this.state.screen = "home";
    }

    async openList(kind) {
        this.state.kind = kind;
        this.state.list = await this.call("pickings", kind);
        this.state.screen = "list";
    }

    async openPicking(id) {
        this.show("picking", await this.call("picking", id));
    }

    async openCount(locationId) {
        this.show("count", await this.call("count", locationId));
    }

    async openProduct(barcode) {
        const data = await this.call("product", barcode);
        if (!data.found) {
            this.notification.add(data.message, { type: "danger" });
            this.beep();
            return;
        }
        Object.assign(this.state, { screen: "product", data });
    }

    // --- scanning

    async onScan(barcode) {
        barcode = (barcode || "").trim();
        if (!barcode) {
            return;
        }
        const { screen, data } = this.state;
        if (screen === "picking" && !data.done) {
            this.show("picking", await this.call("picking_scan", data.id, barcode));
        } else if (screen === "count") {
            this.show("count", await this.call("count_scan", data.id, barcode));
        } else {
            const found = await this.call("scan", barcode);
            if (found.type === "picking") {
                await this.openPicking(found.id);
            } else if (found.type === "count") {
                await this.openCount(found.id);
            } else if (found.type === "product") {
                await this.openProduct(found.barcode);
            } else {
                this.notification.add(found.message, { type: "danger" });
                this.beep();
            }
        }
    }

    async onCamera() {
        let barcode;
        try {
            barcode = await scanBarcode(this.env);
        } catch {
            return; // closed, or no camera allowed
        }
        await this.onScan(barcode);
    }

    async onTyped(ev) {
        if (ev.key === "Enter") {
            const barcode = ev.target.value;
            this.state.typed = "";
            ev.target.value = "";
            await this.onScan(barcode);
        }
    }

    // --- a transfer

    async setMove(line, quantity) {
        this.show("picking", await this.call("picking_set", line.move_id, Math.max(quantity, 0)));
    }

    async validate() {
        const result = await this.call("picking_validate", this.state.data.id);
        if (result.action) {
            // Odoo asks first (a backorder for what is missing...): its own dialog, then the screen again
            await this.action.doAction(result.action, { onClose: () => this.openPicking(this.state.data.id) });
            return;
        }
        this.show("picking", result.data);
    }

    // --- a stock count

    async setQuant(line, quantity) {
        this.show("count", await this.call("count_set", line.quant_id, Math.max(quantity, 0)));
    }

    async applyCount() {
        this.show("count", await this.call("count_apply", this.state.data.id));
    }

    // --- formats

    qty(value) {
        return formatFloat(value, { digits: [16, 3] }).replace(/\.?0+$/, "") || "0";
    }

    date(value) {
        return value ? formatDateTime(deserializeDateTime(value.replace("T", " ")), { showSeconds: false }) : "";
    }
}

registry.category("actions").add("veron_barcode.app", BarcodeApp);
