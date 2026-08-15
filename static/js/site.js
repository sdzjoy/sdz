(() => {
  const root = document.documentElement;
  const themeButton = document.querySelector(".theme-toggle");
  const navButton = document.querySelector(".nav-toggle");
  const navigation = document.querySelector(".site-nav");

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

  themeButton?.addEventListener("click", () => {
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const currentDark = root.dataset.theme ? root.dataset.theme === "dark" : systemDark;
    const nextTheme = currentDark ? "light" : "dark";
    root.dataset.theme = nextTheme;
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
})();
