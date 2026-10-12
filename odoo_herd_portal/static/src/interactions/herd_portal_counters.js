import {patch} from "@web/core/utils/patch";
import {PortalHomeCounters} from "@portal/interactions/portal_home_counters";

patch(PortalHomeCounters.prototype, {
    /**
     * The "Odoo instances" card stays visible at 0: it offers to add a
     * database. The server omits the counter for users who have nothing to
     * see nor to request, which keeps the card hidden for them.
     */
    getCountersAlwaysDisplayed() {
        return super
            .getCountersAlwaysDisplayed(...arguments)
            .concat(["herd_instance_count"]);
    },
});
