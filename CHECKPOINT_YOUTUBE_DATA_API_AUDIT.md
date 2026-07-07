# CHECKPOINT: YouTube Data API v3  -  Official Access Audit

Date: 2026-07-07
Status: official_audit / proceed_to_setup  -  implementation not approved yet

---

## Official API identity

| Field | Value |
|---|---|
| Official API name | YouTube Data API v3 |
| Service base URL | `https://www.googleapis.com/youtube/v3` |
| Operated by | Google |
| Primary documentation | `https://developers.google.com/youtube/v3` |
| Getting started | `https://developers.google.com/youtube/v3/getting-started` |
| `search.list` reference | `https://developers.google.com/youtube/v3/docs/search/list` |
| `videos.list` reference | `https://developers.google.com/youtube/v3/docs/videos/list` |
| Quota documentation | `https://developers.google.com/youtube/v3/determine_quota_cost` |
| Official and Google-supported | **yes** |

---

## Access requirements

| Requirement | Required | Notes |
|---|---|---|
| Google Cloud project | **yes** | Create at console.cloud.google.com; existing `zaryotech-product-discovery` project can be reused |
| YouTube Data API v3 enabled | **yes** | Enable in Google Cloud project -> APIs & Services -> Enable APIs -> search "YouTube Data API v3" |
| API key | **yes**  -  for public search | Sufficient for all public read-only endpoints (`search.list`, `videos.list` with public video data). No OAuth needed for product keyword research. |
| OAuth 2.0 | no (for our use case) | Required only for user-owned data (own channel analytics, private videos, subscriptions). Not needed for product discovery. |
| Billing account | not identified as required in official docs | Billing not identified as required in official YouTube Data API docs for default quota; confirm in Google Cloud Console during setup. |
| Business / company verification | no | No identity confirmation required (unlike Meta). |
| Third-party approval or invitation | no | No approval queue. Enable API -> generate key -> make calls. |

---

## Quota model

| Bucket | Default daily limit | Resets |
|---|---|---|
| `search.list` (dedicated bucket) | **100 calls/day** | Midnight Pacific Time |
| `videos.insert` (dedicated bucket) | 100 calls/day | Midnight Pacific Time |
| All other endpoints combined (videos.list, channels.list, etc.) | **10,000 units/day** | Midnight Pacific Time |

**Quota cost per call:**

| Endpoint | Cost |
|---|---|
| `search.list` | 1 unit (from the 100-call/day search bucket) |
| `videos.list` | 1 unit (from the 10,000-unit general bucket) |
| `channels.list` | 1 unit (from the 10,000-unit general bucket) |

**Quota extension:** Possible via the YouTube API Services Audit and Quota Extension Form. Audit required when requesting additional `search.list` quota. If a prior audit was completed within 12 months, re-submission is sufficient.

---

## Endpoint audit: `search.list`

**Endpoint:** `GET https://www.googleapis.com/youtube/v3/search`

**What it searches:** Videos, channels, and playlists (filterable via `type` parameter).

**Required parameters:**

| Parameter | Value | Notes |
|---|---|---|
| `part` | `snippet` | Mandatory  -  specifies which resource properties to return |
| `key` | `{API_KEY}` | API key for public searches |

**Useful parameters for product keyword research:**

| Parameter | Type | Use |
|---|---|---|
| `q` | string | Search query  -  product name, category, or phrase. Supports `-term` (exclude) and `term1\|term2` (OR). |
| `type` | string | `video`  -  filters results to videos only (recommended for product signals) |
| `order` | string | `relevance` (default), `date`, `viewCount`  -  use `date` for velocity; `viewCount` for top-performing content |
| `publishedAfter` | RFC 3339 datetime | Filter to videos published after a date  -  useful for 30-day or 90-day content velocity |
| `publishedBefore` | RFC 3339 datetime | Upper bound on publish date |
| `relevanceLanguage` | ISO 639-1 | `en`  -  target English content |
| `regionCode` | ISO 3166-1 | `US`  -  limit to US-viewable content |
| `videoDuration` | string | `short` (<4 min), `medium` (4 - 20 min), `long` (>20 min)  -  use `medium` or `long` to filter out Shorts-only content |
| `maxResults` | integer | 1 - 50 (default 5)  -  use 50 for max results per call |

**Response fields (from `snippet`):**

| Field | Description |
|---|---|
| `id.videoId` | Video ID  -  pass to `videos.list` for engagement metrics |
| `snippet.title` | Video title |
| `snippet.description` | Video description (first ~200 chars) |
| `snippet.channelTitle` | Channel name |
| `snippet.publishedAt` | ISO 8601 publish timestamp |
| `snippet.thumbnails` | Thumbnail URLs (default, medium, high) |
| `pageInfo.totalResults` | Approximate total result count for the query |
| `pageInfo.resultsPerPage` | Results per page |
| `nextPageToken` | Token for next page (each page = 1 additional quota unit) |

**Quota cost note:** Each additional results page costs 1 more unit from the 100-call/day search bucket.

---

## Endpoint audit: `videos.list`

**Endpoint:** `GET https://www.googleapis.com/youtube/v3/videos`

**What it returns:** Detailed video resource data for specified video IDs.

**Required parameters:**

| Parameter | Value | Notes |
|---|---|---|
| `part` | comma-separated parts | Specify which data blocks to retrieve |
| `id` | comma-separated video IDs | Video IDs from `search.list` results |
| `key` | `{API_KEY}` | API key |

**Part values for product discovery signals:**

| Part | Fields returned | Quota note |
|---|---|---|
| `statistics` | `viewCount`, `likeCount`, `commentCount`, `favoriteCount` | included in 1-unit call cost |
| `snippet` | `publishedAt`, `title`, `description`, `channelId`, `channelTitle`, `tags[]`, `categoryId` | included in 1-unit call cost |
| `contentDetails` | `duration` (ISO 8601), `dimension`, `definition`, `caption` | included in 1-unit call cost |

**Batch behavior:** Multiple video IDs can be passed as a comma-separated list to the `id` parameter in a single 1-unit call. The `maxResults` and `pageToken` parameters are not supported when using the `id` parameter.

**Quota cost:** 1 unit per call regardless of how many video IDs are in the `id` parameter (within a single request).

---

## Endpoint audit: `channels.list`

**Endpoint:** `GET https://www.googleapis.com/youtube/v3/channels`

**Relevance:** Lower priority for product discovery. Useful only if we want to assess whether a specific brand's channel exists and how large it is (subscriber count, total view count). Not needed for keyword-based product research.

**Quota cost:** 1 unit per call.

---

## Product discovery signals  -  YouTube

### Signal types available

| Signal | How to extract | What it means |
|---|---|---|
| **Review volume** | `search.list(q="product unboxing review", type=video)` -> `pageInfo.totalResults` | Total video count for a product is a proxy for how much content-creation interest exists |
| **Content velocity** | `search.list(..., publishedAfter=90_days_ago, order=date)` -> result count | How many new videos about this product appeared in the last 90 days  -  rising = emerging trend |
| **Top-performing content** | `search.list(..., order=viewCount)` -> top 5 - 10 video IDs -> `videos.list(part=statistics)` | View counts, like counts, comment counts on the most-viewed product content |
| **Unboxing content** | `search.list(q="product unboxing", type=video, videoDuration=short OR medium)` | Unboxing content signals purchase-stage curiosity |
| **Comparison content** | `search.list(q="product vs alternative")` | Comparison content indicates a buying-decision stage, high purchase intent |
| **How-to content** | `search.list(q="how to use product")` | How-to content indicates already-sold audience; lower discovery value but useful for market size |
| **Creator competition** | Number of distinct `channelTitle` values in top results | High creator diversity = broader market interest; single channel dominating = niche or low interest |
| **Audience engagement proxy** | `viewCount / publishedAt` age in days = views per day | Engagement rate proxy without needing YouTube Analytics |

### Two-step lookup pattern (efficient within quota)

```
Step 1  -  search.list (1 quota unit)
  GET /search?part=snippet&q={product+unboxing}&type=video&order=viewCount
             &publishedAfter={90_days_ago}&regionCode=US&maxResults=10&key={KEY}
  -> collect videoId list, totalResults count, snippet titles

Step 2  -  videos.list (1 quota unit for all IDs in batch)
  GET /videos?part=statistics,contentDetails&id={id1,id2,...,id10}&key={KEY}
  -> collect viewCount, likeCount, commentCount, duration per video
```

Total cost for one product: **2 quota units** (1 search + 1 batch stats call).
At 100 search.list calls/day: maximum **100 product keyword searches/day** before search quota exhausts.
At 10,000 general units/day: maximum **10,000 videos.list batch calls/day** (far exceeds what 100 searches can generate).

Practical throughput: **~50 products/day** at 2 searches per product (e.g., `unboxing` + `review`), well within default quota.

---

## Limitations

| Limitation | Detail |
|---|---|
| `totalResults` is approximate | Google's search result count is an estimate, not exact. Cannot be used as a precise view-count metric. Useful only as an order-of-magnitude signal. |
| 100 search.list calls/day default | Tight for large-scale discovery. Sufficient for 30 - 50 products per day with 2 keyword searches each. Extendable via quota audit. |
| View count != purchase intent | A video with 1M views on an unboxing product does not mean 1M people bought it. Correlation, not causation. |
| No direct sales data | YouTube does not expose purchase data of any kind. |
| No keyword search volume | `totalResults` is not equivalent to Google Trends or Google Ads keyword volume. It counts videos, not searches. |
| Content noise | Spam, reposts, reaction compilations, and clickbait inflate result counts. Quality filtering requires reading titles. |
| YouTube Shorts contamination | Shorts (under 60 seconds) appear in results and may inflate counts without representing genuine product content. Mitigated with `videoDuration=medium` or `long`. |
| No engagement rate normalization | Cannot directly compare a 1-year-old video's view count with a 1-week-old video without manual normalization. |
| Liking/comment data accuracy | Like counts are public. Comment counts are public. Dislike counts are not returned (hidden by YouTube since 2021). |
| API terms require compliance | Data must be used in accordance with YouTube API Services Terms of Service. Storing large volumes of video data or displaying it outside YouTube context may require compliance review. |

---

## Proposed status model

```
connector name:              youtube_data_api
status:                      official_audit (current) -> proceed_to_setup (proposed)
official_api:                true
implementation_approved:     false
can_fetch_real_data:         false  (until API key set + live verify call confirmed)
db_persistence:              none   (signal-only source  -  no videos ever saved to products.db)
stub_videos:                 none   (never save fake/stub video objects)
scraping_allowed:            false
unofficial_clients_allowed:  false
oauth_required:              false  (API key sufficient for public product keyword research)
billing_required:            not confirmed  -  billing not identified as required in official docs for default quota; verify in Google Cloud Console during setup
```

**Status progression:**
```
official_audit      current  -  research complete, setup not started
pending_setup       API key not yet generated; GCP project not confirmed for YouTube API
missing_credentials API enabled but YOUTUBE_API_KEY absent from .env
ready               API key set + POST /sources/youtube/verify confirms live results
active              verify ran and returned real content data (auto-promoted)
```

---

## Suitability decision

**proceed_to_setup**

Reasons:
- Official Google API, fully documented, no approval queue
- API key only  -  no OAuth, no identity confirmation, no third-party approval
- Existing GCP project (`zaryotech-product-discovery`) can reuse; just enable YouTube Data API v3
- Billing not identified as required in official YouTube Data API docs for default quota; confirm in Google Cloud Console during setup.
- 100 search.list calls/day supports 30 - 50 products/day coverage  -  adequate for initial discovery
- Two-step lookup (search -> stats) gives: total result count, top video view counts, content velocity, video count by category (unboxing / review / comparison)
- Limitations are real but manageable: approximate counts, no purchase intent, Shorts noise
- No connector is currently in active implementation phase  -  setup can begin after explicit owner approval

**Condition:** This decision is `proceed_to_setup` only  -  not `proceed_to_implementation`. The next step is:
1. Owner reviews this audit and approves setup
2. Enable YouTube Data API v3 in `zaryotech-product-discovery` GCP project
3. Generate API key (restricted to YouTube Data API v3)
4. Set `YOUTUBE_API_KEY=` in `backend/.env` (gitignored, never committed)
5. Implement connector + verify endpoint
6. Confirm live call returns real results -> `active`

No implementation starts until owner explicitly approves moving past setup.

---

## Access rules for this connector

| Source | Status |
|---|---|
| YouTube Data API v3 (official) | Allowed  -  after owner approves setup |
| `search.list`, `videos.list`, `channels.list` | Allowed endpoints |
| YouTube Analytics API | Not needed for this use case (own-channel data only) |
| Scraping youtube.com | NOT ALLOWED |
| Browser automation | NOT ALLOWED |
| yt-dlp, pytube, or any unofficial YouTube client | NOT ALLOWED |
| Third-party YouTube data APIs | NOT approved in this phase |

---

## Files changed

| File | Change |
|---|---|
| `CHECKPOINT_YOUTUBE_DATA_API_AUDIT.md` | This file  -  created |

No connector logic changed. No `.env` modified. No API called. No commit yet.

---

## Freeze rules (unchanged)

| Connector | Rule |
|---|---|
| eBay | FROZEN  -  live, complete |
| CJ Dropshipping | CLOSED  -  frozen except Phase 2/3 enrichment |
| TikTok Ads | FROZEN  -  waiting for TikTok Developer Support |
| Google Trends | FROZEN  -  waiting for alpha invitation at admin@zaryotech.com |
| Meta Ad Library | POSTPONED  -  not approved for implementation |
| **YouTube Data API** | **official_audit complete  -  proceed_to_setup pending owner approval** |
