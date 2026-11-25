"""Remove SOJA demo records and generated records linked to them."""

def ref(xmlid):
    return env.ref("soja_management.%s" % xmlid, raise_if_not_found=False)


demo_partners = env["res.partner"].sudo().browse([
    ref("cooperative_save").id,
    ref("cooperative_borgou").id,
    ref("factory_soja_centre").id,
    ref("bank_agri_benin").id,
    ref("producer_jean_koffi").id,
    ref("producer_pauline_hounkpatin").id,
])
demo_exploitations = env["product.product"].sudo().browse([
    ref("exploitation_jean_save").id,
    ref("exploitation_pauline_borgou").id,
])
demo_harvests = env["soja.harvest"].sudo().search([
    ("exploitation_product_id", "in", demo_exploitations.ids),
])
demo_locations = env["stock.location"].sudo().search([
    ("soja_cooperative_partner_id", "in", demo_partners.ids),
])

pickings = demo_harvests.mapped("stock_picking_id")
env["crm.lead"].sudo().search([
    ("soja_exploitation_product_id", "in", demo_exploitations.ids),
]).unlink()
env["crm.lead"].sudo().search([
    ("soja_bank_partner_id", "in", demo_partners.ids),
]).unlink()
env["mrp.production"].sudo().search([
    ("soja_exploitation_product_id", "in", demo_exploitations.ids),
]).unlink()
env["mrp.production"].sudo().search([
    ("factory_partner_id", "in", demo_partners.ids),
]).unlink()
env["stock.quant"].sudo().search([
    "|",
    ("product_id", "in", demo_exploitations.ids),
    ("location_id", "in", demo_locations.ids),
]).unlink()
env["soja.plot.point"].sudo().search([
    ("exploitation_product_id", "in", demo_exploitations.ids),
]).unlink()
env["soja.storage.info"].sudo().search([
    ("exploitation_product_id", "in", demo_exploitations.ids),
]).unlink()
env["soja.storage.info"].sudo().search([
    ("cooperative_partner_id", "in", demo_partners.ids),
]).unlink()
env["soja.treatment.info"].sudo().search([
    ("exploitation_product_id", "in", demo_exploitations.ids),
]).unlink()
env["soja.treatment.info"].sudo().search([
    ("factory_partner_id", "in", demo_partners.ids),
]).unlink()
env["soja.bank.info"].sudo().search([
    ("exploitation_product_id", "in", demo_exploitations.ids),
]).unlink()
env["soja.bank.info"].sudo().search([
    ("bank_partner_id", "in", demo_partners.ids),
]).unlink()
demo_locations.unlink()
demo_harvests.unlink()
pickings.unlink()
demo_exploitations.unlink()
demo_partners.unlink()
env.cr.commit()

print("Removed SOJA demo records: %s partners, %s exploitations, %s harvests" % (
    len(demo_partners), len(demo_exploitations), len(demo_harvests),
))
