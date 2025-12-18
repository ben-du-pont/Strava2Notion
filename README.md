# Strava to Notion Triathlon Sync

Automated GitHub Actions workflow that syncs Strava activities to Notion databases with support for running, cycling, and swimming activities.

## Features

- 🏃 **Sport-Specific Fields**: Automatically uses appropriate fields based on activity type (Run, Ride, Swim)
- 🔄 **Automatic Sync**: Runs hourly via GitHub Actions cron schedule
- ✅ **Duplicate Prevention**: Checks Strava activity ID to avoid duplicate entries
- 🔗 **Planned Activity Linking**: Matches and links completed activities to planned activities
- 📊 **Status Updates**: Automatically marks planned activities as "Done"
- 🛡️ **Error Handling**: Graceful failure handling - errors don't crash the entire sync

## Architecture

The project consists of three main modules:

- **`strava.py`**: Handles Strava API authentication and activity fetching
- **`notion.py`**: Manages Notion database queries, inserts, and updates
- **`sync.py`**: Orchestrates the sync process with branching logic by sport type

## Prerequisites

### Strava Setup

1. Create a Strava API application at https://www.strava.com/settings/api
2. Note your `Client ID` and `Client Secret`
3. Get a refresh token by following Strava's OAuth flow

### Notion Setup

1. Create a Notion integration at https://www.notion.so/my-integrations
2. Note your integration token
3. Create two databases:
   - **Activities Database** with properties:
     - Name (Title)
     - Strava ID (Number)
     - Type (Select: Run, Ride, Swim)
     - Date (Date)
     - Distance (Number)
     - Duration (Number)
     - Elevation (Number)
     - Average Pace (Number) - for Run/Swim
     - Average Speed (Number) - for Ride
     - Average HR (Number) - optional
     - Average Power (Number) - for Ride
     - Cadence (Number) - for Run
     - Planned Activity (Relation to Planned Activities DB)
   - **Planned Activities Database** with properties:
     - Date (Date)
     - Type (Select: Run, Ride, Swim)
     - Status (Status with "Done" option)
4. Share both databases with your integration
5. Copy the database IDs from the URLs

## GitHub Setup

Add the following secrets to your GitHub repository (Settings → Secrets and variables → Actions):

- `STRAVA_CLIENT_ID`: Your Strava application client ID
- `STRAVA_CLIENT_SECRET`: Your Strava application client secret
- `STRAVA_REFRESH_TOKEN`: Your Strava refresh token
- `NOTION_TOKEN`: Your Notion integration token
- `NOTION_ACTIVITIES_DB_ID`: ID of your Activities database
- `NOTION_PLANNED_DB_ID`: ID of your Planned Activities database

## Usage

### Automatic Sync

The workflow runs automatically every hour via GitHub Actions cron schedule.

### Manual Sync

Trigger manually from the Actions tab:
1. Go to the "Actions" tab in your repository
2. Select "Sync Strava to Notion" workflow
3. Click "Run workflow"

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export STRAVA_CLIENT_ID="your_client_id"
export STRAVA_CLIENT_SECRET="your_client_secret"
export STRAVA_REFRESH_TOKEN="your_refresh_token"
export NOTION_TOKEN="your_notion_token"
export NOTION_ACTIVITIES_DB_ID="your_activities_db_id"
export NOTION_PLANNED_DB_ID="your_planned_db_id"

# Run sync
python sync.py
```

## How It Works

1. **Fetch Activities**: Gets activities from Strava from the last 7 days
2. **Check Duplicates**: Skips activities that already exist in Notion (by Strava ID)
3. **Sport Detection**: Identifies sport type (Run/Ride/Swim) and uses appropriate fields
4. **Create Entry**: Creates new activity in Notion Activities database
5. **Match Planned**: Searches for a matching planned activity by date and sport type
6. **Link & Update**: Links the activity to the planned entry and marks it as "Done"

## Sport-Specific Fields

### Running
- Average Pace (min/km)
- Average Heart Rate
- Cadence (steps per minute)

### Cycling
- Average Speed (km/h)
- Average Power (watts)
- Average Heart Rate

### Swimming
- Average Pace (min/100m)

## Error Handling

The sync process is designed to fail gracefully:
- Individual activity failures don't stop the entire sync
- All errors are logged with context
- The workflow will continue processing remaining activities

## Contributing

Feel free to open issues or submit pull requests!

## License

See [LICENSE](LICENSE) file for details.