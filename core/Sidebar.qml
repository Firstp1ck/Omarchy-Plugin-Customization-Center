import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Item {
    id: root

    property var modules: []
    property string selectedModuleId: ""
    signal selected(string moduleId)

    implicitWidth: Style.space(210)

    ColumnLayout {
        anchors.fill: parent
        spacing: Style.spacing.md

        Text {
            Layout.fillWidth: true
            Layout.leftMargin: Style.spacing.rowPaddingX
            Layout.rightMargin: Style.spacing.rowPaddingX
            text: "Customization Center"
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.heading
            font.bold: true
            wrapMode: Text.WordWrap
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Style.spacing.xs
            clip: true
            model: root.modules
            currentIndex: {
                for (var i = 0; i < root.modules.length; ++i)
                    if (root.modules[i].id === root.selectedModuleId) return i
                return -1
            }
            keyNavigationEnabled: true
            activeFocusOnTab: true

            delegate: Ui.Button {
                required property var modelData
                width: ListView.view.width
                text: modelData.title || modelData.id
                iconText: modelData.icon || ""
                selected: modelData.id === root.selectedModuleId
                hasCursor: ListView.isCurrentItem && list.activeFocus
                focusable: true
                leftAlign: true
                onClicked: root.selected(modelData.id)
            }

            Keys.onReturnPressed: if (currentIndex >= 0) root.selected(root.modules[currentIndex].id)
            Keys.onEnterPressed: if (currentIndex >= 0) root.selected(root.modules[currentIndex].id)
        }
    }
}
