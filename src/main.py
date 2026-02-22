#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI News Bot - 每日AI资讯聚合推送到飞书群
Daily AI news aggregation and push to Feishu group.

Features:
- 英文渠道:中文渠道 = 6:4
- 英文内容中英文对照 (使用智谱 AI 翻译)
- 优先级：社媒 > 聚合社区 > 官方博客 > 学术前沿
- 热点资讯控制在10条以内
"""

import os
import json
import re
import hashlib
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from openai import OpenAI

# ============================================================
# 配置区 Configuration
# ============================================================

FEISHU_WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# 北京时区
CST = timezone(timedelta(hours=8))

# 渠道优先级权重（越高越优先）
SOURCE_PRIORITY = {
    "social": 4,
    "community": 3,
    "official": 2,
    "academic": 1,
}

# RSS 数据源配置
RSS_SOURCES = {
    "en": [
        {"name": "Reddit r/MachineLearning", "url": "https://www.reddit.com/r/MachineLearning/.rss", "priority": "social"},
        {"name": "Reddit r/artificial", "url": "https://www.reddit.com/r/artificial/.rss", "priority": "social"},
        {"name": "Hacker News", "url": "https://hnrss.org/frontpage?q=AI+OR+LLM+OR+GPT+OR+machine+learning", "priority": "community"},
        {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "priority": "community"},
        {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "priority": "community"},
        {"name": "Wired AI", "url": "https://www.wired.com/feed/tag/ai/latest/rss", "priority": "community"},
        {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss/", "priority": "official"},
        {"name": "HuggingFace Blog", "url": "https://huggingface.co/blog/feed.xml", "priority": "official"},
        {"name": "ArXiv CS.AI", "url": "http://arxiv.org/rss/cs.AI", "priority": "academic"},
    ],
    "zh": [
        {"name": "量子位", "url": "https://www.qbitai.com/feed/", "priority": "community"},
        {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "priority": "community"},
        {"name": "36氪AI", "url": "https://36kr.com/feed", "priority": "community"},
        {"name": "少数派", "url": "https://sspai.com/feed", "priority": "community"},
    ],
}

AI_KEYWORDS = ["AI", "intelligence", "learning", "LLM", "GPT", "ChatGPT", "Claude", "Gemini", "人工智能", "大模型"]

# ============================================================
# 数据处理模块
# ============================================================

def fetch_rss(source: dict ) -> list:
    try:
        feed = feedparser.parse(source["url"])
        entries = []
        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", entry.get("description", "")))[:300]
            if title and link:
                entries.append({
                    "title": title, "link": link, "summary": summary, "source": source["name"],
                    "priority": SOURCE_PRIORITY.get(source["priority"], 1), "priority_label": source["priority"]
                })
        return entries
    except: return []

def translate_to_chinese(text: str, client: OpenAI) -> str:
    if not text or not client: return ""
    try:
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "system", "content": "你是一个专业的AI领域翻译，请将以下英文内容翻译为简洁的中文。只输出翻译结果。"},
                      {"role": "user", "content": text}],
            max_tokens=200, temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except: return ""

def build_feishu_card(news_items: list) -> dict:
    now_cst = datetime.now(tz=CST)
    elements = [{"tag": "hr"}]
    for i, item in enumerate(news_items, 1):
        emoji = {"social": "🔥", "community": "📰", "official": "🏢", "academic": "🎓"}.get(item['priority_label'], "📰")
        content = f"**{i}. {emoji} [{item['source']}]**\n"
        if item.get("is_bilingual"):
            content += f"**{item.get('title_zh', '')}**\n*{item['title']}*\n> {item.get('summary_zh', '')}\n"
        else:
            content += f"**{item['title']}**\n> {item['summary'][:150]}\n"
        content += f"[🔗 阅读原文]({item['link']})"
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content}})
        elements.append({"tag": "hr"})
    
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"⏰ 更新时间：{now_cst.strftime('%H:%M')} CST | 🤖 AI News Bot"}})
    return {
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": f"🤖 AI 日报 · {now_cst.strftime('%m月%d日')}"}},
        "elements": elements
    }

def main():
    client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://open.bigmodel.cn/api/paas/v4/" ) if OPENAI_API_KEY else None
    en_news, zh_news = [], []
    for lang, sources in RSS_SOURCES.items():
        for s in sources:
            res = fetch_rss(s)
            for r in res: r["lang"] = lang
            if lang == "en": en_news.extend(res)
            else: zh_news.extend(res)
    
    selected_en = sorted(en_news, key=lambda x: x['priority'], reverse=True)[:6]
    selected_zh = sorted(zh_news, key=lambda x: x['priority'], reverse=True)[:4]
    
    processed = []
    for item in selected_en:
        item.update({"title_zh": translate_to_chinese(item["title"], client), 
                     "summary_zh": translate_to_chinese(item["summary"], client), "is_bilingual": True})
        processed.append(item)
    for item in selected_zh:
        item["is_bilingual"] = False
        processed.append(item)
        
    card = build_feishu_card(processed)
    requests.post(FEISHU_WEBHOOK_URL, json={"msg_type": "interactive", "card": json.dumps(card)})

if __name__ == "__main__":
    main()
