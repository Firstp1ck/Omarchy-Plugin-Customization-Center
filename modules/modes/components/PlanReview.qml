import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
    id: root
    property var plan: null
    property var commands: []
    spacing: Style.spacing.md
    Text { text: root.plan ? root.plan.summary || "Review mode" : "Review mode"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading }
    Repeater { model: root.plan ? root.plan.segments || [] : []
        ColumnLayout { required property var modelData; Layout.fillWidth: true
            Text { text: modelData.moduleId || modelData.module || ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
            Text { text: (modelData.operationIds || []).join(" · "); color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WrapAnywhere }
        }
    }
    Text { visible: root.plan && (root.plan.operations || []).some(function(item) { return item.kind === "TimedConfirmation" }); Layout.fillWidth: true; text: "Monitors change first. Confirm the layout before later members run."; color: Color.urgent; font.family: Style.font.family; wrapMode: Text.WordWrap }
    Repeater { model: root.commands
        Text { required property var modelData; Layout.fillWidth: true; text: modelData.command || modelData; color: Color.foreground; font.family: Style.font.family; wrapMode: Text.WrapAnywhere }
    }
    Text { Layout.fillWidth: true; text: root.plan ? "Plan digest: " + (root.plan.planDigest || "pending") : ""; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WrapAnywhere }
}
