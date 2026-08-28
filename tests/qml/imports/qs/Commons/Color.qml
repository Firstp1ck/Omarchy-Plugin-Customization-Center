pragma Singleton
import QtQuick
QtObject {
    property color foreground: "#eeeeee"
    property color background: "#111111"
    property color accent: "#aaaaee"
    property color urgent: "#ee7777"
    property color muted: "#999999"
    property QtObject popups: QtObject { property color background: "#111111"; property color text: "#eeeeee"; property color border: "#aaaaee" }
    property QtObject menu: QtObject { property color background: "#111111"; property color text: "#eeeeee"; property color border: "#aaaaee"; property color scrim: "#99111111" }
    property QtObject notifications: QtObject { property color background: "#111111"; property color text: "#eeeeee"; property color border: "#aaaaee" }
}
