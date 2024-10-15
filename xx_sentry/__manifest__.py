# Copyright 2016-2017 Versada <https://versada.eu/>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Sentry",
    "summary": "Report Odoo errors to Sentry",
    "version": "17.0.1.0.0",
    "category": "Extra Tools",
    "website": "https://github.com/OCA/server-tools",
    "author": "Mohammed Barsi,"
    "Versada,"
    "Nicolas JEUDY,"
    "Odoo Community Association (OCA),"
    "Vauxoo",
    "maintainers": ["barsi", "naglis", "versada", "moylop260", "fernandahf"],
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "assets": {
        "web.assets_backend": [
            "xx_sentry/static/src/js/sentry_init.js",
        ],
    },
    "external_dependencies": {
        "python": [
            "sentry_sdk<=1.9.0",
        ]
    },
    "depends": [
        "base",
    ],
    "data": [
        "data/config_parameter.xml",
    ],
    "post_load": "post_load",
}
