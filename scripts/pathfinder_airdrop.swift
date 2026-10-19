import Foundation
import ApplicationServices
import Cocoa

func matchesAirDrop(_ element: AXUIElement) -> Bool {
    var descValue: AnyObject?
    if AXUIElementCopyAttributeValue(element, kAXDescriptionAttribute as CFString, &descValue) == .success,
       let desc = descValue as? String {
        if desc == "AirDrop" || desc == "隔空投送" {
            return true
        }
    }
    var titleValue: AnyObject?
    if AXUIElementCopyAttributeValue(element, kAXTitleAttribute as CFString, &titleValue) == .success,
       let title = titleValue as? String {
        if title == "AirDrop" || title == "隔空投送" {
            return true
        }
    }
    return false
}

func findAirDropButton(in element: AXUIElement, depth: Int = 0) -> AXUIElement? {
    if depth > 6 { return nil }
    if matchesAirDrop(element) {
        return element
    }
    
    var childrenValue: AnyObject?
    if AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &childrenValue) == .success,
       let children = childrenValue as? [AXUIElement] {
        for child in children {
            if let found = findAirDropButton(in: child, depth: depth + 1) {
                return found
            }
        }
    }
    return nil
}

func triggerAirDrop() -> Bool {
    let bundleIds = ["com.cocoatech.PathFinder-setapp", "com.cocoatech.PathFinder"]
    var targetApp: NSRunningApplication?
    for bid in bundleIds {
        if let app = NSRunningApplication.runningApplications(withBundleIdentifier: bid).first {
            targetApp = app
            break
        }
    }
    
    guard let app = targetApp else {
        fputs("Path Finder is not running\n", stderr)
        return false
    }
    
    let pid = app.processIdentifier
    let appRef = AXUIElementCreateApplication(pid)
    
    // Activate Path Finder
    app.activate()
    
    // Find menu bar -> "Commands" / "命令" -> "Share…" / "共享…"
    var menuBarVal: AnyObject?
    guard AXUIElementCopyAttributeValue(appRef, kAXMenuBarAttribute as CFString, &menuBarVal) == .success,
          let menuBar = menuBarVal as! AXUIElement? else {
        fputs("Failed to get menu bar\n", stderr)
        return false
    }
    
    var menuBarItemsVal: AnyObject?
    guard AXUIElementCopyAttributeValue(menuBar, kAXChildrenAttribute as CFString, &menuBarItemsVal) == .success,
          let menuBarItems = menuBarItemsVal as? [AXUIElement] else {
        fputs("Failed to get menu bar items\n", stderr)
        return false
    }
    
    var commandsMenu: AXUIElement?
    for item in menuBarItems {
        var titleVal: AnyObject?
        if AXUIElementCopyAttributeValue(item, kAXTitleAttribute as CFString, &titleVal) == .success,
           let title = titleVal as? String, (title == "Commands" || title == "命令") {
            var childrenVal: AnyObject?
            if AXUIElementCopyAttributeValue(item, kAXChildrenAttribute as CFString, &childrenVal) == .success,
               let children = childrenVal as? [AXUIElement], let first = children.first {
                commandsMenu = first
            }
            break
        }
    }
    
    guard let commands = commandsMenu else {
        fputs("Commands menu not found\n", stderr)
        return false
    }
    
    var commandsItemsVal: AnyObject?
    guard AXUIElementCopyAttributeValue(commands, kAXChildrenAttribute as CFString, &commandsItemsVal) == .success,
          let commandItems = commandsItemsVal as? [AXUIElement] else {
        fputs("Failed to get Commands items\n", stderr)
        return false
    }
    
    var shareItem: AXUIElement?
    for item in commandItems {
        var titleVal: AnyObject?
        if AXUIElementCopyAttributeValue(item, kAXTitleAttribute as CFString, &titleVal) == .success,
           let title = titleVal as? String, (title.hasPrefix("Share") || title.hasPrefix("共享")) {
            shareItem = item
            break
        }
    }
    
    guard let share = shareItem else {
        fputs("Share… menu item not found\n", stderr)
        return false
    }
    
    // Click Share…
    let pressRes = AXUIElementPerformAction(share, kAXPressAction as CFString)
    guard pressRes == .success else {
        fputs("Failed to press Share…: \(pressRes.rawValue)\n", stderr)
        return false
    }
    
    // Poll for the popover window and the AirDrop button
    let start = Date()
    while Date().timeIntervalSince(start) < 2.0 {
        // 1. Check focused UI element
        var focusedVal: AnyObject?
        if AXUIElementCopyAttributeValue(appRef, kAXFocusedUIElementAttribute as CFString, &focusedVal) == .success,
           let focused = focusedVal as! AXUIElement? {
            if let button = findAirDropButton(in: focused) {
                let res = AXUIElementPerformAction(button, kAXPressAction as CFString)
                if res == .success {
                    return true
                }
            }
        }
        
        // 2. Check top-level children of app
        var appChildrenVal: AnyObject?
        if AXUIElementCopyAttributeValue(appRef, kAXChildrenAttribute as CFString, &appChildrenVal) == .success,
           let children = appChildrenVal as? [AXUIElement] {
            for child in children {
                if let button = findAirDropButton(in: child) {
                    let res = AXUIElementPerformAction(button, kAXPressAction as CFString)
                    if res == .success {
                        return true
                    }
                }
            }
        }
        
        // 3. Check windows
        var windowsVal: AnyObject?
        if AXUIElementCopyAttributeValue(appRef, kAXWindowsAttribute as CFString, &windowsVal) == .success,
           let windows = windowsVal as? [AXUIElement] {
            for win in windows {
                if let button = findAirDropButton(in: win) {
                    let res = AXUIElementPerformAction(button, kAXPressAction as CFString)
                    if res == .success {
                        return true
                    }
                }
            }
        }
        
        usleep(10_000) // 10ms poll
    }
    
    fputs("Timed out waiting for AirDrop button\n", stderr)
    return false
}

exit(triggerAirDrop() ? 0 : 1)
