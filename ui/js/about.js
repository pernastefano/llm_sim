/* ═══════════════════════════════════════════════════════════════════════
   about.js — How-it-works page logic (ToC active link on scroll)
   Depends on: i18n.js (must be loaded first)
═══════════════════════════════════════════════════════════════════════ */

const sections = document.querySelectorAll(".section[id]");
const tocLinks  = document.querySelectorAll(".toc a[href^='#']");

const observer = new IntersectionObserver(
  entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        tocLinks.forEach(a => {
          a.classList.toggle("active", a.getAttribute("href") === "#" + entry.target.id);
        });
      }
    });
  },
  { rootMargin: "-20% 0px -70% 0px" }
);

sections.forEach(s => observer.observe(s));

/* ── Probability bar animation (animate from 0 → target on scroll) ─── */
const barObserver = new IntersectionObserver(
  entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.querySelectorAll(".prob-bar-fill").forEach(fill => {
          fill.classList.add("animated");
        });
        barObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.4 }
);

const probDemo = document.querySelector(".prob-demo");
if (probDemo) barObserver.observe(probDemo);
