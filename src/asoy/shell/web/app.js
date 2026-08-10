// Placeholder frontend entry point. Its only job is to prove the shell is wired up:
// it asks Python for the version over the pywebview bridge and reports the outcome.
// See ARCHITECTURE section 4.1 and ADR-018.

(function () {
  "use strict";

  var BRIDGE_TIMEOUT_MS = 5000;
  var answered = false;

  function set(id, text, state) {
    var el = document.getElementById(id);
    if (!el) {
      return;
    }
    el.textContent = text;
    el.className = state || "";
  }

  function onReady() {
    window.pywebview.api
      .get_version()
      .then(function (version) {
        answered = true;
        set("version", version, "ok");
        set("bridge", "reachable", "ok");
        return window.pywebview.api.get_tier();
      })
      .then(function (tier) {
        var label = tier.tier;
        if (tier.device) {
          label += " (" + tier.device;
          if (tier.vram_gib) {
            label += ", " + tier.vram_gib.toFixed(2) + " GiB";
          }
          label += ")";
        }
        set("tier", label, tier.tier === "GPU" ? "ok" : "warn");
        set("tier-reason", tier.reason, "");
        return window.pywebview.api.get_environment();
      })
      .then(function (env) {
        set("environment", env.ok ? "ready" : env.status, env.ok ? "ok" : "warn");
        set("environment-remedy", env.ok ? env.detail : env.detail + " " + env.remedy, "");
      })
      .catch(function (error) {
        answered = true;
        set("bridge", "call failed: " + error, "bad");
      });
  }

  window.addEventListener("pywebviewready", onReady);

  window.setTimeout(function () {
    if (!answered) {
      set("bridge", "not reachable", "bad");
    }
  }, BRIDGE_TIMEOUT_MS);
})();
