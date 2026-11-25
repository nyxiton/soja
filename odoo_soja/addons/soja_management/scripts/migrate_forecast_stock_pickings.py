PurchaseOrder = env["purchase.order"].sudo()
Harvest = env["soja.harvest"].sudo()

orders = PurchaseOrder.search([
    ("soja_harvest_id", "!=", False),
    ("state", "in", ["draft", "sent", "cancel"]),
])
harvests_with_orders = orders.mapped("soja_harvest_id")
harvests_with_orders.write({"purchase_order_id": False})
orders.filtered(lambda order: order.state != "cancel").button_cancel()
orders.unlink()

harvests = Harvest.search([
    ("stock_picking_id", "=", False),
    ("exploitation_product_id", "!=", False),
    "|",
    ("harvest_forecast_date", "!=", False),
    ("forecast_t", ">", 0),
])

created = 0
for harvest in harvests:
    before = harvest.stock_picking_id
    harvest.action_create_stock_receipt()
    if not before and harvest.stock_picking_id:
        created += 1

env.cr.commit()

print("Deleted draft SOJA purchase orders:", len(orders))
print("Created SOJA stock forecasts:", created)
print("Checked harvests:", len(harvests))
