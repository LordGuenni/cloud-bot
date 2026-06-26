(function() {
  const canvas = document.getElementById('warmind-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // Warmind field configuration options (matching Vue props)
  const props = {
    webNodes: 130,
    emberFrac: 0.16,
    linkDistFrac: 0.085,
    driftSpeed: 16,
    surgeCount: 7,
    maxSparks: 260,
    trail: 0.22,
    backdrop: true,
    core: [56, 18, 0], // Rasputin Orange Core Glow
    edge: [11, 12, 14]  // Deep Bunker Charcoal Background
  };

  let raf = 0;
  let running = false;
  let reduced = false;

  let W = 0, H = 0, DPR = 1, cx = 0, cy = 0, linkDist = 0;
  let last = 0;
  let firstPaint = true;

  let nodes = [];
  let sparks = [];
  let surges = [];

  const rint = (a, b) => a + Math.random() * (b - a);

  function newSurge() {
    const a = Math.floor(rint(0, nodes.length));
    return { a, b: a, p: 1, speed: rint(0.6, 1.6), heat: rint(0.7, 1) };
  }

  function build() {
    nodes = [];
    for (let i = 0; i < props.webNodes; i++) {
      const ang = rint(0, Math.PI * 2);
      const sp = rint(0.4, 1.3) * props.driftSpeed;
      nodes.push({
        x: rint(0, W),
        y: rint(0, H),
        vx: Math.cos(ang) * sp,
        vy: Math.sin(ang) * sp,
        gold: Math.random() < 0.5,
        ember: Math.random() < props.emberFrac,
        flick: rint(0, Math.PI * 2)
      });
    }
    surges = [];
    for (let i = 0; i < props.surgeCount; i++) surges.push(newSurge());
  }

  function resize() {
    const newW = canvas.clientWidth || window.innerWidth;
    const newH = canvas.clientHeight || window.innerHeight;

    // Ignore small vertical resizes (e.g. mobile address bar) to avoid flickering
    if (W === newW && Math.abs(H - newH) < 150 && W > 0) {
      return;
    }

    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = newW;
    H = newH;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    cx = W / 2;
    cy = H / 2;
    linkDist = Math.hypot(W, H) * props.linkDistFrac;
    build();
    firstPaint = true;
  }

  function moveNodes(dt) {
    const m = 40;
    for (const n of nodes) {
      n.x += n.vx * dt;
      n.y += n.vy * dt;
      if (n.x < -m) n.x = W + m;
      else if (n.x > W + m) n.x = -m;
      if (n.y < -m) n.y = H + m;
      else if (n.y > H + m) n.y = -m;
    }
  }

  function spawnSparks() {
    if (reduced) return;
    if (Math.random() < 0.7 && sparks.length < props.maxSparks) {
      const e = nodes.filter(n => n.ember);
      if (e.length) {
        const n = e[Math.floor(Math.random() * e.length)];
        if (n) {
          sparks.push({
            x: n.x + rint(-6, 6),
            y: n.y + rint(-6, 6),
            vx: rint(-14, 14),
            vy: rint(-26, -4),
            life: 0,
            span: rint(0.6, 1.6),
            size: rint(0.8, 2.1),
            type: 'ember'
          });
        }
      }
    }
    if (Math.random() < 0.5 && sparks.length < props.maxSparks) {
      sparks.push({
        x: rint(0, W),
        y: rint(0, H),
        vx: rint(-6, 6),
        vy: rint(-12, -2),
        life: 0,
        span: rint(2.5, 6),
        size: rint(0.6, 1.8),
        type: 'mote'
      });
    }
  }

  function updateSparks(dt) {
    for (const s of sparks) {
      s.life += dt / s.span;
      s.x += s.vx * dt;
      s.y += s.vy * dt;
      if (s.type === 'ember') {
        s.vy += 20 * dt;
        s.vx *= 0.99;
        s.vy *= 0.99;
      }
    }
    sparks = sparks.filter(s => s.life < 1);
  }

  function drawHaze(time) {
    ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < 4; i++) {
      const px = (0.5 + 0.42 * Math.sin(time * 0.13 + i * 1.7)) * W;
      const py = (0.5 + 0.42 * Math.cos(time * 0.11 + i * 2.1)) * H;
      const r = Math.max(W, H) * 0.34;
      const g = ctx.createRadialGradient(px, py, 0, px, py, r);
      g.addColorStop(0, i % 2 === 0 ? 'rgba(255,140,70,0.035)' : 'rgba(120,110,130,0.04)');
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawWebAndAdj(time) {
    const adj = nodes.map(() => []);
    ctx.globalCompositeOperation = 'lighter';
    ctx.lineWidth = 1;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        if (!a || !b) continue;
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < linkDist) {
          adj[i].push(j);
          adj[j].push(i);
          const fade = 1 - d / linkDist;
          const flick = 0.6 + 0.4 * Math.sin(time * 2.2 + a.flick);
          const col = a.gold && b.gold ? '255,200,90' : '255,95,45';
          ctx.strokeStyle = `rgba(${col},${(fade * flick * 0.30).toFixed(3)})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
    for (const n of nodes) {
      const flick = 0.5 + 0.5 * Math.sin(time * 2.6 + n.flick);
      ctx.fillStyle = `rgba(255,225,180,${(0.25 + 0.35 * flick).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(n.x, n.y, 1.1, 0, Math.PI * 2);
      ctx.fill();
    }
    for (const n of nodes) {
      if (!n.ember) continue;
      const pulse = 0.55 + 0.45 * Math.sin(time * 2.4 + n.flick);
      const r = 3 + 2 * pulse;
      const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 4);
      g.addColorStop(0, `rgba(255,240,210,${0.85 * pulse})`);
      g.addColorStop(0.3, `rgba(255,120,50,${0.6 * pulse})`);
      g.addColorStop(1, 'rgba(255,60,20,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r * 4, 0, Math.PI * 2);
      ctx.fill();
    }
    return adj;
  }

  function drawSurges(adj, dt) {
    ctx.globalCompositeOperation = 'lighter';
    for (const s of surges) {
      s.p += s.speed * dt;
      if (s.p >= 1) {
        const nb = adj[s.b];
        if (nb && nb.length) {
          let next = nb[Math.floor(Math.random() * nb.length)];
          if (nb.length > 1) {
            let g = 0;
            while (next === s.a && g++ < 4) next = nb[Math.floor(Math.random() * nb.length)];
          }
          if (next !== undefined) {
            s.a = s.b;
            s.b = next;
            s.p = 0;
          }
        } else {
          Object.assign(s, newSurge());
          continue;
        }
      }
      const A = nodes[s.a], B = nodes[s.b];
      if (!A || !B) {
        Object.assign(s, newSurge());
        continue;
      }
      const x = A.x + (B.x - A.x) * s.p, y = A.y + (B.y - A.y) * s.p;
      const r = 7 * s.heat;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r * 3);
      g.addColorStop(0, `rgba(255,255,255,${0.9 * s.heat})`);
      g.addColorStop(0.3, `rgba(255,200,130,${0.55 * s.heat})`);
      g.addColorStop(1, 'rgba(255,120,40,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(x, y, r * 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = `rgba(255,235,200,${0.5 * s.heat})`;
      ctx.lineWidth = 1.6;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(A.x, A.y);
      ctx.lineTo(x, y);
      ctx.stroke();
    }
  }

  function drawSparks() {
    ctx.globalCompositeOperation = 'lighter';
    for (const s of sparks) {
      const fade = Math.sin(Math.min(s.life, 1) * Math.PI);
      ctx.fillStyle = s.type === 'ember'
        ? `rgba(255,150,70,${(0.85 * fade).toFixed(3)})`
        : `rgba(240,238,255,${(0.45 * fade).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function paintBackdrop() {
    ctx.globalCompositeOperation = 'source-over';
    if (!props.backdrop) {
      ctx.clearRect(0, 0, W, H);
      return;
    }
    if (firstPaint || props.trail <= 0) {
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(W, H) * 0.8);
      g.addColorStop(0, `rgb(${props.core.join(',')})`);
      g.addColorStop(1, `rgb(${props.edge.join(',')})`);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
    } else {
      ctx.fillStyle = `rgba(${props.edge.join(',')},${props.trail})`;
      ctx.fillRect(0, 0, W, H);
    }
  }

  function renderOnce(time, dt) {
    paintBackdrop();
    firstPaint = false;
    if (!reduced) moveNodes(dt);
    drawHaze(time);
    const adj = drawWebAndAdj(time);
    if (!reduced) drawSurges(adj, dt);
    spawnSparks();
    updateSparks(dt);
    drawSparks();
  }

  function frame(now) {
    if (!running) return;
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    renderOnce(now / 1000, dt);
    raf = requestAnimationFrame(frame);
  }

  function start() {
    if (running || reduced) return;
    running = true;
    last = performance.now();
    raf = requestAnimationFrame(frame);
  }

  function stop() {
    running = false;
    cancelAnimationFrame(raf);
  }

  function onVisibility() {
    if (document.hidden) stop();
    else start();
  }

  const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
  reduced = mq.matches;

  const onReducedChange = () => {
    reduced = !!mq.matches;
    if (reduced) {
      stop();
      renderOnce(0, 0);
    } else {
      start();
    }
  };

  if (mq.addEventListener) {
    mq.addEventListener('change', onReducedChange);
  }

  resize();
  const ro = new ResizeObserver(() => resize());
  ro.observe(canvas);
  document.addEventListener('visibilitychange', onVisibility);

  if (reduced) renderOnce(0, 0);
  else start();
})();
