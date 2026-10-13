(() => {
  const banner = document.querySelector('[data-forum-banner]');
  if (!banner) return;
  const link = banner.querySelector('[data-forum-banner-link]');
  const text = banner.querySelector('[data-forum-banner-text]');
  const track = banner.querySelector('.forum-banner-track');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let lastId = null;
  let nextTimer;
  let endTimer;
  let loading = false;

  function hide() {
    clearTimeout(endTimer);
    banner.hidden = true;
    clearTimeout(nextTimer);
    nextTimer = setTimeout(showNext, 20000);
  }

  async function showNext() {
    if (loading || document.hidden) return;
    loading = true;
    try {
      // Refresh each time so newly created/deleted posts are reflected.
      const response = await fetch('/api/forum/notices', {cache: 'no-store'});
      if (!response.ok) throw new Error('Feed unavailable');
      const result = await response.json();
      if (document.hidden) return;
      const posts = (result.posts || []).filter((post) => post.url !== window.location.pathname);
      if (!posts.length) {
        hide();
        return;
      }
      const candidates = posts.length > 1 ? posts.filter((post) => post.id !== lastId) : posts;
      const post = candidates[Math.floor(Math.random() * candidates.length)];
      lastId = post.id;
      link.href = post.url;
      link.setAttribute('aria-label', `Đọc bài ${post.title} của ${post.author_name}`);
      text.textContent = `${post.author_name} chia sẻ: ${post.title}`;
      text.classList.remove('is-running');
      banner.hidden = false;
      const distance = track.clientWidth + text.scrollWidth;
      text.style.setProperty('--banner-duration', `${Math.max(8, distance / 110)}s`);
      text.style.setProperty('--banner-start', `${track.clientWidth}px`);
      // Restart the single pass, including when the same post is shown again.
      void text.offsetWidth;
      text.classList.add('is-running');
      if (reducedMotion.matches) endTimer = setTimeout(hide, 8000);
    } catch {
      hide();
    } finally {
      loading = false;
    }
  }

  text.addEventListener('animationend', (event) => {
    if (event.animationName === 'forum-banner-pass') hide();
  });
  reducedMotion.addEventListener('change', () => {
    if (!banner.hidden) hide();
  });
  document.addEventListener('visibilitychange', () => {
    clearTimeout(nextTimer);
    clearTimeout(endTimer);
    banner.hidden = true;
    if (!document.hidden) nextTimer = setTimeout(showNext, 20000);
  });
  showNext();
})();
