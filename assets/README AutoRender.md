# 🎭 1vmo Auto Render v3

## 🎯 User Guide

### Input Controls
- 📥 Select: Add videos to the processing list
- 🗑️ Delete: Remove selected videos from the list
- ❓ Help: Show this user guide
- 🔄 Updates: Check for new versions on GitHub

### Config Management
- Filter: Use the dropdown to filter encoders by group (Resolution, 1vmo Ultimate, Sound, Color & Effect, Image, Blur, Quality, Zoom, Metadata & Text, Frame, Text)
- Encoder Controls:
  - ♻️ Add: Add a new encoder
  - 🛠️ Edit: Edit the current encoder
  - 🗑️ Delete: Delete the selected encoder
  - 🔄 Refresh: Reload the encoder list
- Hover over ℹ️ to see detailed encoder tooltips.

### Render Modes
- Single Render:
  - Choose multiple encoders from the list
  - Each video is processed with each encoder independently
  - Produces one output file per encoder selected
- X Render:
  - Choose up to 5 encoders in processing order
  - Video is processed sequentially through the chain
  - Result is a single output file that has passed through every step
  - Shows detailed progress for each stage

### Output Controls
- 📍 Directory: Choose the folder for output videos
- 📂 Open: Open the output folder
- 🚀 Start: Begin rendering
- 🛑 Stop: Stop rendering

### Output List
Shows information about processed files:
- Index number
- Source filename
- Output filename
- Duration (Loading… while processing)
- Resolution (Loading… while processing)
- Status:
  - 🟡 Processing: In progress
  - 🟢 Completed: Done
  - 🔴 Error: Failed (with error details)