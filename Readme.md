<p align="center">
  <img src="https://files.catbox.moe/ompn1o.jpg" width="100%" alt="Animated Header" />
</p>

<h1 align="center">
  🎵 SOURCE VENOM 🎵
</h1>

<p align="center">
  <b>The Most Advanced, Lightning-Fast, and Highly Optimized Telegram Music Bot</b><br>
  <i>Crafted with Passion by Abdallah</i>
</p>

<p align="center">
  <a href="https://t.me/p_x_4bot">
    <img src="https://files.catbox.moe/eh780q.jpg" width="700" style="border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.5);" alt="Source Venom Banner">
  </a>
</p>

<p align="center">
  <a href="https://t.me/p_x_4bot"><img src="https://img.shields.io/badge/🤖_Try_Bot-@p__x__4bot-1E1E1E?style=for-the-badge&logo=telegram&logoColor=white"/></a>
  <a href="https://t.me/Abdallah"><img src="https://img.shields.io/badge/👨‍💻_Developer-Abdallah-1E1E1E?style=for-the-badge&logo=github&logoColor=white"/></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white"/></a>
  <a href="https://github.com/Pyrogram/Pyrogram"><img src="https://img.shields.io/badge/Framework-Pyrogram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white"/></a>
</p>

<p align="center">
  <a href="https://github.com/Abdallah/SourceVenom/stargazers"><img src="https://img.shields.io/github/stars/Abdallah/SourceVenom?color=success&style=flat-square"/></a>
  <a href="https://github.com/Abdallah/SourceVenom/network/members"><img src="https://img.shields.io/github/forks/Abdallah/SourceVenom?color=important&style=flat-square"/></a>
  <a href="https://github.com/Abdallah/SourceVenom/issues"><img src="https://img.shields.io/github/issues/Abdallah/SourceVenom?color=critical&style=flat-square"/></a>
</p>

<hr>

## 📑 Table of Contents
1. [About The Project](#-about-the-project)
2. [Key Features](#-key-features)
3. [Prerequisites](#-prerequisites)
4. [Environment Variables](#-environment-variables)
5. [Deployment Guides](#-deployment-guides)
   - [VPS / Local Machine (Ubuntu/Debian)](#1-vps--local-machine-ubuntudebian)
   - [Docker Deployment](#2-docker-deployment)
   - [Fly.io Deployment](#3-flyio-deployment)
   - [Heroku Deployment](#4-heroku-deployment)
6. [Commands List](#-commands-list)
   - [User Commands](#user-commands)
   - [Admin Commands](#admin-commands)
   - [Sudo Commands](#sudo-commands)
7. [Troubleshooting & FAQ](#-troubleshooting--faq)
8. [Changelog](#-changelog)
9. [Support & Contact](#-support--contact)
10. [License & Credits](#-license--credits)

<hr>

## 📖 About The Project

**Source Venom** is a fully customized, next-generation Telegram Voice Chat Music Bot. Originally conceptualized to provide zero-latency audio and video streaming, this bot leverages the true power of **PyTgCalls 3.x** and **Pyrogram**.

Unlike traditional bots that suffer from lag and buffering, Source Venom uses optimized FFmpeg flags, direct API fetching for YouTube streams, and local caching mechanisms. It is designed to handle massive traffic across thousands of groups simultaneously without dropping a single frame.

<hr>

## 🚀 Key Features

* **⚡ Zero-Latency Streaming:** Engineered with native `ntgcalls` integration for seamless audio/video playback.
* **🎧 Multi-Platform Support:** Streams directly from YouTube, Spotify, Apple Music, Resso, SoundCloud, and local files.
* **🎮 Full Playback Control:** Play, Pause, Resume, Skip, Stop, Mute, Unmute, and Volume Control.
* **👥 Smart Queue System:** Advanced queuing with loop, shuffle, and auto-play functionalities.
* **🌐 Multi-Language:** Built-in support for multiple languages including English, Arabic, and more.
* **👮 Group Management:** Ban, mute, promote, demote, and manage your group directly through the bot.
* **🗄️ Database Driven:** Uses MongoDB for persistent storage of playlists, sudo users, and chat configurations.
* **🎨 Custom Thumbnails:** High-quality, dynamically generated thumbnails for currently playing tracks.
* **🤖 Auto-Leave:** Automatically leaves the voice chat when the group is empty to save server resources.
* **🛡️ Secure:** Owner and Sudo level permissions to prevent unauthorized access to core bot functions.

<hr>

## 🛠 Prerequisites

Before you begin, ensure you have met the following requirements:
* **Python 3.9 to 3.13** installed on your machine.
* **FFmpeg** installed and added to your system PATH.
* **Node.js** (Optional, but recommended for some yt-dlp extra features).
* **MongoDB** database cluster (You can get a free one at [MongoDB Atlas](https://www.mongodb.com/)).
* A Telegram **Bot Token** from [@BotFather](https://t.me/BotFather).
* A Telegram **API ID** and **API HASH** from [my.telegram.org](https://my.telegram.org/).
* A Pyrogram V2 **String Session** from a session generator bot.

<hr>

## 🔐 Environment Variables

You must create a `.env` file in the root directory of the project. Here is the complete list of all acceptable variables:

### 🔴 Mandatory Variables
```env
API_ID=1234567 # Your Telegram API ID
API_HASH=your_api_hash_here # Your Telegram API HASH
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11 # From @BotFather
OWNER_ID=123456789 # Your Telegram User ID
LOGGER_ID=-1001234567890 # A Private Group/Channel ID for bot logs
STRING_SESSION=your_pyrogram_string_session # Assistant Account Session
MONGO_DB_URI=mongodb+srv://user:pass@cluster.mongodb.net/ # MongoDB URI
# limits
DURATION_LIMIT=900 # Max song duration in minutes (Default: 900)
SONG_DOWNLOAD_DURATION=180 # Max download duration

# Assistant Details
ASSISTANT_PREFIX=1 # Command prefix for assistant (Default: 1)
AUTO_LEAVING_ASSISTANT=True # Assistant leaves when chat is empty

# APIs for specific platforms
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# Customization
START_IMG_URL=[https://files.catbox.moe/eh780q.jpg](https://files.catbox.moe/eh780q.jpg)
PING_IMG_URL=[https://files.catbox.moe/ompn1o.jpg](https://files.catbox.moe/ompn1o.jpg)
SUPPORT_CHANNEL=[https://t.me/SourceVenom](https://t.me/SourceVenom)
SUPPORT_GROUP=[https://t.me/SourceVenomGroup](https://t.me/SourceVenomGroup)

# YouTube Cookies (Crucial for Age-Restricted Content)
COOKIE_URL=[https://pastebin.com/raw/your_cookie_link](https://pastebin.com/raw/your_cookie_link)
<hr>
​💻 Deployment Guides
​Deploying Source Venom is straightforward. Choose the method that best suits your infrastructure.
​1. VPS / Local Machine (Ubuntu/Debian)
​This is the recommended method for maximum performance and 24/7 uptime.
​<details>
<summary><b>Click to expand VPS instructions</b></summary>


​Step 1: Update the system and install required packages:
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y ffmpeg python3-pip python3-venv git tmux build-essential gcc python3-dev
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y ffmpeg python3-pip python3-venv git tmux build-essential gcc python3-dev
Step 2: Clone the repository:
git clone [https://github.com/Abdallah/SourceVenom.git](https://github.com/Abdallah/SourceVenom.git)
cd SourceVenom
Command Description
/play <song name> Plays the requested song in the voice chat.
/vplay <video name> Plays the requested video in the voice chat.
/playforce <song> Force plays a song, overriding the current queue.
/song <name> Downloads the song and sends it as an audio file.
/video <name> Downloads the video and sends it as an mp4 file.
/queue Displays the current playing queue.
/lyrics <song> Fetches the lyrics of the requested song.
/search <query> Searches YouTube and provides interactive download links.
/ping Shows the bot's latency and system stats.
/help Displays the interactive help menu.
Sudo Commands
(Can only be used by the Owner and Sudo Users)
| Command | Description |
| :--- | :--- |
| /addsudo <reply/username> | Adds a user to the sudoers list. |
| /delsudo <reply/username> | Removes a user from the sudoers list. |
| /sudolist | Shows the list of all sudo users. |
| /broadcast <message> | Broadcasts a message to all served chats. |
| /logs | Fetches the latest system logs as a document. |
| /update | Fetches updates from the upstream GitHub repository. |
| /reboot or /restart | Restarts the bot instance. |
| /maintenance | Toggles maintenance mode (Disables bot for normal users). |
| /leaveall | Forces the assistant to leave all voice chats. |
<hr>
🔧 Troubleshooting & FAQ
Q1: The bot joins the call but there is no sound?
Fix 1: Ensure the Voice Chat is turned on before playing a song.
Fix 2: Check if the Assistant account is muted by the group admin.
Fix 3: Make sure your VPS/Server has ffmpeg installed properly.
Q2: I get a FloodWait error when starting the bot?
Reason: Telegram rate-limits your bot if you restart it too many times in a short period.
Fix: Wait for the specified time in the error log (usually 1 hour) or revoke the bot token via @BotFather and generate a new one.
Q3: The Assistant account got banned!
Reason: Telegram occasionally bans user accounts acting as bots.
Fix: Use a secondary phone number to create the assistant. Avoid using your primary personal account for the STRING_SESSION.
Q4: YouTube age-restricted videos won't play.
Fix: Extract your YouTube cookies, upload them to Pastebin (raw format), and place the link in the COOKIE_URL variable in your .env file.
Q5: TgCrypto failed to build during Docker deployment.
Fix: Ensure gcc, python3-dev, and build-essential are included in your Dockerfile (already fixed in Source Venom's native Dockerfile).
<hr>
🔄 Changelog
Version 3.1.0 (2026 Edition)
Upgraded Core: Migrated completely to PyTgCalls 3.x Native Engine.
Python Support: Full compatibility with Python 3.13.
Optimized Queries: Replaced all redundant for loops in YouTube API fetches with direct indexing [0] for lightning-fast lookups.
UI Overhaul: Replaced cluttered thumbnail designs with minimalistic and highly professional aesthetic.
Error Handling: Implemented **kwargs unpacking in MediaStream to permanently fix NoneType video parameter crashes.
Dependencies: Updated yt-dlp, pyrogram, and aiohttp to their absolute latest stable versions.
<hr>
🤝 Support & Contact
We welcome contributions, bug reports, and feature requests!
Telegram Support: Join Source Venom Community
Developer: Abdallah Coder
Bug Tracker: Please use the GitHub Issues tab to report any bugs.
If you like this project, please consider giving it a ⭐ on GitHub!
<hr>
©️ License & Credits
Source Venom is distributed under the MIT License.
Fully optimized, customized, and maintained by Abdallah.
Core Audio Framework provided by the amazing PyTgCalls team.
Telegram API interactions handled flawlessly by Pyrogram.
<p align="center">
<i>"Code is poetry. Make it sing." - Source Venom 2026</i>
</p>
