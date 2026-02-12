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

For **local development**, copy `.env-template` to `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Signing Secret from app credentials |
| `PORT` | Server port (default: 3000) |

The app loads `.env` locally via `python-dotenv`, but **Elastic Beanstalk does _not_ read your local `.env` file** when you deploy.

On **Elastic Beanstalk**, set these as **Environment properties** (per environment), for example with the EB CLI:

```bash
eb setenv \
  SLACK_BOT_TOKEN=xoxb-your-token \
  SLACK_SIGNING_SECRET=your-signing-secret
```

You only need to run `eb setenv` again when the values change; regular `eb deploy` reuses them.

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

   **Option A: Standard (with load balancer)** — ~\$20–\$23/month:
   ```bash
   eb create opoll-env --instance-types t4g.nano
   ```

   **Option B: Single-instance (no load balancer)** — ~\$3–\$5/month (cheapest EB option):
   ```bash
   eb create opoll-env --single --instance-types t4g.nano
   ```
   The `--single` flag creates a single-instance environment without a load balancer, saving ~\$16–\$17/month.

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

### Approximate AWS cost (Elastic Beanstalk)

These are **rough ballpark estimates only** for running this app in a single environment in `eu-west-3`. Always check the [AWS Pricing Calculator](https://calculator.aws/#/) for up‑to‑date numbers.

**Important:** Elastic Beanstalk uses an **Application Load Balancer (ALB)** by default, which charges **hourly** (~\$0.0225/hour ≈ **\$16–\$17/month**) regardless of traffic. This is the main cost driver, even for very low usage.

- **Compute (EC2)**  
  - **t4g.nano**: roughly **\$3–\$5 / month** if running 24/7.  
  - **t3.micro**: roughly **\$8–\$12 / month** (often Free Tier for 12 months).

- **Application Load Balancer (ALB)**  
  - **Hourly charge**: ~\$16–\$17/month (runs 24/7, regardless of traffic).  
  - **LCU charges**: Minimal for low traffic (3–4 requests/week ≈ pennies/month).  
  - **Note**: ALB charges apply even if your app receives zero requests.

- **Other costs**  
  - S3 storage for app versions and logs: **\< \$1 / month** at small scale.  
  - Data transfer: First 100 GB/month free, then ~\$0.09/GB (usually negligible for this app).

- **Total rough estimate**  
  - **t4g.nano + ALB**: about **\$20–\$23 / month** (mostly ALB + instance).  
  - **t3.micro + ALB**: about **\$25–\$30 / month**.

**For very low usage (3–4 times/week):**  
The ALB hourly charge (~\$16–\$17/month) dominates, so your total cost stays roughly the same regardless of request volume. Traffic-based charges are negligible.

**Cheaper alternatives for low-traffic usage:**

1. **Single-instance Elastic Beanstalk (no ALB)** — **~\$3–\$5/month**  
   Configure EB to use a single instance without a load balancer:
   ```bash
   eb create opoll-env --single --instance-types t4g.nano
   ```
   Or in EB Console: **Configuration** → **Capacity** → **Environment type**: **Single instance** (saves ~\$16–\$17/month by removing ALB).

2. **AWS Lambda + API Gateway** — **~\$0–\$1/month** for 3–4 requests/week  
   Pay-per-request pricing. With AWS Free Tier (1M requests/month for 12 months), this could be **essentially free**. Requires refactoring the app to work with Lambda (serverless), but very cost-effective for sporadic usage.

3. **Direct EC2 instance** (without Elastic Beanstalk) — **~\$3–\$5/month**  
   Run the app directly on a t4g.nano EC2 instance. No ALB, no EB overhead. Requires manual setup (SSH, nginx, systemd, etc.) but cheapest "always-on" option.

**Recommendation for 3–4 requests/week:**  
- **Lambda + API Gateway** = cheapest (~\$0/month with Free Tier, then pennies)  
- **Single-instance EB** = easiest to set up, ~\$3–\$5/month  
- **Standard EB with ALB** = most expensive (~\$20–\$23/month) but easiest to manage

**Cost optimization tips:**
- **Shut down the environment** when not needed: `eb terminate opoll-env` (recreate with `eb create` when needed).  
- Use **single-instance mode** to avoid ALB charges.  
- Use **t4g.nano** instead of t3.micro to save ~\$5/month on compute.

### Initializing with t4g.nano (ARM)

**t4g.nano** is the cheapest option but uses **ARM (Graviton)**. You must create the environment with the **Arm** Python platform, then use instance type **t4g.nano**.

**Option A – AWS Console (easiest)**

1. Create the environment from the **Elastic Beanstalk** console (or `eb create` first).
2. In **Configuration** → **Capacity**:
   - **Processor:** **arm64** (Graviton).
   - **Instance types:** `t4g.nano`.
3. Apply and let the environment update (or set these when creating the environment).

**Option B – EB CLI with command-line flag**

1. **Init** with the standard Python platform:
   ```bash
   eb init -p python-3.11 opoll --region eu-west-3
   ```
   Note: Modern Python platforms support both x86 and ARM architectures. The architecture is configured at the instance level.

2. **Create** the environment with ARM instance type using the command-line flag:
   ```bash
   eb create opoll-env --instance-types t4g.nano
   ```
   This sets the instance type during environment creation. For subsequent deploys, you can configure it in the AWS Console (Configuration → Capacity → Instance types) or use `eb config` to save the setting.

3. Set env vars and Slack URLs as in the main deployment steps.

**Note:** If ARM platforms aren't available in your region, or if you encounter errors with t4g.nano, you can use x86 instances instead (e.g., `t3.micro`) which are also cost-effective and Free Tier eligible.

### Optional: HTTPS with a custom domain

To use `https://your-domain.com` for Slack:

1. Add a custom domain in **Elastic Beanstalk** or put the app behind **CloudFront** / **Application Load Balancer** with an ACM certificate.
2. Set your Slack Request URLs to `https://your-domain.com/slack/events`.

## Tech stack

- **Python 3.9+**
- [Slack Bolt for Python](https://github.com/slackapi/bolt-python) + Flask

## License

MIT.
