# Strava to Notion Triathlon Sync

A Python application that automatically syncs your triathlon training activities (swimming, biking, and running) from Strava to a Notion database.

## Features

- 🏊 **Automatic Sync**: Syncs swim, bike, and run activities from Strava to Notion
- ⏰ **Scheduled Updates**: Runs daily via GitHub Actions
- 📊 **Activity Details**: Captures distance, duration, elevation, heart rate, and more
- 🔄 **Smart Updates**: Detects existing activities and updates them instead of creating duplicates
- 🚀 **Manual Trigger**: Run sync manually via GitHub Actions workflow dispatch

## Setup

### Prerequisites

- A Strava account with API access
- A Notion account with an integration and database
- GitHub repository with Actions enabled

### 1. Strava API Setup

1. Go to [Strava API Settings](https://www.strava.com/settings/api)
2. Create an application to get your `Client ID` and `Client Secret`
3. Generate a refresh token using the OAuth flow
4. Save these credentials - you'll need them later

### 2. Notion Setup

1. Create a [Notion integration](https://www.notion.so/my-integrations)
2. Copy the integration token
3. Create a database with the following properties:
   - **Name** (Title)
   - **Type** (Select: Swim, Ride, Run)
   - **Date** (Date)
   - **Distance (km)** (Number)
   - **Duration (min)** (Number)
   - **Elevation (m)** (Number)
   - **Avg Heart Rate** (Number)
   - **Strava ID** (Number)
4. Share the database with your integration
5. Copy the database ID from the URL

### 3. Configure GitHub Secrets

Add the following secrets to your GitHub repository (Settings → Secrets and variables → Actions):

- `STRAVA_CLIENT_ID`: Your Strava application client ID
- `STRAVA_CLIENT_SECRET`: Your Strava application client secret
- `STRAVA_REFRESH_TOKEN`: Your Strava refresh token
- `NOTION_TOKEN`: Your Notion integration token
- `NOTION_DATABASE_ID`: Your Notion database ID

### 4. Enable GitHub Actions

The workflow will run automatically daily at 6 AM UTC. You can also trigger it manually from the Actions tab.

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── sync.yml          # GitHub Actions workflow
├── src/
│   ├── strava.py            # Strava API client
│   ├── notion.py            # Notion API client
│   └── sync.py              # Main sync script
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Local Development

### Installation

```bash
# Clone the repository
git clone https://github.com/ben-du-pont/strava2notion_triathlon.git
cd strava2notion_triathlon

# Install dependencies
pip install -r requirements.txt
```

### Running Locally

Set environment variables:

```bash
export STRAVA_CLIENT_ID="your_client_id"
export STRAVA_CLIENT_SECRET="your_client_secret"
export STRAVA_REFRESH_TOKEN="your_refresh_token"
export NOTION_TOKEN="your_notion_token"
export NOTION_DATABASE_ID="your_database_id"
```

Run the sync:

```bash
cd src
python sync.py
```

Optional environment variables:
- `DAYS_BACK`: Number of days to look back (default: 7)
- `DRY_RUN`: Set to "true" to preview without syncing (default: false)

## Usage

### Manual Sync

1. Go to the "Actions" tab in your GitHub repository
2. Select "Sync Strava to Notion" workflow
3. Click "Run workflow"
4. Optionally adjust the number of days to sync
5. Click "Run workflow" to start

### Scheduled Sync

The workflow runs automatically every day at 6 AM UTC. It syncs activities from the last 7 days by default.

## How It Works

1. **Fetch Activities**: Retrieves activities from Strava API for the specified time period
2. **Filter**: Keeps only triathlon activities (Swim, Ride/Bike, Run)
3. **Transform**: Converts Strava activity data to Notion page properties
4. **Sync**: Creates new pages or updates existing ones based on Strava ID
5. **Report**: Displays statistics about created, updated, and skipped activities

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Troubleshooting

### Activities not syncing

- Verify all GitHub secrets are set correctly
- Check the Actions tab for error logs
- Ensure your Notion database has all required properties
- Verify your Strava API credentials are valid

### Rate Limits

Both Strava and Notion have API rate limits. The default 7-day sync window helps stay within these limits.

## Acknowledgments

- [Strava API](https://developers.strava.com/)
- [Notion API](https://developers.notion.com/)
