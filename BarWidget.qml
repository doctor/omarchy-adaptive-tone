import QtQuick
import qs.Ui as Ui
import qs.Commons
import qs.Commons as Commons

Ui.BarWidget {
  id: root
  moduleName: "io.github.doctor.adaptive-tone"
  // Re-resolve when services register, including after plugin reloads.
  property var toneService: null
  readonly property var telemetry: toneService ? toneService.telemetry : ({ mode: "starting", settings: {} })
  readonly property bool opened: panel.open
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function open() { panel.open = true }
  function close() { panel.open = false }
  function toggle() { panel.open = !panel.open }
  function resume() { if (toneService) toneService.resume() }
  function pause() { if (toneService) toneService.pause() }
  function status() { return JSON.stringify(telemetry) }
  function setWarmth(value) {
    if (toneService) toneService.configure({ minimum_kelvin: Math.max(3500, Math.min(6250, value)) })
  }
  function setSpeed(value) {
    if (toneService) toneService.configure({ smoothing_seconds: value })
  }
  function resolveService() {
    toneService = root.bar && root.bar.shell ? root.bar.shell.serviceFor(root.moduleName) : null
  }
  onBarChanged: resolveService()
  Component.onCompleted: resolveService()
  Timer { interval: 1000; running: true; repeat: true; onTriggered: root.resolveService() }
  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  function modeLabel() {
    if (telemetry.mode === "manual") {
      const minutes = Math.max(0, Math.ceil((telemetry.override_until - Date.now() / 1000) / 60))
      return strings.t("mode.manual").arg(Commons.I18n.formatNumber(minutes))
    }
    return strings.t("mode." + telemetry.mode)
  }
  function number(value, suffix) {
    return typeof value === "number" ? Commons.I18n.formatNumber(Math.round(value)) + suffix : "—"
  }

  Ui.BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.telemetry.mode === "paused" || root.telemetry.mode === "manual" ? "󰏤" : "󰃠"
    slotSize: Style.bar.statusSlot
    tooltipText: ""
    onPressed: function(b) {
      if (b === Qt.RightButton) {
        if (root.telemetry.mode === "automatic") root.pause()
        else root.resume()
      } else root.toggle()
    }
  }

  Ui.KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    focusTarget: keys
    contentWidth: panel.fittedContentWidth(Style.space(330))
    contentHeight: panel.fittedContentHeight(panelContent.implicitHeight)

    Ui.PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) {
        if (root.bar) root.bar.switchPanelFrom(root, direction)
      }
      onTextKey: function(key) {
        if (key === "a") root.resume()
        if (key === "p") root.pause()
      }
      onMoveRequested: function(dx, dy) {
        if (dx) root.setWarmth(root.telemetry.settings.minimum_kelvin + dx * 250)
        if (dy) {
          const speeds = [20, 45, 90]
          const index = Math.max(0, speeds.indexOf(root.telemetry.settings.smoothing_seconds))
          root.setSpeed(speeds[(index + dy + 3) % 3])
        }
      }

      Column {
        id: panelContent
        width: parent.width
        spacing: Style.space(12)

        PlainText { width: parent.width; text: strings.t("title"); font.pixelSize: Style.font.subtitle; font.bold: true }
        PlainText { width: parent.width; text: root.modeLabel(); color: Commons.Color.accent }
        PlainText {
          width: parent.width
          text: strings.t("reading").arg(root.number(root.telemetry.lux, " lx")).arg(root.number(root.telemetry.temperature_kelvin, " K"))
          font.pixelSize: Style.font.heading
        }
        PlainText { width: parent.width; text: strings.t("target").arg(root.number(root.telemetry.target_kelvin, " K")) }

        Row {
          spacing: Style.space(8)
          Ui.Button { text: strings.t("auto"); selected: root.telemetry.mode === "automatic"; focusable: true; onClicked: root.resume() }
          Ui.Button { text: strings.t("pause"); selected: root.telemetry.mode === "paused"; focusable: true; onClicked: root.pause() }
        }

        PlainText { width: parent.width; text: strings.t("warmth").arg(root.number(root.telemetry.settings.minimum_kelvin, " K")) }
        Row {
          spacing: Style.space(8)
          Ui.Button { text: strings.t("warmer"); focusable: true; onClicked: root.setWarmth(root.telemetry.settings.minimum_kelvin - 250) }
          Ui.Button { text: strings.t("cooler"); focusable: true; onClicked: root.setWarmth(root.telemetry.settings.minimum_kelvin + 250) }
        }

        PlainText { width: parent.width; text: strings.t("speed") }
        Row {
          spacing: Style.space(6)
          Ui.Button { text: strings.t("responsive"); selected: root.telemetry.settings.smoothing_seconds === 20; focusable: true; onClicked: root.setSpeed(20) }
          Ui.Button { text: strings.t("gentle"); selected: root.telemetry.settings.smoothing_seconds === 45; focusable: true; onClicked: root.setSpeed(45) }
          Ui.Button { text: strings.t("slow"); selected: root.telemetry.settings.smoothing_seconds === 90; focusable: true; onClicked: root.setSpeed(90) }
        }

        PlainText { width: parent.width; visible: !!root.telemetry.error; text: root.telemetry.error || ""; font.pixelSize: Style.font.bodySmall }
        PlainText { width: parent.width; text: strings.t("explanation"); font.pixelSize: Style.font.bodySmall }
        PlainText { width: parent.width; text: strings.t("shortcuts"); font.pixelSize: Style.font.bodySmall }
      }
    }
  }
}
