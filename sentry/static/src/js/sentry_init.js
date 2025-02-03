/** @odoo-module */

import {session} from "@web/session";

(function () {
    "use strict";

    var script = document.createElement("script");
    script.src = "https://js-de.sentry-cdn.com/1ffe4a061c5d53bf95e3cfb9ff2a6ec7.min.js";
    script.crossOrigin = "anonymous";
    script.onload = function () {
        fetch("/sentry/config", {
            method: "GET",
        })
            .then((response) => response.text())
            .then((text) => {
                if (text) {
                    /* eslint-disable no-undef */
                    Sentry.init({
                        dsn: text,
                        tracesSampleRate: 1,
                    });
                    Sentry.setUser({
                        id: session.uid,
                        username: session.name,
                        email: session.username,
                    });
                    /* eslint-enable no-undef */
                    console.log("Sentry initialized");
                } else {
                    console.error("Sentry DSN not configured or found");
                }
            })
            .catch((error) => {
                console.error("Error fetching Sentry DSN:", error);
            });
    };

    script.onerror = function () {
        alert(
            "To unlock the full potential of this application, you need to disable your add-blocker.\nFor more information, search `disable add-blocker` in the wiki."
        );
    };

    document.head.appendChild(script);
})();
