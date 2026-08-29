import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Item {
    id: root
    property var rows: []
    property string searchText: ""
    property string filter: "All"
    property int selectedIndex: -1
    signal rowActivated(var row)
    implicitHeight: list.contentHeight

    ListView {
        id: list
        anchors.fill: parent
        clip: true
        model: root.rows || []
        spacing: Style.spacing.xs
        delegate: Ui.Button {
            required property var modelData
            required property int index
            width: list.width
            visible: {
                var needle = root.searchText.toLowerCase()
                var textMatches = needle === "" || (String(modelData.display) + " " + String(modelData.description) + " " + String(modelData.arg)).toLowerCase().indexOf(needle) >= 0
                var filterMatches = root.filter === "All"
                    || (root.filter === "Managed" && modelData.classification === "managed")
                    || (root.filter === "Omarchy defaults" && modelData.classification === "omarchy_default")
                    || (root.filter === "Other" && modelData.classification === "external")
                    || (root.filter === "Read-only" && modelData.readOnlyReason)
                    || (root.filter === "Pointer and switches" && modelData.domain !== "keyboard")
                return textMatches && filterMatches
            }
            height: visible ? implicitHeight : 0
            text: String(modelData.display || modelData.keyToken || "Unknown chord") + "  ·  " + String(modelData.description || modelData.dispatcher || "No description")
            leftAlign: true
            focusable: true
            bordered: true
            selected: root.selectedIndex === index
            onClicked: {
                root.selectedIndex = index
                root.rowActivated(modelData)
            }
        }
    }
}
