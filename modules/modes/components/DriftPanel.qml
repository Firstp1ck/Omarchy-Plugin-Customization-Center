import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
    id: root
    property var report: null
    visible: report !== null
    Text { text: report ? "Last applied: " + report.state : ""; color: report && report.state !== "applied" ? Color.urgent : Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
    Text { visible: report && report.definitionChanged; text: "The saved mode definition changed after apply."; color: Color.urgent; font.family: Style.font.family }
    Repeater { model: report ? report.findings || [] : []
        Text { required property var modelData; Layout.fillWidth: true; text: modelData.member + " · " + modelData.field + ": expected " + JSON.stringify(modelData.expected) + ", now " + JSON.stringify(modelData.actual); color: Color.foreground; font.family: Style.font.family; wrapMode: Text.WordWrap }
    }
    Repeater { model: report ? report.indeterminate || [] : []
        Text { required property var modelData; Layout.fillWidth: true; text: modelData.member + ": " + modelData.reason; color: Color.urgent; font.family: Style.font.family; wrapMode: Text.WordWrap }
    }
}
