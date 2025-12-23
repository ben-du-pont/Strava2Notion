# Strava to Notion Triathlon Sync

A Python application that automatically syncs your triathlon training activities (swimming, biking, and running) from Strava to Notion with intelligent matching to planned workouts.

## Features

- 🏊 **Automatic Sync**: Syncs swim, bike, and run activities from Strava to Notion
- ⏰ **Hourly Updates**: Runs every hour via GitHub Actions
- 📊 **Sport-Specific Fields**: Different field mappings for running (pace), cycling (speed), and swimming (pace per 100m)
- 🚫 **Duplicate Prevention**: Skips activities that already exist using Strava ID
- 🔗 **Planned Activity Linking**: Automatically matches and links completed activities to planned workouts
- ✅ **Status Updates**: Marks planned activities as "Done" when matched
- 🚀 **Manual Trigger**: Run sync manually via GitHub Actions workflow dispatch
- 🔒 **Secure**: Never logs sensitive tokens or credentials

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
3. Create two databases:

   **Training Log Database** (completed activities):
   - **Name** (Title)
   - **Color Select** (Select: Swim, Bike, Run) - Note: Strava "Ride" activities are mapped to "Bike"
   - **Date** (Date)
   - **Strava ID** (Number) - for duplicate prevention
   - **Linked Planned Workout** (Relation to Planning Database)
   - **Sport Type** (Relation to Sports Database)

   **Sport-specific fields**:
   - For Runs: `Distance (km)`, `Duration (min)`, `Average pace` (number), `Pace` (text), `Elevation (m)`, `Heart Rate Avg`, `Heart Rate Max`, `Average Cadence`, `Calories`
   - For Bikes: `Distance (km)`, `Duration (min)`, `Speed (km/h)`, `Elevation (m)`, `Heart Rate Avg`, `Heart Rate Max`, `Power Avg (Watts)`, `Power Max (Watts)`, `Average Cadence`, `Calories`
   - For Swims: `Distance (m)`, `Duration (min)`, `Swim Pace (min/100m)` (text), `Heart Rate Avg`, `Heart Rate Max`, `Stroke Rate`, `Calories`

   **Planning Database** (planned workouts):
   - **Sport relation** (Select: Run, Bike, Swim)
   - **Date** (Date)
   - **Selection status** (Select field with "Done" option)
   - **Training Log Entries** (Relation back to Training Log)

   **Sports Database** (sport types for categorization):
   - **Name** (Title) - Create pages for: Run, Bike, Swim (and optionally: Abs, Stretching, Gym)
   - This database is used to link activities to sport types for statistics and filtering

4. Share all three databases with your integration
5. Copy all three database IDs from the URLs (the 32-character hex string)

### 3. Configure GitHub Secrets

Add the following secrets to your GitHub repository (Settings → Secrets and variables → Actions):

- `STRAVA_CLIENT_ID`: Your Strava application client ID
- `STRAVA_CLIENT_SECRET`: Your Strava application client secret
- `STRAVA_REFRESH_TOKEN`: Your Strava refresh token
- `NOTION_TOKEN`: Your Notion integration token
- `NOTION_ACTIVITIES_DB_ID`: Your Training Log database ID
- `NOTION_PLANNED_DB_ID`: Your Planning Database ID
- `NOTION_SPORTS_DB_ID`: Your Sports database ID

### 4. Enable GitHub Actions

The workflow will run automatically every hour. You can also trigger it manually from the Actions tab.

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

1. Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

2. Run the sync:

```bash
cd src
python sync.py
```

Optional environment variables:
- `DAYS_BACK`: Number of days to look back (default: 7)
- `DRY_RUN`: Set to "true" to preview without syncing (default: false)

Example:
```bash
DAYS_BACK=30 python sync.py  # Sync last 30 days
DRY_RUN=true python sync.py  # Test without creating pages
```

## Usage

### Manual Sync

1. Go to the "Actions" tab in your GitHub repository
2. Select "Sync Strava to Notion" workflow
3. Click "Run workflow"
4. Optionally adjust the number of days to sync
5. Click "Run workflow" to start

### Scheduled Sync

The workflow runs automatically every hour. It syncs activities from the last 7 days by default.

## How It Works

1. **Fetch Activities**: Retrieves activities from Strava API for the specified time period
2. **Filter**: Keeps only triathlon activities (Swim, Ride, Run)
3. **Duplicate Check**: Skips activities that already exist in Notion (via Strava ID)
4. **Transform**: Converts Strava activity data to sport-specific Notion properties
5. **Create Activity**: Creates new page in Activities database
6. **Find Planned**: Searches Planned Activities database for matching type and date
7. **Link & Update**: Links activity to planned workout and marks status as "Done"
8. **Report**: Displays statistics about created, skipped, and any errors

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Troubleshooting

### Activities not syncing

- Verify all GitHub secrets are set correctly (especially the two database IDs)
- Check the Actions tab for error logs
- Ensure both Notion databases have all required properties
- Verify your Strava API credentials are valid
- Check that the Notion integration has access to both databases

### Activities syncing but not linking to planned workouts

The code has been configured to match your Notion schema:

- **Planned activity matching** ([notion.py:418-453](src/notion.py#L418-L453)): Uses fields `Sport relation` (Select) and `Date` (Date)
- **Linking** ([notion.py:455-475](src/notion.py#L455-L475)): Uses relation field `Linked Planned Workout`
- **Status update** ([notion.py:477-496](src/notion.py#L477-L496)): Uses select field `Selection status` with option `Done`

If your field names differ, adjust these methods in [notion.py](src/notion.py).

### Sport-specific fields not populating

Check the field mapping methods in [notion.py](src/notion.py):
- [`_get_run_properties()`](src/notion.py#L180) - Maps running data to your Notion fields
- [`_get_ride_properties()`](src/notion.py#L258) - Maps cycling data to your Notion fields
- [`_get_swim_properties()`](src/notion.py#L333) - Maps swimming data to your Notion fields

The code has been updated to match your actual field names. If fields are still not populating, verify that:
1. The field names in your Notion database exactly match those in the code
2. The field types are correct (number vs text vs rich_text)
3. The Strava activities contain the relevant data

### Rate Limits

Both Strava and Notion have API rate limits. The default 7-day sync window helps stay within these limits. Hourly syncs with duplicate prevention ensure minimal API usage.

## Acknowledgments

- [Strava API](https://developers.strava.com/)
- [Notion API](https://developers.notion.com/)
