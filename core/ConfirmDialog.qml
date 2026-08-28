import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Item {
    id: root

    property bool opened: false
    property string title: "Confirm change"
    property string message: ""
    property string itemName: ""
    property bool requireTypedName: itemName !== ""
    property string typedName: ""
    property bool acknowledged: false
    readonly property bool confirmationEnabled: requireTypedName ? typedName === itemName : acknowledged

    signal canceled()
    signal confirmed()

    visible: opened

    function open() {
        typedName = ""
        acknowledged = false
        opened = true
        Qt.callLater(function() {
            if (requireTypedName) nameField.forceActiveFocus()
            else acknowledgeSwitch.forceActiveFocus()
        })
    }

    function close() { opened = false }

    Rectangle {
        anchors.fill: parent
        color: Color.menu.scrim
    }

    MouseArea {
        anchors.fill: parent
        onClicked: {
            root.close()
            root.canceled()
        }
    }

    Ui.BorderSurface {
        id: card
        anchors.centerIn: parent
        width: Math.min(parent.width - Style.spacing.panelPadding * 2, Style.space(460))
        implicitHeight: form.implicitHeight + Style.spacing.panelPadding * 2
        color: Color.popups.background
        radius: Style.cornerRadius
        borderSpec: Border.localOrSurfaceSpec("popups", "border", Color.popups.border, Color.popups.border, Style.normalBorderWidth)

        MouseArea { anchors.fill: parent; onClicked: mouse.accepted = true }

        ColumnLayout {
            id: form
            anchors.fill: parent
            anchors.margins: Style.spacing.panelPadding
            spacing: Style.spacing.panelGap

            Text {
                Layout.fillWidth: true
                text: root.title
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.heading
                font.bold: true
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                text: root.message
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.body
                wrapMode: Text.WordWrap
            }
            Ui.TextField {
                id: nameField
                Layout.fillWidth: true
                visible: root.requireTypedName
                placeholderText: root.itemName
                text: root.typedName
                onTextChanged: root.typedName = text
                onAccepted: if (root.confirmationEnabled) confirmButton.clicked()
            }
            RowLayout {
                Layout.fillWidth: true
                visible: !root.requireTypedName
                spacing: Style.spacing.md
                Ui.ToggleSwitch {
                    id: acknowledgeSwitch
                    checked: root.acknowledged
                    onToggled: root.acknowledged = !root.acknowledged
                }
                Text {
                    Layout.fillWidth: true
                    text: "I understand this change cannot be reversed automatically."
                    color: Color.popups.text
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                }
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: Style.spacing.md
                Ui.Button {
                    text: "Cancel"
                    bordered: true
                    focusable: true
                    onClicked: {
                        root.close()
                        root.canceled()
                    }
                }
                Ui.Button {
                    id: confirmButton
                    text: "Confirm"
                    bordered: true
                    focusable: true
                    enabled: root.confirmationEnabled
                    onClicked: {
                        root.close()
                        root.confirmed()
                    }
                }
            }
        }
    }

    Keys.onEscapePressed: {
        root.close()
        root.canceled()
    }
}
