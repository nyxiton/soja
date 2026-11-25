import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    soja_cooperative_id = fields.Many2one(
        "res.partner",
        string="Coopérative SOJA",
        domain=[("is_company", "=", True), ("is_soja_cooperative", "=", True)],
        help="Coopérative utilisée automatiquement pour les saisies de cet utilisateur.",
    )
    soja_factory_id = fields.Many2one(
        "res.partner",
        string="Usine SOJA",
        domain=[("is_company", "=", True), ("is_soja_factory", "=", True)],
        help="Usine utilisée automatiquement pour les saisies de cet utilisateur.",
    )
    soja_bank_id = fields.Many2one(
        "res.partner",
        string="Banque SOJA",
        domain=[("is_company", "=", True), ("is_soja_bank", "=", True)],
        help="Banque utilisée automatiquement pour les saisies de cet utilisateur.",
    )


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_soja_producer = fields.Boolean(string="Producteur SOJA", index=True, tracking=True)
    is_soja_cooperative = fields.Boolean(string="Cooperative SOJA", index=True)
    is_soja_factory = fields.Boolean(string="Usine SOJA", index=True)
    is_soja_bank = fields.Boolean(string="Banque SOJA", index=True)
    soja_external_id = fields.Char(string="Identifiant SOJA", copy=False, default="SOJA")
    soja_user_id = fields.Many2one("res.users", string="Utilisateur portail SOJA", index=True)
    soja_zone = fields.Char(string="Zone")
    soja_coop = fields.Char(string="Cooperative historique")
    soja_cooperative_id = fields.Many2one(
        "res.partner",
        string="Cooperative",
        domain=[("is_company", "=", True), ("is_soja_cooperative", "=", True)],
        index=True,
    )
    soja_soy = fields.Selection(
        [("conventional", "Conventionnel"), ("organic", "Bio")],
        string="Type de soja",
        default="conventional",
    )
    soja_tenure = fields.Selection(
        [
            ("owner", "Propriete"),
            ("rental", "Location"),
            ("concession", "Concession"),
            ("other", "Autre"),
        ],
        string="Titre de propriete / location",
        default="owner",
    )
    soja_fertilizer = fields.Selection(
        [
            ("seed", "Semence"),
            ("k2so4", "K2SO4"),
            ("kcl", "KCL"),
            ("inoculum", "Inoculum"),
            ("none", "Aucun"),
        ],
        string="Types d'engrais utilises",
    )
    soja_pesticide = fields.Selection(
        [
            ("total", "Herbicide total"),
            ("selective", "Herbicide selectif"),
            ("none", "Aucun"),
        ],
        string="Herbicides",
    )
    soja_department = fields.Char(string="Departement")
    soja_coop_president = fields.Char(string="President cooperative")
    soja_coop_president_phone = fields.Char(string="Contact president")
    soja_credit_ongoing = fields.Selection([("yes", "Oui"), ("no", "Non")], string="Credit en cours")
    soja_sex = fields.Selection([("f", "F"), ("m", "M")], string="Sexe")
    soja_age = fields.Integer(string="Age")
    soja_identity_photo = fields.Image(string="Photo identite", max_width=1024, max_height=1024)
    soja_exploitation_ids = fields.One2many("soja.exploitation", "producer_id", string="Exploitations SOJA")
    soja_point_ids = fields.One2many("soja.plot.point", "partner_id", string="Points GPS")
    soja_area_ha = fields.Float(string="Surface (ha)", digits=(10, 2))
    soja_centroid_lon = fields.Float(string="Centroide longitude", digits=(10, 6))
    soja_centroid_lat = fields.Float(string="Centroide latitude", digits=(10, 6))
    soja_exploitation_count = fields.Integer(string="Exploitations", compute="_compute_soja_exploitation_stats")
    soja_total_area_ha = fields.Float(string="Surface totale (ha)", digits=(10, 2), compute="_compute_soja_exploitation_stats")
    soja_exploitation_api_identifiers = fields.Char(
        string="UUID des exploitations",
        compute="_compute_soja_exploitation_api_identifiers",
    )
    soja_harvest_ids = fields.One2many("soja.harvest", "partner_id", string="Semences et recoltes")
    soja_latest_harvest_id = fields.Many2one("soja.harvest", string="Derniere campagne", compute="_compute_soja_latest_harvest")
    soja_latest_campaign = fields.Char(string="Campagne", compute="_compute_soja_latest_harvest")
    soja_latest_forecast_t = fields.Float(string="Qte prevue (t)", compute="_compute_soja_latest_harvest")
    soja_latest_actual_t = fields.Float(string="Qte effective (t)", compute="_compute_soja_latest_harvest")
    soja_latest_share_status = fields.Selection(
        [
            ("private", "Prive"),
            ("partners", "Partenaires"),
            ("cooperative", "Cooperative"),
            ("factory", "Usine"),
            ("bank", "Banque"),
        ],
        string="Partage",
        compute="_compute_soja_latest_harvest",
    )
    soja_attachment_count = fields.Integer(string="Documents SOJA", compute="_compute_soja_attachment_count")
    soja_task_count = fields.Integer(string="Activites projet SOJA", compute="_compute_soja_task_count")

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("is_soja_producer") and values.get("soja_coop") and not values.get("soja_cooperative_id"):
                cooperative = self._get_or_create_soja_company(values["soja_coop"], "cooperative")
                values["soja_cooperative_id"] = cooperative.id
        return super().create(vals_list)

    def write(self, values):
        if values.get("soja_coop") and "soja_cooperative_id" not in values:
            cooperative = self._get_or_create_soja_company(values["soja_coop"], "cooperative")
            values = dict(values, soja_cooperative_id=cooperative.id)
        return super().write(values)

    @api.onchange("soja_cooperative_id")
    def _onchange_soja_cooperative_id(self):
        for partner in self:
            if partner.soja_cooperative_id:
                partner.soja_coop = partner.soja_cooperative_id.name

    @api.model
    def _get_or_create_soja_company(self, name, role):
        name = (name or "").strip()
        if not name:
            return self.env["res.partner"]
        role_field = {
            "cooperative": "is_soja_cooperative",
            "factory": "is_soja_factory",
            "bank": "is_soja_bank",
        }.get(role)
        if not role_field:
            return self.env["res.partner"]
        Partner = self.env["res.partner"].sudo()
        partner = Partner.search([("name", "=", name), ("is_company", "=", True)], limit=1)
        if partner:
            if not partner[role_field]:
                partner.write({role_field: True})
            return partner
        return Partner.create({"name": name, "is_company": True, "company_type": "company", role_field: True})

    @api.depends("soja_harvest_ids", "soja_harvest_ids.create_date", "soja_harvest_ids.campaign", "soja_harvest_ids.forecast_t", "soja_harvest_ids.actual_t", "soja_harvest_ids.share_status")
    def _compute_soja_latest_harvest(self):
        for partner in self:
            harvest = partner.soja_harvest_ids[:1]
            partner.soja_latest_harvest_id = harvest
            partner.soja_latest_campaign = harvest.campaign
            partner.soja_latest_forecast_t = harvest.forecast_t
            partner.soja_latest_actual_t = harvest.actual_t
            partner.soja_latest_share_status = harvest.share_status

    def _compute_soja_attachment_count(self):
        Attachment = self.env["ir.attachment"].sudo()
        for partner in self:
            partner.soja_attachment_count = Attachment.search_count([
                ("res_model", "=", "res.partner"),
                ("res_id", "=", partner.id),
            ])

    def _compute_soja_task_count(self):
        Task = self.env["project.task"].sudo()
        for partner in self:
            partner.soja_task_count = Task.search_count([("soja_partner_id", "=", partner.id)])

    @api.depends("soja_exploitation_ids", "soja_exploitation_ids.soja_area_ha")
    def _compute_soja_exploitation_stats(self):
        for partner in self:
            exploitations = partner.soja_exploitation_ids
            partner.soja_exploitation_count = len(exploitations)
            partner.soja_total_area_ha = sum(exploitations.mapped("soja_area_ha"))

    @api.depends("soja_exploitation_ids.api_identifier")
    def _compute_soja_exploitation_api_identifiers(self):
        for partner in self:
            partner.soja_exploitation_api_identifiers = ", ".join(
                exploitation.api_identifier
                for exploitation in partner.soja_exploitation_ids
                if exploitation.api_identifier
            )

    def action_open_soja_exploitations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Exploitations",
            "res_model": "soja.exploitation",
            "view_mode": "tree,form",
            "domain": [("producer_id", "=", self.id)],
            "context": {
                "default_producer_id": self.id,
            },
        }

    def action_open_soja_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Documents producteur",
            "res_model": "ir.attachment",
            "view_mode": "kanban,tree,form",
            "domain": [("res_model", "=", "res.partner"), ("res_id", "=", self.id)],
            "context": {"default_res_model": "res.partner", "default_res_id": self.id},
        }

    def action_open_soja_tasks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Activites terrain",
            "res_model": "project.task",
            "view_mode": "kanban,tree,form",
            "domain": [("soja_partner_id", "=", self.id)],
            "context": {"default_soja_partner_id": self.id, "default_partner_id": self.id},
        }

class SojaExploitation(models.Model):
    _name = "soja.exploitation"
    _description = "Exploitation SOJA"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _last_osm_request_at = 0.0
    _sql_constraints = [
        ("api_identifier_unique", "unique(api_identifier)", "L'identifiant API de l'exploitation doit être unique."),
    ]

    name = fields.Char(string="Nom", required=True, tracking=True)
    active = fields.Boolean(default=True)
    producer_id = fields.Many2one(
        "res.partner",
        string="Producteur SOJA",
        required=True,
        domain=[("is_soja_producer", "=", True)],
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    api_identifier = fields.Char(string="Identifiant API", copy=False, index=True, default=lambda self: str(uuid.uuid4()))
    zone = fields.Char(string="Zone géographique")
    area_ha = fields.Float(string="Surface (ha)", digits=(10, 2), compute="_compute_plot_geometry", store=True, readonly=True)
    centroid_lon = fields.Float(string="Centroide longitude", digits=(10, 6), compute="_compute_plot_geometry", store=True, readonly=True)
    centroid_lat = fields.Float(string="Centroide latitude", digits=(10, 6), compute="_compute_plot_geometry", store=True, readonly=True)
    point_ids = fields.One2many("soja.plot.point", "exploitation_id", string="Points GPS")
    harvest_ids = fields.One2many("soja.harvest", "exploitation_id", string="Campagnes SOJA")
    harvest_product_ids = fields.One2many("product.product", "soja_exploitation_id", string="Saisons de récolte")
    storage_info_ids = fields.One2many("soja.storage.info", "exploitation_id", string="Informations de stockage")
    storage_quant_ids = fields.One2many("stock.quant", "soja_exploitation_id", string="Stocks Inventaire SOJA", domain=[("soja_cooperative_partner_id", "!=", False)])
    treatment_info_ids = fields.One2many("mrp.production", "soja_exploitation_id", string="Traitements usine", domain=[("factory_partner_id", "!=", False)])
    bank_info_ids = fields.One2many("crm.lead", "soja_exploitation_id", string="Dossiers bancaires", domain=[("soja_bank_partner_id", "!=", False)])
    project_id = fields.Many2one("project.project", string="Projet d'exploitation", copy=False, ondelete="set null")
    harvest_count = fields.Integer(string="Campagnes", compute="_compute_harvest_count")

    # Compatibility aliases for code/views that still expect the old field names.
    soja_owner_id = fields.Many2one(related="producer_id", string="Producteur SOJA", readonly=False)
    soja_api_identifier = fields.Char(related="api_identifier", string="Identifiant API", readonly=False)
    soja_zone = fields.Char(related="zone", string="Zone", readonly=False)
    soja_area_ha = fields.Float(related="area_ha", string="Surface (ha)", readonly=False)
    soja_centroid_lon = fields.Float(related="centroid_lon", string="Centroide longitude", readonly=False)
    soja_centroid_lat = fields.Float(related="centroid_lat", string="Centroide latitude", readonly=False)
    soja_point_ids = fields.One2many(related="point_ids", string="Points GPS", readonly=False)
    soja_harvest_ids = fields.One2many(related="harvest_ids", string="Campagnes SOJA", readonly=False)
    soja_storage_info_ids = fields.One2many(related="storage_info_ids", string="Informations de stockage", readonly=False)
    soja_stock_quant_ids = fields.One2many(related="storage_quant_ids", string="Stocks Inventaire SOJA", readonly=False)
    soja_treatment_info_ids = fields.One2many(related="treatment_info_ids", string="Traitements usine", readonly=False)
    soja_bank_info_ids = fields.One2many(related="bank_info_ids", string="Dossiers bancaires", readonly=False)
    soja_harvest_count = fields.Integer(related="harvest_count", string="Campagnes")

    @api.depends("harvest_ids")
    def _compute_harvest_count(self):
        for exploitation in self:
            exploitation.harvest_count = len(exploitation.harvest_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values.setdefault("api_identifier", str(uuid.uuid4()))
        exploitations = super().create(vals_list)
        exploitations._ensure_project()
        return exploitations

    def write(self, values):
        result = super().write(values)
        if {"name", "producer_id", "zone"}.intersection(values):
            self._sync_project_values()
        return result

    def _project_values(self):
        self.ensure_one()
        name_parts = [self.name or "Exploitation SOJA"]
        if self.producer_id:
            name_parts.append(self.producer_id.name)
        if self.zone:
            name_parts.append(self.zone)
        return {
            "name": " - ".join(name_parts),
            "partner_id": self.producer_id.id,
        }

    def _ensure_project(self):
        Project = self.env["project.project"].sudo()
        for exploitation in self:
            if exploitation.project_id:
                continue
            exploitation.project_id = Project.create(exploitation._project_values()).id
        return self.mapped("project_id")

    def _sync_project_values(self):
        for exploitation in self.filtered("project_id"):
            exploitation.project_id.sudo().write(exploitation._project_values())

    @api.depends("point_ids.sequence", "point_ids.longitude", "point_ids.latitude")
    def _compute_plot_geometry(self):
        for exploitation in self:
            points = exploitation._ordered_plot_points()
            if len(points) < 3:
                exploitation.area_ha = 0.0
                exploitation.centroid_lon = 0.0
                exploitation.centroid_lat = 0.0
                continue
            area_ha, centroid_lon, centroid_lat = exploitation._calculate_plot_geometry(points)
            exploitation.area_ha = area_ha
            exploitation.centroid_lon = centroid_lon
            exploitation.centroid_lat = centroid_lat

    @api.onchange("point_ids", "point_ids.sequence", "point_ids.longitude", "point_ids.latitude", "point_ids.osm_situation")
    def _onchange_point_ids_geometry(self):
        for exploitation in self:
            osm_situations = exploitation.point_ids.filtered("osm_situation").mapped("osm_situation")
            if osm_situations:
                exploitation.zone = osm_situations[-1]
            points = exploitation._ordered_plot_points()
            if len(points) < 3:
                exploitation.area_ha = 0.0
                exploitation.centroid_lon = 0.0
                exploitation.centroid_lat = 0.0
                continue
            area_ha, centroid_lon, centroid_lat = exploitation._calculate_plot_geometry(points)
            exploitation.area_ha = area_ha
            exploitation.centroid_lon = centroid_lon
            exploitation.centroid_lat = centroid_lat

    def _ordered_plot_points(self):
        self.ensure_one()
        return [
            (point.longitude, point.latitude)
            for point in self.point_ids.sorted(lambda point: (point.sequence, point.id or 0))
            if point.longitude is not None and point.latitude is not None
        ]

    @staticmethod
    def _calculate_plot_geometry(points):
        radius_m = 6371000.0
        lat0_rad = math.radians(sum(point[1] for point in points) / len(points))
        cos_lat0 = math.cos(lat0_rad) or 1.0
        xy_points = [
            (
                math.radians(lon) * radius_m * cos_lat0,
                math.radians(lat) * radius_m,
            )
            for lon, lat in points
        ]
        double_area = 0.0
        centroid_x = 0.0
        centroid_y = 0.0
        for index, (x1, y1) in enumerate(xy_points):
            x2, y2 = xy_points[(index + 1) % len(xy_points)]
            cross = x1 * y2 - x2 * y1
            double_area += cross
            centroid_x += (x1 + x2) * cross
            centroid_y += (y1 + y2) * cross
        signed_area = double_area / 2.0
        area_ha = abs(signed_area) / 10000.0
        if abs(double_area) < 1e-9:
            centroid_lon = sum(point[0] for point in points) / len(points)
            centroid_lat = sum(point[1] for point in points) / len(points)
        else:
            centroid_x = centroid_x / (3.0 * double_area)
            centroid_y = centroid_y / (3.0 * double_area)
            centroid_lon = math.degrees(centroid_x / (radius_m * cos_lat0))
            centroid_lat = math.degrees(centroid_y / radius_m)
        return round(area_ha, 2), round(centroid_lon, 6), round(centroid_lat, 6)

    def action_update_osm_zone(self):
        self._update_osm_zone_from_centroid()
        return True

    def _update_osm_zone_from_centroid(self):
        updated = False
        for exploitation in self:
            points = exploitation._ordered_plot_points()
            if not points:
                continue
            if len(points) < 3:
                centroid_lon, centroid_lat = points[0]
            else:
                _area_ha, centroid_lon, centroid_lat = exploitation._calculate_plot_geometry(points)
            situation = exploitation._reverse_geocode_osm(centroid_lat, centroid_lon)
            if situation:
                exploitation.zone = situation
                updated = True
        return updated

    @classmethod
    def _reverse_geocode_osm(cls, latitude, longitude):
        elapsed = time.monotonic() - cls._last_osm_request_at
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        query = urllib.parse.urlencode({
            "format": "jsonv2",
            "lat": "%.6f" % latitude,
            "lon": "%.6f" % longitude,
            "zoom": "14",
            "addressdetails": "1",
            "accept-language": "fr",
        })
        request = urllib.request.Request(
            "https://nominatim.openstreetmap.org/reverse?%s" % query,
            headers={
                "Accept": "application/json",
                "User-Agent": "soja-management-odoo/1.0",
            },
        )
        cls._last_osm_request_at = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError):
            return False
        return payload.get("display_name") or False

    def action_open_soja_harvests(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Semences et recoltes",
            "res_model": "soja.harvest",
            "view_mode": "tree,form,pivot,graph,calendar",
            "domain": [("exploitation_id", "=", self.id)],
            "context": {
                "default_partner_id": self.producer_id.id,
                "default_exploitation_id": self.id,
                "default_cooperative_partner_id": self.producer_id.soja_cooperative_id.id,
            },
        }

    def action_open_project(self):
        self.ensure_one()
        self._ensure_project()
        return {
            "type": "ir.actions.act_window",
            "name": "Projet d'exploitation",
            "res_model": "project.project",
            "res_id": self.project_id.id,
            "view_mode": "form",
        }


class SojaPlotPoint(models.Model):
    _name = "soja.plot.point"
    _description = "Point GPS parcelle SOJA"
    _order = "sequence, id"

    partner_id = fields.Many2one("res.partner", string="Contact producteur", required=True, ondelete="cascade", index=True)
    exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation", ondelete="cascade", index=True)
    exploitation_product_id = fields.Many2one("product.product", string="Ancienne exploitation produit", ondelete="set null", index=True)
    sequence = fields.Integer(string="Point", default=10)
    longitude = fields.Float(string="Longitude", digits=(10, 6), required=True)
    latitude = fields.Float(string="Latitude", digits=(10, 6), required=True)
    osm_situation = fields.Char(string="Situation OSM", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        points = super().create(vals_list)
        points._sync_exploitation_zone_from_osm()
        points.mapped("exploitation_id")._update_osm_zone_from_centroid()
        return points

    def write(self, values):
        result = super().write(values)
        if {"osm_situation", "exploitation_id"}.intersection(values):
            self._sync_exploitation_zone_from_osm()
        if {"longitude", "latitude", "sequence", "exploitation_id", "osm_situation"}.intersection(values):
            self.mapped("exploitation_id")._update_osm_zone_from_centroid()
        return result

    def unlink(self):
        exploitations = self.mapped("exploitation_id")
        result = super().unlink()
        exploitations._update_osm_zone_from_centroid()
        return result

    def _sync_exploitation_zone_from_osm(self):
        for point in self:
            if point.exploitation_id and point.osm_situation:
                point.exploitation_id.zone = point.osm_situation

    @api.onchange("exploitation_id")
    def _onchange_exploitation_id(self):
        for point in self:
            if point.exploitation_id.producer_id:
                point.partner_id = point.exploitation_id.producer_id

    @api.constrains("partner_id", "exploitation_id")
    def _check_exploitation_owner(self):
        for point in self:
            owner = point.exploitation_id.producer_id
            if point.exploitation_id and owner and point.partner_id != owner:
                raise ValidationError("Le point GPS doit appartenir au producteur de l'exploitation.")


class ProductProduct(models.Model):
    _inherit = "product.product"

    is_soja_harvest_product = fields.Boolean(string="Saison de récolte SOJA", index=True)
    soja_exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation SOJA", index=True, ondelete="set null")
    soja_project_id = fields.Many2one(
        "project.project",
        string="Projet d'exploitation",
        related="soja_exploitation_id.project_id",
        store=True,
        readonly=True,
    )
    soja_campaign = fields.Char(string="Campagne SOJA", index=True)
    soja_harvest_ids = fields.One2many("soja.harvest", "product_id", string="Récoltes SOJA")
    soja_harvest_count = fields.Integer(string="Récoltes", compute="_compute_soja_harvest_count")

    # Legacy exploitation-on-product fields kept only for existing databases.
    is_soja_exploitation = fields.Boolean(string="Ancienne exploitation SOJA", index=True)
    soja_owner_id = fields.Many2one(
        "res.partner",
        string="Producteur SOJA",
        domain=[("is_soja_producer", "=", True)],
        index=True,
    )
    soja_zone = fields.Char(string="Zone")
    soja_area_ha = fields.Float(string="Surface (ha)", digits=(10, 2))
    soja_centroid_lon = fields.Float(string="Centroide longitude", digits=(10, 6))
    soja_centroid_lat = fields.Float(string="Centroide latitude", digits=(10, 6))
    soja_point_ids = fields.One2many("soja.plot.point", "exploitation_product_id", string="Points GPS legacy")
    soja_storage_info_ids = fields.One2many("soja.storage.info", "exploitation_product_id", string="Informations de stockage")
    soja_stock_quant_ids = fields.One2many("stock.quant", "product_id", string="Stocks Inventaire SOJA", domain=[("soja_cooperative_partner_id", "!=", False)])
    soja_treatment_info_ids = fields.One2many("mrp.production", "soja_exploitation_product_id", string="Traitements usine", domain=[("factory_partner_id", "!=", False)])
    soja_bank_info_ids = fields.One2many("crm.lead", "soja_exploitation_product_id", string="Dossiers bancaires", domain=[("soja_bank_partner_id", "!=", False)])

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("is_soja_exploitation"):
                values.setdefault("type", "service")
                values.setdefault("sale_ok", False)
                values.setdefault("purchase_ok", False)
        return super().create(vals_list)

    def write(self, values):
        if values.get("is_soja_exploitation"):
            values = dict(values)
            values.setdefault("type", "service")
            values.setdefault("sale_ok", False)
            values.setdefault("purchase_ok", False)
        return super().write(values)

    @api.onchange("is_soja_exploitation")
    def _onchange_is_soja_exploitation(self):
        for product in self:
            if product.is_soja_exploitation:
                product.type = "service"
                product.sale_ok = False
                product.purchase_ok = False

    @api.constrains("is_soja_exploitation", "soja_owner_id")
    def _check_soja_exploitation_owner(self):
        for product in self:
            if product.is_soja_exploitation and not product.soja_owner_id:
                raise ValidationError("Une exploitation SOJA doit être rattachée à un producteur.")

    @api.depends("soja_harvest_ids")
    def _compute_soja_harvest_count(self):
        for product in self:
            product.soja_harvest_count = len(product.soja_harvest_ids)

    def action_open_soja_harvests(self):
        self.ensure_one()
        producer = self.soja_exploitation_id.producer_id or self.soja_owner_id
        return {
            "type": "ir.actions.act_window",
            "name": "Semences et recoltes",
            "res_model": "soja.harvest",
            "view_mode": "tree,form,pivot,graph,calendar",
            "domain": [("product_id", "=", self.id)],
            "context": {
                "default_partner_id": producer.id,
                "default_exploitation_id": self.soja_exploitation_id.id,
                "default_product_id": self.id,
                "default_cooperative_partner_id": producer.soja_cooperative_id.id,
            },
        }


class ProjectTask(models.Model):
    _inherit = "project.task"

    soja_partner_id = fields.Many2one("res.partner", string="Contact producteur SOJA", index=True)
    soja_exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation SOJA", index=True)
    soja_harvest_id = fields.Many2one("soja.harvest", string="Campagne SOJA", index=True)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    base_unit_count = fields.Float(string="Base Unit Count", default=1.0)
