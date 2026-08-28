import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

FormField {
    id: root

    property var field: ({})
    property var values: ({})
    property bool readOnly: false
    readonly property string keyName: String(field.key || "")
    readonly property bool hasValue: values && Object.prototype.hasOwnProperty.call(values, keyName)
    readonly property var effectiveValue: hasValue ? values[keyName] : field.defaultValue
    readonly property string controlKind: String(field.type || "")

    signal valueEdited(string key, var value)
    signal requestDeleteKey(string key)

    label: String(field.label || keyName)
    description: String(field.description || "")
    stateText: hasValue ? "Set" : "Default"

    RowLayout {
        width: parent ? parent.width : implicitWidth
        spacing: Style.spacing.md

        Loader {
            Layout.fillWidth: true
            sourceComponent: {
                switch (root.controlKind) {
                case "boolean": return booleanEditor
                case "integer": return integerEditor
                case "string": return stringEditor
                case "path": return stringEditor
                case "enum": return (root.field.options || []).length > 8 ? searchableEnumEditor : enumEditor
                case "multiselect": return multiselectEditor
                default: return unsupportedEditor
                }
            }
        }

        Ui.Button {
            visible: root.hasValue
            enabled: !root.readOnly
            text: "Remove key"
            tooltipText: "Use the bar file route to remove " + root.keyName
            bordered: true
            focusable: true
            onClicked: root.requestDeleteKey(root.keyName)
        }
    }

    Component {
        id: booleanEditor
        RowLayout {
            Ui.ToggleSwitch {
                checked: Boolean(root.effectiveValue)
                enabled: !root.readOnly
                onToggled: root.valueEdited(root.keyName, !checked)
            }
            Text {
                text: Boolean(root.effectiveValue) ? "On" : "Off"
                color: Color.foreground
                font.family: Style.font.family
                font.pixelSize: Style.font.body
            }
        }
    }

    Component {
        id: integerEditor
        Ui.NumberField {
            value: Number(root.effectiveValue === undefined ? 0 : root.effectiveValue)
            from: root.field.min === undefined ? -2147483647 : Number(root.field.min)
            to: root.field.max === undefined ? 2147483647 : Number(root.field.max)
            stepSize: root.field.step === undefined ? 1 : Number(root.field.step)
            enabled: !root.readOnly
            onModified: function(nextValue) { root.valueEdited(root.keyName, nextValue) }
        }
    }

    Component {
        id: stringEditor
        Ui.TextField {
            width: parent ? parent.width : implicitWidth
            text: root.effectiveValue === undefined ? "" : String(root.effectiveValue)
            placeholderText: root.controlKind === "path" ? "Path" : "Value"
            enabled: !root.readOnly
            onEditingFinished: root.valueEdited(root.keyName, text)
        }
    }

    Component {
        id: enumEditor
        Ui.Dropdown {
            value: root.effectiveValue === undefined ? "" : String(root.effectiveValue)
            options: root.field.options || []
            enabled: !root.readOnly
            onChanged: function(nextValue) { root.valueEdited(root.keyName, nextValue) }
        }
    }

    Component {
        id: searchableEnumEditor
        Ui.SearchableDropdown {
            value: root.effectiveValue === undefined ? "" : String(root.effectiveValue)
            options: root.field.options || []
            enabled: !root.readOnly
            onChanged: function(nextValue) { root.valueEdited(root.keyName, nextValue) }
        }
    }

    Component {
        id: multiselectEditor
        Ui.MultiSelect {
            values: Array.isArray(root.effectiveValue) ? root.effectiveValue : []
            options: root.field.options || []
            placeholderText: root.field.ui && root.field.ui.placeholderText ? root.field.ui.placeholderText : "Search"
            emptyText: root.field.ui && root.field.ui.emptyText ? root.field.ui.emptyText : "No options"
            noSelectionText: root.field.ui && root.field.ui.noSelectionText ? root.field.ui.noSelectionText : "None selected"
            enabled: !root.readOnly
            onChanged: function(nextValues) { root.valueEdited(root.keyName, nextValues) }
        }
    }

    Component {
        id: unsupportedEditor
        Text {
            text: "Unsupported field type: " + root.controlKind
            color: Color.urgent
            font.family: Style.font.family
            font.pixelSize: Style.font.body
        }
    }
}
