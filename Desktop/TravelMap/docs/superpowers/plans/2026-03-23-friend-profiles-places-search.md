# Friend/Guide Profiles + Places Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tappable friend/guide profiles with collections and "View on Map", plus rework Places search to filter pins directly across all cities with tap-to-navigate-on-map.

**Architecture:** Two independent features sharing a common navigation mechanism (tab switching + map focus via AppState). Feature 1 adds `ProfileSource` enum, `FriendProfileView`, mock collections for all friends/guides, and tappable entry points in 3 views. Feature 2 reworks PlacesView search to filter pins directly and adds `navigateToPin` to AppState for cross-tab map navigation.

**Tech Stack:** SwiftUI, UIKit (MapKit interop), @Observable, NotificationCenter

---

## File Structure

**New files:**
- `TravelMap/Models/ProfileSource.swift` — `ProfileSource` enum wrapping Friend or Guide
- `TravelMap/Views/Profile/FriendProfileView.swift` — Unified profile view for friends/guides

**Modified files:**
- `TravelMap/AppState/AppState.swift` — Add `mapFocusSource`, `navigateToPin`, `selectedTab`, friend/guide collection helpers
- `TravelMap/MockData/MockData.swift` — Add mock collections for all friends and guides
- `TravelMap/Models/Friend.swift` — Add `collections: [PinCollection]` field
- `TravelMap/Models/Guide.swift` — Add `collections: [PinCollection]` field
- `TravelMap/MainTabView.swift` — Bind `selectedTab` to AppState for programmatic tab switching
- `TravelMap/Views/Profile/ProfileView.swift` — Make friend/guide rows tappable → NavigationLink to FriendProfileView
- `TravelMap/Components/CityDrawerView.swift` — Make friend/guide rows tappable → sheet to FriendProfileView
- `TravelMap/Views/Map/PinDetailSheet.swift` — Make sourceLabel tappable → sheet to FriendProfileView
- `TravelMap/Views/Map/MapContainerView.swift` — Handle `mapFocusSource` (filter + zoom), handle `navigateToPin` (fly + auto-open detail)
- `TravelMap/Views/Places/PlacesView.swift` — Rework search to filter pins directly, add tap-to-navigate

---

### Task 1: Add ProfileSource enum

**Files:**
- Create: `TravelMap/Models/ProfileSource.swift`

- [ ] **Step 1: Create ProfileSource.swift**

```swift
import Foundation

enum ProfileSource: Identifiable {
    case friend(Friend)
    case guide(Guide)

    var id: String {
        switch self {
        case .friend(let f): return f.id
        case .guide(let g): return g.id
        }
    }

    var name: String {
        switch self {
        case .friend(let f): return f.name
        case .guide(let g): return g.author
        }
    }

    var handle: String {
        switch self {
        case .friend(let f): return f.handle
        case .guide(let g): return g.author
        }
    }

    var pins: [Pin] {
        switch self {
        case .friend(let f): return f.pins
        case .guide(let g): return g.pins
        }
    }

    var collections: [PinCollection] {
        switch self {
        case .friend(let f): return f.collections
        case .guide(let g): return g.collections
        }
    }

    var displayTitle: String {
        switch self {
        case .friend(let f): return f.name
        case .guide(let g): return "\(g.title) by \(g.author)"
        }
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED (will fail until Friend/Guide get `collections` field — that's Task 2)

- [ ] **Step 3: Commit**

```bash
git add TravelMap/Models/ProfileSource.swift
git commit -m "feat: add ProfileSource enum for unified friend/guide profiles"
```

---

### Task 2: Add collections field to Friend and Guide models

**Files:**
- Modify: `TravelMap/Models/Friend.swift`
- Modify: `TravelMap/Models/Guide.swift`

- [ ] **Step 1: Add `collections` to Friend**

In `Friend.swift`, add `var collections: [PinCollection] = []` as a stored property. Update both `init` methods to include it with a default of `[]`. In the `init(from decoder:)`, add:
```swift
collections = (try? c.decode([PinCollection].self, forKey: .collections)) ?? []
```

Add `.collections` to `CodingKeys` if needed (it will be auto-synthesized since it's a stored property with a default).

- [ ] **Step 2: Add `collections` to Guide**

Same pattern in `Guide.swift`: add `var collections: [PinCollection] = []`, update both inits, add decode with `?? []` fallback.

- [ ] **Step 3: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 4: Commit**

```bash
git add TravelMap/Models/Friend.swift TravelMap/Models/Guide.swift
git commit -m "feat: add collections field to Friend and Guide models"
```

---

### Task 3: Add mock collections to all friends and guides

**Files:**
- Modify: `TravelMap/MockData/MockData.swift`

- [ ] **Step 1: Restructure mock data to pre-create pin arrays**

Since pins are created with `uid()` (new UUID each app launch), collections need to reference those same pin objects. Restructure each friend/guide: extract the pins array into a `let` constant first, then build the Friend/Guide with those pins and collections referencing those pin IDs.

Example for Leo S.:
```swift
private let leoSPins = [
    friendPin("Fuglen Tokyo", .food, 35.6580, 139.7016, "Best flat white in the city"),
    // ... rest of pins
]

// Then in MOCK_FRIENDS:
Friend(id: "leo_s", handle: "@leo_s", name: "Leo S.", pins: leoSPins,
       collections: [
           PinCollection(id: uid(), title: "Tokyo Coffee Run", description: "My go-to cafés",
                         pinIds: [leoSPins[0].id, leoSPins[4].id], dateAdded: mockDate2024),
           PinCollection(id: uid(), title: "Berlin Essentials", description: "First week in Berlin",
                         pinIds: [leoSPins[6].id, leoSPins[7].id, leoSPins[8].id], dateAdded: mockDate2024),
       ],
       visible: true, showInSidebar: true),
```

Do this for all 10 friends (1-2 collections each) and all 5 guides (1 collection each). Each collection should have 2-4 pins from that person's existing pin array, with a thematic title and short description.

- [ ] **Step 2: Verify it compiles and collections are populated**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add TravelMap/MockData/MockData.swift
git commit -m "feat: add mock collections for all friends and guides"
```

---

### Task 4: Add navigation state to AppState

**Files:**
- Modify: `TravelMap/AppState/AppState.swift`

- [ ] **Step 1: Add new state properties**

Add these properties to AppState (these are transient navigation state, no persistence needed — do NOT add `didSet { scheduleSave() }`):

```swift
// MARK: - Navigation state (transient, not persisted)
var selectedTab: AppTab = .map
var mapFocusSource: ProfileSource? = nil
var navigateToPin: Pin? = nil
```

These do NOT get `didSet { scheduleSave() }` and are NOT included in the Snapshot struct or init parameters.

- [ ] **Step 2: Add helper to find friend/guide that owns a pin**

Add to AppState:

```swift
func profileSource(forPinId pinId: String) -> ProfileSource? {
    if let friend = friends.first(where: { $0.pins.contains(where: { $0.id == pinId }) }) {
        return .friend(friend)
    }
    if let guide = guides.first(where: { $0.pins.contains(where: { $0.id == pinId }) }) {
        return .guide(guide)
    }
    return nil
}
```

- [ ] **Step 3: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 4: Commit**

```bash
git add TravelMap/AppState/AppState.swift
git commit -m "feat: add navigation state properties to AppState"
```

---

### Task 5: Bind selectedTab in MainTabView

**Files:**
- Modify: `TravelMap/MainTabView.swift`

- [ ] **Step 1: Bind TabView selection to AppState.selectedTab**

Replace `@State private var selectedTab: AppTab = .map` with reading from AppState:

```swift
@Environment(AppState.self) private var appState
```

Change `TabView(selection: $selectedTab)` to use a binding to appState:

```swift
TabView(selection: Bindable(appState).selectedTab) {
```

Remove the `@State private var selectedTab` line. Update all references from `selectedTab` to `appState.selectedTab`.

- [ ] **Step 2: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add TravelMap/MainTabView.swift
git commit -m "feat: bind tab selection to AppState for programmatic switching"
```

---

### Task 6: Create FriendProfileView

**Files:**
- Create: `TravelMap/Views/Profile/FriendProfileView.swift`

- [ ] **Step 1: Create FriendProfileView**

Build a SwiftUI view matching the design:

```swift
import SwiftUI
import MapKit

struct FriendProfileView: View {
    let source: ProfileSource
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @State private var expandedCities: Set<String> = []
    @State private var selectedCollection: PinCollection? = nil

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    // Avatar + name + handle
                    headerSection

                    // Stats row (pins, cities)
                    statsRow
                        .padding(.horizontal, 20)
                        .padding(.top, 24)

                    // View on Map button
                    viewOnMapButton
                        .padding(.horizontal, 20)
                        .padding(.top, 16)

                    // Collections section
                    if !source.collections.isEmpty {
                        collectionsSection
                    }

                    // Pins by city
                    pinsSection

                    Spacer(minLength: 100)
                }
            }
            .background(Theme.Colors.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { dismiss() } label: {
                        Image(systemName: "chevron.left")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(Theme.Colors.text)
                    }
                }
            }
            .sheet(item: $selectedCollection) { collection in
                friendCollectionDetail(collection)
                    .presentationDetents([.large])
                    .presentationBackground(Theme.Colors.background)
            }
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(spacing: 0) {
            // Avatar circle with initial
            ZStack {
                Circle()
                    .fill(Theme.Colors.surfaceSecondary)
                    .frame(width: 88, height: 88)
                Text(String(source.name.prefix(1)))
                    .font(.system(size: 36, weight: .semibold))
                    .foregroundStyle(Theme.Colors.text)
            }
            .overlay(Circle().strokeBorder(.white, lineWidth: 3))

            Text(source.name)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(Theme.Colors.text)
                .padding(.top, 12)

            Text(source.handle)
                .font(.system(size: 15))
                .foregroundStyle(Theme.Colors.textSecondary)
                .padding(.top, 2)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 24)
    }

    // MARK: - Stats Row

    private var statsRow: some View {
        HStack(spacing: 0) {
            statCell(value: "\(source.pins.count)", label: "PINS")
            thinDivider
            statCell(value: "\(citiesCount)", label: "CITIES")
        }
        .background(Theme.Colors.surface)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.medium))
        .shadow(color: Theme.Shadow.cardShadowColor,
                radius: Theme.Shadow.cardShadowRadius,
                y: Theme.Shadow.cardShadowY)
    }

    private func statCell(value: String, label: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.georgia(28))
                .foregroundStyle(Theme.Colors.text)
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .tracking(1)
                .foregroundStyle(Theme.Colors.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
    }

    private var citiesCount: Int {
        Set(source.pins.compactMap { appState.nearestCity(for: $0)?.id }).count
    }

    private var thinDivider: some View {
        Rectangle()
            .fill(Theme.Colors.border)
            .frame(width: 0.5, height: 40)
    }

    // MARK: - View on Map

    private var viewOnMapButton: some View {
        Button {
            appState.mapFocusSource = source
            appState.selectedTab = .map
            dismiss()
        } label: {
            HStack {
                Image(systemName: "map.fill")
                Text("View on Map")
                    .font(.system(size: 15, weight: .semibold))
            }
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .frame(height: 44)
            .background(Theme.Colors.accentBlue)
            .clipShape(Capsule())
        }
    }

    // MARK: - Collections

    private var collectionsSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            sectionHeader("COLLECTIONS")
                .padding(.top, 28)

            LazyVGrid(columns: [
                GridItem(.adaptive(minimum: 160), spacing: 12)
            ], spacing: 12) {
                ForEach(source.collections) { collection in
                    collectionCard(collection)
                        .onTapGesture { selectedCollection = collection }
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func collectionCard(_ collection: PinCollection) -> some View {
        let collectionPins = source.pins.filter { collection.pinIds.contains($0.id) }
        let dominantCategory = collectionPins.map(\.category)
            .reduce(into: [:]) { $0[$1, default: 0] += 1 }
            .max(by: { $0.value < $1.value })?.key ?? .essentials

        return VStack(alignment: .leading, spacing: 8) {
            // Color band
            RoundedRectangle(cornerRadius: 4)
                .fill(dominantCategory.color)
                .frame(height: 8)

            Text(collection.title)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.Colors.text)
                .lineLimit(1)

            Text("\(collectionPins.count) pins")
                .font(.system(size: 13))
                .foregroundStyle(Theme.Colors.textSecondary)

            if !collection.description.isEmpty {
                Text(collection.description)
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.Colors.textMuted)
                    .lineLimit(2)
            }
        }
        .padding(12)
        .background(Theme.Colors.surface)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.medium))
        .shadow(color: Theme.Shadow.cardShadowColor,
                radius: Theme.Shadow.cardShadowRadius,
                y: Theme.Shadow.cardShadowY)
    }

    // MARK: - Collection Detail (read-only)

    private func friendCollectionDetail(_ collection: PinCollection) -> some View {
        let collectionPins = source.pins.filter { collection.pinIds.contains($0.id) }
        let dominantCategory = collectionPins.map(\.category)
            .reduce(into: [:]) { $0[$1, default: 0] += 1 }
            .max(by: { $0.value < $1.value })?.key ?? .essentials

        return ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                // Color band
                RoundedRectangle(cornerRadius: 0)
                    .fill(dominantCategory.color)
                    .frame(height: 8)

                Text(collection.title)
                    .font(.georgia(28))
                    .foregroundStyle(Theme.Colors.text)
                    .padding(.horizontal, 20)
                    .padding(.top, 16)

                Text("\(collectionPins.count) pins")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.Colors.textSecondary)
                    .padding(.horizontal, 20)
                    .padding(.top, 4)

                if !collection.description.isEmpty {
                    Text(collection.description)
                        .font(.system(size: 15))
                        .foregroundStyle(Theme.Colors.textMuted)
                        .padding(.horizontal, 20)
                        .padding(.top, 8)
                }

                if collectionPins.isEmpty {
                    VStack(spacing: 8) {
                        Image(systemName: "mappin.slash")
                            .font(.system(size: 32))
                            .foregroundStyle(Theme.Colors.textMuted)
                        Text("No pins")
                            .font(.system(size: 15))
                            .foregroundStyle(Theme.Colors.textMuted)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 40)
                } else {
                    LazyVStack(spacing: 0) {
                        ForEach(collectionPins) { pin in
                            HStack(spacing: 10) {
                                Circle()
                                    .fill(pin.category.color)
                                    .frame(width: 10, height: 10)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(pin.name)
                                        .font(.system(size: 16, weight: .semibold))
                                        .foregroundStyle(Theme.Colors.text)
                                    if !pin.notes.isEmpty {
                                        Text(pin.notes)
                                            .font(.system(size: 14).italic())
                                            .foregroundStyle(Theme.Colors.textSecondary)
                                            .lineLimit(1)
                                    }
                                }
                                Spacer()
                            }
                            .padding(.horizontal, 20)
                            .padding(.vertical, 12)

                            Rectangle()
                                .fill(Theme.Colors.border)
                                .frame(height: 0.5)
                                .padding(.leading, 50)
                        }
                    }
                    .padding(.top, 16)
                }

                Spacer(minLength: 40)
            }
        }
    }

    // MARK: - Pins Section

    private var pinsSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            sectionHeader("PINS")
                .padding(.top, 28)

            // Group pins by approximate city
            let grouped = groupPinsByCity()
            LazyVStack(spacing: 0) {
                ForEach(grouped, id: \.city) { group in
                    cityAccordion(group.city, pins: group.pins)
                }
            }
        }
    }

    private func groupPinsByCity() -> [(city: String, pins: [Pin])] {
        var groups: [String: [Pin]] = [:]
        for pin in source.pins {
            let cityName = appState.nearestCity(for: pin)?.name ?? "Other"
            groups[cityName, default: []].append(pin)
        }
        return groups.map { (city: $0.key, pins: $0.value) }
            .sorted { $0.city < $1.city }
    }

    private func cityAccordion(_ cityName: String, pins: [Pin]) -> some View {
        let isExpanded = expandedCities.contains(cityName)
        return VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.25)) {
                    if isExpanded { expandedCities.remove(cityName) }
                    else { expandedCities.insert(cityName) }
                }
            } label: {
                HStack {
                    Text(cityName)
                        .font(.georgia(22))
                        .foregroundStyle(Theme.Colors.text)
                    Spacer()
                    Text("\(pins.count)")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Theme.Colors.surfaceSecondary)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    Image(systemName: "chevron.down")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.Colors.textMuted)
                        .rotationEffect(.degrees(isExpanded ? 180 : 0))
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
            }

            if isExpanded {
                ForEach(pins) { pin in
                    HStack(spacing: 10) {
                        Circle()
                            .fill(pin.category.color)
                            .frame(width: 10, height: 10)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(pin.name)
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundStyle(Theme.Colors.text)
                            if !pin.notes.isEmpty {
                                Text(pin.notes)
                                    .font(.system(size: 14).italic())
                                    .foregroundStyle(Theme.Colors.textSecondary)
                                    .lineLimit(1)
                            }
                        }
                        Spacer()
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)

                    Rectangle()
                        .fill(Theme.Colors.border)
                        .frame(height: 0.5)
                        .padding(.leading, 50)
                }
            }

            Rectangle()
                .fill(Theme.Colors.border)
                .frame(height: 0.5)
                .padding(.horizontal, 20)
        }
    }

    // MARK: - Section Header

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 11, weight: .semibold))
            .tracking(3)
            .foregroundStyle(Theme.Colors.textSecondary)
            .padding(.horizontal, 20)
            .padding(.bottom, 14)
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add TravelMap/Views/Profile/FriendProfileView.swift
git commit -m "feat: add FriendProfileView for friend/guide profiles"
```

---

### Task 7: Make friends/guides tappable in ProfileView

**Files:**
- Modify: `TravelMap/Views/Profile/ProfileView.swift`

- [ ] **Step 1: Add state for selected profile**

Add to ProfileView:
```swift
@State private var selectedProfileSource: ProfileSource?
```

- [ ] **Step 2: Wrap friendManagementRow in a Button/tap gesture**

In the `friendsExpanded` block, wrap each `friendManagementRow(friend)` so tapping the row (not the star) opens the profile. Add `.onTapGesture` to the row's main content area (exclude the star button). The simplest approach: wrap the entire `friendManagementRow` in a `Button` that sets `selectedProfileSource = .friend(friend)`, and keep the star as an overlay button.

Actually, simpler: make the name/handle/avatar area tappable, leave the star button as-is. In `friendManagementRow`, wrap the `ZStack` (avatar) + `VStack` (name/handle) in a `Button` that sets `selectedProfileSource`.

Do the same for `guideManagementRow` — tap sets `selectedProfileSource = .guide(guide)`.

- [ ] **Step 3: Add sheet presentation**

Add to ProfileView body, after the settings sheet:
```swift
.sheet(item: $selectedProfileSource) { source in
    FriendProfileView(source: source)
        .environment(appState)
}
```

- [ ] **Step 4: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 5: Commit**

```bash
git add TravelMap/Views/Profile/ProfileView.swift
git commit -m "feat: make friend/guide rows tappable in ProfileView"
```

---

### Task 8: Make friends/guides tappable in CityDrawerView

**Files:**
- Modify: `TravelMap/Components/CityDrawerView.swift`

- [ ] **Step 1: Add state for selected profile**

Add to CityDrawerView:
```swift
@State private var selectedProfileSource: ProfileSource?
```

- [ ] **Step 2: Make friend rows tappable**

In `friendRow(_ friend:)`, wrap the name/handle VStack in a `Button` that sets `selectedProfileSource = .friend(friend)`. Keep the visibility `Toggle` separate. The text area should be tappable, the toggle should remain independent.

- [ ] **Step 3: Make guide rows tappable**

Same pattern for `guideRow(_ guide:)` — tap the text area sets `selectedProfileSource = .guide(guide)`.

- [ ] **Step 4: Add sheet presentation**

Add `.sheet(item: $selectedProfileSource)` to the drawer panel:
```swift
.sheet(item: $selectedProfileSource) { source in
    FriendProfileView(source: source)
        .environment(appState)
}
```

- [ ] **Step 5: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 6: Commit**

```bash
git add TravelMap/Components/CityDrawerView.swift
git commit -m "feat: make friend/guide rows tappable in CityDrawerView"
```

---

### Task 9: Make source label tappable in PinDetailSheet

**Files:**
- Modify: `TravelMap/Views/Map/PinDetailSheet.swift`

- [ ] **Step 1: Add state for profile sheet**

Add to PinDetailSheet:
```swift
@State private var selectedProfileSource: ProfileSource?
```

- [ ] **Step 2: Add tappable source label**

In the detail sheet, after the pin title (the `Text(name)` around line 108), add a conditional: if the pin has a `sourceLabel` (meaning it's a friend/guide pin), show the owner's name as a tappable link.

```swift
// After the title Text(name)
if case .saved(let pin) = source, pin.sourceLabel != nil {
    if let profileSource = appState.profileSource(forPinId: pin.id) {
        Button {
            selectedProfileSource = profileSource
        } label: {
            HStack(spacing: 4) {
                Text("by \(profileSource.name)")
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.Colors.accentBlue)
                Image(systemName: "chevron.right")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.Colors.accentBlue)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 4)
    }
}
```

- [ ] **Step 3: Add sheet**

Add to PinDetailSheet body:
```swift
.sheet(item: $selectedProfileSource) { source in
    FriendProfileView(source: source)
        .environment(appState)
}
```

- [ ] **Step 4: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 5: Commit**

```bash
git add TravelMap/Views/Map/PinDetailSheet.swift
git commit -m "feat: make friend/guide name tappable on pin detail sheet"
```

---

### Task 10: Handle mapFocusSource in MapContainerView

**Files:**
- Modify: `TravelMap/Views/Map/MapContainerView.swift`

- [ ] **Step 1: Add map focus filter banner**

In MapContainerView, add a computed property that checks `appState.mapFocusSource`:
- When set, `filteredPins` should return empty (hide user's pins)
- `filteredFriendGuidePins` should return only that person's pins
- Show a banner overlay at the top: "Viewing [Name]'s pins" with X button

Add an overlay banner in the body ZStack:
```swift
// Focus mode banner
if appState.mapFocusSource != nil {
    VStack {
        HStack {
            Text("Viewing \(appState.mapFocusSource!.name)'s pins")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(Theme.Colors.text)
            Spacer()
            Button {
                appState.mapFocusSource = nil
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 20))
                    .foregroundStyle(Theme.Colors.textMuted)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Theme.Colors.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: Theme.Shadow.cardShadowColor,
                radius: Theme.Shadow.cardShadowRadius,
                y: Theme.Shadow.cardShadowY)
        .padding(.horizontal, 12)
        .padding(.top, 100)  // Below the top bar
        Spacer()
    }
}
```

- [ ] **Step 2: Modify filtered pin computed properties**

Update `filteredPins` and `filteredFriendGuidePins` to respect `mapFocusSource`:
```swift
private var filteredPins: [Pin] {
    if appState.mapFocusSource != nil { return [] }
    let source = appState.pins
    if activeCategories.isEmpty { return source }
    return source.filter { activeCategories.contains($0.category) }
}

private var filteredFriendGuidePins: [Pin] {
    if let focus = appState.mapFocusSource {
        return focus.pins
    }
    var source = appState.visibleFriendPins + appState.visibleGuidePins
    if !activeCategories.isEmpty {
        source = source.filter { activeCategories.contains($0.category) }
    }
    return source
}
```

- [ ] **Step 3: Zoom to fit focused pins**

Add an `.onChange(of: appState.mapFocusSource)` handler that posts a notification to zoom the map to fit all pins. Use a new notification or direct Coordinator access.

Simplest: compute bounding MKMapRect and post a new notification `.zoomToRect`:

```swift
.onChange(of: appState.mapFocusSource?.id) { _, newId in
    if let source = appState.mapFocusSource {
        zoomToFitPins(source.pins)
    }
}
```

Add helper:
```swift
private func zoomToFitPins(_ pins: [Pin]) {
    guard !pins.isEmpty else { return }
    var minLat = pins[0].lat, maxLat = pins[0].lat
    var minLng = pins[0].lng, maxLng = pins[0].lng
    for pin in pins {
        minLat = min(minLat, pin.lat)
        maxLat = max(maxLat, pin.lat)
        minLng = min(minLng, pin.lng)
        maxLng = max(maxLng, pin.lng)
    }
    let centerLat = (minLat + maxLat) / 2
    let centerLng = (minLng + maxLng) / 2
    let spanLat = max((maxLat - minLat) * 1.3, 0.01)
    let spanLng = max((maxLng - minLng) * 1.3, 0.01)
    NotificationCenter.default.post(
        name: .navigateToCity,
        object: nil,
        userInfo: ["lat": centerLat, "lng": centerLng, "spanLat": spanLat, "spanLng": spanLng]
    )
}
```

Update `handleNavigateToCity` in Coordinator to optionally accept custom span:
```swift
@objc private func handleNavigateToCity(_ notification: Notification) {
    guard let lat = notification.userInfo?["lat"] as? Double,
          let lng = notification.userInfo?["lng"] as? Double,
          let map = mapViewRef else { return }
    let spanLat = notification.userInfo?["spanLat"] as? Double ?? 0.05
    let spanLng = notification.userInfo?["spanLng"] as? Double ?? 0.05
    let region = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: lat, longitude: lng),
        span: MKCoordinateSpan(latitudeDelta: spanLat, longitudeDelta: spanLng)
    )
    map.setRegion(region, animated: true)
}
```

- [ ] **Step 4: Handle navigateToPin**

Add `.onChange(of: appState.navigateToPin?.id)`:
```swift
.onChange(of: appState.navigateToPin?.id) { _, newId in
    if let pin = appState.navigateToPin {
        // Navigate map to pin
        NotificationCenter.default.post(
            name: .navigateToCity,
            object: nil,
            userInfo: ["lat": pin.lat, "lng": pin.lng, "spanLat": 0.01, "spanLng": 0.01]
        )
        // Show pin detail after a short delay for map animation
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            selectedDetailSource = .saved(pin)
            showPinDetail = true
            appState.navigateToPin = nil
        }
    }
}
```

- [ ] **Step 5: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 6: Commit**

```bash
git add TravelMap/Views/Map/MapContainerView.swift
git commit -m "feat: handle mapFocusSource and navigateToPin in MapContainerView"
```

---

### Task 11: Rework PlacesView search + tap-to-navigate

**Files:**
- Modify: `TravelMap/Views/Places/PlacesView.swift`

- [ ] **Step 1: Rework search to filter pins directly**

Replace the `groupedData` computed property:

```swift
private var groupedData: [(city: City, pins: [Pin])] {
    let all = appState.pinsGroupedByCity()
    if searchText.isEmpty { return all }
    let query = searchText.lowercased()
    // Filter pins directly by name and notes
    return all.compactMap { group in
        let matchingPins = group.pins.filter {
            $0.name.lowercased().contains(query) ||
            $0.notes.lowercased().contains(query)
        }
        if matchingPins.isEmpty { return nil }
        return (city: group.city, pins: matchingPins)
    }
}
```

- [ ] **Step 2: Add flat search results view**

Add a computed property for flat search results:
```swift
private var searchResults: [(pin: Pin, cityName: String)] {
    guard !searchText.isEmpty else { return [] }
    let query = searchText.lowercased()
    var results: [(pin: Pin, cityName: String)] = []
    for group in appState.pinsGroupedByCity() {
        for pin in group.pins {
            if pin.name.lowercased().contains(query) || pin.notes.lowercased().contains(query) {
                results.append((pin: pin, cityName: group.city.name))
            }
        }
    }
    return results
}
```

- [ ] **Step 3: Update body to switch between accordion and flat search**

In the body, replace the city accordions section:
```swift
if searchText.isEmpty {
    // City accordions (unchanged)
    LazyVStack(spacing: 0) {
        ForEach(groupedData, id: \.city.id) { group in
            cityAccordion(group.city, pins: group.pins)
        }
    }
} else if searchResults.isEmpty {
    // No results
    VStack(spacing: 8) {
        Image(systemName: "magnifyingglass")
            .font(.system(size: 32))
            .foregroundStyle(Theme.Colors.textMuted)
        Text("No pins found")
            .font(.system(size: 15))
            .foregroundStyle(Theme.Colors.textMuted)
    }
    .frame(maxWidth: .infinity)
    .padding(.top, 40)
} else {
    // Flat search results
    LazyVStack(spacing: 0) {
        ForEach(searchResults, id: \.pin.id) { result in
            searchResultRow(result.pin, cityName: result.cityName)
        }
    }
}
```

- [ ] **Step 4: Add search result row with tap-to-navigate**

```swift
private func searchResultRow(_ pin: Pin, cityName: String) -> some View {
    Button {
        navigateToPin(pin)
    } label: {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Circle()
                    .fill(pin.category.color)
                    .frame(width: 10, height: 10)
                VStack(alignment: .leading, spacing: 3) {
                    Text(pin.name)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(Theme.Colors.text)
                    Text(cityName)
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.Colors.textSecondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.Colors.textMuted)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)

            Rectangle()
                .fill(Theme.Colors.border)
                .frame(height: 0.5)
                .padding(.leading, 50)
        }
    }
}
```

- [ ] **Step 5: Make accordion pin rows tappable too**

Update `pinRow` to wrap in a `Button` that calls `navigateToPin`:

```swift
private func pinRow(_ pin: Pin, cityId: String) -> some View {
    let distance = distanceFromCity(pin: pin, cityId: cityId)
    return Button {
        navigateToPin(pin)
    } label: {
        VStack(spacing: 0) {
            // ... existing row content unchanged
        }
    }
}
```

- [ ] **Step 6: Add navigateToPin helper**

```swift
private func navigateToPin(_ pin: Pin) {
    appState.navigateToPin = pin
    appState.selectedTab = .map
}
```

- [ ] **Step 7: Verify it compiles**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: BUILD SUCCEEDED

- [ ] **Step 8: Commit**

```bash
git add TravelMap/Views/Places/PlacesView.swift
git commit -m "feat: rework Places search to filter pins directly, add tap-to-navigate"
```

---

### Task 12: Final integration build + smoke test

**Files:** All modified files

- [ ] **Step 1: Full clean build**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' clean build 2>&1 | tail -20`
Expected: BUILD SUCCEEDED

- [ ] **Step 2: Verify no warnings for new code**

Run: `cd /Users/leoseltzer/Desktop/TravelMap && xcodebuild -scheme TravelMap -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | grep -i warning | head -20`
Expected: No new warnings from our files

- [ ] **Step 3: Commit any final fixes**

If any build fixes were needed:
```bash
git add -A
git commit -m "fix: resolve build issues from integration"
```

---

### Task 13: Update CLAUDE.md

**Files:**
- Modify: `/Users/leoseltzer/CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md with new features**

Update the file map, architecture notes, and known issues to reflect:
- New files: `ProfileSource.swift`, `FriendProfileView.swift`
- Friend/Guide models now have `collections` field
- AppState has transient navigation state (`selectedTab`, `mapFocusSource`, `navigateToPin`)
- PlacesView search now filters pins directly
- Navigation from Places/Profile/Drawer/PinDetail to map

- [ ] **Step 2: Commit**

```bash
git add /Users/leoseltzer/CLAUDE.md
git commit -m "docs: update CLAUDE.md with friend profiles and places search features"
```
