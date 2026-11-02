/** @odoo-module **/
/* Control room: the Proxmox card.

   The component renders a snapshot computed by the server from the local
   Proxmox mirrors. It never calls Proxmox: opening a dashboard must not load
   an hypervisor. The age of the snapshot is displayed, because a stale figure
   presented as live is worse than no figure. */
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {Component, onWillStart, onWillUnmount, useProps, useState} from "@odoo/owl";
import {standardActionServiceProps} from "@web/webclient/actions/action_plugin";

const REFRESH_MS = 60000;

export class ControlRoomDashboard extends Component {
    static template = "hermes_control_room.Dashboard";
    props = useProps({...standardActionServiceProps});

    setup() {
        this.orm = useService("orm");
        this.state = useState({data: null, k8s: null, loading: true, error: null});
        this.timer = null;
        onWillStart(() => this.reload());
        onWillUnmount(() => this.stopTimer());
    }

    stopTimer() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    async reload() {
        this.state.loading = true;
        try {
            const [proxmox, kubernetes] = await Promise.all([
                this.orm.call("control.room", "proxmox_snapshot", []),
                this.orm.call("control.room", "kubernetes_snapshot", []),
            ]);
            this.state.data = proxmox;
            this.state.k8s = kubernetes;
            this.state.error = null;
            if (!this.timer) {
                this.timer = setInterval(() => this.reload(), REFRESH_MS);
            }
        } catch (error) {
            this.state.error = error.message || String(error);
            this.stopTimer();
        } finally {
            this.state.loading = false;
        }
    }

    get totals() {
        return (this.state.data && this.state.data.totals) || {};
    }

    get nodes() {
        return (this.state.data && this.state.data.nodes) || [];
    }

    get alerts() {
        return (this.state.data && this.state.data.alerts) || [];
    }

    get clusters() {
        return (this.state.k8s && this.state.k8s.clusters) || [];
    }

    get k8sTotals() {
        return (this.state.k8s && this.state.k8s.totals) || {};
    }

    get memoryPercent() {
        const totals = this.totals;
        return totals.memory_max ? Math.round((totals.memory_used / totals.memory_max) * 100) : 0;
    }
}

registry.category("actions").add("hermes_control_room.dashboard", ControlRoomDashboard);
