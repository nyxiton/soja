from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SojaHarvest(models.Model):
    _name = "soja.harvest"
    _description = "Semence et recolte SOJA"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    partner_id = fields.Many2one("res.partner", string="Producteur", required=True, ondelete="cascade", tracking=True, domain=[("is_soja_producer", "=", True)])
    company_id = fields.Many2one("res.company", string="Société", required=True, default=lambda self: self.env.company, index=True)
    exploitation_id = fields.Many2one(
        "soja.exploitation",
        string="Exploitation",
        domain="[('producer_id', '=', partner_id)]",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    exploitation_product_id = fields.Many2one("product.product", string="Ancienne exploitation produit", ondelete="set null", index=True)
    cooperative_partner_id = fields.Many2one(
        "res.partner",
        string="Cooperative",
        domain=[("is_company", "=", True), ("is_soja_cooperative", "=", True)],
        tracking=True,
    )
    factory_partner_id = fields.Many2one(
        "res.partner",
        string="Usine",
        domain=[("is_company", "=", True), ("is_soja_factory", "=", True)],
        tracking=True,
    )
    bank_partner_id = fields.Many2one(
        "res.partner",
        string="Banque",
        domain=[("is_company", "=", True), ("is_soja_bank", "=", True)],
        tracking=True,
    )
    campaign = fields.Char(string="Campagne", default="2025 - 2026", tracking=True)

    seed_date = fields.Date(string="Date semence")
    harvest_forecast_date = fields.Date(string="Date recolte prevue")
    harvest_actual_date = fields.Date(string="Date récolte effective")
    forecast_t = fields.Float(string="Quantité prévisionnelle (t)", digits=(10, 2), compute="_compute_forecast_t", store=True, readonly=False)
    actual_t = fields.Float(string="Quantité effective (t)", digits=(10, 2), compute="_compute_actual_t", store=True, readonly=False)
    yield_tha = fields.Float(string="Rendement prévisionnel (t/ha)", digits=(10, 2))
    actual_yield_tha = fields.Float(string="Rendement effectif (t/ha)", digits=(10, 2))

    share_status = fields.Selection(
        [
            ("private", "Prive"),
            ("partners", "Partenaires"),
            ("cooperative", "Cooperative"),
            ("factory", "Usine"),
            ("bank", "Banque"),
        ],
        string="Partage",
        default="partners",
        required=True,
    )
    service_drone = fields.Boolean(string="Drone")
    service_soil = fields.Boolean(string="Analyse sol")
    service_training = fields.Boolean(string="Coaching")
    service_finance = fields.Boolean(string="Financement")

    stock_type = fields.Selection([("partial", "Partiel"), ("total", "Total")], string="Stockage cooperative")
    stock_qty_t = fields.Float(string="Quantite stockee (t)", digits=(10, 2))
    stock_date = fields.Date(string="Date stockage")
    stock_note = fields.Char(string="Note stockage")

    factory_dehull = fields.Boolean(string="Decorticage")
    factory_grind = fields.Boolean(string="Broyage")
    factory_process_date = fields.Date(string="Date traitement")
    factory_process_note = fields.Char(string="Note traitement")

    bank_borrower_type = fields.Selection(
        [("producer", "Producteur"), ("buyer", "Acheteur"), ("cooperative", "Cooperative"), ("group", "Groupement")],
        string="Type emprunteur",
    )
    bank_borrower_name = fields.Char(string="Nom emprunteur")
    bank_requested_amount = fields.Monetary(string="Montant demande")
    bank_approved_amount = fields.Monetary(string="Montant approuve")
    bank_risk_level = fields.Selection(
        [("low", "Faible"), ("standard", "Standard"), ("watch", "A surveiller"), ("priority", "Prioritaire"), ("medium", "Moyen"), ("high", "Eleve")],
        string="Risque",
    )
    bank_status = fields.Char(string="Statut banque")
    bank_decision_date = fields.Date(string="Date decision")
    bank_note = fields.Char(string="Note banque")
    currency_id = fields.Many2one("res.currency", string="Devise", default=lambda self: self.env.company.currency_id)

    product_id = fields.Many2one("product.product", string="Produit campagne / recolte", domain="[('is_soja_harvest_product', '=', True), ('soja_exploitation_id', '=', exploitation_id)]")
    transformed_product_id = fields.Many2one("product.product", string="Produit transforme", default=lambda self: self._default_transformed_product())
    lot_id = fields.Many2one("stock.lot", string="Lot recolte")
    stock_picking_id = fields.Many2one("stock.picking", string="Prevision stock", copy=False)
    forecast_history_ids = fields.One2many("soja.harvest.forecast.history", "harvest_id", string="Historique des previsions", copy=False)
    storage_info_ids = fields.One2many("soja.storage.info", "harvest_id", string="Informations de stockage")
    stock_quant_ids = fields.One2many("stock.quant", "soja_harvest_id", string="Stocks Inventaire")
    treatment_info_ids = fields.One2many("mrp.production", "soja_harvest_id", string="Traitements usine")
    bank_info_ids = fields.One2many("crm.lead", "soja_harvest_id", string="Dossiers bancaires", domain=[("soja_bank_partner_id", "!=", False)])
    mrp_production_id = fields.Many2one("mrp.production", string="Ordre de fabrication", copy=False)
    purchase_order_id = fields.Many2one("purchase.order", string="Contrat achat producteur", copy=False)
    sale_order_id = fields.Many2one("sale.order", string="Contrat vente", copy=False)
    service_sale_order_id = fields.Many2one("sale.order", string="Devis services", copy=False)
    crm_lead_id = fields.Many2one("crm.lead", string="Opportunite financement", copy=False)
    account_move_id = fields.Many2one("account.move", string="Piece comptable", copy=False)
    project_task_id = fields.Many2one("project.task", string="Tache terrain", copy=False)

    _FORECAST_FIELDS = {
        "exploitation_id",
        "campaign",
        "seed_date",
        "harvest_forecast_date",
        "yield_tha",
        "forecast_t",
    }

    @api.model_create_multi
    def create(self, vals_list):
        harvests = super().create(vals_list)
        harvests._ensure_harvest_products()
        harvests.filtered("exploitation_id").action_record_forecast_history()
        return harvests

    def write(self, vals):
        result = super().write(vals)
        if {"exploitation_id", "campaign"}.intersection(vals):
            self._ensure_harvest_products()
        if self._FORECAST_FIELDS.intersection(vals):
            self.filtered("exploitation_id").action_record_forecast_history()
        return result

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for harvest in self:
            if harvest.partner_id:
                harvest.cooperative_partner_id = harvest.partner_id.soja_cooperative_id
                if harvest.exploitation_id.producer_id != harvest.partner_id:
                    harvest.exploitation_id = harvest.partner_id.soja_exploitation_ids[:1]

    @api.onchange("exploitation_id")
    def _onchange_exploitation_id(self):
        for harvest in self:
            if harvest.exploitation_id.producer_id:
                harvest.partner_id = harvest.exploitation_id.producer_id
                harvest.cooperative_partner_id = harvest.partner_id.soja_cooperative_id

    @api.constrains("partner_id", "exploitation_id")
    def _check_exploitation_owner(self):
        for harvest in self:
            if harvest.exploitation_id.producer_id != harvest.partner_id:
                raise ValidationError("L'exploitation sélectionnée doit appartenir au producteur de la saisie.")

    @api.depends("exploitation_id.area_ha", "yield_tha")
    def _compute_forecast_t(self):
        for harvest in self:
            area = harvest.exploitation_id.area_ha
            if area and harvest.yield_tha:
                harvest.forecast_t = area * harvest.yield_tha

    @api.depends("exploitation_id.area_ha", "actual_yield_tha")
    def _compute_actual_t(self):
        for harvest in self:
            area = harvest.exploitation_id.area_ha
            if area and harvest.actual_yield_tha:
                harvest.actual_t = area * harvest.actual_yield_tha

    @api.model
    def _get_or_create_harvest_product(self, exploitation, campaign):
        exploitation._ensure_project()
        campaign = campaign or "Campagne SOJA"
        code_campaign = "".join(char if char.isalnum() else "-" for char in campaign.upper()).strip("-")
        code = "SOJA-%s-%s" % (exploitation.id, code_campaign or "CAMPAGNE")
        Product = self.env["product.product"].sudo()
        product = Product.search([("default_code", "=", code)], limit=1)
        values = {
            "name": "Soja brut - %s - %s" % (exploitation.display_name, campaign),
            "default_code": code,
            "type": "product",
            "tracking": "lot",
            "purchase_ok": True,
            "sale_ok": True,
            "is_soja_harvest_product": True,
            "soja_exploitation_id": exploitation.id,
            "soja_campaign": campaign,
        }
        if product:
            product.write(values)
            return product
        return Product.create(values)

    def _ensure_harvest_products(self):
        for harvest in self:
            if harvest.exploitation_id:
                harvest.product_id = harvest._get_or_create_harvest_product(harvest.exploitation_id, harvest.campaign).id

    @api.model
    def _default_transformed_product(self):
        return self._get_or_create_product("Soja transforme", "SOJA-TRANS")

    @api.model
    def _get_or_create_product(self, name, code):
        Product = self.env["product.product"].sudo()
        product = Product.search([("default_code", "=", code)], limit=1)
        if product:
            return product
        return Product.create({
            "name": name,
            "default_code": code,
            "type": "product",
            "tracking": "lot",
            "purchase_ok": True,
            "sale_ok": True,
        })

    @api.model
    def _get_or_create_service_product(self, name, code):
        Product = self.env["product.product"].sudo()
        product = Product.search([("default_code", "=", code)], limit=1)
        if product:
            return product
        return Product.create({
            "name": name,
            "default_code": code,
            "type": "service",
            "sale_ok": True,
            "purchase_ok": False,
        })

    def _qty(self):
        self.ensure_one()
        return self.actual_t or self.forecast_t or 1.0

    def _stock_locations(self):
        return (
            self.env.ref("stock.stock_location_suppliers"),
            self.env.ref("stock.stock_location_stock"),
            self.env.ref("stock.stock_location_customers"),
        )

    def action_create_stock_receipt(self):
        for harvest in self:
            qty = harvest.forecast_t or harvest._qty()
            scheduled_date = fields.Datetime.to_datetime(harvest.harvest_forecast_date) if harvest.harvest_forecast_date else fields.Datetime.now()
            supplier_location, stock_location, _customer_location = harvest._stock_locations()
            picking_type = self.env["stock.picking.type"].sudo().search([("code", "=", "incoming")], limit=1)
            picking_values = {
                "partner_id": harvest.partner_id.id,
                "picking_type_id": picking_type.id,
                "location_id": supplier_location.id,
                "location_dest_id": stock_location.id,
                "scheduled_date": scheduled_date,
                "origin": "Prévision récolte SOJA %s" % (harvest.campaign or harvest.id),
                "soja_partner_id": harvest.partner_id.id,
                "soja_exploitation_id": harvest.exploitation_id.id,
                "soja_harvest_id": harvest.id,
            }
            move_values = {
                "name": "%s - %s" % (harvest.product_id.display_name, harvest.exploitation_id.display_name),
                "product_id": harvest.product_id.id,
                "product_uom_qty": qty,
                "product_uom": harvest.product_id.uom_id.id,
                "location_id": supplier_location.id,
                "location_dest_id": stock_location.id,
            }
            if harvest.stock_picking_id and harvest.stock_picking_id.state not in ("done", "cancel"):
                harvest.stock_picking_id.write(picking_values)
                move = harvest.stock_picking_id.move_ids_without_package[:1]
                if move:
                    move.write(move_values)
                else:
                    harvest.stock_picking_id.write({"move_ids_without_package": [(0, 0, move_values)]})
                continue
            if harvest.stock_picking_id:
                continue
            picking = self.env["stock.picking"].sudo().create(dict(picking_values, move_ids_without_package=[(0, 0, move_values)]))
            harvest.stock_picking_id = picking.id
        return self.action_open_stock_receipt()

    def action_record_forecast_history(self):
        History = self.env["soja.harvest.forecast.history"].sudo()
        for harvest in self:
            if not harvest.exploitation_id:
                continue
            last = History.search([("harvest_id", "=", harvest.id)], limit=1)
            values = {
                "harvest_id": harvest.id,
                "partner_id": harvest.partner_id.id,
                "exploitation_id": harvest.exploitation_id.id,
                "campaign": harvest.campaign,
                "seed_date": harvest.seed_date,
                "harvest_forecast_date": harvest.harvest_forecast_date,
                "yield_tha": harvest.yield_tha,
                "forecast_t": harvest.forecast_t,
                "stock_picking_id": harvest.stock_picking_id.id,
            }
            if last and all(last[field_name] == values[field_name] for field_name in (
                "campaign",
                "seed_date",
                "harvest_forecast_date",
                "yield_tha",
                "forecast_t",
            )) and last.exploitation_id.id == values["exploitation_id"] and last.stock_picking_id.id == values["stock_picking_id"]:
                continue
            History.create(values)

    def action_validate_stock_receipt(self):
        for harvest in self:
            if not harvest.stock_picking_id:
                harvest.action_create_stock_receipt()
            picking = harvest.stock_picking_id
            if not picking or picking.state == "done":
                continue
            if picking.state == "cancel":
                raise ValidationError("La prévision stock liée est annulée. Créez une nouvelle prévision avant de valider la récolte effective.")
            qty = harvest.actual_t or harvest._qty()
            move = picking.move_ids_without_package.filtered(lambda item: item.product_id == harvest.product_id)[:1] or picking.move_ids_without_package[:1]
            if move:
                move.write({
                    "product_uom_qty": qty,
                    "quantity": qty,
                })
            if picking.state == "draft":
                picking.action_confirm()
            if picking.state in ("confirmed", "waiting", "assigned"):
                picking.action_assign()
            if not harvest.lot_id:
                harvest.lot_id = self.env["stock.lot"].sudo().create({
                    "name": "%s - %s" % (harvest.partner_id.name, harvest.campaign or harvest.id),
                    "product_id": harvest.product_id.id,
                    "company_id": self.env.company.id,
                }).id
            move = picking.move_ids_without_package.filtered(lambda item: item.product_id == harvest.product_id)[:1] or picking.move_ids_without_package[:1]
            if move.move_line_ids:
                move.move_line_ids.write({
                    "quantity": qty,
                    "lot_id": harvest.lot_id.id,
                })
            elif move:
                self.env["stock.move.line"].sudo().create({
                    "picking_id": picking.id,
                    "move_id": move.id,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "quantity": qty,
                    "lot_id": harvest.lot_id.id,
                })
            picking.with_context(skip_backorder=True, skip_immediate=True).button_validate()
        return self.action_open_stock_receipt()

    def action_create_manufacturing_order(self):
        for harvest in self:
            if harvest.mrp_production_id:
                continue
            production = self.env["mrp.production"].sudo().create({
                "origin": "SOJA %s" % (harvest.campaign or harvest.id),
                "product_id": harvest.transformed_product_id.id,
                "product_qty": harvest._qty(),
                "product_uom_id": harvest.transformed_product_id.uom_id.id,
            })
            harvest.mrp_production_id = production.id
        return self.action_open_manufacturing_order()

    def action_create_purchase_order(self):
        for harvest in self:
            order_values = {
                "partner_id": harvest.partner_id.id,
                "origin": "SOJA %s" % (harvest.campaign or harvest.id),
                "soja_partner_id": harvest.partner_id.id,
                "soja_exploitation_id": harvest.exploitation_id.id,
                "soja_harvest_id": harvest.id,
            }
            line_values = {
                "name": "%s - %s" % (harvest.product_id.display_name, harvest.exploitation_id.display_name),
                "product_id": harvest.product_id.id,
                "product_qty": harvest.forecast_t or harvest._qty(),
                "product_uom": harvest.product_id.uom_po_id.id,
                "price_unit": 0.0,
                "date_planned": fields.Datetime.to_datetime(harvest.harvest_forecast_date) if harvest.harvest_forecast_date else fields.Datetime.now(),
            }
            if harvest.purchase_order_id and harvest.purchase_order_id.state in ("draft", "sent"):
                harvest.purchase_order_id.write(order_values)
                line = harvest.purchase_order_id.order_line[:1]
                if line:
                    line.write(line_values)
                else:
                    harvest.purchase_order_id.write({"order_line": [(0, 0, line_values)]})
                continue
            if harvest.purchase_order_id:
                continue
            order = self.env["purchase.order"].sudo().create(dict(order_values, order_line=[(0, 0, line_values)]))
            harvest.purchase_order_id = order.id
        return self.action_open_purchase_order()

    def action_create_service_order(self):
        service_map = [
            ("service_drone", "Service drone SOJA", "SOJA-SERVICE-DRONE"),
            ("service_soil", "Analyse sol SOJA", "SOJA-SERVICE-SOL"),
            ("service_training", "Coaching agricole SOJA", "SOJA-SERVICE-COACH"),
            ("service_finance", "Montage financement SOJA", "SOJA-SERVICE-FIN"),
        ]
        for harvest in self:
            if harvest.service_sale_order_id:
                continue
            lines = []
            for field_name, name, code in service_map:
                if harvest[field_name]:
                    product = harvest._get_or_create_service_product(name, code)
                    lines.append((0, 0, {
                        "name": product.display_name,
                        "product_id": product.id,
                        "product_uom_qty": 1.0,
                        "product_uom": product.uom_id.id,
                        "price_unit": 0.0,
                    }))
            if not lines:
                continue
            order = self.env["sale.order"].sudo().create({
                "partner_id": harvest.partner_id.id,
                "origin": "SOJA services %s" % (harvest.campaign or harvest.id),
                "order_line": lines,
            })
            harvest.service_sale_order_id = order.id
        return self.action_open_service_order()

    def action_create_financing_opportunity(self):
        for harvest in self:
            if harvest.crm_lead_id:
                continue
            lead = self.env["crm.lead"].sudo().create({
                "name": "Financement SOJA - %s - %s" % (harvest.partner_id.name, harvest.campaign or ""),
                "type": "opportunity",
                "partner_id": harvest.partner_id.id,
                "expected_revenue": harvest.bank_requested_amount or 0.0,
                "description": harvest.bank_note or harvest.bank_status or "",
            })
            harvest.crm_lead_id = lead.id
        return self.action_open_financing_opportunity()

    def action_create_field_task(self):
        for harvest in self:
            if harvest.project_task_id:
                continue
            harvest.exploitation_id._ensure_project()
            task = self.env["project.task"].sudo().create({
                "name": "Suivi %s - %s" % (harvest.partner_id.name, harvest.campaign or ""),
                "project_id": harvest.exploitation_id.project_id.id,
                "partner_id": harvest.partner_id.id,
                "soja_partner_id": harvest.partner_id.id,
                "soja_exploitation_id": harvest.exploitation_id.id,
                "soja_harvest_id": harvest.id,
            })
            harvest.project_task_id = task.id
        return self.action_open_field_task()

    def action_open_stock_receipt(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Prevision stock", "res_model": "stock.picking", "res_id": self.stock_picking_id.id, "view_mode": "form"}

    def action_open_manufacturing_order(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Fabrication", "res_model": "mrp.production", "res_id": self.mrp_production_id.id, "view_mode": "form"}

    def action_open_purchase_order(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Contrat achat", "res_model": "purchase.order", "res_id": self.purchase_order_id.id, "view_mode": "form"}

    def action_open_service_order(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Devis services", "res_model": "sale.order", "res_id": self.service_sale_order_id.id, "view_mode": "form"}

    def action_open_financing_opportunity(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Financement", "res_model": "crm.lead", "res_id": self.crm_lead_id.id, "view_mode": "form"}

    def action_open_field_task(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Tache terrain", "res_model": "project.task", "res_id": self.project_task_id.id, "view_mode": "form"}


class SojaStorageInfo(models.Model):
    _name = "soja.storage.info"
    _description = "Information de stockage SOJA"
    _order = "date desc, id desc"

    harvest_id = fields.Many2one("soja.harvest", string="Campagne", ondelete="set null", index=True)
    exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation", ondelete="cascade")
    exploitation_product_id = fields.Many2one("product.product", string="Ancienne exploitation produit", ondelete="set null")
    partner_id = fields.Many2one("res.partner", string="Producteur", related="exploitation_id.producer_id", store=True, readonly=True)
    cooperative_partner_id = fields.Many2one("res.partner", string="Coopérative de stockage", required=True, ondelete="restrict", domain=[("is_company", "=", True), ("is_soja_cooperative", "=", True)])
    storage_type = fields.Selection([("partial", "Partiel"), ("total", "Total")], string="Type de stockage", required=True)
    quantity_t = fields.Float(string="Quantité stockée (t)", digits=(10, 2))
    date = fields.Date(string="Date de stockage")
    note = fields.Char(string="Note")


class StockLocation(models.Model):
    _inherit = "stock.location"

    soja_cooperative_partner_id = fields.Many2one(
        "res.partner", string="Coopérative SOJA", ondelete="restrict", index=True,
        domain=[("is_company", "=", True), ("is_soja_cooperative", "=", True)],
    )


class StockQuant(models.Model):
    _inherit = "stock.quant"

    soja_cooperative_partner_id = fields.Many2one(
        "res.partner", string="Coopérative SOJA", ondelete="restrict", index=True,
        domain=[("is_company", "=", True), ("is_soja_cooperative", "=", True)],
    )
    soja_harvest_id = fields.Many2one("soja.harvest", string="Récolte SOJA", ondelete="set null", index=True)
    soja_exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation SOJA", compute="_compute_soja_exploitation_id", store=True, readonly=True)
    soja_exploitation_product_id = fields.Many2one("product.product", string="Ancienne exploitation produit", ondelete="set null")
    soja_storage_type = fields.Selection([("partial", "Partiel"), ("total", "Total")], string="Type de stockage")
    soja_storage_date = fields.Date(string="Date de stockage")
    soja_storage_note = fields.Char(string="Note de stockage")

    @api.model_create_multi
    def create(self, vals_list):
        Harvest = self.env["soja.harvest"].sudo()
        for values in vals_list:
            harvest = Harvest.browse(values.get("soja_harvest_id")).exists()
            if harvest and harvest.product_id:
                values["product_id"] = harvest.product_id.id
        return super().create(vals_list)

    def write(self, values):
        if values.get("soja_harvest_id") and not self.env.context.get("skip_soja_quant_product_sync"):
            harvest = self.env["soja.harvest"].sudo().browse(values["soja_harvest_id"]).exists()
            if harvest and harvest.product_id:
                values = dict(values, product_id=harvest.product_id.id)
        return super().write(values)

    @api.depends("soja_harvest_id.exploitation_id", "product_id.soja_exploitation_id")
    def _compute_soja_exploitation_id(self):
        for quant in self:
            quant.soja_exploitation_id = quant.soja_harvest_id.exploitation_id or quant.product_id.soja_exploitation_id

    @api.constrains("product_id", "quantity", "soja_cooperative_partner_id")
    def _check_soja_storage_quantity_against_actual_harvest(self):
        for quant in self.filtered(lambda item: item.product_id.is_soja_harvest_product and item.soja_cooperative_partner_id):
            harvests = quant.product_id.soja_harvest_ids.filtered(
                lambda item: item.harvest_actual_date or item.actual_t
            ).sorted(key=lambda item: (item.write_date or item.create_date, item.id), reverse=True)
            if not harvests:
                if quant.product_id.soja_stock_quant_ids.filtered(lambda item: item.soja_cooperative_partner_id and item.quantity > 0):
                    raise ValidationError(
                        "La quantité stockée ne peut être saisie qu'après l'enregistrement de la récolte effective."
                    )
                continue
            limit = harvests[0].actual_t
            total = sum(quant.product_id.soja_stock_quant_ids.filtered("soja_cooperative_partner_id").mapped("quantity"))
            if total > limit + 0.000001:
                raise ValidationError(
                    "Le total stocké pour l'exploitation (%s t) dépasse la quantité effective (%s t)."
                    % (total, limit)
                )


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    soja_partner_id = fields.Many2one("res.partner", string="Producteur SOJA", index=True)
    soja_exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation SOJA", index=True, ondelete="set null")
    soja_exploitation_product_id = fields.Many2one("product.product", string="Ancienne exploitation produit", index=True, ondelete="set null")
    factory_partner_id = fields.Many2one("res.partner", string="Usine SOJA", ondelete="restrict", index=True, domain=[("is_company", "=", True), ("is_soja_factory", "=", True)])
    soja_storage_source_id = fields.Many2one("stock.quant", string="Stockage source", ondelete="set null", domain="[('soja_exploitation_id', '=', soja_exploitation_id), ('soja_cooperative_partner_id', '!=', False)]")
    soja_harvest_id = fields.Many2one("soja.harvest", string="Récolte SOJA", ondelete="set null", index=True)
    soja_dehull = fields.Boolean(string="Décorticage")
    soja_grind = fields.Boolean(string="Broyage")
    soja_process_date = fields.Date(string="Date de traitement")
    soja_process_note = fields.Char(string="Note de traitement")


class CrmLead(models.Model):
    _inherit = "crm.lead"

    soja_currency_id = fields.Many2one("res.currency", string="Devise SOJA", default=lambda self: self.env.company.currency_id)
    soja_partner_id = fields.Many2one("res.partner", string="Producteur SOJA", index=True, ondelete="set null")
    soja_exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation SOJA", index=True, ondelete="set null")
    soja_exploitation_product_id = fields.Many2one(
        "product.product", string="Ancienne exploitation produit", index=True, ondelete="set null",
    )
    soja_bank_partner_id = fields.Many2one(
        "res.partner", string="Banque SOJA", index=True, ondelete="restrict",
        domain=[("is_company", "=", True), ("is_soja_bank", "=", True)],
    )
    soja_harvest_id = fields.Many2one("soja.harvest", string="Récolte SOJA", index=True, ondelete="set null")
    soja_borrower_type = fields.Selection(
        [("producer", "Producteur"), ("buyer", "Acheteur"), ("cooperative", "Coopérative"), ("group", "Groupement")],
        string="Type emprunteur",
    )
    soja_borrower_name = fields.Char(string="Nom emprunteur")
    soja_requested_amount = fields.Monetary(string="Montant demandé", currency_field="soja_currency_id")
    soja_approved_amount = fields.Monetary(string="Montant approuvé", currency_field="soja_currency_id")
    soja_risk_level = fields.Selection(
        [("low", "Faible"), ("standard", "Standard"), ("watch", "À surveiller"), ("priority", "Prioritaire"), ("medium", "Moyen"), ("high", "Élevé")],
        string="Risque",
    )
    soja_decision_status = fields.Char(string="Statut décision")
    soja_decision_date = fields.Date(string="Date de décision")
    soja_financing_note = fields.Char(string="Note financement")

class SojaTreatmentInfo(models.Model):
    _name = "soja.treatment.info"
    _description = "Information de traitement usine SOJA"
    _order = "process_date desc, id desc"

    harvest_id = fields.Many2one("soja.harvest", string="Campagne", ondelete="set null", index=True)
    exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation", ondelete="cascade")
    exploitation_product_id = fields.Many2one("product.product", string="Ancienne exploitation produit", ondelete="set null")
    storage_info_id = fields.Many2one("stock.quant", string="Stockage source", ondelete="set null", domain="[('soja_exploitation_id', '=', exploitation_id), ('soja_cooperative_partner_id', '!=', False)]")
    partner_id = fields.Many2one("res.partner", string="Producteur", related="exploitation_id.producer_id", store=True, readonly=True)
    factory_partner_id = fields.Many2one("res.partner", string="Usine", required=True, ondelete="restrict", domain=[("is_company", "=", True), ("is_soja_factory", "=", True)])
    dehull = fields.Boolean(string="Décorticage")
    grind = fields.Boolean(string="Broyage")
    process_date = fields.Date(string="Date de traitement")
    note = fields.Char(string="Note")


class SojaBankInfo(models.Model):
    _name = "soja.bank.info"
    _description = "Information bancaire SOJA"
    _order = "decision_date desc, id desc"

    harvest_id = fields.Many2one("soja.harvest", string="Campagne", ondelete="set null", index=True)
    exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation", ondelete="cascade")
    exploitation_product_id = fields.Many2one("product.product", string="Ancienne exploitation produit", ondelete="set null")
    partner_id = fields.Many2one("res.partner", string="Producteur", related="exploitation_id.producer_id", store=True, readonly=True)
    bank_partner_id = fields.Many2one("res.partner", string="Banque", required=True, ondelete="restrict", domain=[("is_company", "=", True), ("is_soja_bank", "=", True)])
    borrower_type = fields.Selection([("producer", "Producteur"), ("buyer", "Acheteur"), ("cooperative", "Coopérative"), ("group", "Groupement")], string="Type emprunteur")
    borrower_name = fields.Char(string="Nom emprunteur")
    requested_amount = fields.Monetary(string="Montant demandé")
    approved_amount = fields.Monetary(string="Montant approuvé")
    risk_level = fields.Selection([("low", "Faible"), ("standard", "Standard"), ("watch", "À surveiller"), ("priority", "Prioritaire"), ("medium", "Moyen"), ("high", "Élevé")], string="Risque")
    status = fields.Char(string="Statut")
    decision_date = fields.Date(string="Date de décision")
    note = fields.Char(string="Note")
    currency_id = fields.Many2one("res.currency", string="Devise", default=lambda self: self.env.company.currency_id)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    soja_partner_id = fields.Many2one("res.partner", string="Producteur SOJA", index=True)
    soja_exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation SOJA", index=True, ondelete="set null")
    soja_exploitation_product_id = fields.Many2one(
        "product.product",
        string="Ancienne exploitation produit",
        index=True,
    )
    soja_harvest_id = fields.Many2one("soja.harvest", string="Prevision SOJA", index=True)


class SojaHarvestForecastHistory(models.Model):
    _name = "soja.harvest.forecast.history"
    _description = "Historique des previsions de recolte SOJA"
    _order = "create_date desc, id desc"

    harvest_id = fields.Many2one("soja.harvest", string="Recolte SOJA", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one("res.partner", string="Producteur", required=True, index=True)
    exploitation_id = fields.Many2one(
        "soja.exploitation",
        string="Exploitation",
        required=True,
        index=True,
    )
    exploitation_product_id = fields.Many2one("product.product", string="Ancienne exploitation produit", ondelete="set null")
    campaign = fields.Char(string="Campagne")
    seed_date = fields.Date(string="Date semence")
    harvest_forecast_date = fields.Date(string="Date recolte prevue")
    yield_tha = fields.Float(string="Rendement prevu (t/ha)", digits=(10, 2))
    forecast_t = fields.Float(string="Quantite prevue (t)", digits=(10, 2))
    stock_picking_id = fields.Many2one("stock.picking", string="Prevision stock", ondelete="set null")


class StockPicking(models.Model):
    _inherit = "stock.picking"

    soja_partner_id = fields.Many2one("res.partner", string="Producteur SOJA", index=True)
    soja_exploitation_id = fields.Many2one("soja.exploitation", string="Exploitation SOJA", index=True, ondelete="set null")
    soja_exploitation_product_id = fields.Many2one(
        "product.product",
        string="Ancienne exploitation produit",
        index=True,
    )
    soja_harvest_id = fields.Many2one("soja.harvest", string="Prevision SOJA", index=True)
