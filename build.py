"""Turn data/books.json into the single-file dashboard in dist/.

Everything the page needs is baked in, jackets included: a published page is
not allowed to fetch images from the presses' own servers, so the small ones
travel with it as data URIs and the full-resolution one is asked for only
where the page is allowed to have it. Under all of that sits a typographic
jacket, so a book with no cover posted yet still presents itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from presses import PRESSES

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "books.json"
COVERS = HERE / "data" / "covers.json"
PICKS = HERE / "data" / "picks.json"
OUT = HERE / "dist" / "the-season-ahead.html"

TEMPLATE = r"""<meta charset="utf-8">
<title>The Season Ahead</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,500;0,7..72,600;1,7..72,400&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* ---------------------------------------------------------------- tokens */
:root{
  --paper:#EDEDE8;      /* uncoated stock, cooler than cream */
  --sheet:#F7F7F4;      /* the page a book sits on */
  --sheet-2:#FFFFFE;
  --ink:#15171C;        /* printing ink is never pure black */
  --ink-2:#5A5F6B;
  --ink-3:#8A8F9A;
  --rule:#D8D8D1;
  --rule-2:#E6E6E0;
  --hi:#FDF6DC;         /* search highlight */
  --shadow:0 1px 2px rgba(21,23,28,.06), 0 8px 24px rgba(21,23,28,.06);
  --harvard:#AF2340; --princeton:#C57806; --yale:#2E63B2; --mit:#5C7F12; --chicago:#A65AA8;
  --soon:#9A5B08;       /* semantic: imminent, distinct from every press hue */
  --focus:#2E63B2;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#111217; --sheet:#1B1D24; --sheet-2:#22252D;
    --ink:#E9E9E4; --ink-2:#9BA1AE; --ink-3:#6E7482;
    --rule:#2E313A; --rule-2:#262932;
    --hi:#3A3418;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.32);
    --harvard:#DE4C77; --princeton:#B4862C; --yale:#5B8FD6; --mit:#749B34; --chicago:#B072B6;
    --soon:#D9A441;
    --focus:#5B8FD6;
  }
}
:root[data-theme="dark"]{
  --paper:#111217; --sheet:#1B1D24; --sheet-2:#22252D;
  --ink:#E9E9E4; --ink-2:#9BA1AE; --ink-3:#6E7482;
  --rule:#2E313A; --rule-2:#262932;
  --hi:#3A3418;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.32);
  --harvard:#DE4C77; --princeton:#B4862C; --yale:#5B8FD6; --mit:#749B34; --chicago:#B072B6;
  --soon:#D9A441;
  --focus:#5B8FD6;
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font:400 15px/1.55 "IBM Plex Sans","Segoe UI",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;
}
:focus-visible{outline:2px solid var(--focus); outline-offset:2px; border-radius:2px}
button{font:inherit; color:inherit; background:none; border:0; cursor:pointer}
a{color:inherit}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums}
.lbl{font-size:10.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3)}
mark{background:var(--hi); color:inherit; border-radius:2px; padding:0 1px}

/* --------------------------------------------------------------- masthead */
.masthead{
  display:flex; align-items:baseline; gap:20px; flex-wrap:wrap;
  padding:13px 20px 12px; border-bottom:1px solid var(--rule);
  background:var(--sheet); position:sticky; top:0; z-index:20;
}
.wordmark{font-family:Literata,Georgia,serif; font-weight:600; font-size:19px; letter-spacing:-.015em; white-space:nowrap}
.wordmark em{font-style:normal; color:var(--ink-3); font-weight:400}
.masthead .presses{display:flex; gap:14px; flex-wrap:wrap; font-size:11.5px; color:var(--ink-2)}
.masthead .presses span{display:inline-flex; align-items:center; gap:5px; white-space:nowrap}
.dot{width:8px; height:8px; border-radius:50%; flex:none}
.spacer{flex:1 1 40px}
.searchbox{position:relative; flex:0 1 300px; min-width:190px}
.searchbox input{
  width:100%; padding:7px 30px 7px 11px; border:1px solid var(--rule);
  border-radius:3px; background:var(--sheet-2); color:var(--ink); font:inherit; font-size:13.5px;
}
.searchbox input::placeholder{color:var(--ink-3)}
.searchbox .clear{position:absolute; right:4px; top:4px; padding:2px 7px; color:var(--ink-3); font-size:15px; line-height:1.2}
.iconbtn{border:1px solid var(--rule); border-radius:3px; padding:6px 10px; font-size:12px; color:var(--ink-2); background:var(--sheet-2)}
.iconbtn:hover{color:var(--ink); border-color:var(--ink-3)}
.fresh{font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink-3); white-space:nowrap}
.fresh.stale{color:var(--soon)}

/* ------------------------------------------------------------------- desk */
.desk{display:grid; grid-template-columns:216px minmax(320px,1fr) minmax(0,1.25fr); height:calc(100vh - 53px)}
.rail,.list,.reader{overflow-y:auto; overscroll-behavior:contain}
.rail{border-right:1px solid var(--rule); padding:16px 14px 40px; background:var(--paper)}
.list{border-right:1px solid var(--rule); background:var(--sheet)}
.reader{background:var(--sheet-2); padding:0}

/* ------------------------------------------------------------------- rail */
.rail section{margin-bottom:22px}
.rail h2{margin:0 0 8px; font-size:10.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3)}
.opt{
  display:flex; align-items:center; gap:8px; width:100%; text-align:left;
  padding:4px 6px; border-radius:3px; font-size:13px; color:var(--ink-2); line-height:1.35;
}
.opt:hover{background:var(--rule-2); color:var(--ink)}
.opt[aria-pressed="true"]{background:var(--rule-2); color:var(--ink); font-weight:500}
.opt .n{margin-left:auto; font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink-3); font-variant-numeric:tabular-nums}
.opt[aria-pressed="true"] .n{color:var(--ink-2)}
.opt .badge{margin-left:auto; font-family:"IBM Plex Mono",monospace; font-size:10.5px; background:var(--soon); color:var(--paper); border-radius:9px; padding:1px 6px; font-weight:500}

/* the season: one row per month, bar length = number of titles */
.mo{display:grid; grid-template-columns:56px 1fr 26px; align-items:center; gap:7px; width:100%; padding:2.5px 5px; border-radius:3px; font-size:11.5px; color:var(--ink-2)}
.mo:hover{background:var(--rule-2); color:var(--ink)}
.mo[aria-pressed="true"]{background:var(--rule-2); color:var(--ink)}
.mo .name{font-family:"IBM Plex Mono",monospace; font-size:11px; white-space:nowrap}
.mo .track{display:block; height:8px; background:var(--rule-2); border-radius:0 2px 2px 0; overflow:hidden}
.mo .bar{display:block; height:100%; background:var(--ink-3); border-radius:0 2px 2px 0}
.mo[aria-pressed="true"] .bar{background:var(--ink)}
.mo .n{font-family:"IBM Plex Mono",monospace; font-size:10.5px; text-align:right; color:var(--ink-3); font-variant-numeric:tabular-nums}
.mo.now .name{color:var(--soon); font-weight:500}

/* ------------------------------------------------------------------- list */
.listhead{
  position:sticky; top:0; z-index:5; background:var(--sheet);
  border-bottom:1px solid var(--rule); padding:9px 16px;
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
}
.listhead .count{font-size:12px; color:var(--ink-2)}
.listhead select{
  font:inherit; font-size:12px; padding:3px 6px; border:1px solid var(--rule);
  border-radius:3px; background:var(--sheet-2); color:var(--ink-2);
}
.mogroup{
  position:sticky; top:38px; z-index:4; background:var(--sheet);
  padding:13px 16px 5px; font-family:"IBM Plex Mono",monospace; font-size:11px;
  letter-spacing:.06em; text-transform:uppercase; color:var(--ink-3);
  border-bottom:1px solid var(--rule-2);
}
.row{
  display:grid; grid-template-columns:3px minmax(0,1fr) 30px; align-items:stretch;
  border-bottom:1px solid var(--rule-2); position:relative;
}
.row:hover{background:var(--rule-2)}
.row:has(.rowmain[aria-current="true"]){background:var(--rule-2)}
.row:has(.rowmain[aria-current="true"]) .stripe{opacity:1}
.stripe{opacity:.62}
.rowmain{
  display:grid; grid-template-columns:34px minmax(0,1fr); gap:0 11px; align-items:start;
  text-align:left; padding:10px 4px 10px 11px; width:100%;
}
.row .jacket{width:34px; aspect-ratio:2/3; border-radius:1px; overflow:hidden; position:relative}
.row .meta{min-width:0}
.row .meta{position:relative; display:flex; flex-direction:column; gap:2px}
.row .t{font-family:Literata,Georgia,serif; font-weight:500; font-size:14.5px; line-height:1.32; color:var(--ink)}
.row .s{font-family:Literata,Georgia,serif; font-style:italic; font-size:13px; color:var(--ink-2); line-height:1.35}
.row .b{font-size:12px; color:var(--ink-2); margin-top:1px}
.row .tags{display:flex; align-items:center; gap:9px; margin-top:3px; font-size:10.5px; color:var(--ink-3); flex-wrap:wrap}
.row .press{font-weight:600; letter-spacing:.05em; text-transform:uppercase; font-size:10px}
.row .when{font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums}
.row .when.soon{color:var(--soon)}
.leadchip{
  border:1px solid currentColor; border-radius:2px; padding:0 4px;
  font-size:9.5px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
}
.row .leadchip{color:var(--ink-2)}
.row .pickchip{color:var(--soon)}
.picknote{
  margin:0 0 20px; padding:14px 16px; border-radius:3px;
  background:var(--rule-2); max-width:62ch;
}
.picknote h3{
  margin:0 0 6px; font-size:10.5px; font-weight:600; letter-spacing:.09em;
  text-transform:uppercase; color:var(--ink-3);
}
.picknote p{margin:0; font-family:Literata,Georgia,serif; font-size:15px; line-height:1.55}
.distrib{font-style:italic}
.blurb .by{
  display:block; margin-top:6px; font-family:"IBM Plex Sans",sans-serif;
  font-size:12px; font-style:normal; color:var(--ink-2);
}
.blurb .by b{font-weight:600; color:var(--ink)}
.blurb .by .cred{color:var(--ink-3)}
.kindsw{display:flex; gap:4px; margin:-2px 0 6px}
.kindsw button{
  font-size:10.5px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
  color:var(--ink-3); padding:2px 6px; border-radius:3px;
}
.kindsw button[aria-pressed="true"]{background:var(--rule-2); color:var(--ink)}
.opt.chosen{background:var(--rule-2); color:var(--ink); font-weight:500}
.railnote{margin:2px 6px 0; font-size:11px; line-height:1.4; color:var(--ink-3)}
.newdot{position:absolute; left:-6px; top:6px; width:5px; height:5px; border-radius:50%; background:var(--soon)}
.star{align-self:start; font-size:13px; line-height:1; color:var(--rule); padding:11px 8px 4px 0}
.star:hover{color:var(--ink-2)}
.star.on{color:var(--soon)}
.empty{padding:44px 24px; color:var(--ink-2); font-size:14px; max-width:38ch; line-height:1.6}

/* ----------------------------------------------------------------- reader */
.reader .inner{padding:26px 34px 80px; max-width:760px}
.reader .backbtn{display:none}
.rhead{display:flex; gap:24px; align-items:flex-start; margin-bottom:22px}
/* 132px: the jacket carried inside this file is 96px wide, so where the page
   cannot reach the press for the full-resolution one this is as far as it can
   be stretched without going soft. */
.rhead .jacket{
  width:132px; flex:none; aspect-ratio:2/3; border-radius:2px; overflow:hidden;
  box-shadow:var(--shadow); position:relative; container-type:inline-size;
}
/* Three layers, best last: a typographic jacket, the small one carried inside
   this file, and — where the page is allowed to reach the press's CDN — the
   full-resolution one. Each hides itself if it cannot load. */
.jacket img{position:absolute; inset:0; width:100%; height:100%; object-fit:cover; display:block}
.jacket .thumb{z-index:1}
.jacket .full{z-index:2}
.jacket img.failed{display:none}
.fallback{
  position:absolute; inset:0; z-index:0; display:flex; flex-direction:column;
  justify-content:center; padding:12% 10%; gap:.4em; text-align:center;
  font-family:Literata,Georgia,serif; color:#fff; line-height:1.22; overflow:hidden;
}
.rhead .fallback{font-size:clamp(8px,8.5cqw,13px)}
.fallback .ft{font-weight:600}
.fallback .fa{font-size:.82em; opacity:.8}
.rtitle h1{font-family:Literata,Georgia,serif; font-weight:600; font-size:29px; line-height:1.18; margin:0 0 4px; letter-spacing:-.012em; text-wrap:balance}
.rtitle .sub{font-family:Literata,Georgia,serif; font-style:italic; font-size:18px; line-height:1.35; color:var(--ink-2); margin:0 0 10px; text-wrap:balance}
.rtitle .by{font-size:14px; margin:0 0 12px}
.pressline{display:flex; align-items:center; gap:7px; margin-bottom:10px; font-size:11px; font-weight:600; letter-spacing:.07em; text-transform:uppercase}
.pubchip{display:inline-flex; align-items:center; gap:6px; font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--ink-2); margin-bottom:14px}
.pubchip b{font-weight:500; color:var(--ink)}
.pubchip .soon{color:var(--soon)}
.actions{display:flex; gap:8px; flex-wrap:wrap}
.actions a,.actions button{
  border:1px solid var(--rule); border-radius:3px; padding:6px 11px; font-size:12.5px;
  text-decoration:none; color:var(--ink-2); background:var(--sheet-2); white-space:nowrap;
}
.actions a:hover,.actions button:hover{border-color:var(--ink-3); color:var(--ink)}
.actions .primary{background:var(--ink); color:var(--paper); border-color:var(--ink)}
.actions .primary:hover{color:var(--paper); opacity:.87}

.tag{font-family:Literata,Georgia,serif; font-size:20px; line-height:1.42; margin:0 0 20px; padding-left:15px; border-left:2px solid currentColor; color:var(--ink)}
.rbody{font-family:Literata,Georgia,serif; font-size:16px; line-height:1.62; max-width:62ch}
.rbody p{margin:0 0 .95em}
.sect{margin-top:30px; padding-top:18px; border-top:1px solid var(--rule)}
.sect > h3{margin:0 0 12px; font-size:10.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3)}
blockquote.blurb{
  margin:0 0 14px; font-family:Literata,Georgia,serif; font-size:15px; line-height:1.55;
  color:var(--ink); padding-left:14px; border-left:1px solid var(--rule); max-width:62ch;
}
.bio{font-family:Literata,Georgia,serif; font-size:15px; line-height:1.6; max-width:62ch; color:var(--ink-2)}
.bio p{margin:0 0 .8em}
.specs{display:grid; grid-template-columns:auto 1fr; gap:5px 18px; font-size:12.5px; max-width:62ch}
.specs dt{color:var(--ink-3); font-size:10.5px; font-weight:600; letter-spacing:.07em; text-transform:uppercase; padding-top:2px}
.specs dd{margin:0; color:var(--ink-2); font-family:"IBM Plex Mono",monospace; font-size:12px}
.specs dd.plain{font-family:inherit; font-size:12.5px}
.nothing{padding:70px 34px; color:var(--ink-3); font-family:Literata,Georgia,serif; font-size:16px; max-width:34ch; line-height:1.6}

/* -------------------------------------------------------------- responsive */
@media (max-width:1180px){
  .masthead .presses{display:none}
  .desk{grid-template-columns:200px 1fr}
  .reader{
    position:fixed; inset:53px 0 0 auto; width:min(620px,100%); z-index:30;
    border-left:1px solid var(--rule); box-shadow:var(--shadow); transform:translateX(101%);
    transition:transform .2s ease;
  }
  .reader.open{transform:none}
  .reader .backbtn{
    display:block; position:sticky; top:0; width:100%; text-align:left; z-index:2;
    padding:9px 16px; background:var(--sheet-2); border-bottom:1px solid var(--rule);
    font-size:12.5px; color:var(--ink-2);
  }
  .reader .inner{padding:22px 24px 80px}
}
@media (max-width:720px){
  .desk{grid-template-columns:1fr; height:auto}
  .rail{
    border-right:0; border-bottom:1px solid var(--rule); max-height:none; overflow:visible;
    display:grid; grid-template-columns:repeat(auto-fit,minmax(146px,1fr)); gap:0 18px;
    align-items:start;
  }
  .rail .season{grid-column:1/-1; max-height:190px; overflow-y:auto}
  .list{border-right:0}
  .reader{inset:0; width:100%}
  .searchbox{flex:1 1 100%; order:5}
  .rhead{gap:16px}
  .rhead .jacket{width:104px}
  .rtitle h1{font-size:24px}
}
@media (prefers-reduced-motion:reduce){ .reader{transition:none} }
</style>

<script>
  /* Apply a remembered theme before anything paints. */
  try{ var t = localStorage.getItem("seasonAhead.theme");
       if (t) document.documentElement.setAttribute("data-theme", t); }catch(e){}
</script>

<header class="masthead">
  <div class="wordmark">The Season Ahead <em>&mdash; forthcoming university press books</em></div>
  <div class="presses" id="pressKey"></div>
  <div class="spacer"></div>
  <span class="fresh" id="fresh"></span>
  <div class="searchbox">
    <input id="q" type="search" autocomplete="off" spellcheck="false"
           placeholder="Search titles, authors, jacket copy&hellip;" aria-label="Search every field">
    <button class="clear" id="qclear" hidden aria-label="Clear search">&times;</button>
  </div>
  <button class="iconbtn" id="themeBtn" title="Switch between light and dark">Theme</button>
</header>

<div class="desk">
  <aside class="rail">
    <section>
      <h2>Shelves</h2>
      <div id="views"></div>
    </section>
    <section>
      <h2>Press</h2>
      <div id="pressFilter"></div>
    </section>
    <section class="season">
      <h2>The season</h2>
      <div id="months"></div>
    </section>
    <section>
      <h2>Recommended by</h2>
      <div class="kindsw" id="endorserKind">
        <button data-kind="person">People</button>
        <button data-kind="outlet">Press</button>
      </div>
      <div id="endorsers"></div>
    </section>
    <section>
      <h2>Subject</h2>
      <div id="topics"></div>
    </section>
  </aside>

  <section class="list">
    <div class="listhead">
      <span class="count" id="count"></span>
      <div class="spacer"></div>
      <label class="lbl" for="sort">Sort</label>
      <select id="sort">
        <option value="date">Publication date</option>
        <option value="title">Title</option>
        <option value="author">Author</option>
        <option value="press">Press, then date</option>
        <option value="push">Biggest push</option>
      </select>
    </div>
    <div id="rows"></div>
  </section>

  <article class="reader" id="reader">
    <button class="backbtn" id="backbtn">&larr; Back to the list</button>
    <div id="readerInner"></div>
  </article>
</div>

<script id="data" type="application/json">__DATA__</script>
<script id="covers" type="application/json">__COVERS__</script>
<script>
(function(){
"use strict";
const DATA    = JSON.parse(document.getElementById("data").textContent);
const COVERS  = JSON.parse(document.getElementById("covers").textContent);
const BOOKS   = DATA.books;
const PRESSES = DATA.presses;
const ORDER   = ["chicago","harvard","mit","princeton","yale"];
// Relative labels are measured against the day the page is OPENED, not the day
// it was built, so an old file says "out last month" rather than "in 3 weeks".
const NOW     = new Date();
const TODAY   = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate());
const BUILT   = new Date(DATA.generated);
const AGE     = Math.round((TODAY - new Date(BUILT.getFullYear(), BUILT.getMonth(), BUILT.getDate())) / 86400000);

/* One lower-cased haystack per book, so the search box can stay dumb and fast.
   Built here rather than shipped in the JSON, which would near enough double
   the size of the file for text already present. */
BOOKS.forEach((b,i) => {
  b.id = b.press + ":" + b.isbn;
  b.i  = i;
  b.hay = [b.title, b.subtitle, b.authors, b.tagline, b.description, b.bio,
           b.series, b.subjects.join(" "), b.distributor,
           b.praise.map(p => p.q + " " + p.by).join(" "),
           PRESSES[b.press].name].join(" ").toLowerCase();
});

/* ------------------------------------------------------------ persistence */
const KEY = "seasonAhead.v1";
let saved = {};
try { saved = JSON.parse(localStorage.getItem(KEY)) || {}; } catch(e){}

// First ever open: treat the whole list as already seen, so the reader is not
// handed a thousand unread markers. After that, only genuinely new titles —
// ones a later rebuild added — carry the dot.
const firstRun = !Array.isArray(saved.seen);
const store = {
  seen:  new Set(firstRun ? BOOKS.map(b => b.id) : saved.seen),
  shelf: new Set(saved.shelf || []),
};
function saveState(){                       // Sets do not survive JSON
  try {
    localStorage.setItem(KEY, JSON.stringify({
      seen:[...store.seen], shelf:[...store.shelf], build:DATA.generated
    }));
  } catch(e){}
}
if (firstRun) saveState();

/* ------------------------------------------------------------------ dates */
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function monthKey(iso){ return iso.slice(0,7); }
function monthName(key){
  const [y,m] = key.split("-");
  return MONTHS[+m - 1] + " " + y;
}
function days(iso){
  return Math.round((new Date(iso + "T00:00:00") - TODAY) / 86400000);
}
function whenLabel(iso){
  const d = days(iso);
  if (d < -7)  return "Out " + monthName(monthKey(iso));
  if (d < 0)   return "Just out";
  if (d === 0) return "Out today";
  if (d === 1) return "Tomorrow";
  if (d <= 14) return "in " + d + " days";
  if (d <= 60) return "in " + Math.round(d/7) + " weeks";
  const dt = new Date(iso + "T00:00:00");
  return MONTHS[dt.getMonth()] + " " + dt.getDate() + ", " + dt.getFullYear();
}
function fullDate(iso){
  const dt = new Date(iso + "T00:00:00");
  return dt.toLocaleDateString("en-US",{month:"long", day:"numeric", year:"numeric"});
}

/* -------------------------------------------------------------------- misc */
function esc(s){
  return String(s == null ? "" : s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function highlight(s){
  if (!terms.length) return esc(s);
  let out = esc(s);
  terms.forEach(t => {
    if (t.length < 2) return;
    const re = new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g,"\\$&") + ")","gi");
    out = out.replace(re, "<mark>$1</mark>");
  });
  return out;
}
function paras(text, cls){
  if (!text) return "";
  return text.split("\n\n").filter(Boolean)
    .map(p => "<p" + (cls ? ' class="' + cls + '"' : "") + ">" + highlight(p) + "</p>").join("");
}
function jacket(b, big){
  const thumb = COVERS[b.id];
  const under = big
    ? '<span class="ft">' + esc(b.title) + '</span><span class="fa">' + esc(b.authors) + '</span>'
    : "";
  let html = '<span class="fallback" style="background:var(--' + b.press + ')">' + under + '</span>';
  if (thumb) html += '<img class="thumb" loading="lazy" decoding="async" alt="" src="' + thumb + '">';
  // Chicago keys its jackets by an ISBN that is not always the one you buy,
  // so those records carry their own URL and there is no template.
  const tpl = PRESSES[b.press].cover;
  const full = b.cover || (tpl ? tpl.replace("{isbn}", b.isbn).replace("{w}", 400) : "");
  if (big && full){
    html += '<img class="full" decoding="async" alt="" src="' + esc(full) + '">';
  }
  return html;
}
// A jacket that will not load simply uncovers the layer beneath it.
document.addEventListener("error", ev => {
  if (ev.target && ev.target.tagName === "IMG") ev.target.classList.add("failed");
}, true);

/* ------------------------------------------------------------------- state */
const state = { q:"", terms:[], press:new Set(), topic:new Set(), month:new Set(),
                view:"all", sort:"date", sel:null,
                // Chicago warehouses for ~100 other houses; those are off by
                // default so its own list is not buried in them.
                distributed:false,
                endorser:null, endorserKind:"person", endorserAll:false };
let terms = [];

function newCount(){ return BOOKS.filter(b => !store.seen.has(b.id)).length; }

function passesExceptView(b){
  if (!state.distributed && !b.own_list) return false;
  if (state.endorser && !b.endorsers.includes(state.endorser)
      && !b.outlets.includes(state.endorser)) return false;
  if (state.press.size && !state.press.has(b.press)) return false;
  if (state.topic.size && !state.topic.has(b.topic)) return false;
  if (state.month.size && !state.month.has(monthKey(b.pub_date))) return false;
  for (const t of terms) if (b.hay.indexOf(t) === -1) return false;
  return true;
}
function passesView(b){
  if (state.view === "new")     return !store.seen.has(b.id);
  if (state.view === "shelf")   return store.shelf.has(b.id);
  if (state.view === "soon")    { const d = days(b.pub_date); return d >= 0 && d <= 60; }
  if (state.view === "pick")    return b.pick;
  if (state.view === "lead")    return b.lead;
  if (state.view === "praise")  return b.has_praise;
  return true;
}
function selected(){
  return BOOKS.filter(b => passesView(b) && passesExceptView(b));
}

const SORTS = {
  date:   (a,b) => a.pub_date.localeCompare(b.pub_date) || a.title.localeCompare(b.title),
  title:  (a,b) => a.title.localeCompare(b.title),
  author: (a,b) => (a.authors||"~").localeCompare(b.authors||"~") || a.pub_date.localeCompare(b.pub_date),
  press:  (a,b) => ORDER.indexOf(a.press) - ORDER.indexOf(b.press) || a.pub_date.localeCompare(b.pub_date),
  // What a press is betting on: blurbs commissioned, then length of jacket copy.
  push:   (a,b) => (b.praise.length - a.praise.length) || (b.word_count - a.word_count),
};

/* -------------------------------------------------------------- rendering */
const $ = id => document.getElementById(id);

function renderRail(){
  const shown = BOOKS.filter(passesExceptView);
  const nNew  = newCount();

  const pool = BOOKS.filter(b => state.distributed || b.own_list);
  const views = [
    ["all",    "Everything",     pool.length],
    ["new",    "New to me",      nNew, true],
    ["pick",   "Editor's picks", pool.filter(b => b.pick).length],
    ["lead",   "Lead titles",    pool.filter(b => b.lead).length],
    ["soon",   "Next 60 days",   pool.filter(b => { const d = days(b.pub_date); return d>=0 && d<=60; }).length],
    ["praise", "Has blurbs",     pool.filter(b => b.has_praise).length],
    ["shelf",  "My shelf",       store.shelf.size],
  ];
  $("views").innerHTML = views.map(([k,label,n,isNew]) =>
    '<button class="opt" data-view="' + k + '" aria-pressed="' + (state.view===k) + '">'
    + '<span>' + label + '</span>'
    + (isNew && n ? '<span class="badge">' + n + '</span>' : '<span class="n">' + n + '</span>')
    + '</button>').join("")
    + (nNew ? '<button class="opt" id="markseen" style="margin-top:4px"><span style="font-size:12px;color:var(--ink-3)">Mark all as seen</span></button>' : "");

  $("pressFilter").innerHTML = ORDER.map(p => {
    const n = shown.filter(b => b.press === p).length;
    return '<button class="opt" data-press="' + p + '" aria-pressed="' + state.press.has(p) + '">'
      + '<span class="dot" style="background:var(--' + p + ')"></span>'
      + '<span>' + PRESSES[p].short + '</span><span class="n">' + n + '</span></button>';
  }).join("")
  + '<button class="opt" id="distToggle" aria-pressed="' + state.distributed + '">'
  +   '<span>&hellip;and distributed</span>'
  +   '<span class="n">' + BOOKS.filter(b => !b.own_list).length + '</span></button>'
  + '<p class="railnote">Chicago warehouses for about a hundred other houses. '
  +   'Its own list is ' + BOOKS.filter(b => b.press === "chicago" && b.own_list).length
  +   ' of these titles.</p>';

  const counts = {};
  shown.forEach(b => { const k = monthKey(b.pub_date); counts[k] = (counts[k]||0) + 1; });
  const keys = Object.keys(counts).sort();
  const max  = Math.max(1, ...Object.values(counts));
  const nowK = TODAY.toISOString().slice(0,7);
  $("months").innerHTML = keys.map(k =>
    '<button class="mo' + (k === nowK ? " now" : "") + '" data-month="' + k + '"'
    + ' aria-pressed="' + state.month.has(k) + '" title="' + counts[k] + ' titles in ' + monthName(k) + '">'
    + '<span class="name">' + monthName(k) + '</span>'
    + '<span class="track"><span class="bar" style="width:' + Math.max(3, counts[k]/max*100) + '%"></span></span>'
    + '<span class="n">' + counts[k] + '</span></button>').join("");

  // Who is recommending these books. Counting the endorser rather than the
  // blurb is the point: it is how one name surfaces across several titles.
  const field = state.endorserKind === "person" ? "endorsers" : "outlets";
  const ec = {};
  BOOKS.filter(b => state.distributed || b.own_list)
       .forEach(b => [...new Set(b[field])].forEach(w => { ec[w] = (ec[w]||0) + 1; }));
  const ranked = Object.entries(ec).sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0]));
  const cut = state.endorserAll ? 60 : 10;
  document.querySelectorAll("#endorserKind button").forEach(el =>
    el.setAttribute("aria-pressed", el.dataset.kind === state.endorserKind));
  $("endorsers").innerHTML =
    (state.endorser ? '<button class="opt chosen" id="clearEndorser">'
        + '<span>&larr; ' + esc(state.endorser) + '</span></button>' : "")
    + ranked.slice(0, cut).map(([w, c]) =>
        '<button class="opt" data-endorser="' + esc(w) + '" aria-pressed="'
        + (state.endorser === w) + '"><span>' + esc(w) + '</span>'
        + '<span class="n">' + c + '</span></button>').join("")
    + (ranked.length > cut
        ? '<button class="opt" id="moreEndorsers"><span style="color:var(--ink-3)">'
          + (state.endorserAll ? "Fewer" : "More of " + ranked.length) + '</span></button>'
        : "");

  const tc = {};
  shown.forEach(b => { tc[b.topic] = (tc[b.topic]||0) + 1; });
  $("topics").innerHTML = Object.entries(tc).sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0]))
    .map(([t,n]) => '<button class="opt" data-topic="' + esc(t) + '" aria-pressed="' + state.topic.has(t) + '">'
      + '<span>' + esc(t) + '</span><span class="n">' + n + '</span></button>').join("");

  $("pressKey").innerHTML = ORDER.map(p =>
    '<span><span class="dot" style="background:var(--' + p + ')"></span>' + PRESSES[p].short + '</span>').join("");
}

function renderList(){
  const list = selected().sort(SORTS[state.sort]);
  $("count").innerHTML = "<b>" + list.length + "</b> "
    + (list.length === 1 ? "title" : "titles")
    + (list.length !== BOOKS.length ? " of " + BOOKS.length : "");

  if (!list.length){
    $("rows").innerHTML = '<p class="empty">Nothing matches. Loosen a filter, or clear the search.</p>';
    return;
  }

  let html = "", lastMonth = "";
  const grouped = state.sort === "date";
  list.forEach(b => {
    const mk = monthKey(b.pub_date);
    if (grouped && mk !== lastMonth){
      lastMonth = mk;
      html += '<div class="mogroup">' + monthName(mk) + '</div>';
    }
    const d = days(b.pub_date);
    const starred = store.shelf.has(b.id);
    html += '<div class="row">'
      + '<span class="stripe" style="background:var(--' + b.press + ')"></span>'
      + '<button class="rowmain" data-i="' + b.i + '" aria-current="' + (state.sel === b.i) + '">'
      +   '<span class="jacket">' + jacket(b, false) + '</span>'
      +   '<span class="meta">'
      +     (store.seen.has(b.id) ? "" : '<span class="newdot" title="Added since you last looked"></span>')
      +     '<span class="t">' + highlight(b.title) + '</span>'
      +     (b.subtitle ? '<span class="s">' + highlight(b.subtitle) + '</span>' : "")
      +     (b.authors ? '<span class="b">' + highlight(b.authors) + '</span>' : "")
      +     '<span class="tags">'
      +       '<span class="press" style="color:var(--' + b.press + ')">' + PRESSES[b.press].short + '</span>'
      +       '<span class="when' + (d >= 0 && d <= 30 ? " soon" : "") + '">' + whenLabel(b.pub_date) + '</span>'
      +       (b.pick ? '<span class="leadchip pickchip">Pick</span>' : "")
      +       (b.lead ? '<span class="leadchip">Lead</span>' : "")
      +       (b.praise.length ? '<span>' + b.praise.length + ' blurb' + (b.praise.length>1?"s":"") + '</span>' : "")
      +       (b.pages ? '<span>' + b.pages + 'pp</span>' : "")
      +       (b.distributor ? '<span class="distrib">for ' + esc(b.distributor) + '</span>' : "")
      +     '</span>'
      +   '</span>'
      + '</button>'
      + '<button class="star' + (starred ? " on" : "") + '" data-star="' + b.i + '"'
      +   ' aria-pressed="' + starred + '" title="' + (starred ? "On my shelf" : "Add to shelf") + '">'
      + (starred ? "★" : "☆") + '</button>'
      + '</div>';
  });
  $("rows").innerHTML = html;
}

function renderReader(){
  const el = $("readerInner");
  if (state.sel == null){
    el.innerHTML = '<p class="nothing">Pick a title to read its jacket copy, the blurbs the press has gathered, and the specifications.</p>';
    return;
  }
  const b = BOOKS[state.sel];
  const P = PRESSES[b.press];
  const d = days(b.pub_date);
  const onShelf = store.shelf.has(b.id);

  const specs = [
    ["Publisher", P.name, true],
    ["Published", fullDate(b.pub_date), false],
    ["Format",    (b.formats.length ? b.formats.join(", ") : b.format) || "—", true],
    ["Pages",     b.pages || "", false],
    ["Size",      b.trim || "", false],
    ["Price",     b.price || "", false],
    ["ISBN",      b.isbn, false],
    ["Series",    b.series || "", true],
    ["Distributed for", b.distributor || "", true],
    ["Subjects",  b.subjects.join(" · ") || "", true],
  ].filter(r => r[1]);

  el.innerHTML =
    '<div class="inner">'
    + '<div class="pressline" style="color:var(--' + b.press + ')">'
    +   '<span class="dot" style="background:var(--' + b.press + ')"></span>' + esc(P.name)
    +   (b.distributor ? ' <span class="distrib" style="text-transform:none">distributing for '
                       + esc(b.distributor) + '</span>' : "")
    +   (b.lead ? ' <span class="leadchip" title="Among the titles this press is pushing hardest for its month">Lead</span>' : "")
    + '</div>'
    + '<div class="rhead">'
    +   '<div class="jacket">' + jacket(b, true) + '</div>'
    +   '<div class="rtitle">'
    +     '<h1>' + highlight(b.title) + '</h1>'
    +     (b.subtitle ? '<p class="sub">' + highlight(b.subtitle) + '</p>' : "")
    +     (b.authors ? '<p class="by">' + highlight(b.authors) + '</p>' : "")
    +     '<p class="pubchip">' + (d >= 0 && d <= 60 ? '<span class="soon">' + whenLabel(b.pub_date) + '</span> · ' : "")
    +       '<b>' + fullDate(b.pub_date) + '</b></p>'
    +     '<div class="actions">'
    +       '<a class="primary" href="' + esc(b.url) + '" target="_blank" rel="noopener">Open at ' + PRESSES[b.press].short + ' &nearr;</a>'
    +       '<button data-star="' + b.i + '">' + (onShelf ? "★ On my shelf" : "☆ Add to shelf") + '</button>'
    +       '<button data-copy="' + b.i + '">Copy reference</button>'
    +     '</div>'
    +   '</div>'
    + '</div>'
    + (b.pick ? '<div class="picknote"><h3>Why this one</h3><p>' + highlight(b.pick_note) + '</p></div>' : "")
    + (b.tagline ? '<p class="tag" style="border-color:var(--' + b.press + ')">' + highlight(b.tagline) + '</p>' : "")
    + (b.description ? '<div class="rbody">' + paras(b.description) + '</div>'
       : b.tagline ? ""
       : '<p class="bio">' + esc(PRESSES[b.press].short) + ' has not posted jacket copy for this title yet.</p>')
    + (b.praise.length ? '<div class="sect"><h3>' + b.praise.length + ' blurb' + (b.praise.length>1?"s":"") + '</h3>'
        + b.praise.map(p =>
            '<blockquote class="blurb">' + highlight(p.q)
            + (p.by
                ? '<span class="by">'
                  + (p.who ? '<b>' + highlight(p.who) + '</b>' : highlight(p.by))
                  + (p.cred ? '<span class="cred">, ' + highlight(p.cred) + '</span>' : "")
                  + '</span>'
                : "")
            + '</blockquote>').join("") + '</div>' : "")
    + (b.bio ? '<div class="sect"><h3>About the author</h3><div class="bio">' + paras(b.bio) + '</div></div>' : "")
    + '<div class="sect"><h3>Specifications</h3><dl class="specs">'
    +   specs.map(([k,v,plain]) => '<dt>' + k + '</dt><dd' + (plain ? ' class="plain"' : "") + '>' + esc(v) + '</dd>').join("")
    + '</dl></div>'
    + '</div>';
}

function render(){ renderRail(); renderList(); renderReader(); }

/* ----------------------------------------------------------------- events */
function toggle(set, v){ set.has(v) ? set.delete(v) : set.add(v); }

function select(i){
  state.sel = i;
  const b = BOOKS[i];
  if (!store.seen.has(b.id)){ store.seen.add(b.id); saveState(); }
  renderRail(); renderList(); renderReader();
  $("reader").classList.add("open");
  $("reader").scrollTop = 0;
  const row = document.querySelector('.rowmain[data-i="' + i + '"]');
  if (row) row.scrollIntoView({block:"nearest"});
}

document.addEventListener("click", ev => {
  const star = ev.target.closest("[data-star]");
  if (star){
    ev.stopPropagation(); ev.preventDefault();
    const b = BOOKS[+star.dataset.star];
    toggle(store.shelf, b.id); saveState(); render();
    return;
  }
  const copy = ev.target.closest("[data-copy]");
  if (copy){
    const b = BOOKS[+copy.dataset.copy];
    const line = [b.authors, b.title + (b.subtitle ? ": " + b.subtitle : ""),
                  PRESSES[b.press].name, fullDate(b.pub_date), "ISBN " + b.isbn].filter(Boolean).join(". ");
    navigator.clipboard && navigator.clipboard.writeText(line);
    copy.textContent = "Copied";
    setTimeout(() => { copy.textContent = "Copy reference"; }, 1400);
    return;
  }
  const row = ev.target.closest(".rowmain");
  if (row){ select(+row.dataset.i); return; }

  const v = ev.target.closest("[data-view]");
  if (v){ state.view = v.dataset.view; render(); return; }

  const p = ev.target.closest("[data-press]");
  if (p){ toggle(state.press, p.dataset.press); render(); return; }

  const t = ev.target.closest("[data-topic]");
  if (t){ toggle(state.topic, t.dataset.topic); render(); return; }

  const m = ev.target.closest("[data-month]");
  if (m){ toggle(state.month, m.dataset.month); render(); return; }

  const en = ev.target.closest("[data-endorser]");
  if (en){
    state.endorser = state.endorser === en.dataset.endorser ? null : en.dataset.endorser;
    render(); return;
  }
  if (ev.target.closest("#clearEndorser")){ state.endorser = null; render(); return; }
  if (ev.target.closest("#moreEndorsers")){ state.endorserAll = !state.endorserAll; render(); return; }
  const kd = ev.target.closest("[data-kind]");
  if (kd){
    state.endorserKind = kd.dataset.kind; state.endorser = null; render(); return;
  }
  if (ev.target.closest("#distToggle")){
    state.distributed = !state.distributed; render(); return;
  }
  if (ev.target.closest("#markseen")){
    BOOKS.forEach(b => store.seen.add(b.id)); saveState(); render(); return;
  }
  if (ev.target.closest("#backbtn")){ $("reader").classList.remove("open"); return; }
  if (ev.target.closest("#themeBtn")){
    const cur = document.documentElement.getAttribute("data-theme");
    const dark = cur ? cur === "dark"
                     : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("seasonAhead.theme", next); } catch(e){}
    return;
  }
  if (ev.target.closest("#qclear")){
    $("q").value = ""; state.q = ""; terms = []; $("qclear").hidden = true; render(); return;
  }
});

let qt;
$("q").addEventListener("input", e => {
  clearTimeout(qt);
  $("qclear").hidden = !e.target.value;
  qt = setTimeout(() => {
    state.q = e.target.value;
    terms = state.q.toLowerCase().split(/\s+/).filter(t => t.length > 1);
    render();
  }, 130);
});
$("sort").addEventListener("change", e => { state.sort = e.target.value; renderList(); });

document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement !== $("q")){ e.preventDefault(); $("q").focus(); return; }
  if (e.key === "Escape"){ $("reader").classList.remove("open"); return; }
  if (e.key !== "j" && e.key !== "k") return;
  if (document.activeElement === $("q")) return;
  const list = selected().sort(SORTS[state.sort]);
  const at = list.findIndex(b => b.i === state.sel);
  const next = e.key === "j" ? Math.min(list.length - 1, at + 1) : Math.max(0, at - 1);
  if (list[next]) select(list[next].i);
});

/* Say plainly how old the data is: a forthcoming list goes off. */
const fresh = $("fresh");
fresh.textContent = AGE <= 0 ? "Read today"
  : AGE === 1 ? "Read yesterday"
  : AGE < 28  ? "Read " + AGE + " days ago"
  : "Read " + BUILT.toLocaleDateString("en-US",{month:"short", day:"numeric"}) + " — refresh me";
fresh.title = "The presses were last read on " + BUILT.toLocaleString();
if (AGE >= 21) fresh.classList.add("stale");

/* Open on the next title to publish, so the page is never a blank shell. */
render();
const opener = BOOKS.filter(b => days(b.pub_date) >= 0).sort(SORTS.date)[0] || BOOKS[0];
if (opener) { state.sel = opener.i; renderList(); renderReader(); }
})();
</script>
"""


def main():
    if not DATA.exists():
        print(f"no data yet — run scrape.py first ({DATA})")
        return 1
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    payload["presses"] = PRESSES          # pick up any template changes

    # Both are rebuilt in the browser: the search index from fields already
    # present, the jacket URL from its press's template. Shipping either would
    # near enough double the file for no new information.
    for b in payload["books"]:
        b.pop("hay", None)
        if b["press"] != "chicago":          # the rest rebuild from a template
            b.pop("cover", None)

    # A hand-written shortlist: {"press:isbn": "why this one"}. Nothing derives
    # it, which is the point — it is a reading recommendation, not a ranking.
    picks = {}
    if PICKS.exists():
        picks = json.loads(PICKS.read_text(encoding="utf-8"))
    for b in payload["books"]:
        note = picks.get(f"{b['press']}:{b['isbn']}")
        b["pick"] = bool(note)
        if note:
            b["pick_note"] = note

    covers = {}
    if COVERS.exists():
        covers = {k: v for k, v in json.loads(COVERS.read_text(encoding="utf-8")).items() if v}

    # </script> inside jacket copy would close the tag early
    def blob(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.replace("__DATA__", blob(payload))
                           .replace("__COVERS__", blob(covers)), encoding="utf-8")

    mb = OUT.stat().st_size / 1e6
    print(f"{len(payload['books'])} titles, {len(covers)} jackets, "
          f"{sum(1 for b in payload['books'] if b['pick'])} picks -> {OUT}  ({mb:,.1f} MB)")
    if not covers:
        print("   no jacket cache — run covers.py so the page carries its own images")

    return 0


if __name__ == "__main__":
    sys.exit(main())
