import CoreGraphics
import Foundation

guard CommandLine.arguments.count == 4,
      let x = Double(CommandLine.arguments[1]),
      let y = Double(CommandLine.arguments[2]),
      let delta = Int32(CommandLine.arguments[3]) else {
    fputs("usage: mouse-scroll <x> <y> <delta>\n", stderr)
    exit(2)
}

let point = CGPoint(x: x, y: y)
let source = CGEventSource(stateID: .combinedSessionState)
let move = CGEvent(mouseEventSource: source, mouseType: .mouseMoved,
                   mouseCursorPosition: point, mouseButton: .left)
move?.post(tap: .cghidEventTap)
Thread.sleep(forTimeInterval: 0.02)

// A wheel event is separate from the click helper, so list scanning never
// relies on a held mouse button or a drag gesture.
let scroll = CGEvent(scrollWheelEvent2Source: source, units: .line,
                     wheelCount: 1, wheel1: delta, wheel2: 0, wheel3: 0)
scroll?.post(tap: .cghidEventTap)
