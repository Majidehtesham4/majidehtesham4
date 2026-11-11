/** What the agent's page and the chat window share: the conversation, text, a voice message whose text the
 * person checks before it is sent, a photo from the camera, a PDF or an Excel file, the options of the
 * conversation, and answers read aloud. The person chooses the built-in assistant (no AI) or the AI when the
 * agent has one. */
import { Component, markup, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { deserializeDateTime, formatDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

const { DateTime } = luxon;

export class AgentChat extends Component {
    static template = "";
    static props = ["*"];
    static components = { Dropdown, DropdownItem };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.list = useRef("list");
        this.fileInput = useRef("fileInput");
        this.photoInput = useRef("photoInput");
        this.textarea = useRef("textarea");
        this.state = useState({
            agents: [], agentId: false, conversationId: false, messages: [], text: "",
            files: [], busy: false, recording: false, uploading: false, ai: false, engine: "internal", prompts: [],
            options: { web_search: true, show_steps: false, think_longer: false }, previousId: false,
            agentName: "", agentImage: "", agentDescription: "", webSearch: false, filter: "",
        });
        this.recorder = null;
        this.userAvatar = `/web/image/res.users/${user.userId}/avatar_128`;
        this.userName = user.name;
        onWillStart(() => this.start());
        onMounted(() => this.scroll());
    }

    async start() {}

    /** After an answer: the page refreshes its list of conversations */
    afterSend() {}

    get agent() {
        return this.state.agents.find((a) => a.id === this.state.agentId);
    }

    /** The messages shown: all, or those that hold the words searched for */
    get shownMessages() {
        const words = this.state.filter.trim().toLowerCase();
        if (!words) {
            return this.state.messages;
        }
        return this.state.messages.filter((m) => `${m.body} ${m.body_html}`.toLowerCase().includes(words));
    }

    get placeholder() {
        return this.state.agentName ? _t("Message %s...", this.state.agentName) : _t("Write your request...");
    }

    html(value) {
        return markup(value || "");
    }

    /** The time of a message or a conversation: the hour today, else the date */
    when(value) {
        if (!value) {
            return "";
        }
        const date = deserializeDateTime(value.split(".")[0]);
        return date.hasSame(DateTime.local(), "day") ? date.toFormat("HH:mm") : formatDate(date);
    }

    /** The agent the conversation is with, as the page and the window show it */
    useAgent(info) {
        Object.assign(this.state, {
            agentName: info.name || "", agentImage: info.image || "", agentDescription: info.description || "",
        });
    }

    /** A conversation brought in from the server */
    useConversation(result) {
        Object.assign(this.state, {
            conversationId: result.conversation_id, messages: result.messages || [], files: [],
            options: result.options || this.state.options,
        });
        if ("previous_id" in result) {
            this.state.previousId = result.previous_id;
        }
        setTimeout(() => this.scroll());
    }

    /** A new chat with the agent; the latest one with messages may be resumed */
    async newChat(agentId = this.state.agentId) {
        const result = await this.orm.call("veron.ai.conversation", "veron_chat_start", [agentId]);
        this.state.agentId = result.agent_id;
        this.useConversation(result);
        this.state.text = "";
    }

    async openConversation(conversationId) {
        const result = await this.orm.call("veron.ai.conversation", "veron_chat_load", [conversationId]);
        this.state.agentId = result.agent_id;
        this.state.previousId = false;
        this.useConversation(result);
    }

    async setOption(key, value) {
        this.state.options[key] = value;
        if (this.state.conversationId) {
            this.state.options = await this.orm.call("veron.ai.conversation", "veron_chat_options",
                [this.state.conversationId, { [key]: value }]);
        }
    }

    pick(kind) {
        (kind === "photo" ? this.photoInput : this.fileInput).el?.click();
    }

    stepIcon(step) {
        return {
            allowed: "fa-check text-success", reused: "fa-check text-success", approval: "fa-hourglass-half text-warning",
            suggestion: "fa-lightbulb-o text-info", denied: "fa-ban text-danger", failed: "fa-times text-danger",
            needs_info: "fa-question-circle text-warning",
        }[step.decision] || "fa-circle-o";
    }

    /** The box to write in grows with the text, up to a few lines */
    onInput(ev) {
        const el = ev.target;
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
    }

    fileIcon(kind) {
        return { image: "fa-picture-o", pdf: "fa-file-pdf-o", audio: "fa-microphone", sheet: "fa-file-excel-o" }[kind] || "fa-file-o";
    }

    /** The engine the person chose last for this agent, remembered in the browser */
    useEngine(agentId, ai, engine) {
        let chosen = engine === "ai" && ai ? "ai" : "internal";
        try {
            chosen = localStorage.getItem(`veron_ai_engine_${agentId}`) || chosen;
        } catch {
            // the browser keeps nothing; the default stays
        }
        this.state.ai = ai;
        this.state.engine = ai ? chosen : "internal";
    }

    setEngine(engine) {
        this.state.engine = engine;
        try {
            localStorage.setItem(`veron_ai_engine_${this.state.agentId}`, engine);
        } catch {
            // the choice holds for this page only
        }
    }

    /** The page the person is on, so that "this invoice" or "this customer" is understood */
    page() {
        return false;
    }

    scroll() {
        const el = this.list.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }


    /** A photo the server may not open (HEIC, AVIF... often named .jpg) is sent as a JPEG when the browser can
     * draw it; a JPEG, a PNG, a PDF and other files are sent as they are */
    async asJpeg(file) {
        const head = new Uint8Array(await file.slice(0, 4).arrayBuffer());
        const plain = (head[0] === 0xff && head[1] === 0xd8) || (head[0] === 0x89 && head[1] === 0x50) ||
            (head[0] === 0x25 && head[1] === 0x50);
        const looksImage = file.type.startsWith("image/") || /\.(jpe?g|png|heic|heif|avif|webp)$/i.test(file.name);
        if (plain || !looksImage || !window.createImageBitmap) {
            return file;
        }
        try {
            const bitmap = await createImageBitmap(file);
            const canvas = document.createElement("canvas");
            canvas.width = bitmap.width;
            canvas.height = bitmap.height;
            canvas.getContext("2d").drawImage(bitmap, 0, 0);
            const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
            if (!blob) {
                return file;
            }
            const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
            return new File([blob], name, { type: "image/jpeg" });
        } catch {
            // The browser cannot draw it either: the server converts it, or says why it cannot
            return file;
        }
    }

    async upload(file, purpose = "other") {
        if (purpose !== "voice") {
            file = await this.asJpeg(file);
        }
        const form = new FormData();
        form.append("agent_id", this.state.agentId);
        form.append("purpose", purpose);
        form.append("engine", this.state.ai ? this.state.engine : "internal");
        form.append("file", file);
        form.append("csrf_token", odoo.csrf_token);
        this.state.uploading = true;
        try {
            const response = await fetch("/veron_ai/upload", { method: "POST", body: form });
            const data = await response.json();
            if (data.error && !data.id) {
                this.notification.add(data.error, { type: "danger" });
                return;
            }
            if (data.error) {
                this.notification.add(data.error, { type: "warning" });
            }
            this.state.files.push({ ...data, transcriptEdit: data.transcript || "" });
            if (data.kind === "audio" && data.transcript) {
                this.notification.add(_t("Check the text of your voice message, then send."), { type: "info" });
            }
        } finally {
            this.state.uploading = false;
        }
    }

    onPickFile(ev, purpose) {
        for (const file of ev.target.files) {
            this.upload(file, purpose);
        }
        ev.target.value = "";
    }

    removeFile(file) {
        this.state.files = this.state.files.filter((f) => f !== file);
    }

    async toggleRecording() {
        if (this.state.recording) {
            this.recorder.stop();
            return;
        }
        if (!navigator.mediaDevices?.getUserMedia) {
            this.notification.add(_t("This browser cannot record; open the page over HTTPS."), { type: "warning" });
            return;
        }
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const chunks = [];
        this.recorder = new MediaRecorder(stream);
        this.recorder.ondataavailable = (ev) => chunks.push(ev.data);
        this.recorder.onstop = async () => {
            stream.getTracks().forEach((t) => t.stop());
            this.state.recording = false;
            const type = this.recorder.mimeType || "audio/webm";
            const blob = new Blob(chunks, { type });
            await this.upload(new File([blob], "voice.webm", { type }), "voice");
        };
        this.recorder.start();
        this.state.recording = true;
    }

    /** A button the assistant offered: the meaning it was unsure of, or one of the records it found */
    choose(option) {
        if (option.res_model && option.ids) {
            // The records of an answer, as a list in the program
            this.action.doAction({ type: "ir.actions.act_window", res_model: option.res_model, name: option.label,
                domain: [["id", "in", option.ids]], views: [[false, "list"], [false, "form"]] });
            return;
        }
        if (option.res_model) {
            this.action.doAction({ type: "ir.actions.act_window", res_model: option.res_model, res_id: option.res_id, views: [[false, "form"]] });
            return;
        }
        this.send(option.code ? `#intent:${option.code}` : String(option.choice), option.label);
    }

    async decide(approval, approve) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const messages = await this.orm.call("veron.ai.conversation", "veron_chat_decide", [
                this.state.conversationId, approval.id, approve,
            ]);
            for (const message of this.state.messages) {
                message.pending = (message.pending || []).filter((a) => a.id !== approval.id);
            }
            this.state.messages.push(...messages);
        } finally {
            this.state.busy = false;
            setTimeout(() => this.scroll());
        }
    }

    /** The ready requests of the page (default prompts); one is sent as if typed */
    async loadPrompts() {
        const page = this.page() || {};
        this.state.prompts = await this.orm.call("veron.ai.prompt.rule", "veron_prompts", [page.model || false,
            this.state.agentId || false]);
    }

    usePrompt(prompt) {
        this.state.text = prompt.prompt;
        this.send();
    }

    async send(command = false, shown = false) {
        const text = command || this.state.text.trim();
        if ((!text && !this.state.files.length) || this.state.busy) {
            return;
        }
        // A voice message nothing turned into text goes with what was typed in the message box
        const audioWithoutText = this.state.files.find((f) => f.kind === "audio" && !f.transcriptEdit.trim());
        if (audioWithoutText && !text) {
            this.notification.add(_t("The voice message has no text; type it, or remove the voice message."), { type: "warning" });
            return;
        }
        const transcripts = {};
        for (const file of this.state.files) {
            if (file.kind === "audio") {
                transcripts[file.id] = file.transcriptEdit.trim() || text;
            }
        }
        this.state.busy = true;
        const pendingText = text || this.state.files.filter((f) => f.kind === "audio").map((f) => f.transcriptEdit).join("\n");
        this.state.messages.push({ id: "tmp", role: "user", body: shown || pendingText, sources: this.state.files.map((f) => ({ name: f.name, kind: f.kind })), pending: [] });
        setTimeout(() => this.scroll());
        try {
            const messages = await this.orm.call("veron.ai.conversation", "veron_chat_send", [
                this.state.conversationId, pendingText, this.state.files.map((f) => f.id), transcripts,
                command || !this.state.ai ? "internal" : this.state.engine, this.page(),
            ]);
            this.state.messages = this.state.messages.filter((m) => m.id !== "tmp").concat(messages);
            // «بازش کن»: what the answer says to open is opened at once
            const last = messages[messages.length - 1];
            const auto = last && (last.options || []).find((option) => option.auto);
            if (auto) {
                this.choose(auto);
            }
            if (!command) {
                this.state.text = "";
                if (this.textarea.el) {
                    this.textarea.el.style.height = "";
                }
            }
            this.state.files = [];
            this.afterSend();
        } catch (error) {
            this.state.messages = this.state.messages.filter((m) => m.id !== "tmp");
            throw error;
        } finally {
            this.state.busy = false;
            setTimeout(() => this.scroll());
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    async speak(message) {
        const result = await rpc("/veron_ai/speak", { message_id: message.id });
        if (result.audio) {
            new Audio(`data:${result.mimetype};base64,${result.audio}`).play();
            return;
        }
        if (result.error) {
            this.notification.add(result.error, { type: "warning" });
            return;
        }
        const div = document.createElement("div");
        div.innerHTML = message.body_html;
        const utterance = new SpeechSynthesisUtterance(div.innerText);
        utterance.lang = "fa-IR";
        window.speechSynthesis.speak(utterance);
    }

    openRun(run) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "veron.ai.run", res_id: run.id, views: [[false, "form"]] });
    }

    async openGuide(code) {
        const action = await this.orm.call("veron.ai.guide", "action_by_code", [code]);
        this.action.doAction(action);
    }

    openApproval(approval) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "veron.ai.approval", res_id: approval.id, views: [[false, "form"]] });
    }
}

