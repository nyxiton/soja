import json
from html import escape

from odoo import http
from odoo.exceptions import AccessDenied, AccessError, ValidationError
from odoo.http import request


SOY_TO_ODOO = {"Conventionnel": "conventional", "Bio": "organic", "conventional": "conventional", "organic": "organic"}
SOY_FROM_ODOO = {"conventional": "Conventionnel", "organic": "Bio"}
TENURE_TO_ODOO = {"Propriété": "owner", "Propriete": "owner", "Location": "rental", "Concession": "concession", "Autre": "other", "owner": "owner", "rental": "rental", "concession": "concession", "other": "other"}
TENURE_FROM_ODOO = {"owner": "Propriété", "rental": "Location", "concession": "Concession", "other": "Autre"}
FERTILIZER_TO_ODOO = {"Semence": "seed", "K2SO4": "k2so4", "KCL": "kcl", "Inoculum": "inoculum", "Aucun": "none", "seed": "seed", "k2so4": "k2so4", "kcl": "kcl", "inoculum": "inoculum", "none": "none"}
FERTILIZER_FROM_ODOO = {"seed": "Semence", "k2so4": "K2SO4", "kcl": "KCL", "inoculum": "Inoculum", "none": "Aucun"}
PESTICIDE_TO_ODOO = {"Herbicide total": "total", "Herbicide sélectif": "selective", "Herbicide selectif": "selective", "Aucun": "none", "total": "total", "selective": "selective", "none": "none"}
PESTICIDE_FROM_ODOO = {"total": "Herbicide total", "selective": "Herbicide sélectif", "none": "Aucun"}
YESNO_TO_ODOO = {"Oui": "yes", "Non": "no", "yes": "yes", "no": "no"}
YESNO_FROM_ODOO = {"yes": "Oui", "no": "Non"}
SEX_TO_ODOO = {"F": "f", "M": "m", "f": "f", "m": "m"}
SEX_FROM_ODOO = {"f": "F", "m": "M"}
RISK_TO_ODOO = {
    "Faible": "low",
    "Standard": "standard",
    "À surveiller": "watch",
    "A surveiller": "watch",
    "Prioritaire": "priority",
    "low": "low",
    "standard": "standard",
    "watch": "watch",
    "priority": "priority",
    "medium": "medium",
    "high": "high",
}
RISK_FROM_ODOO = {"low": "Faible", "standard": "Standard", "watch": "À surveiller", "priority": "Prioritaire", "medium": "Moyen", "high": "Élevé"}
CRM_STATUS_STAGE_XMLIDS = {
    "Dossier reçu": "soja_crm_stage_received",
    "Analyse risque": "soja_crm_stage_risk",
    "Proposition financement": "soja_crm_stage_proposal",
    "Approuvé": "soja_crm_stage_approved",
    "Refusé": "soja_crm_stage_refused",
    "Décision en attente": "soja_crm_stage_pending",
}
ASSET_VERSION = "20260908-disable-offline-refresh"
ROLE_GROUPS = {
    "manager": "soja_management.group_soja_manager",
    "producer": "soja_management.group_soja_producer",
    "cooperative": "soja_management.group_soja_cooperative",
    "factory": "soja_management.group_soja_factory",
    "bank": "soja_management.group_soja_bank",
}
REGISTERABLE_ROLES = {
    "producer": "Producteur",
    "cooperative": "Cooperative",
    "factory": "Usine",
    "bank": "Banque",
}
ROLE_VIEWS = {
    "manager": ["entry", "list", "details", "seed", "harvest", "cooperative", "factory", "bank"],
    "producer": ["entry", "details", "harvest"],
    "cooperative": ["cooperative", "details"],
    "factory": ["factory", "details"],
    "bank": ["bank", "details"],
}
PARTNER_SHARE_STATUS = {
    "cooperative": ["partners", "cooperative"],
    "factory": ["partners", "factory"],
    "bank": ["partners", "bank"],
}
PRODUCER_HARVEST_KEYS = {
    "partner_id",
    "exploitation_id",
    "campaign",
    "seed_date",
    "harvest_forecast_date",
    "harvest_actual_date",
    "yield_tha",
    "actual_yield_tha",
    "forecast_t",
    "actual_t",
    "share_status",
    "service_drone",
    "service_soil",
    "service_training",
    "service_finance",
}
PARTNER_HARVEST_KEYS = {
    "cooperative": {"partner_id", "exploitation_id", "stock_type", "stock_qty_t", "stock_date", "stock_note", "share_status"},
    "factory": {"partner_id", "exploitation_id", "factory_dehull", "factory_grind", "factory_process_date", "factory_process_note", "share_status"},
    "bank": {
        "partner_id",
        "exploitation_id",
        "bank_borrower_type",
        "bank_borrower_name",
        "bank_requested_amount",
        "bank_approved_amount",
        "bank_risk_level",
        "bank_status",
        "bank_decision_date",
        "bank_note",
        "share_status",
    },
}


def _body():
    try:
        return json.loads(request.httprequest.get_data(as_text=True) or "{}")
    except json.JSONDecodeError:
        return {}


def _json_error(message, status=403):
    return request.make_json_response({"error": message}, status=status)


def _crm_stage_for_status(status):
    xmlid = CRM_STATUS_STAGE_XMLIDS.get(status or "")
    return request.env.ref("soja_management.%s" % xmlid, raise_if_not_found=False) if xmlid else request.env["crm.stage"]


def _current_role():
    user = request.env.user
    if user.has_group("base.group_system") or user.has_group(ROLE_GROUPS["manager"]):
        return "manager"
    for role in ("producer", "cooperative", "factory", "bank"):
        if user.has_group(ROLE_GROUPS[role]):
            return role
    return None


def _role_partner(role):
    user_fields = {
        "cooperative": "soja_cooperative_id",
        "factory": "soja_factory_id",
        "bank": "soja_bank_id",
    }
    field_name = user_fields.get(role)
    if not field_name:
        return request.env["res.partner"]
    user = request.env.user.sudo()
    partner = getattr(user, field_name)
    if partner:
        return partner
    partner = user.partner_id
    role_flags = {"cooperative": "is_soja_cooperative", "factory": "is_soja_factory", "bank": "is_soja_bank"}
    if getattr(partner, role_flags[role]):
        return partner
    role_partner = request.env["res.partner"].sudo().search([
        ("is_company", "=", True),
        (role_flags[role], "=", True),
    ], limit=2)
    return role_partner if len(role_partner) == 1 else request.env["res.partner"]


def _session_payload():
    role = _current_role()
    return {
        "user": {"id": request.env.user.id, "name": request.env.user.name},
        "role": role,
        "views": ROLE_VIEWS.get(role, []),
    }


def _producer_domain(role):
    base_domain = [("is_soja_producer", "=", True)]
    if role == "manager":
        return base_domain
    if role == "producer":
        return base_domain + [("soja_user_id", "=", request.env.user.id)]
    if role in PARTNER_SHARE_STATUS:
        return base_domain + [("soja_harvest_ids.share_status", "in", PARTNER_SHARE_STATUS[role])]
    return [("id", "=", 0)]


def _producer_for_access(producer_id, role):
    return request.env["res.partner"].search([("id", "=", producer_id)] + _producer_domain(role), limit=1)


def _exploitation_for_access(exploitation_ref, role, write=False):
    if write and role not in ("manager", "producer"):
        return request.env["soja.exploitation"]
    domain = []
    if str(exploitation_ref or "").isdigit():
        domain = [("id", "=", int(exploitation_ref))]
    else:
        domain = [("api_identifier", "=", _str(exploitation_ref))]
    producer_domain = _producer_domain(role)
    if producer_domain == [("id", "=", 0)]:
        return request.env["soja.exploitation"]
    return request.env["soja.exploitation"].sudo().search(domain + [("producer_id." + item[0], item[1], item[2]) for item in producer_domain], limit=1)


def _can_create_producer(role):
    if role == "manager":
        return True
    if role != "producer":
        return False
    return not request.env["res.partner"].search_count([("is_soja_producer", "=", True), ("soja_user_id", "=", request.env.user.id)])


def _filter_values(values, allowed_keys):
    return {key: value for key, value in values.items() if key in allowed_keys}


def _html_response(content):
    return request.make_response(content, headers=[("Content-Type", "text/html; charset=utf-8")])


def _js_response(content):
    return request.make_response(content, headers=[("Content-Type", "application/javascript; charset=utf-8"), ("Cache-Control", "no-cache")])


def _auth_page(mode="login", error="", values=None):
    values = values or {}
    is_register = mode == "register"
    title = "Inscription SOJA" if is_register else "Connexion SOJA"
    action = "/soja/register" if is_register else "/soja/login"
    role_options = "".join(
        '<option value="%s" %s>%s</option>' % (
            escape(key),
            "selected" if values.get("role") == key else "",
            escape(label),
        )
        for key, label in REGISTERABLE_ROLES.items()
    )
    register_fields = """
        <label>Rôle
          <select name="role" required>%s</select>
        </label>
        <label>Nom complet
          <input name="name" autocomplete="name" required value="%s"/>
        </label>
        <label>Confirmer le mot de passe
          <input name="confirm_password" type="password" autocomplete="new-password" required/>
        </label>
    """ % (role_options, escape(values.get("name", ""))) if is_register else ""
    return _html_response("""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>%s</title>
  <style>
    :root { --bg:#f6f8fb; --card:#fff; --text:#111827; --muted:#667085; --line:rgba(17,24,39,.14); --accent:#246bfe; --danger:#dc2626; }
    * { box-sizing:border-box; }
    body { min-height:100vh; margin:0; display:grid; place-items:center; background:var(--bg); color:var(--text); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { width:min(460px, calc(100vw - 32px)); padding:28px; border:1px solid var(--line); border-radius:8px; background:var(--card); box-shadow:0 18px 42px rgba(16,24,40,.10); }
    h1 { margin:0 0 8px; font-size:1.7rem; }
    p { margin:0 0 22px; color:var(--muted); font-weight:650; line-height:1.45; }
    form { display:grid; gap:14px; }
    label { display:grid; gap:7px; font-weight:800; }
    input, select { min-height:44px; width:100%%; padding:10px 12px; border:1px solid var(--line); border-radius:8px; font:inherit; color:var(--text); background:#fff; }
    input:focus, select:focus { outline:none; border-color:rgba(36,107,254,.55); box-shadow:0 0 0 4px rgba(36,107,254,.12); }
    button { min-height:44px; border:0; border-radius:8px; background:var(--accent); color:#fff; font:inherit; font-weight:850; cursor:pointer; }
    .error { margin:0 0 16px; padding:12px; border:1px solid rgba(220,38,38,.22); border-radius:8px; background:#fef2f2; color:var(--danger); }
    .links { display:flex; justify-content:space-between; gap:12px; margin-top:18px; }
    a { color:var(--accent); font-weight:800; text-decoration:none; }
  </style>
</head>
<body>
  <main>
    <h1>%s</h1>
    <p>%s</p>
    %s
    <form method="post" action="%s">
      %s
      <label>Identifiant
        <input name="login" type="text" autocomplete="username" required value="%s"/>
      </label>
      <label>Mot de passe
        <input name="password" type="password" autocomplete="%s" required/>
      </label>
      <button type="submit">%s</button>
    </form>
    <div class="links">%s</div>
  </main>
</body>
</html>""" % (
        escape(title),
        escape(title),
        "Créez votre session SOJA et accédez uniquement à l'espace autorisé." if is_register else "Connectez-vous pour accéder à votre espace SOJA.",
        '<div class="error">%s</div>' % escape(error) if error else "",
        action,
        register_fields,
        escape(values.get("login", "")),
        "new-password" if is_register else "current-password",
        "Créer le compte" if is_register else "Se connecter",
        '<a href="/soja/login">Déjà inscrit</a>' if is_register else "",
    ))


def _request_db():
    return request.db or request.session.db or "odoo_soja"


def _date(value):
    return value.isoformat() if value else None


def _float(value):
    if value in (None, ""):
        return False
    try:
        return float(value)
    except (TypeError, ValueError):
        return False


def _str(value):
    return (value or "").strip() if isinstance(value, str) else (value or "")


def _gps_points_from_payload(payload):
    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        raise ValidationError("Le champ points doit être une liste.")
    points = []
    for index, point in enumerate(raw_points, start=1):
        if not isinstance(point, dict):
            raise ValidationError("Le point GPS %s est invalide." % index)
        longitude = point.get("lon", point.get("longitude"))
        latitude = point.get("lat", point.get("latitude"))
        try:
            longitude = float(longitude)
            latitude = float(latitude)
        except (TypeError, ValueError):
            raise ValidationError("Longitude/latitude invalides pour le point %s." % index)
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise ValidationError("Coordonnées GPS hors limites pour le point %s." % index)
        points.append({
            "sequence": int(point.get("sequence") or index),
            "longitude": longitude,
            "latitude": latitude,
            "osm_situation": _str(point.get("osmSituation") or point.get("osm_situation")),
        })
    return points


def _soja_company(name, role):
    return request.env["res.partner"]._get_or_create_soja_company(_str(name), role)


def _latest_harvest(producer):
    return producer.soja_harvest_ids[:1]


def _primary_exploitation(producer):
    return producer.soja_exploitation_ids[:1]


def _find_payload_exploitation(producer, harvest_payload):
    exploitation_id = harvest_payload.get("exploitationId")
    try:
        exploitation_id = int(exploitation_id or 0)
    except (TypeError, ValueError):
        exploitation_id = 0
    if exploitation_id:
        exploitation = request.env["soja.exploitation"].sudo().search([
            ("id", "=", exploitation_id),
            ("producer_id", "=", producer.id),
        ], limit=1)
        if exploitation:
            return exploitation
    return _primary_exploitation(producer)


def _cooperative_stock_location(cooperative):
    Location = request.env["stock.location"].sudo()
    location = Location.search([
        ("soja_cooperative_partner_id", "=", cooperative.id),
        ("usage", "=", "internal"),
    ], limit=1)
    if location:
        return location
    parent = Location.search([
        ("usage", "=", "internal"), ("scrap_location", "=", False),
        ("company_id", "in", [False, request.env.company.id]),
    ], limit=1)
    company_id = parent.company_id.id if parent and parent.company_id else request.env.company.id
    return Location.create({
        "name": "Stockage SOJA - %s" % cooperative.name,
        "location_id": parent.id if parent else False,
        "usage": "internal",
        "soja_cooperative_partner_id": cooperative.id,
        "company_id": company_id,
    })


def _serialize_exploitation(exploitation, role=None):
    role_partner = _role_partner(role)
    storage_infos = exploitation.soja_storage_info_ids
    native_storage_infos = exploitation.soja_stock_quant_ids.filtered("soja_cooperative_partner_id")
    treatment_infos = exploitation.soja_treatment_info_ids
    bank_infos = exploitation.soja_bank_info_ids
    if role == "cooperative" and role_partner:
        native_storage_infos = native_storage_infos.filtered(lambda item: item.soja_cooperative_partner_id == role_partner)
        storage_infos = storage_infos.filtered(lambda item: item.cooperative_partner_id == role_partner) if not native_storage_infos else request.env["soja.storage.info"]
    elif role == "factory" and role_partner:
        treatment_infos = treatment_infos.filtered(lambda item: item.factory_partner_id == role_partner)
    elif role == "bank" and role_partner:
        bank_infos = bank_infos.filtered(lambda item: item.soja_bank_partner_id == role_partner)
    return {
        "id": exploitation.id,
        "uid": exploitation.api_identifier or str(exploitation.id),
        "name": exploitation.name or "",
        "zone": exploitation.soja_zone or "",
        "areaHa": exploitation.soja_area_ha or None,
        "centroid": {"lon": exploitation.soja_centroid_lon or None, "lat": exploitation.soja_centroid_lat or None},
        "points": [{"lon": point.longitude, "lat": point.latitude} for point in exploitation.soja_point_ids],
        "storageInfos": ([{
            "id": item.id,
            "cooperativeId": item.soja_cooperative_partner_id.id,
            "cooperativeName": item.soja_cooperative_partner_id.name,
            "type": item.soja_storage_type or "",
            "quantityT": item.quantity,
            "date": _date(item.soja_storage_date),
            "note": item.soja_storage_note or "",
        } for item in native_storage_infos] if native_storage_infos else [{
            "id": item.id,
            "cooperativeId": item.cooperative_partner_id.id,
            "cooperativeName": item.cooperative_partner_id.name,
            "type": item.storage_type,
            "quantityT": item.quantity_t,
            "date": _date(item.date),
            "note": item.note or "",
        } for item in storage_infos]),
        "treatmentInfos": [{
            "id": item.id,
            "factoryId": item.factory_partner_id.id,
            "factoryName": item.factory_partner_id.name,
            "storageInfoId": item.soja_storage_source_id.id if item.soja_storage_source_id else None,
            "storageInfoLabel": item.soja_storage_source_id.soja_cooperative_partner_id.name if item.soja_storage_source_id else "",
            "dehull": item.soja_dehull,
            "grind": item.soja_grind,
            "date": _date(item.soja_process_date),
            "note": item.soja_process_note or "",
        } for item in treatment_infos],
        "bankInfos": [{
            "id": item.id,
            "bankId": item.soja_bank_partner_id.id,
            "bankName": item.soja_bank_partner_id.name,
            "borrowerType": item.soja_borrower_type or "",
            "borrowerName": item.soja_borrower_name or "",
            "requestedAmount": item.soja_requested_amount or None,
            "approvedAmount": item.soja_approved_amount or None,
            "riskLevel": RISK_FROM_ODOO.get(item.soja_risk_level, item.soja_risk_level or ""),
            "status": item.stage_id.name if item.stage_id else item.soja_decision_status or "",
            "date": _date(item.soja_decision_date),
            "note": item.soja_financing_note or "",
        } for item in bank_infos],
    }


def _serialize_harvest(harvest, role=None):
    if not harvest:
        return None
    stock_type = harvest.stock_type or ""
    stock_qty_t = harvest.stock_qty_t or None
    stock_date = _date(harvest.stock_date)
    stock_note = harvest.stock_note or ""
    factory_dehull = harvest.factory_dehull
    factory_grind = harvest.factory_grind
    factory_process_date = _date(harvest.factory_process_date)
    factory_process_note = harvest.factory_process_note or ""
    bank_loan = {
        "borrowerType": harvest.bank_borrower_type or "",
        "borrowerName": harvest.bank_borrower_name or "",
        "requestedAmount": harvest.bank_requested_amount or None,
        "approvedAmount": harvest.bank_approved_amount or None,
        "riskLevel": RISK_FROM_ODOO.get(harvest.bank_risk_level, harvest.bank_risk_level or ""),
        "status": harvest.bank_status or "",
        "decisionDate": _date(harvest.bank_decision_date),
        "note": harvest.bank_note or "",
    }
    role_partner = _role_partner(role)
    crm_bank_infos = harvest.exploitation_id.soja_bank_info_ids if harvest.exploitation_id else request.env["crm.lead"]
    if role == "bank" and role_partner:
        crm_bank_infos = crm_bank_infos.filtered(lambda item: item.soja_bank_partner_id == role_partner)
    crm_bank_info = crm_bank_infos[:1]
    if crm_bank_info:
        crm_bank_info = crm_bank_info[0]
        bank_loan = {
            "borrowerType": crm_bank_info.soja_borrower_type or "",
            "borrowerName": crm_bank_info.soja_borrower_name or "",
            "requestedAmount": crm_bank_info.soja_requested_amount or None,
            "approvedAmount": crm_bank_info.soja_approved_amount or None,
            "riskLevel": RISK_FROM_ODOO.get(crm_bank_info.soja_risk_level, crm_bank_info.soja_risk_level or ""),
                "status": crm_bank_info.stage_id.name if crm_bank_info.stage_id else crm_bank_info.soja_decision_status or "",
            "decisionDate": _date(crm_bank_info.soja_decision_date),
            "note": crm_bank_info.soja_financing_note or "",
        }
    if role_partner and harvest.exploitation_id and role == "factory":
        treatment = harvest.exploitation_id.soja_treatment_info_ids.filtered(
            lambda item: item.factory_partner_id == role_partner
        )[:1]
        if treatment:
            treatment = treatment[0]
            factory_dehull = treatment.soja_dehull
            factory_grind = treatment.soja_grind
            factory_process_date = _date(treatment.soja_process_date)
            factory_process_note = treatment.soja_process_note or ""
    if role_partner and harvest.exploitation_id and role == "bank":
        bank_info = harvest.exploitation_id.soja_bank_info_ids.filtered(
            lambda item: item.soja_bank_partner_id == role_partner
        )[:1]
        if bank_info:
            bank_info = bank_info[0]
            bank_loan = {
                "borrowerType": bank_info.soja_borrower_type or "",
                "borrowerName": bank_info.soja_borrower_name or "",
                "requestedAmount": bank_info.soja_requested_amount or None,
                "approvedAmount": bank_info.soja_approved_amount or None,
                "riskLevel": RISK_FROM_ODOO.get(bank_info.soja_risk_level, bank_info.soja_risk_level or ""),
                "status": bank_info.soja_decision_status or "",
                "decisionDate": _date(bank_info.soja_decision_date),
                "note": bank_info.soja_financing_note or "",
            }
    if role == "cooperative":
        cooperative = _role_partner(role)
        storage = harvest.exploitation_id.soja_stock_quant_ids.filtered(
            lambda item: item.soja_cooperative_partner_id == cooperative
        )[:1] if cooperative and harvest.exploitation_id else request.env["stock.quant"]
        if storage:
            storage = storage[0]
            stock_type = storage.soja_storage_type or ""
            stock_qty_t = storage.quantity or None
            stock_date = _date(storage.soja_storage_date)
            stock_note = storage.soja_storage_note or ""
    return {
        "id": harvest.id,
        "exploitationId": harvest.exploitation_id.id if harvest.exploitation_id else None,
        "exploitationName": harvest.exploitation_id.name if harvest.exploitation_id else "",
        "stockPickingId": harvest.stock_picking_id.id if harvest.stock_picking_id else None,
        "stockPickingName": harvest.stock_picking_id.name if harvest.stock_picking_id else "",
        "campaign": harvest.campaign or "",
        "seedDate": _date(harvest.seed_date),
        "harvestForecastDate": _date(harvest.harvest_forecast_date),
        "harvestActualDate": _date(harvest.harvest_actual_date),
        "forecastT": harvest.forecast_t or None,
        "actualT": harvest.actual_t or None,
        "yieldTha": harvest.yield_tha or None,
        "actualYieldTha": harvest.actual_yield_tha or None,
        "shareStatus": harvest.share_status or "partners",
        "services": {
            "drone": harvest.service_drone,
            "soil": harvest.service_soil,
            "training": harvest.service_training,
            "finance": harvest.service_finance,
        },
        "stock": {
            "type": stock_type,
            "qtyT": stock_qty_t,
            "date": stock_date,
            "note": stock_note,
        },
        "factoryProcess": {
            "dehull": factory_dehull,
            "grind": factory_grind,
            "date": factory_process_date,
            "note": factory_process_note,
        },
        "bankLoan": bank_loan,
    }


def _serialize_producer(producer, role=None):
    producer_sudo = producer.sudo()
    exploitation = _primary_exploitation(producer_sudo)
    exploitation_values = _serialize_exploitation(exploitation, role=role) if exploitation else {}
    harvests = producer_sudo.soja_harvest_ids.sorted(key=lambda item: (item.write_date or item.create_date, item.id), reverse=True)
    return {
        "id": producer_sudo.id,
        "externalId": producer_sudo.soja_external_id,
        "createdAt": producer_sudo.create_date.isoformat() if producer_sudo.create_date else None,
        "name": producer_sudo.name,
        "zone": producer_sudo.soja_zone or "",
        "coop": producer_sudo.soja_cooperative_id.name or producer_sudo.soja_coop or "",
        "soy": SOY_FROM_ODOO.get(producer_sudo.soja_soy, producer_sudo.soja_soy or ""),
        "tenure": TENURE_FROM_ODOO.get(producer_sudo.soja_tenure, producer_sudo.soja_tenure or ""),
        "phone": producer_sudo.phone or "",
        "email": producer_sudo.email or "",
        "fertilizer": FERTILIZER_FROM_ODOO.get(producer_sudo.soja_fertilizer, producer_sudo.soja_fertilizer or ""),
        "pesticide": PESTICIDE_FROM_ODOO.get(producer_sudo.soja_pesticide, producer_sudo.soja_pesticide or ""),
        "department": producer_sudo.soja_department or "",
        "coopPresident": producer_sudo.soja_coop_president or "",
        "coopPresidentPhone": producer_sudo.soja_coop_president_phone or "",
        "creditOngoing": YESNO_FROM_ODOO.get(producer_sudo.soja_credit_ongoing, producer_sudo.soja_credit_ongoing or ""),
        "sex": SEX_FROM_ODOO.get(producer_sudo.soja_sex, producer_sudo.soja_sex or ""),
        "age": producer_sudo.soja_age or None,
        "identityPhoto": f"/web/image/res.partner/{producer_sudo.id}/soja_identity_photo" if producer_sudo.soja_identity_photo else "",
        "exploitations": [_serialize_exploitation(item, role=role) for item in producer_sudo.soja_exploitation_ids],
        "points": exploitation_values.get("points") or [{"lon": point.longitude, "lat": point.latitude} for point in producer_sudo.soja_point_ids],
        "areaHa": producer_sudo.soja_total_area_ha or exploitation_values.get("areaHa") or producer_sudo.soja_area_ha or None,
        "centroid": exploitation_values.get("centroid") or {"lon": producer_sudo.soja_centroid_lon or None, "lat": producer_sudo.soja_centroid_lat or None},
        "harvest": _serialize_harvest(harvests[:1], role=role),
        "harvests": [_serialize_harvest(item, role=role) for item in harvests],
    }


def _producer_values(payload, role=None):
    cooperative = _soja_company(payload.get("coop"), "cooperative")
    values = {
        "is_soja_producer": True,
        "soja_external_id": _str(payload.get("externalId")) or f"SOJA-{request.env['ir.sequence'].next_by_code('base.partner.root') or ''}",
        "name": _str(payload.get("name")),
        "soja_zone": _str(payload.get("zone")),
        "soja_coop": _str(payload.get("coop")),
        "soja_cooperative_id": cooperative.id if cooperative else False,
        "soja_soy": SOY_TO_ODOO.get(payload.get("soy"), "conventional"),
        "soja_tenure": TENURE_TO_ODOO.get(payload.get("tenure"), "owner"),
        "phone": _str(payload.get("phone")),
        "email": _str(payload.get("email")),
        "soja_fertilizer": FERTILIZER_TO_ODOO.get(payload.get("fertilizer")) or False,
        "soja_pesticide": PESTICIDE_TO_ODOO.get(payload.get("pesticide")) or False,
        "soja_department": _str(payload.get("department")),
        "soja_coop_president": _str(payload.get("coopPresident")),
        "soja_coop_president_phone": _str(payload.get("coopPresidentPhone")),
        "soja_credit_ongoing": YESNO_TO_ODOO.get(payload.get("creditOngoing")) or False,
        "soja_sex": SEX_TO_ODOO.get(payload.get("sex")) or False,
        "soja_age": int(payload.get("age") or 0),
    }
    if role == "producer":
        values["soja_user_id"] = request.env.user.id
    return values


def _payload_exploitations(payload):
    exploitations = payload.get("exploitations")
    if isinstance(exploitations, list) and exploitations:
        return exploitations
    return [{
        "id": payload.get("exploitationId"),
        "name": payload.get("exploitationName") or payload.get("zone") or "Exploitation SOJA",
        "zone": payload.get("zone"),
        "areaHa": payload.get("areaHa"),
        "centroid": payload.get("centroid") or {},
        "points": payload.get("points") or [],
    }]


def _sync_exploitations(producer, payload):
    Exploitation = request.env["soja.exploitation"].sudo()
    existing_exploitations = producer.soja_exploitation_ids
    kept_ids = []
    for index, item in enumerate(_payload_exploitations(payload), start=1):
        name = _str(item.get("name")) or "Exploitation SOJA %s - %s" % (producer.name, index)
        values = {
            "name": name,
            "producer_id": producer.id,
            "zone": _str(item.get("zone")) or producer.soja_zone,
        }
        exploitation = Exploitation.search([
            ("id", "=", item.get("id") or 0),
            ("producer_id", "=", producer.id),
        ], limit=1)
        if exploitation:
            exploitation.write(values)
        else:
            exploitation = Exploitation.create(values)
        kept_ids.append(exploitation.id)
        points = item.get("points") or []
        exploitation.soja_point_ids.unlink()
        for point_index, point in enumerate(points, start=1):
            if point.get("lon") is not None and point.get("lat") is not None:
                request.env["soja.plot.point"].sudo().create({
                    "partner_id": producer.id,
                    "exploitation_id": exploitation.id,
                    "sequence": point_index,
                    "longitude": point.get("lon"),
                    "latitude": point.get("lat"),
                })
        exploitation._update_osm_zone_from_centroid()
    removed_exploitations = existing_exploitations.filtered(lambda item: item.id not in kept_ids)
    for exploitation in removed_exploitations:
        if exploitation.soja_harvest_ids:
            exploitation.active = False
        else:
            exploitation.unlink()
    producer.invalidate_recordset(["soja_exploitation_ids"])
    return producer.soja_exploitation_ids.filtered(lambda item: item.id in kept_ids)[:1] or producer.soja_exploitation_ids[:1]


def _harvest_values(payload, producer, role="manager"):
    harvest = payload.get("harvest") or {}
    services = harvest.get("services") or {}
    stock = harvest.get("stock") or {}
    factory = harvest.get("factoryProcess") or {}
    bank = harvest.get("bankLoan") or {}
    factory_partner = _soja_company(factory.get("partnerName") or factory.get("name"), "factory")
    bank_partner = _soja_company(bank.get("partnerName") or bank.get("bankName") or bank.get("name"), "bank")
    exploitation = _find_payload_exploitation(producer, harvest)
    area = exploitation.soja_area_ha
    yield_tha = _float(harvest.get("yieldTha"))
    actual_yield = _float(harvest.get("actualYieldTha")) or yield_tha
    values = {
        "partner_id": producer.id,
        "exploitation_id": exploitation.id if exploitation else False,
        "cooperative_partner_id": producer.soja_cooperative_id.id if producer.soja_cooperative_id else False,
        "factory_partner_id": factory_partner.id if factory_partner else False,
        "bank_partner_id": bank_partner.id if bank_partner else False,
        "campaign": _str(harvest.get("campaign")) or "2025 - 2026",
        "seed_date": harvest.get("seedDate") or False,
        "harvest_forecast_date": harvest.get("harvestForecastDate") or False,
        "harvest_actual_date": harvest.get("harvestActualDate") or False,
        "yield_tha": yield_tha,
        "actual_yield_tha": actual_yield if harvest.get("harvestActualDate") or harvest.get("actualT") else False,
        "forecast_t": _float(harvest.get("forecastT")) or ((area or 0) * yield_tha if yield_tha else False),
        "actual_t": _float(harvest.get("actualT")) or ((area or 0) * actual_yield if actual_yield and harvest.get("harvestActualDate") else False),
        "share_status": harvest.get("shareStatus") or "partners",
        "service_drone": bool(services.get("drone")),
        "service_soil": bool(services.get("soil")),
        "service_training": bool(services.get("training")),
        "service_finance": bool(services.get("finance")),
        "stock_type": stock.get("type") or False,
        "stock_qty_t": _float(stock.get("qtyT")),
        "stock_date": stock.get("date") or False,
        "stock_note": _str(stock.get("note")),
        "factory_dehull": bool(factory.get("dehull")),
        "factory_grind": bool(factory.get("grind")),
        "factory_process_date": factory.get("date") or False,
        "factory_process_note": _str(factory.get("note")),
        "bank_borrower_type": bank.get("borrowerType") if bank.get("borrowerType") in ("producer", "buyer", "cooperative", "group") else False,
        "bank_borrower_name": _str(bank.get("borrowerName")),
        "bank_requested_amount": _float(bank.get("requestedAmount")),
        "bank_approved_amount": _float(bank.get("approvedAmount")),
        "bank_risk_level": RISK_TO_ODOO.get(bank.get("riskLevel")) or False,
        "bank_status": _str(bank.get("status")),
        "bank_decision_date": bank.get("decisionDate") or False,
        "bank_note": _str(bank.get("note")),
    }
    if role == "producer":
        return _filter_values(values, PRODUCER_HARVEST_KEYS)
    if role in PARTNER_HARVEST_KEYS:
        return _filter_values(values, PARTNER_HARVEST_KEYS[role])
    return values


def _upsert_harvest(producer, payload, role="manager"):
    if "harvest" not in payload:
        return
    harvest_payload = payload.get("harvest") or {}
    values = _harvest_values(payload, producer, role=role)
    forecast_keys = {"seedDate", "harvestForecastDate", "forecastT", "yieldTha"}
    actual_keys = {"harvestActualDate", "actualT", "actualYieldTha"}
    if actual_keys.intersection(harvest_payload) and not forecast_keys.intersection(harvest_payload):
        values = {
            key: values[key]
            for key in ("partner_id", "exploitation_id", "harvest_actual_date", "actual_yield_tha", "actual_t")
            if key in values
        }
    elif forecast_keys.intersection(harvest_payload) and not actual_keys.intersection(harvest_payload):
        values = {
            key: values[key]
            for key in (
                "partner_id", "exploitation_id", "campaign", "seed_date",
                "harvest_forecast_date", "yield_tha", "forecast_t", "share_status",
                "service_drone", "service_soil", "service_training", "service_finance",
            )
            if key in values
        }
    harvest_id = harvest_payload.get("id")
    try:
        harvest_id = int(harvest_id or 0)
    except (TypeError, ValueError):
        harvest_id = 0
    exploitation = _find_payload_exploitation(producer, harvest_payload)
    harvest = producer.soja_harvest_ids.filtered(lambda h: h.id == harvest_id)[:1]
    if harvest and exploitation and harvest.exploitation_id != exploitation:
        harvest = request.env["soja.harvest"]
    if not harvest and exploitation:
        harvest = producer.soja_harvest_ids.filtered(lambda h: h.exploitation_id == exploitation)[:1]
    if not harvest and role not in ("manager", "producer") and not harvest_payload.get("exploitationId"):
        harvest = _latest_harvest(producer)
    if harvest:
        harvest.write(values)
    else:
        harvest = request.env["soja.harvest"].create(values)
    if role in ("manager", "producer") and actual_keys.intersection(harvest_payload) and harvest.exploitation_id and harvest.harvest_actual_date:
        harvest.sudo().action_validate_stock_receipt()
    elif role in ("manager", "producer") and forecast_keys.intersection(harvest_payload) and harvest.exploitation_id:
        harvest.sudo().action_create_stock_receipt()
        harvest.sudo().action_record_forecast_history()


def _harvest_from_request(producer):
    harvest_id = request.params.get("harvest_id")
    exploitation_id = request.params.get("exploitation_id")
    try:
        harvest_id = int(harvest_id or 0)
    except (TypeError, ValueError):
        harvest_id = 0
    try:
        exploitation_id = int(exploitation_id or 0)
    except (TypeError, ValueError):
        exploitation_id = 0
    harvests = producer.soja_harvest_ids
    if harvest_id:
        harvest = harvests.filtered(lambda item: item.id == harvest_id)[:1]
        if harvest:
            return harvest
    if exploitation_id:
        harvest = harvests.filtered(lambda item: item.exploitation_id.id == exploitation_id)[:1]
        if harvest:
            return harvest
    return harvests[:1]


def _delete_forecast_stock_picking(harvest):
    picking = harvest.stock_picking_id
    if not picking:
        return
    if picking.state == "done":
        return
    if picking.state != "cancel":
        picking.action_cancel()
    picking.unlink()


class SojaAppController(http.Controller):
    @http.route("/soja/login", type="http", auth="public", methods=["GET", "POST"], csrf=False)
    def soja_login(self, **post):
        dbname = _request_db()
        if request.httprequest.method == "POST":
            login = _str(post.get("login")).lower()
            password = post.get("password") or ""
            if request.session.uid:
                request.session.logout(keep_db=True)
            try:
                request.session.authenticate(dbname, login, password)
            except AccessDenied:
                return _auth_page("login", "Email ou mot de passe incorrect.", {"login": login})
            return request.redirect("/soja")
        if request.session.uid:
            request.session.logout(keep_db=True)
        return _auth_page("login")

    @http.route("/soja/logout", type="http", auth="public", methods=["GET"], csrf=False)
    def soja_logout(self, **_kwargs):
        request.session.logout(keep_db=True)
        return request.redirect("/soja/login")

    @http.route("/soja/register", type="http", auth="public", methods=["GET", "POST"], csrf=False)
    def soja_register(self, **post):
        return request.redirect("/soja/login")
        if request.session.uid:
            return request.redirect("/soja")
        if request.httprequest.method == "POST":
            role = post.get("role")
            name = _str(post.get("name"))
            login = _str(post.get("login")).lower()
            password = post.get("password") or ""
            confirm_password = post.get("confirm_password") or ""
            values = {"role": role, "name": name, "login": login}
            if role not in REGISTERABLE_ROLES:
                return _auth_page("register", "Choisissez un type d'utilisateur valide.", values)
            if not name or not login or not password:
                return _auth_page("register", "Tous les champs sont obligatoires.", values)
            if password != confirm_password:
                return _auth_page("register", "Les mots de passe ne correspondent pas.", values)
            Users = request.env["res.users"].sudo()
            if Users.search_count([("login", "=", login)]):
                return _auth_page("register", "Un compte existe déjà avec cet email.", values)
            group_ids = [
                request.env.ref("base.group_portal").id,
                request.env.ref(ROLE_GROUPS[role]).id,
            ]
            user = Users.with_context(no_reset_password=True).create({
                "name": name,
                "login": login,
                "email": login,
                "groups_id": [(6, 0, group_ids)],
            })
            user.with_context(no_reset_password=True).write({"password": password})
            request.env.cr.commit()
            request.session.authenticate(_request_db(), login, password)
            return request.redirect("/soja")
        return _auth_page("register")

    @http.route("/soja", type="http", auth="public", website=True, sitemap=True)
    def soja_app(self, **_kwargs):
        if not request.session.uid:
            return request.redirect("/soja/login")
        if not _current_role():
            return request.redirect("/web")
        return request.render("soja_management.website_soja_app_page", {"asset_version": ASSET_VERSION})

    @http.route("/soja/sw.js", type="http", auth="public", methods=["GET"], csrf=False)
    def soja_service_worker(self, **_kwargs):
        script = """
const CACHE_NAME = "soja-offline-%s";
const APP_SHELL = [
  "/soja/",
  "/soja",
  "/soja_management/static/src/css/soja_app.css?v=%s",
  "/soja_management/static/src/js/soja_app.js?v=%s",
];

function sameOrigin(url) {
  return new URL(url).origin === self.location.origin;
}

function cacheSuccessfulResponse(request, response) {
  if (!response || !response.ok) return response;
  const clone = response.clone();
  caches.open(CACHE_NAME).then((cache) => cache.put(request, clone)).catch(() => {});
  return response;
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || !sameOrigin(request.url)) return;
  const url = new URL(request.url);
  if (request.mode === "navigate" || url.pathname === "/soja" || url.pathname === "/soja/") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put("/soja/", clone)).catch(() => {});
          return response;
        })
        .catch(() => caches.match("/soja/").then((cached) => cached || caches.match("/soja")))
    );
    return;
  }
  event.respondWith(
    fetch(request)
      .then((response) => cacheSuccessfulResponse(request, response))
      .catch(() => caches.match(request))
  );
});
""" % (ASSET_VERSION, ASSET_VERSION, ASSET_VERSION)
        return _js_response(script)

    @http.route("/soja/api/session", type="http", auth="user", methods=["GET"], csrf=False)
    def session(self, **_kwargs):
        role = _current_role()
        if not role:
            return _json_error("Aucun rôle SOJA n'est attribué à cet utilisateur.")
        return request.make_json_response(_session_payload())

    @http.route("/soja/api/reverse-geocode", type="http", auth="user", methods=["GET"], csrf=False)
    def reverse_geocode(self, **kwargs):
        role = _current_role()
        if not role:
            return _json_error("Aucun rôle SOJA n'est attribué à cet utilisateur.")
        try:
            latitude = float(kwargs.get("lat"))
            longitude = float(kwargs.get("lon"))
        except (TypeError, ValueError):
            return request.make_json_response({"error": "Coordonnées GPS invalides."}, status=400)
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return request.make_json_response({"error": "Coordonnées GPS hors limites."}, status=400)
        situation = request.env["soja.exploitation"]._reverse_geocode_osm(latitude, longitude)
        if not situation:
            return request.make_json_response({"error": "Situation OpenStreetMap indisponible."}, status=502)
        return request.make_json_response({"situation": situation})

    @http.route("/soja/api/exploitations/<string:exploitation_ref>/points", type="http", auth="user", methods=["GET", "POST", "PUT"], csrf=False)
    def exploitation_points(self, exploitation_ref, **_kwargs):
        role = _current_role()
        if not role:
            return _json_error("Aucun rôle SOJA n'est attribué à cet utilisateur.")
        write_request = request.httprequest.method in ("POST", "PUT")
        exploitation = _exploitation_for_access(exploitation_ref, role, write=write_request)
        if not exploitation:
            return request.make_json_response({"error": "Exploitation introuvable ou non autorisée."}, status=404)
        if request.httprequest.method == "GET":
            return request.make_json_response(_serialize_exploitation(exploitation, role=role))
        payload = _body()
        mode = payload.get("mode") or "replace"
        if mode not in ("replace", "append"):
            return _json_error("Mode invalide. Utilisez replace ou append.", status=400)
        try:
            points = _gps_points_from_payload(payload)
        except ValidationError as error:
            return _json_error(error.args[0] if error.args else "Points GPS invalides.", status=400)
        Point = request.env["soja.plot.point"].sudo()
        if mode == "replace":
            exploitation.soja_point_ids.unlink()
        start_sequence = max(exploitation.soja_point_ids.mapped("sequence") or [0]) if mode == "append" else 0
        for index, point in enumerate(points, start=1):
            Point.create({
                "partner_id": exploitation.producer_id.id,
                "exploitation_id": exploitation.id,
                "sequence": point["sequence"] if mode == "replace" else start_sequence + index,
                "longitude": point["longitude"],
                "latitude": point["latitude"],
                "osm_situation": point["osm_situation"],
            })
        exploitation._update_osm_zone_from_centroid()
        return request.make_json_response(_serialize_exploitation(exploitation, role=role))

    @http.route("/soja/api/producers", type="http", auth="user", methods=["GET", "POST"], csrf=False)
    def producers(self, **_kwargs):
        role = _current_role()
        if not role:
            return _json_error("Aucun rôle SOJA n'est attribué à cet utilisateur.")
        Producer = request.env["res.partner"]
        try:
            if request.httprequest.method == "GET":
                return request.make_json_response({"results": [_serialize_producer(producer, role=role) for producer in Producer.search(_producer_domain(role))]})
            if not _can_create_producer(role):
                return _json_error("Création de producteur non autorisée pour ce rôle.")
            payload = _body()
            if not payload.get("name"):
                return request.make_json_response({"error": "Le nom du producteur est obligatoire."}, status=400)
            producer = Producer.create(_producer_values(payload, role=role))
            _sync_exploitations(producer, payload)
            _upsert_harvest(producer, payload, role=role)
            return request.make_json_response(_serialize_producer(producer, role=role), status=201)
        except AccessError as error:
            return request.make_json_response({"error": error.args[0] if error.args else "Accès Odoo refusé."}, status=403)

    @http.route("/soja/api/producers/<int:producer_id>", type="http", auth="user", methods=["GET", "PUT", "DELETE"], csrf=False)
    def producer_detail(self, producer_id, **_kwargs):
        role = _current_role()
        if not role:
            return _json_error("Aucun rôle SOJA n'est attribué à cet utilisateur.")
        try:
            if request.httprequest.method == "GET":
                producer = request.env["res.partner"].search([("id", "=", producer_id), ("is_soja_producer", "=", True)], limit=1)
            else:
                producer = _producer_for_access(producer_id, role)
            if not producer:
                return request.make_json_response({"error": "Producteur introuvable."}, status=404)
            if request.httprequest.method == "GET":
                return request.make_json_response(_serialize_producer(producer, role=role))
            if request.httprequest.method == "DELETE":
                if role != "manager":
                    return _json_error("Suppression réservée au gestionnaire.")
                producer.unlink()
                return request.make_json_response({})
            payload = _body()
            if role in ("cooperative", "factory", "bank"):
                _upsert_harvest(producer, payload, role=role)
                return request.make_json_response(_serialize_producer(producer, role=role))
            if "harvest" in payload and "name" not in payload:
                _upsert_harvest(producer, payload, role=role)
                return request.make_json_response(_serialize_producer(producer, role=role))
            if not payload.get("name"):
                return request.make_json_response({"error": "Le nom du producteur est obligatoire."}, status=400)
            producer.write(_producer_values(payload, role=role))
            _sync_exploitations(producer, payload)
            _upsert_harvest(producer, payload, role=role)
            return request.make_json_response(_serialize_producer(producer, role=role))
        except AccessError as error:
            return request.make_json_response({"error": error.args[0] if error.args else "Accès Odoo refusé."}, status=403)

    @http.route("/soja/api/producers/<int:producer_id>/operations", type="http", auth="user", methods=["POST"], csrf=False)
    def producer_operation(self, producer_id, **_kwargs):
        role = _current_role()
        if role not in ("cooperative", "factory", "bank"):
            return _json_error("Cette saisie est réservée aux utilisateurs partenaires.")
        producer = _producer_for_access(producer_id, role)
        partner = _role_partner(role)
        payload = _body()
        if not producer or not partner:
            return request.make_json_response({"error": "Ce compte n'est pas rattaché à un partenaire Odoo."}, status=403)
        operation = payload.get("operation")
        operation_models = {
            "storage": ("stock.quant", "soja_cooperative_partner_id", "storageId", "cooperative"),
            "treatment": ("mrp.production", "factory_partner_id", "treatmentId", "factory"),
            "bank": ("crm.lead", "soja_bank_partner_id", "bankId", "bank"),
        }
        operation_config = operation_models.get(operation)
        if not operation_config or operation_config[3] != role:
            return _json_error("Type d'opération partenaire non reconnu.", status=400)
        model_name, partner_field, record_key, _ = operation_config
        operation_mode = payload.get("mode") or ("update" if payload.get("storageId") else "create")
        if operation != "storage":
            operation_mode = payload.get("mode") or ("update" if payload.get(record_key) else "create")
        if operation_mode not in ("create", "update"):
            return _json_error("Mode d'enregistrement invalide.", status=400)
        try:
            exploitation_id = int(payload.get("exploitationId") or 0)
        except (TypeError, ValueError):
            exploitation_id = 0
        exploitation = request.env["soja.exploitation"].sudo().search([
            ("id", "=", exploitation_id),
            ("producer_id", "=", producer.id),
        ], limit=1)
        if not exploitation:
            return _json_error("Exploitation introuvable pour ce producteur.", status=400)
        harvest = request.env["soja.harvest"].sudo().browse(int(payload.get("harvestId") or 0)).exists()
        if not harvest or harvest.exploitation_id != exploitation:
            harvest = exploitation.soja_harvest_ids[:1]
        if not harvest:
            return _json_error("Aucune campagne de récolte n'est liée à cette exploitation.", status=400)
        Operation = request.env[model_name].sudo()
        exploitation_field = "soja_exploitation_id" if operation in ("storage", "treatment", "bank") else "exploitation_id"
        record = Operation.search([
            ("id", "=", int(payload.get(record_key) or 0)),
            (exploitation_field, "=", exploitation.id),
            (partner_field, "=", partner.id),
        ], limit=1) if operation_mode == "update" else Operation.browse()
        if operation_mode == "update" and not record:
            return _json_error("La ligne sélectionnée est introuvable.", status=404)
        values = payload.get("storage" if operation == "storage" else "treatment" if operation == "treatment" else "bank") or {}
        if operation == "storage":
            operation_values = {
                "product_id": harvest.product_id.id,
                "location_id": _cooperative_stock_location(partner).id,
                "company_id": _cooperative_stock_location(partner).company_id.id or request.env.company.id,
                partner_field: partner.id,
                "soja_harvest_id": int(payload.get("harvestId") or 0) or False,
                "quantity": _float(values.get("quantityT", values.get("qtyT"))),
                "soja_storage_type": values.get("type") or "partial",
                "soja_storage_date": values.get("date") or False,
                "soja_storage_note": _str(values.get("note")),
            }
        elif operation == "treatment":
            operation_values = {
                "soja_partner_id": producer.id,
                "soja_exploitation_id": exploitation.id,
                partner_field: partner.id,
                "soja_harvest_id": int(payload.get("harvestId") or 0) or False,
                "soja_storage_source_id": int(values.get("storageInfoId") or 0) or False,
                "soja_dehull": bool(values.get("dehull")),
                "soja_grind": bool(values.get("grind")),
                "soja_process_date": values.get("date") or False,
                "soja_process_note": _str(values.get("note")),
            }
            if operation_mode == "create":
                source = request.env["stock.quant"].sudo().browse(operation_values["soja_storage_source_id"])
                product_qty = source.quantity if source.exists() else (harvest.actual_t or harvest.forecast_t or 1.0)
                operation_values.update({
                    "product_id": harvest.transformed_product_id.id,
                    "product_qty": max(product_qty, 0.0001),
                    "product_uom_id": harvest.transformed_product_id.uom_id.id,
                    "company_id": request.env.company.id,
                })
        else:
            operation_values = {
                "name": "Financement SOJA - %s" % exploitation.name,
                "soja_harvest_id": int(payload.get("harvestId") or 0) or False,
                "soja_exploitation_id": exploitation.id,
                "soja_partner_id": producer.id,
                partner_field: partner.id,
                "description": _str(values.get("note")),
                "soja_borrower_type": values.get("borrowerType") or False,
                "soja_borrower_name": _str(values.get("borrowerName")),
                "soja_requested_amount": _float(values.get("requestedAmount")),
                "soja_approved_amount": _float(values.get("approvedAmount")),
                "soja_risk_level": RISK_TO_ODOO.get(values.get("riskLevel"), values.get("riskLevel") or False),
                "soja_decision_status": _str(values.get("status")),
                "soja_decision_date": values.get("date") or False,
                "soja_financing_note": _str(values.get("note")),
            }
            stage = _crm_stage_for_status(values.get("status"))
            if stage:
                operation_values["stage_id"] = stage.id
        try:
            if record:
                record.write(operation_values)
            else:
                record = Operation.create(operation_values)
        except ValidationError as error:
            return _json_error(error.args[0] if error.args else "La quantité stockée est invalide.", status=400)
        return request.make_json_response(_serialize_producer(producer, role=role))

    @http.route("/soja/api/producers/<int:producer_id>/operations", type="http", auth="user", methods=["DELETE"], csrf=False)
    def delete_producer_operation(self, producer_id, **_kwargs):
        role = _current_role()
        if role not in ("cooperative", "factory", "bank"):
            return _json_error("Cette suppression est réservée aux utilisateurs partenaires.")
        producer = _producer_for_access(producer_id, role)
        partner = _role_partner(role)
        if not producer or not partner:
            return request.make_json_response({"error": "Ce compte n'est pas rattaché à un partenaire Odoo."}, status=403)
        try:
            operation = request.params.get("operation")
            operation_id = int(request.params.get("operation_id") or 0)
            exploitation_id = int(request.params.get("exploitation_id") or 0)
        except (TypeError, ValueError):
            return _json_error("Ligne invalide.", status=400)
        operation_models = {
            "storage": ("stock.quant", "soja_cooperative_partner_id", "cooperative"),
            "treatment": ("mrp.production", "factory_partner_id", "factory"),
            "bank": ("crm.lead", "soja_bank_partner_id", "bank"),
        }
        config = operation_models.get(operation)
        if not config or config[2] != role:
            return _json_error("Type d'opération partenaire invalide.", status=400)
        Operation = request.env[config[0]].sudo()
        exploitation_field = "soja_exploitation_id" if operation in ("storage", "treatment", "bank") else "exploitation_id"
        record = Operation.search([
            ("id", "=", operation_id),
            (exploitation_field, "=", exploitation_id),
            (exploitation_field + ".producer_id", "=", producer.id),
            (config[1], "=", partner.id),
        ], limit=1)
        if not record:
            return _json_error("Ligne de stockage introuvable.", status=404)
        record.unlink()
        return request.make_json_response(_serialize_producer(producer, role=role))

    @http.route("/soja/api/producers/<int:producer_id>/harvest", type="http", auth="user", methods=["DELETE"], csrf=False)
    def producer_harvest(self, producer_id, **_kwargs):
        role = _current_role()
        if role != "manager":
            return _json_error("Suppression réservée au gestionnaire.")
        producer = _producer_for_access(producer_id, role)
        if not producer:
            return request.make_json_response({"error": "Producteur introuvable."}, status=404)
        harvest = _harvest_from_request(producer)
        if harvest:
            _delete_forecast_stock_picking(harvest)
            harvest.unlink()
        return request.make_json_response(_serialize_producer(producer, role=role))

    @http.route("/soja/api/producers/<int:producer_id>/harvest/actual", type="http", auth="user", methods=["DELETE"], csrf=False)
    def producer_actual_harvest(self, producer_id, **_kwargs):
        role = _current_role()
        if role not in ("manager", "producer"):
            return _json_error("Suppression de récolte non autorisée pour ce rôle.")
        producer = _producer_for_access(producer_id, role)
        if not producer:
            return request.make_json_response({"error": "Producteur introuvable."}, status=404)
        harvest = _harvest_from_request(producer)
        if harvest:
            harvest.write({"harvest_actual_date": False, "actual_t": False, "actual_yield_tha": False})
        return request.make_json_response(_serialize_producer(producer, role=role))
