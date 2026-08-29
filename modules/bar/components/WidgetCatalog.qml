import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

FocusScope {
    id: root
    property var catalog: []
    property string filter: ""
    signal addRequested(var item)
    implicitWidth: 250
    function focusFirst() { search.forceActiveFocus() }
    ColumnLayout {
        anchors.fill: parent; spacing: Style.spacing.md
        Ui.TextField { id: search; objectName: "catalogSearch"; Layout.fillWidth: true; text: root.filter; onTextChanged: root.filter = text }
        ListView {
            id: list; objectName: "widgetCatalogList"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: root.catalog
            delegate: FocusScope {
                required property var modelData
                width: ListView.view.width; height: visible ? Style.spacing.controlHeight + Style.spacing.md : 0
                visible: !root.filter || String(modelData.displayName).toLowerCase().indexOf(root.filter.toLowerCase()) >= 0
                activeFocusOnTab: visible
                Keys.onReturnPressed: root.addRequested(modelData)
                Rectangle { anchors.fill: parent; color: parent.activeFocus ? Color.accent : Style.normalFill; border.color: Color.muted; border.width: Style.normalBorderWidth }
                Text { anchors.centerIn: parent; text: modelData.displayName + (modelData.allowMultiple ? "  +" : ""); color: parent.activeFocus ? Color.background : Color.foreground; font.family: Style.font.family }
                MouseArea { anchors.fill: parent; onClicked: root.addRequested(modelData) }
            }
        }
    }
}
