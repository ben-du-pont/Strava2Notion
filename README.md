# Strava to Notion Triathlon Sync

Automatically sync your triathlon training activities from Strava to Notion with smart workout matching and fully customizable field mappings.

## 🎯 Main Goal

This tool bridges the gap between **planning** and **execution** in your triathlon training:

1. **Plan your workouts** in Notion (e.g., "Run 10km on Monday")
2. **Complete your activities** and track them on Strava
3. **Automatic sync** intelligently matches completed Strava activities to planned Notion workouts

**Smart Matching Logic:**
- Matches by **sport type** (Run, Bike, or Swim)
- First tries **exact date match**
- If not found, searches within **±3 days** for flexibility (you did Monday's workout on Tuesday? No problem!)
- Skips workouts already marked as **"Done"** or already linked to other activities
- Chooses the **closest match** by date if multiple options exist
- Automatically **links** the activity to the planned workout and marks it as **"Done"**

This creates a seamless workflow where your training plan automatically updates as you complete workouts, even if you don't stick to the exact schedule. Perfect for real-world training where plans change!

## ✨ Features

- **🏊 Triathlon-Focused**: Automatically syncs swimming, biking, and running activities
- **⏰ Automated**: Runs every hour via GitHub Actions (or manually on-demand)
- **📊 Sport-Specific Data**: Different metrics for each sport (pace for running, speed for cycling, pace/100m for swimming)
- **🎯 Smart Matching**: Automatically links completed activities to planned workouts
- **🔧 Fully Customizable**: Easy YAML configuration for all field mappings
- **🚫 Duplicate-Safe**: Never creates the same activity twice
- **🎨 Visual Icons**: Sport-specific emoji icons for each activity
- **📈 Rich Metrics**: Distance, duration, heart rate, cadence, elevation, power, and more
- **🔒 Secure**: Your credentials stay private - never logged or exposed

## 📋 Prerequisites

Before you begin, you'll need:

1. **A Strava account** with activities to sync
2. **A Notion account** with workspace access
3. **A GitHub account** (for automated hourly syncing) OR Python 3.11+ (for local running)
4. **5-10 minutes** to complete the setup

## Quick Start

1. Fork this repository
2. Set up your Strava and Notion credentials (see detailed setup below)
3. Configure GitHub secrets
4. Enable GitHub Actions
5. Let it run automatically every hour, or trigger manually

## Detailed Setup Guide

### Step 1: Strava API Setup

1. **Create a Strava API Application**
   - Go to [Strava API Settings](https://www.strava.com/settings/api)
   - Click "Create an App" if you haven't already
   - Fill in the required fields:
     - **Application Name**: Choose any name (e.g., "Notion Sync")
     - **Website**: Your GitHub repo URL or any valid URL
     - **Authorization Callback Domain**: `localhost` (for local OAuth flow)
   - Click "Create"

2. **Get Your Credentials**
   - After creating the app, you'll see:
     - **Client ID**: A numeric ID (e.g., `12345`)
     - **Client Secret**: A long alphanumeric string
   - Save both of these - you'll need them later

3. **Generate a Refresh Token**
   - The refresh token allows the app to access your Strava data
   - Visit this URL in your browser (replace `YOUR_CLIENT_ID` with your actual Client ID):
   ```
   https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=activity:read_all
   ```
   - Click "Authorize"
   - You'll be redirected to a URL like `http://localhost/?code=XXXXXX`
   - Copy the `code` value from the URL
   - Exchange the code for a refresh token using this curl command (replace `YOUR_CLIENT_ID`, `YOUR_CLIENT_SECRET`, and `YOUR_CODE`):
   ```bash
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=YOUR_CLIENT_ID \
     -d client_secret=YOUR_CLIENT_SECRET \
     -d code=YOUR_CODE \
     -d grant_type=authorization_code
   ```
   - In the response, find the `refresh_token` value - this is what you need

### Step 2: Notion Setup

**Option A: Use the Notion Template (Recommended)**

The easiest way to get started is to duplicate the pre-configured Notion template:

1. **Duplicate the template**: [Strava to Notion Template](https://your-template-link-here) *(Coming soon - for now, use Option B below)*
2. **Share with your integration**: Once duplicated, share all three databases with your integration (see Step 3 below)
3. **Get database IDs**: Copy the database IDs from the URLs (see Step 4 below)

**Option B: Create Databases Manually**

If you prefer to create your own databases or customize the structure:

1. **Create a Notion Integration**
   - Go to [Notion Integrations](https://www.notion.so/my-integrations)
   - Click "+ New integration"
   - **Name**: Choose any name (e.g., "Strava Sync")
   - **Associated workspace**: Select your workspace
   - Click "Submit"
   - Copy the **Internal Integration Token** (starts with `secret_...`)

2. **Create Three Notion Databases**

   You need to create three databases in Notion. Below are the exact properties required for each:

   **a) Training Log Database** (where completed activities are stored)

   Create a new database with these properties:

   | Property Name | Type | Options/Notes |
   |--------------|------|---------------|
   | **Name** | Title | Required - activity name |
   | **Color Select** | Select | Options: `Swim`, `Bike`, `Run` |
   | **Date** | Date | Activity date |
   | **Strava ID** | Number | For duplicate prevention |
   | **Linked Planned Workout** | Relation | Link to Planning Database (created below) |
   | **Sport Type** | Relation | Link to Sports Database (created below) |
   | **Distance (km)** | Number | Format: Number, 2 decimals |
   | **Duration (min)** | Number | Format: Number, 2 decimals |
   | **Elevation Gain (m)** | Number | Format: Number |
   | **Heart Rate Avg** | Number | Format: Number |
   | **Heart Rate Max** | Number | Format: Number |
   | **Calories** | Number | Format: Number |

   **Running-specific properties:**
   - **Average pace** (Number) - numeric pace value for calculations
   - **Pace** (Text) - formatted pace like "5:30 /km"
   - **Average Cadence** (Number) - steps per minute

   **Cycling-specific properties:**
   - **Speed (km/h)** (Number) - average speed
   - **Power Avg (Watts)** (Number)
   - **Power Max (Watts)** (Number)
   - **Average Cadence** (Number) - RPM for cycling

   **Swimming-specific properties:**
   - **Swim Pace (min/100m)** (Text) - formatted pace like "1:45"
   - **Stroke Rate** (Number) - strokes per minute

   **b) Planning Database** (where planned workouts are stored)

   Create a new database with these properties:

   | Property Name | Type | Options/Notes |
   |--------------|------|---------------|
   | **Sport relation** | Select | Options: `Run`, `Bike`, `Swim` |
   | **Date** | Date | Planned workout date |
   | **Selection status** | Select | Must include option: `Done` |
   | **Training Log Entries** | Relation | Link back to Training Log Database |

   **c) Sports Database** (for categorizing activities)

   Create a new database with one property:

   | Property Name | Type | Notes |
   |--------------|------|-------|
   | **Name** | Title | Sport type name |

   Then create pages in this database for each sport type:
   - **Run** (required for running activities)
   - **Bike** (required for cycling activities)
   - **Swim** (required for swimming activities)
   - **Abs** (optional - for tracking other workouts)
   - **Stretching** (optional)
   - **Gym** (optional)

3. **Share Databases with Integration**
   - For each of the three databases:
     - Click the "..." menu in the top-right
     - Select "Connections" or "Add connections"
     - Find your integration and add it
   - This gives the integration permission to read/write these databases

4. **Get Database IDs**
   - Open each database as a full page
   - Look at the URL in your browser:
     ```
     https://www.notion.so/workspace/DATABASE_ID?v=...
     ```
   - The `DATABASE_ID` is the 32-character string (without dashes)
   - Copy this ID for each database - you'll need them for GitHub secrets

### Step 3: Configure GitHub Secrets

Now you need to add your credentials to GitHub so the automated workflow can access them securely.

1. **Go to your GitHub repository**
   - Navigate to **Settings** → **Secrets and variables** → **Actions**
   - Click **New repository secret**

2. **Add each of the following secrets:**

   | Secret Name | Value | Where to get it |
   |------------|-------|-----------------|
   | `STRAVA_CLIENT_ID` | Your Strava Client ID | From Step 1.2 |
   | `STRAVA_CLIENT_SECRET` | Your Strava Client Secret | From Step 1.2 |
   | `STRAVA_REFRESH_TOKEN` | Your Strava refresh token | From Step 1.3 |
   | `NOTION_TOKEN` | Your Notion integration token | From Step 2.1 (starts with `secret_...`) |
   | `NOTION_ACTIVITIES_DB_ID` | Training Log database ID | From Step 2.4 (32 characters) |
   | `NOTION_PLANNED_DB_ID` | Planning database ID | From Step 2.4 (32 characters) |
   | `NOTION_SPORTS_DB_ID` | Sports database ID | From Step 2.4 (32 characters) |

   For each secret:
   - Click "New repository secret"
   - Enter the **Name** exactly as shown above
   - Paste the **Value**
   - Click "Add secret"

### Step 4: Enable GitHub Actions

1. **Enable Actions** (if not already enabled)
   - Go to the **Actions** tab in your repository
   - If prompted, click "I understand my workflows, go ahead and enable them"

2. **Verify the workflow**
   - You should see a workflow called "Sync Strava to Notion"
   - The workflow is configured to run automatically every hour at the top of the hour
   - It will sync activities from the last 7 days by default

3. **Optional: Run manually to test**
   - Click on "Sync Strava to Notion" workflow
   - Click "Run workflow" button
   - Optionally adjust the "Days to look back" parameter
   - Click "Run workflow" to start
   - Watch the progress in real-time by clicking on the running workflow

That's it! Your sync is now set up and will run automatically every hour.

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── sync.yml          # GitHub Actions workflow
├── src/
│   ├── strava.py            # Strava API client
│   ├── notion.py            # Notion API client
│   ├── config_loader.py     # Configuration management
│   └── sync.py              # Main sync script
├── config.yml               # Field mapping configuration
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Configuration

The field mappings between Strava and Notion are defined in `config.yml`. This allows you to:
- Customize Notion field names to match your database
- Enable/disable specific fields per sport type
- Configure emoji icons and formatting options

### Customizing Field Mappings

Edit `config.yml` to match your Notion database schema:

```yaml
# Enable a field mapping
distance: "Distance (km)"

# Disable a field
max_watts: false

# Comment out to disable
# calories: "Calories"
```

The configuration file is organized into sections:
- **common_fields**: Fields that apply to all activity types (name, date, Strava ID, etc.)
- **run_fields**: Running-specific fields (pace, cadence for running)
- **bike_fields**: Cycling-specific fields (speed, power, cadence for cycling)
- **swim_fields**: Swimming-specific fields (swim pace, stroke rate)
- **sport_icons**: Emoji icons for each sport type
- **options**: Advanced options (pace suffix, unit conversions)

## Running Locally (Optional)

If you prefer to run the sync locally instead of using GitHub Actions, follow these steps.

> **⚠️ Important**: The `.env` file is for **local development only**. Never commit your `.env` file to Git as it contains sensitive credentials. The `.env` file is already included in `.gitignore` to prevent accidental commits. For automated syncing via GitHub Actions, use GitHub Secrets instead (see Step 3 above).

### Prerequisites

- Python 3.11 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/ben-du-pont/strava2notion_triathlon.git
   cd strava2notion_triathlon
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create and configure `.env` file** (for local use only)
   ```bash
   cp .env.example .env
   ```

   Then edit `.env` with your actual credentials:
   ```bash
   # Use your favorite text editor
   nano .env
   # or
   vim .env
   # or
   code .env
   ```

   Fill in all the values following the same format as the GitHub secrets in Step 3 above.

   **Remember**: Never commit this file to Git! It's already in `.gitignore` for your safety.

### Running the Sync

**Basic usage:**
```bash
cd src
python sync.py
```

**Advanced options:**

Sync activities from the last 30 days:
```bash
DAYS_BACK=30 python sync.py
```

Test mode (preview what would be synced without creating anything):
```bash
DRY_RUN=true python sync.py
```

Combine options:
```bash
DAYS_BACK=14 DRY_RUN=true python sync.py
```

**Environment variables:**
- `DAYS_BACK`: Number of days to look back (default: 7)
- `DRY_RUN`: Set to `true` to preview without syncing (default: `false`)

## How It Works

Understanding the sync process:

1. **Fetch Activities**: Retrieves recent activities from Strava API (default: last 7 days)
2. **Filter by Sport**: Keeps only triathlon activities (Run, Ride/Bike, Swim)
3. **Check for Duplicates**: Uses Strava ID to skip activities already synced to Notion
4. **Transform Data**: Converts Strava activity data to sport-specific Notion properties
5. **Create Activity Page**: Adds new page to Training Log database with:
   - Activity name, date, and metrics
   - Sport-specific data (pace for running, speed for cycling, etc.)
   - Sport Type relation link (for statistics)
   - Emoji icon based on sport type
6. **Smart Matching**: Searches Planning database for matching workouts:
   - Same sport type (Run, Bike, or Swim)
   - First tries exact date match
   - If no exact match, searches within ±3 days
   - Filters out workouts already "Done" or already linked
   - Selects the closest match by date
7. **Link & Update**: If a match is found:
   - Links the completed activity to the planned workout (bidirectional)
   - Updates planned workout status to "Done"
8. **Report**: Shows summary of synced, skipped, and any errors


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Troubleshooting

### Problem: Activities not syncing at all

**Possible causes and solutions:**

1. **Invalid Strava credentials**
   - Go to Actions tab and check the workflow logs for authentication errors
   - Verify `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, and `STRAVA_REFRESH_TOKEN` are correct
   - Try generating a new refresh token (see Step 1.3 in setup)

2. **Invalid Notion credentials**
   - Check for 401 Unauthorized errors in workflow logs
   - Verify `NOTION_TOKEN` is correct and starts with `secret_`
   - Ensure your integration hasn't been deleted

3. **Wrong database IDs**
   - Verify all three database IDs are correct (32 characters each)
   - Database IDs should NOT include dashes or the `?v=...` part
   - Make sure you copied the full ID from the URL

4. **Databases not shared with integration**
   - For each database, click "..." → "Connections"
   - Verify your integration appears in the list
   - If not, add it and try again

### Problem: Activities syncing but not linking to planned workouts

**Required setup for automatic linking:**

The Planning database must have these exact field names (case-sensitive):
- `Sport relation` (Select field with options: Run, Bike, Swim)
- `Date` (Date field)
- `Selection status` (Select field with at least a "Done" option)
- `Training Log Entries` (Relation field linking back to Training Log)

**To fix:**
1. Check your Planning database field names match exactly
2. Verify the "Done" option exists in the `Selection status` select field
3. Ensure the `Training Log Entries` relation is set up correctly

If you use different field names, you'll need to update [notion.py](src/notion.py) lines 418-496.

### Problem: Sport Type relation error

**Error message**: `"Sport Type is not a property that exists"`

**Solutions:**

1. **Verify field name is exact**
   - In your Training Log database, the field must be named exactly `Sport Type` (case-sensitive)
   - Check for extra spaces or typos

2. **Confirm field type**
   - The `Sport Type` field must be a **Relation** field type
   - It should link to your Sports database

3. **Check Sports database is shared**
   - Go to your Sports database
   - Click "..." → "Connections"
   - Verify your integration has access

4. **Verify Sports database ID is set**
   - Check that `NOTION_SPORTS_DB_ID` GitHub secret is configured
   - The ID should be the 32-character ID of your Sports database

5. **Ensure Sports database has pages**
   - Your Sports database should contain pages named: `Run`, `Bike`, `Swim`
   - These names must match exactly (case-sensitive)

### Problem: Sport-specific fields not populating

**Field mappings are configured in [config.yml](config.yml)**

**Troubleshooting steps:**

1. **Check field names match exactly**
   - Open [config.yml](config.yml)
   - Find the relevant section (`run_fields`, `bike_fields`, or `swim_fields`)
   - Ensure the Notion field names match your database exactly (case-sensitive)
   - Example: `distance: "Distance (km)"` - the string must match your Notion field

2. **Verify field is enabled**
   - Make sure the field isn't set to `false`
   - Make sure it's not commented out with `#`

3. **Check Notion field types match**
   - Distance, duration, pace, speed, etc. → **Number** fields
   - Pace text, swim pace text → **Text** or **Rich text** fields
   - Make sure you're using the correct field type in Notion

4. **Verify Strava has the data**
   - Some fields like power data require a power meter
   - Heart rate requires a heart rate monitor
   - Check your Strava activity to confirm the data exists

**To customize field mappings:**
1. Open [config.yml](config.yml)
2. Find the field under the appropriate section
3. Update: `strava_field: "Your Notion Field Name"`
4. Disable: `strava_field: false` or comment with `#`
5. Save and push changes to GitHub

### Problem: API Rate Limits

**Symptoms**: Sync stops working after many activities

**Solutions:**
- Strava allows 100 requests per 15 minutes, 1,000 per day
- Notion allows 3 requests per second
- The default 7-day sync window helps stay within limits
- If syncing many activities, try running with smaller `DAYS_BACK` values
- Hourly syncs with duplicate prevention minimize API usage

### Need More Help?

- **Check workflow logs**: Go to Actions tab → Click on failed run → View logs
- **Enable debug mode**: Look for lines starting with `[DEBUG]` in the logs
- **Test locally**: Run locally with `DRY_RUN=true` to see what would happen
- **File an issue**: [Create a GitHub issue](https://github.com/ben-du-pont/strava2notion_triathlon/issues) with:
  - Error message
  - Workflow logs
  - Description of your Notion database setup

## Acknowledgments

- [Strava API](https://developers.strava.com/)
- [Notion API](https://developers.notion.com/)

