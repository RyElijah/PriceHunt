"""Global CSS and theme tokens for PriceHunt Streamlit UI."""

from __future__ import annotations

import streamlit as st

# Design tokens
COLORS = {
    "bg": "#0c1017",
    "surface": "#151c28",
    "surface_2": "#1e2738",
    "border": "#2a3548",
    "text": "#f1f5f9",
    "muted": "#94a3b8",
    "primary": "#2dd4bf",
    "primary_dim": "#14b8a6",
    "accent": "#fbbf24",
    "danger": "#f87171",
    "success": "#4ade80",
    "carousell": "#ff6633",
    "olx": "#002f34",
}

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}

/* Hide default Streamlit chrome */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {
    background: transparent;
    border: none;
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 3rem;
    max-width: 1100px;
}

/* Hero */
.ph-hero {
    background: linear-gradient(135deg, #151c28 0%, #0f172a 50%, #0c2a28 100%);
    border: 1px solid #2a3548;
    border-radius: 20px;
    padding: 2.25rem 2.5rem;
    margin-bottom: 1.75rem;
    position: relative;
    overflow: hidden;
}
.ph-hero::before {
    content: '';
    position: absolute;
    top: -40%;
    right: -10%;
    width: 320px;
    height: 320px;
    background: radial-gradient(circle, rgba(45,212,191,0.15) 0%, transparent 70%);
    pointer-events: none;
}
.ph-hero h1 {
    font-size: 2.25rem;
    font-weight: 800;
    margin: 0 0 0.5rem 0;
    letter-spacing: -0.03em;
    color: #f8fafc;
}
.ph-hero h1 span {
    background: linear-gradient(90deg, #2dd4bf, #34d399);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.ph-hero p {
    color: #94a3b8;
    font-size: 1.05rem;
    margin: 0;
    max-width: 520px;
    line-height: 1.6;
}
.ph-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 1.25rem;
}
.ph-pill {
    background: rgba(45, 212, 191, 0.1);
    border: 1px solid rgba(45, 212, 191, 0.25);
    color: #5eead4;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

/* Search panel */
.ph-search-panel {
    background: #151c28;
    border: 1px solid #2a3548;
    border-radius: 16px;
    padding: 1.5rem 1.75rem;
    margin-bottom: 1.5rem;
}
.ph-search-panel label {
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    color: #94a3b8 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* Stats row */
.ph-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.75rem;
    margin-bottom: 1.5rem;
}
@media (max-width: 768px) {
    .ph-stats { grid-template-columns: repeat(2, 1fr); }
}
.ph-stat {
    background: #151c28;
    border: 1px solid #2a3548;
    border-radius: 12px;
    padding: 1rem 1.1rem;
}
.ph-stat-label {
    font-size: 0.7rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.35rem;
}
.ph-stat-value {
    font-size: 1.35rem;
    font-weight: 700;
    color: #f1f5f9;
}
.ph-stat-value.ok { color: #4ade80; }
.ph-stat-value.warn { color: #fbbf24; }

/* Listing cards */
.ph-card {
    background: #151c28;
    border: 1px solid #2a3548;
    border-radius: 14px;
    padding: 1.25rem 1.35rem;
    margin-bottom: 0.85rem;
    transition: border-color 0.2s;
}
.ph-card:hover {
    border-color: #3d4f6a;
}
.ph-card.top-pick {
    border-color: rgba(45, 212, 191, 0.5);
    background: linear-gradient(145deg, #152a28 0%, #151c28 60%);
    box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.15), 0 8px 32px rgba(0,0,0,0.25);
}
.ph-card.flagged {
    border-color: rgba(248, 113, 113, 0.4);
    opacity: 0.92;
}
.ph-badge {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 0.2rem 0.55rem;
    border-radius: 6px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-right: 0.35rem;
}
.ph-badge-top { background: #2dd4bf; color: #042f2e; }
.ph-badge-source-c { background: rgba(255,102,51,0.2); color: #ff8a65; }
.ph-badge-source-o { background: rgba(45,212,191,0.15); color: #5eead4; }
.ph-card-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #f8fafc;
    margin: 0.5rem 0 0.35rem 0;
    line-height: 1.4;
}
.ph-price {
    font-size: 1.5rem;
    font-weight: 800;
    color: #2dd4bf;
    letter-spacing: -0.02em;
}
.ph-meta {
    font-size: 0.85rem;
    color: #94a3b8;
    margin: 0.25rem 0;
}
.ph-scores {
    display: flex;
    gap: 1rem;
    margin: 0.85rem 0 0.5rem 0;
    flex-wrap: wrap;
}
.ph-score-block {
    flex: 1;
    min-width: 120px;
}
.ph-score-label {
    font-size: 0.7rem;
    font-weight: 600;
    color: #64748b;
    margin-bottom: 0.3rem;
}
.ph-score-bar-bg {
    height: 6px;
    background: #1e2738;
    border-radius: 99px;
    overflow: hidden;
}
.ph-score-bar {
    height: 100%;
    border-radius: 99px;
}
.ph-score-num {
    font-size: 0.8rem;
    font-weight: 700;
    color: #cbd5e1;
    margin-top: 0.25rem;
}
.ph-flags {
    margin-top: 0.65rem;
}
.ph-flag {
    font-size: 0.78rem;
    color: #fca5a5;
    background: rgba(248,113,113,0.08);
    border-left: 3px solid #f87171;
    padding: 0.35rem 0.6rem;
    margin-bottom: 0.35rem;
    border-radius: 0 6px 6px 0;
}
.ph-section-title {
    font-size: 0.75rem;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 1.5rem 0 0.75rem 0;
}
.ph-negotiation {
    background: #1a2332;
    border: 1px dashed #3d4f6a;
    border-radius: 12px;
    padding: 1.1rem 1.25rem;
    font-size: 0.92rem;
    color: #cbd5e1;
    line-height: 1.65;
    margin-top: 0.5rem;
}
.ph-empty {
    text-align: center;
    padding: 3rem 2rem;
    background: #151c28;
    border: 1px dashed #2a3548;
    border-radius: 16px;
    color: #64748b;
}
.ph-empty-icon {
    font-size: 3rem;
    margin-bottom: 0.75rem;
    opacity: 0.6;
}
.ph-sidebar-brand {
    font-size: 1.35rem;
    font-weight: 800;
    color: #f8fafc;
    margin-bottom: 0.15rem;
}
.ph-sidebar-tag {
    font-size: 0.75rem;
    color: #64748b;
    margin-bottom: 1.25rem;
}
.ph-history-item {
    background: #1e2738;
    border-radius: 10px;
    padding: 0.65rem 0.85rem;
    margin-bottom: 0.5rem;
    border: 1px solid #2a3548;
}
.ph-history-query {
    font-size: 0.85rem;
    font-weight: 600;
    color: #e2e8f0;
}
.ph-history-meta {
    font-size: 0.72rem;
    color: #64748b;
    margin-top: 0.15rem;
}

/* Streamlit widgets */
div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input {
    background-color: #1e2738 !important;
    border-color: #2a3548 !important;
    color: #f1f5f9 !important;
    border-radius: 10px !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: #2dd4bf !important;
    box-shadow: 0 0 0 1px #2dd4bf !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #14b8a6, #2dd4bf) !important;
    color: #042f2e !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.65rem 1.5rem !important;
    box-shadow: 0 4px 14px rgba(45, 212, 191, 0.35) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 20px rgba(45, 212, 191, 0.45) !important;
    transform: translateY(-1px);
}
section[data-testid="stSidebar"] {
    background: #0a0e14 !important;
    border-right: 1px solid #1e2738 !important;
}
.ph-suggest-hint {
    font-size: 0.75rem;
    color: #64748b;
    margin-top: 0.35rem;
}
"""


def inject_theme() -> None:
    st.markdown(f"<style>{CUSTOM_CSS}</style>", unsafe_allow_html=True)


def score_bar_color(score: int) -> str:
    if score >= 70:
        return "#4ade80"
    if score >= 50:
        return "#fbbf24"
    return "#f87171"
