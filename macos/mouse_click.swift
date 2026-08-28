import CoreGraphics
import Foundation

guard CommandLine.arguments.count == 3,
      let x = Double(CommandLine.arguments[1]),
      let y = Double(CommandLine.arguments[2]) else {
    fputs("usage: mouse-click <x> <y>\n", stderr)
    exit(2)
}

let point = CGPoint(x: x, y: y)
let source = CGEventSource(stateID: .combinedSessionState)
let move = CGEvent(mouseEventSource: source, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left)
let down = CGEvent(mouseEventSource: source, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left)
let up = CGEvent(mouseEventSource: source, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left)

// Keep the pointer stationary for the complete button gesture.  A small
// settle delay after moving and an explicit click state prevent WeChat from
// interpreting a busy event stream as a drag of the conversation row.
down?.setIntegerValueField(.mouseEventClickState, value: 1)
up?.setIntegerValueField(.mouseEventClickState, value: 1)
move?.post(tap: .cgSessionEventTap)
Thread.sleep(forTimeInterval: 0.02)
down?.post(tap: .cgSessionEventTap)
Thread.sleep(forTimeInterval: 0.025)
up?.post(tap: .cgSessionEventTap)
