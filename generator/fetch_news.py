"""
Content generation engine for 星尘笔记 (Stardust Notes).
Fetches real AI news from multiple sources, cross-validates, and generates
Chinese-language insight articles using Claude API.

Usage:
    python fetch_news.py              # Generate new articles
    python fetch_news.py --dry-run    # Preview without saving
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
import yaml
import requests

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent.parent
ARTICLES_FILE = BASE_DIR / "articles.json"
SOURCES_FILE = Path(__file__).resolve().parent / "sources.yaml"

UNSPLASH_IMAGES = [
    "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&q=80",
    "https://images.unsplash.com/photo-1464802686167-b939a6910659?w=800&q=80",
    "https://images.unsplash.com/photo-1518837695005-2083093ee35b?w=800&q=80",
    "https://images.unsplash.com/photo-1534447677768-be436bb09401?w=800&q=80",
    "https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?w=800&q=80",
    "https://images.unsplash.com/photo-1507783548227-544c3b8fc065?w=800&q=80",
    "https://images.unsplash.com/photo-1470813740244-df37b8c1edcb?w=800&q=80",
    "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=800&q=80",
    "https://images.unsplash.com/photo-1518531933037-91b2f5f229cc?w=800&q=80",
]

CLAUDE_SYSTEM_PROMPT = """你是"星尘笔记"博客的主编——一位神秘而理性、追求真相的深夜观察者。

你的任务：根据提供的【真实新闻来源】，撰写一篇面向中文读者的AI科技深度分析文章。

写作要求：
1. **只基于提供的新闻来源撰写**，不编造任何未在来源中出现的细节。如果来源信息有矛盾，如实指出。
2. 风格：神秘、优美、有深度。像深夜中的思考者，冷静而透彻。
3. 结构：
   - 开篇用引人入胜的叙述引出话题（不要"近日"式新闻导语）
   - 中间展开核心事实与分析，穿插你自己的深度见解
   - 结尾以哲思或前瞻视角收束，留下余味
4. 字数：800-1200字中文
5. 用 Markdown 格式输出（h2 小标题、段落、必要时用 blockquote 引用关键数据）
6. 文末附一个 ## 关键事实速览 小节，用列表列出 3-5 条经过验证的核心事实。
7. 全文语气：像一个洞悉一切的观察者在深夜写下思考，而非新闻播报员。"""


def load_config() -> dict:
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_existing_articles() -> list[dict]:
    if ARTICLES_FILE.exists():
        try:
            with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else data.get("articles", [])
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def save_articles(articles: list[dict]) -> None:
    articles.sort(key=lambda a: a.get("date", ""), reverse=True)
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump({"articles": articles}, f, ensure_ascii=False, indent=2)


def fetch_feed(url: str, timeout: int = 15) -> list[dict]:
    """Fetch and parse a single RSS feed. Returns list of story dicts."""
    try:
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent": "StardustNotes/1.0 (Blog Content Aggregator)"
        })
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)

        stories = []
        for entry in feed.entries[:15]:  # only recent 15 per feed
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            # Strip HTML tags from summary
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")

            if title and link:
                stories.append({
                    "title": title,
                    "link": link,
                    "summary": summary[:500],
                    "published": published,
                })
        return stories
    except Exception as e:
        print(f"  [WARN] Failed to fetch {url}: {e}", file=sys.stderr)
        return []


def normalize_title(title: str) -> str:
    """Normalize title for comparison: lowercase, remove common noise words."""
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    noise = {"the", "a", "an", "is", "are", "was", "were", "has", "have",
             "this", "that", "these", "those", "its", "new", "how", "why",
             "what", "can", "will", "could", "would", "may", "might"}
    words = [w for w in t.split() if w not in noise]
    return " ".join(words[:12])


def find_overlapping_stories(all_feeds: dict[str, list[dict]]) -> list[dict]:
    """
    Group stories from different sources that report the same event.
    A story is "verified" if it appears in >= min_sources independent feeds.
    Returns list of verified story groups, each with source citations.
    """
    config = load_config()
    min_sources = config.get("min_sources", 2)
    keywords = [kw.lower() for kw in config.get("keywords", [])]

    # Build inverted index: normalized phrase -> list of (feed_name, story)
    from collections import defaultdict

    groups = defaultdict(list)

    for feed_name, stories in all_feeds.items():
        for story in stories:
            # Keyword filter: at least one AI-related keyword
            combined = (story["title"] + " " + story["summary"]).lower()
            if not any(kw in combined for kw in keywords):
                continue

            norm = normalize_title(story["title"])
            # Use 3-5 word shingles for fuzzy matching
            words = norm.split()
            if len(words) >= 3:
                for i in range(len(words) - 2):
                    shingle = " ".join(words[i:i + 3])
                    groups[shingle].append((feed_name, story))

    # Collect groups with >= min_sources
    verified_groups: dict[str, dict] = {}
    seen_urls = set()

    for shingle, entries in groups.items():
        # Deduplicate by feed name
        unique_feeds = {}
        for feed_name, story in entries:
            if feed_name not in unique_feeds:
                unique_feeds[feed_name] = story

        if len(unique_feeds) >= min_sources:
            # Use the first story's title as the group representative
            first_story = list(unique_feeds.values())[0]
            group_key = normalize_title(first_story["title"])[:60]

            if group_key in verified_groups:
                continue  # already captured

            # Avoid duplicates by URL
            urls = [s["link"] for s in unique_feeds.values()]
            if any(u in seen_urls for u in urls):
                continue
            for u in urls:
                seen_urls.add(u)

            verified_groups[group_key] = {
                "representative_title": first_story["title"],
                "sources": [
                    {
                        "name": fn,
                        "url": s["link"],
                        "title": s["title"],
                        "summary": s["summary"][:300],
                    }
                    for fn, s in unique_feeds.items()
                ],
                "source_count": len(unique_feeds),
            }

    # Sort by source count (more sources = more verified)
    result = sorted(verified_groups.values(),
                    key=lambda g: g["source_count"], reverse=True)
    return result


def call_claude_to_generate(story_group: dict, api_key: str) -> dict | None:
    """Call Claude API to generate a Chinese insight article from verified sources."""

    # Build source context
    sources_text = ""
    for i, src in enumerate(story_group["sources"], 1):
        sources_text += f"\n[来源{i}] {src['name']}\n标题: {src['title']}\n摘要: {src.get('summary', 'N/A')}\n链接: {src['url']}\n"

    user_prompt = f"""以下是经过{story_group['source_count']}个独立新闻源交叉验证的真实AI科技报道。请基于此撰写一篇深度分析文章。

=== 已验证新闻来源 ===
{sources_text}

=== 写作指令 ===
- 主题方向：基于以上来源，撰写一篇关于此话题的中文深度分析
- 如果多个来源存在信息差异，请如实指出版本差异
- 保持神秘而优美的深夜思考者风格
- 文末 ## 关键事实速览 列出3-5条核心事实"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 3000,
                "system": CLAUDE_SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        content = data["content"][0]["text"]

        # Extract title (first line that starts with # or a bold line)
        lines = content.strip().split("\n")
        title = ""
        body_start = 0
        for i, line in enumerate(lines):
            cleaned = line.strip().lstrip("#").strip()
            if cleaned and len(cleaned) > 5:
                title = cleaned
                body_start = i + 1
                break

        if not title:
            title = story_group["representative_title"]

        body = "\n".join(lines[body_start:]).strip()

        return {
            "title": title,
            "content": body,
            "summary": body[:200].rsplit(".", 1)[0].strip() + "……",
            "sources": story_group["sources"],
            "source_count": story_group["source_count"],
        }

    except Exception as e:
        print(f"  [ERROR] Claude API call failed: {e}", file=sys.stderr)
        return None


def generate_article_id(title: str) -> str:
    """Generate a short unique ID from the title."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    slug = re.sub(r"[^a-zA-Z0-9一-鿿]", "", title)[:20]
    return f"{ts}-{slug}"


def pick_image(articles: list[dict]) -> str:
    """Pick an Unsplash image not recently used."""
    recent_imgs = {a["image"] for a in articles[-6:] if "image" in a}
    available = [img for img in UNSPLASH_IMAGES if img not in recent_imgs]
    if not available:
        available = UNSPLASH_IMAGES
    # Deterministic-ish rotation based on date
    idx = int(datetime.now().strftime("%d")) % len(available)
    return available[idx]


def detect_tags(title: str, content: str) -> list[str]:
    """Auto-detect relevant tags from article content."""
    tag_keywords = {
        "OpenAI": "OpenAI",
        "GPT": "GPT",
        "Claude": "Claude",
        "Anthropic": "Anthropic",
        "Gemini": "Gemini",
        "Google": "Google AI",
        "LLM": "大语言模型",
        "开源": "开源",
        "开源模型": "开源模型",
        "AGI": "AGI",
        "安全": "AI安全",
        "监管": "AI监管",
        "芯片": "AI芯片",
        "机器人": "机器人",
        "多模态": "多模态",
        "编程": "AI编程",
        "代码": "AI编程",
        "智能体": "AI Agent",
        "Agent": "AI Agent",
        "生成式": "生成式AI",
        "深度学习": "深度学习",
        "推理": "推理",
    }
    combined = (title + " " + content).lower()
    tags = []
    for kw, tag in tag_keywords.items():
        if kw.lower() in combined and tag not in tags:
            tags.append(tag)
    if not tags:
        tags.append("AI前沿")
    return tags[:4]


def main() -> None:
    parser = argparse.ArgumentParser(description="星尘笔记 - Content Generation Engine")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--max-articles", type=int, default=2,
                        help="Max articles to generate per run")
    args = parser.parse_args()

    config = load_config()
    sources_config = config.get("sources", [])
    max_articles = args.max_articles

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[FATAL] ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    print(f"星尘笔记 · 内容生成引擎")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"信源数量: {len(sources_config)}")
    print(f"=" * 50)

    # Step 1: Fetch all RSS feeds
    print("\n[1/4] 抓取 RSS 源...")
    all_feeds: dict[str, list[dict]] = {}
    for src in sources_config:
        name = src["name"]
        url = src["url"]
        print(f"  → {name}")
        stories = fetch_feed(url)
        all_feeds[name] = stories
        print(f"    获取 {len(stories)} 条")

    total_raw = sum(len(s) for s in all_feeds.values())
    print(f"  总计: {total_raw} 条原始新闻")

    # Step 2: Cross-reference
    print(f"\n[2/4] 交叉验证 (最少 {config.get('min_sources', 2)} 个独立来源)...")
    verified = find_overlapping_stories(all_feeds)
    print(f"  验证通过: {len(verified)} 组")
    for i, v in enumerate(verified[:5]):
        print(f"  [{v['source_count']}源] {v['representative_title'][:80]}...")

    if not verified:
        print("  未发现可通过交叉验证的新闻组，本次跳过。")
        return

    # Step 3: Generate articles via Claude
    print(f"\n[3/4] 生成中文文章 (最多 {max_articles} 篇)...")
    existing = load_existing_articles()
    existing_urls = set()
    for a in existing:
        for s in a.get("sources", []):
            existing_urls.add(s.get("url", ""))

    new_articles = []
    for i, group in enumerate(verified):
        if len(new_articles) >= max_articles:
            break

        # Skip if we already have this story
        group_urls = {s["url"] for s in group["sources"]}
        if group_urls & existing_urls:
            print(f"  [SKIP] 已存在: {group['representative_title'][:60]}...")
            continue

        print(f"  [{i+1}/{min(len(verified), max_articles)}] 生成中...")
        print(f"    话题: {group['representative_title'][:80]}...")
        generated = call_claude_to_generate(group, api_key)

        if generated:
            article = {
                "id": generate_article_id(generated["title"]),
                "title": generated["title"],
                "date": datetime.now().strftime("%Y.%m.%d"),
                "summary": generated["summary"],
                "content": generated["content"],
                "tags": detect_tags(generated["title"], generated["content"]),
                "image": pick_image(existing + new_articles),
                "sources": generated["sources"],
            }
            new_articles.append(article)
            print(f"    完成: {article['title'][:60]}...")
            # Brief pause between API calls
            if len(new_articles) < max_articles:
                time.sleep(2)

    print(f"  成功生成: {len(new_articles)} 篇")

    # Step 4: Save
    print(f"\n[4/4] 保存文章...")
    if args.dry_run:
        print("  [DRY RUN] 以下文章不会被保存：")
        for a in new_articles:
            print(f"    - {a['title']}")
            print(f"      ID: {a['id']}")
            print(f"      信源: {len(a['sources'])}")
    else:
        all_articles = existing + new_articles
        save_articles(all_articles)
        print(f"  已保存到: {ARTICLES_FILE}")
        print(f"  文章总数: {len(all_articles)}")

        # Also generate RSS
        generate_rss(all_articles)
        print(f"  RSS 已更新: {BASE_DIR / 'rss.xml'}")

    print(f"\n{'=' * 50}")
    print(f"生成完成。{'(DRY RUN)' if args.dry_run else ''}")


def generate_rss(articles: list[dict]) -> None:
    """Generate RSS 2.0 XML feed."""
    site_url = "https://steady-nasturtium-fa34fb.netlify.app"

    items_xml = ""
    for a in articles[:20]:
        article_url = f"{site_url}/article.html?id={a['id']}"
        escaped_summary = a["summary"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        escaped_title = a["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        items_xml += f"""    <item>
      <title>{escaped_title}</title>
      <link>{article_url}</link>
      <description>{escaped_summary}</description>
      <pubDate>{a['date']}T20:00:00+08:00</pubDate>
      <guid isPermaLink="true">{article_url}</guid>
    </item>
"""

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>星尘笔记 — AI 前沿观察</title>
    <link>{site_url}</link>
    <description>每夜八点更新的AI前沿观察与深度思考，所有文章经过多源交叉验证</description>
    <language>zh-CN</language>
    <lastBuildDate>{datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')}</lastBuildDate>
    <atom:link href="{site_url}/rss.xml" rel="self" type="application/rss+xml"/>
{items_xml}  </channel>
</rss>
"""
    rss_path = BASE_DIR / "rss.xml"
    with open(rss_path, "w", encoding="utf-8") as f:
        f.write(rss_xml)


if __name__ == "__main__":
    main()
