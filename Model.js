// Validate worker telemetry before it reaches UI bindings. No rich-text sinks.
function finite(value, low, high) {
  return typeof value === "number" && isFinite(value) && value >= low && value <= high
}

function parseState(line) {
  if (typeof line !== "string" || line.length > 16384) return null
  var data
  try { data = JSON.parse(line) } catch (_) { return null }
  if (!data || typeof data !== "object" || Array.isArray(data)) return null
  if (["starting", "automatic", "manual", "paused", "error"].indexOf(data.mode) === -1) return null
  var config = data.settings && typeof data.settings === "object" ? data.settings : {}
  return {
    mode: data.mode,
    lux: finite(data.lux, 0, 200000) ? data.lux : null,
    temperature_kelvin: finite(data.temperature_kelvin, 1000, 20000) ? data.temperature_kelvin : null,
    target_kelvin: finite(data.target_kelvin, 3500, 6500) ? data.target_kelvin : null,
    override_until: finite(data.override_until, 0, 1e12) ? data.override_until : 0,
    error: typeof data.error === "string" ? data.error.slice(0, 300) : "",
    settings: {
      minimum_kelvin: finite(config.minimum_kelvin, 3500, 6250) ? config.minimum_kelvin : 5000,
      smoothing_seconds: finite(config.smoothing_seconds, 1, 86400) ? config.smoothing_seconds : 45
    }
  }
}

if (typeof module !== "undefined") module.exports = { parseState: parseState }
