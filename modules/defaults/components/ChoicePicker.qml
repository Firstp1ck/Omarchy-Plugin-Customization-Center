import QtQuick
import qs.Commons
import qs.Ui as Ui

FocusScope {
    id: root
    property var choices: []
    property string selector: ""
    property string currentChoice: ""
    property var detailsChoice: null
    signal choicePicked(var choice)

    implicitHeight: pickerColumn.implicitHeight

    function filteredChoices() {
        var result = []
        var needle = search.text.toLowerCase()
        for (var i = 0; i < choices.length; ++i) {
            var item = choices[i]
            if (!needle || String(item.label).toLowerCase().indexOf(needle) >= 0 || String(item.id).toLowerCase().indexOf(needle) >= 0)
                result.push(item)
        }
        return result
    }
    function focusFirst() { search.forceActiveFocus() }

    Column {
        id: pickerColumn
        width: parent.width
        spacing: Style.spacing.sm
        Ui.TextField {
            id: search
            width: parent.width
            enabled: root.enabled
            placeholderText: "Search choices"
            Keys.onEscapePressed: text = ""
        }
        Repeater {
            model: root.filteredChoices()
            delegate: Ui.Button {
                required property var modelData
                width: pickerColumn.width
                text: modelData.label + " · " + modelData.state + " · argv: " + root.selector + " " + modelData.id
                leftAlign: true
                bordered: true
                focusable: true
                selected: root.currentChoice === modelData.id
                enabled: root.enabled
                onClicked: root.choicePicked(modelData)
                onRightClicked: root.detailsChoice = modelData
            }
        }
        ChoiceDetails { width: parent.width; choice: root.detailsChoice }
    }
}
