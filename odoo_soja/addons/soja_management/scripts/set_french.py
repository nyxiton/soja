Lang = env["res.lang"].sudo()
Users = env["res.users"].sudo().with_context(active_test=False)

Lang._activate_lang("fr_FR")
lang = Lang.search([("code", "=", "fr_FR")], limit=1)
if lang and not lang.active:
    lang.active = True

env["base.language.install"].sudo().create({
    "lang_ids": [(6, 0, lang.ids)],
    "overwrite": True,
}).lang_install()

partners = Users.search([]).mapped("partner_id")
partners.write({"lang": "fr_FR"})

env["ir.default"].sudo().set("res.partner", "lang", "fr_FR")
if "website" in env:
    websites = env["website"].sudo().search([])
    websites.write({
        "default_lang_id": lang.id,
        "language_ids": [(4, lang.id)],
    })
env.cr.commit()

print("Odoo language set to fr_FR")
print("Updated users:", len(partners))
