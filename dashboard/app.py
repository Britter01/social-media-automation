"""Brite Tech Lifestyle — Automation Dashboard."""

from __future__ import annotations

import calendar
import hmac
import html
import logging
import os
import time
from collections import Counter, defaultdict
from datetime import UTC, date, datetime

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logger = logging.getLogger(__name__)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Brite Tech Lifestyle — Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS / JS injection ────────────────────────────────────────────────────────
# Injected into the parent document (not the iframe) so it applies globally.
# We also start the 60-second auto-refresh countdown here.

components.html(
    r"""
<script>
(function () {
  const doc = window.parent.document;

  /* ── Brand fonts ─────────────────────────────────────────────────────── */
  if (!doc.getElementById('btl-fonts')) {
    const link = doc.createElement('link');
    link.id   = 'btl-fonts';
    link.rel  = 'stylesheet';
    link.href = 'https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800;900&family=Bricolage+Grotesque:opsz,wght@12..60,300;12..60,400;12..60,500;12..60,600&display=swap';
    doc.head.appendChild(link);
  }

  /* ── Theme CSS ───────────────────────────────────────────────────────── */
  const CSS = `
    :root {
      --bg-base:#0b0d12; --bg-card:#131621; --bg-raised:#1a1d28;
      --border:#1e2335;  --border-vis:#252840;
      --accent:#4d8eff;  --accent-dim:rgba(77,142,255,0.12);
      --text-pri:#e6e8f0; --text-sec:#7a8299; --text-faint:#3d4155;
    }
    html, body, [class*="css"], button, input, textarea, select {
      font-family: 'Bricolage Grotesque', system-ui, sans-serif !important;
    }
    .stApp, [data-testid="stAppViewContainer"] { background: var(--bg-base) !important; }
    [data-testid="stHeader"] {
      background: var(--bg-base) !important;
      border-bottom: 1px solid var(--border) !important;
    }
    [data-testid="stSidebar"] {
      background: var(--bg-card) !important;
      border-right: 1px solid var(--border) !important;
    }
    [data-testid="stSidebar"] * { color: var(--text-pri) !important; }
    [data-testid="stSidebarContent"] h1,
    [data-testid="stSidebarContent"] h2,
    [data-testid="stSidebarContent"] h3 {
      font-family: 'Big Shoulders Display', sans-serif !important;
      letter-spacing: -0.02em !important;
    }
    #MainMenu, footer { visibility: hidden; }
    .block-container { padding-top: 3.5rem !important; max-width: 1420px !important; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
      background: var(--bg-card) !important;
      border: 1px solid var(--border-vis) !important;
      border-radius: 10px !important;
      padding: 4px !important;
      gap: 2px !important;
      margin-bottom: 8px !important;
    }
    .stTabs [data-baseweb="tab"] {
      border-radius: 7px !important;
      font-weight: 600 !important;
      font-size: 13px !important;
      color: var(--text-sec) !important;
      background: transparent !important;
      padding: 7px 16px !important;
    }
    .stTabs [aria-selected="true"] {
      background: var(--text-pri) !important;
      color: var(--bg-base) !important;
    }
    .stTabs [data-baseweb="tab-border"] { display: none !important; }
    .stTabs [data-baseweb="tab-panel"] { padding-top: 8px !important; }

    /* ── Buttons ── */
    .stButton > button {
      border-radius: 8px !important;
      font-weight: 600 !important;
      background: var(--bg-raised) !important;
      color: var(--text-pri) !important;
      border: 1px solid var(--border-vis) !important;
    }
    .stButton > button:hover {
      background: var(--border-vis) !important;
      border-color: var(--accent) !important;
      color: var(--text-pri) !important;
    }
    .stButton > button[kind="primary"] {
      background: var(--accent) !important;
      border-color: var(--accent) !important;
      color: #fff !important;
    }
    .stButton > button[kind="primary"]:hover {
      background: #6da0ff !important;
    }
    .stButton > button[kind="secondary"] {
      background: var(--bg-raised) !important;
    }

    /* ── Containers ── */
    [data-testid="stVerticalBlockBorderWrapper"] {
      background: var(--bg-card) !important;
      border: 1px solid var(--border-vis) !important;
      border-radius: 12px !important;
    }

    /* ── Expanders ── */
    [data-testid="stExpander"] details {
      background: var(--bg-card) !important;
      border: 1px solid var(--border-vis) !important;
      border-radius: 10px !important;
      margin-bottom: 6px !important;
      overflow: hidden !important;
    }
    [data-testid="stExpander"] summary {
      background: var(--bg-raised) !important;
      color: var(--text-pri) !important;
      font-weight: 600 !important;
      font-size: 13px !important;
      padding: 10px 14px !important;
      cursor: pointer !important;
    }

    /* ── Alerts ── */
    .stAlert {
      background: var(--bg-card) !important;
      border: 1px solid var(--border-vis) !important;
      color: var(--text-pri) !important;
      border-radius: 10px !important;
    }

    /* ── Inputs ── */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input {
      background: var(--bg-raised) !important;
      border: 1px solid var(--border-vis) !important;
      color: var(--text-pri) !important;
      border-radius: 8px !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus {
      border-color: var(--accent) !important;
    }
    [data-baseweb="select"] > div:first-child {
      background: var(--bg-raised) !important;
      border: 1px solid var(--border-vis) !important;
      color: var(--text-pri) !important;
      border-radius: 8px !important;
    }
    [data-baseweb="popover"] [data-baseweb="menu"] {
      background: var(--bg-raised) !important;
      border: 1px solid var(--border-vis) !important;
      border-radius: 8px !important;
    }
    [data-baseweb="option"] { background: var(--bg-raised) !important; color: var(--text-pri) !important; }
    [data-baseweb="option"]:hover { background: var(--border-vis) !important; }

    /* ── Text ── */
    [data-testid="stMarkdownContainer"] p { color: var(--text-pri) !important; }
    [data-testid="stCaptionContainer"] { color: var(--text-sec) !important; }
    .stCaption { color: var(--text-sec) !important; }
    hr { border-color: var(--border) !important; }
    h1, h2, h3 {
      font-family: 'Big Shoulders Display', sans-serif !important;
      letter-spacing: -0.02em !important;
      color: var(--text-pri) !important;
    }
    [data-testid="stMetric"] label { color: var(--text-sec) !important; }
    [data-testid="stMetricValue"] { color: var(--text-pri) !important; }
    [data-testid="stCheckbox"] label { color: var(--text-pri) !important; }
  `;

  if (!doc.getElementById('btl-css')) {
    const style = doc.createElement('style');
    style.id = 'btl-css';
    style.textContent = CSS;
    doc.head.appendChild(style);
  }

  /* ── Auto-refresh countdown badge ───────────────────────────────────── */
  const existing = doc.getElementById('btl-badge');
  if (existing) existing.remove();

  const badge = doc.createElement('div');
  badge.id = 'btl-badge';
  badge.style.cssText = `
    position:fixed; bottom:20px; right:20px;
    background:#131621; border:1px solid #252840; border-radius:8px;
    padding:5px 12px; font-family:'Bricolage Grotesque',sans-serif;
    font-size:12px; color:#7a8299; z-index:9999; cursor:pointer;
    user-select:none; transition:border-color 0.25s, color 0.25s;
  `;
  let secs = 60, paused = false;
  function tick() {
    badge.textContent = paused ? '⏸  refresh paused' : '↺  ' + secs + 's';
    badge.style.borderColor = paused ? '#3d4155' : (secs < 10 ? '#4d8eff' : '#252840');
    badge.style.color = paused ? '#3d4155' : (secs < 10 ? '#4d8eff' : '#7a8299');
  }
  tick();
  badge.addEventListener('click', () => { paused = !paused; tick(); });
  doc.body.appendChild(badge);
  const t = setInterval(() => {
    if (!paused) { secs--; tick(); if (secs <= 0) { clearInterval(t); window.parent.location.reload(); } }
  }, 1000);
})();
</script>
""",
    height=0,
)

# ── Authentication ────────────────────────────────────────────────────────────

_AUTH_MAX_ATTEMPTS = 5
_AUTH_LOCKOUT_SECS = 900


def _check_password() -> bool:
    try:
        expected = st.secrets.get("DASHBOARD_PASSWORD") or os.getenv("DASHBOARD_PASSWORD", "")
    except Exception:
        expected = os.getenv("DASHBOARD_PASSWORD", "")
    if not expected:
        st.error("DASHBOARD_PASSWORD is not set.")
        st.stop()
    if st.session_state.get("authenticated"):
        return True
    now = datetime.now(UTC).timestamp()
    attempts: list[float] = [
        t for t in st.session_state.get("_auth_attempts", []) if now - t < _AUTH_LOCKOUT_SECS
    ]
    if len(attempts) >= _AUTH_MAX_ATTEMPTS:
        st.error("Too many failed attempts. Please wait 15 minutes and try again.")
        return False

    st.markdown("<br>" * 4, unsafe_allow_html=True)
    col = st.columns([1, 1, 1])[1]
    with col:
        st.markdown(
            """
<div style="text-align:center;margin-bottom:32px">
  <div style="font-family:'Big Shoulders Display',sans-serif;font-size:64px;
              font-weight:900;letter-spacing:-0.04em;color:#e6e8f0;line-height:1">Brite</div>
  <div style="font-size:10px;font-weight:400;letter-spacing:0.28em;color:#3d4155;
              text-transform:uppercase;margin-top:6px">Tech Lifestyle</div>
  <div style="font-size:13px;color:#7a8299;margin-top:16px">Automation Dashboard</div>
</div>
""",
            unsafe_allow_html=True,
        )
        pwd = st.text_input(
            "Password", type="password", placeholder="Enter password", label_visibility="collapsed"
        )
        if st.button("Sign in", use_container_width=True, type="primary"):
            if hmac.compare_digest(pwd, expected):
                st.session_state["authenticated"] = True
                st.session_state["_auth_attempts"] = []
                st.rerun()
            else:
                attempts.append(now)
                st.session_state["_auth_attempts"] = attempts
                time.sleep(1)
                st.error("Incorrect password.")
    return False


if not _check_password():
    st.stop()

# ── Supabase ──────────────────────────────────────────────────────────────────


@st.cache_resource
def get_db():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except (KeyError, FileNotFoundError):
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        st.error("SUPABASE_URL and SUPABASE_KEY must be set.")
        st.stop()
    return create_client(url, key)


db = get_db()

# ── Data ──────────────────────────────────────────────────────────────────────


@st.cache_data(ttl=60)
def load_topics():
    return (
        db.table("topics").select("*").order("relevance_score", desc=True).limit(200).execute().data
        or []
    )


@st.cache_data(ttl=60)
def load_posts():
    return (
        db.table("posts").select("*").order("scheduled_time", desc=False).limit(500).execute().data
        or []
    )


topics = load_topics()
posts = load_posts()


def by_status(items, *statuses):
    return [i for i in items if i.get("status") in statuses]


pending = by_status(topics, "pending_approval")
approved_t = by_status(topics, "approved")
in_progress = by_status(posts, "content_ready", "media_ready")
scheduled = by_status(posts, "scheduled")
published = by_status(posts, "published")
failed = by_status(posts, "failed")

# ── Sidebar — pipeline controls ───────────────────────────────────────────────

_CMD_COOLDOWN_SECS = 10
_VALID_PILLARS = ["AI Guide", "Tech Lifestyle", "Productivity", "Fitness Tech", "Review"]
_VALID_PLATFORMS = ["instagram", "facebook", "twitter", "linkedin", "youtube", "tiktok"]


def _queue_command(command: str, cooldown_key: str | None = None) -> None:
    key = f"_cmd_ts_{cooldown_key or command}"
    now = datetime.now(UTC).timestamp()
    if now - st.session_state.get(key, 0.0) < _CMD_COOLDOWN_SECS:
        raise RuntimeError("Please wait a moment before running again.")
    db.table("pipeline_commands").insert(
        {"command": command, "status": "pending", "requested_at": datetime.now(UTC).isoformat()}
    ).execute()
    st.session_state[key] = now


with st.sidebar:
    st.markdown(
        """
<div style="padding:8px 0 20px">
  <div style="font-family:'Big Shoulders Display',sans-serif;font-size:42px;
              font-weight:900;letter-spacing:-0.04em;color:#e6e8f0;line-height:1">Brite</div>
  <div style="font-size:9px;letter-spacing:0.28em;color:#3d4155;
              text-transform:uppercase;margin-top:4px">Tech Lifestyle</div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;"
        "color:#3d4155;margin-bottom:8px'>Pipeline Controls</div>",
        unsafe_allow_html=True,
    )

    _cmds = [
        ("Research Now", "research", "Discover trending topics for the approval queue."),
        (
            "Weekly Strategy",
            "weekly_strategy",
            "Competitor-pattern analysis. Queues 7 shaped ideas.",
        ),
        ("Content Pipeline", "content", "Generate posts directly (skips research gate)."),
        ("Refresh Images", "image_refresh", "Regenerate missing or failed thumbnails."),
        ("Publish Due Posts", "publish", "Push any scheduled post whose time has passed."),
        ("Run Everything", "all", "Image refresh + publish in one go."),
    ]
    for label, cmd, tip in _cmds:
        if st.button(label, use_container_width=True, help=tip):
            try:
                _queue_command(cmd)
                st.success("Queued — worker picks up within 2 min.")
            except RuntimeError as e:
                st.warning(str(e))
            except Exception:
                st.error("Failed to queue command.")

    st.divider()

    # Manual data refresh
    if st.button("↺  Refresh data now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    now_utc = datetime.now(UTC)
    st.markdown(
        f"<div style='font-size:11px;color:#3d4155;margin-top:8px'>"
        f"{now_utc.strftime('%d %b %Y · %H:%M UTC')}</div>",
        unsafe_allow_html=True,
    )

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(
    """
<div style="background:#131621;border:1px solid #1e2335;border-radius:14px;
            padding:18px 28px;margin-bottom:16px;
            display:flex;align-items:center;justify-content:space-between">
  <div>
    <div style="font-family:'Big Shoulders Display',sans-serif;font-size:13px;
                font-weight:700;letter-spacing:0.12em;text-transform:uppercase;
                color:#3d4155;margin-bottom:4px">Content Pipeline</div>
    <div style="font-family:'Big Shoulders Display',sans-serif;font-size:28px;
                font-weight:800;letter-spacing:-0.02em;color:#e6e8f0;line-height:1">
      Everything that goes out, in one place.
    </div>
  </div>
  <div style="text-align:right">
    <div style="font-size:11px;color:#3d4155;font-style:italic">Technology, beautifully lived.</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ── Pipeline status bar ───────────────────────────────────────────────────────

STAGES = [
    ("Pending Review", len(pending), "#F59E0B"),
    ("In Progress", len(in_progress), "#8B5CF6"),
    ("Scheduled", len(scheduled), "#10B981"),
    ("Published", len(published), "#059669"),
    ("Failed", len(failed), "#EF4444"),
]

cols = st.columns(len(STAGES))
for i, (label, count, color) in enumerate(STAGES):
    with cols[i]:
        st.markdown(
            f"""<div style="background:{color}10;border:1px solid {color}30;border-radius:10px;
                            padding:14px 10px;text-align:center">
              <div style="font-size:32px;font-weight:900;font-family:'Big Shoulders Display',sans-serif;
                          color:{color};line-height:1;letter-spacing:-0.02em">{count}</div>
              <div style="font-size:10px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;
                          color:{color};opacity:0.7;margin-top:5px">{label}</div>
            </div>""",
            unsafe_allow_html=True,
        )

st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

PLATFORM_COLORS = {
    "instagram": "#E91E8C",
    "facebook": "#1877F2",
    "twitter": "#1DA1F2",
    "linkedin": "#0A66C2",
    "tiktok": "#25F4EE",
    "youtube": "#FF0000",
}


def _pill(text: str, color: str, bg_alpha: str = "18") -> str:
    e = html.escape(str(text))
    return (
        f"<span style='background:{color}{bg_alpha};color:{color};border-radius:6px;"
        f"padding:2px 9px;font-size:11px;font-weight:700;letter-spacing:0.04em;"
        f"text-transform:uppercase'>{e}</span>"
    )


def _sched_str(p):
    raw = p.get("scheduled_time") or p.get("published_time") or ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%a %d %b · %H:%M")
    except Exception:
        return raw


def _post_card(post: dict, time_str: str = "", time_label: str = "") -> None:
    is_carousel = post.get("post_type") == "carousel"
    slides = post.get("slides") or []
    platform = post.get("platform", "")
    title = post.get("title") or post.get("topic") or "Untitled"
    pillar = post.get("pillar") or "—"
    caption = post.get("caption") or ""
    hashtags = post.get("hashtags") or []
    plat_color = PLATFORM_COLORS.get(platform.lower(), "#7a8299")
    sched_color = "#10B981" if time_label == "scheduled" else "#059669"

    e_title = html.escape(str(title))
    e_pillar = html.escape(str(pillar))
    e_caption = html.escape(str(caption))

    url = post.get("thumbnail_url", "")
    if url:
        st.image(url if url.endswith(".png") else url + ".png", use_container_width=True)
    else:
        st.markdown(
            "<div style='background:#1a1d28;border-radius:8px;height:88px;display:flex;"
            "align-items:center;justify-content:center;color:#3d4155;font-size:12px'>"
            "No image yet</div>",
            unsafe_allow_html=True,
        )

    pills = _pill(platform, plat_color) + " "
    if is_carousel:
        pills += f"<span style='color:#8B5CF6;font-size:11px;font-weight:700'>⬡ {len(slides)} slides</span> "
    if time_str:
        icon = "📅" if time_label == "scheduled" else "📢"
        pills += f"<span style='color:{sched_color};font-size:11px;font-weight:600'>{icon} {html.escape(time_str)}</span>"

    st.markdown(
        f"""<div style='padding:6px 2px 4px'>
          <div style='margin-bottom:5px'>{pills}</div>
          <div style='font-family:"Big Shoulders Display",sans-serif;font-size:17px;font-weight:700;
                      color:#e6e8f0;line-height:1.2;margin-bottom:3px'>{e_title}</div>
          <div style='font-size:11px;color:#7a8299'>{e_pillar}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    if is_carousel and slides:
        with st.expander(f"View {len(slides)} slides"):
            for j, slide in enumerate(slides):
                role = slide.get("role", "")
                tag = " (cover)" if role == "cover" else " (CTA)" if role == "cta" else ""
                e_hl = html.escape(str(slide.get("headline", "")))
                e_bd = html.escape(str(slide.get("body", "")))
                st.markdown(
                    f"<div style='font-weight:700;color:#e6e8f0;font-size:13px'>"
                    f"{j + 1}. {e_hl}{tag}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='font-size:12px;color:#7a8299;margin-bottom:6px'>{e_bd}</div>",
                    unsafe_allow_html=True,
                )
                img = slide.get("image_url", "")
                if img:
                    st.image(
                        img if img.endswith(".png") else img + ".png", use_container_width=True
                    )
                st.divider()
    elif caption:
        tags_html = (
            "<div style='font-size:11px;color:#4d8eff;margin-top:6px;line-height:1.8'>"
            + " ".join(f"#{html.escape(str(h))}" for h in hashtags)
            + "</div>"
            if hashtags
            else ""
        )
        st.markdown(
            f"""<details style="margin-top:8px;border:1px solid #1e2335;border-radius:8px;overflow:hidden">
              <summary style="padding:9px 14px;font-size:12px;font-weight:600;color:#e6e8f0;
                              background:#1a1d28;cursor:pointer;list-style:none">
                Caption ›
              </summary>
              <div style="padding:12px 14px;font-size:13px;color:#e6e8f0;
                          line-height:1.7;background:#131621">
                {e_caption}{tags_html}
              </div>
            </details>""",
            unsafe_allow_html=True,
        )


# ── Tabs ──────────────────────────────────────────────────────────────────────

(
    tab_topics,
    tab_progress,
    tab_scheduled,
    tab_calendar,
    tab_published,
    tab_pipeline,
) = st.tabs(
    [
        f"Topics  {len(pending)}",
        f"In Progress  {len(in_progress)}",
        f"Scheduled  {len(scheduled)}",
        "Calendar",
        f"Published  {len(published)}",
        "Pipeline",
    ]
)

# ── Topics ────────────────────────────────────────────────────────────────────

with tab_topics:
    if not pending:
        st.info("All clear — no topics awaiting review. Research runs daily at 05:30.")
    else:
        # Bulk approve
        ba_col, _, count_col = st.columns([1, 3, 1])
        with ba_col:
            if st.button(f"Approve all {len(pending)}", type="primary"):
                ids = [t["id"] for t in pending if t.get("id")]
                if ids:
                    db.table("topics").update({"status": "approved"}).in_("id", ids).execute()
                    st.cache_data.clear()
                    st.rerun()
        with count_col:
            st.markdown(
                f"<div style='text-align:right;font-size:12px;color:#7a8299;padding-top:6px'>"
                f"{len(pending)} awaiting</div>",
                unsafe_allow_html=True,
            )

        for topic in pending:
            with st.container(border=True):
                score = topic.get("relevance_score", 0)
                sc = "#10B981" if score >= 80 else "#F59E0B" if score >= 60 else "#EF4444"
                tid = topic["id"]
                plat = topic.get("platform", "")
                e_title = html.escape(str(topic.get("title", "")))
                pillar_val = topic.get("pillar", "—")

                # Header row: title + score + platform + action buttons
                h_left, h_right = st.columns([5, 1])
                with h_left:
                    st.markdown(
                        f'<div style=\'font-family:"Big Shoulders Display",sans-serif;'
                        f"font-size:18px;font-weight:700;color:#e6e8f0;margin-bottom:4px'>"
                        f"{e_title}</div>"
                        f"<div style='margin-bottom:6px'>"
                        f"{_pill(f'Score {score}', sc)} &nbsp;"
                        f"{_pill(plat, PLATFORM_COLORS.get(plat.lower(), '#7a8299'))} &nbsp;"
                        f"<span style='font-size:11px;color:#7a8299'>{html.escape(pillar_val)}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.caption(topic.get("summary", ""))
                    if topic.get("content_angle"):
                        st.markdown(
                            f"<div style='font-size:12px;color:#7a8299;margin-top:2px'>"
                            f"<b style='color:#e6e8f0'>Angle:</b> {html.escape(topic['content_angle'])}</div>",
                            unsafe_allow_html=True,
                        )
                    if topic.get("rationale"):
                        st.markdown(
                            f"<div style='font-size:12px;color:#7a8299'>"
                            f"<b style='color:#e6e8f0'>Why:</b> {html.escape(topic['rationale'])}</div>",
                            unsafe_allow_html=True,
                        )
                    for src in (topic.get("sources") or [])[:2]:
                        if src.startswith(("http://", "https://")):
                            st.markdown(
                                f"<div style='font-size:11px;color:#4d8eff'>"
                                f"<a href='{html.escape(src)}' target='_blank' "
                                f"style='color:#4d8eff'>{html.escape(src[:60])}…</a></div>",
                                unsafe_allow_html=True,
                            )

                with h_right:
                    if st.button(
                        "Approve", key=f"a_{tid}", use_container_width=True, type="primary"
                    ):
                        db.table("topics").update({"status": "approved"}).eq("id", tid).execute()
                        st.cache_data.clear()
                        st.rerun()
                    if st.button("Reject", key=f"r_{tid}", use_container_width=True):
                        db.table("topics").update({"status": "rejected"}).eq("id", tid).execute()
                        st.cache_data.clear()
                        st.rerun()

                # Edit platform / pillar inline
                with st.expander("Edit before approving"):
                    ef1, ef2, ef3 = st.columns([2, 2, 1])
                    with ef1:
                        new_platform = st.selectbox(
                            "Platform",
                            _VALID_PLATFORMS,
                            index=_VALID_PLATFORMS.index(plat) if plat in _VALID_PLATFORMS else 0,
                            key=f"edit_plat_{tid}",
                        )
                    with ef2:
                        new_pillar = st.selectbox(
                            "Pillar",
                            _VALID_PILLARS,
                            index=_VALID_PILLARS.index(pillar_val)
                            if pillar_val in _VALID_PILLARS
                            else 0,
                            key=f"edit_pillar_{tid}",
                        )
                    with ef3:
                        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                        if st.button("Save & Approve", key=f"save_{tid}", use_container_width=True):
                            db.table("topics").update(
                                {
                                    "platform": new_platform,
                                    "pillar": new_pillar,
                                    "status": "approved",
                                }
                            ).eq("id", tid).execute()
                            st.cache_data.clear()
                            st.rerun()

# ── In Progress ───────────────────────────────────────────────────────────────

with tab_progress:
    if not in_progress:
        st.info("Nothing being processed right now.")
    else:
        cols = st.columns(3)
        for i, post in enumerate(in_progress):
            with cols[i % 3]:
                with st.container(border=True):
                    _post_card(post)
                    pid = post.get("id", "")
                    if pid and st.button(
                        "Dismiss", key=f"dismiss_prog_{pid}", use_container_width=True
                    ):
                        db.table("posts").update({"status": "dismissed"}).eq("id", pid).execute()
                        st.cache_data.clear()
                        st.rerun()

# ── Scheduled ─────────────────────────────────────────────────────────────────

with tab_scheduled:
    if not scheduled:
        st.info("Nothing scheduled yet.")
    else:
        sched_sorted = sorted(scheduled, key=lambda p: p.get("scheduled_time") or "")
        cols = st.columns(3)
        for i, p in enumerate(sched_sorted):
            with cols[i % 3]:
                with st.container(border=True):
                    _post_card(p, _sched_str(p), "scheduled")
                    pid = p.get("id", "")
                    btn_pub, btn_dis = st.columns(2)
                    with btn_pub:
                        if pid and st.button(
                            "Publish now",
                            key=f"pub_{pid}",
                            use_container_width=True,
                            type="primary",
                        ):
                            db.table("posts").update(
                                {"scheduled_time": datetime.now(UTC).isoformat()}
                            ).eq("id", pid).execute()
                            try:
                                _queue_command("publish", cooldown_key=f"pub_{pid}")
                                st.success("Queued — publishing within 2 min.")
                            except RuntimeError as e:
                                st.warning(str(e))
                    with btn_dis:
                        if pid and st.button(
                            "Dismiss", key=f"dismiss_sched_{pid}", use_container_width=True
                        ):
                            db.table("posts").update({"status": "dismissed"}).eq(
                                "id", pid
                            ).execute()
                            st.cache_data.clear()
                            st.rerun()

# ── Calendar ──────────────────────────────────────────────────────────────────

with tab_calendar:
    all_active = [p for p in posts if p.get("status") not in ("failed", "draft", "dismissed")]
    date_posts: dict[date, list[dict]] = defaultdict(list)
    for p in all_active:
        raw = p.get("scheduled_time") or p.get("published_time") or ""
        if raw:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                date_posts[dt.date()].append(p)
            except Exception:
                pass

    today = datetime.now(UTC).date()
    if "cal_year" not in st.session_state:
        st.session_state.cal_year = today.year
    if "cal_month" not in st.session_state:
        st.session_state.cal_month = today.month

    col_p, col_t, col_n = st.columns([1, 5, 1])
    with col_p:
        if st.button("← Prev", use_container_width=True):
            if st.session_state.cal_month == 1:
                st.session_state.cal_month = 12
                st.session_state.cal_year -= 1
            else:
                st.session_state.cal_month -= 1
            st.rerun()
    with col_t:
        mname = datetime(st.session_state.cal_year, st.session_state.cal_month, 1).strftime("%B %Y")
        st.markdown(
            f'<div style=\'font-family:"Big Shoulders Display",sans-serif;font-size:26px;'
            f"font-weight:800;letter-spacing:-0.02em;color:#e6e8f0;text-align:center;"
            f"padding:4px 0'>{mname}</div>",
            unsafe_allow_html=True,
        )
    with col_n:
        if st.button("Next →", use_container_width=True):
            if st.session_state.cal_month == 12:
                st.session_state.cal_month = 1
                st.session_state.cal_year += 1
            else:
                st.session_state.cal_month += 1
            st.rerun()

    year = st.session_state.cal_year
    month = st.session_state.cal_month
    cal = calendar.monthcalendar(year, month)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    header_html = "".join(
        f'<div style="text-align:center;font-size:10px;font-weight:700;letter-spacing:0.1em;'
        f'text-transform:uppercase;color:#3d4155;padding:8px 0">{d}</div>'
        for d in days
    )
    cells_html = ""
    for week in cal:
        for day_num in week:
            if day_num == 0:
                cells_html += '<div style="min-height:80px"></div>'
                continue
            d = date(year, month, day_num)
            is_today = d == today
            day_posts = date_posts.get(d, [])
            border = "2px solid #4d8eff" if is_today else "1px solid #1e2335"
            num_color = "#4d8eff" if is_today else "#e6e8f0"
            dots = ""
            for p in day_posts[:8]:
                plat = (p.get("platform") or "").lower()
                c = PLATFORM_COLORS.get(plat, "#7a8299")
                t = html.escape(str(p.get("topic", "")))
                dots += (
                    f'<div style="width:10px;height:10px;border-radius:50%;'
                    f'background:{c};flex-shrink:0" title="{t}"></div>'
                )
            count_html = (
                f'<div style="font-size:10px;font-weight:700;color:#4d8eff;margin-top:4px">'
                f"{len(day_posts)}</div>"
                if day_posts
                else ""
            )
            cells_html += (
                f'<div style="background:#131621;border:{border};border-radius:8px;'
                f'min-height:80px;padding:8px">'
                f'<div style="font-size:13px;font-weight:700;color:{num_color};margin-bottom:4px">'
                f"{day_num}</div>"
                f'<div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">{dots}</div>'
                f"{count_html}</div>"
            )

    cal_html = (
        "<!DOCTYPE html><html><head>"
        '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..60,400;12..60,600&display=swap" rel="stylesheet">'
        "<style>*{margin:0;padding:0;box-sizing:border-box;"
        "font-family:'Bricolage Grotesque',sans-serif}body{background:#0b0d12;padding:6px}</style>"
        "</head><body>"
        f'<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:5px">'
        f"{header_html}{cells_html}</div></body></html>"
    )
    components.html(cal_html, height=len(cal) * 93 + 48, scrolling=False)

    legend = " &nbsp; ".join(
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'font-size:12px;color:#7a8299">'
        f'<span style="width:10px;height:10px;border-radius:50%;background:{c};'
        f'display:inline-block"></span>{p.title()}</span>'
        for p, c in PLATFORM_COLORS.items()
    )
    st.markdown(f"<div style='margin-top:10px'>{legend}</div>", unsafe_allow_html=True)

    st.divider()
    col_d, col_m, col_y = st.columns(3)
    with col_d:
        sel_day = st.number_input("Day", 1, 31, today.day, label_visibility="collapsed")
    with col_m:
        sel_mn = st.selectbox(
            "Month", list(calendar.month_name)[1:], index=month - 1, label_visibility="collapsed"
        )
        sel_m = list(calendar.month_name).index(sel_mn)
    with col_y:
        sel_y = st.number_input("Year", 2026, 2030, year, label_visibility="collapsed")
    try:
        sel_date = date(sel_y, sel_m, int(sel_day))
        day_items = date_posts.get(sel_date, [])
        if day_items:
            st.caption(f"{len(day_items)} post(s) on {sel_date.strftime('%A %d %B %Y')}")
            dcols = st.columns(min(len(day_items), 3))
            for i, p in enumerate(day_items):
                with dcols[i % 3]:
                    with st.container(border=True):
                        _post_card(p, _sched_str(p), p.get("status", "scheduled"))
        else:
            st.caption(f"No posts on {sel_date.strftime('%A %d %B %Y')}.")
    except ValueError:
        st.warning("Invalid date.")

    month_items = [
        p for d, ps in date_posts.items() for p in ps if d.year == year and d.month == month
    ]
    if month_items:
        pcounts = Counter(p.get("platform", "").lower() for p in month_items)
        st.markdown(
            f'<div style=\'font-family:"Big Shoulders Display",sans-serif;'
            f"font-size:18px;font-weight:700;color:#e6e8f0;margin-top:12px'>"
            f"{mname} — {len(month_items)} posts</div>",
            unsafe_allow_html=True,
        )
        scols = st.columns(len(pcounts))
        for i, (plat, cnt) in enumerate(sorted(pcounts.items(), key=lambda x: -x[1])):
            c = PLATFORM_COLORS.get(plat, "#7a8299")
            with scols[i]:
                st.markdown(
                    f'<div style="background:{c}12;border:1px solid {c}30;'
                    f'border-radius:8px;padding:12px;text-align:center;margin-top:6px">'
                    f'<div style="font-size:24px;font-weight:800;'
                    f"font-family:'Big Shoulders Display',sans-serif;color:{c}\">{cnt}</div>"
                    f'<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
                    f'text-transform:uppercase;color:{c};opacity:0.7;margin-top:3px">{plat}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

# ── Published ─────────────────────────────────────────────────────────────────

with tab_published:
    if not published:
        st.info("Nothing published yet — posts will appear here once live.")
    else:
        cols = st.columns(3)
        for i, post in enumerate(published):
            with cols[i % 3]:
                with st.container(border=True):
                    _post_card(post, _sched_str(post), "published")

# ── Pipeline flowchart ────────────────────────────────────────────────────────

with tab_pipeline:
    st.markdown(
        '<div style=\'font-family:"Big Shoulders Display",sans-serif;font-size:22px;'
        "font-weight:800;letter-spacing:-0.02em;color:#e6e8f0;margin-bottom:12px'>"
        "How the pipeline works</div>",
        unsafe_allow_html=True,
    )

    FLOW_HTML = r"""<!DOCTYPE html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800&family=Bricolage+Grotesque:opsz,wght@12..60,400;12..60,500;12..60,600&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; font-family:'Bricolage Grotesque',sans-serif; }
body { background:#0b0d12; color:#e6e8f0; padding:20px; font-size:13px; }
.row { display:flex; align-items:flex-start; justify-content:center; gap:12px; margin-bottom:6px; }
.arr { text-align:center; color:#3d4155; font-size:22px; margin:2px 0; }
.node {
  background:#131621; border:1px solid #252840; border-radius:10px;
  padding:12px 16px; text-align:center; min-width:140px; max-width:180px;
}
.node .label {
  font-family:'Big Shoulders Display',sans-serif; font-size:15px; font-weight:700;
  color:#e6e8f0; line-height:1.2;
}
.node .sub { font-size:11px; color:#7a8299; margin-top:4px; line-height:1.4; }
.node .badge {
  display:inline-block; border-radius:4px; padding:2px 8px;
  font-size:10px; font-weight:600; letter-spacing:0.06em; text-transform:uppercase;
  margin-top:6px;
}
.node.trigger { border-color:#F59E0B40; background:#F59E0B08; }
.node.trigger .label { color:#F59E0B; }
.node.gate { border-color:#10B98140; background:#10B98108; }
.node.gate .label { color:#10B981; }
.node.media { border-color:#8B5CF640; background:#8B5CF608; }
.node.media .label { color:#8B5CF6; }
.node.publish { border-color:#4d8eff40; background:#4d8eff08; }
.node.publish .label { color:#4d8eff; }
.node.live { border-color:#059669; background:#05966910; }
.node.live .label { color:#10B981; }
.col2 { display:flex; gap:12px; }
.connector { display:flex; flex-direction:column; align-items:center; }
.line { width:1px; background:#252840; flex:1; min-height:16px; }
.split { display:flex; align-items:flex-start; gap:12px; position:relative; }
.split-bar { width:calc(100% - 24px); height:1px; background:#252840; position:absolute; top:0; left:12px; }
.tag { font-size:10px; color:#3d4155; letter-spacing:0.06em; text-transform:uppercase; margin-bottom:4px; }
</style>
</head><body>

<!-- Row 1: Two trigger nodes -->
<div class="row">
  <div class="node trigger">
    <div class="tag">Daily 05:30</div>
    <div class="label">Research Agent</div>
    <div class="sub">Searches the web for trending topics across your 5 niches. Scores each for brand fit.</div>
  </div>
  <div style="min-width:12px"></div>
  <div class="node trigger">
    <div class="tag">Monday 07:00</div>
    <div class="label">Weekly Strategy</div>
    <div class="sub">Studies competitor accounts &amp; viral patterns. Generates 7 shaped ideas.</div>
  </div>
</div>

<!-- Arrows down -->
<div class="row"><div class="arr">↓</div><div style="min-width:60px"></div><div class="arr">↓</div></div>

<!-- Row 2: Approval gate -->
<div class="row">
  <div class="node gate" style="min-width:340px;max-width:400px">
    <div class="label">Approval Queue</div>
    <div class="sub">Topics land here. <b style="color:#10B981">You approve or reject each one.</b><br>
    Nothing moves forward without your sign-off. Use the Topics tab above.</div>
  </div>
</div>

<div class="row"><div class="arr">↓</div></div>
<div class="row"><div style="font-size:11px;color:#3d4155;letter-spacing:0.06em;text-transform:uppercase">every 15 min</div></div>
<div class="row"><div class="arr">↓</div></div>

<!-- Row 3: Content agent -->
<div class="row">
  <div class="node" style="min-width:300px">
    <div class="label">Content Agent</div>
    <div class="sub">Writes the caption, hashtags, and title for each approved topic. Uses Claude Sonnet.</div>
  </div>
</div>

<div class="row"><div class="arr">↓</div></div>

<!-- Row 4: Platform fork -->
<div class="row" style="align-items:stretch">
  <div class="node media" style="max-width:200px">
    <div class="tag">Instagram · Facebook</div>
    <div class="label">Carousel Agent</div>
    <div class="sub">Plans 4–6 slides with Claude. Cover photo from Imagen. Numbered dark text cards for content. CTA card at the end.</div>
  </div>
  <div style="display:flex;align-items:center;padding:0 8px">
    <div style="width:1px;height:60px;background:#252840"></div>
  </div>
  <div class="node media" style="max-width:200px">
    <div class="tag">Twitter · LinkedIn</div>
    <div class="label">Thumbnail Agent</div>
    <div class="sub">Single editorial photo from Imagen. Brand logo composited in quietest corner.</div>
  </div>
</div>

<div class="row"><div class="arr">↓</div></div>

<!-- Row 5: Scheduler -->
<div class="row">
  <div class="node publish" style="min-width:300px">
    <div class="label">Scheduler Agent</div>
    <div class="sub">Finds the best time slot for each platform based on peak-engagement windows. Status → <b style="color:#4d8eff">scheduled</b>.</div>
  </div>
</div>

<div class="row"><div class="arr">↓</div></div>
<div class="row"><div style="font-size:11px;color:#3d4155;letter-spacing:0.06em;text-transform:uppercase">every 5 min</div></div>
<div class="row"><div class="arr">↓</div></div>

<!-- Row 6: Publisher -->
<div class="row">
  <div class="node publish" style="min-width:300px">
    <div class="label">Publisher Agent</div>
    <div class="sub">Checks for posts whose scheduled time has passed and sends them to each platform's API.</div>
  </div>
</div>

<div class="row"><div class="arr">↓</div></div>

<!-- Row 7: Live -->
<div class="row">
  <div class="node live" style="min-width:300px">
    <div class="label">Live on Platform</div>
    <div class="sub">Status → <b style="color:#10B981">published</b>. Appears in the Published tab.</div>
  </div>
</div>

<div style="margin-top:28px;padding-top:16px;border-top:1px solid #1e2335">
  <div style="font-family:'Big Shoulders Display',sans-serif;font-size:14px;font-weight:700;
              color:#3d4155;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:12px">
    Background jobs</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap">
    <div class="node" style="min-width:0;max-width:none;flex:1;text-align:left;padding:10px 14px">
      <div class="label" style="font-size:13px">QC Retry  <span style="color:#3d4155;font-weight:400;font-size:11px">every 4 hrs</span></div>
      <div class="sub">Re-generates thumbnails that failed the image quality check.</div>
    </div>
    <div class="node" style="min-width:0;max-width:none;flex:1;text-align:left;padding:10px 14px">
      <div class="label" style="font-size:13px">Image Refresh  <span style="color:#3d4155;font-weight:400;font-size:11px">daily 02:00</span></div>
      <div class="sub">Regenerates any post that is missing a thumbnail image.</div>
    </div>
    <div class="node" style="min-width:0;max-width:none;flex:1;text-align:left;padding:10px 14px">
      <div class="label" style="font-size:13px">Cleanup  <span style="color:#3d4155;font-weight:400;font-size:11px">Sunday 03:00</span></div>
      <div class="sub">Prunes pipeline command rows older than 7 days.</div>
    </div>
  </div>
</div>

</body></html>"""

    components.html(FLOW_HTML, height=960, scrolling=True)

# ── Failed alert ──────────────────────────────────────────────────────────────

if failed:
    st.divider()
    with st.expander(f"⚠  {len(failed)} failed post(s) — click to review"):
        col_retry_all, col_del_all, _ = st.columns([1, 1, 4])
        with col_retry_all:
            if st.button("Retry all", key="retry_all_failed", type="primary"):
                ids = [p["id"] for p in failed if p.get("id")]
                if ids:
                    db.table("posts").update({"status": "scheduled", "error": None}).in_(
                        "id", ids
                    ).execute()
                    st.success(f"Reset {len(ids)} post(s) to scheduled.")
                    st.rerun()
        with col_del_all:
            if st.button("Dismiss all", key="delete_all_failed"):
                ids = [p["id"] for p in failed if p.get("id")]
                if ids:
                    db.table("posts").update({"status": "dismissed"}).in_("id", ids).execute()
                    st.success(f"Dismissed {len(ids)} failed post(s).")
                    st.rerun()

        for post in failed:
            title = post.get("title") or post.get("topic", "Untitled")
            detail = post.get("error") or "No detail"
            post_id = post.get("id", "")
            col_err, col_retry, col_del = st.columns([5, 1, 1])
            with col_err:
                st.markdown(
                    f"<div style='background:#EF444415;border:1px solid #EF444430;border-radius:8px;"
                    f"padding:10px 14px;margin-bottom:4px'>"
                    f"<div style='font-weight:700;color:#e6e8f0;font-size:13px'>"
                    f"{html.escape(str(title))} "
                    f"<span style='color:#7a8299;font-weight:400'>({html.escape(str(post.get('platform', '')))})</span>"
                    f"</div>"
                    f"<div style='font-size:12px;color:#EF4444;margin-top:4px'>"
                    f"{html.escape(str(detail))}</div></div>",
                    unsafe_allow_html=True,
                )
            with col_retry:
                if post_id and st.button("Retry", key=f"retry_{post_id}"):
                    db.table("posts").update({"status": "scheduled", "error": None}).eq(
                        "id", post_id
                    ).execute()
                    st.success("Reset.")
                    st.rerun()
            with col_del:
                if post_id and st.button("Dismiss", key=f"delete_{post_id}"):
                    db.table("posts").update({"status": "dismissed"}).eq("id", post_id).execute()
                    st.rerun()
