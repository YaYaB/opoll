# Poll for Slack (open source)

A free, open-source Slack app to create polls with multiple options. Anyone can vote with one click; voter names appear next to each option (like the built-in `/opoll`), with **no vote limit**.

## Features

- **Slash command** `/opoll` with a question and bullet-point options
- **One click to vote** — names appear next to the option
- **One vote per user** — changing your vote moves your name to the new option
- No database required (state is stored in the message)

## Usage

In any channel where the app is installed:

**Single choice** (one vote per person; changing your vote moves it to the new option):

```
/opoll What's for lunch?
• Pizza
• Sushi
• Salad
```

Or on one line with bullets:

```
/opoll What's for lunch? • Pizza • Sushi • Salad
```

Or with **double-quoted** question and options (handy for spaces or punctuation in each part):

```
/opoll "What's for lunch?" "Pizza" "Sushi" "Salad"
```

**Multiple choice** (vote for several options; click again to remove your vote): put `multiple` or `--multiple` at the start:

```
/opoll multiple Which days work for you?
• Monday
• Tuesday
• Wednesday
```

Or: `/opoll multiple Pick your toppings • Cheese • Pepperoni • Mushrooms`

Use `•` or `-` for bullet points. People click **Vote** next to an option; their name is shown next to that option. The poll message shows "Single choice" or "Multiple choice" at the bottom.

## Setup

### 1. Create a Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.
2. Name it (e.g. "Poll") and pick your workspace.

### 2. Bot token and permissions

1. **OAuth & Permissions**: add Bot Token Scopes:
   - `chat:write` — post and update poll messages
   - `chat:write.public` — post in channels without joining (optional)
   - `commands` — slash commands
2. **Install to Workspace** and copy the **Bot User OAuth Token** (starts with `xoxb-`).

**Posting in channels:** The bot must be able to post in the channel. Either:
- **Invite the app** in the channel: type `/invite @YourPollApp` in that channel, or
- Add the **`chat:write.public`** scope so the app can post in any *public* channel without being invited (private channels still require an invite).

### 3. Slash command

1. **Slash Commands** → **Create New Command**:
   - Command: `/opoll`
   - Request URL: `https://YOUR_SERVER/slack/events`
   - Short description: `Create a poll with multiple options`
   - Usage hint: `What's for lunch? • Pizza • Sushi • Salad`
2. Save.

### 4. Interactivity

1. **Interactivity & Shortcuts** → turn **On**.
2. Request URL: `https://YOUR_SERVER/slack/events` (same as above).
3. Save.

### 5. Signing secret

Under **Basic Information** → **App Credentials**, copy the **Signing Secret**.

### 6. Run the app

```bash
cd poll_os
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export SLACK_BOT_TOKEN=xoxb-your-token
export SLACK_SIGNING_SECRET=your-signing-secret
python app.py
```

#### 7. Local dev 

The app listens on port **3000** (or set `PORT`). For local development, expose it with [ngrok](https://ngrok.com/):

```bash
ngrok http 3000
```

Use the `https://...ngrok.io` URL as the base for your Request URLs, e.g. `https://abc123.ngrok.io/slack/events`.

### Environment variables

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Signing Secret from app credentials |
| `PORT` | Server port (default: 3000) |

## Deploy on AWS

You can run the app on **AWS Elastic Beanstalk** so it’s always on and reachable by Slack (no ngrok needed).

### Prerequisites

- [AWS CLI](https://aws.amazon.com/cli/) configured (`aws configure`)
- [EB CLI](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3-install.html):  
  `pip install awsebcli`

### Deploy with Elastic Beanstalk

1. **Initialize the app** (from the project root):

   ```bash
   eb init -p python-3.11 opoll --region eu-west-3
   ```
   Use your preferred region (`us-east-1`, `eu-west-3`, etc.). Choose default or your own application name when prompted.

2. **Create and start an environment**:

   ```bash
   eb create opoll-env
   ```
   This creates the environment and deploys the app. The first run can take several minutes.

3. **Set environment variables** in the AWS console or via CLI:

   ```bash
   eb setenv SLACK_BOT_TOKEN=xoxb-your-token SLACK_SIGNING_SECRET=your-signing-secret
   ```

   Or in the **Elastic Beanstalk** → **Configuration** → **Software** → **Environment properties**, add:
   - `SLACK_BOT_TOKEN`
   - `SLACK_SIGNING_SECRET`

4. **Get the public URL**:

   ```bash
   eb status
   ```
   Note the **CNAME** (e.g. `opoll-env.xxx.region.elasticbeanstalk.com`).

5. **Point Slack to your app**  
   In [api.slack.com/apps](https://api.slack.com/apps) → your app:
   - **Slash Commands** → Request URL: `https://YOUR_CNAME/slack/events`
   - **Interactivity & Shortcuts** → Request URL: `https://YOUR_CNAME/slack/events`  
   Use **HTTPS** and the CNAME from step 4. If the environment is not behind a load balancer with HTTPS, use the HTTP URL for testing or add an HTTPS certificate (e.g. with a custom domain and ALB).

6. **Later: update the app**:

   ```bash
   eb deploy
   ```

The project includes a **Procfile** so Elastic Beanstalk runs the app with **Gunicorn** on port 8000. For production, the app is served via Gunicorn instead of the Flask dev server.

### Cheapest EC2 instance

Suitable instance types:

| Type         | vCPU | RAM    | Notes |
|--------------|------|--------|--------|
| **t4g.nano** | 2    | 0.5 GiB | **Cheapest.** ARM (Graviton). Use only with the Arm Python platform (see below). |
| **t3.micro** | 2    | 1 GiB  | **Recommended (x86).** Burstable, low cost. [Free Tier](https://aws.amazon.com/free/) eligible (12 months) in many regions. |

**In Elastic Beanstalk:** open **Configuration** → **Capacity** and set **Instance types** to the type you want (e.g. `t3.micro` or `t4g.nano`). The default may be larger.

### Initializing with t4g.nano (ARM)

**t4g.nano** is the cheapest option but uses **ARM (Graviton)**. You must create the environment with the **Arm** Python platform, then use instance type **t4g.nano**.

**Option A – AWS Console (easiest)**

1. Create the environment from the **Elastic Beanstalk** console (or `eb create` first).
2. In **Configuration** → **Capacity**:
   - **Processor:** **arm64** (Graviton).
   - **Instance types:** `t4g.nano`.
3. Apply and let the environment update (or set these when creating the environment).

**Option B – EB CLI with included config**

1. **Init** with the **Arm** Python platform so the environment is Graviton from the start:
   ```bash
   eb platform list
   ```
   Pick the platform that includes **Arm** (e.g. *Python 3.11 running on 64bit Arm Amazon Linux 2*). Then:
   ```bash
   eb init -p "Python 3.11 running on 64bit Arm Amazon Linux 2" opoll --region eu-west-3
   ```
2. **Create** the environment. The repo includes `.ebextensions/01-t4g-nano.config`, which sets the instance type to **t4g.nano** for every deploy:
   ```bash
   eb create opoll-env
   ```
3. Set env vars and Slack URLs as in the main deployment steps.

If the Arm platform name differs in your region, use the one that contains `Arm` from `eb platform list`. If you already created an x86 environment, you cannot switch it to ARM; create a new environment with the Arm platform and t4g.nano instead.

### Optional: HTTPS with a custom domain

To use `https://your-domain.com` for Slack:

1. Add a custom domain in **Elastic Beanstalk** or put the app behind **CloudFront** / **Application Load Balancer** with an ACM certificate.
2. Set your Slack Request URLs to `https://your-domain.com/slack/events`.

## Tech stack

- **Python 3.9+**
- [Slack Bolt for Python](https://github.com/slackapi/bolt-python) + Flask

## License

MIT.
