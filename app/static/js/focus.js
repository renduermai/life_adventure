const clock = document.getElementById('focus-clock');
if (clock) {
  const base = Number(clock.dataset.seconds), start = Date.now(), target = Number(clock.dataset.target), running = clock.dataset.running === 'yes';
  function draw() {
    const elapsed = base + (running ? Math.floor((Date.now() - start) / 1000) : 0);
    const seconds = target ? Math.max(0, target - elapsed) : elapsed;
    const h = String(Math.floor(seconds / 3600)).padStart(2, '0'), m = String(Math.floor(seconds / 60) % 60).padStart(2, '0'), s = String(seconds % 60).padStart(2, '0');
    clock.textContent = `${h}:${m}:${s}`;
  }
  draw(); setInterval(draw, 1000);
}
