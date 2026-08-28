import CoreGraphics
import Foundation

guard CommandLine.arguments.count >= 2 else {
    fputs("usage: mouse-state idle|position|move [x y]\n", stderr)
    exit(2)
}

switch CommandLine.arguments[1] {
case "idle":
    // hidSystemState excludes the synthetic events emitted by this project.
    // That keeps our own click/move events from making the user look busy.
    let events: [CGEventType] = [.mouseMoved, .leftMouseDown, .rightMouseDown, .keyDown]
    let idle = events.map {
        CGEventSource.secondsSinceLastEventType(.hidSystemState, eventType: $0)
    }.min() ?? 0
    print(String(format: "%.3f", max(0, idle)))

case "position":
    guard let event = CGEvent(source: nil) else {
        fputs("unable to read cursor position\n", stderr)
        exit(1)
    }
    let point = event.location
    print(String(format: "%.1f,%.1f", point.x, point.y))

case "move":
    guard CommandLine.arguments.count == 4,
          let x = Double(CommandLine.arguments[2]),
          let y = Double(CommandLine.arguments[3]) else {
        fputs("usage: mouse-state move <x> <y>\n", stderr)
        exit(2)
    }
    let source = CGEventSource(stateID: .combinedSessionState)
    let event = CGEvent(mouseEventSource: source, mouseType: .mouseMoved,
                        mouseCursorPosition: CGPoint(x: x, y: y),
                        mouseButton: .left)
    event?.post(tap: .cgSessionEventTap)

default:
    fputs("unknown command\n", stderr)
    exit(2)
}
