import QtQuick
import QtQuick.Layouts
import qs.Commons
ColumnLayout { id: root; property var palette: ({}); spacing: Style.spacing.sm; Repeater { model: ["Caption", "Body", "Title", "Heading", "Display"]; delegate: Text { required property string modelData; text: modelData; color: root.palette.foreground; font.family: Style.font.family; font.pixelSize: modelData === "Display" ? Style.font.display : modelData === "Heading" ? Style.font.heading : modelData === "Title" ? Style.font.title : modelData === "Caption" ? Style.font.caption : Style.font.body } } }
