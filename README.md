# 29029 Steamboat Lap Tracker

This test version opens the 29029 Steamboat 2026 page in Chromium and searches the Ascent Board for:

1. Ty Brookover
2. Carey Cooper
3. Barbee Fagan
4. Jared King
5. Jill King
6. Jessica Seidel

The GitHub Actions workflow can be run manually and is also scheduled for seven minutes after each hour. It currently runs in scrape-only mode: no Monday.com credentials or setup are required.

## First test

Open **Actions** in GitHub, choose **Steamboat Lap Tracker**, select **Run workflow**, and open the completed run. Under **Scrape live Steamboat lap counts**, the log should show the six names and the lap counts found. Debug screenshots are uploaded as an artifact for troubleshooting.
