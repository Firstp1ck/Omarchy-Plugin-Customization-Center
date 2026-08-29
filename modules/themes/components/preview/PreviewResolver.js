.pragma library

var sectionDefaults = {
    bar: { background: "background", "background-alpha": 1.0, text: "foreground", active: "red", "scale-with-font": true, "size-horizontal": 26, "size-vertical": 28 },
    controls: {
        "normal-color": "foreground", "normal-fill-alpha": .04, "normal-border": "foreground", "normal-border-width": "1", "normal-border-alpha": .4,
        "hover-cursor-color": "foreground", "hover-cursor-fill-alpha": .08, "hover-cursor-border": "foreground", "hover-cursor-border-width": "1", "hover-cursor-border-alpha": .25,
        "focus-color": "foreground", "focus-fill-alpha": .08, "focus-border": "foreground", "focus-border-width": "1", "focus-border-alpha": .25,
        "selected-color": "foreground", "selected-fill-alpha": .18, "selected-border": "foreground", "selected-border-width": "0", "selected-border-alpha": 1.0,
        "pressed-fill-alpha": .22, "selection-fill-alpha": .35
    },
    spacing: { scale: 1.0, "scale-with-font": true },
    font: { "base-size": 12 },
    popups: { background: "background", "background-alpha": 1.0, text: "foreground", border: "hyprland.active-border", "border-alpha": 1.0, "border-width": null },
    tooltip: { background: "background", "background-alpha": .97, text: "foreground", border: "hyprland.active-border-foreground", "border-alpha": 1.0 },
    notifications: { background: "background", "background-alpha": 1.0, text: "foreground", border: "hyprland.active-border", "border-alpha": 1.0, "border-width": null, countdown: "accent" },
    launcher: { background: "background", "background-alpha": .95, text: "foreground", border: "hyprland.active-border-foreground", "border-alpha": 1.0, "border-width": null, scrim: "background", "scrim-alpha": .5, "selected-background": "foreground", "selected-background-alpha": .08, "selected-text": "accent", "selected-border": "hyprland.active-border-foreground", "selected-border-alpha": .25, "selected-border-width": null },
    menu: { background: "background", "background-alpha": 1.0, text: "foreground", border: "hyprland.active-border-foreground", "border-alpha": 1.0, "border-width": null, scrim: "background", "scrim-alpha": .5, "selected-background": "foreground", "selected-background-alpha": .08, "selected-text": "accent", "selected-border": "hyprland.active-border-foreground", "selected-border-alpha": .25, "selected-border-width": null },
    polkit: { background: "background", "background-alpha": 1.0, text: "foreground", border: "hyprland.active-border", "border-alpha": 1.0, "border-width": null, "text-error": "red", "border-error": "red", scrim: "background", "scrim-alpha": .5, accent: "accent" },
    lock: { background: "background", "background-alpha": .8, text: "foreground", placeholder: null, "text-error": "red", border: "hyprland.active-border", "border-active": "hyprland.active-border", "border-error": "red", "border-alpha": 1.0, selection: "accent", "selection-alpha": .45, "border-width": null, "border-active-width": null, "border-error-width": null },
    "image-picker": { scrim: "background", "scrim-alpha": .5, text: "foreground", "selected-border": "accent", "selected-border-alpha": 1.0, "unselected-border": "foreground", "unselected-border-alpha": .28, "selected-border-width": null, "unselected-border-width": null }
}
var spacingNames = ["xxs", "xs", "sm", "md", "lg", "xl", "xxl", "xxxl", "huge", "control-gap", "control-padding-x", "control-padding-y", "input-padding-y", "control-height", "popup-row-height", "row-gap", "row-padding-x", "label-gap", "panel-gap", "panel-padding", "popup-padding", "dropdown-width", "searchable-dropdown-width", "number-field-width", "searchable-popup-min-height"]
var spacingDefaults = [2, 3, 4, 6, 8, 10, 12, 14, 18, 8, 10, 6, 7, 28, 28, 8, 12, 4, 14, 18, 14, 240, 260, 120, 220]
var fontMultipliers = { caption: .833, "body-small": .917, body: 1.0, subtitle: 1.083, title: 1.167, heading: 1.333, display: 2.0, "display-large": 2.333, "icon-small": .917, icon: 1.167, "icon-large": 1.5 }
Object.keys(fontMultipliers).forEach(function(key) { sectionDefaults.font[key] = null })
spacingNames.forEach(function(key) { sectionDefaults.spacing[key] = null })

function clone(value) { return JSON.parse(JSON.stringify(value)) }
function channel(value, offset) { return parseInt(value.substring(offset, offset + 2), 16) }
function mix(first, second, amount) {
    var output = "#"
    for (var offset = 1; offset < 6; offset += 2)
        output += Math.floor(channel(first, offset) * (1 - amount) + channel(second, offset) * amount + .5).toString(16).padStart(2, "0")
    return output
}
function seeded(input) {
    var p = clone(input || ({})); var dark = p.mode !== "light"
    p.selection = p.selection || mix(p.background, p.foreground, .15)
    p.muted = p.muted || mix(p.foreground, p.background, .5)
    p.dark_background = p.dark_background || mix(p.background, "#000000", .25)
    p.darker_background = p.darker_background || mix(p.background, "#000000", .5)
    p.lighter_background = p.lighter_background || mix(p.background, p.foreground, .08)
    p.dark_foreground = p.dark_foreground || mix(p.foreground, p.background, .4)
    p.light_foreground = p.light_foreground || mix(p.foreground, dark ? "#ffffff" : "#000000", dark ? .08 : .2)
    p.bright_foreground = p.bright_foreground || (dark ? mix(p.foreground, "#ffffff", .15) : p.foreground)
    p.orange = p.orange || mix(p.yellow, p.red, .4); p.brown = p.brown || mix(p.orange, "#000000", .5)
    var bases = ["red", "yellow", "green", "cyan", "blue", "magenta"]
    for (var i = 0; i < bases.length; ++i) p["bright_" + bases[i]] = p["bright_" + bases[i]] || mix(p[bases[i]], "#ffffff", .2)
    p.urgent = p.red; return p
}
function role(value, p, hyprland) {
    if (p[value] !== undefined && typeof p[value] === "string") return p[value]
    var roles = { foreground: p.foreground, text: p.foreground, accent: p.accent, urgent: p.red, muted: p.muted, background: p.background, transparent: "#00000000", "hyprland.active-border": hyprland["active-border"], "hyprland.active-border-foreground": hyprland["active-border-foreground"] }
    return roles[value] !== undefined ? roles[value] : value
}
function border(value, p, hyprland) {
    return String(role(value, p, hyprland)).split(" ").map(function(word) { return String(role(word, p, hyprland)) }).join(" ")
}
function alphaColor(value, alpha) {
    if (value === "#00000000") return value
    return /^#[0-9a-f]{6}$/.test(value) ? value + Math.max(0, Math.min(255, Math.round(alpha * 255))).toString(16).padStart(2, "0") : value
}
function borderStops(raw) {
    if (/^#[0-9a-f]{6}$/.test(raw)) return [{ color: raw, alpha: 1 }]
    var out = []; var expression = /rgb\(([0-9a-f]{6})\)|rgba\(([0-9a-f]{8})\)/g; var found
    while ((found = expression.exec(raw)) !== null) { var value = found[1] || found[2]; out.push({ color: "#" + value.substring(0, 6), alpha: value.length === 8 ? parseInt(value.substring(6), 16) / 255 : 1 }) }
    return out
}
function resolve(draft, machineOverride, options) {
    options = options || ({}); var effective = options.effective === undefined ? true : !!options.effective
    var p = seeded(draft && draft.palette ? draft.palette : ({}))
    var hyprland = { "active-border": p.hyprland_active_border || p.accent, "active-border-foreground": p.hyprland_active_border || p.foreground, "inactive-border": p.hyprland_inactive_border || "rgba(595959aa)" }
    var source = draft && draft.sections ? draft.sections : ({}); var sections = ({}); var masked = []
    for (var name in sectionDefaults) { sections[name] = clone(sectionDefaults[name]); if (source[name]) Object.assign(sections[name], clone(source[name])) }
    var machine = machineOverride || ({})
    if (effective) for (var flat in machine) { var dot = flat.indexOf("."); if (dot < 1) continue; var sectionName = flat.substring(0, dot); var key = flat.substring(dot + 1); if (sections[sectionName] && sections[sectionName][key] !== undefined) { masked.push({ section: sectionName, key: key, draftValue: sections[sectionName][key], overrideValue: machine[flat] }); sections[sectionName][key] = machine[flat] } }
    if (sections.lock.placeholder === null) sections.lock.placeholder = mix(p.foreground, p.background, .34)
    var resolved = ({}); var borders = ({})
    for (var section in sections) { resolved[section] = ({}); borders[section] = ({}); for (var field in sections[section]) { var value = sections[section][field]; if (value === null) resolved[section][field] = null; else if (field.indexOf("border") >= 0 && field.indexOf("alpha") < 0 && field.indexOf("width") < 0) { var raw = border(value, p, hyprland); resolved[section][field] = raw; var width = sections[section][field + "-width"] || sections[section]["border-width"] || "1"; var a = Number(sections[section][field + "-alpha"] !== undefined ? sections[section][field + "-alpha"] : (sections[section]["border-alpha"] !== undefined ? sections[section]["border-alpha"] : 1)); borders[section][field] = { raw: raw, width: String(width), alpha: a, stops: borderStops(raw).map(function(stop) { return { color: stop.color, alpha: stop.alpha * a } }) } } else if (["background", "text", "active", "countdown", "scrim", "selected-background", "selected-text", "text-error", "placeholder", "selection", "accent"].indexOf(field) >= 0 || field.endsWith("-color")) resolved[section][field] = role(value, p, hyprland); else resolved[section][field] = value } }
    var base = Math.max(1, Number(sections.font["base-size"] || 12)); var font = { baseSize: base, scale: Math.max(1 / 12, base / 12) }
    for (var fontName in fontMultipliers) font[fontName] = Math.max(1, Math.round(sections.font[fontName] !== undefined && sections.font[fontName] !== null ? Number(sections.font[fontName]) : base * fontMultipliers[fontName]))
    var spacingScale = Number(sections.spacing.scale || 1); var spacingEffective = spacingScale * (sections.spacing["scale-with-font"] ? font.scale : 1); var spacing = { scale: spacingScale, scaleWithFont: !!sections.spacing["scale-with-font"], effective: spacingEffective }
    for (var si = 0; si < spacingNames.length; ++si) spacing[spacingNames[si]] = sections.spacing[spacingNames[si]] !== undefined && sections.spacing[spacingNames[si]] !== null ? Math.round(Number(sections.spacing[spacingNames[si]])) : Math.max(1, Math.round(spacingDefaults[si] * spacingEffective))
    var barScale = sections.bar["scale-with-font"] ? font.scale : 1; var barMetrics = { sizeHorizontal: Math.max(1, Math.round(Number(sections.bar["size-horizontal"] || 26) * barScale)), sizeVertical: Math.max(1, Math.round(Number(sections.bar["size-vertical"] || 28) * barScale)), scaleWithFont: !!sections.bar["scale-with-font"] }
    var controls = ({}); ["normal", "hover-cursor", "focus", "selected"].forEach(function(state) { var color = resolved.controls[state + "-color"]; var fillAlpha = Number(resolved.controls[state + "-fill-alpha"]); controls[state] = { color: color, fill: alphaColor(color, fillAlpha), fillAlpha: fillAlpha, border: borders.controls[state + "-border"] || ({}) } }); controls.pressedFillAlpha = Number(resolved.controls["pressed-fill-alpha"]); controls.selectionFillAlpha = Number(resolved.controls["selection-fill-alpha"])
    return { palette: p, roles: { foreground: p.foreground, text: p.foreground, accent: p.accent, urgent: p.red, muted: p.muted, background: p.background, transparent: "#00000000" }, hyprland: hyprland, sections: resolved, borders: borders, metrics: { font: font, spacing: spacing, bar: barMetrics }, controls: controls, masked: masked, machineOverride: machine, effective: effective }
}
