from odoo import http
from odoo.http import request
from odoo.tools import config


class SentryConfigController(http.Controller):
    @http.route("/sentry/config", auth="user")
    def get_sentry_config(self):
        env = request.env
        dsn = (
            env["ir.config_parameter"]
            .sudo()
            .get_param("sentry.sentry_dsn", config.get("sentry_dsn", None))
        )
        return dsn
