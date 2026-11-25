"""Move legacy storage information to native Odoo stock quants."""

Storage = env["soja.storage.info"].sudo()
Quant = env["stock.quant"].sudo()
Location = env["stock.location"].sudo()
created = 0

for info in Storage.search([]):
    exploitation = info.exploitation_product_id
    cooperative = info.cooperative_partner_id
    if not exploitation or not cooperative:
        continue
    if exploitation.product_tmpl_id.type != "product":
        exploitation.product_tmpl_id.write({"type": "product"})
    location = Location.search([
        ("soja_cooperative_partner_id", "=", cooperative.id),
        ("usage", "=", "internal"),
    ], limit=1)
    if not location:
        parent = Location.search([
            ("usage", "=", "internal"), ("scrap_location", "=", False),
            ("company_id", "in", [False, env.company.id]),
        ], limit=1)
        company_id = parent.company_id.id if parent and parent.company_id else env.company.id
        location = Location.create({
            "name": "Stockage SOJA - %s" % cooperative.name,
            "location_id": parent.id if parent else False,
            "usage": "internal",
            "soja_cooperative_partner_id": cooperative.id,
            "company_id": company_id,
        })
    quant = Quant.search([
        ("product_id", "=", exploitation.id),
        ("location_id", "=", location.id),
        ("soja_cooperative_partner_id", "=", cooperative.id),
    ], limit=1)
    values = {
        "product_id": exploitation.id,
        "location_id": location.id,
        "company_id": location.company_id.id or env.company.id,
        "soja_cooperative_partner_id": cooperative.id,
        "soja_harvest_id": info.harvest_id.id if info.harvest_id else False,
        "quantity": info.quantity_t or 0,
        "soja_storage_type": info.storage_type or "partial",
        "soja_storage_date": info.date or False,
        "soja_storage_note": info.note or "",
    }
    if quant:
        quant.write(values)
    else:
        Quant.create(values)
        created += 1

env.cr.commit()
print("Created inventory quants: %s" % created)
