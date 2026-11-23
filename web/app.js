/* 五笔练习 · 本地版前端 */
(() => {
  'use strict';

  /* ------------------------------------------------------------ 工具 */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const clamp = (n, a, b) => Math.min(b, Math.max(a, n));
  const fmt = (n, d = 0) => Number(n).toFixed(d).replace(/\.0$/, '');

  const LS_KEY = 'wubi.prefs.v2';

  const PUNCT_KEYS = {
    '，': ',', '。': '.', '、': '\\', '；': ';', '：': ':',
    '？': '?', '！': '!', '“': '"', '”': '"', '‘': "'", '’': "'",
    '（': '(', '）': ')', '《': '<', '》': '>', '【': '[', '】': ']',
    '「': '[', '」': ']', '『': '[', '』': ']', '〔': '[', '〕': ']',
    '—': '-', '…': '^', '·': '`', '　': ' ',
    '～': '~', '－': '-', '％': '%', '＆': '&', '＃': '#', '＠': '@',
    '＋': '+', '＝': '=', '｜': '|', '／': '/', '＼': '\\',
  };
  const CJK_RE = /[\u3400-\u9fff\uf900-\ufaff]/;
  const CJK_PUNCT_RE = /[\u3000-\u303f\u2010-\u2027\u2030-\u205e]|[\uff01-\uff0f\uff1a-\uff20\uff3b-\uff40\uff5b\uff5d]/;

  const DATA = {
    keys: [],
    keyByLetter: {},
    pools: {},
    chars: {},
    words: {},
    jm1: new Set(),
    keyname: new Set(),
    chengzi: new Set(),
    charRoots: {},
    rootFontOk: false,
  };

  const state = {
    view: 'five',
    pool: 'common',
    wordPool: 'w2',
    perRound: 50,
    mode: 'short',   // short | full
    autoHint: false, // 初学模式：始终显示键位提示
    sound: true,
    words2: [],
    words3: [],
    words4: [],
    errors: [],
    stats: null,
    modalOpen: false,
  };

  function loadPrefs() {
    try {
      const p = JSON.parse(localStorage.getItem(LS_KEY) || '{}');
      if (p.perRound) state.perRound = p.perRound;
      if (p.mode) state.mode = p.mode;
      if (typeof p.autoHint === 'boolean') state.autoHint = p.autoHint;
      if (typeof p.sound === 'boolean') state.sound = p.sound;
    } catch (e) { /* ignore */ }
  }

  function savePrefs() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({
        perRound: state.perRound, mode: state.mode, autoHint: state.autoHint, sound: state.sound,
      }));
    } catch (e) { /* ignore */ }
  }

  let toastTimer = 0;
  function toast(msg, isErr) {
    const box = $('#toast');
    box.textContent = msg;
    box.className = 'toast show' + (isErr ? ' err' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { box.className = 'toast'; }, isErr ? 2600 : 1600);
  }

  let actx = null;
  function beep(kind) {
    if (!state.sound) return;
    try {
      actx = actx || new (window.AudioContext || window.webkitAudioContext)();
      const o = actx.createOscillator();
      const g = actx.createGain();
      o.type = kind === 'ok' ? 'sine' : 'square';
      o.frequency.value = kind === 'ok' ? 880 : 150;
      o.connect(g);
      g.connect(actx.destination);
      const t = actx.currentTime;
      g.gain.setValueAtTime(0.045, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + 0.1);
      o.start(t);
      o.stop(t + 0.11);
    } catch (e) { /* ignore */ }
  }

  /* ------------------------------------------------------------ 数据加载 */
  async function fetchJSON(url) {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(url + ' ' + res.status);
    return res.json();
  }

  async function loadData() {
    const [keys, pools, chars, words, errs] = await Promise.all([
      fetchJSON('/data/keys86.json'),
      fetchJSON('/data/pools.json'),
      fetchJSON('/data/chars.json'),
      fetchJSON('/data/words.json'),
      fetchJSON('/api/errors').catch(() => ({ errors: [] })),
    ]);
    DATA.keys = keys;
    keys.forEach(k => { DATA.keyByLetter[k.key] = k; });
    DATA.pools = pools;
    DATA.chars = chars.chars || {};
    DATA.words = words.words || {};
    DATA.jm1 = new Set(pools.jm1 || []);
    DATA.keyname = new Set(pools.keyname || []);
    DATA.chengzi = new Set(pools.chengzi || []);
    state.errors = errs.errors || [];
    state.stats = await fetchJSON('/api/stats').catch(() => null);
    const w2 = [], w3 = [], w4 = [];
    (pools.w2 || []).forEach(w => w2.push(w));
    (pools.w3 || []).forEach(w => w3.push(w));
    (pools.w4 || []).forEach(w => w4.push(w));
    state.words2 = w2;
    state.words3 = w3;
    state.words4 = w4;
  }

  /* ------------------------------------------------------------ 键位信息 */
  function keyInfo(letter) {
    return DATA.keyByLetter[letter.toUpperCase()] || { key: letter.toUpperCase(), name: '', roots: [], rhyme: '', zone: 0, finger: '' };
  }

  let charRootsPromise = null;

  async function loadCharRoots() {
    if (charRootsPromise) return charRootsPromise;
    charRootsPromise = (async () => {
      try {
        const data = await fetchJSON('/data/char_roots.json');
        DATA.charRoots = data.chars || {};
      } catch (e) {
        DATA.charRoots = {};
      }
      try { await document.fonts.load('24px WubiRoots'); } catch (e) { /* font optional */ }
      try { DATA.rootFontOk = document.fonts.check('24px WubiRoots'); } catch (e) { DATA.rootFontOk = false; }
      return DATA.charRoots;
    })();
    return charRootsPromise;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  }

  function rootEntry(ch) {
    return DATA.charRoots[ch] || null;
  }

  function rootGlyphHTML(entry) {
    return entry.units.map((unit, i) => {
      const key = (entry.keys[i] || '').toUpperCase();
      const info = keyInfo(key);
      const ident = !!entry.identifyLast && i === entry.units.length - 1;
      const id = ident ? entry.identify : null;
      const title = id
        ? `识别码：末笔${id.strokeName} · ${id.structure}型 → ${id.key}（${id.zone}区${id.position}位）`
        : `${info.name}键 ${info.rhyme}`;
      return `<span class="root-chip${ident ? ' identify' : ''}" title="${escapeHtml(title)}">
        <span class="root-glyph">${unit}</span>
        <span class="root-key">${key}</span>
        ${ident ? '<span class="root-ident">识</span>' : ''}
      </span>`;
    }).join('<span class="root-plus">+</span>');
  }

  function fallbackRootHTML(ch) {
    const d = DATA.chars[ch];
    if (!d) return '<span class="root-fallback">无拆字数据</span>';
    const code = state.mode === 'full' ? d.f : d.s;
    return '<span class="root-fallback-label">码位字根</span>' +
      [...code].map(k => {
        const info = keyInfo(k);
        return `<span class="root-fallback-chip"><b>${k.toUpperCase()}</b>${escapeHtml(info.roots.slice(0, 3).join('/'))}</span>`;
      }).join('');
  }

  function rootCharHTML(ch) {
    const entry = rootEntry(ch);
    return `<div class="root-char">
      <span class="root-char-name">${escapeHtml(ch)}</span>
      <div class="root-chain">${entry && DATA.rootFontOk ? rootGlyphHTML(entry) : fallbackRootHTML(ch)}</div>
    </div>`;
  }

  function rootBlockHTML(chars) {
    const exact = DATA.rootFontOk && chars.every(ch => !!rootEntry(ch));
    const notes = chars.map(ch => {
      const entry = rootEntry(ch);
      const id = entry && entry.identify;
      if (!id) return '';
      return `<span class="root-ident-note">${escapeHtml(ch)}：识别码 = 末笔${id.strokeName} · ${id.structure}型 → ${id.key}（${id.zone}区${id.position}位）</span>`;
    }).filter(Boolean);
    return `<div class="root-head">
      <span>${exact ? '拆字字根' : '码位字根'}</span>
      <span class="root-note">${exact ? '字根字形 + 键位' : '未收录逐字拆解，显示该键常见字根'}</span>
    </div>
    <div class="root-row">${chars.map(rootCharHTML).join('')}</div>
    ${notes.length ? `<div class="root-notes">${notes.join('')}</div>` : ''}`;
  }

  function rootCodeHTML(code) {
    return [...code].map(k => {
      const info = keyInfo(k);
      return `<span class="root-code-chip"><b>${k.toUpperCase()}</b><small>${escapeHtml(info.name)}键</small></span>`;
    }).join('');
  }

  function renderKeyboard(container, opts) {
    const { full = false, clickable = false } = opts || {};
    const rows = ['QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM'];
    container.innerHTML = rows.map(row => {
      const keys = [...row].map(letter => {
        const k = keyInfo(letter);
        return `<button type="button" class="key zone-${k.zone}${clickable ? ' clickable' : ''}" data-key="${letter}" aria-label="${letter} 键 ${k.name}">
          <span class="k-letter">${letter}</span>
          <span class="k-name">${k.name}</span>
          ${full ? `<span class="k-roots">${k.roots.join(' ')}</span>` : ''}
        </button>`;
      }).join('');
      return `<div class="kb-row">${keys}</div>`;
    }).join('');
  }

  function setActiveKey(container, letter) {
    $$('.key.active', container).forEach(k => k.classList.remove('active'));
    if (!letter) return;
    const node = $(`.key[data-key="${letter.toUpperCase()}"]`, container);
    if (node) node.classList.add('active');
  }

  function flashKey(container, letter, cls) {
    const node = $(`.key[data-key="${letter.toUpperCase()}"]`, container);
    if (!node) return;
    node.classList.add(cls || 'hit');
    setTimeout(() => node.classList.remove(cls || 'hit'), 260);
  }

  /* ------------------------------------------------------------ 练习台 */
  const CHAR_POOLS = [
    { id: 'jm1', name: '一级简码' },
    { id: 'jm2', name: '二级简码' },
    { id: 'jm3', name: '三级简码' },
    { id: 'jm4', name: '全码字' },
    { id: 'common', name: '常用字' },
    { id: 'common2', name: '扩展常用' },
    { id: 'gb2312', name: '通用字' },
    { id: 'keyname', name: '键名字' },
    { id: 'chengzi', name: '成字字根' },
    { id: 'hard', name: '难拆字' },
    { id: 'errors', name: '错字本' },
  ];

  const WORD_POOLS = [
    { id: 'w2', name: '二字词' },
    { id: 'w3', name: '三字词' },
    { id: 'w4', name: '四字词' },
  ];

  const POOL_NAMES = {};
  CHAR_POOLS.concat(WORD_POOLS).forEach(p => { POOL_NAMES[p.id] = p.name; });
  POOL_NAMES.article = '文章';
  const poolLabel = id => POOL_NAMES[id] || id;

  function shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    }
    return arr;
  }

  /* ------------------------------------------------------------ 学习状态出题 */
  const BUCKET_ORDER = ['error', 'new', 'low'];
  const BUCKET_TARGET = { error: 0.45, new: 0.45, low: 0.10 };

  // 最大余数法：把 total 按 weights 分配成整数
  function apportion(total, weights) {
    const keys = Object.keys(weights);
    const out = {};
    keys.forEach(k => { out[k] = 0; });
    if (total <= 0) return out;
    const sum = keys.reduce((a, k) => a + weights[k], 0);
    if (sum <= 0) return out;
    const raw = keys.map(k => total * weights[k] / sum);
    let used = 0;
    keys.forEach((k, i) => {
      out[k] = Math.floor(raw[i]);
      used += out[k];
    });
    let remain = total - used;
    const order = keys.map((k, i) => ({ k, frac: raw[i] - Math.floor(raw[i]), i }))
      .sort((a, b) => b.frac - a.frac || a.i - b.i);
    for (let i = 0; i < remain; i++) out[order[i % order.length].k]++;
    return out;
  }

  function buildGroups(items, statusMap) {
    const groups = { error: [], new: [], low: [] };
    items.forEach(item => {
      const s = statusMap && statusMap[item];
      if (!s) groups.new.push(item);
      else if (s.status === 'low') groups.low.push(item);
      else if (s.status === 'error') groups.error.push(item);
      // mastered 跳过
    });
    return groups;
  }

  // 45% / 45% / 10%，某桶不足时按比例把余量分给其它桶
  function sampleBuckets(groups, total) {
    const caps = {};
    BUCKET_ORDER.forEach(k => { caps[k] = (groups[k] || []).length; });
    const capTotal = BUCKET_ORDER.reduce((a, k) => a + caps[k], 0);
    const n = Math.min(total, capTotal);
    if (n <= 0) return [];

    const quotas = apportion(n, BUCKET_TARGET);
    const take = {};
    let leftover = 0;
    BUCKET_ORDER.forEach(k => {
      take[k] = Math.min(quotas[k], caps[k]);
      leftover += quotas[k] - take[k];
    });

    let guard = 0;
    while (leftover > 0 && guard++ < 20) {
      const avail = BUCKET_ORDER.filter(k => caps[k] > take[k]);
      if (!avail.length) break;
      const weights = {};
      avail.forEach(k => { weights[k] = BUCKET_TARGET[k]; });
      const extra = apportion(leftover, weights);
      let added = 0;
      avail.forEach(k => {
        const add = Math.min(extra[k], caps[k] - take[k]);
        take[k] += add;
        added += add;
      });
      if (!added) break;
      leftover -= added;
    }

    const out = [];
    BUCKET_ORDER.forEach(k => {
      out.push(...shuffle((groups[k] || []).slice()).slice(0, take[k]));
    });
    return shuffle(out);
  }

  function learningLabel(status, streak) {
    if (status === 'mastered') return '已掌握';
    if (status === 'low') return `低频 ${streak}/3`;
    if (status === 'error') return `错题 ${streak}/3`;
    return '';
  }

  // 仅在 ?__test 时暴露，便于检查分桶比例；正常页面不挂全局
  if (new URLSearchParams(location.search).has('__test')) {
    window.__wubiSample = { apportion, sampleBuckets };
  }

  class Trainer {
    constructor(viewEl, kind) {
      this.viewEl = viewEl;
      this.kind = kind;                  // 'char' | 'word'
      this.poolId = kind === 'char' ? state.pool : state.wordPool;
      this.bag = [];
      this.round = [];
      this.idx = 0;
      this.pos = 0;
      this.done = 0;
      this.correct = 0;
      this.wrong = 0;
      this.streak = 0;
      this.bestStreak = 0;
      this.startedAt = null;
      this.timer = 0;
      this.locked = false;
      this.item = null;
      this.charError = false;
      this.hintShown = false;
      this.hintUsed = false;
      this.attemptSent = false;
      this.roundTotal = 0;
      this.roundToken = 0;
      this.statusMap = {};
      this.poolCounts = null;
      this.learningOk = true;
      this.errorItems = [];
      this.errorKind = new Map();
      this.advanceTimer = 0;
      this.rootToken = 0;
      this.build();
    }

    build() {
      this.viewEl.innerHTML = `
        <div class="pool-bar"><div class="chips" data-role="pools"></div></div>
        <div class="card stage">
          <div class="stage-head">
            <span class="stage-label" data-role="label">准备开始</span>
            <div class="progress"><i data-role="bar"></i></div>
            <span data-role="count">0 / ${state.perRound}</span>
          </div>
          <div class="pool-stats" data-role="poolStats"></div>
          <div class="char-wrap">
            <div class="char" data-role="char">·</div>
            <div class="char-sub" data-role="sub"></div>
          </div>
          <div class="slots" data-role="slots"></div>
          <div class="hint" data-role="hint">输入五笔编码开始练习</div>
          <div class="root-hint" data-role="rootHint" hidden></div>
          <div class="stage-actions">
            <button class="btn ghost" data-role="skip">跳过</button>
            <button class="btn ghost" data-role="hintBtn" disabled>看提示（空格）</button>
          </div>
          <div class="stage-foot">答错后按 <kbd>空格</kbd> 显示提示 · <kbd>Esc</kbd> 重新开始本轮</div>
        </div>
        <div class="card keyboard-card">
          <div class="kb-head">
            <span>86 版键位 · 五个分区用底色区分</span>
            <span class="kb-legend" data-role="legend"></span>
          </div>
          <div class="kb kb--compact" data-role="kb"></div>
        </div>
        <div class="metrics" data-role="metrics"></div>`;

      this.el = {
        pools: $('[data-role="pools"]', this.viewEl),
        label: $('[data-role="label"]', this.viewEl),
        bar: $('[data-role="bar"]', this.viewEl),
        count: $('[data-role="count"]', this.viewEl),
        poolStats: $('[data-role="poolStats"]', this.viewEl),
        char: $('[data-role="char"]', this.viewEl),
        sub: $('[data-role="sub"]', this.viewEl),
        slots: $('[data-role="slots"]', this.viewEl),
        rootHint: $('[data-role="rootHint"]', this.viewEl),
        hint: $('[data-role="hint"]', this.viewEl),
        kb: $('[data-role="kb"]', this.viewEl),
        legend: $('[data-role="legend"]', this.viewEl),
        metrics: $('[data-role="metrics"]', this.viewEl),
      };

      renderKeyboard(this.el.kb, {});
      this.el.legend.innerHTML = DATA.keys.reduce((acc, k) => {
        if (!acc.includes(k.zoneName)) acc.push(k.zoneName);
        return acc;
      }, []).map(z => {
        const zone = DATA.keys.find(k => k.zoneName === z).zone;
        return `<span><i style="background:var(--z${zone})"></i>${z}</span>`;
      }).join('');

      this.renderPools();
      this.renderMetrics();

      $('[data-role="skip"]', this.viewEl).addEventListener('click', () => this.skip());
      this.hintBtn = $('[data-role="hintBtn"]', this.viewEl);
      this.hintBtn.addEventListener('click', () => this.requestHint());
      window.addEventListener('keydown', e => this.onKey(e));
      this.startRound();
    }

    get pools() { return this.kind === 'char' ? CHAR_POOLS : WORD_POOLS; }

    poolSize(id) {
      if (this.kind === 'char') {
        if (id === 'errors') return state.errors.length;
        return (DATA.pools[id] || []).length;
      }
      return id === 'w2' ? state.words2.length : id === 'w3' ? state.words3.length : state.words4.length;
    }

    poolName(id) {
      const p = this.pools.find(x => x.id === id);
      return p ? p.name : id;
    }

    renderPools() {
      this.el.pools.innerHTML = this.pools.map(p => {
        const n = this.poolSize(p.id);
        return `<button type="button" class="chip${p.id === this.poolId ? ' on' : ''}" data-pool="${p.id}"${n ? '' : ' disabled'}>
          ${p.name}<span class="n">${n}</span></button>`;
      }).join('');
      $$('.chip', this.el.pools).forEach(chip => {
        chip.addEventListener('click', () => {
          if (chip.disabled) return;
          this.poolId = chip.dataset.pool;
          if (this.kind === 'char') state.pool = this.poolId; else state.wordPool = this.poolId;
          $$('.chip', this.el.pools).forEach(c => c.classList.toggle('on', c === chip));
          this.startRound();
        });
      });
    }

    poolSource() {
      if (this.kind === 'char') return (DATA.pools[this.poolId] || []).slice();
      return (this.poolId === 'w2' ? state.words2
        : this.poolId === 'w3' ? state.words3 : state.words4).slice();
    }

    async startRound() {
      const token = ++this.roundToken;
      clearInterval(this.timer);
      clearTimeout(this.advanceTimer);
      this.bag = [];
      this.roundTotal = 0;
      this.pos = 0;
      this.done = 0;
      this.correct = 0;
      this.wrong = 0;
      this.streak = 0;
      this.bestStreak = 0;
      this.startedAt = null;
      this.locked = true;
      this.item = null;
      this.attemptSent = false;
      this.statusMap = {};
      this.poolCounts = null;
      this.learningOk = true;
      this.el.bar.style.width = '0%';
      this.el.count.textContent = '…';
      this.el.char.textContent = '·';
      this.el.char.className = 'char';
      this.el.slots.innerHTML = '';
      this.el.sub.innerHTML = '';
      this.hideRootHint();
      this.el.hint.className = 'hint';
      this.el.hint.textContent = '正在载入学习状态…';
      this.el.label.textContent = '正在准备…';
      this.renderMetrics();
      this.renderPoolStats();

      let source = [];
      try {
        if (this.poolId === 'errors') {
          const data = await fetchJSON('/api/errors');
          if (token !== this.roundToken) return;
          this.errorItems = data.errors || [];
          state.errors = this.errorItems;
          this.errorKind = new Map(this.errorItems.map(e => [e.item, e.kind]));
          source = this.errorItems.map(e => e.item);
          this.poolCounts = { total: source.length, error: source.length };
        } else {
          const data = await fetchJSON('/api/learning?pool=' + encodeURIComponent(this.poolId));
          if (token !== this.roundToken) return;
          this.statusMap = data.items || {};
          this.poolCounts = data.counts || null;
          source = this.poolSource();
        }
      } catch (e) {
        if (token !== this.roundToken) return;
        this.learningOk = false;
        this.statusMap = {};
        this.poolCounts = null;
        source = this.poolId === 'errors'
          ? (state.errors || []).map(x => x.item)
          : this.poolSource();
        toast('学习状态不可用：本轮按均匀出题，不记录进度');
      }

      let sample;
      if (this.poolId === 'errors') {
        sample = shuffle(source.slice()).slice(0, Math.min(state.perRound, source.length));
      } else {
        sample = sampleBuckets(buildGroups(source, this.statusMap), state.perRound);
      }
      if (token !== this.roundToken) return;

      this.bag = sample.slice();
      this.roundTotal = sample.length;
      this.renderPoolStats();
      this.el.count.textContent = `0 / ${this.roundTotal}`;
      this.el.bar.style.width = '0%';
      if (!this.roundTotal) {
        this.showEmpty();
        return;
      }
      this.timer = setInterval(() => this.tick(), 500);
      this.nextItem();
    }

    showEmpty() {
      this.locked = true;
      this.hideRootHint();
      this.el.char.textContent = this.poolId === 'errors' ? '空' : '✓';
      this.el.char.className = 'char ok';
      this.el.slots.innerHTML = '';
      this.el.count.textContent = '0 / 0';
      this.el.bar.style.width = '100%';
      this.el.sub.innerHTML = '';
      this.el.hint.className = 'hint';
      if (this.poolId === 'errors') {
        this.el.hint.textContent = '错题本为空：先在其它科目练出错题，或到统计页重置学习进度';
      } else {
        const total = this.poolCounts ? this.poolCounts.total : 0;
        this.el.hint.textContent = `本科目已全部掌握（${total}/${total}），可在统计页重置本科目进度`;
      }
      this.renderMetrics();
    }

    renderPoolStats() {
      if (!this.el.poolStats) return;
      if (this.poolId === 'errors') {
        const n = (state.errors || []).length;
        this.el.poolStats.innerHTML = `错题视图 · <b>${n}</b> 项` +
          (state.autoHint ? ' · 初学模式不记录学习进度' : '');
        return;
      }
      const c = this.poolCounts;
      if (!c) {
        this.el.poolStats.textContent = this.learningOk ? '学习进度读取中…' : '学习状态不可用（本轮不记录）';
        return;
      }
      this.el.poolStats.innerHTML = `本科：新 <b>${c.new}</b> · 错 <b>${c.error}</b> · ` +
        `低频 <b>${c.low}</b> · 已掌握 <b>${c.mastered}</b>` +
        (state.autoHint ? ' · 初学模式不记录学习进度' : '');
    }

    drawItem() {
      const text = this.bag.pop();
      if (!text) return null;
      const kind = this.poolId === 'errors'
        ? (this.errorKind.get(text) || 'char')
        : this.kind;
      if (kind === 'char') {
        const d = DATA.chars[text];
        if (!d) return null;
        const code = state.mode === 'full' ? d.f : d.s;
        return { text, code, short: d.s, full: d.f, kind: 'char' };
      }
      const code = DATA.words[text];
      if (!code) return null;
      return { text, code, short: code, full: code, kind: 'word' };
    }

    nextItem(first) {
      this.hideRootHint();
      const item = this.drawItem();
      if (!item) {
        if (this.done >= this.roundTotal) this.endRound();
        else this.el.hint.textContent = '本轮题目已用完';
        return;
      }
      this.item = item;
      this.pos = 0;
      this.locked = false;
      this.charError = false;
      this.hintShown = state.autoHint;
      this.hintUsed = false;
      this.attemptSent = false;
      this.el.char.textContent = item.text;
      this.el.char.className = 'char' + (item.kind === 'word' ? ' word' : '');
      this.el.char.classList.add('pop');
      setTimeout(() => this.el.char.classList.remove('pop'), 340);
      this.el.sub.innerHTML = '';
      this.el.hint.className = 'hint';
      this.renderSlots();
      this.updateHint();
      this.updateHintBtn();
      this.el.label.textContent = `${this.poolName(this.poolId)} · 第 ${this.done + 1} / ${this.roundTotal} ${this.poolId === 'errors' ? '项' : this.kind === 'char' ? '字' : '词'}`;
    }

    renderSlots() {
      const code = this.item.code;
      this.el.slots.innerHTML = Array.from(code).map((ch, i) => {
        const filled = i < this.pos;
        const cur = i === this.pos && !this.locked;
        return `<div class="slot${filled ? ' filled' : ''}${cur ? ' current' : ''}${this.locked ? ' done' : ''}">
          <span class="idx">${i + 1}</span>${filled ? ch.toUpperCase() : ''}</div>`;
      }).join('');
    }

    hintVisible() {
      return state.autoHint || this.hintShown;
    }

    updateHint() {
      if (!this.item || this.locked) return;
      const expected = this.item.code[this.pos];
      if (!expected) return;
      const posLabel = `第 ${this.pos + 1} 码`;
      if (!this.hintVisible()) {
        this.el.hint.className = this.charError ? 'hint err' : 'hint';
        this.el.hint.innerHTML = this.charError
          ? `${posLabel} · 按 <span class="keycap">空格</span> 查看提示`
          : `${posLabel} · 输入五笔编码`;
        setActiveKey(this.el.kb, '');
        return;
      }
      const k = keyInfo(expected);
      this.el.hint.className = 'hint';
      this.el.hint.innerHTML = `${posLabel} · 按 <span class="keycap">${expected.toUpperCase()}</span> ${k.name}键 —— ${k.rhyme}`;
      setActiveKey(this.el.kb, expected);
    }

    updateHintBtn() {
      if (!this.hintBtn) return;
      this.hintBtn.disabled = this.locked || this.hintVisible() || !this.charError;
    }

    hideRootHint() {
      this.rootToken++;
      if (!this.el.rootHint) return;
      this.el.rootHint.hidden = true;
      this.el.rootHint.innerHTML = '';
    }

    async renderRootHint() {
      if (!this.el.rootHint) return;
      if (!this.charError || !this.item) { this.hideRootHint(); return; }
      const token = ++this.rootToken;
      const chars = this.item.kind === 'char' ? [this.item.text] : [...this.item.text];
      await loadCharRoots();
      if (token !== this.rootToken || !this.charError || !this.item) return;
      this.el.rootHint.innerHTML = rootBlockHTML(chars);
      this.el.rootHint.hidden = false;
    }

    requestHint() {
      if (this.locked || !this.item || this.hintVisible()) return;
      if (!this.charError) {
        toast('先自己拆。答错一次后，按空格就能看到这一码的提示');
        return;
      }
      this.hintShown = true;
      this.hintUsed = true;
      this.sendAttempt('error', 'hint');
      this.updateHint();
      this.updateHintBtn();
      toast('提示已显示，照着按就行');
    }

    sendAttempt(result, reason) {
      if (state.autoHint || !this.learningOk || this.attemptSent || !this.item) return;
      this.attemptSent = true;
      const item = this.item.text;
      const kind = this.item.kind;
      const pool = this.poolId;
      fetch('/api/attempt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pool, item, kind, result, reason }),
      }).then(res => (res.ok ? res.json() : null)).then(data => {
        if (data) this.applyAttempt(data, item, kind);
      }).catch(() => { /* 离线时忽略，练习继续 */ });
    }

    applyAttempt(data, item, kind) {
      if (data.pool === 'errors') {
        const still = !!data.stillError;
        if (!still) {
          state.errors = (state.errors || []).filter(e => !(e.item === item && e.kind === kind));
          this.errorItems = (this.errorItems || []).filter(e => !(e.item === item && e.kind === kind));
          this.bag = this.bag.filter(x => x !== item);
          if (trainers[0]) trainers[0].renderPools();
          toast(`「${item}」已掌握，移出错题本`);
        } else {
          [this.errorItems, state.errors].forEach(list => {
            const entry = (list || []).find(e => e.item === item && e.kind === kind);
            if (entry) entry.sources = data.sources || entry.sources;
          });
        }
        const maxStreak = (data.sources || []).reduce((a, s) => Math.max(a, s.streak || 0), 0);
        this.tagAttempt(item, still ? `错题 ${maxStreak}/3` : '已掌握');
        return;
      }
      const s = { status: data.status, streak: data.streak, errorCount: data.errorCount };
      this.statusMap[item] = s;
      if (data.counts) this.poolCounts = data.counts;
      this.renderPoolStats();
      if (data.status === 'error' || data.mastered) refreshErrors();
      if (data.mastered) {
        this.bag = this.bag.filter(x => x !== item);
        toast(`「${item}」连续 3 次全对，已掌握`);
      }
      this.tagAttempt(item, learningLabel(s.status, s.streak));
    }

    tagAttempt(item, label) {
      if (!label || !this.item || this.item.text !== item || !this.el.sub) return;
      $$('.tag.learn', this.el.sub).forEach(x => x.remove());
      this.el.sub.insertAdjacentHTML('beforeend', `<span class="tag alt learn">${label}</span>`);
    }

    onKey(e) {
      if (state.view !== (this.kind === 'char' ? 'five' : 'words')) return;
      if (state.modalOpen) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        this.requestHint();
        return;
      }
      const k = e.key.toLowerCase();
      if (!/^[a-z]$/.test(k)) return;
      e.preventDefault();
      this.input(k);
    }

    input(letter) {
      if (this.locked || !this.item) return;
      const expected = this.item.code[this.pos];
      if (!expected) return;
      if (this.startedAt === null) this.startedAt = Date.now();
      if (letter === expected) {
        this.correct++;
        this.streak++;
        this.bestStreak = Math.max(this.bestStreak, this.streak);
        this.pos++;
        beep('ok');
        flashKey(this.el.kb, letter, 'hit');
        if (this.pos >= this.item.code.length) {
          this.complete();
        } else {
          this.renderSlots();
          this.updateHint();
        }
        this.renderMetrics();
      } else {
        this.wrong++;
        this.streak = 0;
        beep('bad');
        this.charError = true;
        this.sendAttempt('error', 'wrong');
        this.renderRootHint();
        flashKey(this.el.kb, letter, 'wrong');
        toast('按错了 · 按空格查看提示', true);
        this.updateHint();
        this.updateHintBtn();
        this.renderMetrics();
      }
    }

    complete() {
      this.locked = true;
      this.hideRootHint();
      this.done++;
      this.renderSlots();
      this.el.char.classList.add('ok');
      setActiveKey(this.el.kb, '');
      this.updateHintBtn();
      const item = this.item;
      const tags = [];
      if (item.kind === 'char') {
        if (DATA.jm1.has(item.text)) tags.push('一级简码');
        else if (item.short.length < 4) tags.push('简码');
        if (DATA.keyname.has(item.text)) tags.push('键名字');
        if (DATA.chengzi.has(item.text)) tags.push('成字字根');
        if (item.full !== item.code) tags.push(`全码 ${item.full.toUpperCase()}`);
      } else {
        tags.push(`编码 ${item.code.toUpperCase()}`);
        const rule = { 2: '二字词取各字前两码', 3: '三字词取前两字首码 + 末字前两码', 4: '四字词各取首码' }[item.text.length];
        if (rule) tags.push(rule);
      }
      this.el.sub.innerHTML = tags.map(t => `<span class="tag">${t}</span>`).join('');
      if (!state.autoHint && !this.charError && !this.hintUsed) {
        this.sendAttempt('perfect', 'ok');
      }
      this.el.hint.className = 'hint';
      this.el.hint.innerHTML = `✓ 完成 · ${item.code.toUpperCase()}${this.item.full !== this.item.code ? `（全码 ${this.item.full.toUpperCase()}）` : ''}`;
      this.el.count.textContent = `${this.done} / ${this.roundTotal}`;
      this.el.bar.style.width = Math.min(100, this.done / this.roundTotal * 100) + '%';
      this.renderMetrics();

      this.advanceTimer = setTimeout(() => {
        this.el.char.classList.remove('ok');
        if (this.done >= this.roundTotal) this.endRound();
        else this.nextItem();
      }, 500);
    }

    skip() {
      if (!this.item || this.locked) return;
      this.locked = true;
      this.hideRootHint();
      this.sendAttempt('error', 'skip');
      toast(`已跳过「${this.item.text}」，编码 ${this.item.code.toUpperCase()}`);
      this.done++;
      this.el.count.textContent = `${this.done} / ${this.roundTotal}`;
      this.el.bar.style.width = Math.min(100, this.done / this.roundTotal * 100) + '%';
      this.renderMetrics();
      if (this.done >= this.roundTotal) this.endRound();
      else this.nextItem();
    }

    tick() {
      if (state.view !== (this.kind === 'char' ? 'five' : 'words')) return;
      this.renderMetrics();
    }

    elapsed() {
      return this.startedAt ? (Date.now() - this.startedAt) / 1000 : 0;
    }

    speed() {
      const t = this.elapsed();
      return t > 1 ? this.done / (t / 60) : 0;
    }

    accuracy() {
      const total = this.correct + this.wrong;
      return total ? this.correct / total * 100 : 100;
    }

    renderMetrics() {
      const t = Math.floor(this.elapsed());
      const mm = String(Math.floor(t / 60)).padStart(2, '0');
      const ss = String(t % 60).padStart(2, '0');
      this.el.metrics.innerHTML = `
        <div class="metric"><span>速度</span><b>${fmt(this.speed())}<small>${this.poolId === 'errors' ? '项' : this.kind === 'char' ? '字' : '词'}/分</small></b></div>
        <div class="metric"><span>正确率</span><b>${fmt(this.accuracy(), 1)}<small>%</small></b></div>
        <div class="metric"><span>连击</span><b>${this.streak}<small>最高 ${this.bestStreak}</small></b></div>
        <div class="metric"><span>用时</span><b>${mm}:${ss}</b></div>`;
    }

    async endRound() {
      clearInterval(this.timer);
      setActiveKey(this.el.kb, '');
      const payload = {
        mode: this.kind,
        pool: this.poolId,
        total: this.done,
        correct: this.correct,
        wrong: this.wrong,
        duration: Math.max(1, Math.round(this.elapsed())),
      };
      const acc = this.accuracy();
      const speed = this.speed();
      showSummary({
        title: '本轮完成',
        subtitle: `${this.poolName(this.poolId)} · ${this.done} ${this.poolId === 'errors' ? '项' : this.kind === 'char' ? '字' : '词'}`,
        accuracy: acc,
        speed,
        unit: this.poolId === 'errors' ? '项/分' : this.kind === 'char' ? '字/分' : '词/分',
        duration: payload.duration,
        wrong: this.wrong,
        onAgain: () => { this.startRound(); },
      });
      try {
        const res = await fetch('/api/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          const data = await res.json();
          updateTodayChip(data.todayChars);
          state.stats = data.stats;
          const errs = await fetchJSON('/api/errors').catch(() => null);
          if (errs && errs.errors) {
            state.errors = errs.errors;
            if (trainers[0]) trainers[0].renderPools();
          }
        }
      } catch (e) { /* 离线也可继续练 */ }
    }
  }

  /* ------------------------------------------------------------ 结果弹层 */
  function showSummary(o) {
    const mask = $('#modalMask');
    const card = $('#modalCard');
    const r = 54;
    const c = 2 * Math.PI * r;
    const dash = c * clamp(o.accuracy, 0, 100) / 100;
    card.innerHTML = `
      <h2>${o.title}</h2>
      <p class="m-sub">${o.subtitle}</p>
      <div class="ring-wrap">
        <svg width="150" height="150" viewBox="0 0 150 150">
          <circle cx="75" cy="75" r="${r}" fill="none" stroke="#eee7db" stroke-width="12"></circle>
          <circle cx="75" cy="75" r="${r}" fill="none" stroke="var(--ok)" stroke-width="12"
            stroke-linecap="round" stroke-dasharray="${dash} ${c}" transform="rotate(-90 75 75)"></circle>
        </svg>
        <div class="ring-txt"><b>${fmt(o.accuracy, 1)}%</b><span>正确率</span></div>
      </div>
      <div class="m-stats">
        <div><span>速度</span><b>${fmt(o.speed)}</b><br><small class="muted">${o.unit}</small></div>
        <div><span>用时</span><b>${o.duration}s</b><br><small class="muted">本轮</small></div>
        <div><span>错误</span><b>${o.wrong}</b><br><small class="muted">次</small></div>
      </div>
      <div class="modal-actions">
        <button class="btn primary" data-act="again">${o.againLabel || '再来一轮'}</button>
        <button class="btn" data-act="stats">查看统计</button>
      </div>`;
    mask.hidden = false;
    state.modalOpen = true;
    let closed = false;
    const close = (act) => {
      if (closed) return;
      closed = true;
      mask.hidden = true;
      state.modalOpen = false;
      card.innerHTML = '';
      mask.onclick = null;
      document.removeEventListener('keydown', onEsc);
      // 关闭结算后直接进入下一轮，避免停在已锁定的最后一字；
      // 文章练习用 manualAgain，只有点“重新开始”才重置。
      if (o.onAgain && (!o.manualAgain || act === 'again')) o.onAgain();
    };
    const onEsc = e => { if (e.key === 'Escape') close('esc'); };
    $$('[data-act]', card).forEach(btn => {
      btn.addEventListener('click', () => {
        const act = btn.dataset.act;
        close(act);
        if (act === 'stats') location.hash = '#/stats';
      });
    });
    mask.onclick = e => { if (e.target === mask) close('mask'); };
    document.addEventListener('keydown', onEsc);
  }

  function updateTodayChip(n) {
    if (typeof n === 'number') $('#todayChip').textContent = `今日 ${n} 字`;
  }

  async function refreshErrors() {
    const data = await fetchJSON('/api/errors').catch(() => null);
    if (data && data.errors) {
      state.errors = data.errors;
      trainers.forEach(t => t.renderPools());
    }
  }

  /* ------------------------------------------------------------ 文章练习 */
  const article = {
    mounted: false,
    viewEl: null,
    libraryEl: null,
    practiceEl: null,
    paperEl: null,
    listEl: null,
    fileInput: null,
    id: null,
    data: null,
    units: [],
    pos: 0,
    buffer: '',
    statuses: new Map(),
    unitErrors: new Map(),
    pending: new Map(),
    currentEl: null,
    correct: 0,
    wrong: 0,
    elapsedBase: 0,
    startedAt: null,
    timer: 0,
    saveTimer: 0,
    saving: false,
    saveAgain: false,
    savePromise: null,
    completed: false,
    locked: false,
    font: 19,
    showHint: false,
    warnedUnsupported: false,
    warnedFinish: false,
    token: 0,
    openToken: 0,
    rootToken: 0,
    blockSeq: 0,
    wordCandidates: [],
    pendingSingle: false,

    mount() {
      if (this.mounted) return;
      this.mounted = true;
      this.viewEl = $('#view-article');
      this.viewEl.innerHTML = `
        <div data-role="library">
          <div class="page-head">
            <h1>文章练习</h1>
            <p>导入 txt / docx，按原文排版逐字输入。未输入淡灰，正确黑色，错误红色；中文可按单字或词组五笔码输入，标点按提示键。</p>
          </div>
          <div class="card article-import-card">
            <div class="article-drop" data-role="drop">
              <div class="article-drop-icon">＋</div>
              <div>
                <h2>导入一篇文章</h2>
                <p>支持 .txt / .docx · 最大 10MB · 单篇最多 20,000 字 · 文件只在本地解析</p>
              </div>
              <button class="btn primary" data-role="importBtn">选择文件</button>
            </div>
          </div>
          <div class="article-list-head">
            <h2>我的文章</h2><span class="muted" data-role="count"></span>
          </div>
          <div class="article-list" data-role="list"></div>
        </div>
        <div data-role="practice" hidden>
          <div class="card article-toolbar">
            <div class="article-title-wrap">
              <h2 data-role="title">文章</h2>
              <p data-role="meta"></p>
            </div>
            <div class="article-tools">
              <button class="btn ghost" data-role="import">导入</button>
              <button class="btn ghost" data-role="hint">提示：关</button>
              <button class="btn ghost" data-role="fontDown" title="缩小字号">A−</button>
              <button class="btn ghost" data-role="fontUp" title="放大字号">A＋</button>
              <button class="btn ghost" data-role="restart">重新开始</button>
            </div>
          </div>
          <div class="article-progress-row">
            <div class="article-progress"><i data-role="bar"></i></div>
            <span data-role="count">0 / 0</span>
          </div>
          <div class="article-layout">
            <div class="article-paper" data-role="paper"></div>
            <aside class="article-side">
              <div class="card article-stat-card">
                <div class="article-stat"><span>速度</span><b data-role="speed">0</b><small>字/分</small></div>
                <div class="article-stat"><span>正确率</span><b data-role="acc">100</b><small>%</small></div>
                <div class="article-stat"><span>错误</span><b data-role="wrong">0</b><small>处</small></div>
                <div class="article-stat"><span>用时</span><b data-role="time">00:00</b><small></small></div>
              </div>
              <div class="card article-legend">
                <h3>文字状态</h3>
                <p><i class="lg lg-gray"></i>未输入（淡灰）</p>
                <p><i class="lg lg-black"></i>已正确（黑色）</p>
                <p><i class="lg lg-red"></i>错误（红色 + 波浪线）</p>
                <p><i class="lg lg-cur"></i>当前光标位置</p>
              </div>
              <div class="card article-hint-card">
                <h3>输入提示</h3>
                <p data-role="hintText">准备开始</p>
                <p class="muted article-hint-note">Tab 跳过本字 · Backspace 删除当前码 · 空格确认单字</p>
              </div>
            </aside>
          </div>
          <div class="card article-root-card" data-role="rootCard" hidden></div>
        </div>
        <input type="file" accept=".txt,.docx" data-role="file" hidden>`;
      this.libraryEl = $('[data-role="library"]', this.viewEl);
      this.practiceEl = $('[data-role="practice"]', this.viewEl);
      this.paperEl = $('[data-role="paper"]', this.viewEl);
      this.rootCard = $('[data-role="rootCard"]', this.viewEl);
      this.listEl = $('[data-role="list"]', this.viewEl);
      this.fileInput = $('[data-role="file"]', this.viewEl);
      this.titleEl = $('[data-role="title"]', this.viewEl);
      this.metaEl = $('[data-role="meta"]', this.viewEl);
      this.barEl = $('[data-role="bar"]', this.viewEl);
      this.countEl = $('[data-role="count"]', this.practiceEl);
      this.speedEl = $('[data-role="speed"]', this.viewEl);
      this.accEl = $('[data-role="acc"]', this.viewEl);
      this.wrongEl = $('[data-role="wrong"]', this.viewEl);
      this.timeEl = $('[data-role="time"]', this.viewEl);
      this.hintEl = $('[data-role="hintText"]', this.viewEl);
      this.hintBtn = $('[data-role="hint"]', this.viewEl);
      this.countListEl = $('[data-role="count"]', this.libraryEl);

      $('[data-role="importBtn"]', this.viewEl).addEventListener('click', e => {
        e.stopPropagation();
        this.pickFile();
      });
      $('[data-role="import"]', this.viewEl).addEventListener('click', () => this.pickFile());
      this.fileInput.addEventListener('change', () => {
        const f = this.fileInput.files && this.fileInput.files[0];
        if (f) this.importFile(f);
        this.fileInput.value = '';
      });
      const drop = $('[data-role="drop"]', this.viewEl);
      drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('drag'); });
      drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
      drop.addEventListener('drop', e => {
        e.preventDefault();
        drop.classList.remove('drag');
        const f = e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) this.importFile(f);
      });
      this.hintBtn.addEventListener('click', () => {
        this.showHint = !this.showHint;
        this.updateHint();
      });
      $('[data-role="fontDown"]', this.viewEl).addEventListener('click', () => this.setFont(-1));
      $('[data-role="fontUp"]', this.viewEl).addEventListener('click', () => this.setFont(1));
      $('[data-role="restart"]', this.viewEl).addEventListener('click', () => this.restart(false));
      window.addEventListener('keydown', e => this.onKey(e));
      window.addEventListener('pagehide', () => this.flush(true));
    },

    async enter(sub) {
      this.mount();
      if (sub) await this.open(sub);
      else this.showLibrary();
    },

    leave() {
      if (!this.mounted) return;
      this.openToken++;
      this.token++;
      this.flush(true);
      this.stopTicker();
    },

    async showLibrary() {
      this.openToken++;
      this.token++;
      this.flush(true);
      this.stopTicker();
      this.id = null;
      this.data = null;
      this.units = [];
      this.paperEl.innerHTML = '';
      this.libraryEl.hidden = false;
      this.practiceEl.hidden = true;
      await this.loadList();
    },

    async loadList() {
      let data;
      try {
        data = await fetchJSON('/api/articles');
      } catch (e) {
        this.listEl.innerHTML = '<div class="article-empty">文章服务不可用，请确认通过 python app.py 启动</div>';
        return;
      }
      const list = data.articles || [];
      this.countListEl.textContent = list.length ? `${list.length} 篇` : '';
      if (!list.length) {
        this.listEl.innerHTML = '<div class="article-empty">还没有文章。先导入一篇 txt 或 docx 吧。</div>';
        return;
      }
      this.listEl.innerHTML = '';
      list.forEach(a => {
        const card = document.createElement('article');
        card.className = 'card article-card';
        const head = document.createElement('div');
        head.className = 'article-card-head';
        const title = document.createElement('h3');
        title.textContent = a.title;
        const del = document.createElement('button');
        del.className = 'btn ghost mini article-del';
        del.textContent = '删除';
        del.addEventListener('click', e => { e.stopPropagation(); this.remove(a); });
        head.append(title, del);
        const meta = document.createElement('p');
        meta.className = 'article-card-meta';
        meta.textContent = `${a.kind === 'docx' ? 'DOCX' : 'TXT'} · ${a.filename} · ${a.charCount} 字`;
        const bar = document.createElement('div');
        bar.className = 'article-mini-bar';
        const fill = document.createElement('i');
        fill.style.width = Math.max(0, Math.min(100, a.percent)) + '%';
        bar.append(fill);
        const foot = document.createElement('div');
        foot.className = 'article-card-foot';
        foot.innerHTML = `<span>${a.completed ? '已完成' : a.percent ? '已输入 ' + a.percent + '%' : '未开始'}</span><span class="muted">${a.updated || a.created || ''}</span>`;
        card.append(head, meta, bar, foot);
        card.addEventListener('click', () => { location.hash = '#/article/' + a.id; });
        this.listEl.append(card);
      });
    },

    pickFile() { this.fileInput.value = ''; this.fileInput.click(); },

    importFile(file) {
      const name = file.name || '';
      if (!/\.(txt|docx)$/i.test(name)) { toast('只支持 .txt 或 .docx 文件', true); return; }
      if (file.size > 10 * 1024 * 1024) { toast('文件超过 10MB', true); return; }
      const reader = new FileReader();
      reader.onload = () => { this.uploadFile(name, reader.result); };
      reader.onerror = () => toast('文件读取失败', true);
      reader.readAsDataURL(file);
    },

    async uploadFile(name, dataUrl, force = false) {
      const data = String(dataUrl).split(',')[1] || '';
      toast('正在解析文章…');
      let res, body;
      try {
        res = await fetch('/api/articles', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: name, data, force: !!force }),
        });
        body = await res.json().catch(() => ({}));
      } catch (e) {
        toast('上传失败，请确认服务已启动', true);
        return;
      }
      if (!res.ok) { toast(body.error || '文章解析失败', true); return; }
      if (body.duplicate && !force) {
        const openOld = window.confirm('这篇文章已导入过。\n确定：打开原文章；取消：新建一份副本。');
        if (!openOld) { this.uploadFile(name, dataUrl, true); return; }
      }
      const a = body.article;
      if (!a) { toast('文章数据为空', true); return; }
      toast(body.duplicate ? '已打开原文章' : '文章已导入');
      const target = '#/article/' + a.id;
      if (location.hash === target) this.open(a.id);
      else location.hash = target;
    },

    async remove(a) {
      if (!window.confirm(`删除「${a.title}」及其练习进度？`)) return;
      try {
        const res = await fetch('/api/articles/' + a.id, { method: 'DELETE' });
        if (!res.ok) throw new Error('delete');
        toast('文章已删除');
        if (this.id === a.id) {
          if (location.hash === '#/article') this.showLibrary();
          else location.hash = '#/article';
        } else this.loadList();
      } catch (e) { toast('删除失败', true); }
    },

    async open(id) {
      if (!/^[0-9a-f]{32}$/.test(id)) { location.hash = '#/article'; return; }
      const token = ++this.openToken;
      if (this.id !== id) this.flush(true);
      let data;
      try {
        const res = await fetch('/api/articles/' + id, { cache: 'no-store' });
        if (token !== this.openToken) return;
        if (res.status === 404) { toast('文章不存在', true); location.hash = '#/article'; return; }
        if (!res.ok) throw new Error('load');
        data = await res.json();
      } catch (e) {
        if (token === this.openToken) toast('文章读取失败', true);
        return;
      }
      if (token !== this.openToken) return;
      this.id = id;
      this.data = data;
      this.titleEl.textContent = data.title || '文章';
      this.metaEl.textContent = `${data.kind === 'docx' ? 'DOCX' : 'TXT'} · ${data.filename || ''} · ${data.charCount || 0} 字`;
      this.buildPaper();
      this.applyProgress();
      this.libraryEl.hidden = true;
      this.practiceEl.hidden = false;
      this.updateMetrics();
    },

    buildPaper() {
      this.token++;
      this.hideRootCard();
      this.units = [];
      this.blockSeq = 0;
      this.wordCandidates = [];
      this.pendingSingle = false;
      this.pos = 0;
      this.buffer = '';
      this.statuses.clear();
      this.unitErrors.clear();
      this.pending.clear();
      this.correct = 0;
      this.wrong = 0;
      this.elapsedBase = 0;
      this.startedAt = null;
      this.completed = false;
      this.locked = false;
      this.currentEl = null;
      this.warnedUnsupported = false;
      this.warnedFinish = false;
      const frag = document.createDocumentFragment();
      this.renderBlocks((this.data.doc && this.data.doc.blocks) || [], frag);
      this.paperEl.replaceChildren(frag);
      this.paperEl.classList.remove('article-completed');
      this.paperEl.style.setProperty('--article-font-size', this.font + 'px');
      this.startTicker();
    },

    renderBlocks(blocks, parent) {
      blocks.forEach(b => {
        if (!b || !b.type) return;
        if (b.type === 'p') {
          const p = document.createElement('p');
          p.className = 'ap';
          const blockId = this.blockSeq++;
          if (b.heading) p.classList.add('article-h');
          if (b.list) p.classList.add('article-list-p');
          if (b.preserve) p.classList.add('preserve');
          if (b.align) p.style.textAlign = b.align;
          if (b.indentLeft) p.style.marginLeft = b.indentLeft + 'pt';
          if (b.indentRight) p.style.marginRight = b.indentRight + 'pt';
          if (typeof b.indentFirst === 'number') p.style.textIndent = b.indentFirst + 'pt';
          if (b.spaceBefore) p.style.marginTop = b.spaceBefore + 'pt';
          if (b.spaceAfter) p.style.marginBottom = b.spaceAfter + 'pt';
          if (b.lineHeight) p.style.lineHeight = b.lineHeight;
          if (b.lineHeightPt) p.style.lineHeight = b.lineHeightPt + 'pt';
          if (b.list) {
            const mark = document.createElement('span');
            mark.className = 'article-list-mark';
            mark.textContent = (b.list === 'number' ? '– ' : '• ');
            p.append(mark);
          }
          (b.runs || []).forEach(r => this.renderRun(r, p, blockId));
          if (!p.childNodes.length) {
            p.classList.add('article-empty-p');
            p.append(document.createTextNode('\u00a0'));
          }
          parent.append(p);
          return;
        }
        if (b.type === 'table') {
          const table = document.createElement('table');
          table.className = 'article-table';
          const tbody = document.createElement('tbody');
          (b.rows || []).forEach(row => {
            const tr = document.createElement('tr');
            (row || []).forEach(cell => {
              const td = document.createElement('td');
              this.renderBlocks((cell && cell.blocks) || [], td);
              tr.append(td);
            });
            tbody.append(tr);
          });
          table.append(tbody);
          parent.append(table);
          return;
        }
        if (b.type === 'pageBreak') {
          const hr = document.createElement('hr');
          hr.className = 'article-pagebreak';
          parent.append(hr);
          return;
        }
        if (b.type === 'image') {
          this.appendImage(b, parent);
        }
      });
    },

    appendImage(run, parent) {
      const img = document.createElement('img');
      img.className = 'article-image';
      img.src = run.src;
      img.alt = '';
      img.loading = 'lazy';
      if (run.width) img.style.width = Math.min(1200, run.width) + 'px';
      parent.append(img);
    },

    renderRun(run, parent, blockId) {
      if (run.type === 'image') { this.appendImage(run, parent); return; }
      const text = run.text || '';
      for (const ch of text) {
        if (ch === '\n' || ch === '\r') {
          parent.append(document.createTextNode('\n'));
          continue;
        }
        if (ch === '\t') {
          parent.append(document.createTextNode('\t'));
          continue;
        }
        const span = document.createElement('span');
        span.className = 'ach untyped';
        span.dataset.pos = String(this.units.length);
        span.textContent = ch;
        if (run.bold) span.style.fontWeight = '700';
        if (run.italic) span.style.fontStyle = 'italic';
        if (run.underline) span.style.textDecoration = 'underline';
        if (run.size) span.style.fontSize = run.size + 'pt';
        if (run.font) span.style.fontFamily = `"${run.font}","SimSun",serif`;
        const unit = this.makeUnit(ch, this.units.length, span, blockId);
        this.units.push(unit);
        parent.append(span);
      }
    },

    makeUnit(ch, pos, span, blockId) {
      const base = { pos, text: ch, el: span, errors: 0, block: blockId };
      // 标点优先：chars.json 里也收录了全角标点（zz 占位码），文章里应按标点键输入
      if (PUNCT_KEYS[ch] !== undefined) {
        return { ...base, kind: 'punct', key: PUNCT_KEYS[ch] };
      }
      if (CJK_PUNCT_RE.test(ch)) {
        span.classList.add('unsupported');
        span.title = '未配置按键的标点，自动跳过';
        return { ...base, kind: 'unsupported' };
      }
      if (DATA.chars[ch]) {
        const d = DATA.chars[ch];
        const code = state.mode === 'full' ? d.f : d.s;
        return { ...base, kind: 'hanzi', code, full: d.f, short: d.s };
      }
      if (ch === ' ' || ch === '\u00a0') {
        return { ...base, kind: 'space', key: ' ' };
      }
      if (/^[\x21-\x7e]$/.test(ch)) {
        return { ...base, kind: 'ascii', key: ch };
      }
      const codePoint = ch.charCodeAt(0);
      if (codePoint >= 0xff01 && codePoint <= 0xff5e) {
        return { ...base, kind: 'ascii', key: String.fromCharCode(codePoint - 0xfee0) };
      }
      span.classList.add('unsupported');
      span.title = '未收录的字，自动跳过';
      return { ...base, kind: 'unsupported' };
    },

    applyProgress() {
      const p = (this.data && this.data.progress) || {};
      this.correct = Math.max(0, Number(p.correct) || 0);
      this.wrong = Math.max(0, Number(p.wrong) || 0);
      this.elapsedBase = Math.max(0, Number(p.elapsed) || 0);
      this.pos = clamp(Number(p.cursor) || 0, 0, this.units.length);
      (this.data.chars || []).forEach(c => {
        const pos = Number(c.pos);
        if (!Number.isFinite(pos) || pos < 0 || pos >= this.units.length) return;
        const st = c.status === 'error' ? 'error' : 'correct';
        this.statuses.set(pos, st);
        this.unitErrors.set(pos, Math.max(0, Number(c.errors) || 0));
        const el = this.units[pos].el;
        el.classList.remove('untyped');
        el.classList.add(st);
        if (this.units[pos].kind === 'unsupported') el.classList.add('skipped');
      });
      this.completed = this.pos >= this.units.length && this.units.length > 0;
      if (this.completed) {
        this.locked = true;
        this.paperEl.classList.add('article-completed');
        this.currentEl = null;
        this.updateHint();
        this.updateMetrics();
        return;
      }
      this.autoSkipUnsupported();
      if (this.pos < this.units.length) {
        this.setCurrent();
      } else {
        this.completed = true;
        this.locked = true;
        this.updateHint();
      }
      this.updateMetrics();
    },

    autoSkipUnsupported() {
      let skipped = 0;
      while (this.pos < this.units.length && this.units[this.pos].kind === 'unsupported') {
        const u = this.units[this.pos];
        if (!this.statuses.has(this.pos)) {
          this.statuses.set(this.pos, 'correct');
          this.correct++;
          u.el.classList.remove('untyped');
          u.el.classList.add('correct', 'skipped');
          this.pending.set(this.pos, { status: 'correct', errors: 0 });
        }
        this.pos++;
        skipped++;
      }
      if (skipped) {
        this.scheduleSave();
        if (!this.warnedUnsupported) {
          this.warnedUnsupported = true;
          toast(`有 ${skipped} 个未收录字已自动跳过`);
        }
      }
    },

    setCurrent() {
      if (this.currentEl) this.currentEl.classList.remove('current');
      this.hideRootCard();
      if (this.pos >= this.units.length) {
        this.currentEl = null;
        return;
      }
      const u = this.units[this.pos];
      this.currentEl = u.el;
      this.pendingSingle = false;
      this.wordCandidates = this.collectWordCandidates();
      u.el.classList.add('current');
      this.updateHint();
      try {
        u.el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      } catch (e) { /* ignore */ }
    },

    hideRootCard() {
      this.rootToken++;
      if (!this.rootCard) return;
      this.rootCard.hidden = true;
      this.rootCard.innerHTML = '';
    },

    async showRootCard() {
      const u = this.currentUnit();
      if (!this.rootCard || !u || u.kind !== 'hanzi' || this.statuses.get(this.pos) !== 'error') {
        this.hideRootCard();
        return;
      }
      const token = ++this.rootToken;
      await loadCharRoots();
      if (token !== this.rootToken || !this.rootCard) return;
      const cur = this.currentUnit();
      if (!cur || cur.text !== u.text || this.statuses.get(this.pos) !== 'error') return;
      const full = (cur.full || cur.code || '').toLowerCase();
      this.rootCard.innerHTML = `
        <div class="article-root-head"><b>错字纠正</b><span>${escapeHtml(u.text)} · 全码 ${full.toUpperCase()}</span></div>
        <div class="article-root-code">${rootCodeHTML(full)}</div>
        ${rootBlockHTML([u.text])}`;
      this.rootCard.hidden = false;
    },

    currentUnit() {
      return this.pos >= 0 && this.pos < this.units.length ? this.units[this.pos] : null;
    },

    collectWordCandidates() {
      const u = this.currentUnit();
      if (!u || u.kind !== 'hanzi' || this.statuses.has(this.pos)) return [];
      const out = [];
      for (let len = 2; len <= 4; len++) {
        const arr = this.units.slice(this.pos, this.pos + len);
        if (arr.length !== len) break;
        if (arr.some(x => x.kind !== 'hanzi' || x.block !== u.block || this.statuses.has(x.pos))) break;
        const text = arr.map(x => x.text).join('');
        const code = DATA.words[text];
        if (code) out.push({ text, code, length: len });
      }
      return out.sort((a, b) => b.length - a.length);
    },

    onKey(e) {
      if (state.view !== 'article' || !this.practiceEl || this.practiceEl.hidden) return;
      if (state.modalOpen || this.completed || this.locked) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
      if (e.key === 'Backspace') {
        e.preventDefault();
        const cur = this.currentUnit();
        if (this.buffer) this.buffer = this.buffer.slice(0, -1);
        this.pendingSingle = !!(cur && cur.kind === 'hanzi' && this.buffer === cur.code &&
          this.wordCandidates.some(w => w.code.startsWith(this.buffer)));
        this.updateHint();
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        this.skipCurrent();
        return;
      }
      if (e.key === ' ' || e.key === 'Enter') {
        const u = this.currentUnit();
        if (u && u.kind === 'hanzi') {
          e.preventDefault();
          this.commitFromBuffer();
          return;
        }
      }
      if (e.key !== ' ' && e.key.length !== 1) return;
      const u = this.currentUnit();
      if (!u) return;
      if (u.kind === 'hanzi') {
        if (!/^[a-zA-Z]$/.test(e.key)) return;
        e.preventDefault();
        this.inputHanzi(e.key.toLowerCase());
      } else {
        e.preventDefault();
        this.inputLiteral(e.key);
      }
    },

    beginInput() {
      if (this.startedAt === null) this.startedAt = Date.now();
      this.startTicker();
    },

    inputHanzi(key) {
      const u = this.currentUnit();
      if (!u || u.kind !== 'hanzi' || this.locked) return;
      this.beginInput();

      // 单字码已经完整，但当前文章位置还可能是词组开头：
      // 若下一个键能继续词组，就继续；否则先完成单字，再把这个键交给下一个字。
      if (this.pendingSingle) {
        const next = this.buffer + key;
        const continuesWord = this.wordCandidates.some(w => w.code.startsWith(next));
        if (continuesWord) {
          this.pendingSingle = false;
          this.buffer = next;
          this.afterBuffer(u);
          return;
        }
        this.pendingSingle = false;
        this.commitSingle();
        if (this.completed || this.locked) return;
        const nu = this.currentUnit();
        if (!nu) return;
        if (nu.kind === 'hanzi') this.inputHanzi(key);
        else this.inputLiteral(key);
        return;
      }

      const next = this.buffer + key;
      const singlePrefix = u.code.startsWith(next);
      const wordPrefix = this.wordCandidates.some(w => w.code.startsWith(next));
      if (!singlePrefix && !wordPrefix) {
        this.markError();
        return;
      }
      this.buffer = next;
      this.afterBuffer(u);
    },

    afterBuffer(u) {
      const b = this.buffer;
      if (!b) { this.updateHint(); return; }
      const singleExact = b === u.code;
      const exactWords = this.wordCandidates.filter(w => w.code === b);
      const longerWord = this.wordCandidates.some(w => w.code.startsWith(b) && w.code.length > b.length);
      const prefixOk = u.code.startsWith(b) ||
        this.wordCandidates.some(w => w.code.startsWith(b));
      if (!prefixOk) { this.markError(); return; }

      if (exactWords.length && !longerWord) {
        this.commitWord(exactWords[0]);
        return;
      }
      if (singleExact && !longerWord && !exactWords.length) {
        this.commitSingle();
        return;
      }
      if (singleExact) {
        this.pendingSingle = true;
        this.updateHint();
        return;
      }
      if (b.length >= 4) { this.markError(); return; }
      this.updateHint();
    },

    commitFromBuffer() {
      const u = this.currentUnit();
      if (!u || u.kind !== 'hanzi') return;
      const b = this.buffer;
      if (!b) return;
      const exactWord = this.wordCandidates.find(w => w.code === b);
      if (exactWord) { this.commitWord(exactWord); return; }
      if (b === u.code) { this.commitSingle(); return; }
      // 单字码已经完整、但又多按了词组前缀：空格先确认单字，
      // 多余的键顺延给后面的字，避免用户卡在词组前缀里。
      if (b.startsWith(u.code)) {
        const extra = b.slice(u.code.length);
        this.buffer = '';
        this.pendingSingle = false;
        this.commitSingle();
        if (this.completed || this.locked) return;
        for (const ch of extra) {
          const nu = this.currentUnit();
          if (!nu || this.completed || this.locked) break;
          if (nu.kind === 'hanzi') this.inputHanzi(ch.toLowerCase());
          else this.inputLiteral(ch);
        }
        return;
      }
      toast('编码还没输完 · 继续输入，或按 Tab 跳过本字', true);
    },

    commitSingle() {
      this.pendingSingle = false;
      this.buffer = '';
      this.completeCurrent();
    },

    commitWord(word) {
      const u = this.currentUnit();
      if (!u || this.locked) return;
      const arr = this.units.slice(this.pos, this.pos + word.length);
      if (arr.length !== word.length || arr.some(x => this.statuses.has(x.pos))) {
        this.markError();
        return;
      }
      arr.forEach(x => {
        this.statuses.set(x.pos, 'correct');
        this.correct++;
        this.pending.set(x.pos, { status: 'correct', errors: 0 });
        x.el.classList.remove('untyped', 'error', 'current');
        x.el.classList.add('correct');
      });
      this.currentEl = null;
      this.pos += word.length;
      this.buffer = '';
      this.pendingSingle = false;
      this.wordCandidates = [];
      this.beepOk();
      this.scheduleSave();
      this.updateMetrics();
      toast(`词组「${word.text}」`);
      if (this.pos >= this.units.length) { this.finish(); return; }
      this.autoSkipUnsupported();
      if (this.pos >= this.units.length) { this.finish(); return; }
      this.setCurrent();
      this.updateHint();
    },

    inputLiteral(key) {
      const u = this.currentUnit();
      if (!u || u.kind === 'unsupported' || this.locked) return;
      this.beginInput();
      if (key === u.key) this.completeCurrent();
      else this.markError();
    },

    markError() {
      const u = this.currentUnit();
      if (!u) return;
      if (this.statuses.get(this.pos) !== 'error') {
        this.statuses.set(this.pos, 'error');
        this.wrong++;
        this.beepBad();
        this.pending.set(this.pos, { status: 'error', errors: (this.unitErrors.get(this.pos) || 0) + 1 });
      } else {
        this.pending.set(this.pos, { status: 'error', errors: (this.unitErrors.get(this.pos) || 0) + 1 });
      }
      const errors = (this.unitErrors.get(this.pos) || 0) + 1;
      this.unitErrors.set(this.pos, errors);
      u.el.classList.remove('untyped', 'correct');
      u.el.classList.add('error');
      this.buffer = '';
      this.pendingSingle = false;
      this.wordCandidates = [];
      this.showRootCard();
      this.scheduleSave();
      this.updateHint();
      this.updateMetrics();
      toast('按错了 · 重试，或按 Tab 跳过', true);
    },

    completeCurrent() {
      const u = this.currentUnit();
      if (!u || this.locked) return;
      this.hideRootCard();
      const hadError = this.statuses.get(this.pos) === 'error';
      if (!hadError) {
        this.statuses.set(this.pos, 'correct');
        this.correct++;
        u.el.classList.remove('untyped', 'error');
        u.el.classList.add('correct');
      } else {
        u.el.classList.remove('untyped');
        u.el.classList.add('error');
      }
      this.pending.set(this.pos, {
        status: hadError ? 'error' : 'correct',
        errors: this.unitErrors.get(this.pos) || 0,
      });
      u.el.classList.remove('current');
      this.currentEl = null;
      this.pos++;
      this.buffer = '';
      this.pendingSingle = false;
      this.wordCandidates = [];
      this.beepOk();
      this.scheduleSave();
      this.updateMetrics();
      if (this.pos >= this.units.length) {
        this.finish();
        return;
      }
      this.autoSkipUnsupported();
      if (this.pos >= this.units.length) {
        this.finish();
        return;
      }
      this.setCurrent();
      this.updateHint();
    },

    skipCurrent() {
      if (this.locked || this.completed) return;
      this.hideRootCard();
      const u = this.currentUnit();
      if (!u) return;
      if (this.statuses.get(this.pos) !== 'error') {
        this.statuses.set(this.pos, 'error');
        this.wrong++;
      }
      this.unitErrors.set(this.pos, (this.unitErrors.get(this.pos) || 0) + 1);
      this.pending.set(this.pos, {
        status: 'error',
        errors: this.unitErrors.get(this.pos) || 1,
      });
      u.el.classList.remove('untyped', 'correct', 'current');
      u.el.classList.add('error');
      this.currentEl = null;
      this.buffer = '';
      this.pendingSingle = false;
      this.wordCandidates = [];
      this.pos++;
      this.scheduleSave();
      this.updateMetrics();
      toast(`已跳过「${u.text}」`, true);
      if (this.pos >= this.units.length) { this.finish(); return; }
      this.autoSkipUnsupported();
      if (this.pos >= this.units.length) { this.finish(); return; }
      this.setCurrent();
      this.updateHint();
    },

    beepOk() { beep('ok'); },
    beepBad() { beep('bad'); },

    updateHint() {
      if (!this.hintEl) return;
      this.hintBtn.textContent = this.showHint ? '提示：开' : '提示：关';
      if (this.completed) {
        this.hintEl.textContent = '文章已完成 · 可以重新开始';
        return;
      }
      const u = this.currentUnit();
      if (!u) { this.hintEl.textContent = '准备开始'; return; }
      if (u.kind === 'hanzi') {
        const wc = this.wordCandidates[0] || null;
        const wtext = wc ? wc.text : '';
        let s = '';
        if (this.pendingSingle) {
          s = `当前：${u.text} · 单字码已完整 · 空格确认单字`;
          if (wtext) s += ` / 继续输入词组「${wtext}」`;
          if (this.showHint) {
            s += ` · 单字 ${u.code.toUpperCase()}`;
            if (wc) s += ` / 词组 ${wc.code.toUpperCase()}`;
          }
        } else if (this.buffer) {
          s = `当前：${u.text} · 已按 ${this.buffer.toUpperCase()}`;
          if (wtext) s += ` · 继续词组「${wtext}」`;
          if (this.showHint && wc) s += `（${wc.code.toUpperCase()}）`;
          if (this.buffer.startsWith(u.code) && this.buffer.length > u.code.length) {
            s += ' · 空格确认单字';
          }
        } else {
          s = this.showHint
            ? `当前：${u.text} · 编码 ${u.code.toUpperCase()}`
            : `当前：${u.text} · 输入五笔编码`;
          if (wtext) s += ` · 可输入词组「${wtext}」`;
          if (this.showHint && wc) s += `（${wc.code.toUpperCase()}）`;
        }
        this.hintEl.textContent = s;
      } else if (u.kind === 'space') {
        this.hintEl.textContent = '当前：空格 · 按 Space';
      } else if (u.kind === 'punct') {
        this.hintEl.textContent = `当前：${u.text} · 按 ${u.key === ' ' ? 'Space' : u.key}`;
      } else if (u.kind === 'ascii') {
        this.hintEl.textContent = `当前：${u.text} · 按 ${u.key}`;
      } else {
        this.hintEl.textContent = '当前字未收录，自动跳过';
      }
    },

    elapsed() {
      return this.elapsedBase + (this.startedAt ? (Date.now() - this.startedAt) / 1000 : 0);
    },

    speed() {
      const t = this.elapsed();
      const done = this.correct + this.wrong;
      return t > 1 ? done / (t / 60) : 0;
    },

    accuracy() {
      const done = this.correct + this.wrong;
      return done ? this.correct / done * 100 : 100;
    },

    updateMetrics() {
      if (!this.countEl) return;
      const total = this.units.length;
      const done = Math.min(total, this.pos);
      this.countEl.textContent = `${done} / ${total}`;
      this.barEl.style.width = total ? Math.min(100, done / total * 100) + '%' : '0%';
      this.speedEl.textContent = fmt(this.speed());
      this.accEl.textContent = fmt(this.accuracy(), 1);
      this.wrongEl.textContent = String(this.wrong);
      const t = Math.floor(this.elapsed());
      this.timeEl.textContent = `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
    },

    startTicker() {
      if (this.timer) return;
      this.timer = setInterval(() => this.updateMetrics(), 1000);
    },

    stopTicker() {
      clearInterval(this.timer);
      this.timer = 0;
    },

    scheduleSave() {
      if (!this.id || !this.data) return;
      if (this.pending.size >= 20) { this.flush(false); return; }
      clearTimeout(this.saveTimer);
      this.saveTimer = setTimeout(() => this.flush(false), 2000);
    },

    flush(keepalive) {
      clearTimeout(this.saveTimer);
      this.saveTimer = 0;
      if (!this.id || !this.data) return;
      if (!this.pending.size && !keepalive) return;
      this.save(!!keepalive);
    },

    save(keepalive) {
      if (this.saving) { this.saveAgain = true; return; }
      this.saving = true;
      const sent = new Map(this.pending);
      const body = {
        cursor: this.pos,
        correct: this.correct,
        wrong: this.wrong,
        elapsed: Math.max(0, this.elapsed()),
        chars: Array.from(sent.entries()).map(([pos, v]) => ({ pos, status: v.status, errors: v.errors })),
      };
      this.savePromise = fetch('/api/articles/' + this.id + '/progress', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        keepalive,
      }).then(res => {
        if (!res.ok) throw new Error('save');
        sent.forEach((v, pos) => {
          const cur = this.pending.get(pos);
          if (cur && cur.status === v.status && cur.errors === v.errors) this.pending.delete(pos);
        });
      }).catch(() => { /* 下次继续保存 */ }).finally(() => {
        this.saving = false;
        if (this.pending.size) this.scheduleSave();
      });
    },

    setFont(delta) {
      this.font = clamp(this.font + delta, 14, 30);
      this.paperEl.style.setProperty('--article-font-size', this.font + 'px');
    },

    async finish() {
      if (this.completed) return;
      this.completed = true;
      this.locked = true;
      this.hideRootCard();
      const token = this.token;
      this.stopTicker();
      this.flush(true);
      if (this.savePromise) {
        try { await this.savePromise; } catch (e) { /* ignore */ }
      }
      this.flush(true);
      this.paperEl.classList.add('article-completed');
      this.updateHint();
      this.updateMetrics();
      const duration = Math.max(1, Math.round(this.elapsed()));
      const speed = this.speed();
      const acc = this.accuracy();
      try {
        const res = await fetch('/api/articles/' + this.id + '/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            total: this.units.length,
            correct: this.correct,
            wrong: this.wrong,
            duration,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          if (data.stats) {
            state.stats = data.stats;
            updateTodayChip(data.stats.todayChars);
          }
        }
      } catch (e) { /* 离线也能完成 */ }
      if (token !== this.token || state.view !== 'article') return;
      showSummary({
        title: '文章完成',
        subtitle: `${this.data.title} · ${this.units.length} 字`,
        accuracy: acc,
        speed,
        unit: '字/分',
        duration,
        wrong: this.wrong,
        againLabel: '重新开始',
        manualAgain: true,
        onAgain: () => this.restart(true),
      });
    },

    async restart(skipConfirm) {
      if (!skipConfirm && !window.confirm('重新开始会清空这篇文章的进度，确定吗？')) return;
      if (!this.id) return;
      this.flush(true);
      if (this.savePromise) {
        try { await this.savePromise; } catch (e) { /* ignore */ }
      }
      this.pending.clear();
      clearTimeout(this.saveTimer);
      this.stopTicker();
      try {
        const res = await fetch('/api/articles/' + this.id + '/reset', { method: 'POST' });
        if (!res.ok) throw new Error('reset');
      } catch (e) {
        toast('重置失败', true);
        return;
      }
      toast('已重新开始');
      this.data = null;
      await this.open(this.id);
    },
  };


  const roots = {
    selected: 'G',
    drill: false,
    ok: 0,
    bad: 0,
    answer: null,
    lock: false,
    timer: 0,

    mount() {
      this.kb = $('#kbRoots');
      this.detail = $('#keyDetail');
      renderKeyboard(this.kb, { full: true, clickable: true });

      this.kb.addEventListener('click', e => {
        const key = e.target.closest('.key');
        if (!key) return;
        this.select(key.dataset.key);
      });

      $('#drillStart').addEventListener('click', () => this.startDrill());
      $('#drillStop').addEventListener('click', () => this.stopDrill());
      window.addEventListener('keydown', e => this.onKey(e));

      this.select('G');
      this.legend();
    },

    legend() {
      $('#rootsLegend').innerHTML = [1, 2, 3, 4, 5].map(z => {
        const name = DATA.keys.find(k => k.zone === z).zoneName;
        return `<span><i style="background:var(--z${z})"></i>${name}</span>`;
      }).join('');
    },

    select(letter) {
      this.selected = letter;
      $$('.key', this.kb).forEach(k => k.classList.toggle('selected', k.dataset.key === letter));
      const k = keyInfo(letter);
      this.detail.innerHTML = `
        <div class="kd-top">
          <div class="kd-key">${letter}</div>
          <div>
            <h3>${k.name} 键</h3>
            <div class="kd-sub">${k.zoneName} · ${k.zone} 区 · ${k.finger}</div>
          </div>
        </div>
        <div class="kd-rhyme">${k.rhyme}</div>
        <div class="kd-label">常见字根</div>
        <div class="root-chips">${k.roots.map(r => `<span>${r}</span>`).join('')}</div>
        <div class="kd-finger">点键盘上的其他键可以查看对应的字根与口诀。</div>`;
    },

    startDrill() {
      this.drill = true;
      this.ok = 0;
      this.bad = 0;
      this.lock = false;
      this.answer = null;
      $('#drillBody').hidden = false;
      $('#drillStart').hidden = true;
      $('#drillStop').hidden = false;
      this.nextDrill();
    },

    stopDrill() {
      this.drill = false;
      $('#drillBody').hidden = true;
      $('#drillStart').hidden = false;
      $('#drillStop').hidden = true;
      clearTimeout(this.timer);
    },

    nextDrill() {
      if (!this.drill) return;
      this.lock = false;
      const k = DATA.keys[Math.floor(Math.random() * DATA.keys.length)];
      this.answer = k.key;
      $('#drillPrompt').textContent = k.rhyme;
      $('#drillAnswer').innerHTML = '按对应的键 <b>?</b>';
      setActiveKey(this.kb, '');
      this.renderDrillStats();
    },

    renderDrillStats() {
      const total = this.ok + this.bad;
      $('#drillOk').textContent = this.ok;
      $('#drillBad').textContent = this.bad;
      $('#drillAcc').textContent = (total ? this.ok / total * 100 : 100).toFixed(1).replace(/\.0$/, '') + '%';
    },

    onKey(e) {
      if (!this.drill || state.view !== 'roots') return;
      if (state.modalOpen || e.ctrlKey || e.metaKey || e.altKey) return;
      const letter = e.key.toUpperCase();
      if (!/^[A-Z]$/.test(letter)) return;
      e.preventDefault();
      if (this.lock) return;
      if (letter === this.answer) {
        this.ok++;
        beep('ok');
        flashKey(this.kb, letter, 'hit');
        $('#drillAnswer').innerHTML = `✓ 正确：<b>${letter}</b> 键 ${keyInfo(letter).name}`;
        this.lock = true;
        this.renderDrillStats();
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.nextDrill(), 450);
      } else {
        this.bad++;
        beep('bad');
        flashKey(this.kb, letter, 'wrong');
        const k = keyInfo(this.answer);
        $('#drillAnswer').innerHTML = `✗ 应为 <b>${this.answer}</b> 键 ${k.name} —— ${k.rhyme}`;
        setActiveKey(this.kb, this.answer);
        this.lock = true;
        this.renderDrillStats();
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.nextDrill(), 1100);
      }
    },
  };

  /* ------------------------------------------------------------ 字典页 */
  function codeKeyChain(code) {
    return [...code].map(l => {
      const k = keyInfo(l);
      return `<span><b>${l.toUpperCase()}</b>${k.name}</span>`;
    }).join('');
  }

  function charTags(ch) {
    const d = DATA.chars[ch];
    const tags = [];
    if (DATA.jm1.has(ch)) tags.push('一级简码');
    else if (d.s.length < 4) tags.push(`${d.s.length} 级简码`);
    if (DATA.keyname.has(ch)) tags.push('键名字');
    if (DATA.chengzi.has(ch)) tags.push('成字字根');
    return tags.map(t => `<span class="tag alt">${t}</span>`).join('');
  }

  function dictRowChar(ch) {
    const d = DATA.chars[ch];
    if (!d) return '';
    return `<div class="dict-row">
      <div class="dict-char">${ch}</div>
      <div class="dict-info">
        <div class="dict-code">${d.f.toUpperCase()}${d.s !== d.f ? `<small>简码 ${d.s.toUpperCase()}</small>` : '<small>全码</small>'}</div>
        <div class="dict-keys">${codeKeyChain(d.f)}</div>
        <div class="dict-tags">${charTags(ch)}</div>
      </div>
    </div>`;
  }

  function dictRowWord(word) {
    const code = DATA.words[word];
    return `<div class="dict-row">
      <div class="dict-char" style="font-size:26px;letter-spacing:.06em">${word}</div>
      <div class="dict-info">
        <div class="dict-code">${code.toUpperCase()}<small>${word.length} 字词</small></div>
        <div class="dict-keys">${codeKeyChain(code)}</div>
      </div>
    </div>`;
  }

  function renderDict(q) {
    const box = $('#dictResults');
    q = (q || '').trim();
    if (!q) {
      box.innerHTML = '<div class="dict-empty">输入一个汉字、一个词，或者一段五笔编码</div>';
      return;
    }
    if (/^[a-zA-Z]{1,4}$/.test(q)) {
      const code = q.toLowerCase();
      const exactChars = [], prefixChars = [], exactWords = [];
      for (const ch in DATA.chars) {
        const d = DATA.chars[ch];
        if (d.s === code || d.f === code) exactChars.push(ch);
        else if (exactChars.length < 20 && (d.s.startsWith(code) || d.f.startsWith(code)) && d.s.length <= code.length + 1) prefixChars.push(ch);
      }
      for (const w in DATA.words) {
        if (DATA.words[w] === code) exactWords.push(w);
      }
      const rows = [];
      if (exactChars.length) {
        rows.push(`<div class="dict-group-title">编码 ${code.toUpperCase()} · 单字 ${exactChars.length} 个</div>`);
        rows.push(exactChars.slice(0, 40).map(dictRowChar).join(''));
      }
      if (exactWords.length) {
        rows.push(`<div class="dict-group-title">编码 ${code.toUpperCase()} · 词组 ${exactWords.length} 个</div>`);
        rows.push(exactWords.slice(0, 30).map(dictRowWord).join(''));
      }
      if (prefixChars.length) {
        rows.push(`<div class="dict-group-title">以 ${code.toUpperCase()} 开头的单字</div>`);
        rows.push(prefixChars.slice(0, 24).map(dictRowChar).join(''));
      }
      box.innerHTML = rows.length ? rows.join('') : '<div class="dict-empty">没有找到这个编码</div>';
      return;
    }

    const out = [];
    if (q.length > 1 && DATA.words[q]) {
      out.push('<div class="dict-group-title">词组</div>');
      out.push(dictRowWord(q));
    }
    const unknown = [];
    for (const ch of q) {
      if (DATA.chars[ch]) out.push(dictRowChar(ch));
      else if (!/\s/.test(ch)) unknown.push(ch);
    }
    if (!out.length) {
      box.innerHTML = `<div class="dict-empty">码表里没有「${q.slice(0, 12)}」${unknown.length ? '（' + unknown.join('') + '）' : ''}</div>`;
      return;
    }
    if (unknown.length) out.push(`<div class="dict-empty">未收录：${unknown.join(' ')}</div>`);
    box.innerHTML = out.join('');
  }

  function mountDict() {
    const input = $('#dictInput');
    let t = 0;
    input.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => renderDict(input.value), 90);
    });
    $('#dictClear').addEventListener('click', () => {
      input.value = '';
      input.focus();
      renderDict('');
    });
    const quick = ['我', '的', '中国', '五笔', '练习', 'rqyy', 'khlg'];
    $('#dictQuick').innerHTML = quick.map(q => `<button type="button" data-q="${q}">${q}</button>`).join('');
    $('#dictQuick').addEventListener('click', e => {
      const b = e.target.closest('button');
      if (!b) return;
      input.value = b.dataset.q;
      renderDict(b.dataset.q);
      input.focus();
    });
    renderDict('');
  }

  /* ------------------------------------------------------------ 统计页 */
  async function resetLearning(pool) {
    const name = pool ? poolLabel(pool) : '全部科目';
    if (!window.confirm(`确定重置「${name}」的学习进度？\n已掌握、错题、低频状态会清空，历史成绩保留。`)) return;
    try {
      const res = await fetch('/api/learning/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pool ? { pool } : {}),
      });
      if (!res.ok) throw new Error('reset failed');
      toast(`已重置${name}的学习进度`);
      const errs = await fetchJSON('/api/errors').catch(() => null);
      if (errs && errs.errors) {
        state.errors = errs.errors;
        trainers.forEach(t => t.renderPools());
      }
      trainers.forEach(t => {
        if (!pool || t.poolId === pool) t.startRound();
      });
      if (state.view === 'stats') renderStats();
    } catch (e) {
      toast('重置失败，请确认服务已启动', true);
    }
  }

  async function renderStats() {
    let s;
    try {
      s = await fetchJSON('/api/stats');
    } catch (e) {
      $('#statCards').innerHTML = '<div class="dict-empty">统计服务不可用（请通过 python app.py 启动）</div>';
      return;
    }
    state.stats = s;
    updateTodayChip(s.todayChars);

    const cards = [
      ['累计字数', s.totalChars, '字'],
      ['总正确率', fmt(s.accuracy, 1) + '%', ''],
      ['最快速度', fmt(s.bestSpeed), '字/分'],
      ['今日', s.todayChars, '字'],
      ['连续练习', s.streak, '天'],
    ];
    $('#statCards').innerHTML = cards.map(c => `<div class="s-card"><span>${c[0]}</span><b>${c[1]}</b><small>${c[2]}</small></div>`).join('');

    const learning = s.learning || { distinct: {}, pools: [] };
    const d = learning.distinct || {};
    const learnCards = [
      ['已掌握', d.mastered || 0, '字/词'],
      ['错题', d.error || 0, '字/词'],
      ['低频', d.low || 0, '字/词'],
    ];
    $('#learningCards').innerHTML = learnCards.map(c =>
      `<div class="s-card"><span>${c[0]}</span><b>${c[1]}</b><small>${c[2]}</small></div>`).join('');

    const pools = learning.pools || [];
    $('#poolProgress').innerHTML = pools.length ? pools.map(p => {
      const pct = p.total ? Math.round(p.mastered / p.total * 100) : 0;
      return `<div class="pool-row">
        <span class="pool-name">${poolLabel(p.id)}</span>
        <span class="pool-nums">新 ${p.new} · 错 ${p.error} · 低频 ${p.low} · 掌握 ${p.mastered}</span>
        <span class="pool-progress"><i style="width:${pct}%"></i></span>
        <span class="pool-pct">${pct}%</span>
        <button class="btn ghost mini" data-reset="${p.id}">重置</button>
      </div>`;
    }).join('') : '<div class="dict-empty">还没有学习记录</div>';
    $$('#poolProgress [data-reset]').forEach(btn => {
      btn.onclick = () => resetLearning(btn.dataset.reset);
    });

    const recent = s.recent || [];
    $('#recentList').innerHTML = recent.length ? recent.map(r => {
      const acc = (r.correct + r.wrong) ? r.correct / (r.correct + r.wrong) * 100 : 100;
      const modeLabel = r.mode === 'article' ? '文章' : r.mode === 'word' ? '词组' : '单字';
      const unit = r.mode === 'word' ? '词' : '字';
      const what = r.mode === 'article'
        ? `文章练习 · <b>${r.total}</b> ${unit}`
        : `${modeLabel} · ${poolLabel(r.pool)} · <b>${r.total}</b> ${unit}`;
      return `
      <div class="recent-item">
        <span class="when">${r.ts.slice(5, 16)}</span>
        <span class="what">${what}</span>
        <span class="num">${fmt(r.speed)} ${unit}/分 · ${fmt(acc, 0)}%</span>
      </div>`;
    }).join('') : '<div class="dict-empty">还没有练习记录</div>';

    const errs = s.errors || [];
    $('#errCount').textContent = errs.length ? `${errs.length} 项` : '';
    const practiceBtn = $('#practiceErrors');
    practiceBtn.hidden = !errs.length;
    practiceBtn.onclick = () => {
      if (!errs.length) { toast('错题本是空的'); return; }
      const t = trainers[0];
      t.poolId = 'errors';
      state.pool = 'errors';
      t.renderPools();
      t.startRound();
      location.hash = '#/five';
      toast(`错题本专项练习：${errs.length} 项`);
    };
    $('#errorList').innerHTML = errs.length ? errs.map(e => {
      const src = (e.sources || []).map(x => poolLabel(x.pool)).join(' / ');
      return `<button type="button" class="error-chip${e.kind === 'word' ? ' word' : ''}"
        data-item="${e.item}" title="累计错 ${e.errorCount} 次${src ? ' · 来源：' + src : ''}">
        <b>${e.item}</b><span>×${e.errorCount}</span>${src ? `<i>${src}</i>` : ''}
      </button>`;
    }).join('') : '<div class="dict-empty">错题本是空的，很好</div>';
    $$('.error-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        $('#dictInput').value = chip.dataset.item;
        location.hash = '#/dict';
        renderDict(chip.dataset.item);
      });
    });
  }

  /* ------------------------------------------------------------ 设置 / 路由 */
  function applySettingsUI() {
    $$('#optRounds button').forEach(b => b.classList.toggle('on', Number(b.dataset.round) === state.perRound));
    $$('#optMode button').forEach(b => b.classList.toggle('on', b.dataset.mode === state.mode));
    $('#optHint').checked = state.autoHint;
    $('#optSound').checked = state.sound;
  }

  function mountSettings() {
    const panel = $('#settingsPanel');
    $('#settingsBtn').addEventListener('click', e => {
      e.stopPropagation();
      panel.hidden = !panel.hidden;
    });
    document.addEventListener('click', e => {
      if (!panel.hidden && !panel.contains(e.target) && e.target.id !== 'settingsBtn') panel.hidden = true;
    });
    $('#optRounds').addEventListener('click', e => {
      const b = e.target.closest('button');
      if (!b) return;
      state.perRound = Number(b.dataset.round);
      savePrefs();
      applySettingsUI();
      trainers.forEach(t => t.startRound());
      toast(`每轮最多 ${state.perRound} 项`);
    });
    $('#optMode').addEventListener('click', e => {
      const b = e.target.closest('button');
      if (!b) return;
      state.mode = b.dataset.mode;
      savePrefs();
      applySettingsUI();
      if (trainers[0]) trainers[0].startRound();
      toast(state.mode === 'full' ? '已切换为全码模式' : '已切换为简码优先');
    });
    $('#optHint').addEventListener('change', e => {
      state.autoHint = e.target.checked;
      savePrefs();
      trainers.forEach(t => {
        if (!state.autoHint) t.hintShown = false;
        t.updateHint();
        t.updateHintBtn();
        t.renderPoolStats();
      });
    });
    $('#optSound').addEventListener('change', e => {
      state.sound = e.target.checked;
      savePrefs();
    });
    $('#resetAllLearning').addEventListener('click', () => resetLearning(null));
    applySettingsUI();
  }

  const VIEWS = ['five', 'roots', 'words', 'article', 'dict', 'stats'];

  function route() {
    const raw = location.hash.replace(/^#\//, '') || 'five';
    const [idPart, queryPart] = raw.split('?');
    const parts = idPart.split('/');
    const id = parts[0];
    const sub = parts[1] || '';
    const view = VIEWS.includes(id) ? id : 'five';
    state.view = view;
    const pageTitles = {
      five: '看图拆字', roots: '字根口诀', words: '词组练习',
      article: '文章练习', dict: '编码查询', stats: '练习统计',
    };
    document.title = `${pageTitles[view] || '五笔练习'} · 五笔练习`;
    VIEWS.forEach(v => {
      const node = $('#view-' + v);
      if (node) node.classList.toggle('active', v === view);
    });
    $$('#nav a').forEach(a => a.classList.toggle('active', a.dataset.nav === view));
    if (view === 'stats') renderStats();
    if (view === 'dict') {
      const input = $('#dictInput');
      const q = queryPart ? new URLSearchParams(queryPart).get('q') : '';
      if (q) { input.value = q; renderDict(q); }
      input.focus();
    }
    if (view === 'article') article.enter(sub);
    else if (article.mounted) article.leave();
    if (view !== 'roots' && roots.drill) roots.stopDrill();
    if (view === 'five' && trainers[0]) trainers[0].tick();
    if (view === 'words' && trainers[1]) trainers[1].tick();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /* ------------------------------------------------------------ 启动 */
  const trainers = [];

  async function boot() {
    loadPrefs();
    const bootEl = document.createElement('div');
    bootEl.className = 'boot';
    bootEl.textContent = '正在载入五笔码表…';
    $('#main').prepend(bootEl);
    try {
      await loadData();
    } catch (e) {
      bootEl.textContent = '码表载入失败：' + e.message + '（请确认通过 python app.py 启动）';
      return;
    }
    bootEl.remove();

    trainers.push(new Trainer($('#view-five'), 'char'));
    trainers.push(new Trainer($('#view-words'), 'word'));
    roots.mount();
    article.mount();
    mountDict();
    mountSettings();
    setTimeout(() => loadCharRoots(), 1200);

    // Esc：重新开始本轮（设置面板打开时先收起；结算弹层由弹层自己处理）
    document.addEventListener('keydown', e => {
      if (e.key !== 'Escape' || state.modalOpen) return;
      const panel = $('#settingsPanel');
      if (panel && !panel.hidden) { panel.hidden = true; return; }
      if (state.view !== 'five' && state.view !== 'words') return;
      const t = state.view === 'five' ? trainers[0] : trainers[1];
      if (!t) return;
      e.preventDefault();
      t.startRound();
      toast('已重新开始本轮');
    });

    updateTodayChip(state.stats ? state.stats.todayChars : 0);

    window.addEventListener('hashchange', route);
    route();
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
