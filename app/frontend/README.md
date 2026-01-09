# Poker Tournament Chip Tracker

A React-based visualization tool for tracking chip progression across poker tournament hands.

## Prerequisites

- **Node.js** v18 or higher
- **npm** v9 or higher

## Installation

```bash
cd app/frontend
npm install
```

## Starting the Application

### Development Mode

```bash
cd app/frontend
npm run dev
```

The app will be available at http://localhost:5173/

### Expose to Network

To share with colleagues on the same network:

```bash
cd app/frontend
npm run dev -- --host
```

This will display a network URL (e.g., `http://192.168.x.x:5173/`) that others can access.

### Production Build

```bash
cd app/frontend
npm run build
npm run preview
```

## Data Source

The application reads tournament JSON files from `app/data/gamestates/`. These files must follow the format version 3 structure with `hand_summaries`.

### Refreshing Data

When new tournament files are added to `app/data/gamestates/`:

1. **Update the manifest** (lists available files):

```bash
cd app/data/gamestates
ls -1 tournament_*.json | jq -R -s '{ files: split("\n") | map(select(length > 0)) }' > manifest.json
```

Or use the provided script:

```bash
bash app/frontend/scripts/update-manifest.sh
```

2. **Click "↻ Refresh"** in the UI to reload the file list

## Usage

### File Selection

- Use **"Last 5"**, **"Last 10"**, or **"All"** buttons for quick selection
- Click individual files to toggle them
- Files are sorted by timestamp

### Player Filtering

- Click player checkboxes to show/hide their chip lines
- Each player has a unique color

### EV-Adjusted Chips

- Toggle **"Use EV-adjusted chips"** to switch between:
  - **Checked**: Uses `ev_adjusted_chips` when available for a player, falls back to `chips_won`
  - **Unchecked**: Always uses `chips_won`

### Graph Interaction

- Hover over data points to see details
- The tooltip shows:
  - Hand number
  - Source file
  - Chip count per player
  - "(EV)" indicator when EV-adjusted values are used

## File Structure

```
app/frontend/
├── src/
│   ├── App.jsx           # Main application component
│   ├── App.css           # Styles
│   └── components/
│       └── ChipGraph.jsx # Recharts line graph component
├── public/
│   └── gamestates/       # Symlink to app/data/gamestates
├── scripts/
│   └── update-manifest.sh
└── package.json
```

## Tournament File Format

Expected JSON structure (format version 3):

```json
{
  "tournament_id": "abc123",
  "timestamp": "20251215_120000",
  "format_version": 3,
  "players": ["agent_a", "agent_b", ...],
  "hands": [
    {
      "hand_number": 1,
      "starting_stacks": { "agent_a": 1500, ... }
    }
  ],
  "hand_summaries": [
    {
      "hand_number": 1,
      "chips_won": { "agent_a": 100, "agent_b": -100, ... },
      "ev_adjusted_chips": null
    }
  ]
}
```
