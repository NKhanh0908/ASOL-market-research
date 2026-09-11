# Specification: Phase 3.5 — Monetization & Grossing Intelligence

## 1. Executive Summary & Goals
Phase 3.5 expands **Casual Scout** into revenue, monetization patterns, and grossing performance across the 12 target markets (11 ASEAN + US). 

While Phase 1-3 focused on popularity and downloads (Top Free charts), Phase 3.5 provides deep intelligence into:
1. **Top Grossing Rankings**: Collecting and tracking Top 100 Grossing Casual games.
2. **In-App Purchase (IAP) Metadata**: Extracting IAP tier structures, prices, currencies, and presence.
3. **Monetization Model Classification**: Automatically categorizing games into `PURE_IAP`, `HYBRID`, `PURE_ADS`, or `PAID_PREMIUM`.
4. **Download vs. Revenue Correlation Matrix**: Detecting high-efficiency monetization outliers (`HIGH_GROSSING_EFFICIENCY`, `MEGA_HIT`, `VIRAL_FREE`).
5. **Opportunity Radar v1.5 with Grossing Power**: Factoring revenue generation capability into opportunity scoring (Max 100 points).

---

## 2. Data Architecture & Schema Evolution

### 2.1 Multi-Chart Support (`charts` & `market_runs`)
The existing `charts` table already supports generic charts (`provider`, `platform`, `country`, `category`, `feed_type`).
* `feed_type`:
  * `'top-free'` (existing): Top 100 Free Apps/Games
  * `'top-grossing'` (new): Top 100 Grossing Apps/Games from Apple RSS / iTunes feeds.

### 2.2 Metadata Versions Extension
Add columns to `metadata_versions` (with safe migrations):
* `in_app_purchases_json` (TEXT): JSON array of `{ name, price, price_formatted, currency }`.
* `has_in_app_purchases` (INTEGER 0/1): Flag indicating IAP presence.
* `monetization_model` (TEXT): Classified model (`PURE_IAP`, `HYBRID`, `PURE_ADS`, `PAID_PREMIUM`).

### 2.3 Daily Rank Analytics Extension (`daily_rank_analytics`)
Add columns to `daily_rank_analytics`:
* `grossing_rank` (INTEGER NULL): Rank in Top Grossing on that date in that country (1..100 or NULL).
* `free_rank` (INTEGER NULL): Rank in Top Free on that date in that country (1..100 or NULL).
* `monetization_model` (TEXT NOT NULL DEFAULT 'PURE_ADS'): Monetization model classification.
* `monetization_efficiency_flag` (TEXT NULL): e.g. `'HIGH_GROSSING_EFFICIENCY'`, `'MEGA_HIT'`, `'VIRAL_FREE'`.

---

## 3. Core Algorithms & Classification Engine

### 3.1 Monetization Model Classification Rules
For each app in a market on a given date:
1. **`PAID_PREMIUM`**: `price > 0`.
2. **`HYBRID`**: App appears in **both** Top Free and Top Grossing charts OR has active IAPs detected while maintaining high free download velocity.
3. **`PURE_IAP`**: App has high rank in Top Grossing (Rank $\le 100$) and rich IAP tiers, with minimal ad presence.
4. **`PURE_ADS` (IAA)**: App is in Top Free (Rank $\le 100$) but does **not** appear in Top Grossing (outside Top 100) and has no prominent IAPs.

### 3.2 Correlation Signals (`monetization_efficiency_flag`)
* 💎 **`HIGH_GROSSING_EFFICIENCY`**: `free_rank` > 30 (or NULL) but `grossing_rank` $\le 30$ (Whale monetization / High ARPU).
* 🔥 **`MEGA_HIT`**: `free_rank` $\le 15$ AND `grossing_rank` $\le 15$ (Both viral scale and massive monetization).
* 🚀 **`VIRAL_FREE`**: `free_rank` $\le 10$ AND `grossing_rank` is NULL (Hypercasual ad cash-cow).

### 3.3 Opportunity Radar v1.5 Scoring Formula
The Opportunity Score incorporates **Grossing Power** with explainable weights:
$$\text{Opportunity Score (0-100)} = \text{Momentum (max 35)} + \text{Market Breadth (max 30)} + \text{Rank Tier (max 20)} + \text{Grossing Power (max 15)}$$

* **Grossing Power Breakdown (Max 15 pts)**:
  * Grossing Rank 1 - 10: **+15 points**
  * Grossing Rank 11 - 30: **+10 points**
  * Grossing Rank 31 - 70: **+6 points**
  * Grossing Rank 71 - 100: **+3 points**
  * Not in Top Grossing: **0 points**

* **Efficiency Multiplier / Bonus**:
  * If `HIGH_GROSSING_EFFICIENCY`: +5 bonus points (Capped at 100 total).

---

## 4. Web UI & REST API Enhancements

### 4.1 Market Data View (`/data`)
* **Tab Switcher**: Toggle easily between `🆓 Top Free (100)` and `💰 Top Grossing (100)`.
* **Cross-Chart Reference**: When viewing Top Free, shows corresponding Grossing Rank badge (e.g. `Grossing #14`), and vice-versa.
* **Monetization Badge**: Displays `HYBRID`, `PURE_IAP`, `PURE_ADS` chips on table rows.

### 4.2 Dashboard View (`/dashboard`)
* **Opportunity Radar Table**: Includes Monetization Model, Grossing Rank, and Grossing Power breakdown.
* **Monetization Distribution Chart**: Donut chart of revenue models across ASEAN + US.
* **Top Grossing Leaders KPI**: Highest earning casual games of the week.

### 4.3 Game Detail View (`/games/{country}/{app_id}`)
* **Monetization & IAP Breakdown Card**:
  * List of In-App Purchases with price tiers.
  * Dual-history chart: 14-day history comparing `Free Rank` vs `Grossing Rank`.

### 4.4 REST APIs
* `/api/stats/monetization`: Overview of monetization models by market.
* `/api/charts/grossing?country=vn&date=YYYY-MM-DD`: Get Top Grossing snapshot.

---

## 5. CLI Commands Evolution
* `casual_scout collect [--chart-type all|free|grossing]`: Selectively collect Free, Grossing, or both.
* `casual_scout stats radar [--monetization all|hybrid|iap|ads]`: Filter radar items by monetization category.
* `casual_scout trends [--chart-type free|grossing]`: Query trends on free or grossing charts.

---

## 6. Verification & Acceptance Criteria
1. **Collection Immutability**: Top Grossing snapshots stored immutably with SHA-256 raw payloads.
2. **Deterministic Classification**: 100% reproducible monetization labeling for all test cases.
3. **Zero-Touch Migration**: Existing SQLite databases seamlessly upgrade schema without data loss.
4. **Automated Test Coverage**: 100% unit and integration tests passing on Python 3.12.
