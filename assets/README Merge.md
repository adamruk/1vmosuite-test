# 🧩 1vmo Merge v3

## 🎯 User Guide

### Input Controls
- Group 1: Add videos/images to Group 1
- Group 2: Add videos/images to Group 2
- Group 3: Add videos/images to Group 3
- Group 4: Add videos/images to Group 4
- 🎵 Audio: Add an audio file
- Delete: Remove the selected file
- ❓ Help: Show this user guide
- 🔄 Updates: Check for new versions on GitHub

### Configuration
- Number of Videos: Choose how many videos/images to merge (1–4)
- Layout Mode: Choose how to arrange them
  - Single: Process a single video/image
  - Horizontal: Side by side
  - Vertical: Top and bottom
  - Overlay: Secondary video/image layered on top of the primary
  - 2x2 Grid: Four videos/images in a 2x2 grid
- Output Format: Choose the output aspect ratio
  - Free: Keep the original ratio
  - 16:9: Convert to 16:9
  - 9:16: Convert to 9:16
  - 1:1: Convert to square
- Video Ratio (when 2 videos + Horizontal/Vertical are selected):
  - Adjust the size ratio between video 1 and 2
  - Default 5:5 (equal split)
- Audio Source: Choose the audio source
  - Longest: Use audio from the longest video
  - Shortest: Use audio from the shortest video
  - Custom Audio: Use an external audio file
- Audio Mode (when Custom Audio is selected):
  - 🔁 Order: Use audio files in order
  - 🎲 Random: Use audio files randomly
- Overlay Options (when Overlay mode is selected):
  - Overlay Group: Choose which group is layered on top
  - Opacity: Adjust transparency (0–100%)

### Preview
- Shows a preview of the arrangement before rendering
- Updates automatically as you change configuration
- Displays the number of videos/images and the output ratio
- Visualizes the size ratio between videos/images

### Output Controls
- 📍 Directory: Choose the output folder
- 📂 Open: Open the output folder
- ⚡ Boost: Processing speed mode
  - OFF: Normal mode — better quality
  - ON: Fast mode — faster processing
- 🚀 Start: Begin merging
- 🛑 Stop: Stop merging

### Output List
Shows information about processed files:
- Index number
- Source filename
- Output filename
- Duration
- Resolution
- Format
- Status:
  - ⏳ Waiting: Queued
  - 🔄 Processing: In progress
  - 🟢 Completed: Done
  - 🔴 Error: Failed
  - 🟡 Cancelled: Stopped by user

### Notes
- Supports many video formats: MP4, AVI, MKV, MOV, WMV, FLV, WEBM
- Supports many image formats: JPG, JPEG, PNG, BMP, GIF, TIFF
- Supports many audio formats: MP3, WAV, M4A, AAC, OGG, FLAC, WMA
- Configuration and last-used paths are saved automatically
- Multi-threaded processing (up to 3 threads)