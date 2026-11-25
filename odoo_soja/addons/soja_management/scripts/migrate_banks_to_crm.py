"""Convert legacy SOJA bank dossiers into native CRM opportunities."""

Legacy = env["soja.bank.info"].sudo()
Lead = env["crm.lead"].sudo()
created = 0
stage_ids = {
    "Dossier reçu": "soja_crm_stage_received",
    "Analyse risque": "soja_crm_stage_risk",
    "Proposition financement": "soja_crm_stage_proposal",
    "Approuvé": "soja_crm_stage_approved",
    "Refusé": "soja_crm_stage_refused",
    "Décision en attente": "soja_crm_stage_pending",
}
for legacy in Legacy.search([]):
    exploitation = legacy.exploitation_product_id
    if not exploitation or not legacy.bank_partner_id:
        continue
    origin = "SOJA dossier bancaire %s" % legacy.id
    existing = Lead.search([("description", "ilike", origin)], limit=1)
    if existing:
        stage = env.ref("soja_management.%s" % stage_ids.get(legacy.status), raise_if_not_found=False)
        if stage:
            existing.write({"stage_id": stage.id})
        continue
    lead = Lead.create({
        "name": "Financement SOJA - %s" % exploitation.name,
        "type": "opportunity",
        "description": "%s\n%s" % (origin, legacy.note or ""),
        "soja_partner_id": exploitation.soja_owner_id.id,
        "soja_exploitation_product_id": exploitation.id,
        "soja_bank_partner_id": legacy.bank_partner_id.id,
        "soja_harvest_id": legacy.harvest_id.id if legacy.harvest_id else False,
        "soja_borrower_type": legacy.borrower_type,
        "soja_borrower_name": legacy.borrower_name,
        "soja_requested_amount": legacy.requested_amount,
        "soja_approved_amount": legacy.approved_amount,
        "soja_risk_level": legacy.risk_level,
        "soja_decision_status": legacy.status,
        "soja_decision_date": legacy.decision_date,
        "soja_financing_note": legacy.note,
        "stage_id": env.ref("soja_management.%s" % stage_ids.get(legacy.status), raise_if_not_found=False).id if stage_ids.get(legacy.status) else False,
    })
    created += 1

print("Created CRM financing opportunities: %s" % created)
env.cr.commit()
