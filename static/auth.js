(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const banner = $("#banner");

  function showBanner(message, type) {
    banner.textContent = message;
    banner.className = "banner " + type;
    banner.classList.remove("hidden");
  }
  function hideBanner() {
    banner.classList.add("hidden");
  }

  const tabBtns = document.querySelectorAll(".tab-btn");
  const panels = { login: $("#loginForm"), register: $("#registerForm") };

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      Object.entries(panels).forEach(([key, el]) => {
        el.classList.toggle("hidden", key !== btn.dataset.tab);
      });
      hideBanner();
    });
  });

  $("#loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    hideBanner();
    const email = $("#loginEmail").value.trim();
    const password = $("#loginPassword").value;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        showBanner(data.error || "Could not sign in.", "error");
        return;
      }
      window.location.href = data.must_change_password ? "/change-password" : "/";
    } catch (err) {
      showBanner("Network error while signing in.", "error");
    }
  });

  $("#registerForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    hideBanner();
    const email = $("#registerEmail").value.trim();
    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) {
        showBanner(data.error || "Could not create account.", "error");
        return;
      }
      let msg = data.message;
      if (data.dev_password) {
        msg += ` Temporary password: ${data.dev_password}`;
      }
      showBanner(msg, "success");
      // Pre-fill and switch to the login tab so they can sign in right away.
      $("#loginEmail").value = email;
      document.querySelector('.tab-btn[data-tab="login"]').click();
      // Re-show the banner since switching tabs above clears it.
      showBanner(msg, "success");
    } catch (err) {
      showBanner("Network error while creating your account.", "error");
    }
  });
})();
