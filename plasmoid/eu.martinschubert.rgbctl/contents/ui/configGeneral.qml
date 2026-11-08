import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_rgbctlPath: pathField.text

    Kirigami.FormLayout {
        QQC2.TextField {
            id: pathField
            Kirigami.FormData.label: "rgbctl command:"
            Layout.preferredWidth: Kirigami.Units.gridUnit * 20
            placeholderText: "rgbctl"
        }
        QQC2.Label {
            Layout.preferredWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.WordWrap
            opacity: 0.7
            text: "Leave empty to use rgbctl from PATH or ~/.local/bin (install.sh links it there). Otherwise enter the full path to rgbctl.py."
        }
    }
}
