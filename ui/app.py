from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Final

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.master import MasterAgent
from core.models import AgentResult, MatchConfidence
from core.reasoning import ReasoningEngine

logger: logging.Logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="UzMarket Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

TEXTS: Final[dict[str, dict[str, str]]] = {
    "uz": {
        "title": "UzMarket Intelligence Agent",
        "subtitle": "Avtonom ko'p-marketplace mahsulot qidiruvi",
        "search_placeholder": "Mahsulot nomini kiriting (masalan: Samsung A33 5G 128GB)",
        "search_button": "Qidirish",
        "searching": "Qidirilmoqda...",
        "results_title": "Natijalar",
        "no_results": "Hech narsa topilmadi. Boshqa kalit so'zlarni sinab ko'ring.",
        "price": "Narx",
        "confidence": "Moslik",
        "marketplace": "Do'kon",
        "open_link": "Havolani ochish",
        "stats_scraped": "Jami topilgan",
        "stats_matched": "Mos keluvchi",
        "stats_time": "Vaqt",
        "stats_best": "Eng arzon",
        "reasoning": "Agent izoh",
        "parsed_query": "Tahlil qilingan so'rov",
        "errors": "Xatolar",
        "exact": "Aniq mos",
        "close": "Yaqin mos",
        "accessory": "Aksessuar",
        "unrelated": "Aloqasiz",
        "lang_switch": "English",
        "sec": "soniya",
    },
    "en": {
        "title": "UzMarket Intelligence Agent",
        "subtitle": "Autonomous Multi-Marketplace Product Search",
        "search_placeholder": "Enter product name (e.g., Samsung A33 5G 128GB)",
        "search_button": "Search",
        "searching": "Searching across marketplaces...",
        "results_title": "Results",
        "no_results": "No results found. Try different keywords.",
        "price": "Price",
        "confidence": "Match",
        "marketplace": "Store",
        "open_link": "Open link",
        "stats_scraped": "Total scraped",
        "stats_matched": "Matched",
        "stats_time": "Time",
        "stats_best": "Best price",
        "reasoning": "Agent reasoning",
        "parsed_query": "Parsed query",
        "errors": "Errors",
        "exact": "Exact match",
        "close": "Close match",
        "accessory": "Accessory",
        "unrelated": "Unrelated",
        "lang_switch": "O'zbekcha",
        "sec": "sec",
    },
}

CONFIDENCE_COLORS: Final[dict[MatchConfidence, str]] = {
    MatchConfidence.EXACT: "#2ecc71",
    MatchConfidence.CLOSE: "#f39c12",
    MatchConfidence.ACCESSORY: "#e74c3c",
    MatchConfidence.UNRELATED: "#95a5a6",
}

MARKETPLACE_ICONS: Final[dict[str, str]] = {
    "uzum": "🟣",
    "asaxiy": "🔵",
    "olcha": "🟢",
}


def _t(key: str) -> str:
    lang: str = st.session_state.get("lang", "uz")
    return TEXTS[lang].get(key, key)


# ── Sidebar ────────────────────────────────────────────────────

with st.sidebar:
    if "lang" not in st.session_state:
        st.session_state.lang = "uz"

    if st.button(_t("lang_switch")):
        st.session_state.lang = "en" if st.session_state.lang == "uz" else "uz"
        st.rerun()

    st.markdown("---")
    st.markdown("### Architecture")
    st.markdown(
        """
        ```
        User Query
           │
           ▼
        ┌─────────────┐
        │ Master Agent │
        │  (LLM Parse) │
        └──────┬──────┘
               │ asyncio.gather()
        ┌──────┼──────┐
        ▼      ▼      ▼
      Uzum  Asaxiy  Olcha
      Worker Worker Worker
        │      │      │
        └──────┼──────┘
               ▼
        ┌─────────────┐
        │ LLM Entity  │
        │ Alignment   │
        └──────┬──────┘
               ▼
        Ranked Results
        ```
        """
    )
    st.markdown("---")
    st.markdown(
        "**Research:** Agentic Web Navigation + "
        "Zero-shot Entity Resolution"
    )
    st.caption("Built for MBZUAI application")


# ── Main content ───────────────────────────────────────────────

st.title(_t("title"))
st.caption(_t("subtitle"))

query_input: str = st.text_input(
    label="search",
    placeholder=_t("search_placeholder"),
    label_visibility="collapsed",
)

search_clicked: bool = st.button(
    _t("search_button"), type="primary", use_container_width=True
)


def _run_search(q: str) -> AgentResult:
    engine: ReasoningEngine = ReasoningEngine()
    agent: MasterAgent = MasterAgent(reasoning_engine=engine)
    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(agent.run(q))
    finally:
        loop.close()


if search_clicked and query_input.strip():
    with st.spinner(_t("searching")):
        result: AgentResult = _run_search(query_input.strip())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(_t("stats_scraped"), result.total_scraped)
    c2.metric(_t("stats_matched"), result.total_matched)
    c3.metric(_t("stats_time"), f"{result.duration_seconds} {_t('sec')}")
    c4.metric(
        _t("stats_best"),
        f"{result.best_price:,} UZS" if result.best_price else "\u2014",
    )

    with st.expander(_t("parsed_query"), expanded=False):
        cols = st.columns(3)
        q = result.query
        cols[0].write(f"**Brand:** {q.brand or '\u2014'}")
        cols[0].write(f"**Model:** {q.model or '\u2014'}")
        cols[1].write(f"**Storage:** {q.storage_gb or '\u2014'} GB")
        cols[1].write(f"**RAM:** {q.ram_gb or '\u2014'} GB")
        cols[2].write(f"**Color:** {q.color or '\u2014'}")

    if result.errors:
        with st.expander(_t("errors"), expanded=False):
            for err in result.errors:
                st.error(err)

    st.subheader(_t("results_title"))

    if not result.matches:
        st.warning(_t("no_results"))
    else:
        for match in result.matches:
            listing = match.listing
            conf: MatchConfidence = match.confidence
            color: str = CONFIDENCE_COLORS.get(conf, "#95a5a6")
            icon: str = MARKETPLACE_ICONS.get(listing.marketplace.value, "")

            with st.container():
                col_img, col_info, col_price, col_action = st.columns(
                    [1, 4, 2, 1]
                )

                with col_img:
                    if listing.image_url:
                        st.image(listing.image_url, width=100)
                    else:
                        st.markdown("🖼️")

                with col_info:
                    st.markdown(f"**{listing.title}**")
                    badge_text: str = _t(conf.value)
                    st.markdown(
                        f'{icon} {listing.marketplace.value.upper()} &nbsp; '
                        f'<span style="background:{color};color:white;padding:2px 8px;'
                        f'border-radius:4px;font-size:0.8em;">{badge_text}</span> '
                        f'&nbsp; Score: {match.relevance_score:.0%}',
                        unsafe_allow_html=True,
                    )
                    if match.reasoning:
                        st.caption(f"💡 {match.reasoning}")

                with col_price:
                    if listing.price:
                        st.markdown(f"### {listing.price:,} UZS")
                    else:
                        st.markdown(f"_{listing.price_str or '\u2014'}_")

                with col_action:
                    st.link_button(_t("open_link"), listing.url)

                st.divider()

elif search_clicked:
    st.warning(_t("search_placeholder"))
