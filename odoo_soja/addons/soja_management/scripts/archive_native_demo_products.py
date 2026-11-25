"""Archive standard catalog demo products while preserving SOJA products."""

ProductTemplate = env["product.template"].sudo()
Product = env["product.product"].sudo()

# The standard demo catalog occupies these templates in this database.
templates = ProductTemplate.search([
    ("id", "<=", 50),
    ("name", "not ilike", "SOJA"),
    ("is_soja_exploitation", "=", False),
])
templates.write({"active": False})
Product.search([("product_tmpl_id", "in", templates.ids)]).write({"active": False})
env.cr.commit()
print("Archived native demo product templates: %s" % len(templates))
