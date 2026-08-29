import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property var categories: []
    property var values: ({})
    signal changed(var values)
    Text { text: "Installed defaults"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
    Repeater { model: root.categories
        RowLayout { required property var modelData; visible: modelData.id !== "agent"
            Text { Layout.fillWidth: true; text: modelData.label || modelData.id; color: Color.foreground; font.family: Style.font.family }
            Ui.Dropdown { value: root.values[modelData.id] || ""; options: [""].concat((modelData.choices || []).filter(function(item) { return item.state === "available" }).map(function(item) { return item.id })); onChanged: function(value) { var next=JSON.parse(JSON.stringify(root.values)); if (value) next[modelData.id]=value; else delete next[modelData.id]; root.changed(next) } }
        }
    }
}
