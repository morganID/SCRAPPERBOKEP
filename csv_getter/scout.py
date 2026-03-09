"""
CSV Getter Scout - v3
  + Auto-Discovery containers
  + Comprehensive Modern Pagination Detection
    (numbered, next/prev, load-more, infinite-scroll, AJAX API interception)
"""

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from playwright.async_api import (
    async_playwright,
    Page,
    Playwright,
    Browser,
    BrowserContext,
    Request,
)

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--window-size=1920,1080",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

VIEWPORT = {"width": 1920, "height": 1080}

NAVIGATION_STRATEGIES = [
    ("domcontentloaded", 30_000),
    ("load", 45_000),
]

SCROLL_COUNT = 3
SCROLL_DELAY = 1.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Static Selector Candidates
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONTAINER_CANDIDATES = [
    (".video-list .video-item", 10),
    (".videos-list article", 10),
    (".video-grid .video", 9),
    (".video-list-item", 9),
    (".list-videos .video", 8),
    ("article.video", 8),
    (".posts .post", 7),
    (".content article", 6),
    ("[class*='video-list'] > *", 5),
    ("[class*='videos'] article", 5),
    (".content .video", 4),
    (".videos .video", 4),
    ("article", 2),
]

TITLE_CANDIDATES = [
    (".video-title", 10),
    ("h6.title", 9),
    ("h3", 8),
    ("h2", 7),
    ("h4", 6),
    ("h5", 6),
    ("h6", 6),
    (".title", 6),
    (".entry-title", 7),
    ("[class*='title']", 4),
    ("h1", 3),
]

LINK_CANDIDATES = [
    (".thumb a", 9),
    (".video-thumb a", 9),
    (".thumbnail a", 8),
    ("a[href*='/videos/']", 9),
    ("a[href*='/video']", 8),
    ("a[href*='/watch']", 8),
    ("a[href*='/v/']", 8),
    ("h6 a", 7),
    ("h3 a", 7),
    ("h2 a", 7),
    (".title a", 7),
    ("a[href]", 2),
    ("a", 1),
]

THUMBNAIL_CANDIDATES = [
    (".thumbnail img", 9),
    ("[class*='thumb'] img", 8),
    ("img.thumb", 8),
    (".video-thumb img", 8),
    ("img[data-src]", 8),
    ("img.lazy", 7),
    ("img[loading='lazy']", 6),
    ("img", 2),
]

DURATION_CANDIDATES = [
    (".duration", 10),
    (".video-duration", 9),
    ("[class*='duration']", 7),
    (".time", 5),
    ("[class*='time']", 3),
]

VIEWS_CANDIDATES = [
    (".views", 10),
    (".view-count", 9),
    (".views-count", 9),
    ("[class*='views']", 6),
    ("[class*='view-count']", 6),
    ("[class*='view']", 3),
]

# ── OLD static pagination (masih dipakai sebagai Phase-1) ──
PAGINATION_CANDIDATES_STATIC = [
    (".page-item a.page-link", 10),
    ("a.page-link", 9),
    (".page-item a", 8),
    ("li.page-item a", 8),
    ("ul.pagination a", 8),
    (".pagination a", 7),
    (".page-numbers a", 7),
    ("a.page-numbers", 7),
    ("[class*='pagination'] a", 6),
    ("[class*='paging'] a", 5),
    (".paging a", 5),
    (".pager a", 5),
    ("nav.pagination a", 6),
    ("a[href*='/page/']", 4),
    ("a[href*='?page=']", 4),
    ("a[href*='&page=']", 4),
    ("a[data-action='ajax']", 3),
]

STEALTH_SCRIPTS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Auto-Discovery JS: Containers (dari v2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AUTO_DISCOVER_JS = r"""
() => {
  const MIN_ITEMS = 3;
  const SKIP_TAGS = new Set([
    'SCRIPT','STYLE','BR','HR','META','LINK','HEAD','NOSCRIPT','SVG','PATH'
  ]);
  const VIDEO_RE  = /video|movie|film|clip|thumb|gallery|listing|catalog|mozaique|result|entry|item|card|media|content|post|archive|collection|channel|playlist|feed|stream/i;
  const STRUCT_RE = /list|grid|row|col|wrap|block|cell|tile|panel|box|section|container/i;
  const seen      = new Set();
  const candidates = [];

  function shortSel(el) {
    if (!el || el === document.documentElement || el === document.body) return null;
    if (el.id) return '#' + CSS.escape(el.id);
    let tag = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const parts = el.className.trim().split(/\s+/)
        .filter(c => c && !/[:()[\]{}=+~>^$|@!]/.test(c));
      if (parts.length) tag += '.' + parts.map(c => CSS.escape(c)).join('.');
    }
    return tag;
  }

  function makeFullSel(parent, childSample) {
    const pSel = shortSel(parent);
    const cSel = shortSel(childSample);
    if (!pSel || !cSel) return null;
    let full = pSel + ' > ' + cSel;
    try { if (document.querySelectorAll(full).length >= MIN_ITEMS) return full; } catch(_){}
    full = pSel + ' ' + cSel;
    try { if (document.querySelectorAll(full).length >= MIN_ITEMS) return full; } catch(_){}
    return null;
  }

  function childSignature(el) {
    const classes = (el.className || '').toString().trim().split(/\s+/).sort();
    return el.tagName + '|' + classes.join('.');
  }

  const parents = document.querySelectorAll(
    'div, section, main, ul, ol, nav, article, aside'
  );

  for (const parent of parents) {
    const rect = parent.getBoundingClientRect();
    if (rect.height < 80) continue;
    const children = Array.from(parent.children).filter(c => !SKIP_TAGS.has(c.tagName));
    if (children.length < MIN_ITEMS) continue;
    const groups = {};
    for (const c of children) {
      const sig = childSignature(c);
      (groups[sig] = groups[sig] || []).push(c);
    }
    for (const [sig, group] of Object.entries(groups)) {
      if (group.length < MIN_ITEMS) continue;
      let withLink = 0, withImg = 0, withText = 0, totalArea = 0;
      for (const el of group) {
        if (el.querySelector('a[href]')) withLink++;
        if (el.querySelector('img')) withImg++;
        const t = el.textContent.trim();
        if (t.length > 5 && t.length < 2000) withText++;
        const r = el.getBoundingClientRect();
        totalArea += r.width * r.height;
      }
      const n = group.length;
      const linkR = withLink / n, imgR = withImg / n, textR = withText / n;
      const avgArea = totalArea / n;
      let score = 0;
      if (linkR >= 0.8) score += 5; else if (linkR >= 0.5) score += 3; else if (linkR >= 0.3) score += 1;
      if (imgR >= 0.8) score += 4; else if (imgR >= 0.5) score += 2;
      if (textR >= 0.7) score += 2;
      if (n >= 12) score += 3; else if (n >= 6) score += 2; else score += 1;
      const combinedCls = ((parent.className||'') + ' ' + (group[0].className||'')).toString().toLowerCase();
      if (VIDEO_RE.test(combinedCls)) score += 3;
      if (STRUCT_RE.test(combinedCls)) score += 1;
      if (avgArea > 10000) score += 2; else if (avgArea > 3000) score += 1;
      if (linkR < 0.1) score -= 5;
      if (avgArea < 500 && imgR === 0) score -= 3;
      if (score < 3) continue;
      const fullSel = makeFullSel(parent, group[0]);
      if (!fullSel || seen.has(fullSel)) continue;
      seen.add(fullSel);
      let vc, visc;
      try { const els = document.querySelectorAll(fullSel); vc = els.length;
        visc = Array.from(els).filter(e => e.offsetParent !== null || e.getClientRects().length > 0).length;
      } catch(_) { continue; }
      if (vc < MIN_ITEMS) continue;
      const first = group[0];
      candidates.push({
        selector: fullSel, count: vc, visible: visc, score,
        sampleText: first.textContent.trim().substring(0, 80),
        sampleAttr: ((first.querySelector('a[href]')||{}).href||'').substring(0, 120),
        meta: { linkPct: Math.round(linkR*100), imgPct: Math.round(imgR*100),
                textPct: Math.round(textR*100), avgArea: Math.round(avgArea), childTag: group[0].tagName },
      });
    }
  }
  candidates.sort((a,b) => b.score - a.score || b.visible - a.visible);
  return candidates.slice(0, 20);
}
"""

AUTO_DISCOVER_INNER_JS = r"""
(containerSel) => {
  const items = Array.from(document.querySelectorAll(containerSel));
  if (!items.length) return {};
  const sample = items.slice(0, Math.min(8, items.length));
  const n = sample.length;
  function relSel(el, root) {
    if (el === root) return null;
    let tag = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const parts = el.className.trim().split(/\s+/).filter(c => c && !/[:()[\]{}=+~>^$|@!]/.test(c));
      if (parts.length) tag += '.' + parts.map(c => CSS.escape(c)).join('.');
    }
    return tag;
  }
  const linkMap={}, imgMap={}, durMap={}, viewMap={}, titleMap={};
  for (const item of sample) {
    item.querySelectorAll('a[href]').forEach(a => { const s=relSel(a,item)||'a'; linkMap[s]=(linkMap[s]||0)+1; });
    item.querySelectorAll('img').forEach(img => { const s=relSel(img,item)||'img'; imgMap[s]=(imgMap[s]||0)+1; });
    item.querySelectorAll('*').forEach(el => {
      const cls=(el.className||'').toString().toLowerCase();
      const txt=(el.textContent||'').trim();
      const sel=relSel(el,item);
      if(!sel) return;
      if(/\d{1,2}:\d{2}(:\d{2})?/.test(txt) && txt.length<15) durMap[sel]=(durMap[sel]||0)+1;
      if(/\d+[\d,.]*\s*(k|m|views|view|번|回)/i.test(txt) && txt.length<30) viewMap[sel]=(viewMap[sel]||0)+1;
      const isH=/^H[1-6]$/.test(el.tagName), isT=/title/i.test(cls);
      if((isH||isT) && txt.length>=3 && txt.length<=200) titleMap[sel]=(titleMap[sel]||0)+1;
    });
  }
  function best(map, minR) { minR=minR||0.4; let top=null,tc=0;
    for(const[s,c] of Object.entries(map)) { if(c/n>=minR && c>tc){top=s;tc=c;} } return top; }
  let mainLink=best(linkMap,0.6);
  if(!mainLink && linkMap['a']>=n*0.5) mainLink='a';
  let titleSel=best(titleMap,0.4);
  if(!titleSel){for(const h of ['h1','h2','h3','h4','h5','h6']){if(sample.filter(it=>it.querySelector(h)).length>=n*0.5){titleSel=h;break;}}}
  if(!titleSel && mainLink) titleSel=mainLink;
  return {
    title: titleSel, link: mainLink,
    thumbnail: best(imgMap,0.5)||(imgMap['img']>=n*0.3?'img':null),
    duration: best(durMap,0.3), views: best(viewMap,0.3),
  };
}
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🆕 Auto-Discover PAGINATION JS  (the big new piece)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AUTO_DISCOVER_PAGINATION_JS = r"""
() => {
  const results = [];
  
  /* ── helpers ── */
  function shortSel(el) {
    if (!el || el === document.documentElement || el === document.body) return null;
    if (el.id) return '#' + CSS.escape(el.id);
    let tag = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const parts = el.className.trim().split(/\s+/)
        .filter(c => c && !/[:()[\]{}=+~>^$|@!]/.test(c) && c.length < 40);
      if (parts.length) tag += '.' + parts.map(c => CSS.escape(c)).join('.');
    }
    return tag;
  }
  
  function fullPath(el) {
    // build a reasonably specific selector path
    const parts = [];
    let cur = el;
    let depth = 0;
    while (cur && cur !== document.body && depth < 4) {
      const s = shortSel(cur);
      if (s) parts.unshift(s);
      // if we hit an ID, stop — that's specific enough
      if (cur.id) break;
      cur = cur.parentElement;
      depth++;
    }
    return parts.join(' > ') || shortSel(el) || '';
  }
  
  function isVisible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && 
           (el.offsetParent !== null || el.getClientRects().length > 0);
  }

  /* ═══════════════════════════════════════════
     1. <link rel="next"> / <a rel="next">
     ═══════════════════════════════════════════ */
  const relNextLink = document.querySelector('link[rel="next"]');
  if (relNextLink) {
    results.push({
      type:       'rel_next_meta',
      selector:   'link[rel="next"]',
      confidence: 10,
      nextUrl:    relNextLink.href || relNextLink.getAttribute('href') || '',
      text:       '',
      visible:    false,
      method:     'meta',
    });
  }
  
  const relNextA = document.querySelector('a[rel="next"]');
  if (relNextA) {
    results.push({
      type:       'rel_next_link',
      selector:   fullPath(relNextA),
      confidence: 10,
      nextUrl:    relNextA.href || '',
      text:       relNextA.textContent.trim().substring(0, 30),
      visible:    isVisible(relNextA),
      method:     'click',
    });
  }

  /* ═══════════════════════════════════════════
     2. NUMBERED PAGINATION
     Cari container yg punya beberapa child dgn angka sequential
     ═══════════════════════════════════════════ */
  const pagContainers = document.querySelectorAll(
    'nav, ul, ol, div, footer, section, ' +
    '[class*="pag"], [class*="page"], [class*="pager"], ' +
    '[id*="pag"], [id*="page"], [role="navigation"]'
  );
  
  for (const container of pagContainers) {
    // get all clickable children (recursive)
    const clickables = container.querySelectorAll('a, button, [role="button"], li > span');
    const numbered = [];
    const others = [];
    
    for (const el of clickables) {
      const text = el.textContent.trim();
      if (/^\d{1,5}$/.test(text)) {
        numbered.push({ el, num: parseInt(text, 10) });
      } else {
        others.push({ el, text });
      }
    }
    
    if (numbered.length < 2) continue;
    
    // check sequential
    const nums = numbered.map(n => n.num).sort((a, b) => a - b);
    let seqCount = 0;
    for (let i = 1; i < nums.length; i++) {
      if (nums[i] - nums[i - 1] <= 2) seqCount++;
    }
    if (seqCount < 1) continue;
    
    // looks like pagination! build selector
    const sample = numbered[0].el;
    const containerSel = shortSel(container);
    const itemTag = sample.tagName.toLowerCase();
    
    // try building a good selector
    let pagSel = '';
    if (containerSel) {
      pagSel = containerSel + ' ' + itemTag;
      try {
        const test = document.querySelectorAll(pagSel);
        if (test.length < 2) pagSel = '';
      } catch(_) { pagSel = ''; }
    }
    if (!pagSel) pagSel = fullPath(sample);
    
    // find "next" page link
    let nextUrl = '';
    const currentPage = nums.find(n => {
      // the "active" / "current" page often has a different class
      const matchEl = numbered.find(x => x.num === n);
      if (!matchEl) return false;
      const el = matchEl.el;
      const cls = (el.className || '').toString().toLowerCase();
      const parentCls = (el.parentElement?.className || '').toString().toLowerCase();
      return /active|current|selected|on\b|disabled/i.test(cls + ' ' + parentCls);
    }) || nums[0];
    
    const nextNum = currentPage + 1;
    const nextEl = numbered.find(n => n.num === nextNum);
    if (nextEl) {
      nextUrl = nextEl.el.href || nextEl.el.getAttribute('data-url') || '';
    }
    
    let conf = 6;
    if (seqCount >= 3) conf += 2;
    if (numbered.length >= 5) conf += 1;
    if (/pag/i.test(containerSel)) conf += 1;
    conf = Math.min(conf, 10);
    
    results.push({
      type:       'numbered',
      selector:   pagSel,
      confidence: conf,
      nextUrl:    nextUrl,
      text:       nums.join(','),
      visible:    isVisible(sample),
      method:     sample.tagName === 'A' ? 'navigate' : 'click',
      pageCount:  Math.max(...nums),
      currentPage: currentPage,
    });
  }

  /* ═══════════════════════════════════════════
     3. NEXT / PREV BUTTONS  (multi-language)
     ═══════════════════════════════════════════ */
  const NEXT_PATTERNS = [
    /* English */
    /^next$/i, /^next\s*page$/i, /^next\s*»$/i,
    /^›$/,  /^»$/,  /^→$/,  /^▶$/,  /^>$/,  /^>>$/,
    /* Japanese */
    /次へ/,  /次のページ/,  /次ページ/,  /次の/,
    /* Korean */
    /다음/,  /다음\s*페이지/,
    /* Chinese */
    /下一[页頁]/,  /下一?頁/,  /后页/,
    /* French */
    /suivant/i,  /page\s*suivante/i,
    /* Spanish */
    /siguiente/i,
    /* German */
    /n[äa]chste/i,  /weiter/i,
    /* Portuguese */
    /pr[óo]xim/i,
    /* Dutch */
    /volgende/i,
    /* Italian */
    /successiv/i,  /prossim/i,
    /* Russian */
    /след/i,  /дальше/i,
    /* Arabic (text direction might differ) */
    /التالي/,
    /* Generic arrow/chevron text */
    /^next\b/i,
  ];
  
  const PREV_PATTERNS = [
    /^prev(ious)?$/i, /^‹$/, /^«$/, /^←$/, /^◀$/, /^<$/, /^<<$/,
    /前へ/, /前のページ/, /이전/, /上一[页頁]/, /précédent/i,
    /anterior/i, /vorherige/i, /vorige/i,
  ];
  
  // Scan ALL clickable elements on the page
  const allClickable = document.querySelectorAll(
    'a, button, [role="button"], [class*="btn"], ' +
    '[class*="next"], [class*="prev"], [class*="forward"], [class*="back"], ' +
    'input[type="button"], input[type="submit"], ' +
    '[class*="arrow"], [class*="chevron"], [class*="nav-"]'
  );
  
  for (const el of allClickable) {
    const text = el.textContent.trim();
    const ariaLabel = el.getAttribute('aria-label') || '';
    const title = el.getAttribute('title') || '';
    const cls = (el.className || '').toString();
    const combined = text + '|' + ariaLabel + '|' + title + '|' + cls;
    
    // Check class-based indicators too
    const classHasNext = /\bnext\b|forward|chevron.?right|arrow.?right/i.test(cls);
    
    let isNext = false;
    for (const p of NEXT_PATTERNS) {
      if (p.test(text) || p.test(ariaLabel) || p.test(title)) {
        isNext = true;
        break;
      }
    }
    if (!isNext && classHasNext && text.length < 20) isNext = true;
    
    if (!isNext) continue;
    
    // Avoid false positives: skip if inside video item container
    // (some video titles might contain "Next")
    if (el.closest('[class*="video-item"], [class*="thumb"], article')) continue;
    
    const sel = fullPath(el);
    if (!sel) continue;
    
    // Also try to build a robust selector
    let bestSel = sel;
    // If element has distinctive class
    if (/next/i.test(cls)) {
      const parts = cls.trim().split(/\s+/).filter(c => /next/i.test(c));
      if (parts.length) {
        const trySel = el.tagName.toLowerCase() + '.' + CSS.escape(parts[0]);
        try { if (document.querySelectorAll(trySel).length <= 3) bestSel = trySel; } catch(_){}
      }
    }
    // rel="next" already covered above, but add class-based
    if (el.getAttribute('rel') === 'next') continue; // already found
    
    results.push({
      type:       'next_button',
      selector:   bestSel,
      confidence: 8,
      nextUrl:    el.href || el.getAttribute('data-url') || el.getAttribute('data-href') || '',
      text:       text.substring(0, 30),
      visible:    isVisible(el),
      method:     el.tagName === 'A' && el.href ? 'navigate' : 'click',
    });
  }

  /* ═══════════════════════════════════════════
     4. LOAD MORE BUTTONS (multi-language)
     ═══════════════════════════════════════════ */
  const LOAD_MORE_PATTERNS = [
    /* English */
    /load\s*more/i,  /show\s*more/i,  /view\s*more/i,  /see\s*more/i,
    /see\s*all/i,    /more\s*videos/i, /more\s*results/i,
    /* Japanese */
    /もっと見る/,     /もっと読み込む/,  /さらに表示/,    /続きを見る/,
    /もっと表示/,     /追加読み込み/,    /さらに読み込む/,
    /* Korean */
    /더\s*보기/,      /더\s*불러오기/,   /더\s*읽기/,     /추가\s*로드/,
    /* Chinese */
    /加[载載]\s*更多/,  /查看更多/,      /显示更多/,      /載入更多/,
    /更多/,
    /* French */
    /voir\s*plus/i,   /charger\s*plus/i, /afficher\s*plus/i,
    /* Spanish */
    /cargar\s*m[áa]s/i, /ver\s*m[áa]s/i, /mostrar\s*m[áa]s/i,
    /* German */
    /mehr\s*(laden|anzeigen|zeigen)/i,
    /* Portuguese */
    /carregar\s*mais/i, /ver\s*mais/i,
    /* Dutch */
    /meer\s*(laden|tonen|weergeven)/i,
    /* Italian */
    /carica\s*(di\s*)?pi[ùu]/i, /mostra\s*(di\s*)?pi[ùu]/i,
    /* Russian */
    /показать\s*ещ[ёе]/i, /загрузить\s*ещ[ёе]/i, /ещ[ёе]/i,
    /* Turkish */
    /daha\s*fazla/i,
    /* Arabic */
    /عرض المزيد/,    /تحميل المزيد/,
    /* Generic */
    /^more$/i,
  ];
  
  // Also look via class/id names
  const loadMoreByAttr = document.querySelectorAll(
    '[class*="load-more"], [class*="loadmore"], [class*="load_more"], ' +
    '[class*="show-more"], [class*="showmore"], [class*="show_more"], ' +
    '[class*="view-more"], [id*="load-more"], [id*="loadmore"], ' +
    '[id*="show-more"], [data-action*="load"], [data-action*="more"]'
  );
  
  const loadMoreCandidates = new Set();
  
  // Text-based scan
  for (const el of allClickable) {
    const text = el.textContent.trim();
    if (text.length > 50) continue; // not a button
    for (const p of LOAD_MORE_PATTERNS) {
      if (p.test(text)) {
        loadMoreCandidates.add(el);
        break;
      }
    }
  }
  
  // Attribute-based scan
  for (const el of loadMoreByAttr) {
    loadMoreCandidates.add(el);
  }
  
  for (const el of loadMoreCandidates) {
    const sel = fullPath(el);
    if (!sel) continue;
    
    // try a cleaner selector via class
    let bestSel = sel;
    const cls = (el.className || '').toString();
    const loadClass = cls.trim().split(/\s+/).find(c => 
      /load|more|show/i.test(c)
    );
    if (loadClass) {
      const trySel = el.tagName.toLowerCase() + '.' + CSS.escape(loadClass);
      try { if (document.querySelectorAll(trySel).length <= 3) bestSel = trySel; } catch(_){}
    }
    
    results.push({
      type:       'load_more',
      selector:   bestSel,
      confidence: 8,
      nextUrl:    el.href || el.getAttribute('data-url') || '',
      text:       el.textContent.trim().substring(0, 40),
      visible:    isVisible(el),
      method:     'click',
    });
  }

  /* ═══════════════════════════════════════════
     5. INFINITE SCROLL DETECTION
     ═══════════════════════════════════════════ */
  
  // 5a. Sentinel/loader elements near bottom of page
  const sentinelCandidates = document.querySelectorAll(
    '[class*="sentinel"], [class*="infinite"], [class*="scroll-load"], ' +
    '[class*="scroll-trigger"], [class*="lazy-load"], [class*="auto-load"], ' +
    '[class*="loading-more"], [class*="load-trigger"], ' +
    '[data-infinite], [data-infinite-scroll], [data-scroll-load], ' +
    '[data-next-page], [data-load-more], ' +
    '[id*="sentinel"], [id*="infinite"], [id*="scroll-load"], ' +
    '[id*="scroll-trigger"]'
  );
  
  const docHeight = document.documentElement.scrollHeight;
  const viewHeight = window.innerHeight;
  
  for (const el of sentinelCandidates) {
    const rect = el.getBoundingClientRect();
    const absTop = rect.top + window.scrollY;
    // is it in the lower half of the page?
    if (absTop > docHeight * 0.4) {
      results.push({
        type:       'infinite_scroll_sentinel',
        selector:   fullPath(el),
        confidence: 7,
        nextUrl:    el.getAttribute('data-next-page') || el.getAttribute('data-url') || '',
        text:       el.textContent.trim().substring(0, 30),
        visible:    isVisible(el),
        method:     'scroll',
      });
    }
  }
  
  // 5b. Check for loading spinners near bottom (common pattern)
  const spinners = document.querySelectorAll(
    '[class*="spinner"], [class*="loading"], [class*="loader"], ' +
    '.lds-ring, .lds-dual-ring, .sk-spinner, [class*="spin"]'
  );
  for (const el of spinners) {
    const rect = el.getBoundingClientRect();
    const absTop = rect.top + window.scrollY;
    if (absTop > docHeight * 0.6) {
      // check if it's hidden (most spinners are hidden until triggered)
      const style = window.getComputedStyle(el);
      const hidden = style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0';
      results.push({
        type:       'infinite_scroll_spinner',
        selector:   fullPath(el),
        confidence: hidden ? 6 : 4,  // hidden spinner = more likely pagination
        nextUrl:    '',
        text:       '(loading spinner)',
        visible:    !hidden,
        method:     'scroll',
      });
    }
  }
  
  // 5c. Check for data-page / data-next attributes on the main container
  const dataPageEls = document.querySelectorAll(
    '[data-page], [data-current-page], [data-total-pages], ' +
    '[data-next-page-url], [data-pagination], ' +
    '[data-paging], [data-paginate]'
  );
  for (const el of dataPageEls) {
    const attrs = {};
    for (const attr of el.attributes) {
      if (/page|pag|next|total/i.test(attr.name)) {
        attrs[attr.name] = attr.value;
      }
    }
    results.push({
      type:       'data_attribute',
      selector:   fullPath(el),
      confidence: 7,
      nextUrl:    el.getAttribute('data-next-page-url') || el.getAttribute('data-next') || '',
      text:       JSON.stringify(attrs).substring(0, 80),
      visible:    isVisible(el),
      method:     'data_attr',
      meta:       attrs,
    });
  }

  /* ═══════════════════════════════════════════
     6. URL PATTERN ANALYSIS
     ═══════════════════════════════════════════ */
  const url = window.location.href;
  const urlPatterns = [
    { re: /([?&])page=(\d+)/,    param: 'page',   type: 'query' },
    { re: /([?&])p=(\d+)/,       param: 'p',      type: 'query' },
    { re: /([?&])offset=(\d+)/,  param: 'offset', type: 'query' },
    { re: /([?&])start=(\d+)/,   param: 'start',  type: 'query' },
    { re: /([?&])from=(\d+)/,    param: 'from',   type: 'query' },
    { re: /([?&])skip=(\d+)/,    param: 'skip',   type: 'query' },
    { re: /([?&])cursor=([^&]+)/,param: 'cursor', type: 'query' },
    { re: /\/page\/(\d+)/,       param: 'page',   type: 'path' },
    { re: /\/p\/(\d+)/,          param: 'p',      type: 'path' },
  ];
  
  for (const pat of urlPatterns) {
    const m = url.match(pat.re);
    if (m) {
      const val = m[m.length - 1]; // last capture group
      results.push({
        type:       'url_pattern',
        selector:   '',
        confidence: 6,
        nextUrl:    '',
        text:       `URL has ${pat.param}=${val} (${pat.type})`,
        visible:    false,
        method:     'url_increment',
        urlPattern: { param: pat.param, currentValue: val, type: pat.type },
      });
    }
  }

  /* ═══════════════════════════════════════════
     7. JAVASCRIPT FRAMEWORK INDICATORS
     (React/Vue/Angular router pagination)
     ═══════════════════════════════════════════ */
  const spaIndicators = [];
  if (window.__NEXT_DATA__)     spaIndicators.push('nextjs');
  if (window.__NUXT__)          spaIndicators.push('nuxt');
  if (document.querySelector('[data-reactroot], [id="__next"]'))  spaIndicators.push('react');
  if (document.querySelector('[data-v-], [data-vue]'))            spaIndicators.push('vue');
  if (document.querySelector('[ng-app], [data-ng-app], [_nghost]')) spaIndicators.push('angular');
  
  if (spaIndicators.length) {
    results.push({
      type:       'spa_framework',
      selector:   '',
      confidence: 3,
      nextUrl:    '',
      text:       'SPA detected: ' + spaIndicators.join(', '),
      visible:    false,
      method:     'spa',
      meta:       { frameworks: spaIndicators },
    });
  }

  /* ═══ de-duplicate & sort ═══ */
  const seen = new Set();
  const unique = [];
  for (const r of results) {
    const key = r.type + '|' + r.selector;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(r);
  }
  unique.sort((a, b) => b.confidence - a.confidence);
  return unique;
}
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Data Classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class SelectorMatch:
    selector: str
    count: int = 0
    visible: int = 0
    confidence: int = 1
    sample_text: Optional[str] = None
    sample_attr: Optional[str] = None
    source: str = "static"


@dataclass
class PaginationInfo:
    """One detected pagination mechanism."""
    ptype: str  # numbered | next_button | load_more | infinite_scroll_sentinel |
                # infinite_scroll_spinner | data_attribute | url_pattern |
                # rel_next_meta | rel_next_link | spa_framework
    selector: str = ""
    confidence: int = 0
    next_url: str = ""
    text: str = ""
    is_visible: bool = False
    method: str = ""  # navigate | click | scroll | url_increment | meta | data_attr | spa
    source: str = "auto"
    url_pattern: Optional[Dict] = None  # {param, currentValue, type}
    meta: Optional[Dict] = None
    page_count: Optional[int] = None
    current_page: Optional[int] = None

    @property
    def actionable(self) -> bool:
        """Can we actually use this for pagination?"""
        return self.method in ("navigate", "click", "scroll", "url_increment") and (
            bool(self.selector) or bool(self.next_url)
        )

    @property
    def type_emoji(self) -> str:
        return {
            "numbered":                  "🔢",
            "next_button":               "➡️",
            "load_more":                 "📥",
            "infinite_scroll_sentinel":  "♾️",
            "infinite_scroll_spinner":   "🔄",
            "data_attribute":            "📊",
            "url_pattern":               "🔗",
            "rel_next_meta":             "🏷️",
            "rel_next_link":             "🏷️",
            "spa_framework":             "⚛️",
        }.get(self.ptype, "❓")

    @property
    def type_label(self) -> str:
        return {
            "numbered":                  "Numbered Pages",
            "next_button":               "Next Button",
            "load_more":                 "Load More Button",
            "infinite_scroll_sentinel":  "Infinite Scroll (sentinel)",
            "infinite_scroll_spinner":   "Infinite Scroll (spinner)",
            "data_attribute":            "Data Attributes",
            "url_pattern":               "URL Pattern",
            "rel_next_meta":             "Meta rel=next",
            "rel_next_link":             "Link rel=next",
            "spa_framework":             "SPA Framework",
        }.get(self.ptype, self.ptype)


@dataclass
class AnalysisResult:
    url: str
    domain: str
    final_url: str = ""
    page_title: str = ""
    containers: List[SelectorMatch] = field(default_factory=list)
    titles: List[SelectorMatch] = field(default_factory=list)
    links: List[SelectorMatch] = field(default_factory=list)
    thumbnails: List[SelectorMatch] = field(default_factory=list)
    durations: List[SelectorMatch] = field(default_factory=list)
    views: List[SelectorMatch] = field(default_factory=list)
    pagination_static: List[SelectorMatch] = field(default_factory=list)
    pagination_info: List[PaginationInfo] = field(default_factory=list)
    ajax_requests: List[Dict] = field(default_factory=list)
    error: Optional[str] = None
    error_type: Optional[str] = None

    @property
    def best_container(self) -> Optional[str]:
        return self.containers[0].selector if self.containers else None

    @property
    def best_title(self) -> Optional[str]:
        return self.titles[0].selector if self.titles else None

    @property
    def best_link(self) -> Optional[str]:
        return self.links[0].selector if self.links else None

    @property
    def best_thumbnail(self) -> Optional[str]:
        return self.thumbnails[0].selector if self.thumbnails else None

    @property
    def best_duration(self) -> Optional[str]:
        return self.durations[0].selector if self.durations else None

    @property
    def best_views(self) -> Optional[str]:
        return self.views[0].selector if self.views else None

    @property
    def best_pagination(self) -> Optional[PaginationInfo]:
        """Return the best actionable pagination."""
        for p in self.pagination_info:
            if p.actionable:
                return p
        # fallback to static
        if self.pagination_static:
            return PaginationInfo(
                ptype="numbered",
                selector=self.pagination_static[0].selector,
                confidence=self.pagination_static[0].confidence,
                method="navigate",
                source="static",
            )
        return None

    @property
    def best_pagination_selector(self) -> Optional[str]:
        bp = self.best_pagination
        return bp.selector if bp else None

    @property
    def pagination_type(self) -> str:
        bp = self.best_pagination
        return bp.ptype if bp else "none"

    @property
    def is_valid(self) -> bool:
        return bool(self.containers and self.links)

    @property
    def has_pagination(self) -> bool:
        return bool(self.pagination_info or self.pagination_static)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  URL Normalizer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def normalize_url(url: str) -> List[str]:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    variants = set()
    paths = [parsed.path]
    if parsed.path.endswith("/"):
        paths.append(parsed.path.rstrip("/") or "/")
    else:
        paths.append(parsed.path + "/")
    netlocs = [parsed.netloc]
    if parsed.netloc.startswith("www."):
        netlocs.append(parsed.netloc[4:])
    else:
        netlocs.append("www." + parsed.netloc)
    for netloc in netlocs:
        for path in paths:
            variants.add(urlunparse(parsed._replace(netloc=netloc, path=path)))
    result = []
    with_slash = urlunparse(
        parsed._replace(path=parsed.path.rstrip("/") + "/" if parsed.path else "/")
    )
    if with_slash in variants:
        result.append(with_slash)
        variants.discard(with_slash)
    if url in variants:
        result.append(url)
        variants.discard(url)
    result.extend(sorted(variants))
    return result


def classify_error(error_msg: str) -> tuple:
    msg = str(error_msg).upper()
    if "ERR_NAME_NOT_RESOLVED" in msg or "NXDOMAIN" in msg:
        return ("dns", "DNS resolution failed.")
    if "ERR_CONNECTION_RESET" in msg or "ERR_CONNECTION_REFUSED" in msg:
        return ("blocked", "Connection blocked.")
    if "TIMEOUT" in msg:
        return ("timeout", "Connection timeout.")
    return ("unknown", f"Error: {error_msg[:150]}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CSVScout
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class CSVScout:
    def __init__(self, proxy: Optional[str] = None, headless: bool = True):
        self._proxy = proxy
        self._headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._final_url: str = ""

    async def __aenter__(self):
        await self._start()
        return self

    async def __aexit__(self, *args):
        await self._close()

    async def _start(self):
        self._playwright = await async_playwright().start()
        launch = {"headless": self._headless, "args": BROWSER_ARGS}
        if self._proxy:
            launch["proxy"] = {"server": self._proxy}
        self._browser = await self._playwright.chromium.launch(**launch)
        self._context = await self._browser.new_context(
            viewport=VIEWPORT,
            user_agent=random.choice(USER_AGENTS),
            locale="en-US",
            bypass_csp=True,
            ignore_https_errors=True,
        )
        await self._context.add_init_script(STEALTH_SCRIPTS)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(60_000)

    async def _close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _navigate(self, url: str) -> tuple:
        url_variants = normalize_url(url)
        print(f"   📡 Trying {len(url_variants)} URL variants...")
        last_error = None
        for try_url in url_variants:
            for strategy, timeout in NAVIGATION_STRATEGIES:
                try:
                    print(f"   → {try_url} ({strategy})")
                    resp = await self._page.goto(
                        try_url, wait_until=strategy, timeout=timeout
                    )
                    if resp and resp.status < 400:
                        self._final_url = try_url
                        print(f"   ✅ Success: {try_url}")
                        return (True, None)
                except Exception as exc:
                    last_error = str(exc)
                    upper = last_error.upper()
                    if any(p in upper for p in [
                        "ERR_NAME_NOT_RESOLVED",
                        "ERR_CONNECTION_RESET",
                        "ERR_CONNECTION_REFUSED",
                    ]):
                        break
                    continue
        return (False, last_error)

    async def _scroll_page(self) -> None:
        for _ in range(SCROLL_COUNT):
            await self._page.evaluate(
                f"window.scrollBy(0, {random.randint(300, 800)})"
            )
            await asyncio.sleep(SCROLL_DELAY + random.random() * 0.5)
        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

    # ── static selector scan ──

    async def _find_selectors(
        self,
        candidates: List[tuple],
        context: Optional[str] = None,
        min_count: int = 1,
    ) -> List[SelectorMatch]:
        results = []
        for selector, confidence in candidates:
            try:
                full = f"{context} {selector}" if context else selector
                info = await self._page.evaluate(
                    """(sel) => {
                        const els = document.querySelectorAll(sel);
                        if (!els.length) return null;
                        let vis=0,st='',sa='';
                        els.forEach((e,i) => {
                            if (e.offsetParent!==null||e.getClientRects().length) vis++;
                            if (i===0) {
                                st=(e.textContent||'').trim().substring(0,60);
                                sa=e.getAttribute('href')||e.getAttribute('src')||e.getAttribute('data-src')||'';
                            }
                        });
                        return {count:els.length, visible:vis, st, sa:sa.substring(0,100)};
                    }""",
                    full,
                )
                if info and info["count"] >= min_count:
                    results.append(SelectorMatch(
                        selector=selector,
                        count=info["count"],
                        visible=info["visible"],
                        confidence=confidence,
                        sample_text=info["st"] or None,
                        sample_attr=info["sa"] or None,
                        source="static",
                    ))
            except Exception:
                continue
        results.sort(
            key=lambda m: (m.confidence * (1 if m.visible else 0.3), m.count),
            reverse=True,
        )
        return results

    # ── container auto-discovery ──

    async def _auto_discover_containers(self) -> List[SelectorMatch]:
        print("   🔬 Auto-discovering containers …")
        try:
            raw = await self._page.evaluate(AUTO_DISCOVER_JS)
        except Exception as exc:
            print(f"   ⚠️ Auto-discover error: {exc}")
            return []
        if not raw:
            return []
        matches = []
        for r in raw:
            matches.append(SelectorMatch(
                selector=r["selector"], count=r["count"], visible=r["visible"],
                confidence=r["score"],
                sample_text=r.get("sampleText"),
                sample_attr=r.get("sampleAttr"),
                source="auto",
            ))
        print(f"   🔬 Found {len(matches)} auto container candidates")
        for m in matches[:5]:
            print(f"      [{m.confidence:2d}] {m.selector}: {m.count}/{m.visible}")
        return matches

    async def _auto_discover_inner(self, container_sel: str) -> Dict:
        print(f"   🔬 Auto-discovering inner selectors in: {container_sel}")
        try:
            raw = await self._page.evaluate(AUTO_DISCOVER_INNER_JS, container_sel)
        except Exception as exc:
            print(f"   ⚠️ Inner discover error: {exc}")
            return {}
        if not raw:
            return {}
        for field_name in ("title", "link", "thumbnail", "duration", "views"):
            val = raw.get(field_name)
            print(f"      {field_name:12s} → {val or '(not found)'}")
        return raw

    def _inner_to_matches(
        self, inner: Dict, field_name: str, static_results: List[SelectorMatch]
    ) -> List[SelectorMatch]:
        merged = list(static_results)
        sel = inner.get(field_name)
        if sel:
            existing = {m.selector for m in merged}
            if sel not in existing:
                merged.insert(0, SelectorMatch(
                    selector=sel, count=0, visible=0,
                    confidence=8, source="auto",
                ))
        return merged

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  🆕 PAGINATION DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _detect_pagination(self) -> tuple:
        """
        Returns (List[SelectorMatch], List[PaginationInfo])
        Phase A: static selectors
        Phase B: auto-discover (JS DOM scan)
        Phase C: AJAX interception (scroll & capture network)
        """
        # ── Phase A: Static ──
        print("\n   📑 Pagination Phase A: Static selectors")
        static = await self._find_selectors(PAGINATION_CANDIDATES_STATIC)
        if static:
            print(f"      Found {len(static)} static matches")
            for s in static[:3]:
                print(f"      [{s.confidence:2d}] {s.selector}: {s.count}")
        else:
            print("      (none)")

        # ── Phase B: Auto-discover ──
        print("   📑 Pagination Phase B: Auto-discovery (DOM scan)")
        pag_info = []
        try:
            raw = await self._page.evaluate(AUTO_DISCOVER_PAGINATION_JS)
            if raw:
                for r in raw:
                    pi = PaginationInfo(
                        ptype=r.get("type", "unknown"),
                        selector=r.get("selector", ""),
                        confidence=r.get("confidence", 0),
                        next_url=r.get("nextUrl", ""),
                        text=r.get("text", ""),
                        is_visible=r.get("visible", False),
                        method=r.get("method", ""),
                        source="auto",
                        url_pattern=r.get("urlPattern"),
                        meta=r.get("meta"),
                        page_count=r.get("pageCount"),
                        current_page=r.get("currentPage"),
                    )
                    pag_info.append(pi)
                print(f"      Found {len(pag_info)} pagination mechanisms")
            else:
                print("      (none)")
        except Exception as exc:
            print(f"      ⚠️ Error: {exc}")

        # ── Phase C: AJAX interception ──
        print("   📑 Pagination Phase C: AJAX interception (scroll)")
        ajax = await self._intercept_scroll_requests()

        return static, pag_info, ajax

    async def _intercept_scroll_requests(self) -> List[Dict]:
        """
        Scroll down dan capture semua XHR/fetch request
        yang terlihat seperti pagination/data loading.
        """
        captured: List[Dict] = []

        # Keywords yang menandakan request ini adalah data/pagination
        DATA_KEYWORDS = (
            "page", "offset", "limit", "skip", "cursor", "after",
            "load", "list", "video", "ajax", "api", "fetch",
            "scroll", "more", "next", "content", "feed",
            "search", "result", "data", "json",
        )

        # Ekstensi yang bukan data
        SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
                     ".css", ".js", ".woff", ".woff2", ".ttf", ".ico")

        def on_request(request: Request):
            if request.resource_type not in ("xhr", "fetch"):
                return
            url = request.url.lower()

            # skip static assets
            if any(url.endswith(ext) for ext in SKIP_EXT):
                return

            # check if URL contains data keywords
            has_keyword = any(kw in url for kw in DATA_KEYWORDS)

            # check content-type expectations
            headers = request.headers
            accept = headers.get("accept", "")
            is_json = "json" in accept or "json" in url

            if has_keyword or is_json:
                entry = {
                    "url": request.url[:200],
                    "method": request.method,
                    "type": request.resource_type,
                    "post_data": None,
                }
                if request.method == "POST":
                    try:
                        entry["post_data"] = request.post_data[:200] if request.post_data else None
                    except Exception:
                        pass
                captured.append(entry)

        # Record initial count of items (to detect if new content loaded)
        initial_height = await self._page.evaluate(
            "document.documentElement.scrollHeight"
        )

        self._page.on("request", on_request)

        try:
            # Scroll to bottom gradually
            for i in range(5):
                await self._page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1.5)

            # Also try clicking "load more" if visible
            # (don't actually click — just detecting here)

        finally:
            self._page.remove_listener("request", on_request)

        new_height = await self._page.evaluate(
            "document.documentElement.scrollHeight"
        )
        height_changed = new_height > initial_height * 1.1

        if captured:
            print(f"      Captured {len(captured)} AJAX requests:")
            for c in captured[:5]:
                print(f"         {c['method']} {c['url'][:80]}")
            if height_changed:
                print(f"      📈 Page height grew: {initial_height} → {new_height} (infinite scroll likely)")
        elif height_changed:
            print(f"      📈 Page height grew but no AJAX captured (might be CSS/lazy)")
        else:
            print("      (no AJAX data requests detected)")

        # If height changed significantly, add an infinite scroll indicator
        if height_changed and not captured:
            # Content grew without detectable AJAX — might be
            # deferred rendering or very fast API calls we missed
            pass

        return captured

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Main analyze()
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def analyze(self, url: str) -> AnalysisResult:
        result = AnalysisResult(
            url=url,
            domain=urlparse(url).netloc or urlparse("https://" + url).netloc,
        )
        print(f"\n🔍 Analyzing: {url}")
        success, error_msg = await self._navigate(url)
        if not success:
            et, um = classify_error(error_msg or "Unknown")
            result.error = um
            result.error_type = et
            return result

        result.final_url = self._final_url
        await asyncio.sleep(2)
        result.page_title = await self._safe_title()
        await self._scroll_page()
        await asyncio.sleep(1)

        # ═══ CONTAINERS ═══
        print("\n   📋 Phase 1: Static container scan")
        result.containers = await self._find_selectors(CONTAINER_CANDIDATES, min_count=3)

        print("\n   📋 Phase 2: Auto-discover containers")
        auto_c = await self._auto_discover_containers()
        existing = {m.selector for m in result.containers}
        for ac in auto_c:
            if ac.selector not in existing:
                result.containers.append(ac)
        result.containers.sort(
            key=lambda m: (m.confidence * (1 if m.visible else 0.3), m.count),
            reverse=True,
        )

        # ═══ SUB-ELEMENTS ═══
        ctx = result.best_container
        print(f"\n   📋 Phase 3: Sub-elements (ctx={ctx})")
        result.titles = await self._find_selectors(TITLE_CANDIDATES, context=ctx)
        result.links = await self._find_selectors(LINK_CANDIDATES, context=ctx)
        result.thumbnails = await self._find_selectors(THUMBNAIL_CANDIDATES, context=ctx)
        result.durations = await self._find_selectors(DURATION_CANDIDATES, context=ctx)
        result.views = await self._find_selectors(VIEWS_CANDIDATES, context=ctx)

        if ctx:
            print(f"\n   📋 Phase 4: Auto-discover inner elements")
            inner = await self._auto_discover_inner(ctx)
            if inner:
                result.titles = self._inner_to_matches(inner, "title", result.titles)
                result.links = self._inner_to_matches(inner, "link", result.links)
                result.thumbnails = self._inner_to_matches(inner, "thumbnail", result.thumbnails)
                result.durations = self._inner_to_matches(inner, "duration", result.durations)
                result.views = self._inner_to_matches(inner, "views", result.views)

        # ═══ PAGINATION (comprehensive) ═══
        static_pag, pag_info, ajax = await self._detect_pagination()
        result.pagination_static = static_pag
        result.pagination_info = pag_info
        result.ajax_requests = ajax

        # If AJAX requests found during scroll, add as pagination info
        if ajax:
            # Find the most likely "data" endpoint
            scored: List[tuple] = []
            for req in ajax:
                url_lower = req["url"].lower()
                score = 0
                if "page" in url_lower or "offset" in url_lower:
                    score += 5
                if "video" in url_lower or "list" in url_lower:
                    score += 3
                if "api" in url_lower:
                    score += 2
                if "json" in url_lower or req["method"] == "POST":
                    score += 2
                scored.append((score, req))

            scored.sort(key=lambda x: x[0], reverse=True)
            if scored:
                best_req = scored[0][1]
                result.pagination_info.append(PaginationInfo(
                    ptype="api_ajax",
                    selector="",
                    confidence=scored[0][0],
                    next_url=best_req["url"],
                    text=f"{best_req['method']} {best_req['url'][:60]}",
                    is_visible=False,
                    method="api_call",
                    source="intercepted",
                    meta=best_req,
                ))

        # Re-sort pagination_info
        result.pagination_info.sort(key=lambda p: p.confidence, reverse=True)

        return result

    async def _safe_title(self) -> str:
        try:
            return await self._page.title() or ""
        except Exception:
            return ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Code Generator (pagination-aware)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def generate_adapter_code(result: AnalysisResult) -> str:
    domain = result.domain.replace("www.", "")
    domain_snake = re.sub(r"[^a-zA-Z0-9]", "_", domain)
    class_name = "".join(w.capitalize() for w in domain_snake.split("_") if w) + "Adapter"

    container = result.best_container or ".videos article"
    title = result.best_title or ".title"
    link = result.best_link or "a"
    thumb = result.best_thumbnail or "img"
    duration = result.best_duration or ".duration"
    views = result.best_views or ".views"

    bp = result.best_pagination
    pag_type = bp.ptype if bp else "none"
    pag_selector = bp.selector if bp else ".pagination a"
    pag_method = bp.method if bp else "navigate"
    pag_next_url = bp.next_url if bp else ""

    # Decide pagination strategy code
    if pag_type in ("load_more",):
        pag_strategy = "load_more"
        pag_code = f'''
    PAGINATION_TYPE = "load_more"
    LOAD_MORE_SELECTOR = "{pag_selector}"

    async def go_next_page(self, page):
        """Click the load-more button and wait for new content."""
        btn = page.locator(self.LOAD_MORE_SELECTOR)
        if await btn.count() > 0 and await btn.first.is_visible():
            await btn.first.click()
            await page.wait_for_timeout(2000)
            return True
        return False
'''
    elif pag_type in ("infinite_scroll_sentinel", "infinite_scroll_spinner"):
        pag_strategy = "infinite_scroll"
        pag_code = f'''
    PAGINATION_TYPE = "infinite_scroll"
    SENTINEL_SELECTOR = "{pag_selector}"

    async def go_next_page(self, page):
        """Scroll to bottom to trigger infinite loading."""
        prev_count = await page.evaluate(
            "(sel) => document.querySelectorAll(sel).length",
            self.CONTAINER_SELECTOR,
        )
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)
        new_count = await page.evaluate(
            "(sel) => document.querySelectorAll(sel).length",
            self.CONTAINER_SELECTOR,
        )
        return new_count > prev_count
'''
    elif pag_type == "api_ajax" and bp and bp.meta:
        pag_strategy = "api"
        api_url = bp.meta.get("url", "") if bp.meta else ""
        api_method = bp.meta.get("method", "GET") if bp.meta else "GET"
        pag_code = f'''
    PAGINATION_TYPE = "api"
    API_ENDPOINT = "{api_url[:120]}"
    API_METHOD = "{api_method}"

    async def go_next_page(self, page):
        """Fetch next page via API."""
        # TODO: Implement API-based pagination
        # Modify page/offset parameter in self.API_ENDPOINT
        raise NotImplementedError("API pagination — customize for this site")
'''
    elif pag_type == "url_pattern" and bp and bp.url_pattern:
        param = bp.url_pattern.get("param", "page")
        pag_strategy = "url_pattern"
        pag_code = f'''
    PAGINATION_TYPE = "url_pattern"
    PAGE_PARAM = "{param}"

    def get_page_url(self, base_url: str, page_num: int) -> str:
        """Build URL for given page number."""
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query)
        params[self.PAGE_PARAM] = [str(page_num)]
        return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
'''
    elif pag_type == "next_button":
        pag_strategy = "next_button"
        pag_code = f'''
    PAGINATION_TYPE = "next_button"
    NEXT_BUTTON_SELECTOR = "{pag_selector}"

    async def go_next_page(self, page):
        """Click the Next button."""
        btn = page.locator(self.NEXT_BUTTON_SELECTOR)
        if await btn.count() > 0 and await btn.first.is_visible():
            await btn.first.click()
            await page.wait_for_load_state("domcontentloaded")
            return True
        return False
'''
    else:
        # Traditional numbered pagination
        pag_strategy = "numbered"
        pag_code = f'''
    PAGINATION_TYPE = "numbered"
    PAGINATION_SELECTOR = "{pag_selector}"
'''

    return f'''"""Adapter for {domain}. Auto-generated by CSVScout v3."""

from typing import List, Dict
from .. import BaseAdapter, AdapterRegistry


@AdapterRegistry.register
class {class_name}(BaseAdapter):
    """Adapter for {domain}."""

    DOMAINS = ["{domain}", "www.{domain}"]

    CONTAINER_SELECTOR  = "{container}"
    TITLE_SELECTOR      = "{title}"
    LINK_SELECTOR       = "{link}"
    THUMBNAIL_SELECTOR  = "{thumb}"
    DURATION_SELECTOR   = "{duration}"
    VIEWS_SELECTOR      = "{views}"
{pag_code}

    async def extract_videos(self, page) -> List[Dict]:
        """Extract video list from current page."""
        return await page.evaluate(
            """(s) => {{
                const results = [];
                document.querySelectorAll(s.container).forEach(item => {{
                    const t = item.querySelector(s.title);
                    const l = item.querySelector(s.link);
                    const i = item.querySelector(s.thumbnail);
                    const d = item.querySelector(s.duration);
                    const v = item.querySelector(s.views);
                    if (t || l) results.push({{
                        title: t ? t.textContent.trim() : '',
                        link: l ? l.href : '',
                        thumbnail: i ? (i.src || i.dataset.src || '') : '',
                        duration: d ? d.textContent.trim() : '',
                        views: v ? v.textContent.trim() : '',
                    }});
                }});
                return results;
            }}""",
            {{
                "container": self.CONTAINER_SELECTOR,
                "title":     self.TITLE_SELECTOR,
                "link":      self.LINK_SELECTOR,
                "thumbnail": self.THUMBNAIL_SELECTOR,
                "duration":  self.DURATION_SELECTOR,
                "views":     self.VIEWS_SELECTOR,
            }},
        )
'''


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Report
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def print_report(result: AnalysisResult) -> None:
    bar = "=" * 62

    print(f"\n{bar}")
    print(f"📊  CSV Scout Analysis: {result.domain}")
    print(bar)
    print(f"   URL:       {result.url}")
    if result.final_url and result.final_url != result.url:
        print(f"   Final URL: {result.final_url}")
    print(f"   Title:     {result.page_title[:50] if result.page_title else '(none)'}")

    if result.error:
        print(f"\n❌ Error [{result.error_type}]: {result.error}")
        print(bar)
        return

    # ── Content sections ──
    sections = [
        ("📦 Containers", result.containers),
        ("📝 Titles", result.titles),
        ("🔗 Links", result.links),
        ("🖼️  Thumbnails", result.thumbnails),
        ("⏱️  Durations", result.durations),
        ("👁️  Views", result.views),
    ]

    for name, matches in sections:
        print(f"\n{name} ({len(matches)}):")
        if not matches:
            print("   ⚠️  None found")
            continue
        for m in matches[:5]:
            vis = "✅" if m.visible else "👻"
            src = f" [{m.source}]" if m.source == "auto" else ""
            sample = ""
            if m.sample_text:
                sample = f' → "{m.sample_text[:30]}"'
            elif m.sample_attr:
                sample = f" → {m.sample_attr[:30]}"
            print(f"   {vis} [{m.confidence:2d}] {m.selector}: {m.count}/{m.visible}{sample}{src}")

    # ── Pagination (comprehensive) ──
    print(f"\n{'─' * 62}")
    print(f"📑 PAGINATION ANALYSIS")
    print(f"{'─' * 62}")

    # Static
    if result.pagination_static:
        print(f"\n   Static selectors ({len(result.pagination_static)}):")
        for s in result.pagination_static[:3]:
            vis = "✅" if s.visible else "👻"
            print(f"      {vis} [{s.confidence:2d}] {s.selector}: {s.count}")

    # Auto-discovered
    if result.pagination_info:
        print(f"\n   Detected mechanisms ({len(result.pagination_info)}):")
        for p in result.pagination_info:
            vis = "✅" if p.is_visible else "👻"
            act = "🎯" if p.actionable else "📌"
            extra = ""
            if p.next_url:
                extra += f"\n         next → {p.next_url[:60]}"
            if p.page_count:
                extra += f" | pages: {p.current_page or '?'}/{p.page_count}"
            if p.url_pattern:
                extra += f"\n         pattern: {p.url_pattern}"
            if p.text and p.ptype not in ("url_pattern",):
                extra += f'\n         text: "{p.text[:50]}"'

            print(
                f"      {p.type_emoji} {act} [{p.confidence:2d}] "
                f"{p.type_label} ({p.method})"
                f"{' | ' + p.selector[:45] if p.selector else ''}"
                f"{extra}"
            )
    else:
        if not result.pagination_static:
            print("\n   ⚠️  No pagination detected at all")

    # AJAX
    if result.ajax_requests:
        print(f"\n   🌐 AJAX requests captured ({len(result.ajax_requests)}):")
        for r in result.ajax_requests[:5]:
            print(f"      {r['method']} {r['url'][:70]}")

    # Best pagination summary
    bp = result.best_pagination
    if bp:
        print(f"\n   🏆 Best: {bp.type_emoji} {bp.type_label}")
        print(f"      Method:   {bp.method}")
        if bp.selector:
            print(f"      Selector: {bp.selector}")
        if bp.next_url:
            print(f"      Next URL: {bp.next_url[:70]}")
    else:
        print(f"\n   ⚠️  No actionable pagination found")
        print(f"      💡 Site might use:")
        print(f"         • client-side routing (SPA)")
        print(f"         • WebSocket updates")
        print(f"         • manual URL editing (?page=2)")

    # ── Final verdict ──
    print(f"\n{'─' * 62}")
    valid = result.is_valid
    has_pag = result.has_pagination
    print(f"   Content: {'✅ Valid' if valid else '⚠️  Invalid'}")
    print(f"   Pagination: {'✅ Detected' if has_pag else '⚠️  Not detected'}")
    if has_pag and bp:
        print(f"   Strategy: {bp.ptype} → {bp.method}")
    print(bar)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def run_scout(
    url: str,
    save: bool = True,
    proxy: Optional[str] = None,
    headless: bool = True,
) -> AnalysisResult:

    print(f"\n{'=' * 62}")
    print("🎯  CSV GETTER SCOUT v3")
    print("   (auto-discovery + modern pagination detection)")
    print(f"{'=' * 62}")

    async with CSVScout(proxy=proxy, headless=headless) as scout:
        result = await scout.analyze(url)

    print_report(result)

    if result.error:
        return result

    code = generate_adapter_code(result)

    print(f"\n{'=' * 62}")
    print("📄  Generated Code:")
    print(f"{'=' * 62}\n")
    print(code)

    if save and result.is_valid:
        domain_file = re.sub(
            r"[^a-zA-Z0-9]", "_", result.domain.replace("www.", "")
        )
        output_path = Path(f"csv_getter/adapters/domains/{domain_file}.py")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code, encoding="utf-8")
        print(f"\n💾  Saved: {output_path}")

    print(f"{'=' * 62}\n")
    return result