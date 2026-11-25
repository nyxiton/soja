Harvest = env["soja.harvest"].sudo()

harvests = Harvest.search([
    ("exploitation_product_id", "!=", False),
    "|",
    ("harvest_forecast_date", "!=", False),
    ("forecast_t", ">", 0),
])

created_before = env["soja.harvest.forecast.history"].sudo().search_count([])
harvests.action_record_forecast_history()
created_after = env["soja.harvest.forecast.history"].sudo().search_count([])

env.cr.commit()

print("Created SOJA forecast history rows:", created_after - created_before)
print("Checked harvests:", len(harvests))
