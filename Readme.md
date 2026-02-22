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
