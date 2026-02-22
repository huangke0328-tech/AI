#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import re
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from openai import OpenAI

# 配置
FEISHU_WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
CST = timezone(timedelta(hours=8))
SOURCE_PRIORITY = {"social": 4, "community": 3, "official": 2, "academic": 1}

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

def fetch_rss(source):
    print(f"  - 正在抓取: {source['name']}...")
    try:
        # 设置 User-Agent 避免被屏蔽
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        resp = requests.get(source["url"], headers=headers, timeout=15)
        feed = feedparser.parse(resp.content)
        entries = []
        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", entry.get("description", "")))[:300]
            if title and link:
                entries.append({
                    "title": title, 
                    "link": link, 
                    "summary": summary, 
                    "source": source["name"], 
                    "priority": SOURCE_PRIORITY.get(source["priority"], 1), 
                    "priority_label": source["priority"]
                })
        print(f"    成功抓取到 {len(entries)} 条内容")
        return entries
    except Exception as e:
        print(f"    抓取失败: {e}")
        return []

def translate_to_chinese(text, client):
    if not text or not client: return ""
    try:
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "system", "content": "你是一个专业的AI领域翻译，请将以下英文内容翻译为简洁的中文。只输出翻译结果。"}, {"role": "user", "content": text}],
            max_tokens=300, temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"    翻译出错: {e}")
        return ""

def build_feishu_card(news_items):
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
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": f"🤖 AI 日报 · {now_cst.strftime('%m月%d日')}"}}, 
        "elements": elements
    }

def main():
    print("=== AI News Bot 启动 ===")
    client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://open.bigmodel.cn/api/paas/v4/") if OPENAI_API_KEY else None
    if client: print("[OK] 智谱 AI 已就绪")
    
    en_news, zh_news = [], []
    print("\n[1/4] 抓取英文源...")
    for s in RSS_SOURCES["en"]:
        res = fetch_rss(s)
        for r in res: r["lang"] = "en"
        en_news.extend(res)
    
    print("\n[2/4] 抓取中文源...")
    for s in RSS_SOURCES["zh"]:
        res = fetch_rss(s)
        for r in res: r["lang"] = "zh"
        zh_news.extend(res)
    
    print(f"\n抓取汇总: 英文 {len(en_news)} 条, 中文 {len(zh_news)} 条")
    
    selected_en = sorted(en_news, key=lambda x: x['priority'], reverse=True)[:6]
    selected_zh = sorted(zh_news, key=lambda x: x['priority'], reverse=True)[:4]
    
    print(f"已筛选热点: 英文 {len(selected_en)} 条, 中文 {len(selected_zh)} 条")
    
    processed = []
    print("\n[3/4] 翻译处理中...")
    for item in selected_en:
        item.update({
            "title_zh": translate_to_chinese(item["title"], client), 
            "summary_zh": translate_to_chinese(item["summary"], client), 
            "is_bilingual": True
        })
        processed.append(item)
    for item in selected_zh:
        item["is_bilingual"] = False
        processed.append(item)
    
    print("\n[4/4] 推送至飞书...")
    card = build_feishu_card(processed)
    resp = requests.post(FEISHU_WEBHOOK_URL, json={"msg_type": "interactive", "card": json.dumps(card)})
    print(f"推送结果: {resp.json()}")
    print("=== AI News Bot 完成 ===")

if __name__ == "__main__":
    main()
