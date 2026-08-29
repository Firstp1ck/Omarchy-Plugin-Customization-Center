import QtQuick
import QtQuick.Layouts
import qs.Commons
import "." as Bar

FocusScope {
    id: root
    objectName: "barPreview"
    property var bar: ({ layout: ({ left: [], center: [], right: [] }), position: "top", transparent: false })
    property var catalog: []
    property string selectedKey: ""
    signal selected(string key)
    signal moveRequested(string key, string section, int index)
    signal removeRequested(string key)
    readonly property bool vertical: bar.position === "left" || bar.position === "right"
    implicitHeight: 260
    Rectangle { anchors.fill: parent; color: Color.background; border.color: Color.muted; border.width: Style.normalBorderWidth }
    Text { anchors.centerIn: parent; text: "All monitors"; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
    Rectangle {
        id: strip
        color: Color.background; opacity: bar.transparent ? 0.55 : 1
        border.color: Color.accent; border.width: Style.normalBorderWidth
        anchors.left: bar.position !== "right" ? parent.left : undefined
        anchors.right: bar.position !== "left" ? parent.right : undefined
        anchors.top: bar.position !== "bottom" ? parent.top : undefined
        anchors.bottom: bar.position !== "top" ? parent.bottom : undefined
        width: root.vertical ? 86 : parent.width; height: root.vertical ? parent.height : 96
        ColumnLayout {
            anchors.fill: parent; anchors.margins: Style.spacing.md; spacing: Style.spacing.xs
            Bar.BarSection { Layout.fillWidth: true; section: "left"; entries: root.bar.layout ? root.bar.layout.left || [] : []; catalog: root.catalog; selectedKey: root.selectedKey; onSelected: key => root.selected(key); onRemoveRequested: key => root.removeRequested(key); onMoveRequested: (key, section, index) => root.moveRequested(key, section, index) }
            Bar.BarSection { Layout.fillWidth: true; section: "center"; entries: root.bar.layout ? root.bar.layout.center || [] : []; catalog: root.catalog; selectedKey: root.selectedKey; onSelected: key => root.selected(key); onRemoveRequested: key => root.removeRequested(key); onMoveRequested: (key, section, index) => root.moveRequested(key, section, index) }
            Bar.BarSection { Layout.fillWidth: true; section: "right"; entries: root.bar.layout ? root.bar.layout.right || [] : []; catalog: root.catalog; selectedKey: root.selectedKey; onSelected: key => root.selected(key); onRemoveRequested: key => root.removeRequested(key); onMoveRequested: (key, section, index) => root.moveRequested(key, section, index) }
        }
    }
}
