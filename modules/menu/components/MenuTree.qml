import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

FocusScope {
    id: root
    property var effective: ({ order: [], rows: ({}) })
    property string selectedId: ""
    property string filterText: ""
    signal selected(string entryId)
    signal editRequested(string entryId)
    readonly property var visibleIds: {
        var out = []
        var order = effective && effective.order ? effective.order : []
        var rows = effective && effective.rows ? effective.rows : ({})
        var needle = filterText.toLowerCase()
        for (var i = 0; i < order.length; ++i) {
            var row = rows[order[i]]
            if (!needle || String(row.fields.label || row.id).toLowerCase().indexOf(needle) >= 0)
                out.push(order[i])
        }
        return out
    }

    function focusFirst() {
        if (visibleIds.length && !selectedId) selectedId = visibleIds[0]
        list.forceActiveFocus()
    }
    function selectId(entryId) {
        var index = visibleIds.indexOf(entryId)
        if (index >= 0) {
            selectedId = entryId
            list.currentIndex = index
            list.positionViewAtIndex(index, ListView.Contain)
            selected(entryId)
        }
    }

    ListView {
        id: list
        anchors.fill: parent
        clip: true
        focus: true
        model: root.visibleIds
        spacing: Style.spacing.xs
        currentIndex: Math.max(0, root.visibleIds.indexOf(root.selectedId))
        keyNavigationWraps: false
        onCurrentIndexChanged: if (currentIndex >= 0 && currentIndex < root.visibleIds.length) root.selectId(root.visibleIds[currentIndex])
        Keys.onPressed: event => {
            if (event.key === Qt.Key_Home) { currentIndex = 0; event.accepted = true }
            else if (event.key === Qt.Key_End) { currentIndex = count - 1; event.accepted = true }
            else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && root.selectedId) {
                root.editRequested(root.selectedId)
                event.accepted = true
            }
        }

        delegate: Ui.BorderSurface {
            id: rowSurface
            required property string modelData
            readonly property var rowData: root.effective.rows[modelData]
            width: ListView.view.width
            implicitHeight: content.implicitHeight + Style.spacing.md * 2
            color: modelData === root.selectedId ? Style.selectedFill : (mouse.containsMouse || activeFocus ? Style.hoverFill : Style.normalFill)
            radius: Style.cornerRadius
            borderSpec: Border.controlSpec(modelData === root.selectedId ? "selected" : activeFocus ? "focus" : mouse.containsMouse ? "hover" : "normal", Color.foreground, Color.accent)

            RowLayout {
                id: content
                anchors.fill: parent
                anchors.leftMargin: Style.spacing.md + Math.min(32, rowSurface.rowData.depth || 0) * Style.spacing.lg
                anchors.rightMargin: Style.spacing.md
                spacing: Style.spacing.md
                Text { text: rowSurface.rowData.fields.icon || "·"; color: Color.foreground; font.family: rowSurface.rowData.fields.iconFont || Style.font.family; font.pixelSize: Style.font.body }
                Text { Layout.fillWidth: true; text: rowSurface.rowData.fields.label || rowSurface.modelData; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; elide: Text.ElideRight }
                ProvenanceBadge { text: rowSurface.rowData.origin === "injected-root" ? "Root" : rowSurface.rowData.origin.charAt(0).toUpperCase() + rowSurface.rowData.origin.slice(1) }
                ProvenanceBadge { visible: rowSurface.rowData.draftState === "draft"; text: "Draft" }
                ProvenanceBadge { visible: rowSurface.rowData.draftState === "deleted"; text: "Deleted" }
                ProvenanceBadge { visible: rowSurface.rowData.structurallyHidden === true; text: "Hidden: no children" }
                Text { text: rowSurface.rowData.route || ""; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
            }
            MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: { root.selectedId = rowSurface.modelData; root.selected(rowSurface.modelData); list.forceActiveFocus() }
                onDoubleClicked: root.editRequested(rowSurface.modelData)
            }
        }
    }
}
