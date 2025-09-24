# Reposter

## Description

`Reposter` is an automated tool for synchronizing and reposting content between VK.com, Telegram and Boosty social networks. The application periodically checks for new posts in specified VK sources, processes them (including downloading media files using yt-dlp), and publishes them to target Telegram channels or Boosty blogs. Flexible configuration of reposting rules and download parameters is supported.

## Features

* **Automated Monitoring:** Periodic checking for new posts in VK (from group walls or VK Donut).
* **Flexible Reposting Rules:** Configuration of bindings between VK sources and target Telegram channels or Boosty blogs.
* **Media Processing:** Downloading videos and audio from various platforms (via yt-dlp) and their subsequent publication.
* **Telegram Support:** Sending text messages, photos, videos, audio, and documents to Telegram channels.
* **Boosty Support:** Publishing posts with videos and text to Boosty blogs.
* **Session Management:** Using Pyrogram session files for Telegram to maintain authorization.
* **Configurable Parameters:** All key application parameters are set via the `config.yaml` file.

## Installation

You can also download a pre-built application from the [Releases](https://github.com/your-username/reposter/releases) section.

1. **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/reposter.git
    cd reposter
    ```

2. **Create a virtual environment and install dependencies:**
    Use `uv` (recommended) or `pip`:

    **With uv:**

    ```bash
    uv venv
    source .venv/bin/activate # Linux/macOS
    .venv\Scripts\activate # Windows
    uv pip install -e .
    ```

    **With pip:**

    ```bash
    python -m venv .venv
    source .venv/bin/activate # Linux/macOS
    .venv\Scripts\activate # Windows
    pip install -e .
    ```

## Configuration

The main project configuration is located in the `config.yaml` file. Create this file in the project's root directory if it doesn't exist, and fill it with the following data. Some parameters can also be set via environment variables.

```sh
# Example .env
# --- Core tokens and keys (can also be set via environment variables) ---
VK_SERVICE_TOKEN: Your VK service access key
TELEGRAM_API_ID: Your Telegram API ID
TELEGRAM_API_HASH: Your Telegram API Hash
```

```yaml
# Example config.yaml
# --- Application settings ---
app:
  wait_time_seconds: 600 # Interval between checking for new posts (in seconds). Minimum 1.
  state_file: state.yaml # File name for saving application state (e.g., IDs of last posts).
  session_name: user_session # Pyrogram session name for Telegram.

# --- Reposting rules (list of VK -> Telegram/Boosty bindings) ---
bindings:
  - vk:
      domain: example_vk_group # Short name or ID of the VK group/user (e.g., "apiclub" or "1").
      post_count: 10 # Number of latest posts to check. Minimum 1.
      post_source: wall # Source of posts: "wall" (wall) or "donut" (VK Donut).
    telegram:
      channel_ids: # List of Telegram channel IDs or @usernames where posts will be sent.
        - -1001234567890 # Example channel ID (starts with -100)
        - "@my_telegram_channel" # Example @username channel
    boosty:
      blog_name: my_boosty_blog # Your Boosty blog name (the part after boosty.to/ in the URL)
  - vk:
      domain: example_vk_group # Short name or ID of the VK group/user (e.g., "apiclub" or "1").
      post_count: 10 # Number of latest posts to check. Minimum 1.
      post_source: wall # Source of posts: "wall" (wall) or "donut" (VK Donut).
    telegram:
      channel_ids: # List of Telegram channel IDs or @usernames where posts will be sent.
        - -1001234567890 # Example channel ID (starts with -100)
        - "@my_telegram_channel" # Example @username channel
  - vk:
      domain: example_vk_group # Short name or ID of the VK group/user (e.g., "apiclub" or "1").
      post_count: 10 # Number of latest posts to check. Minimum 1.
      post_source: wall # Source of posts: "wall" (wall) or "donut" (VK Donut).
    boosty:
      blog_name: my_boosty_blog # Your Boosty blog name (the part after boosty.to/ in the URL)
  # - Add other bindings here if needed

# --- Media downloader settings (yt-dlp) ---
downloader:
  browser: chrome # Browser for obtaining cookies (chrome, firefox, edge).
  output_path: downloads # Path for temporary media file downloads.
  yt_dlp_opts: # Additional options for yt-dlp (see yt-dlp documentation).
    format: bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best
  retries:
    count: 3 # Number of file download attempts.
    delay_seconds: 10 # Delay between attempts (in seconds).
  browser_restart_wait_seconds: 30 # Wait time after browser restart.
```

### Obtaining Tokens and Keys

#### Telegram (API ID and API Hash)

To interact with the Telegram API on behalf of a user, you will need `api_id` and `api_hash`.

1. Go to [my.telegram.org](https://my.telegram.org/).
2. Log in to your Telegram account.
3. Click "API development tools".
4. Fill in the fields:
    * **App title:** `Reposter` (or any other name)
    * **Short name:** `reposter`
    * **Platform:** `Desktop`
    * **URL:** (can be left empty)
    * **Description:** (can be left empty)
5. Click "Create app".
6. You will receive `App api_id` and `App api_hash`. Copy them and paste them into `config.yaml` in the corresponding `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` fields (or set them as environment variables).

The first time the application runs with this data, it will ask for your phone number and confirmation code to create a session file (whose name is specified in `app.session_name`), which will be used for subsequent authorization.

#### VK.com (Service Access Key)

To work with the VK API, you will need a **Service Access Token**. This key is used for requests on behalf of the application and does not require user authorization.

1. **Create a Standalone Application:**
    * Go to [My VK Applications](https://vk.com/apps?act=manage).
    * Click "Create application".
    * Select "Standalone application" type.
    * Come up with a name and click "Connect application".
    * In the application settings, go to the "Settings" section.

2. **Get the Service Access Key:**
    * On the "Settings" page of your application, find the "Service Access Token" field.
    * Copy this key.
    * Paste the copied key into `config.yaml` in the `VK_SERVICE_TOKEN` field (or set it as an environment variable).

#### Boosty (Authentication)

To work with the Boosty API, you will need to obtain authentication tokens:

1. **Obtain Tokens:**
    * You need to get `access_token`, `refresh_token`, and `device_id` from the Boosty API.
    * These tokens should be placed in the `auth.json` file in the project root directory.
    * The `auth.json` file should have the following structure:
      ```json
      {
        "access_token": "your_access_token_here",
        "refresh_token": "your_refresh_token_here",
        "device_id": "your_device_id_here",
        "expires_at": 0
      }
      ```

2. **Configure Blog Name:**
    * In your `config.yaml` file, specify the `blog_name` for each Boosty binding.
    * The `blog_name` is the part of the URL after `boosty.to/` in your blog's address.

## Running the Application

After configuring `config.yaml`, you can run the application:

```bash
uv run python -m src.reposter
```

or

```bash
uv run python main.py
```

To run in debug mode, use the `--debug` flag:

```bash
uv run python -m src.reposter --debug
```

## Development

### Running Tests

```bash
uv run pytest tests
```

### Linting Check (ruff)

```bash
uv run ruff check .
```

### Automatic Linting Fix (ruff)

```bash
uv run ruff check --fix .
```

### Formatting Check (ruff format)

```bash
uv run ruff format --check .
```

### Automatic Formatting Fix (ruff format)

```bash
uv run ruff format .
```

### Type Checking (pyright)

```bash
uv run pyright
```
