(function () {
  "use strict";

  var TRAIL_COLORS = ["#ff9a2e", "#ffc06b", "#19d3f5", "#5aa8ff"];
  var MAX_PARTICLES = 160;
  var MIN_TRAIL_DISTANCE = 4;
  var MAX_ALPHA = 0.75;
  var reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var canvas = null;
  var context = null;
  var particles = [];
  var animating = false;
  var lastPoint = null;

  function ensureCanvas() {
    if (canvas) { return; }
    canvas = document.createElement("canvas");
    canvas.className = "board-effects-canvas";
    canvas.setAttribute("aria-hidden", "true");
    document.body.appendChild(canvas);
    context = canvas.getContext("2d");
    resize();
    window.addEventListener("resize", resize);
  }

  function resize() {
    var ratio = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * ratio;
    canvas.height = window.innerHeight * ratio;
    canvas.style.width = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function random(min, max) { return min + Math.random() * (max - min); }

  function pick(list) { return list[Math.floor(Math.random() * list.length)]; }

  function spawn(x, y, vx, vy, color, size, life) {
    if (particles.length >= MAX_PARTICLES) { particles.shift(); }
    particles.push({ x: x, y: y, vx: vx, vy: vy, color: color, size: size, life: life, maxLife: life });
  }

  function step() {
    context.clearRect(0, 0, window.innerWidth, window.innerHeight);
    context.shadowBlur = 6;
    particles = particles.filter(function (particle) {
      particle.life -= 16;
      if (particle.life <= 0) { return false; }
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.vx *= 0.96;
      particle.vy *= 0.96;
      var alpha = particle.life / particle.maxLife;
      context.globalAlpha = alpha * MAX_ALPHA;
      context.fillStyle = particle.color;
      context.shadowColor = particle.color;
      context.beginPath();
      context.arc(particle.x, particle.y, particle.size * (0.4 + 0.6 * alpha), 0, Math.PI * 2);
      context.fill();
      return true;
    });
    context.globalAlpha = 1;
    context.shadowBlur = 0;
    if (particles.length) {
      window.requestAnimationFrame(step);
    } else {
      animating = false;
      context.clearRect(0, 0, window.innerWidth, window.innerHeight);
    }
  }

  function animate() {
    if (animating) { return; }
    animating = true;
    window.requestAnimationFrame(step);
  }

  function trail(x, y) {
    if (reducedMotion || (x === 0 && y === 0)) { return; }
    var dx = lastPoint ? x - lastPoint.x : 0;
    var dy = lastPoint ? y - lastPoint.y : 0;
    var distance = Math.hypot(dx, dy);
    if (lastPoint && distance < MIN_TRAIL_DISTANCE) { return; }
    ensureCanvas();
    lastPoint = { x: x, y: y };
    var count = Math.min(4, 1 + Math.round(distance / 10));
    for (var index = 0; index < count; index++) {
      var share = index / count;
      spawn(
        x - dx * share + random(-3, 3),
        y - dy * share + random(-3, 3),
        -dx * 0.08 + random(-0.6, 0.6),
        -dy * 0.08 + random(-0.6, 0.6),
        pick(TRAIL_COLORS),
        random(2, 4.5),
        random(380, 700)
      );
    }
    animate();
  }

  function endTrail() { lastPoint = null; }

  window.BoardEffects = { trail: trail, endTrail: endTrail };
})();
