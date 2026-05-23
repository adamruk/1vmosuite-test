# ✂️ 1vmo Cutter v3

## 🎯 User Guide

### Input Controls
- Videos: Add videos to the cutting list
- Delete: Remove the selected video
- ❓ Help: Show this user guide
- 🔄 Updates: Check for new versions on GitHub

### Configuration
- Cutting Mode: Choose how to cut the video
  - Split by Time: Cut into segments by duration
  - Split by Parts: Cut into equal-length parts
  - Trim Start/End: Trim from both ends of the video
  - Specific Time Range: Cut a custom range by start/end time
- Parameters:
  - Segment Duration: Length of each segment (seconds)
  - Number of Parts: How many parts to produce
  - Start Trim: Time to trim from the start (seconds)
  - End Trim: Time to trim from the end (seconds)
  - Start Time: Start of the time range (seconds)
  - End Time: End of the time range (seconds)

### Output Controls
- 📍 Directory: Choose the output folder
- 📂 Open: Open the output folder
- ⚡ Boost: Processing speed mode
  - OFF: Normal mode — better quality
  - ON: Fast mode — faster processing
- 🚀 Start: Begin cutting
- 🛑 Stop: Stop cutting

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