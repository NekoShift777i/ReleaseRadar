# ReleaseRadar

[English](README.md) | [Русский](README-RU.md)

ReleaseRadar is an automated software release monitoring system that sends notifications through Telegram.

It periodically checks configured repositories, compares detected versions with the saved state, and notifies the user when updates are available.

## Features

- Monitor releases on GitHub and GitLab.
- Support stable and prerelease versions.
- Configure GitHub release filtering.
- Use personal API access tokens.
- Check multiple applications concurrently.
- Configure the automatic check interval.
- Manually check individual applications or the entire list.
- Receive update notifications through Telegram.
- Confirm installation of detected versions.
- Skip individual releases and provide a reason.
- View the history of skipped releases.
- Protect against repeated clicks and expired buttons.
- Store application state in SQLite.
- Configure the time zone.
- Run as a Linux service with systemd.

## Supported release sources

- **GitHub** — retrieve releases through the GitHub API.
- **GitLab** — retrieve releases through the GitLab API, including self-hosted GitLab instances.

## Notifications and management

ReleaseRadar uses a Telegram bot for notifications and management.

The bot can check for updates, show application status, confirm that new versions have been installed, and skip specific releases.

Management commands are restricted to the configured user in a private Telegram chat.

# Installation

ReleaseRadar is designed to run on a Linux server. Installation requires Python 3.12 or a compatible version, Git, and internet access.

## Prepare the environment

Install the required system packages.

On Ubuntu and Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git
```

Verify that Python is available:

```bash
python3 --version
```

## Get the source code

Clone the ReleaseRadar repository:

```bash
git clone https://github.com/NekoShift777i/ReleaseRadar.git releaseradar
cd releaseradar
```

## Python virtual environment

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Upgrade the package installer:

```bash
python -m pip install --upgrade pip
```

Install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

The main dependencies are installed automatically, including libraries for Telegram, HTTP requests, YAML parsing, and environment-variable loading.

## Initial configuration

Prepare two files before starting:

- `config.yaml` — check settings and the list of monitored applications.
- `.env` — sensitive Telegram settings and access tokens.

### The .env file

Create `.env` in the project root.

Minimal example:

```dotenv
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=123456789
```

Replace these placeholders with actual values.

`TELEGRAM_BOT_TOKEN` is the Telegram bot token.

`TELEGRAM_CHAT_ID` is the numeric identifier of the user authorized to manage the bot.

If needed, `.env` also contains GitHub and GitLab access tokens. Their environment-variable names are specified in the application configuration.

Do not publish `.env` or commit real access tokens to the repository.

### The config.yaml file

Create `config.yaml` in the project root.

It contains general update-check settings, monitored applications, release-source settings, and release filters.

The next section describes these options in detail.

## First run

After configuring the files, start ReleaseRadar:

```bash
python main.py
```

With a valid configuration, the application starts running and launches the Telegram bot.

Press Ctrl+C to stop it.

## Protect local data

The `.env` file, SQLite database, virtual environment, and log files are excluded from Git through `.gitignore`.

Before publishing changes, also verify that they do not contain passwords, access tokens, or other sensitive information.

## Running with systemd

For continuous operation on Linux, running ReleaseRadar as a systemd service is recommended.

The service starts automatically after system boot and restarts the application if it crashes.

### Project location

The examples below assume that ReleaseRadar is installed in `/opt/releaseradar`.

If you installed it elsewhere, adjust `WorkingDirectory` and `ExecStart` in the service file.

`WorkingDirectory` is especially important because it determines the locations of `config.yaml`, the SQLite database, and the log file.

Before starting the service, make sure the selected system user has the necessary permissions for the project directory.

### Create the service

Create the file:

```bash
sudo nano /etc/systemd/system/releaseradar.service
```

Example contents:

```ini
[Unit]
Description=ReleaseRadar
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<user>
WorkingDirectory=/opt/releaseradar
ExecStart=/opt/releaseradar/.venv/bin/python /opt/releaseradar/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Replace `<user>` with the system account name.

`WorkingDirectory` and `ExecStart` must match the actual ReleaseRadar installation path.

The selected user needs permission to read configuration files and write to the working SQLite database and log directory.

### Enable the service

After creating or changing the service file, run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now releaseradar.service
```

Check its status:

```bash
systemctl status releaseradar.service
```

### Manage the service

Start:

```bash
sudo systemctl start releaseradar.service
```

Stop:

```bash
sudo systemctl stop releaseradar.service
```

Restart:

```bash
sudo systemctl restart releaseradar.service
```

### View service logs

Last 100 service log lines:

```bash
journalctl -u releaseradar.service -n 100 --no-pager
```

Follow new log entries:

```bash
journalctl -u releaseradar.service -f
```

Logs from the current system boot:

```bash
journalctl -u releaseradar.service -b
```

### Update ReleaseRadar

Before updating, back up the working SQLite database and the `config.yaml` and `.env` files.

Stop the service:

```bash
sudo systemctl stop releaseradar.service
```

Update the project files using your preferred method.

If `requirements.txt` has changed, update the dependencies:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

Start the service after updating:

```bash
sudo systemctl start releaseradar.service
```

Check its status and logs:

```bash
systemctl status releaseradar.service
journalctl -u releaseradar.service -n 50 --no-pager
```

A normal source-code update does not require moving or replacing the working SQLite database.

If the new version changes the database schema, read the release notes first.

# Configuring config.yaml

`config.yaml` contains general ReleaseRadar settings and the list of monitored applications.

The file uses YAML. On startup, ReleaseRadar validates its structure, required fields, and allowed values.

## General settings

| Setting | Description | Default |
|---|---|---|
| `timezone` | Time zone used to display timestamps | `UTC` |
| `check_interval_seconds` | Interval between automatic checks, in seconds | `3600` |
| `max_parallel_checks` | Maximum number of concurrent checks | `4` |
| `notification_button_retention` | Lifetime of notification buttons | `30d` |
| `software` | List of monitored applications | Required |

### Update check interval

`check_interval_seconds` controls the interval between automatic release checks.

The value must be a positive integer expressed in seconds.

Example: check every 30 minutes.

```yaml
check_interval_seconds: 1800
```

A very short interval may exceed GitHub or GitLab API rate limits.

For normal use, start with 3600 seconds (one hour).

### Time zone

`timezone` uses names from the IANA time zone database.

For example:

```yaml
timezone: "Asia/Kamchatka"
```

`timezone` is used when displaying timestamps in application status information.

The `/skipped` command has a separate display rule: skipped-release dates are converted to the `Asia/Kamchatka` time zone regardless of the `timezone` setting.

All skip timestamps are stored in SQLite in UTC. Conversion happens only when displaying them, so changing the display time zone does not modify saved records.

### Concurrent checks

`max_parallel_checks` accepts integers from 1 to 16.

```yaml
max_parallel_checks: 4
```

### Button retention

`notification_button_retention` determines how long release-notification buttons remain valid.

Supported units:

- `h` — hours;
- `d` — days;
- `w` — weeks.

The allowed duration is from 14 to 120 days.

Example:

```yaml
notification_button_retention: 30d
```

## Software list

All monitored applications are defined under `software`.

Example:

```yaml
software:
  - id: xray
    name: Xray-core
    provider: github
    repository: XTLS/Xray-core
    channel: stable
    current_version: "26.10.10"
    enabled: true
```

### Required application fields

| Field | Purpose |
|---|---|
| `id` | Unique application identifier |
| `name` | Display name |
| `provider` | Release source: `github` or `gitlab` |
| `repository` | Repository path |
| `channel` | Release channel: `stable` or `prerelease` |
| `current_version` | Initially configured installed version |
| `enabled` | Enable or disable monitoring |

All listed fields are required.

### Application identifier

`id` must be unique within the list.

Avoid changing an identifier once monitoring has begun: it links the application to its saved SQLite state.

### Release source

Two values are supported:

- `github` — GitHub Releases;
- `gitlab` — GitLab Releases.

A GitHub repository path has the format:

`owner/repository`

GitLab also supports nested groups:

`group/subgroup/project`

Do not enter a full repository URL in `repository`.

### Release channels

`stable` monitors releases after filtering out prerelease versions.

`prerelease` allows prerelease versions to be considered.

The details of prerelease detection depend on the provider and are explained below.

### Installed version

`current_version` sets the initial installed version when the application record is first created.

After that, the installed version is stored in SQLite and changes when an update is confirmed.

Quote version numbers in YAML:

```yaml
current_version: "2.9"
```

This prevents some values from being automatically interpreted as numbers.

### Enable monitoring

```yaml
enabled: true
```

`true` includes the application in checks.

`false` excludes it from checks without requiring you to remove its configuration.

## Additional GitHub settings

### Release filtering

GitHub supports the `release_filter` option.

It determines how ReleaseRadar distinguishes stable releases from prereleases.

Allowed values:

| Mode | Behavior |
|---|---|
| `strict` | Excludes releases marked as prereleases on GitHub and versions recognized as prereleases by their version numbers |
| `github` | Uses only GitHub's prerelease flag |
| `version` | Determines prerelease status using only the version string |

The default is `strict`.

Example:

```yaml
software:
  - id: example
    name: Example
    provider: github
    repository: example/project
    channel: stable
    release_filter: strict
    current_version: "1.0.0"
    enabled: true
```

`release_filter` applies when `channel: stable` is selected.

With `channel: prerelease`, both stable and prerelease versions are allowed regardless of the filtering mode. Draft releases are always excluded.

### Version detection details

GitHub lets maintainers manually mark releases as prereleases.

However, that flag does not always match the version string. For example, a release tagged `v2.0.0-beta.1` may not be marked as a prerelease.

`strict` considers both indicators and is recommended for most applications.

ReleaseRadar uses the `packaging` library to parse version numbers. If a version cannot be parsed, `strict` and `version` cannot determine its prerelease status from the version string itself.

### GitHub access token

An optional environment variable is used for GitHub requests:

```dotenv
GITHUB_TOKEN=YOUR_GITHUB_TOKEN
```

Set the token in `.env`.

If the variable is missing or empty, requests are made without authentication.

A token may be needed for private repositories or to increase the available GitHub API request quota.

If GitHub rejects the token, ReleaseRadar reports an authentication error.

## Additional GitLab settings

### Server URL

`gitlab_url` lets you specify a self-hosted GitLab server.

The default is:

`https://gitlab.com`

Example:

```yaml
software:
  - id: internal-project
    name: Internal Project
    provider: gitlab
    repository: team/internal-project
    gitlab_url: https://gitlab.example.com
    channel: stable
    current_version: "1.0.0"
    enabled: true
```

The URL must use HTTPS.

Additional URL paths, query parameters, and embedded credentials are not allowed.

### GitLab access token

`token_env` specifies the name of the environment variable from which ReleaseRadar reads the access token.

Example in `config.yaml`:

```yaml
token_env: GITLAB_TOKEN
```

Corresponding entry in `.env`:

```dotenv
GITLAB_TOKEN=YOUR_GITLAB_TOKEN
```

`token_env` contains the variable name, not the secret token itself.

If `token_env` is set but the corresponding variable is missing or empty, the check fails.

If `token_env` is omitted, requests are made without an access token.

### Prerelease detection

On GitLab, prerelease status is determined from the version string.

The following markers are recognized by default:

- `alpha`
- `beta`
- `rc`
- `pre`
- `preview`
- `dev`
- `snapshot`

For example, `v2.0.0-beta.1` and `v3.0.0-rc1` are considered prereleases.

Use `prerelease_pattern` to customize these rules.

Example:

```yaml
prerelease_pattern: '(?i)(?:alpha|beta|rc|dev)'
```

The value is a Python regular expression.

If omitted, the built-in expression is used.

Invalid regular expressions are rejected during configuration validation.

The `stable` channel excludes prereleases.

The `prerelease` channel allows both release types.

### GitLab release selection details

GitLab releases are checked by publication date (`released_at`).

ReleaseRadar excludes releases whose publication dates are in the future and selects the most recently published release that matches the chosen channel.

This differs from GitHub, where matching releases are selected using parsed and compared version numbers.

# Telegram management

ReleaseRadar provides commands to view application status, manually check for updates, and manage detected releases.

Management is available only to the owner specified by `TELEGRAM_CHAT_ID`, in a private chat with the bot.

## Available commands

| Command | Purpose |
|---|---|
| `/status` | Show monitored application status |
| `/check` | Run a manual update check |
| `/pending` | Resend notifications about unconfirmed updates |
| `/confirm` | Confirm installation of a detected update |
| `/skipped` | Show skipped-release history |

## View status — /status

Shows information about monitored applications based on their saved state.

You can view installed and detected versions, as well as check status.

## Manual check — /check

After invoking the command, the bot displays a list of enabled applications.

Select an individual application or press “Check all”.

If there are many applications, the list is paginated with eight applications per page.

A check that is already running or queued cannot be started again.

Check results are sent in a separate message.

## Repeat notifications — /pending

Resends notifications for available updates that have not yet been confirmed.

Before sending, ReleaseRadar queries the source again and verifies that the release is still current.

Skipped releases are excluded from repeated notifications.

This command does not change the installed version or confirm updates.

## Confirm installation — /confirm

Shows applications with detected but unconfirmed updates.

After you select an application, the bot asks you to confirm installation of the detected version.

Confirmation updates the saved installed version in SQLite.

The command does not actually install software on the server or any other device.

The confirmation request is checked for validity before the state is changed.

A confirmation request expires after one hour.

## Skip a release

New-release notifications include a “Skip version” button.

When pressed, the bot asks for a reason. Send the reason as a normal text message.

The maximum reason length is 1,000 characters.

You can cancel the request using the “Cancel” button.

Skipping a release does not change the application's installed version.

Repeated notifications for that release are suppressed, but subsequent releases continue to be monitored.

Only one unfinished reason-entry request per user is allowed at a time.

## Skip history — /skipped

Shows the 20 most recently skipped releases.

For each release, the bot displays:

- application name;
- version number;
- reason for skipping;
- date and time of the skip.

Times are displayed in the Kamchatka time zone.

If the database contains more than 20 records, the bot reports the total number of skipped releases.

The full history remains in SQLite even when some records are not displayed by the command.

## Button handling

Notification buttons have a limited lifetime set by `notification_button_retention`.

When a button is pressed, ReleaseRadar checks that the button is valid and the release is still current.

Repeated presses must not result in duplicate confirmations or skips.

Separate request identifiers are used for canceling reason entry. An outdated cancel button cannot cancel another request.

## Access restrictions

Only the configured owner can manage the bot, and only in a private Telegram chat.

The numeric `TELEGRAM_CHAT_ID` identifies the owner.

Do not share your Telegram bot token with anyone else.

# Data storage

ReleaseRadar uses SQLite to store application state, skipped-release history, and notification button information.

## Database location

The default database file is:

`release-radar.db`

Its path is relative to the ReleaseRadar process working directory.

When running under systemd, the working directory is defined by `WorkingDirectory`.

The database and required tables are created on the first run.

## Database structure

| Table | Purpose |
|---|---|
| `software_state` | Installed and detected versions, check details, and errors |
| `notification_buttons` | Notification button identifiers and creation timestamps |
| `skipped_releases` | Skipped-release history, reasons, and timestamps |

In `skipped_releases`, the combination of application identifier and version is unique.

Skipping the same release again does not create a new record or replace the previously saved reason.

## State persistence

SQLite data persists across application restarts.

The initial version comes from `config.yaml`; afterward, the installed version is stored in the database.

Deleting the database loses saved state, skip history, and notification button records.

If the database is recreated, initial application state is taken from the configuration.

## Backups

Create a backup before updates, migrations, or database schema changes.

The simplest method is to stop the service and copy the database file.

Example for an installation in `/opt/releaseradar`:

```bash
sudo systemctl stop releaseradar.service
cp /opt/releaseradar/release-radar.db \
   /opt/releaseradar/release-radar.db.backup
sudo systemctl start releaseradar.service
```

The copy command assumes the current user has the necessary permissions.

When moving ReleaseRadar to another server, keep its working database separate from the development environment database.

# Troubleshooting

## Application logs

ReleaseRadar writes operational messages to:

`release-radar.log`

Messages are also written to standard output, so you can inspect them with `journalctl` when running under systemd.

View the last 100 log lines:

```bash
journalctl -u releaseradar.service -n 100 --no-pager
```

Follow new log entries:

```bash
journalctl -u releaseradar.service -f
```

Logs may contain information about checks, detected versions, release-fetching errors, and Telegram bot operation.

ReleaseRadar masks known secret-token formats and values of secret environment variables.

Nevertheless, inspect logs before sharing them with third parties.

## config.yaml errors

If the application cannot start due to a configuration error, check:

- YAML indentation;
- required settings;
- uniqueness of application identifiers;
- allowed `provider` and `channel` values;
- repository paths;
- additional settings.

YAML syntax errors may include line and column numbers.

## Telegram errors

If the bot does not respond, check that these variables are set:

- `TELEGRAM_BOT_TOKEN`;
- `TELEGRAM_CHAT_ID`.

Verify that the token is valid, the numeric identifier is correct, and the server can reach Telegram.

Management commands are intended for the configured owner's private chat.

## GitHub and GitLab errors

If releases cannot be retrieved, check:

- source server availability;
- the `repository` path;
- whether the repository has releases;
- access token validity, if a token is used;
- API rate limits;
- the selected release channel;
- prerelease filtering settings.

For GitLab, also check `gitlab_url` and the `token_env` variable name.

A missing matching release does not necessarily indicate an error: the selected rules may have filtered it out.

## Database errors

If ReleaseRadar cannot save state, check:

- that the working directory exists;
- that the service user has write permissions;
- available disk space;
- accessibility of `release-radar.db`;
- SQLite error messages in the logs.

Do not delete the working database to fix an error without identifying the cause and creating a backup.

## Service fails to start

Check its status:

```bash
systemctl status releaseradar.service
```

Then inspect logs for the current boot:

```bash
journalctl -u releaseradar.service -b --no-pager
```

Verify `WorkingDirectory`, `ExecStart`, and the presence of the Python virtual environment.

After modifying the service file, run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart releaseradar.service
```

If the service starts but the application does not work correctly, inspect its own log and configuration.
