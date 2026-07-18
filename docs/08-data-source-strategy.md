# Data Source Strategy and Feasibility

## Decision

The original CoinGecko-and-yfinance plan is sufficient for a price-based prototype, but it is too thin for forward-looking crisis research. FRA needs independent evidence planes for market reaction, macro conditions, physical supply, events, company exposure, trade dependencies, positioning, and historical outcomes.

The goal is not to accumulate the largest number of connectors. The goal is to turn permitted, point-in-time source data into comparable evidence with explicit provenance and then preserve the forecast and its outcome.

> Data sources are the fuel. The research workflow is the engine. The scored forecast history and exposure graph are the compounding moat. Local Markdown is the trust and privacy advantage.

This feasibility review was performed on **2026-07-18**. Provider plans, limits, schemas, and terms can change. Each adapter manifest must record a `terms_reviewed_at` date and FRA must fail closed when a source's allowed use is unknown.

## Evidence Planes

| Evidence plane | Questions it answers | Typical data |
| --- | --- | --- |
| Market reaction | What is priced now? | prices, volume, volatility, futures proxies, FX, rates |
| Crypto network | Is activity or liquidity changing beneath price? | active addresses, fees, supply, exchange and network metrics |
| Macro and policy | Which countries are financially vulnerable? | inflation, debt, reserves, rates, growth, revisions |
| Physical supply | Can production, inventory, refining, or shipping absorb a shock? | output, stocks, demand, imports, exports, port and passage activity |
| News and events | What happened, who reported it, and when was it knowable? | articles, official releases, event records, threat and action indicators |
| Company exposure | Which businesses gain or lose through revenue, costs, geography, or financing? | filings, XBRL facts, facilities, hedges, segments, debt |
| Trade dependency | Which countries and commodities depend on each other? | bilateral product flows, production and consumption |
| Market positioning | Is a thesis already crowded? | futures open interest and participant positioning |
| Historical outcomes | How often did comparable scenarios occur and what followed? | conflict events, prior shocks, forecast resolutions, asset responses |

## Evaluation Rubric

Every candidate is evaluated on:

1. **authority:** primary source, official statistic, aggregator, or unofficial convenience layer;
2. **coverage:** subjects, geographies, metrics, and identifiers;
3. **time semantics:** observation, event, publication, first-available, revision, and retrieval times;
4. **history:** earliest usable date, survivorship coverage, and access to vintages;
5. **timeliness:** update frequency and normal publication lag;
6. **access:** protocol, key or account requirement, quota, and pagination;
7. **usage rights:** research, commercial use, attribution, retention, transformation, and redistribution;
8. **operability:** schema stability, bulk access, health checks, retry behavior, and service guarantees;
9. **normalization cost:** identifiers, units, currencies, classifications, and revision handling;
10. **forecast value:** whether the source can lead price rather than merely describe it.

## Status Definitions

| Status | Meaning |
| --- | --- |
| **MVP** | Suitable for an initial supported adapter under documented conditions |
| **Conditional** | Useful only for a limited use, geography, license, or local evaluation profile |
| **Experimental** | Valuable for discovery or enrichment, but operational or data-quality behavior needs a spike |
| **Future** | Feasible, but not required for the first vertical slice |
| **Excluded by default** | FRA must not enable it without explicit rights or a changed product scope |

## Feasibility Matrix

| Source | Evidence plane | Access and useful coverage | Main limitation | FRA decision |
| --- | --- | --- | --- | --- |
| CoinGecko Demo | Market reaction | Free account and key; crypto prices, market cap, volume, metadata, history | 10,000 monthly credits, attribution, plan-limited history; commercial licensing is advertised for paid plans | **Conditional MVP:** local evaluation and attributed reports |
| yfinance | Market reaction | No FRA-managed key; broad tickers, daily history, actions, options and best-effort fundamentals | Unofficial; Yahoo data is intended for personal use; reliability and symbol coverage vary | **Conditional MVP:** fallback and research convenience only |
| Coin Metrics Community | Crypto network | Keyless community endpoint; selected network and market metrics | Non-commercial community terms and a subset of paid coverage | **Future:** preferred crypto-network enrichment |
| FRED and ALFRED | Macro and policy | Free API key; economic series, releases, revisions and vintage dates | Coverage is strongest for US and internationally aggregated series | **MVP:** macro and honest point-in-time replay |
| EIA API v2 | Physical supply | Free API key; bulk files require no key; petroleum, gas, power, prices, stocks and production | High-frequency coverage is strongest for the US; international series vary | **MVP:** oil and energy crisis vertical slice |
| World Bank Indicators API | Macro and policy | No key; nearly 16,000 series across development and debt databases | Many country series are annual and revised; not a live crisis feed | **MVP:** structural country vulnerability |
| World Bank Pink Sheet | Market reaction | Direct monthly XLSX download; commodity prices and indexes | File rather than stable row API; monthly frequency cannot replace daily market prices | **MVP:** commodity benchmarks and cross-checks |
| SEC EDGAR | Company exposure | No key; submissions, filings, XBRL company facts, bulk nightly files | US-centric; taxonomy and company extensions require normalization | **MVP:** authoritative US filings and fundamentals |
| Configured RSS/Atom and manual URL ingestion | News and events | Public feeds or user-supplied URLs; works for official sources | Coverage depends on configured feeds; every publisher has separate terms | **MVP:** authoritative document ingestion |
| GDELT 2.0 | News and events | Event, mentions and knowledge-graph files every 15 minutes; multilingual discovery | Media bias, duplicates, extraction errors, unstable throttling, and raw-download transport issues | **Experimental:** discovery only, never sole support |
| Geopolitical Risk index | News and events | Monthly country indexes and a recent daily index as downloadable files | Aggregate news-derived signal; not an event detector or company exposure source | **Future:** historical baseline and risk-regime feature |
| JODI Oil and Gas | Physical supply | Free monthly CSV downloads; global production, trade, demand and stocks | Roughly one-month publication lag and uneven country completeness | **Future:** global physical-balance enrichment |
| UN Comtrade | Trade dependency | No-key preview; free registered API key for broader access; monthly and annual product flows | Preview is capped; releases lag and can be revised; HS-version mapping is required | **Future:** country-product dependency graph |
| FAOSTAT Fertilizers by Product | Trade dependency | Downloadable official country data for production, trade and use | Annual and incomplete by product; unsuitable for immediate crisis detection | **Future:** structural fertilizer dependency |
| IMF PortWatch | Physical supply | Open platform and discoverable API catalog; daily port and critical-passage indicators from 2019 | Experimental estimates, revisions, and API/product stability need validation | **Experimental:** shipping disruption and chokepoint signals |
| CFTC Commitments of Traders | Market positioning | Public API and annual files; historical futures positioning | Tuesday observations are normally published Friday; not real-time and not trader intent | **Future:** crowding and positioning evidence |
| Korea OpenDART | Company exposure | Free account/key; disclosures, original documents, XBRL and financial statements | Key management, Korean identifiers, translations and report taxonomy | **Future:** preferred South Korea filing source |
| KRX Open API | Market reaction | Account, authentication key and per-service approval; daily statistics from 2010 | Approval and redistribution terms; real-time data requires separate arrangements | **Future:** authoritative South Korea market history |
| Vietnam official exchanges and disclosures | Market and company exposure | Public web disclosures and reports; contracted exchange data products exist | No approved API/service agreement in this release | **Completed decision:** no authoritative provider approved; pack remains partial; manual/RSS first and yfinance fallback only |
| UCDP | Historical outcomes | Free token by request; georeferenced and candidate conflict datasets | Research access request and publication cadence make it a base-rate source, not breaking news | **Future:** conflict base rates and forecast resolution |
| ACLED | Historical and current conflict | Authenticated API and rich event data | Commercial use needs a corporate license; AI and competitive-use restrictions are material | **Excluded by default:** integrate only after explicit legal approval |

## Source Findings

### Crypto

#### CoinGecko

CoinGecko remains feasible for the first crypto price workflow. The current Demo plan advertises 100 calls per minute, 10,000 monthly credits, data freshness from 60 seconds, and required attribution. The pricing page distinguishes paid plans with commercial licenses from Demo. FRA must therefore treat Demo as a local-evaluation profile, expose the remaining quota where possible, cache aggressively, and never imply exchange-authoritative prices.

Useful endpoints include coin lookup, current markets, dated history, and market-chart ranges. Coin IDs rather than symbols are the durable provider alias. Inactive-asset history and some depth are plan dependent, so survivorship-free backtests cannot assume Demo coverage.

Sources: [CoinGecko plans and limits](https://www.coingecko.com/en/api/pricing), [endpoint overview](https://docs.coingecko.com/reference/endpoint-overview), [key setup](https://docs.coingecko.com/docs/setting-up-your-api-key).

#### Coin Metrics Community

Coin Metrics fills an important gap left by CoinGecko: selected on-chain and network-health metrics. The Community API needs no key, uses ISO 8601 UTC timestamps, and currently documents a limit of 10 requests per 6 seconds per IP. Community data is a subset and is documented for non-commercial use under a Creative Commons license, so the adapter remains conditional on the workspace use policy.

Source: [Coin Metrics API v4](https://docs.coinmetrics.io/api/v4/).

#### yfinance

yfinance is technically easy to integrate and useful for a local prototype. It supports multi-ticker daily history, corporate actions, options and many ticker types. Intraday history cannot extend beyond the most recent 60 days. Its own documentation says it is not affiliated with Yahoo, is intended for research and education, and that Yahoo data is intended for personal use.

FRA must label it `authority = unofficial_aggregator`, use it only when the active usage policy permits personal research, and allow an authoritative or licensed adapter to replace it without changing workflows. It must not be the source of record for production advice, commercial redistribution, or exchange-authoritative claims.

Sources: [yfinance documentation and legal notice](https://ranaroussi.github.io/yfinance/), [history API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html).

### Macro and commodity benchmarks

#### FRED and ALFRED

FRED is feasible through a registered free API key. Its API exposes series, observations, releases, update dates and vintage dates. ALFRED and real-time periods are especially valuable because FRA can reconstruct what a macro series showed on the forecast date rather than using a later revision.

The adapter must preserve `observation_period`, `published_at` when available, `available_at`, `vintage_date`, and `retrieved_at`. A revised number must supersede rather than overwrite prior evidence.

Source: [FRED API documentation](https://fred.stlouisfed.org/docs/api/fred/).

#### World Bank Indicators

The World Bank Indicators API requires no key and offers programmatic access to nearly 16,000 series across more than 45 databases, including development and debt data. It is well suited to structural country features such as debt, trade dependence and long-run inflation, but many observations are annual and lagged.

Source: [World Bank Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392).

#### World Bank Pink Sheet

The Pink Sheet is feasible as a versioned file adapter rather than an HTTP row API. The World Bank publishes monthly and annual historical XLSX workbooks, and the catalog says commodity prices are normally updated on the second business day of the month. FRA should download with conditional HTTP requests, hash the workbook, normalize only needed rows into Markdown, and retain the file metadata and schema mapping.

Sources: [Pink Sheet files](https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/worldbank-commodities-price-data-the-pink-sheet), [commodity data catalog](https://datacatalog.worldbank.org/search/dataset/0038238/commodity-prices-history-and-projections).

### Physical energy and trade

#### EIA

EIA API v2 is feasible and should be the first physical-energy adapter. API access uses a free key; bulk downloads do not require one. Routes cover petroleum, natural gas, electricity, production, inventories, prices and related metadata. FRA must throttle requests, prefer bulk files for large history, preserve the frequency and units, and distinguish US series from international coverage.

Sources: [EIA API v2 documentation](https://www.eia.gov/opendata/documentation.php), [EIA open data catalog](https://www.eia.gov/opendata/index.php/api).

#### JODI Oil and Gas

JODI complements EIA with monthly, country-level physical balances. Complete Oil CSV series are available free from January 2002 to roughly one month old for more than 90 participating economies; Gas starts in 2009 for around 80. The files include production, imports, exports, demand, stocks and refinery flows. This is strong medium-term supply evidence, not a same-day disruption signal.

Sources: [JODI Oil downloads](https://www.jodidata.org/oil/database/data-downloads.aspx), [JODI Oil coverage](https://www.jodidata.org/oil/database/overview.aspx), [JODI Gas coverage](https://www.jodidata.org/gas/database/overview.aspx).

#### IMF PortWatch

PortWatch is unusually valuable for FRA's chokepoint thesis because it derives daily port-call and shipment indicators from vessel movements for ports and critical maritime passages. It is an open, experimental platform and exposes a searchable API catalog. The adapter needs a feasibility spike to identify stable dataset endpoints, revision behavior, units, and reuse terms before it becomes required evidence.

Sources: [IMF PortWatch launch](https://www.imf.org/en/news/articles/2023/11/13/pr23390-imf-university-oxford-launch-portwatch-platform-monitor-simulate-trade-disruptions), [PortWatch Search API](https://portwatch.imf.org/api/search/definition/), [methodology and coverage](https://www.imf.org/en/publications/wp/issues/2025/05/16/nowcasting-global-trade-from-space-566957).

#### UN Comtrade

UN Comtrade can build bilateral country-product dependencies. A no-key preview exists but is limited to a small result set. A free registered account and subscription key unlock broader free API access; premium plans cover bulk workflows. FRA must version HS classifications, distinguish reporter from mirror estimates, and retain release or retrieval time because data is revised and arrives with a lag.

Source: [UN Comtrade API guide](https://uncomtrade.org/docs/un-comtrade-api/).

#### FAOSTAT fertilizer data

FAOSTAT's Fertilizers by Product domain covers country-level production, trade and agricultural use from 2002, annually. Its methodology maps products such as urea, ammonia, phosphate rock and potash to HS codes, making it useful for the structural dependency graph. It is too slow for live detection, completeness varies by product, and source-specific reuse terms must be reviewed before redistribution.

Source: [FAOSTAT Fertilizers by Product methodology](https://files-faostat.fao.org/production/RFB/RFB_EN_README.pdf).

### Documents, events, and historical base rates

#### Official feeds and manual URLs

Official documents should outrank news aggregators. FRA needs a configurable RSS/Atom adapter and a manual URL ingestion adapter for central banks, regulators, exchanges, statistical offices, energy agencies, company investor-relations pages and government releases. Each configured source gets its own descriptor and terms record; `official` is an authority class, not a guarantee that every claim is correct.

Only permitted excerpts and normalized observations are persisted. FRA stores document URL, publisher, title, publication and retrieval times, content hash, language, and any later correction or withdrawal.

#### GDELT

GDELT 2.0 Event, Mentions and Global Knowledge Graph files update every 15 minutes and add multilingual discovery. It is useful for finding signals and measuring changes in coverage, but its event extraction is not ground truth. FRA must deduplicate syndicated stories, group sources by independence, separate event time from `DATEADDED`, and require corroboration for material claims.

The 2026-07-18 feasibility probe also found a certificate-hostname failure on the HTTPS bulk-download host and immediate throttling on the DOC API. FRA must never disable TLS verification to work around this; use a supported secure endpoint or leave the adapter unavailable.

Sources: [GDELT data catalog](https://www.gdeltproject.org/data.html), [GDELT 2.0 event codebook](https://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf), [DOC API overview](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/).

#### Geopolitical Risk index

The Caldara-Iacoviello GPR dataset provides monthly country-specific indexes and a recent daily series. It is useful as a historical risk-regime feature and as a baseline against FRA's extracted event intensity. It cannot identify a causal chain or individual company by itself.

Source: [Geopolitical Risk index data](https://www.matteoiacoviello.com/gpr.htm).

#### UCDP and ACLED

UCDP's API is free, but a token must be requested and access is reviewed. Its georeferenced and candidate datasets can support base rates and historical forecast resolution.

ACLED is not enabled by default. Its current terms state that commercial entities need a corporate license and place material restrictions on AI, ML, competitive products, and redistribution. A future adapter requires explicit legal approval and a provider policy that proves the active workspace is permitted.

Sources: [UCDP API](https://ucdp.uu.se/apidocs/index.html), [ACLED EULA](https://acleddata.com/eula), [ACLED content usage terms](https://acleddata.com/contentusage).

### Company disclosures and market-specific sources

#### SEC EDGAR

SEC EDGAR is highly feasible for US equities. Its unauthenticated JSON APIs expose submission history and standardized XBRL facts, with bulk files republished nightly. Automated clients must declare a descriptive `User-Agent` and remain within the SEC fair-access ceiling of 10 requests per second.

FRA should use filings as documents and XBRL as normalized fundamentals. It must preserve accession number, acceptance time, filing date, report period, amendment status, taxonomy and units. Filing facts should not be treated as available before the acceptance timestamp.

Sources: [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [SEC fair access guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions).

#### South Korea

OpenDART is feasible with a free authentication key. It provides disclosure search, original documents, XBRL, periodic financial statements and corporate codes, including English endpoints for supported data. The documented call-limit error usually appears at 20,000 requests but may use a different configured threshold.

KRX Open API can provide authoritative daily market statistics from 2010, but it requires membership, an authentication-key application, a separate service application and administrator approval. Redistribution and real-time market data require additional terms or arrangements.

Sources: [OpenDART introduction](https://opendart.fss.or.kr/intro/main.do), [OpenDART disclosure API](https://engopendart.fss.or.kr/guide/detail.do?apiGrpCd=DE001&apiId=AE00001), [KRX access process](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp), [KRX services](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd).

#### Vietnam

The 2026-07-19 release decision selects no authoritative Vietnam price provider. Official exchange
web pages expose market data, and HOSE/HNX offer data-service products, but FRA has no approved
service agreement, usage/retention decision, stable adapter contract, or point-in-time proof for
them. This is a completed no-provider decision for the release—not an unresolved implementation
choice. FRA must not describe yfinance as authoritative Vietnam coverage. The initial Vietnam pack
supports:

- configured official disclosure URLs and feeds where available;
- user-supplied documents;
- explicit symbol and exchange mappings;
- yfinance only under the personal-research fallback policy;
- a new provider review only after exchange/licensed access and terms are recorded.

An authoritative commercial or exchange agreement can later be added behind the same ports. Current
official references include the
[HNX trading-data surface](https://www.hnx.vn/vi-vn/co-phieu-etfs/du-lieu-thi-truong-ny.html),
[HNX information packages](https://www.hnx.vn/vi-vn/dich-vu-cctt/du-lieu-cung-cap-list.html), and
[HOSE Market Data Feed/Webservice pricing](https://staticfile.hsx.vn/Uploads/UploadDocuments/2406142/Bieu%20gia%20dich%20vu%20cung%20cap%20tin.pdf).

### Market positioning

#### CFTC Commitments of Traders

CFTC provides public API access and historical files for futures positioning. The report normally describes Tuesday positions and becomes public Friday at 3:30 p.m. Eastern, so `observation_period` and `available_at` are different. Backtests that expose Tuesday data before Friday have look-ahead leakage.

Sources: [CFTC COT data and API](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm), [release schedule](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm).

## MVP Provider Set

The first implementation should remain a sequence of vertical slices.

### Foundation slice

- `ManualDocumentAdapter` and `RssAtomDocumentAdapter`
- `CoinGeckoMarketDataAdapter` under the local-evaluation policy
- `WorldBankIndicatorsAdapter`
- `MarkdownResearchRepository`
- source registry, router, manifests, provenance envelope and contract tests

### Oil and fertilizer forecasting slice

- `EiaPhysicalFlowAdapter`
- `FredEconomicSeriesAdapter` with ALFRED vintages
- `WorldBankPinkSheetAdapter`
- `SecEdgarFundamentalsAdapter` for US businesses
- `GdeltEventAdapter` as optional discovery
- forecast ledger, exposure graph, monitoring triggers and outcome scoring

### Enrichment slice

- Coin Metrics Community
- JODI Oil and Gas
- UN Comtrade
- FAOSTAT fertilizer data
- CFTC COT
- GPR index
- IMF PortWatch after a successful endpoint and terms spike

### Regional equities slice

1. US: SEC EDGAR plus a permitted price source.
2. South Korea: OpenDART, then KRX after key approval.
3. Vietnam: official-document adapter first; no authoritative price adapter is approved for this
   release, and a later selection requires recorded exchange/licensed access and terms.

## Known Gaps Requiring Paid or Partner Data

Free sources do not fully solve:

- redistribution-safe, exchange-authoritative equity prices across US, Vietnam, and South Korea;
- tick-level or reliable real-time futures and options data;
- full options-implied event probabilities;
- live global AIS vessel tracks and cargo identities;
- complete company facility, supplier, customer, hedge, and geographic exposure data;
- licensed full-text global news archives and earnings-call transcripts;
- corporate actions and delisted-security history suitable for institutional backtests.

These are explicit capability gaps. FRA should return `CapabilityUnavailable` or a lower-confidence report instead of silently filling them with agent guesses.

## Source Selection Policy

An `EvidenceRequirement` declares:

```text
data_kind
subject and provider-independent identifiers
geography and market
fields and units
time range and resolution
maximum age
point_in_time_at
minimum authority
minimum independent sources
allowed usage policy
raw-retention requirement
```

The `SourceRouter` then:

1. filters the registry by typed capability;
2. rejects providers whose usage policy does not permit the active workspace;
3. rejects providers that cannot satisfy the required history, geography, resolution, or point-in-time cutoff;
4. ranks remaining sources by configured authority, freshness, completeness and cost;
5. selects explicit primary, fallback, and cross-check roles;
6. returns separate evidence when sources disagree;
7. records the rule and candidates considered.

It never silently averages contradictory values or falls back from an official source to an unofficial source without a visible warning.

## Adding Future Sources

Each adapter ships with:

1. a `SourceDescriptor` manifest;
2. one or more small typed provider-port implementations;
3. provider-to-FRA identifier mappings;
4. time, unit, revision and pagination normalization;
5. authentication and quota behavior;
6. a health probe that avoids expensive calls;
7. fixture-backed contract tests;
8. live integration tests disabled by default;
9. terms, attribution, retention and allowed-use metadata;
10. documentation of known gaps and fallback behavior.

Built-in adapters register at bootstrap. A future plugin package may register through a Python entry-point group such as `fra.data_sources`; workflows still depend only on FRA-owned ports and evidence requirements.

## Definition of Done for a Source Adapter

A source is not considered integrated merely because one request succeeds. It is complete when:

- its manifest and allowed-use policy validate;
- capabilities are discoverable without workflow knowledge;
- identifiers and ambiguity are handled explicitly;
- all time semantics required for point-in-time replay are populated;
- units, currency, timezone and revisions normalize correctly;
- quotas, retry hints, pagination and partial responses are tested;
- raw provider types never cross the adapter boundary;
- fixtures cover a normal response, empty response, revision, rate limit and schema error;
- normalized evidence round-trips through Markdown;
- the provider can be removed or replaced through configuration only;
- terms and documentation URLs have a recorded review date.
