<div align="center">

# 📹 Percepta

### **Automated Tapo CCTV Footage Downloader, Storage Lifecycle & Monitoring System**

*Lightweight • Low Resource • Raspberry Pi Friendly • Sequential Wi-Fi Sync • Web Video Player*

[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Optimized-C51A4A?style=for-the-badge&logo=raspberry-pi&logoColor=white)](https://www.raspberrypi.com/)

<br/>

[Key Features](#-key-features) •
[Architecture](#-system-architecture) •
[Prerequisites](#-prerequisites) •
[Quick Start](#-quick-start) •
[Camera Setup](#-camera-configuration) •
[External Storage Guide](#-external-storage-setup-raspberry-pi) •
[GitHub Automated Backup](#-automated-github-backup) •
[API Reference](#-api-reference) •
[Troubleshooting](#-troubleshooting--faq)

</div>

---

## 🌟 Overview

**Percepta** is a containerized CCTV automation and footage manager tailored for **TP-Link Tapo cameras**. Engineered from the ground up to run reliably on resource-constrained devices such as **Raspberry Pi (3 / 4 / 5)** with connected external USB drives, as well as home servers (Ubuntu, Debian) and NAS setups.

It eliminates manual MicroSD card pulling by automatically downloading daily footages, structuring them cleanly by date and camera, actively protecting the host from high RAM crashes, compressing completed weeks into ZIP archives, and purging data older than 30 days.

---

## ✨ Key Features

| Feature | Details |
| :--- | :--- |
| 📁 **Dynamic Folder Organization** | Organizes clips into `{Storage_Path}/{YYYY-MM-DD}/{Camera_Name}/{start}_{end}.mp4`. Adding new cameras automatically spawns individual folders under every new date. |
| 🛡️ **Raspberry Pi 90% RAM Guard** | Continuously monitors host memory. If RAM usage reaches **90%** (user-configurable via GUI slider), downloads automatically pause and throttle to prevent Raspberry Pi system crashes. |
| 📶 **Sequential Wi-Fi Optimization** | Downloads cameras **strictly one-by-one** (and clip-by-clip) with buffer tuning (`window_size`) to prevent Wi-Fi bandwidth congestion and dropped packets. |
| 📦 **Weekly Archival & 30-Day Purge** | Automatically compresses previous week's footage into verified ZIP archives every Sunday at midnight, cleaning raw files. Automatically purges data older than 30 days. |
| 🎥 **Web Player with Timeline Seeking** | Responsive Web GUI with date/camera tree explorer. Integrated HTML5 video player supporting **HTTP 206 Partial Content (Range requests)** for smooth timeline scrubbing. |
| 🐙 **Automated Weekly GitHub Backup** | Backs up the entire application codebase and configuration to your private GitHub repository every week via Personal Access Tokens (PAT). |
| 🪵 **Storage Disk Logging** | Rotating logs are written directly to the storage drive at `{Storage_Path}/logs/percepta.log` and viewable in real-time through the GUI terminal. |
| 🔐 **User Accounts & RBAC** | Secure JWT authentication with full user management (create users, delete users, change passwords, role permissions). |

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Cameras["📷 Tapo CCTV Cameras"]
        CAM1["Living Room (192.168.1.109)"]
        CAM2["Front Door / Yard Cameras"]
    end

    subgraph Percepta["🐳 Percepta Docker Container (Port 8585)"]
        API["⚡ FastAPI Web Server & REST API"]
        Worker["🔄 Sequential Downloader (pytapo + ffmpeg)"]
        RAMGuard["🛡️ 90% RAM Safeguard (Auto-throttle)"]
        Scheduler["⏰ APScheduler (Daily Sync & Weekly Tasks)"]
        Lifecycle["📦 Storage Lifecycle (Weekly ZIP & 30-Day Purge)"]
        DB[("🗄️ SQLite Database (/app/data)")]
    end

    subgraph Storage["💾 External Storage Volume (/storage)"]
        Footage["📁 Footage: YYYY-MM-DD/CameraName/*.mp4"]
        Archives["📦 Archives: archives/footage_YYYY-MM-DD.zip"]
        Logs["🪵 Logs: logs/percepta.log"]
    end

    subgraph External["🌐 Web Access & Automated Backups"]
        WebUI["💻 Responsive Web GUI (In-Browser Player)"]
        GitHub["🐙 GitHub Remote Repository (Weekly Push)"]
    end

    CAM1 -->|RTSP: 554 / HTTP: 443| Worker
    CAM2 -->|RTSP: 554 / HTTP: 443| Worker
    Worker --> RAMGuard
    Worker --> Footage
    Lifecycle --> Archives
    Scheduler --> Worker
    Scheduler --> Lifecycle
    Scheduler --> GitHub
    API --> Footage
    API --> Logs
    WebUI --> API
```

---

## 📋 Prerequisites

Before installing, make sure your host machine meets the following requirements:

- **Operating System**: Linux (Ubuntu 20.04+, Debian 11+, Raspberry Pi OS 64-bit) or Windows with Docker Desktop.
- **Docker Engine**: `20.10.0+`
- **Docker Compose**: `v2.0.0+`
- **Network**: The host machine must be on the same local network / subnet as your Tapo cameras.

Verify your Docker installation:
```bash
docker --version
docker compose version
```

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/Percepta.git
cd Percepta
```

### 2. Configure Storage Location (Optional)
By default, footage is stored in `./storage` relative to the project directory.

To point footage to an **external USB hard drive or SSD** (e.g. on a Raspberry Pi mounted at `/media/usb_drive`), open `docker-compose.yml` and adjust the storage volume:

```yaml
volumes:
  - ./data:/app/data
  - /media/usb_drive/percepta_storage:/storage
```

### 3. Start the Container
```bash
docker compose up -d --build
```

### 4. Access the Web GUI
Open your web browser and navigate to:
```
http://<YOUR_SERVER_OR_PI_IP>:8585
```

- **Default Username**: `admin`
- **Default Password**: `admin@123`

> [!TIP]
> Change the default admin password immediately under the **User Accounts** tab after first login!

---

## 📷 Camera Configuration

Percepta supports dual capture modes depending on your camera credentials:

| Credentials | Capabilities |
| :--- | :--- |
| **Camera Account**<br/>*(e.g., `homeadmin` / `admin@123`)* | • High-Definition 1080p RTSP Stream Recording<br/>• Zero-CPU stream copy remuxing (`-c:v copy`)<br/>• Independent of TP-Link Cloud servers |
| **Tapo Cloud Account**<br/>*(Cloud Email & Password)* | • Direct download of historical MicroSD recordings<br/>• Stream decryption via `pytapo` |

### How to Configure in the Tapo App:
1. Open the **Tapo App** on your smartphone.
2. Select your camera → tap the **Settings (gear icon)** in the top right.
3. Tap **Advanced Settings** → **Camera Account**.
4. Create a username (e.g. `homeadmin`) and password (e.g. `admin@123`).
5. Open **Percepta Web GUI** → **Cameras** → **Add Tapo Camera**:
   - **Name**: `Living_Room` *(used as the folder name)*
   - **IP Address**: `192.168.1.109`
   - **User**: `homeadmin`
   - **Password**: `admin@123`
   - **Tapo Cloud Password**: *(Optional, enter your TP-Link cloud password if you want historical MicroSD card file downloads)*
   - Click **Test Connection** → **Save**.

---

## 💾 External Storage Setup (Raspberry Pi)

When running on a Raspberry Pi, saving video files to an external USB hard drive or SSD prevents MicroSD card wear and disk exhaustion:

1. **Plug in your USB drive** and find its UUID:
   ```bash
   sudo blkid
   ```
2. **Create the mount point**:
   ```bash
   sudo mkdir -p /mnt/cctv_storage
   ```
3. **Configure auto-mount in `/etc/fstab`**:
   ```bash
   # Add this line at the bottom of /etc/fstab (replace YOUR-DRIVE-UUID)
   UUID=YOUR-DRIVE-UUID  /mnt/cctv_storage  ext4  defaults,nofail  0  2
   ```
   Mount it immediately:
   ```bash
   sudo mount -a
   ```
4. **Update `docker-compose.yml`**:
   ```yaml
   volumes:
     - ./data:/app/data
     - /mnt/cctv_storage:/storage
   ```
5. **Restart container**:
   ```bash
   docker compose up -d
   ```

---

## 🛡️ Raspberry Pi Memory Protection

Raspberry Pis can easily freeze or encounter kernel OOM (Out Of Memory) crashes when remuxing video streams if memory is unchecked.

Percepta includes an active **RAM Guard worker**:
- Continuously samples `psutil.virtual_memory().percent`.
- If memory exceeds the threshold (default: **90%**), downloads are automatically paused, forcing immediate Python garbage collection (`gc.collect()`).
- The Web GUI dashboard displays a live RAM health gauge, letting you monitor real-time utilization at a glance.

---

## 🐙 Automated GitHub Backup

Keep your code, customizations, and configurations safe by enabling automated weekly backups:

1. Create an empty **Private Repository** on GitHub (e.g. `percepta-backup`).
2. Go to **GitHub Settings → Developer Settings → Personal Access Tokens → Tokens (classic)**:
   - Generate a new token with the `repo` scope enabled.
3. In Percepta Web GUI, navigate to the **GitHub Backup** tab:
   - **Repository URL**: `https://github.com/your-username/percepta-backup.git`
   - **Personal Access Token**: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - **Branch**: `main`
   - Check **Automated Weekly Sunday Code Backup**.
   - Click **Save GitHub Settings**.
4. Click **Backup to GitHub Now** to verify your token and run an immediate test push!

> [!NOTE]
> Sensitive files, camera passwords, SQLite databases, and video clips are automatically excluded via `.gitignore` to prevent leaking private credentials or exceeding repository limits.

---

## 🗂️ Storage Structure

Footage and logs are organized automatically on your storage volume:

```
/storage
├── 2026-09-23/
│   ├── Living_Room/
│   │   ├── 080000_081500.mp4
│   │   └── 081500_083000.mp4
│   └── Front_Door/
│       ├── 080000_081500.mp4
│       └── 081500_083000.mp4
├── 2026-09-24/
│   └── ...
├── archives/
│   ├── footage_2026-09-10.zip
│   └── footage_2026-09-17.zip
└── logs/
    └── percepta.log
```

---

## 📡 API Reference

Percepta provides a comprehensive RESTful API:

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/auth/login` | `POST` | OAuth2 form login, returns JWT bearer token |
| `/api/auth/me` | `GET` | Get current user profile and role |
| `/api/cameras` | `GET` | List all registered cameras and statuses |
| `/api/cameras` | `POST` | Register a new camera |
| `/api/cameras/test` | `POST` | Test connection & probe camera resolution |
| `/api/cameras/{id}/sync` | `POST` | Trigger immediate sync for a specific camera |
| `/api/cameras/sync-all` | `POST` | Trigger sequential sync across all cameras |
| `/api/storage/browse` | `GET` | Browse dates, camera folders, and video files |
| `/api/storage/stream/{date}/{cam}/{file}` | `GET` | Stream MP4 with HTTP 206 Partial Content (range seeking) |
| `/api/storage/trigger-archive` | `POST` | Manually compress footage older than 7 days |
| `/api/storage/trigger-cleanup` | `POST` | Manually purge footage older than 30 days |
| `/api/settings` | `GET` / `POST` | View and update scheduling, storage path & RAM thresholds |
| `/api/settings/github/backup-now` | `POST` | Trigger immediate code backup to GitHub |
| `/api/system/stats` | `GET` | Live CPU, RAM, Disk, and sync progress metrics |
| `/api/system/logs` | `GET` | Retrieve storage disk logs with level filter |

---

## ❓ Troubleshooting & FAQ

<details>
<summary><b>1. Video player won't seek or scrub smoothly?</b></summary>
Percepta streams video with <code>Accept-Ranges: bytes</code> and <code>206 Partial Content</code> headers. Ensure your browser is not blocking range requests and that the container's port <code>8585</code> is directly accessible without an aggressive caching proxy in between.
</details>

<details>
<summary><b>2. Why does pytapo say "Check tapo tag failed" or "Invalid authentication data"?</b></summary>
TP-Link firmware restricts SD card file downloads to the <b>TP-Link Cloud Account</b> (user group <code>root</code>). If you only entered your Camera Account (<code>third_account</code>), live RTSP footage capture works, but for internal SD card file downloads, you must provide your Tapo Cloud Account password in the camera settings.
</details>

<details>
<summary><b>3. How do I change the Web GUI port?</b></summary>
In <code>docker-compose.yml</code>, modify the port mapping:
<pre><code>ports:
  - "9000:8585" # Changes external port to 9000</code></pre>
</details>

<details>
<summary><b>4. How do I inspect container logs directly?</b></summary>
Run:
<pre><code>docker logs -f percepta</code></pre>
Or view them inside the storage disk at <code>/storage/logs/percepta.log</code>.
</details>

---



<div align="center">

Made with ❤️ for home security & automation enthusiasts.

</div>
