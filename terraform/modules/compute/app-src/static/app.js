(function () {
  "use strict";

  var root = document.getElementById("status-root");
  if (!root) { return; }

  var REFRESH_MS = 15000;
  var endpoint = root.getAttribute("data-endpoint");

  function field(name) { return root.querySelector('[data-field="' + name + '"]'); }
  function setText(name, value) {
    var el = field(name);
    if (el) { el.textContent = value; }
  }

  function render(data) {
    var db = data.database || {};
    var badge = field("db-badge");
    if (badge) {
      badge.textContent = db.connected ? "Connected" : "Unavailable";
      badge.className = "badge " + (db.connected ? "badge-ok" : "badge-bad");
    }
    setText("db-version", db.connected ? db.engine + " " + db.version : "\u2013");
    setText("db-tls", db.connected ? (db.tls ? "TLS \u00b7 " + db.cipher : "Not encrypted") : "\u2013");
    setText("db-latency", db.connected ? db.latency_ms + " ms" : "\u2013");
    setText("db-products", db.connected ? db.products + " products" : "\u2013");
    var app = data.application || {};
    setText("app-az", app.az || "unknown");
    setText("app-instance", app.instance_id || "unknown");
    setText("app-runtime", app.runtime || "unknown");
  }

  function refresh() {
    fetch(endpoint, { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (response) { return response.json(); })
      .then(render)
      .catch(function () { /* keep the last known values; the next tick retries */ });
  }

  window.setInterval(refresh, REFRESH_MS);
})();
