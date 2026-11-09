import QtQuick
import Quickshell.Io
import qs.Commons
import "Model.js" as Model

Item {
  id: root
  property var shell: null
  property var manifest: null
  property var telemetry: ({ mode: "starting", error: "", settings: {} })
  readonly property bool running: worker.running
  property bool destroying: false
  property string queuedControl: ""

  function send(action, values) {
    const message = JSON.stringify({ action: action, values: values || {} }) + "\n"
    if (!worker.running) {
      queuedControl = message
      worker.running = true
      return
    }
    worker.write(message)
  }
  function pause() { send("pause") }
  function resume() { send("resume") }
  function configure(values) { send("settings", values) }

  Process {
    id: worker
    command: ["python", decodeURIComponent(Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, "")), "run"]
    stdinEnabled: true
    onStarted: {
      if (root.queuedControl !== "") {
        worker.write(root.queuedControl)
        root.queuedControl = ""
      }
    }
    stdout: SplitParser {
      onRead: function(line) {
        var parsed = Model.parseState(line)
        if (parsed) root.telemetry = parsed
      }
    }
    onExited: function(code) {
      if (!root.destroying && code !== 0 && root.telemetry.mode !== "error")
        root.telemetry = { mode: "error", error: "The tone worker stopped", settings: {} }
    }
  }
  ShellIpc {
    target: "io.github.doctor.adaptive-tone"
    function status(): string { return JSON.stringify(root.telemetry) }
    function pause(): string { root.pause(); return "ok" }
    function resume(): string { root.resume(); return "ok" }
    function configure(values: string): string {
      try {
        const data = JSON.parse(values)
        if (!data || typeof data !== "object" || Array.isArray(data)) return "invalid"
        root.configure(data)
        return "ok"
      } catch (_) { return "invalid" }
    }
  }
  Component.onCompleted: worker.running = true
  Component.onDestruction: {
    destroying = true
    if (worker.running) worker.signal(15)
  }
}
