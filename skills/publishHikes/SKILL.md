---
name: publishHikes
description: Publish every documented hike in the workspace to the leaders' password-protected micro-site on AWS Amplify. Use after /documentMyHike, or when the user asks to publish, update or share the hike website.
---

# Publish the hikes website

The site is rebuilt from scratch from the hike folders every time, so it always matches what is in the workspace. Nothing generated is kept locally.

## 1. Check

- Every hike to publish must have its documents built. A folder with `hike.yaml` but no leader pack is skipped; offer to run **/documentMyHike <slug>** for it first.
- Each hike page shows its staffing sheet (`<slug>_staffing.md`) as a table and links the file, so names and mobiles the user has filled in go on the site. That's fine behind the password, but mention it when you report.
- `.env` in the workspace must hold `HIKE_SITE_AMPLIFY_APP_ID` (and optionally `HIKE_SITE_BRANCH`, default `main`). If it's missing, do the one-off setup below.

## 2. Publish

Run `python3 hike-kit/tools/publish_site.py --deploy` in the workspace. It builds the site in a temporary folder, uploads it to Amplify, waits for the deployment and deletes the temporary folder. It prints the site URL.

To look before publishing, run `--out <scratchpad>/site` instead, and delete that folder afterwards.

## 3. Verify and report

- With the credentials from `.env`, `curl -u USER:PASS <url>/` returns 200, and without them returns 401.
- The hike pages show a Staffing section (grep for `<h2>Staffing` on one page).
- Tell the user the URL and which hikes were added or skipped. Never print the password in chat unless the user asks for it; say it's in `.env` as `HIKE_SITE_PASSWORD`.

## One-off setup (only if there's no app yet)

1. `aws amplify create-app --name hike-routes --platform WEB`
2. `aws amplify create-branch --app-id <id> --branch-name main --stage PRODUCTION --enable-basic-auth --basic-auth-credentials $(printf 'USER:PASS' | base64 -w0)`, with a random 16-character password.
3. Append `HIKE_SITE_AMPLIFY_APP_ID`, `HIKE_SITE_BRANCH`, `HIKE_SITE_USER` and `HIKE_SITE_PASSWORD` to the workspace `.env` (mode 600). Never put them in the repo.

To change the password later: `aws amplify update-branch --app-id <id> --branch-name main --enable-basic-auth --basic-auth-credentials <base64 USER:PASS>`, and update `.env`.
