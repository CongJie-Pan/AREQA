# AREQA Server Control

Cloudflare Worker control page for the two AREQA Render services only:

- `RENDER_BACKEND_SERVICE_ID`
- `RENDER_FRONTEND_SERVICE_ID`

The browser never calls Render directly. It calls this Worker, and the Worker
uses secrets to call the Render API.

## Features

- Mobile-first one-page control panel.
- `Resume All` resumes only AREQA backend and frontend.
- `Suspend All` suspends only AREQA backend and frontend.
- Status refresh shows each service state and latest deploy status when Render
  exposes it.
- Browser access is protected by `CONTROL_TOKEN`.
- The page polls every 5 seconds after unlock.

## Required Secrets

Set these with Wrangler:

```bash
npx wrangler secret put RENDER_API_KEY
npx wrangler secret put RENDER_BACKEND_SERVICE_ID
npx wrangler secret put RENDER_FRONTEND_SERVICE_ID
npx wrangler secret put CONTROL_TOKEN
```

Optional:

```bash
npx wrangler secret put AREQA_APP_URL
```

`AREQA_APP_URL` is the Render frontend URL opened by the `Open AREQA` button.
It is not sensitive, but storing it as a Worker secret keeps deployment setup
consistent.

## Local Development

```bash
cd misc/server_control
npm install
npm run dev
```

For local testing, Wrangler can read `.dev.vars` in this directory:

```text
RENDER_API_KEY=...
RENDER_BACKEND_SERVICE_ID=srv-...
RENDER_FRONTEND_SERVICE_ID=srv-...
CONTROL_TOKEN=...
AREQA_APP_URL=https://your-areqa-frontend.onrender.com
```

Do not commit `.dev.vars`.

## Deploy

```bash
cd misc/server_control
npm install
npx wrangler secret put RENDER_API_KEY
npx wrangler secret put RENDER_BACKEND_SERVICE_ID
npx wrangler secret put RENDER_FRONTEND_SERVICE_ID
npx wrangler secret put CONTROL_TOKEN
npx wrangler secret put AREQA_APP_URL
npm run deploy
```

Open the Worker URL, enter `CONTROL_TOKEN`, then use `Resume All`, `Suspend All`,
`Refresh`, and `Open AREQA`.

## GitHub Actions Deployment

The repository includes `.github/workflows/server-control-deploy.yml`. It deploys
this Worker automatically when files under `misc/server_control/**` change on
`master` or `main`.

Add this GitHub Actions secret:

```text
CLOUDFLARE_API_TOKEN
```

Create the token in Cloudflare with permission to edit Workers scripts for the
account that owns `areqa-server-control`. Runtime secrets such as
`RENDER_API_KEY` remain stored in Cloudflare Worker secrets and do not need to be
duplicated in GitHub for Worker deployment.
