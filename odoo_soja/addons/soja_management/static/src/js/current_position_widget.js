/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class SojaCurrentPositionField extends Component {
    static template = "soja_management.CurrentPositionField";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.notification = useService("notification");
        this.state = useState({ locating: false });
    }

    get sequenceLabel() {
        const sequence = this.props.record.data.sequence || this.props.value;
        return sequence || "";
    }

    async reverseGeocode(latitude, longitude) {
        const params = new URLSearchParams({
            lat: String(Number(latitude).toFixed(6)),
            lon: String(Number(longitude).toFixed(6)),
        });
        const response = await fetch(`/soja/api/reverse-geocode?${params.toString()}`, {
            headers: { Accept: "application/json" },
        });
        if (!response.ok) {
            throw new Error(`Reverse geocode HTTP ${response.status}`);
        }
        const data = await response.json();
        return data.situation || "";
    }

    updateParentZone(osmSituation) {
        if (!osmSituation) {
            return;
        }
        const root = this.props.record.model.root;
        if (root && root.data && "zone" in root.data) {
            root.update({ zone: osmSituation });
        }
    }

    capturePosition() {
        if (!navigator.geolocation) {
            this.notification.add(_t("La géolocalisation n'est pas disponible dans ce navigateur."), {
                type: "danger",
            });
            return;
        }
        this.state.locating = true;
        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const longitude = Number(position.coords.longitude.toFixed(6));
                const latitude = Number(position.coords.latitude.toFixed(6));
                let osmSituation = "";
                try {
                    osmSituation = await this.reverseGeocode(latitude, longitude);
                    this.props.record.update({
                        longitude,
                        latitude,
                        osm_situation: osmSituation,
                    });
                    this.updateParentZone(osmSituation);
                    this.notification.add(_t("Position pour recalcul de surface et situation OpenStreetMap récupérées."), {
                        type: "success",
                    });
                } catch {
                    this.props.record.update({
                        longitude,
                        latitude,
                        osm_situation: "",
                    });
                    this.notification.add(_t("Position récupérée, mais la situation OpenStreetMap est indisponible."), {
                        type: "warning",
                    });
                } finally {
                    this.state.locating = false;
                }
            },
            (error) => {
                this.state.locating = false;
                const message = error.code === error.PERMISSION_DENIED
                    ? _t("Autorisez la localisation dans le navigateur pour récupérer la position actuelle.")
                    : _t("Position pour recalcul de surface indisponible. Utilisez HTTPS ou localhost, puis vérifiez le GPS, le Wi-Fi ou la connexion.");
                this.notification.add(message, { type: "danger" });
            },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
        );
    }
}

registry.category("fields").add("soja_current_position", {
    component: SojaCurrentPositionField,
    supportedTypes: ["integer"],
});
