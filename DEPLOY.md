# Deployment — AI Orbit Data Explorer

## 1. Create the GitHub repository

From the project root:

```bash
cd ~/Downloads/ai_orbit_signal_combined
```

Verify secrets are absent:

```bash
find . -maxdepth 2 -name '.env' -o -name '*.pem' -o -name '*credentials*.json'
```

The command should **not** show `.env` in the submission project.

Then:

```bash
git init
git add .
git status
```

Confirm that `.env`, `.venv`, `__pycache__`, `pipeline.db` and `pipeline.log` are not staged.

Commit:

```bash
git commit -m "AI Orbit trial submission"
```

Create an empty GitHub repository, then:

```bash
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ai-orbit-signal.git
git push -u origin main
```

## 2. Test locally before deployment

```bash
python3 -m http.server 3000
```

Open:

```text
http://localhost:3000
```

Test:

- All
- Companies
- Tools
- Personal
- Creativity
- Models
- Repositories
- MCP
- Robots
- Devices
- Recently Added
- search
- source filter
- sorting
- relationship section
- entity detail modal
- source/evidence links

## 3. Deploy to Vercel

1. Open Vercel.
2. Select **Add New → Project**.
3. Import the GitHub repository.
4. Use the repository root as the project root.
5. Select a static/Other framework preset.
6. Leave the build command empty.
7. Set output directory to `.` if Vercel asks for it.
8. Deploy.

No environment variables are required for the **public dashboard** because the browser only reads static JSON.

## 4. Verify the production site

Open the Vercel URL in an incognito window.

Check:

```text
/
/type=robots
/type=models
/type=mcp
/type=personal
/type=creative
/type=recent
/view=relationships
```

The application uses client-side URL state, so direct refreshes should continue to work on the static deployment.

## 5. Final submission

Send the team:

```text
GitHub repository: https://github.com/YOUR_USERNAME/ai-orbit-signal
Live dashboard: https://YOUR-PROJECT.vercel.app
```

Also submit both in the group and by DM as requested by the trial instructions.

## Important security note

If a real `.env` or API credential was ever included in a shared ZIP, uploaded artifact, Git repository, or chat attachment, rotate those credentials before final submission. Removing the file later does not invalidate an already-exposed secret.
