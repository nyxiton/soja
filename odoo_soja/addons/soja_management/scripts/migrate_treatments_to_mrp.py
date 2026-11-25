"""Convert legacy factory treatment rows into native manufacturing orders."""

Treatment = env["soja.treatment.info"].sudo()
Production = env["mrp.production"].sudo()
Quant = env["stock.quant"].sudo()

created = 0
for legacy in Treatment.search([]):
    exploitation = legacy.exploitation_product_id
    factory = legacy.factory_partner_id
    if not exploitation or not factory:
        continue

    existing = Production.search([
        ("origin", "=", "SOJA traitement %s" % legacy.id),
    ], limit=1)
    if existing:
        continue

    if exploitation.product_tmpl_id.type != "product":
        exploitation.product_tmpl_id.sudo().write({"type": "product"})

    source = legacy.storage_info_id
    if not source or source._name != "stock.quant" or not source.exists():
        source = Quant.search([
            ("product_id", "=", exploitation.id),
            ("soja_cooperative_partner_id", "!=", False),
        ], order="quantity desc, id desc", limit=1)

    harvest = legacy.harvest_id
    quantity = source.quantity if source else (harvest.actual_t or harvest.forecast_t or 1.0)
    Production.create({
        "origin": "SOJA traitement %s" % legacy.id,
        "product_id": exploitation.id,
        "product_qty": max(quantity, 0.0001),
        "product_uom_id": exploitation.uom_id.id,
        "company_id": env.company.id,
        "soja_partner_id": exploitation.soja_owner_id.id,
        "soja_exploitation_product_id": exploitation.id,
        "factory_partner_id": factory.id,
        "soja_storage_source_id": source.id if source else False,
        "soja_harvest_id": harvest.id if harvest else False,
        "soja_dehull": legacy.dehull,
        "soja_grind": legacy.grind,
        "soja_process_date": legacy.process_date,
        "soja_process_note": legacy.note,
    })
    created += 1

print("Created manufacturing orders: %s" % created)
env.cr.commit()
