# 29029 Steamboat → Monday Lap Sync

This job opens the live **29029 Steamboat 2026** page with Chromium, scrolls to the **Ascent Board**, uses the board's participant **search box**, and looks up these six people in last-name order:

1. Ty Brookover
2. Carey Cooper
3. Barbee Fagan
4. Jared King
5. Jill King
6. Jessica Seidel

For each lookup, it reads the returned lap/ascent count. Once Monday is configured, it finds the matching board item and writes that number into **Lap Completed**.

## Test the 29029 lookups before connecting Monday

Install dependencies, install Chromium, then run:

```bash
pip install -r requirements.txt
playwright install chromium
python sync.py --scrape-only
```

For troubleshooting, capture the board after each participant search:

```bash
python sync.py --scrape-only --debug-dir debug
```

Expected output format:

```text
Current lap counts (last-name order):
- Ty Brookover: 4
- Carey Cooper: 5
- Barbee Fagan: 4
- Jared King: 6
- Jill King: 5
- Jessica Seidel: 4
```

The numbers above are only an example; the script reads the live board when it runs.

## Connect Monday

1. Copy `config.example.json` to `config.json`.
2. Replace `monday_board_id` with the numeric board ID.
3. Replace `lap_completed_column_id` with the API column ID for **Lap Completed**.
4. Put the Monday API token in the environment variable `MONDAY_API_TOKEN` (for GitHub Actions, use a repository secret with that exact name).
5. Run `python sync.py` once manually and confirm the six rows update correctly.

## Safety behavior

- It searches the 29029 board **one participant at a time**, mirroring the manual workflow.
- It updates only the six configured people.
- It accepts only plausible event lap values (0–20).
- If a participant can't be confidently read, that participant is skipped rather than guessed.
- If no lap counts can be read, Monday is not updated.

## Hourly GitHub Action

The included workflow runs hourly. Keep `config.json` in your private repository and add the `MONDAY_API_TOKEN` repository secret before enabling the workflow.

## Finding Monday IDs

The `mndy.onelink.me` URL is a mobile deep link and does not expose the board/column IDs. Open the board in Monday's web app. The board ID is generally visible in the URL. The column ID can be queried with Monday's API:

```graphql
query ($board: [ID!]) {
  boards(ids: $board) {
    id
    name
    columns { id title type }
  }
}
```

Use the `id` for the column whose title is **Lap Completed**.
