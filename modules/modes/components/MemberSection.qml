import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property string memberId: ""
    property string title: memberId
    property bool included: false
    property string summary: "Untouched"
    property bool available: true
    property string unavailableReason: ""
    signal inclusionChanged(bool included)
    spacing: Style.spacing.xs
    RowLayout { Layout.fillWidth: true
        Ui.ToggleSwitch { checked: root.included; enabled: root.available; onToggled: root.inclusionChanged(checked) }
        Text { Layout.fillWidth: true; text: root.title; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
        Text { text: root.included ? root.summary : "Untouched"; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
    }
    Text { Layout.fillWidth: true; visible: !root.available; text: root.unavailableReason; color: Color.urgent; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.caption }
}
