import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami
import org.kde.ksvg as KSvg

PlasmoidItem {
    id: root

    // CLI command: the path from the widget settings, or `rgbctl` from PATH / ~/.local/bin
    // (plasmashell's PATH usually lacks ~/.local/bin, where install.sh links it).
    readonly property string rgbctlPath: Plasmoid.configuration.rgbctlPath.trim()
    readonly property string rgbctlCommand: rgbctlPath === "" ? 'PATH="$HOME/.local/bin:$PATH" rgbctl'
        : (rgbctlPath.endsWith(".py") ? "python3 " + quote(rgbctlPath) : quote(rgbctlPath))

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
    // On the desktop the widget draws its own content-sized background (see fullRepresentation).
    readonly property bool onDesktop: Plasmoid.formFactor === PlasmaCore.Types.Planar
    Plasmoid.backgroundHints: onDesktop ? PlasmaCore.Types.NoBackground : PlasmaCore.Types.DefaultBackground
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
        const cmd = rgbctlCommand + " " + args.map(quote).join(" ") + " #" + (++seq)
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
        deriveGlobal()
    }

    // Sets the global effect and colour from what the devices currently show, so the
    // "All devices" part is right after a restart or after changes made elsewhere.
    function deriveGlobal() {
        const known = devices.filter(d => !d.error && d.state)
        if (known.length === 0 || globalEffects.length === 0) return
        const i = globalEffects.findIndex(g => known.every(d => d.state.effect === (g.devices || {})[d.id]))
        if (i < 0) return   // devices show different effects: keep the current selection
        globalIndex = i
        if (!globalEffects[i].color) return
        // Common colour of the devices that show any colour (not ones with a fixed palette).
        const colors = known.filter(d => !d.palette && d.state.color).map(d => d.state.color.toLowerCase())
        if (colors.length > 0 && colors.every(c => c === colors[0])) lastAllColor = colors[0]
    }

    function handle(out, err, code) {
        if (code === 127) {
            lastError = "rgbctl not found. Run install.sh, or set the path in the widget settings."
            return
        }
        try {
            mergeStates(JSON.parse(out))
        } catch (e) {
            lastError = (err || out || String(e)).trim()
        }
    }

    // Notes for the selected global effect, from the device data: which devices show it
    // differently, use their own colours, or only have a fixed palette.
    readonly property string globalHint: {
        const g = globalEffect
        if (!g.devices) return ""
        const notes = []
        for (const d of devices) {
            if (d.error || !d.effects || !(d.id in g.devices)) continue
            const n = d.name || d.id
            const mapped = g.devices[d.id]
            if (mapped === null) { notes.push(n + " has nothing similar and keeps its effect."); continue }
            const e = effectOf(d, mapped)
            if (mapped !== g.id) notes.push(n + " shows this as " + (e ? e.name : mapped).toLowerCase() + ".")
            if (g.color && e && !e.color) notes.push(n + " uses its own colours.")
            else if (g.color && d.palette)
                notes.push(n + " only has " + Object.values(d.palette).join(", ").toLowerCase() + "; it uses the closest.")
        }
        return notes.join(" ")
    }

    onRgbctlCommandChanged: { globalEffects = []; devices = []; lastError = ""; refresh() }

    function refresh() {
        if (globalEffects.length === 0) {
            run(["effects", "--json"], (out) => {
                try {
                    globalEffects = JSON.parse(out)
                    globalIndex = Math.max(0, globalEffects.findIndex(e => e.id === "static"))
                    deriveGlobal()
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
            const hex = selectedColor.toString().slice(0, 7).toLowerCase()
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
        id: rep
        Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        Layout.preferredWidth: Kirigami.Units.gridUnit * 22
        Layout.minimumHeight: contentFrameHeight
        Layout.preferredHeight: Layout.minimumHeight

        // Height of the content plus padding (and the frame's borders on the desktop).
        readonly property real contentFrameHeight: content.implicitHeight + Kirigami.Units.smallSpacing * 2
            + (root.onDesktop ? ownFrame.margins.top + ownFrame.margins.bottom : 0)

        // On the desktop, Plasma keeps a widget at the size the user gave it and never shrinks
        // it. So the widget draws its own background, sized to the content: collapsing the
        // device section shrinks the visible widget, the rest of the area stays transparent.
        KSvg.FrameSvgItem {
            id: ownFrame
            visible: root.onDesktop
            imagePath: "widgets/background"
            anchors { left: parent.left; right: parent.right; top: parent.top }
            height: rep.contentFrameHeight
        }

        ColumnLayout {
            id: content
            anchors.fill: parent
            anchors.margins: Kirigami.Units.smallSpacing
            anchors.leftMargin: Kirigami.Units.smallSpacing + (root.onDesktop ? ownFrame.margins.left : 0)
            anchors.rightMargin: Kirigami.Units.smallSpacing + (root.onDesktop ? ownFrame.margins.right : 0)
            anchors.topMargin: Kirigami.Units.smallSpacing + (root.onDesktop ? ownFrame.margins.top : 0)
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
                    id: globalBox
                    // Not a binding: a new model resets the index to 0 (Off) after the count
                    // changes, so the selection is put back from root.globalIndex afterwards.
                    function sync() { currentIndex = root.globalIndex }
                    Component.onCompleted: sync()
                    onCountChanged: Qt.callLater(sync)
                    Connections { target: root; function onGlobalIndexChanged() { globalBox.sync() } }
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
                visible: text !== ""
                Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.7
                font: Kirigami.Theme.smallFont
                text: root.globalHint
            }

            Flow {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                enabled: root.globalEffect.color
                opacity: enabled ? 1 : 0.35
                Repeater {
                    // Preset swatches, plus the current colour if it is a custom one.
                    model: root.swatches.concat(root.lastAllColor && root.swatches.indexOf(root.lastAllColor) < 0
                                                ? [root.lastAllColor] : [])
                    delegate: Item {
                        id: swatch
                        required property string modelData
                        readonly property bool selected: root.globalEffect.color && root.lastAllColor === modelData
                        // The selected colour is a bigger swatch. All cells have the big height,
                        // so the smaller swatches stay centred in the row.
                        readonly property real size: Kirigami.Units.gridUnit * (selected ? 2.1 : 1.6)
                        width: size; height: Kirigami.Units.gridUnit * 2.1
                        Rectangle {
                            anchors.centerIn: parent
                            width: swatch.size; height: width
                            radius: width / 4
                            color: swatch.modelData
                            border.color: Kirigami.Theme.textColor
                            border.width: swatch.selected || swatchMouse.containsMouse ? 2 : 0.5
                        }
                        MouseArea { id: swatchMouse; anchors.fill: parent; hoverEnabled: true
                            onClicked: root.setAll(swatch.modelData) }
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
