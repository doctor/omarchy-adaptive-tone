import QtQuick
import Quickshell.Io
import "Model.js" as Model

Item {
  id: root
  property var shell: null
  property var manifest: null
  property var telemetry: ({ mode: "starting", error: "", settings: {} })
  readonly property bool running: worker.running
  property bool destroying: false

  function send(action, values) {
    if (!worker.running) {
      worker.running = true
      return
    }
    worker.write(JSON.stringify({ action: action, values: values || {} }) + "\n")
  }
  function pause() { send("pause") }
  function resume() { send("resume") }
  function configure(values) { send("settings", values) }

  Process {
    id: worker
    command: ["python", decodeURIComponent(Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, "")), "run"]
    stdinEnabled: true
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
  Component.onCompleted: worker.running = true
  Component.onDestruction: {
    destroying = true
    if (worker.running) worker.signal(15)
  }
}
