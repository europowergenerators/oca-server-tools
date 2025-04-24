# Copyright 2016-2017 Versada <https://versada.eu/>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import warnings
from collections import abc
from urllib.parse import urlparse

import odoo.http
from odoo import SUPERUSER_ID, api
from odoo.service.server import server
from odoo.tools import config as odoo_config

from . import const
from .logutils import (
    InvalidGitRepository,
    SanitizeOdooCookiesProcessor,
    fetch_git_sha,
    get_extra_context,
)

_logger = logging.getLogger(__name__)
HAS_SENTRY_SDK = True
try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import ignore_logger
    from sentry_sdk.integrations.threading import ThreadingIntegration
    from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware
except ImportError:  # pragma: no cover
    HAS_SENTRY_SDK = False  # pragma: no cover
    _logger.debug(
        "Cannot import 'sentry-sdk'.\
                        Please make sure it is installed."
    )  # pragma: no cover


def before_send(event, hint):
    """Prevent the capture of any exceptions in
    the DEFAULT_IGNORED_EXCEPTIONS list
        -- or --
    Add context to event if include_context is True
    and sanitize sensitive data"""

    exc_info = hint.get("exc_info")
    if exc_info is None and "log_record" in hint:
        # Odoo handles UserErrors by logging the raw exception rather
        # than a message string in odoo/http.py
        try:
            module_name = hint["log_record"].msg.__module__
            class_name = hint["log_record"].msg.__class__.__name__
            qualified_name = module_name + "." + class_name
        except AttributeError:
            qualified_name = "not found"

        if qualified_name in const.DEFAULT_IGNORED_EXCEPTIONS:
            return None

    if event.setdefault("tags", {}).get("include_context", False):
        cxtest = get_extra_context(odoo.http.request)
        info_request = ["tags", "user", "extra", "request"]

        for item in info_request:
            info_item = event.setdefault(item, {})
            info_item.update(cxtest.setdefault(item, {}))

    raven_processor = SanitizeOdooCookiesProcessor()
    raven_processor.process(event)

    return event


def before_send_transaction(event, hint):
    event = before_send(event, hint)

    path = event["transaction"]
    try:
        url = urlparse(event["request"]["url"])
        path = url.path
    except Exception as e:
        _logger.warning("Error parsing url: %s", e)

    event["transaction"] = path
    return event


def get_odoo_commit(odoo_dir):
    """Attempts to get Odoo git commit from :param:odoo_dir."""
    if not odoo_dir:
        return
    try:
        return fetch_git_sha(odoo_dir)
    except InvalidGitRepository:
        _logger.debug("Odoo directory: '%s' not a valid git repository", odoo_dir)


def get_param(env, key, default=None):
    return env["ir.config_parameter"].sudo().get_param(key, default)


def initialize_sentry(config):
    """Setup an instance of :class:sentry_sdk.Client.
    :param config: Sentry configuration
    :param client: class used to instantiate the sentry_sdk client.
    """

    db_name = config.get("db_name")
    registry = odoo.registry(db_name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        def get_config_or_param(key, default=None):
            try:
                return config.get(
                    f"sentry_{key}", get_param(env, f"sentry.sentry_{key}", default)
                )
            except KeyError:
                _logger.warning(
                    f"Configuration parameter {key} not found, using default: {default}"
                )
                return default

        enabled = get_config_or_param("enabled", False)
        if not (HAS_SENTRY_SDK and enabled):
            return
        _logger.info("Initializing sentry...")
        if get_config_or_param("odoo_dir") and get_config_or_param("release"):
            _logger.debug(
                "Both sentry_odoo_dir and \
                           sentry_release defined, choosing sentry_release"
            )
        if get_config_or_param("transport"):
            warnings.warn(
                "sentry_transport has been deprecated.  "
                "Its not neccesary send it, will use HttpTranport by default.",
                DeprecationWarning,
                stacklevel=1,
            )
        options = {}
        for option in const.get_sentry_options():
            value = get_config_or_param(option.key, option.default)
            if isinstance(option.converter, abc.Callable):
                value = option.converter(value)
            options[option.key] = value

        exclude_loggers = const.split_multiple(
            get_config_or_param("exclude_loggers", const.DEFAULT_EXCLUDE_LOGGERS)
        )

        if not get_config_or_param("release"):
            options["release"] = get_config_or_param(
                "release", get_odoo_commit(get_config_or_param("odoo_dir"))
            )

        # Change name ignore_exceptions (with raven)
        # to ignore_errors' (sentry_sdk)
        options["ignore_errors"] = options["ignore_exceptions"]
        del options["ignore_exceptions"]

        options["before_send"] = before_send
        options["before_send_transaction"] = before_send_transaction

        options["integrations"] = [
            options["logging_level"],
            ThreadingIntegration(propagate_hub=True),
        ]
        # Remove logging_level, since in sentry_sdk is include in 'integrations'
        del options["logging_level"]

        debug = config.get("sentry_debug", False)
        if debug:
            options["debug"] = True
            _logger.debug("Sentry debug mode enabled")
            _logger.debug("Initializing Sentry with options: %s", options)

        # options["send_default_pii"] = True
        # options["traces_sample_rate"] = 1
        # options["profile_session_sample_rate"] = 1
        # options["profile_lifecycle"] = "trace"
        client = sentry_sdk.init(**options)

        sentry_sdk.set_tag(
            "include_context", get_config_or_param("include_context", True)
        )

        if exclude_loggers:
            for item in exclude_loggers:
                ignore_logger(item)

        # The server app is already registered so patch it here
        if server:
            server.app = SentryWsgiMiddleware(server.app)

        # https://github.com/hnavarro-kernet/sentry/commit/46fca9dd296f30a090413c1479ca6fd6670e8273
        # XXX: I hate this hack,
        # but I'm not sure how to fix SentryWsgiMiddleware not having
        # methods like session_store that the
        # odoo.http.root has and Odoo calls for them
        # in random places.
        class OdooIntegration(SentryWsgiMiddleware):
            def __init__(self, app, *args, **kwargs):
                super().__init__(app, *args, **kwargs)

            def __getattr__(self, name):
                if hasattr(super(), name):
                    return getattr(super(), name)
                return getattr(self.app, name)

        # Patch the wsgi server in case of further registration
        odoo.http.root = OdooIntegration(odoo.http.root)

        with sentry_sdk.new_scope() as scope:
            scope.set_extra("debug", False)
            sentry_sdk.capture_message("Starting Odoo Server", "info")

        return client


def post_load():
    initialize_sentry(odoo_config)
