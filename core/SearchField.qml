import QtQuick
import qs.Ui as Ui

Ui.TextField {
    id: root
    property alias query: root.text
    signal queryEdited(string query)
    placeholderText: "Search"
    onTextEdited: queryEdited(text)
    function focusInput() { forceActiveFocus() }
}
