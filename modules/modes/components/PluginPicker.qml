import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property var rows: []
    property var enabledMap: ({})
    signal changed(var enabledMap)
    Text { text: "Non-bar plugins"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
    Repeater { model: root.rows
        RowLayout { required property var modelData; visible: (modelData.kinds || []).indexOf("bar") < 0 && (modelData.kinds || []).indexOf("bar-widget") < 0
            Text { Layout.fillWidth: true; text: modelData.name || modelData.id; color: Color.foreground; font.family: Style.font.family }
            Ui.ToggleSwitch { checked: root.enabledMap[modelData.id] === true; onToggled: { var next = JSON.parse(JSON.stringify(root.enabledMap)); next[modelData.id] = checked; root.changed(next) } }
        }
    }
}
