/** The agent chat: text, a voice message whose text the person checks before it is sent, a photo from the
 * camera or a PDF. Answers can be read aloud. */
import { Component, markup, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

export class AgentChat extends Component {
    static template = "veron_ai_agent.Chat";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.list = useRef("list");
        this.state = useState({
            agents: [], agentId: false, conversationId: false, messages: [], text: "",
            files: [], busy: false, recording: false, uploading: false,
        });
        this.recorder = null;
        onWillStart(async () => {
            this.state.agents = await this.orm.call("veron.ai.conversation", "veron_chat_agents", []);
            const wanted = this.props.action?.params?.agent_id;
            const first = this.state.agents.find((a) => a.id === wanted) || this.state.agents[0];
            if (first) {
                await this.openAgent(first.id);
            }
        });
        onMounted(() => this.scroll());
    }

    get agent() {
        return this.state.agents.find((a) => a.id === this.state.agentId);
    }

    html(value) {
        return markup(value || "");
    }

    scroll() {
        const el = this.list.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }

    async openAgent(agentId) {
        const result = await this.orm.call("veron.ai.conversation", "veron_chat_open", [agentId]);
        Object.assign(this.state, { agentId, conversationId: result.conversation_id, messages: result.messages, files: [] });
        setTimeout(() => this.scroll());
    }

    async upload(file, purpose = "other") {
        const form = new FormData();
        form.append("agent_id", this.state.agentId);
        form.append("purpose", purpose);
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

    async send() {
        const text = this.state.text.trim();
        if ((!text && !this.state.files.length) || this.state.busy) {
            return;
        }
        const audioWithoutText = this.state.files.find((f) => f.kind === "audio" && !f.transcriptEdit.trim());
        if (audioWithoutText) {
            this.notification.add(_t("The voice message has no text; type it, or remove the voice message."), { type: "warning" });
            return;
        }
        const transcripts = {};
        for (const file of this.state.files) {
            if (file.kind === "audio") {
                transcripts[file.id] = file.transcriptEdit;
            }
        }
        this.state.busy = true;
        const pendingText = text || this.state.files.filter((f) => f.kind === "audio").map((f) => f.transcriptEdit).join("\n");
        this.state.messages.push({ id: "tmp", role: "user", body: pendingText, sources: this.state.files.map((f) => ({ name: f.name, kind: f.kind })), pending: [] });
        setTimeout(() => this.scroll());
        try {
            const messages = await this.orm.call("veron.ai.conversation", "veron_chat_send", [
                this.state.conversationId, pendingText, this.state.files.map((f) => f.id), transcripts,
            ]);
            this.state.messages = this.state.messages.filter((m) => m.id !== "tmp").concat(messages);
            this.state.text = "";
            this.state.files = [];
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

    openApproval(approval) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "veron.ai.approval", res_id: approval.id, views: [[false, "form"]] });
    }
}

registry.category("actions").add("veron_ai_agent.chat", AgentChat);
