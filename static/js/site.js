(() => {
  const root = document.documentElement;
  const themeButton = document.querySelector(".theme-toggle");
  const navButton = document.querySelector(".nav-toggle");
  const navigation = document.querySelector(".site-nav");
  const header = document.querySelector(".site-header");
  const subsiteSwitcher = document.querySelector(".subsite-switcher");
  const themeColor = document.querySelector('meta[name="theme-color"]');

  root.classList.add("js");
  let storedTheme;
  try {
    storedTheme = window.localStorage.getItem("sdzjoy-theme");
  } catch {
    storedTheme = null;
  }
  if (storedTheme === "light" || storedTheme === "dark") {
    root.dataset.theme = storedTheme;
  }

  const currentTheme = () => root.dataset.theme || "light";
  const updateThemeControls = () => {
    const isDark = currentTheme() === "dark";
    themeButton?.setAttribute("aria-pressed", String(isDark));
    themeButton?.setAttribute("aria-label", isDark ? "切换到浅色主题" : "切换到深色主题");
    themeButton?.setAttribute("title", isDark ? "切换到浅色主题" : "切换到深色主题");
    themeColor?.setAttribute("content", isDark ? "#1c1b18" : "#faf9f5");
  };

  updateThemeControls();

  themeButton?.addEventListener("click", () => {
    const currentDark = currentTheme() === "dark";
    const nextTheme = currentDark ? "light" : "dark";
    root.dataset.theme = nextTheme;
    updateThemeControls();
    try {
      window.localStorage.setItem("sdzjoy-theme", nextTheme);
    } catch {
      // Theme switching still works for this page if storage is unavailable.
    }
  });

  navButton?.addEventListener("click", () => {
    const isOpen = navigation?.classList.toggle("is-open") ?? false;
    navButton.setAttribute("aria-expanded", String(isOpen));
  });

  navigation?.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      navigation.classList.remove("is-open");
      navButton?.setAttribute("aria-expanded", "false");
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const navigationWasOpen = navigation?.classList.contains("is-open") ?? false;
    navigation?.classList.remove("is-open");
    navButton?.setAttribute("aria-expanded", "false");
    subsiteSwitcher?.removeAttribute("open");
    if (navigationWasOpen) navButton?.focus();
  });

  document.addEventListener("click", (event) => {
    if (subsiteSwitcher?.open && !subsiteSwitcher.contains(event.target)) {
      subsiteSwitcher.removeAttribute("open");
    }
  });

  let scrollFrame;
  const updateHeader = () => {
    header?.classList.toggle("is-scrolled", window.scrollY > 8);
    scrollFrame = null;
  };
  window.addEventListener(
    "scroll",
    () => {
      if (!scrollFrame) scrollFrame = window.requestAnimationFrame(updateHeader);
    },
    { passive: true },
  );
  updateHeader();
})();
