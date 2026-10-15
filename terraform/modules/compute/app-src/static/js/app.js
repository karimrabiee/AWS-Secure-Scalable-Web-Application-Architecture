(function () {
  "use strict";
  var toast = document.getElementById("toast"), timer;
  function show(message, isError) {
    toast.textContent = message;
    toast.classList.toggle("err", Boolean(isError));
    toast.hidden = false;
    clearTimeout(timer);
    timer = setTimeout(function () { toast.hidden = true; }, 4500);
  }
  document.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-order]");
    if (!button) { return; }
    button.disabled = true;
    fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: parseInt(button.getAttribute("data-order"), 10), quantity: 1 })
    }).then(function (r) {
      return r.json().then(function (b) { return { ok: r.ok, body: b }; });
    }).then(function (res) {
      if (res.ok) {
        show("Order #" + res.body.id + " placed: " + res.body.product + " (" + res.body.total +
          "), handled by " + res.body.served_by + " in " + res.body.az + ".");
      } else {
        show(res.body.error === "database_unavailable" ? "The database is unavailable right now. Please retry." :
          "The order could not be placed.", true);
      }
    }).catch(function () { show("Network error. Please retry.", true); })
      .then(function () { button.disabled = false; });
  });
})();
