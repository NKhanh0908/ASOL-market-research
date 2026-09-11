# Báo cáo API / Data Source cho nghiên cứu thị trường Casual Game

**Ngày tổng hợp:** 2026-09-10  
**Mục tiêu:** Xây dựng pipeline Python + AI Agent để theo dõi thị trường, doanh thu, độ phổ biến, xu hướng và cơ hội thể loại **Casual / Hybrid Casual / Puzzle / Idle / Simulation / Merge / Sort**.

> Ghi chú quan trọng: không có một API miễn phí duy nhất cung cấp đầy đủ **revenue + downloads + ranking + trend + metadata** cho toàn bộ mobile game. Kiến trúc thực tế nên ghép nhiều nguồn: store data + trend/social + market-intelligence trả phí.

---

## 1. Bảng tổng hợp nhanh

| # | API / Data source | Mức phí | API key | Dữ liệu chính | Hữu ích Casual Game | Endpoint / URL tiêu biểu |
|---|---|---|---|---|---|---|
| 1 | Apple iTunes Search API | Free | Không | App metadata, developer, genre, rating, review count, price, release/update info | ⭐⭐⭐⭐⭐ | `https://itunes.apple.com/search?term=merge&country=us&entity=software` |
| 2 | Apple iTunes Lookup API | Free | Không | Chi tiết app theo App Store ID | ⭐⭐⭐⭐⭐ | `https://itunes.apple.com/lookup?id={APP_ID}&country=us` |
| 3 | Apple Marketing Tools RSS / Charts | Free | Không | Top app/game theo quốc gia, top free/paid | ⭐⭐⭐⭐⭐ | `https://rss.marketingtools.apple.com/api/v2/us/apps/top-free/50/apps.json` |
| 4 | Google Play Developer API - Reviews | Free theo Google Cloud quota | OAuth / service account | Reviews, rating, text, language, device info cho app của bạn | ⭐⭐⭐ | `https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{packageName}/reviews` |
| 5 | Google Trends API Alpha | Free / limited alpha access | Quyền alpha | Search interest theo từ khóa, region, time series | ⭐⭐⭐⭐⭐ | Official alpha: `https://developers.google.com/search/apis/trends` |
| 6 | YouTube Data API v3 | Freemium quota | API key / OAuth | Video search, views, likes, publish time, channel data | ⭐⭐⭐⭐⭐ | `https://www.googleapis.com/youtube/v3/search` / `videos` |
| 7 | Twitch Helix API | Free quota | Twitch Client ID + OAuth | Top games, streams, viewer activity, categories | ⭐⭐⭐⭐ | `https://api.twitch.tv/helix/games/top` / `streams` |
| 8 | Reddit Developer API / Devvit | Free theo policy/quota | Devvit auth / OAuth tùy cách dùng | Posts, comments, search, community discussion | ⭐⭐⭐⭐⭐ | Devvit `searchPosts()` / Reddit platform APIs |
| 9 | IGDB API | Free non-commercial | Twitch Client ID + token | Game metadata, genres, themes, tags, platforms, ratings, hypes, follows | ⭐⭐⭐⭐ | `https://api.igdb.com/v4/games` |
| 10 | RAWG Video Games Database API | Free personal / Paid commercial | API key | 500k+ games, genres, tags, ratings, screenshots, platform data | ⭐⭐⭐⭐ | `https://api.rawg.io/api/games?key={KEY}` |
| 11 | Steam Web API | Free | API key cho nhiều endpoint | Current players, player/game stats, Steam data | ⭐⭐⭐⭐ | `https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={APPID}` |
| 12 | Steam Store API | Free / unofficial-public endpoint | Không | Price, categories, description, release date, supported languages | ⭐⭐⭐⭐ | `https://store.steampowered.com/api/appdetails?appids={APPID}` |
| 13 | SteamSpy API | Free | Không | Estimated owners, CCU, playtime, reviews, genre, tags | ⭐⭐⭐⭐ | `https://steamspy.com/api.php?request=appdetails&appid={APPID}` |
| 14 | itch.io RSS feeds | Free | Không | New games, featured games, sales; niche/indie trend discovery | ⭐⭐⭐ | `https://itch.io/feed/new.xml` / browse page + `.xml` |
| 15 | itch.io Server-side API | Free | API key / JWT | Dữ liệu game của tài khoản: downloads, purchases, views, earnings | ⭐⭐⭐ | `https://api.itch.io/profile/games` |
| 16 | GameAnalytics Metrics API | Paid / product-tier dependent | API key | Revenue, retention, ARPU, ARPPU, conversion, active users | ⭐⭐⭐⭐ | Metrics API theo docs PipelineIQ |
| 17 | Sensor Tower | Paid / Enterprise | Token / account access | Estimated downloads, revenue, rankings, app intelligence, market data | ⭐⭐⭐⭐⭐ | API / Connect product; endpoint tùy package/account |
| 18 | Newzoo Game Performance Monitor | Paid / Enterprise | Account/API access | Revenue, MAU, DAU, player overlap, retention, taxonomy, PC/console market data | ⭐⭐⭐ | API access theo enterprise contract |

---

## 2. Chi tiết từng nguồn

### 1) Apple iTunes Search API

**Loại:** Free — không cần API key  
**Phù hợp:** Mobile iOS market discovery, competitor discovery, keyword-based scanning.

Dữ liệu có thể lấy:

- App name / bundle information
- Developer
- App Store ID
- Primary genre / genres
- Rating và rating count
- Price
- Version
- Release date / current version release date
- Description, icon, store URL

**Endpoint:**

```text
https://itunes.apple.com/search?term=merge&country=us&entity=software&limit=50
```

**Python:** dùng `requests.get()` rất đơn giản.

**Điểm Casual:** ⭐⭐⭐⭐⭐  
Rất tốt để scan các keyword như `merge`, `idle`, `sort`, `puzzle`, `match 3`, `cozy`, `tycoon`.

**Hạn chế:** không cung cấp download/revenue thực tế của competitor.

Official docs: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/

---

### 2) Apple iTunes Lookup API

**Loại:** Free — không cần API key.

Dùng để enrich một App Store ID đã phát hiện từ charts/search.

```text
https://itunes.apple.com/lookup?id=123456789&country=us
```

**Điểm Casual:** ⭐⭐⭐⭐⭐  
Nên ghép với Apple charts để tạo snapshot competitor hàng ngày.

---

### 3) Apple Marketing Tools RSS / App Charts

**Loại:** Free — không cần API key.

Có thể lấy thứ hạng top app theo quốc gia; phù hợp để chụp snapshot mỗi ngày rồi tính biến động ranking.

```text
https://rss.marketingtools.apple.com/api/v2/us/apps/top-free/50/apps.json
```

Ví dụ pipeline:

```text
Top chart hôm nay
      ↓
App IDs
      ↓
iTunes Lookup
      ↓
Database snapshot
      ↓
Rank delta 1d / 7d / 30d
```

**Điểm Casual:** ⭐⭐⭐⭐⭐

**Hạn chế:** chart feed không thay thế market-intelligence; muốn phát hiện Casual cần classify app/game sau khi thu thập.

---

### 4) Google Play Developer API — Reviews

**Loại:** API chính thức; authentication bắt buộc.  
**Phù hợp nhất:** game Android do chính bạn quản lý.

```text
GET https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{packageName}/reviews
```

Dữ liệu:

- Review text
- Star rating
- Language
- Timestamp
- Device metadata
- Developer replies

**Điểm Casual:** ⭐⭐⭐

Rất hữu ích sau khi launch để AI Agent làm:

- sentiment analysis
- complaint clustering
- identify churn reasons
- identify requested features

**Lưu ý:** đây không phải public competitor-review API tổng quát.

Docs: https://developers.google.com/android-publisher/api-ref/rest/v3/reviews/list

---

### 5) Google Trends API Alpha

**Loại:** Free / limited alpha access.  
**Trạng thái:** Google đã công bố API chính thức ở dạng alpha; cần đăng ký quyền truy cập.

Dữ liệu:

- Search interest
- Time series
- Country / sub-region
- Daily / weekly / monthly / yearly aggregation
- Rolling historical window

Ví dụ từ khóa:

```text
merge game
screw puzzle
sort puzzle
cozy game
idle tycoon
match 3
parking jam
block puzzle
```

**Điểm Casual:** ⭐⭐⭐⭐⭐  
Đây là một trong những nguồn tốt nhất để đo **consumer interest trước khi revenue phản ánh trend**.

Docs: https://developers.google.com/search/apis/trends

---

### 6) YouTube Data API v3

**Loại:** Freemium quota — cần Google API key/OAuth.

Search:

```text
GET https://www.googleapis.com/youtube/v3/search
```

Video stats:

```text
GET https://www.googleapis.com/youtube/v3/videos
```

Dữ liệu:

- Search result by keyword
- Publish timestamp
- View count
- Like count
- Channel
- Tags / description

YouTube có topic category riêng cho `Casual game` và `Puzzle video game`, nên có thể dùng thêm topic filtering khi phù hợp.

**Điểm Casual:** ⭐⭐⭐⭐⭐

AI Agent nên tính:

```text
video_count_growth
views_velocity
creator_count_growth
keyword_frequency
engagement_ratio
```

Docs: https://developers.google.com/youtube/v3

---

### 7) Twitch Helix API

**Loại:** Free quota — Twitch Client ID + OAuth token.

Top Games:

```text
GET https://api.twitch.tv/helix/games/top
```

Streams:

```text
GET https://api.twitch.tv/helix/streams?game_id={GAME_ID}
```

Dữ liệu:

- Most watched game categories
- Active streams
- Concurrent viewers
- Stream title / language
- Category/game metadata

**Điểm Casual:** ⭐⭐⭐⭐

Không phải mọi Casual mobile game đều mạnh trên Twitch, nhưng rất tốt để phát hiện game có creator/social momentum.

Docs: https://dev.twitch.tv/docs/api/reference

---

### 8) Reddit Developer API / Devvit

**Loại:** Free theo Reddit policy/quota và môi trường sử dụng.

Dữ liệu:

- Posts
- Comments
- Upvotes / engagement signals
- Search theo subreddit và keyword

Ví dụ logic:

```text
r/AndroidGaming
r/iosgaming
r/Incremental_Games
r/CozyGamers
r/puzzlevideogames
        ↓
keyword extraction
        ↓
mention velocity
        ↓
sentiment / pain points
```

**Điểm Casual:** ⭐⭐⭐⭐⭐

Rất mạnh cho qualitative trend, nhưng nên coi dữ liệu social là **signal**, không phải revenue truth.

Docs: https://developers.reddit.com/docs/capabilities/server/reddit-api

---

### 9) IGDB API

**Loại:** Free cho non-commercial use theo điều khoản hiện tại; Twitch auth bắt buộc.

Base URL:

```text
https://api.igdb.com/v4
```

Games:

```text
POST https://api.igdb.com/v4/games
```

Có thể lấy:

- Genres
- Themes
- Keywords
- Platforms
- Release dates
- Companies
- Ratings
- Rating counts
- Follows
- Hypes
- Similar games
- Screenshots / artworks

**Điểm Casual:** ⭐⭐⭐⭐

IGDB rất phù hợp làm **canonical metadata layer** để normalize game taxonomy.

Docs: https://api-docs.igdb.com/

---

### 10) RAWG API

**Loại:** Free personal/hobby; paid commercial plans.  
**API key:** bắt buộc.

```text
GET https://api.rawg.io/api/games?key={YOUR_KEY}
```

Có thể lấy:

- 500k+ games
- Genres/tags
- Platforms
- Publishers/developers
- Ratings
- Metacritic
- Screenshots
- Release dates
- Store links
- Steam-related playtime/activity data ở một số trường

**Điểm Casual:** ⭐⭐⭐⭐

Dùng tốt cho metadata enrichment và similarity/recommendation.

Docs: https://rawg.io/apidocs

---

### 11) Steam Web API

**Loại:** Free; nhiều endpoint cần Steam Web API key.

Ví dụ useful signal:

```text
https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={APPID}
```

Dữ liệu có thể dùng:

- Current player count
- Game/global stats tùy endpoint
- User/game stats khi được phép

**Điểm Casual:** ⭐⭐⭐⭐

Đặc biệt hữu ích nếu Agent nghiên cứu cả Casual PC, cozy, idle, simulation và puzzle.

Docs: https://partner.steamgames.com/doc/webapi

---

### 12) Steam Store API

**Loại:** Public endpoint, không cần key; không nên xem như SLA-backed official developer API.

```text
https://store.steampowered.com/api/appdetails?appids={APPID}
```

Dữ liệu:

- Name
- Description
- Price / discount
- Categories
- Genres
- Release date
- Developer/publisher
- Languages
- Metacritic (khi có)

**Điểm Casual:** ⭐⭐⭐⭐

Dùng rất tốt cùng SteamSpy.

---

### 13) SteamSpy API

**Loại:** Free — không cần key.

```text
https://steamspy.com/api.php?request=appdetails&appid={APPID}
```

Hoặc:

```text
https://steamspy.com/api.php?request=all&page=0
```

Dữ liệu:

- Estimated owners range
- CCU
- Positive/negative reviews
- Average playtime
- Median playtime
- Genre
- Community tags

**Điểm Casual:** ⭐⭐⭐⭐

**Cảnh báo:** số owners là estimate. SteamSpy cũng cảnh báo dữ liệu game mới ra có thể không đáng tin trong thời gian đầu.

Site/API: https://steamspy.com/api.php  
About/limitations: https://steamspy.com/about

---

### 14) itch.io RSS Feeds

**Loại:** Free — không cần key.

```text
https://itch.io/feed/new.xml
https://itch.io/feed/featured.xml
https://itch.io/feed/sales.xml
```

Ngoài ra nhiều browse URL có thể thêm `.xml`.

Dùng để phát hiện:

- mechanic indie mới
- small-game concepts
- visual theme mới
- niche prototypes

**Điểm Casual:** ⭐⭐⭐

Rất phù hợp cho **idea scouting**, ít phù hợp để suy ra mobile revenue.

Docs: https://itch.io/docs/api/overview

---

### 15) itch.io Server-side API

**Loại:** Free — cần API key/JWT.

```text
GET https://api.itch.io/profile/games
Authorization: Bearer YOUR_API_KEY
```

Với game bạn sở hữu có thể có:

- Downloads count
- Purchases count
- Views count
- Earnings
- Price
- Publish date

**Điểm Casual:** ⭐⭐⭐

Tốt cho internal game analytics / prototype validation trên itch.io.

Docs: https://itch.io/docs/api/serverside

---

### 16) GameAnalytics Metrics API

**Loại:** Paid / phụ thuộc product tier.  
**API key:** có.

Metrics có thể gồm:

- Active users
- Revenue
- Conversion
- Retention
- Retention count
- Paying users
- ARPU / ARPPU
- Ad metrics tùy sản phẩm / schema

**Điểm Casual:** ⭐⭐⭐⭐

Rất quan trọng cho **game của chính studio** sau prototype/soft launch.

Use case:

```text
Market Agent → đề xuất concept
        ↓
Prototype / Soft Launch
        ↓
GameAnalytics
        ↓
Retention / monetization Agent
        ↓
Kill / Iterate / Scale
```

Docs: https://docs.gameanalytics.com/products-and-features/pipeline-iq/metrics-api/api-specification/

---

### 17) Sensor Tower

**Loại:** Paid / Enterprise.

Dữ liệu market-intelligence thường dùng:

- Estimated downloads
- Estimated IAP revenue
- Rankings
- App/category intelligence
- Publisher / competitor analysis
- Country-level performance
- Market trends

**Điểm Casual:** ⭐⭐⭐⭐⭐

Nếu mục tiêu cuối cùng là trả lời:

```text
Game nào đang tăng download?
Subgenre nào đang tăng revenue?
Competitor nào đang scale tại US/JP/KR?
```

thì đây là loại nguồn rất có giá trị.

**Endpoint:** quyền API/data feed phụ thuộc package/account; không nên hard-code một public endpoint trước khi có contract.

Product/API integration: https://sensortower.com/product/connect

---

### 18) Newzoo Game Performance Monitor

**Loại:** Paid / Enterprise.

Dữ liệu được công bố cho platform gồm:

- Revenue
- MAU / DAU
- Lifetime players
- Player overlap
- Acquisition / retention / churn
- Game taxonomy
- PC / PlayStation / Xbox / Switch market intelligence

**Điểm Casual:** ⭐⭐⭐ cho mobile-only; ⭐⭐⭐⭐ nếu nghiên cứu casual PC/console.

API access được cung cấp cho enterprise use case để tích hợp vào internal BI.

Product: https://www.newzoo.com/game-performance-monitor

---

## 3. Nguồn nên ưu tiên theo mục tiêu

### A. Muốn bắt đầu gần như miễn phí

1. **Apple RSS Charts** — ranking signal
2. **Apple iTunes Search / Lookup** — metadata enrichment
3. **Google Trends** — keyword demand
4. **YouTube Data API** — creator/view velocity
5. **Reddit** — community discussion velocity
6. **IGDB / RAWG** — normalize genres/tags/game metadata
7. **Steam + SteamSpy** — PC casual / cozy / puzzle / idle trend

---

### B. Muốn nghiên cứu revenue/download competitor mobile

Ưu tiên bổ sung:

1. **Sensor Tower**
2. Các market-intelligence commercial providers tương đương nếu studio đã có subscription

Không nên cố suy ra revenue chính xác chỉ từ review count hoặc ranking. Có thể dùng chúng làm **proxy feature**, nhưng phải ghi rõ là model estimate.

---

### C. Muốn đánh giá game của chính studio sau soft launch

Ưu tiên:

1. **GameAnalytics**
2. Google Play Developer API
3. App Store Connect API / internal exports (nếu bổ sung vào pipeline sau)
4. Revenue/ad network data của studio

---

## 4. Kiến trúc Python đề xuất

```text
                    CASUAL GAME SCOUT
                           |
          +----------------+----------------+
          |                |                |
       MARKET           TREND            SOCIAL
          |                |                |
  Apple Charts       Google Trends       Reddit
  iTunes API         YouTube              Twitch
  Sensor Tower*      Steam/SteamSpy
          |                |                |
          +----------------+----------------+
                           |
                     NORMALIZATION
                           |
                    IGDB / RAWG tags
                           |
                      PostgreSQL
                           |
                    Feature Engine
                           |
        +------------------+------------------+
        |                  |                  |
   Trend Score       Opportunity Score    Risk Score
        |                  |                  |
        +------------------+------------------+
                           |
                          LLM
                           |
               Daily Casual Game Report
```

`*` = optional paid provider.

---

## 5. Data model tối thiểu nên lưu

```text
games
- source
- source_game_id
- name
- developer
- publisher
- platforms
- genres
- tags
- release_date

market_snapshots
- game_id
- country
- date
- store_rank
- rating
- rating_count
- price
- estimated_downloads
- estimated_revenue

trend_snapshots
- keyword
- source
- country
- date
- value
- growth_1d
- growth_7d
- growth_30d

social_snapshots
- game_id / keyword
- source
- date
- mentions
- views
- likes
- comments
- engagement_rate

scores
- game_id / concept
- date
- trend_score
- competition_score
- monetization_score
- opportunity_score
```

---

## 6. Scoring framework gợi ý cho Casual Game

Ví dụ:

```text
Opportunity Score =
    25% Search Trend Growth
  + 20% Store Rank Momentum
  + 15% Review Velocity
  + 15% YouTube View Velocity
  + 10% Reddit Mention Growth
  + 10% Genre Momentum
  +  5% Market Revenue Signal
```

Khi có Sensor Tower hoặc nguồn revenue tốt hơn:

```text
Opportunity Score =
    20% Download Growth
  + 20% Revenue Growth
  + 15% Search Trend Growth
  + 15% Store Rank Momentum
  + 10% Review Velocity
  + 10% Social Velocity
  + 10% Competition Gap
```

Không nên hard-code trọng số vĩnh viễn. Sau vài tháng dữ liệu, có thể backtest xem feature nào dự báo ranking/download/revenue tốt nhất rồi tối ưu trọng số.

---

## 7. Bộ 8 nguồn mình khuyên dùng cho MVP

| Priority | Source | Vai trò |
|---|---|---|
| P0 | Apple RSS Charts | Daily ranking snapshot |
| P0 | iTunes Search/Lookup | iOS metadata |
| P0 | Google Trends | Search demand |
| P0 | YouTube Data API | Content/view trend |
| P0 | Reddit | Community signal |
| P1 | IGDB | Canonical game metadata |
| P1 | SteamSpy + Steam Store | PC trend / tags / owners proxy |
| P2 | Sensor Tower | Revenue/download premium layer |

Với bộ này, bạn có thể xây Agent trước mà **không phụ thuộc API trả phí**. Sau đó chỉ cần thêm Sensor Tower như một provider mới.

---

## 8. Interface Python nên chuẩn hóa

```python
from typing import Protocol

class MarketDataProvider(Protocol):
    def search_games(self, query: str, country: str = "US") -> list[dict]:
        ...

    def get_game(self, game_id: str, country: str = "US") -> dict:
        ...

    def get_rankings(self, country: str = "US") -> list[dict]:
        ...

    def get_trend(self, keyword: str, country: str = "US") -> list[dict]:
        ...
```

Folder structure:

```text
casual_game_scout/
├── providers/
│   ├── apple_itunes.py
│   ├── apple_charts.py
│   ├── google_trends.py
│   ├── youtube.py
│   ├── reddit.py
│   ├── twitch.py
│   ├── igdb.py
│   ├── rawg.py
│   ├── steam.py
│   ├── steamspy.py
│   └── sensortower.py
├── scoring/
│   ├── trend_score.py
│   ├── competition_score.py
│   └── opportunity_score.py
├── agents/
│   ├── trend_agent.py
│   ├── market_agent.py
│   ├── competitor_agent.py
│   └── idea_agent.py
├── db/
├── reports/
└── main.py
```

---

## 9. Kết luận

Nếu mục tiêu là **AI Agent tìm trend và gợi ý Casual Game**, không nên bắt đầu bằng việc cố mua toàn bộ market data. Nên xây MVP với các signal miễn phí trước:

```text
Apple ranking
+ Google Trends
+ YouTube
+ Reddit
+ Steam/SteamSpy
+ IGDB/RAWG
        ↓
Trend / Opportunity Engine
        ↓
LLM phân tích
        ↓
Game concept recommendations
```

Sau khi pipeline ổn định, thêm **Sensor Tower** để bổ sung estimated downloads/revenue. Như vậy kiến trúc không bị khóa vào một vendor và vẫn chạy được khi không có premium API token.

---

## Nguồn tham khảo chính

- Apple iTunes Search API: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/
- Apple Marketing Tools RSS: https://rss.marketingtools.apple.com/
- Google Play Developer API Reviews: https://developers.google.com/android-publisher/api-ref/rest/v3/reviews/list
- Google Trends API Alpha: https://developers.google.com/search/apis/trends
- YouTube Data API: https://developers.google.com/youtube/v3
- Twitch API: https://dev.twitch.tv/docs/api/reference
- Reddit Developer API: https://developers.reddit.com/docs/capabilities/server/reddit-api
- IGDB: https://api-docs.igdb.com/
- RAWG: https://rawg.io/apidocs
- Steam Web API: https://partner.steamgames.com/doc/webapi
- SteamSpy: https://steamspy.com/api.php
- itch.io API: https://itch.io/docs/api/overview
- GameAnalytics Metrics API: https://docs.gameanalytics.com/products-and-features/pipeline-iq/metrics-api/api-specification/
- Sensor Tower Connect: https://sensortower.com/product/connect
- Newzoo Game Performance Monitor: https://www.newzoo.com/game-performance-monitor

