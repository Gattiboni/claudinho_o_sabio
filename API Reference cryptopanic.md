API Reference
Welcome to the CryptoPanic API reference. This section documents all available endpoints, parameters, responses, and error codes.

Authentication
⚠️ You must include your auth_token in all requests to authenticate.

Here is your API key that you can use for auth_token:

9df04104151c5e7df5b8ac87f9d5e77362641aa2

Your current API level is: DEVELOPER

Endpoints
Base endpoint that needs to be used is:

https://cryptopanic.com/api/developer/v2

News Endpoint
Retrieve a list of news posts.

GET /posts/

❗ Public vs Private Usage Mode
Private Usage Mode:

Uses your personal user settings, including custom sources and disabled sources.
Recommended for tickers, bots, and custom apps where personalized settings are required.
Public Usage Mode:

Designed for non-user-specific news posts, suitable for generic mobile and web apps.
To enable public mode, add the &public=true parameter to your request.
Ideal for public-facing mobile and web applications.
Direct usage in mobile apps is allowed.
For high-traffic web apps, local caching is strongly recommended.
Parameters
auth_token

Scope: Required
Description: It's used for authentication
Value: 9df04104151c5e7df5b8ac87f9d5e77362641aa2
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2
public

Scope: Optional
Description: Differentiates between private and public API usage.
Value: true
Availability: ✅ Developer, ✅ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&public=true
currencies

Scope: Optional
Description: Filters your search by desired currency codes.
Values: Any currency code available on our page, e.g. BTC,ETH
Availability: ✅ Developer, ✅ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&currencies=BTC,ETH
regions

Scope: Optional
Description: Filters your search by desired region.
Values: Any of supported regions on our site en (English), de (Deutsch), nl (Dutch), es (Español), fr (Français), it (Italiano), pt (Português), ru (Русский), tr (Türkçe), ar (عربي), zh (中國人), ja (日本), ko (한국인)
Default: en
Availability: ✅ Developer, ✅ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&regions=en
filter

Scope: Optional
Description: Filters your search by desired filter from our site.
Values: Any of supported filter on our site rising, hot, bullish, bearish, important, saved, lol
Availability: ✅ Developer, ✅ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&filter=rising
kind

Scope: Optional
Description: Filters your search by news kind
Values: available values are news, media, all
Default: all
Availability: ✅ Developer, ✅ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&kind=news
following

Scope: Optional
Description: Filters your search by sources that you follow - it's strictly PRIVATE API usage
Value: true
Availability: ✅ Developer, ✅ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&following=true
last_pull

Scope: Optional
Description: limit your search to the last pull time
Value: ISO date and time, e.g. "2026-03-31T22:29:54.834Z"
Availability: ❌ Developer, ❌ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&last_pull="2026-03-31T22:29:54.834Z"
panic_period

Scope: Optional
Description: include panic score for each news item
Values: 1h, 6h, 24h
Availability: ❌ Developer, ❌ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&panic_period=1h
panic_sort

Scope: Optional
Mandatory param: panic_period=<period>
Description: sort ascending asc or descending desc news items based on panic score value
Value: asc|desc
Availability: ❌ Developer, ❌ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&panic_period=1h&panic_sort=desc
size

Scope: Optional
Description: define how many items per page would you like to receive. Max size can be 500 per page
Value: from 1 to 500
Availability: ❌ Developer, ❌ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&size=20
with_content

Scope: Optional
Description: filter news items by checking if full content exists for those items
Value: true
Availability: ❌ Developer, ❌ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&with_content=true
search

Scope: Optional
Description: Search by keyword
Value: string keyword
Availability: ❌ Developer, ❌ Growth, ✅ Enterprise
Example: /api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&search=bitcoin
Response
      

{
  "next": "url",
  "previous": "url",
  "results": [
    ... array of items ...
  ]
}
        

  
Field	Type	Description
next	string | null	URL of the next page of results (or null).
ISO 8601 URI.
previous	string | null	URL of the previous page of results (or null)..
ISO 8601 URI.
results	array of Items	List of item objects (see “Item Object” below).

Item Object (each item in results)

Field	Type	Description
id	integer	Unique identifier for the post.
slug	string	URL-friendly short title.
title	string	Full title of the post.
description	string	Short summary or excerpt.
published_at	string (date-time)	When the post was published (ISO 8601).
created_at	string (date-time)	When the post was created in the system.
kind	string	Content type: “news”, “media”, “blog”, “twitter”, "reddit".
source	object	See “Source Object” below.
original_url	string (uri)	Link to the original article.
url	string (uri)	Link to the Cryptopanic-hosted article.
image	string (uri)	URL of the cover image.
instruments	array of Instrument	List of instruments mentioned (see “Instrument Object” below), e.g. BTC.
votes	object	See “Votes Object” below.
panic_score	integer (0–100)	Proprietary score quantifying news market importance and impact.
panic_score_1h	integer (0–100)	Proprietary score quantifying news market importance and impact within first hour.
author	string	Name of the article’s author.
content	object	See “Content Object” below.

Instrument Object

Field	Type	Description
code	string	Ticker or code of the instrument.
title	string	Full name of the instrument.
slug	string	URL-friendly identifier.
url	string (uri)	Link to the instrument’s page.
market_cap_usd	number	Market capitalization in USD.
price_in_usd	number	Current price in USD.
price_in_btc	number	Current price in BTC.
price_in_eth	number	Current price in ETH.
price_in_eur	number	Current price in EUR.
market_rank	integer	Global market rank of the instrument.

Source Object

Field	Type	Description
title	string	Publisher name.
region	string	Language code (e.g. “en”, “fr”).
domain	string	Publisher’s domain.
type	string	One of “feed”, “blog”, “twitter”, “media”, "reddit".

Votes Object

Field	Type	Description
negative	integer	Count of negative votes.
positive	integer	Count of positive votes.
important	integer	Count of “important” votes.
liked	integer	Count of “like” votes.
disliked	integer	Count of “dislike” votes.
lol	integer	Count of “lol” reactions.
toxic	integer	Count of “toxic” reactions.
saved	integer	Count of times post was saved.
comments	integer	Count of comments on the post.

Content Object

Field	Type	Description
original	string | null	Raw HTML/markup of the original article (if available).
clean	string | null	Sanitized text-only version of the content.
Portfolio Endpoint
Retrieve your portfolio. Available only under GROWTH and ENTERPRISE api

GET /portfolio/

Try out: /api/developer/v2/portfolio/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2
RSS
Access our RSS feed here: /news/rss/

Customize your RSS by adding API parameters to tailor the feed to your specific needs. To receive content in RSS format, include the parameter format=rss in your request.

/api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&currencies=ETH&filter=rising&format=rss
/api/developer/v2/posts/?auth_token=9df04104151c5e7df5b8ac87f9d5e77362641aa2&following=true&format=rss

IMPORTANT: Please note that when using the format=rss parameter, only 20 items will be returned in the response, regardless of your API plan.

Error Codes
Code	Meaning
401	Unauthorized - Invalid or missing auth_token
403	Forbidden - Rate limit exceeded or no access to this endpoint
429	Too Many Requests - You are being rate limited
500	Internal Server Error
Rate Limits
Rate limits depend on your plan. All requests are subject to two layers:

Level 1: Requests per second (e.g. 2/sec, 10/sec)
Level 2: Monthly cap (e.g. 1,000/month, 300,000/month)
Exceeding the Level 1 or Level 2 limit will result in HTTP 403 or 429 errors.

