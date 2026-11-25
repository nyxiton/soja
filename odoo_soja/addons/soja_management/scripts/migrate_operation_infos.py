"""Convert legacy single storage, factory and bank values into child records."""

Harvest = env["soja.harvest"].sudo()
Storage = env["soja.storage.info"].sudo()
Treatment = env["soja.treatment.info"].sudo()
Bank = env["soja.bank.info"].sudo()

storage_count = treatment_count = bank_count = 0
for harvest in Harvest.search([]):
    exploitation = harvest.exploitation_product_id
    if not exploitation:
        continue

    if harvest.cooperative_partner_id and (harvest.stock_type or harvest.stock_qty_t or harvest.stock_date or harvest.stock_note):
        existing_storage = Storage.search([
            ("exploitation_product_id", "=", exploitation.id),
            ("cooperative_partner_id", "=", harvest.cooperative_partner_id.id),
        ], limit=1)
        if not existing_storage:
            Storage.create({
                "harvest_id": harvest.id,
                "exploitation_product_id": exploitation.id,
                "cooperative_partner_id": harvest.cooperative_partner_id.id,
                "storage_type": harvest.stock_type or "partial",
                "quantity_t": harvest.stock_qty_t,
                "date": harvest.stock_date,
                "note": harvest.stock_note,
            })
            storage_count += 1
        elif not existing_storage.harvest_id:
            existing_storage.harvest_id = harvest.id

    if harvest.factory_partner_id and (harvest.factory_dehull or harvest.factory_grind or harvest.factory_process_date or harvest.factory_process_note):
        existing_treatment = Treatment.search([
            ("exploitation_product_id", "=", exploitation.id),
            ("factory_partner_id", "=", harvest.factory_partner_id.id),
            ("process_date", "=", harvest.factory_process_date),
        ], limit=1)
        if not existing_treatment:
            Treatment.create({
                "harvest_id": harvest.id,
                "exploitation_product_id": exploitation.id,
                "factory_partner_id": harvest.factory_partner_id.id,
                "dehull": harvest.factory_dehull,
                "grind": harvest.factory_grind,
                "process_date": harvest.factory_process_date,
                "note": harvest.factory_process_note,
            })
            treatment_count += 1
        elif not existing_treatment.harvest_id:
            existing_treatment.harvest_id = harvest.id

    if harvest.bank_partner_id and any((
        harvest.bank_borrower_type,
        harvest.bank_borrower_name,
        harvest.bank_requested_amount,
        harvest.bank_approved_amount,
        harvest.bank_risk_level,
        harvest.bank_status,
        harvest.bank_decision_date,
        harvest.bank_note,
    )):
        existing_bank = Bank.search([
            ("exploitation_product_id", "=", exploitation.id),
            ("bank_partner_id", "=", harvest.bank_partner_id.id),
            ("decision_date", "=", harvest.bank_decision_date),
        ], limit=1)
        if not existing_bank:
            Bank.create({
                "harvest_id": harvest.id,
                "exploitation_product_id": exploitation.id,
                "bank_partner_id": harvest.bank_partner_id.id,
                "borrower_type": harvest.bank_borrower_type,
                "borrower_name": harvest.bank_borrower_name,
                "requested_amount": harvest.bank_requested_amount,
                "approved_amount": harvest.bank_approved_amount,
                "risk_level": harvest.bank_risk_level,
                "status": harvest.bank_status,
                "decision_date": harvest.bank_decision_date,
                "note": harvest.bank_note,
                "currency_id": harvest.currency_id.id,
            })
            bank_count += 1
        elif not existing_bank.harvest_id:
            existing_bank.harvest_id = harvest.id

env.cr.commit()
print("Created storage infos: %s" % storage_count)
print("Created treatment infos: %s" % treatment_count)
print("Created bank infos: %s" % bank_count)
