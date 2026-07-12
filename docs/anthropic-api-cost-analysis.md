# Anthropic (Claude) API — Where the Money Goes

**Project:** social-media-automation
**Question answered:** Which parts of the program call the paid Claude API, and roughly what does a typical day/month cost?
**Date:** 2026-07-12

> ⚠️ **Read this first.** Everything below concerns the **Anthropic API** used by the *deployed automation program* — billed pay‑as‑you‑go against an `ANTHROPIC_API_KEY` you set up at console.anthropic.com. This is **separate from, and not covered by, your Claude Max subscription** (which is what powers the Claude Code chat sessions). The token estimates are **rough** — actual spend depends heavily on web‑search result sizes and how often each pipeline actually produces content.

---

## 1. Bottom line

| | Estimate |
|---|---|
| **Typical day** (all pipelines run, 1 post/run) | **~$0.50 / day** |
| **Typical month** (continuous, unpaused) | **~$15–20 / month** |
| **Realistic range** | **~$15–30 / month** depending on posts/day, web‑search sizes, and pause time |

**The cost is dominated by three things:** (1) the **web‑search research steps**, (2) **Sonnet output tokens**, and (3) the **per‑search web‑search fee** ($10 per 1,000 searches). The rest — captions, quality checks — is pennies.

Two other things to know up front:
- **Image and video generation are billed by *other* providers** (Google Imagen, Higgsfield, HeyGen), **not** Anthropic — and can easily exceed the Claude cost. See §7.
- The code already handles hitting your Anthropic spending cap gracefully (it logs *"⚠️ Anthropic API spending limit reached — raise your cap at console.anthropic.com"* and stops rather than crashing).

---

## 2. The two models it uses

Defined in `core/config.py:72-73`:

| Role | Model | Price (input / output per 1M tokens) | Used for |
|---|---|---|---|
| `model_creative` | **`claude-sonnet-4-6`** (Sonnet) | **$3 / $15** | Writing captions, scoring topics, planning infographics/carousels — anything needing judgment |
| `model_fast` | **`claude-haiku-4-5`** (Haiku) | **$1 / $5** | Discovery web-search gather, quality checks — cheap, high-volume work |
| *(server tool)* | **Web search** | **$10 per 1,000 searches** | Trending-topic discovery, AI news, infographic research |

Both are overridable via `ANTHROPIC_MODEL_CREATIVE` / `ANTHROPIC_MODEL_FAST` env vars.

---

## 3. Where the paid calls happen (exact trace)

Every place the program spends Anthropic money, by file and line:

| # | File : line | Agent / step | Model | `max_tokens` | Web search? |
|---|---|---|---|---|---|
| 1 | `agents/research_agent.py:441` | Daily research — **discovery** | Haiku | 8000 | ✅ |
| 2 | `agents/research_agent.py:482` | Daily research — **scoring** (structured) | Sonnet | 4000 | — |
| 3 | `agents/research_agent.py:615` | **Weekly strategy** — discovery | Haiku | 8000 | ✅ |
| 4 | `agents/content_agent.py:297` | **Caption/content** generation | Sonnet | 2000 | — |
| 5 | `agents/quality_agent.py:134` | Quality check — **text** | Haiku | 1024 | — |
| 6 | `agents/quality_agent.py:168` | Quality check — **image** | Haiku | 128 | — |
| 7 | `agents/news_agent.py:245` | Daily AI news — **fetch stories** | Sonnet | 3000 | ✅ |
| 8 | `agents/news_agent.py:267` | Daily AI news — **plan carousel** | Sonnet | 2000 | — |
| 9 | `agents/carousel_agent.py:190` | Carousel — **slide copy** | Sonnet | 1500 | — |
| 10 | `agents/infographic_agent.py:549 / 574` | Infographic — research + plan | Sonnet | 3000 / 1500 | ✅ |
| — | `agents/infographic_agent.py:1380/1400`, `2006/2026` | Alternate infographic templates (one set runs per infographic) | Sonnet | 3000 / 1500 | ✅ |

**Not paid Anthropic calls** (no LLM): the publisher, the analytics agent (Supabase only), the command queue, cleanup, and token refresh. The 15‑second command‑queue poll and 5‑minute publisher are just database reads — no per‑request charge.

---

## 4. When they run (the schedule)

From `scheduler/cron.py:2228-2356`. Times are in your configured timezone.

| Job | Schedule | Spends Anthropic $? |
|---|---|---|
| `research_pipeline` | **Daily 05:30** | ✅ discovery (Haiku+search) + scoring (Sonnet) |
| `content_pipeline` | **Daily 06:00** | ✅ caption (Sonnet) + QA (Haiku) per post |
| `approved_pipeline` | **Every 15 min** | ✅ *only when you've approved topics* — otherwise a no‑op |
| `infographic_pipeline` | **Daily 11:00** | ✅ research + plan (Sonnet+search) |
| `daily_ai_news` | **Daily 12:00** | ✅ fetch + plan + slides (Sonnet+search) |
| `weekly_strategy` | **Mon 07:00** | ✅ discovery (Haiku+search) + scoring (Sonnet) |
| `qc_retry` | Every 4 h | ✅ *only when there are failed posts* — QA re‑checks |
| `analytics` | Every 2 h | ❌ Supabase only |
| `image_refresh` | Daily 02:00 | ❌ Anthropic — but ✅ **Google/Higgsfield** (see §7) |
| `publisher` | Every 5 min | ❌ no LLM |
| `command_queue` | Every 15 s | ❌ database only |
| `cleanup` / `token_refresh` | Weekly | ❌ maintenance |

**Key point:** the recurring 15‑second / 5‑minute jobs cost **nothing** on Anthropic. The money is spent by the **five daily content jobs** + the weekly strategy pass.

---

## 5. Token cost estimate (a typical day)

Assumes all pipelines run unpaused with `POSTS_PER_RUN = 1` (the default, `core/config.py:139`). Token counts are **estimates** — web‑search steps inject a variable amount of fetched content, which is the biggest unknown.

| Step | Model | ~Input tok | ~Output tok | Searches |
|---|---|---:|---:|---:|
| Research discovery | Haiku | 12,000 | 6,000 | ~4 |
| Research scoring | Sonnet | 7,000 | 3,000 | — |
| Content caption (1 post) | Sonnet | 2,000 | 1,200 | — |
| Quality text + image | Haiku | 2,700 | 500 | — |
| Infographic research + plan | Sonnet | 15,000 | 4,500 | ~3 |
| AI news fetch + plan | Sonnet | 16,000 | 5,000 | ~3 |
| Carousel slides + QA | Sonnet+Haiku | 5,200 | 1,700 | — |
| **Totals** | | **~60k** | **~22k** | **~10** |

**Cost breakdown for the day:**

| Component | Calc | Cost |
|---|---|---:|
| Sonnet input (~42.5k) | 42,500 ÷ 1M × $3 | $0.128 |
| Sonnet output (~15k) | 14,900 ÷ 1M × $15 | $0.224 |
| Haiku input (~17.4k) | 17,400 ÷ 1M × $1 | $0.017 |
| Haiku output (~7k) | 7,000 ÷ 1M × $5 | $0.035 |
| Web search (~10) | 10 ÷ 1,000 × $10 | $0.100 |
| **Daily total** | | **~$0.50** |

**→ ~$0.50/day × 30 ≈ ~$15/month**, plus the Monday weekly‑strategy pass (~$0.15 × 4 ≈ $0.60/month). Call it **~$15–20/month** at 1 post/run.

### If you post more
Each **additional standard post** (caption + QA) is only about **$0.025**. So even bumping to ~10 posts/day adds roughly **$0.25/day (~$7.50/month)** — content generation is cheap; the research/search steps are the fixed cost.

---

## 6. Cost drivers & levers

**What costs the most:**
1. **Web search** — both the $10/1k search fee *and* the large blocks of fetched web content that get counted as input tokens. Three pipelines use it (research, news, infographic).
2. **Sonnet output tokens** at $15/1M — the priciest single line.

**Levers if you ever want to trim spend:**
- **Pause pipelines you don't need.** The dashboard's pause switch stops all content jobs; every paused day is ~$0.50 saved.
- **Fewer web‑search‑driven pipelines.** Dropping (say) the daily infographic or news carousel removes one search‑heavy job each (~$0.10–0.15/day apiece).
- **Lower `max_tokens`** on the research/news steps if outputs are longer than needed.
- The design is already cost‑aware: cheap **Haiku** does the high‑token discovery gather; premium **Sonnet** only does the small, judgment‑heavy scoring/planning steps.

---

## 7. Separate paid APIs (NOT Anthropic)

The program also calls **other** paid providers for media. These are billed by those companies, on their own keys — **none of this shows up on your Anthropic bill**, but it's real money:

| Provider | Env var | Used for |
|---|---|---|
| **Google Imagen** (`imagen-4.0-generate-001`) | `GOOGLE_API_KEY` | Post / thumbnail images (`image_refresh` at 02:00) |
| **Higgsfield** | `HIGGSFIELD_API_KEY` | Primary image generation when set |
| **HeyGen** | `HEYGEN_API_KEY` | Video / reels |
| **Freesound** | `FREESOUND_API_KEY` | Audio (free tier) |

Image/video generation is often **more expensive per item than the text**, so if you're budgeting, price those separately with each provider.

---

## 8. Built‑in safeguards

- **`DRY_RUN=true`** (`.env.example:12`) — runs the whole pipeline and logs what *would* be generated/posted **without calling any external API**. Zero spend; good for testing.
- **Spending‑cap handling** — if you hit your Anthropic cap, the code detects it and logs *"raise your cap at console.anthropic.com"* (`scheduler/cron.py:1441, 1920`) rather than erroring out. Set a cap in the Anthropic console to bound the maximum you can ever be charged.

---

## 9. Caveats on these numbers

- Token counts for the **web‑search steps are the biggest source of error** — a search that pulls in several long articles can push input well above the estimates here.
- Estimates assume **every pipeline runs every day**. If automation is paused, real cost is lower.
- **Thinking tokens** (adaptive thinking on the Sonnet scoring/planning steps) are billed as output and are included in the output estimates, but their exact size varies per run.
- Prices are current Anthropic list prices for Sonnet 4.6 / Haiku 4.5 and the web‑search tool as of this document's date.

**For exact figures, the source of truth is your Anthropic Console usage dashboard** (console.anthropic.com → Usage), which shows real per‑day token spend and web‑search counts.
