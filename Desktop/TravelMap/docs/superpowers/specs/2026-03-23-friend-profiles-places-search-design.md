# Friend/Guide Profiles + Places Search & Navigation

## Feature 1: Unified Friend/Guide Profile View

### ProfileSource Enum
A `ProfileSource` enum wraps either a `Friend` or `Guide`, exposing uniform computed properties (name, handle, pins, collections).

### FriendProfileView Layout
Top to bottom:
- **Header:** Avatar circle (first initial, color-coded), display name, @handle
- **Stats row:** Pin count, Cities count (unique cities derived from their pins)
- **"View on Map" button:** Switches to Map tab, filters map to only this person's pins, zooms to fit all pins
- **Collections section:** Adaptive grid (same style as CollectionsView), tappable into read-only collection detail
- **Pins section:** Accordion grouped by city, read-only

### Navigation Entry Points
1. **ProfileView** — tap a friend/guide row in My Network
2. **CityDrawerView** — tap a friend/guide row in the sidebar
3. **PinDetailSheet** — tap the friend/guide name (source label) on their pins

### View on Map Behavior
1. Set `AppState.mapFocusSource: ProfileSource?`
2. Switch to Map tab (selectedTab = 0)
3. MapContainerView hides all other pins, shows only that person's pins
4. Map zooms to fit all pins via MKMapRect union
5. Banner at top: "Viewing [Name]'s pins" with X to clear filter

### Mock Data
All 10 friends and 4 guides get 1-2 mock collections each, built from their existing pins.

## Feature 2: Places Search & Pin Navigation

### Search Overhaul
- Empty search: current city accordion view (unchanged)
- Active search: flat list filtering pins by name/notes across all cities
- Result rows: category color dot, pin name (bold), city name subtitle (muted)

### Tap-to-Navigate (all pin rows)
1. Set `AppState.navigateToPin: Pin?`
2. Switch to Map tab
3. MapContainerView flies to pin coordinates
4. Auto-opens PinDetailSheet for that pin
5. Clears `navigateToPin` after handling

Uses same notification pattern as existing `navigateToCity`.
