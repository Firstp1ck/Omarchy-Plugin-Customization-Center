import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

FocusScope {
    id: root
    property var bar: ({})
    property var barOptions: []
    property var centerIds: []
    property bool busy: false
    signal optionChanged(string key, var value)
    implicitHeight: row.implicitHeight
    function focusFirst() { barDropdown.forceActiveFocus() }
    RowLayout {
        id: row; anchors.fill: parent; spacing: Style.spacing.panelGap
        Ui.Dropdown { id: barDropdown; objectName: "barSelector"; Layout.preferredWidth: 210; enabled: !root.busy; value: root.bar.id || "omarchy.bar"; options: root.barOptions; onChanged: value => root.optionChanged("id", value === "omarchy.bar" ? null : value) }
        Ui.Dropdown { id: position; objectName: "positionSelector"; enabled: !root.busy; value: root.bar.position || "top"; options: ["top", "bottom", "left", "right"]; onChanged: value => root.optionChanged("position", value) }
        Ui.ToggleSwitch { id: transparent; objectName: "transparencyToggle"; enabled: !root.busy; checked: root.bar.transparent === true; onToggled: root.optionChanged("transparent", !checked) }
        Ui.Dropdown { id: anchor; objectName: "anchorSelector"; enabled: !root.busy; value: root.bar.centerAnchor || ""; options: [""].concat(root.centerIds); onChanged: value => root.optionChanged("centerAnchor", value) }
    }
}
