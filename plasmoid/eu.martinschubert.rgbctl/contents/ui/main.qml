import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // Path to the CLI. Change here if the folder moves.
    readonly property string rgbctl: "/home/martin/Documents/Claude/RGB Widget/rgbctl.py"

    property var devices: []          // from `rgbctl.py status --json`
    property var globalEffects: []    // from `rgbctl.py effects --json`
    property int globalIndex: 1       // selected global effect (1 = Static once loaded)
    property string lastAllColor: ""
    readonly property var globalEffect: globalEffects[globalIndex] || { id: "static", name: "Static", color: true }
    property var chosenColor: ({})    // device id -> "#rrggbb" picked in this widget
    property int busy: 0
    property string lastError: ""
    property int seq: 0
    // Per-device section expanded or collapsed; saved in the widget's config.
    property bool showDevices: Plasmoid.configuration.showDevices
    onShowDevicesChanged: Plasmoid.configuration.showDevices = showDevices

    readonly property var swatches: ["#ff0000", "#ff8000", "#ffff00", "#00ff00", "#00ffff",
                                     "#0000ff", "#8000ff", "#ff00ff", "#ffffff"]

    Plasmoid.icon: "preferences-desktop-color"
    toolTipMainText: "RGB Lighting"
    toolTipSubText: devices.map(d => d.name + ": " + stateText(d)).join("\n")
    switchWidth: Kirigami.Units.gridUnit * 14
    switchHeight: Kirigami.Units.gridUnit * 14

    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        property var callbacks: ({})
        onNewData: (source, data) => {
            const cb = callbacks[source]
            delete callbacks[source]
            disconnectSource(source)
            root.busy = Math.max(0, root.busy - 1)
            if (cb) cb(data["stdout"] || "", data["stderr"] || "", data["exit code"])
        }
    }

    function quote(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'" }

    function run(args, cb) {
        // The trailing comment keeps identical commands from being merged by the engine.
        const cmd = "python3 " + quote(rgbctl) + " " + args.map(quote).join(" ") + " #" + (++seq)
        exec.callbacks[cmd] = cb
        busy += 1
        exec.connectSource(cmd)
    }

    function mergeStates(list) {
        const byId = {}
        for (const d of devices) byId[d.id] = d
        for (const d of list) byId[d.id] = d
        devices = Object.values(byId)
        const errs = list.filter(d => d.error).map(d => (d.name || d.id) + ": " + d.error)
        lastError = errs.join("\n")
    }

    function handle(out, err) {
        try {
            mergeStates(JSON.parse(out))
        } catch (e) {
            lastError = (err || out || String(e)).trim()
        }
    }

    function refresh() {
        if (globalEffects.length === 0) {
            run(["effects", "--json"], (out) => {
                try {
                    globalEffects = JSON.parse(out)
                    globalIndex = Math.max(0, globalEffects.findIndex(e => e.id === "static"))
                } catch (e) { }
            })
        }
        run(["status", "--json"], handle)
    }
    function setDevice(id, effect, color) {
        const args = ["set", id, effect]
        if (color) args.push(color)
        args.push("--json")
        run(args, handle)
    }
    function setAll(color) {
        // Applies the selected global effect; colour only for effects that use one.
        const eff = globalEffect
        if (eff.color && color) {
            lastAllColor = color
            const c = {}
            for (const d of devices) c[d.id] = color
            chosenColor = c
            setDevice("all", eff.id, color)
        } else if (!eff.color) {
            setDevice("all", eff.id, "")
        }
    }

    function effectOf(d, id) { return (d.effects || []).find(e => e.id === id) }
    function stateText(d) {
        if (d.error) return "error"
        if (!d.state) return "unknown"
        const e = effectOf(d, d.state.effect)
        let t = e ? e.name : (d.state.effect || "unknown")
        if (d.state.color) t += " " + d.state.color
        if (d.state.note) t += " (" + d.state.note + ")"
        return t
    }

    // PC3.ComboBox pads with the theme frame's `margins`, which shrink while the item is still
    // smaller than the frame (as on popup creation) and cause implicitWidth/implicitHeight
    // binding loops. `fixedMargins` don't depend on the size; the height leaves out the
    // background's implicit height, which has the same problem.
    component StableComboBox: PC3.ComboBox {
        implicitHeight: Math.max(implicitContentHeight, implicitIndicatorHeight) + topPadding + bottomPadding
        readonly property var frameMargins: background && background.item && background.item.fixedMargins
                                            ? background.item.fixedMargins : null
        readonly property real arrowSpace: indicator && indicator.visible ? spacing + indicator.implicitWidth : 0
        topPadding: frameMargins ? frameMargins.top : 0
        bottomPadding: frameMargins ? frameMargins.bottom : 0
        leftPadding: (frameMargins ? frameMargins.left : 0) + (mirrored ? arrowSpace : 0)
        rightPadding: (frameMargins ? frameMargins.right : 0) + (mirrored ? 0 : arrowSpace)
    }

    Component.onCompleted: refresh()
    onExpandedChanged: if (root.expanded) refresh()

    ColorDialog {
        id: colorDialog
        property string target: "all"   // "all" or a device id
        property string effect: "static"
        title: target === "all" ? "Colour for all devices" : "Colour"
        onAccepted: {
            const hex = selectedColor.toString().slice(0, 7)
            if (target === "all") {
                root.setAll(hex)
            } else {
                const c = Object.assign({}, root.chosenColor); c[target] = hex; root.chosenColor = c
                root.setDevice(target, effect, hex)
            }
        }
    }

    compactRepresentation: MouseArea {
        onClicked: root.expanded = !root.expanded
        Kirigami.Icon {
            anchors.fill: parent
            source: "preferences-desktop-color"
            active: parent.containsMouse
        }
        hoverEnabled: true
    }

    fullRepresentation: PlasmaExtras.Representation {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        Layout.preferredWidth: Kirigami.Units.gridUnit * 22
        Layout.minimumHeight: content.implicitHeight + Kirigami.Units.largeSpacing * 2

        ColumnLayout {
            id: content
            anchors.fill: parent
            anchors.margins: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                Kirigami.Heading { level: 4; text: "All devices"; Layout.fillWidth: true }
                PC3.BusyIndicator { running: root.busy > 0; visible: running
                    implicitWidth: Kirigami.Units.iconSizes.small; implicitHeight: implicitWidth }
                PC3.ToolButton { icon.name: "view-refresh"; onClicked: root.refresh()
                    PC3.ToolTip.text: "Read current state"; PC3.ToolTip.visible: hovered }
            }

            RowLayout {
                Layout.fillWidth: true
                PC3.Label { text: "Effect:" }
                StableComboBox {
                    Layout.fillWidth: true
                    model: root.globalEffects
                    textRole: "name"
                    currentIndex: root.globalIndex
                    onActivated: (i) => {
                        root.globalIndex = i
                        const e = root.globalEffects[i]
                        // Effects without colour apply at once; colour effects reuse the last
                        // colour if there is one, otherwise wait for a swatch click.
                        if (!e.color) root.setAll("")
                        else if (root.lastAllColor) root.setAll(root.lastAllColor)
                    }
                }
            }
            PC3.Label {
                visible: root.globalEffect.id === "rainbow"
                Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.7
                font: Kirigami.Theme.smallFont
                text: "G815 shows this as wave, the G Pro as colour cycle."
            }

            Flow {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                enabled: root.globalEffect.color
                opacity: enabled ? 1 : 0.35
                Repeater {
                    model: root.swatches
                    delegate: Rectangle {
                        required property string modelData
                        width: Kirigami.Units.gridUnit * 1.6; height: width; radius: width / 4
                        color: modelData
                        border.color: Kirigami.Theme.textColor; border.width: swatchMouse.containsMouse ? 2 : 0.5
                        MouseArea { id: swatchMouse; anchors.fill: parent; hoverEnabled: true
                            onClicked: root.setAll(parent.modelData) }
                    }
                }
            }
            RowLayout {
                PC3.Button { text: "Custom…"; icon.name: "color-picker"
                    enabled: root.globalEffect.color
                    onClicked: { colorDialog.target = "all"; colorDialog.effect = "static"; colorDialog.open() } }
                PC3.Button { text: "All off"; icon.name: "system-shutdown"
                    onClicked: root.setDevice("all", "off", "") }
            }
            PC3.Label {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.7
                font: Kirigami.Theme.smallFont
                text: "The ASUS logo only has red, green, blue, cyan, magenta and yellow; it uses the closest. Corsair breathing uses its own colours."
            }

            Kirigami.Separator { Layout.fillWidth: true }

            // Collapse toggle for the per-device settings; the "All devices" part stays visible.
            MouseArea {
                Layout.fillWidth: true
                implicitHeight: devicesHeader.implicitHeight
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.showDevices = !root.showDevices
                RowLayout {
                    id: devicesHeader
                    anchors.fill: parent
                    Kirigami.Heading { level: 4; text: "Devices"; Layout.fillWidth: true }
                    PC3.Label { visible: !root.showDevices; opacity: 0.7; text: root.devices.length + " hidden" }
                    PC3.ToolButton {
                        icon.name: root.showDevices ? "arrow-up" : "arrow-down"
                        onClicked: root.showDevices = !root.showDevices
                        PC3.ToolTip.text: root.showDevices ? "Hide device settings" : "Show device settings"
                        PC3.ToolTip.visible: hovered
                    }
                }
            }

            Repeater {
                model: root.showDevices ? root.devices : []
                delegate: ColumnLayout {
                    id: devRow
                    required property var modelData
                    readonly property var dev: modelData
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    RowLayout {
                        Rectangle {
                            width: Kirigami.Units.gridUnit; height: width; radius: width / 2
                            color: devRow.dev.state && devRow.dev.state.color ? devRow.dev.state.color : "transparent"
                            border.color: Kirigami.Theme.textColor; border.width: 0.5
                        }
                        PC3.Label { text: devRow.dev.name || devRow.dev.id; font.bold: true }
                        PC3.Label { text: root.stateText(devRow.dev); opacity: 0.7
                            elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    RowLayout {
                        visible: !!devRow.dev.effects
                        StableComboBox {
                            id: effectBox
                            Layout.fillWidth: true
                            model: devRow.dev.effects || []
                            textRole: "name"
                            currentIndex: Math.max(0, (devRow.dev.effects || []).findIndex(
                                e => devRow.dev.state && e.id === devRow.dev.state.effect))
                            onActivated: (i) => {
                                const e = devRow.dev.effects[i]
                                const c = e.color ? (root.chosenColor[devRow.dev.id]
                                          || (devRow.dev.state && devRow.dev.state.color) || "#ff0000") : ""
                                root.setDevice(devRow.dev.id, e.id, c)
                            }
                        }
                        PC3.Button {
                            readonly property var eff: (devRow.dev.effects || [])[effectBox.currentIndex]
                            enabled: !!eff && eff.color
                            icon.name: "color-picker"
                            text: "Colour…"
                            onClicked: {
                                colorDialog.target = devRow.dev.id
                                colorDialog.effect = eff.id
                                colorDialog.selectedColor = root.chosenColor[devRow.dev.id]
                                    || (devRow.dev.state && devRow.dev.state.color) || "#ff0000"
                                colorDialog.open()
                            }
                        }
                    }
                    Flow {
                        // Fixed palettes (ASUS): pick one directly.
                        visible: !!devRow.dev.palette
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Repeater {
                            model: devRow.dev.palette ? Object.keys(devRow.dev.palette) : []
                            delegate: Rectangle {
                                required property string modelData
                                width: Kirigami.Units.gridUnit * 1.2; height: width; radius: width / 4
                                color: modelData
                                border.color: Kirigami.Theme.textColor
                                border.width: devRow.dev.state && devRow.dev.state.color === modelData ? 2 : 0.5
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: {
                                        const e = (devRow.dev.effects || [])[effectBox.currentIndex]
                                        const eid = e && e.color ? e.id : "static"
                                        const c = Object.assign({}, root.chosenColor); c[devRow.dev.id] = parent.modelData
                                        root.chosenColor = c
                                        root.setDevice(devRow.dev.id, eid, parent.modelData)
                                    }
                                }
                            }
                        }
                    }
                    PC3.Label {
                        visible: !!devRow.dev.error
                        text: devRow.dev.error || ""
                        color: Kirigami.Theme.negativeTextColor
                        wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                }
            }

            PC3.Label {
                visible: root.lastError !== ""
                text: root.lastError
                color: Kirigami.Theme.negativeTextColor
                wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Item { Layout.fillHeight: true }
        }
    }
}
