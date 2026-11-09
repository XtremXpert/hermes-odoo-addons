/** @odoo-module **/
/* Runners : l'état des runners ARC, lu depuis le cluster.

   Le composant n'appelle jamais GitHub et n'appelle jamais le cluster
   directement : le serveur compose l'instantané, ici on l'affiche. L'heure de
   l'instantané est visible, parce qu'un tableau de bord qui masque l'âge de sa
   donnée ment par omission. */
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {Component, onWillStart, onWillUnmount, useProps, useState} from "@odoo/owl";
import {standardActionServiceProps} from "@web/webclient/actions/action_plugin";

const REFRESH_MS = 30000;

export class ArcRunnersDashboard extends Component {
    static template = "hermes_runners.Dashboard";
    props = useProps({...standardActionServiceProps});

    setup() {
        this.orm = useService("orm");
        this.state = useState({data: null, loading: true, error: null});
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

    startTimer() {
        this.stopTimer();
        this.timer = setInterval(() => this.reload(), REFRESH_MS);
    }

    async reload() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.data = await this.orm.call("arc.runners", "runners_snapshot", []);
        } catch (error) {
            this.state.error = error.message || String(error);
        } finally {
            this.state.loading = false;
            this.startTimer();
        }
    }

    phaseClass(phase) {
        if (phase === "Running") {
            return "o_arc_ok";
        }
        if (phase === "Pending") {
            return "o_arc_warn";
        }
        return "o_arc_bad";
    }
}

registry.category("actions").add("hermes_runners.dashboard", ArcRunnersDashboard);
